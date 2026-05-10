"""Tests for ChannelStore and inter-job channel communication."""

import os
import subprocess
import threading
import time
from pathlib import Path

import pytest

from ofx.runner.channels import ChannelStore


@pytest.fixture
def channels_dir(tmp_path):
    """Create a temporary channels directory."""
    d = tmp_path / "channels"
    d.mkdir()
    return d


@pytest.fixture
def store(channels_dir):
    """Create a ChannelStore backed by a temp directory."""
    return ChannelStore(channels_dir)


class TestChannelStoreBasic:
    """Basic publish/get tests for ChannelStore."""

    def test_publish_and_get_dict(self, store):
        store.publish("ch1", {"key": "value"})
        assert store.get("ch1") == {"key": "value"}

    def test_publish_and_get_string(self, store):
        store.publish("ch1", "hello")
        assert store.get("ch1") == "hello"

    def test_publish_and_get_int(self, store):
        store.publish("ch1", 42)
        assert store.get("ch1") == 42

    def test_publish_and_get_float(self, store):
        store.publish("ch1", 3.14)
        assert store.get("ch1") == 3.14

    def test_publish_and_get_bool(self, store):
        store.publish("ch1", True)
        assert store.get("ch1") is True

    def test_publish_and_get_list(self, store):
        store.publish("ch1", [1, "two", 3.0])
        assert store.get("ch1") == [1, "two", 3.0]

    def test_publish_and_get_none(self, store):
        store.publish("ch1", None)
        assert store.get("ch1") is None

    def test_get_nonexistent_channel_returns_none(self, store):
        assert store.get("missing") is None

    def test_overwrite_channel(self, store):
        store.publish("ch1", "first")
        store.publish("ch1", "second")
        assert store.get("ch1") == "second"

    def test_multiple_channels_independent(self, store):
        store.publish("a", 1)
        store.publish("b", 2)
        assert store.get("a") == 1
        assert store.get("b") == 2


class TestChannelStoreSubscribe:
    """Subscribe and wait_for tests."""

    def test_subscribe_yields_on_change(self, store):
        store.publish("ch1", "initial")
        gen = store.subscribe("ch1", poll_interval=0.01)
        assert next(gen) == "initial"

        # Publish new value in background
        def update():
            time.sleep(0.05)
            store.publish("ch1", "updated")

        t = threading.Thread(target=update)
        t.start()

        val = next(gen)
        assert val == "updated"
        t.join()

    def test_wait_for_success(self, store):
        def publish_later():
            time.sleep(0.05)
            store.publish("ch1", "ready")

        t = threading.Thread(target=publish_later)
        t.start()
        result = store.wait_for(
            "ch1", lambda v: v == "ready", timeout=5, poll_interval=0.01
        )
        assert result == "ready"
        t.join()

    def test_wait_for_timeout(self, store):
        with pytest.raises(TimeoutError, match="Timeout waiting for channel"):
            store.wait_for(
                "ch1", lambda v: v == "never", timeout=0.1, poll_interval=0.01
            )


class TestChannelStoreManagement:
    """Delete, list, clear tests."""

    def test_delete_channel(self, store):
        store.publish("ch1", "data")
        assert store.delete("ch1") is True
        assert store.get("ch1") is None

    def test_delete_nonexistent(self, store):
        assert store.delete("nope") is False

    def test_list_channels(self, store):
        store.publish("alpha", 1)
        store.publish("beta", 2)
        channels = sorted(store.list_channels())
        assert channels == ["alpha", "beta"]

    def test_clear(self, store):
        store.publish("a", 1)
        store.publish("b", 2)
        store.clear()
        assert store.list_channels() == []


class TestChannelStoreMtimeCache:
    """Test that mtime-based caching works correctly."""

    def test_cache_returns_same_value_without_reread(self, store):
        store.publish("ch1", "val")
        # First read populates cache
        assert store.get("ch1") == "val"
        # Second read should hit cache (same mtime)
        assert store.get("ch1") == "val"

    def test_cache_invalidated_on_external_write(self, store, channels_dir):
        store.publish("ch1", "original")
        assert store.get("ch1") == "original"

        # Simulate external write (e.g., from bash)
        time.sleep(0.01)  # Ensure mtime changes
        (channels_dir / "ch1").write_text('"modified"')

        assert store.get("ch1") == "modified"


class TestChannelStoreCrossProcess:
    """Test cross-process locking via flock."""

    def test_concurrent_writes_no_corruption(self, channels_dir):
        """Spawn multiple processes writing to the same channel concurrently."""
        script = f"""
import sys
sys.path.insert(0, "{Path(__file__).resolve().parent.parent / "src"}")
from ofx.runner.channels import ChannelStore
store = ChannelStore("{channels_dir}")
for i in range(50):
    store.publish("counter", i)
"""
        procs = []
        for _ in range(4):
            p = subprocess.Popen(
                [os.sys.executable, "-c", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            procs.append(p)

        for p in procs:
            p.wait()

        # After all writes, the file should contain valid JSON
        store = ChannelStore(channels_dir)
        value = store.get("counter")
        assert isinstance(value, int)


class TestBashChannelFunctions:
    """Test that bash ofx_publish / ofx_get work and share the same lock."""

    def test_bash_publish_python_get(self, channels_dir):
        """Publish from bash, read from Python — same flock protocol."""
        bash_script = f"""
export OFX_CHANNELS_DIR="{channels_dir}"

ofx_publish() {{
    local channel="$1"
    shift
    local data="$*"
    local channel_file="$OFX_CHANNELS_DIR/$channel"
    local lock_file="$OFX_CHANNELS_DIR/${{channel}}.lock"
    mkdir -p "$OFX_CHANNELS_DIR"
    (
        flock -x 200
        printf '%s' "$data" > "$channel_file"
    ) 200>"$lock_file"
}}

ofx_publish "test_chan" '"hello from bash"'
"""
        result = subprocess.run(
            ["/bin/bash", "-c", bash_script],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"bash failed: {result.stderr}"

        store = ChannelStore(channels_dir)
        assert store.get("test_chan") == "hello from bash"

    def test_python_publish_bash_get(self, channels_dir):
        """Publish from Python, read from bash."""
        store = ChannelStore(channels_dir)
        store.publish("py_chan", "hello from python")

        bash_script = f"""
export OFX_CHANNELS_DIR="{channels_dir}"

ofx_get() {{
    local channel="$1"
    local channel_file="$OFX_CHANNELS_DIR/$channel"
    local lock_file="$OFX_CHANNELS_DIR/${{channel}}.lock"
    if [ ! -f "$channel_file" ]; then
        return 1
    fi
    (
        flock -s 200
        cat "$channel_file"
    ) 200>"$lock_file"
}}

ofx_get "py_chan"
"""
        result = subprocess.run(
            ["/bin/bash", "-c", bash_script],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"bash failed: {result.stderr}"
        assert result.stdout.strip() == '"hello from python"'

    def test_bash_wait_for(self, channels_dir):
        """Test ofx_wait_for from bash with Python publishing in background."""
        store = ChannelStore(channels_dir)

        def publish_later():
            time.sleep(0.2)
            store.publish("wait_chan", "done")

        t = threading.Thread(target=publish_later)
        t.start()

        bash_script = f"""
export OFX_CHANNELS_DIR="{channels_dir}"

ofx_get() {{
    local channel="$1"
    local channel_file="$OFX_CHANNELS_DIR/$channel"
    local lock_file="$OFX_CHANNELS_DIR/${{channel}}.lock"
    if [ ! -f "$channel_file" ]; then
        return 1
    fi
    (
        flock -s 200
        cat "$channel_file"
    ) 200>"$lock_file"
}}

ofx_wait_for() {{
    local channel="$1"
    local expected="$2"
    local timeout="${{3:-60}}"
    local interval="${{4:-0.1}}"
    local elapsed=0
    while true; do
        local value
        value=$(ofx_get "$channel" 2>/dev/null) || true
        if [ -n "$value" ] && [ "$value" = "$expected" ]; then
            echo "$value"
            return 0
        fi
        sleep "$interval"
        elapsed=$(echo "$elapsed + $interval" | bc)
        if [ "$(echo "$elapsed >= $timeout" | bc)" -eq 1 ]; then
            echo "Timeout waiting for channel" >&2
            return 1
        fi
    done
}}

ofx_wait_for "wait_chan" '"done"' 5 0.1
"""
        result = subprocess.run(
            ["/bin/bash", "-c", bash_script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        t.join()
        assert result.returncode == 0, f"bash failed: {result.stderr}"
        assert '"done"' in result.stdout


class TestScriptRunnerChannelPrimitives:
    """Test that Python script runner supports primitive channel values."""

    @pytest.mark.asyncio
    async def test_script_publish_primitive_string(self):
        from ofx.models.command import Script
        from ofx.runner.commands.command import ScriptRunner
        from ofx.runner.core import RunContext, RunnerStatus

        script_model = Script(
            script="""
publish('str_chan', 'hello world')
val = next(subscribe('str_chan'))
print(f"Got: {val}")
print(f"Type: {type(val).__name__}")
"""
        )
        result = await ScriptRunner(script_model, ctx=RunContext()).run()
        assert result.status == RunnerStatus.COMPLETED
        stdout = result.outputs.get("stdout", "")
        assert "Got: hello world" in stdout
        assert "Type: str" in stdout

    @pytest.mark.asyncio
    async def test_script_publish_primitive_int(self):
        from ofx.models.command import Script
        from ofx.runner.commands.command import ScriptRunner
        from ofx.runner.core import RunContext, RunnerStatus

        script_model = Script(
            script="""
publish('int_chan', 42)
val = next(subscribe('int_chan'))
print(f"Got: {val}")
print(f"Type: {type(val).__name__}")
"""
        )
        result = await ScriptRunner(script_model, ctx=RunContext()).run()
        assert result.status == RunnerStatus.COMPLETED
        stdout = result.outputs.get("stdout", "")
        assert "Got: 42" in stdout
        assert "Type: int" in stdout

    @pytest.mark.asyncio
    async def test_script_publish_dict(self):
        from ofx.models.command import Script
        from ofx.runner.commands.command import ScriptRunner
        from ofx.runner.core import RunContext, RunnerStatus

        script_model = Script(
            script="""
publish('dict_chan', {'key': 'value'})
val = next(subscribe('dict_chan'))
print(f"Got: {val}")
print(f"Type: {type(val).__name__}")
"""
        )
        result = await ScriptRunner(script_model, ctx=RunContext()).run()
        assert result.status == RunnerStatus.COMPLETED
        stdout = result.outputs.get("stdout", "")
        assert "Got: {'key': 'value'}" in stdout
        assert "Type: dict" in stdout

    @pytest.mark.asyncio
    async def test_script_publish_list(self):
        from ofx.models.command import Script
        from ofx.runner.commands.command import ScriptRunner
        from ofx.runner.core import RunContext, RunnerStatus

        script_model = Script(
            script="""
publish('list_chan', [1, 2, 3])
val = next(subscribe('list_chan'))
print(f"Got: {val}")
print(f"Type: {type(val).__name__}")
"""
        )
        result = await ScriptRunner(script_model, ctx=RunContext()).run()
        assert result.status == RunnerStatus.COMPLETED
        stdout = result.outputs.get("stdout", "")
        assert "Got: [1, 2, 3]" in stdout
        assert "Type: list" in stdout
