"""Tests for Task base class, registry, step model, command building, flags, and defaults."""

from pathlib import Path

import pytest

from ofx.models.step import RunType, Step
from ofx.tasks import (
    OptDef,
    Port,
    Task,
    TaskRegistry,
    Url,
)


# ── DummyTask for TestTaskBase ─────────────────────────────────────────────


class DummyTask(Task):
    name = "dummy"
    cmd = "echo"
    description = "Test task"
    category = "test/unit"
    install_cmd = "true"
    output_types = [Url]

    opts = {
        "verbose": OptDef(flag="-v", is_flag=True, help="Verbose"),
        "count": OptDef(flag="-c", type=int, help="Count"),
        "output": OptDef(flag="-o", type=str, help="Output file"),
    }

    input_flag = "-t"

    def parse_output(self, stdout, stderr, output_file=None):
        return [Url(url=line.strip()) for line in stdout.splitlines() if line.strip()]


# ── Task Base ──────────────────────────────────────────────────────────────


class TestTaskBase:
    def test_build_command_basic(self):
        t = DummyTask()
        cmd, out = t.build_command("target.com")
        assert "echo" in cmd
        assert "-t target.com" in cmd

    def test_build_command_with_flag(self):
        t = DummyTask()
        cmd, _ = t.build_command("x.com", verbose=True)
        assert "-v" in cmd

    def test_build_command_with_value_opt(self):
        t = DummyTask()
        cmd, _ = t.build_command("x.com", count=5)
        assert "-c 5" in cmd

    def test_build_command_skips_false_flags(self):
        t = DummyTask()
        cmd, _ = t.build_command("x.com", verbose=False)
        assert "-v" not in cmd

    def test_build_command_skips_none_values(self):
        t = DummyTask()
        cmd, _ = t.build_command("x.com", count=None)
        assert "-c" not in cmd

    def test_build_command_ignores_unknown_opts(self):
        t = DummyTask()
        cmd, _ = t.build_command("x.com", nonexistent="val")
        assert "nonexistent" not in cmd

    def test_parse_output(self):
        t = DummyTask()
        results = t.parse_output("http://a.com\nhttp://b.com\n", "")
        assert len(results) == 2
        assert all(isinstance(r, Url) for r in results)

    def test_check_installed(self):
        t = DummyTask()
        assert t.check_installed()  # echo should exist

    def test_get_install_command(self):
        t = DummyTask()
        assert t.get_install_command() == "true"

    def test_safe_int(self):
        assert Task._safe_int("42") == 42
        assert Task._safe_int("bad") == 0
        assert Task._safe_int(None, 99) == 99

    def test_safe_float(self):
        assert Task._safe_float("3.14") == 3.14
        assert Task._safe_float("bad") == 0.0

    def test_success_codes_default(self):
        t = DummyTask()
        assert t.success_codes == [0]

    def test_success_codes_custom(self):
        class CustomExitTask(DummyTask):
            success_codes = [0, 1, 3]

        t = CustomExitTask()
        assert t.success_codes == [0, 1, 3]

    def test_success_codes_isolated_per_subclass(self):
        """success_codes should not leak between subclasses."""

        class TaskA(DummyTask):
            success_codes = [0, 42]

        class TaskB(DummyTask):
            pass  # inherits default [0]

        assert TaskA().success_codes == [0, 42]
        assert TaskB().success_codes == [0]
        # Mutating TaskA's list must not affect TaskB
        TaskA.success_codes.append(99)
        assert 99 not in TaskB().success_codes


# ── Task Registry ─────────────────────────────────────────────────────────


class TestTaskRegistry:
    def setup_method(self):
        # Force re-load so tasks are always available
        TaskRegistry._ensure_loaded()

    def test_builtin_tasks_registered(self):
        tasks = TaskRegistry.list_tasks()
        assert "nmap" in tasks
        assert "httpx" in tasks
        assert "subfinder" in tasks
        assert "nuclei" in tasks
        assert "ffuf" in tasks

    def test_create_task(self):
        task = TaskRegistry.create("nmap")
        assert task.name == "nmap"
        assert task.cmd == "nmap"

    def test_create_unknown_raises(self):
        with pytest.raises(KeyError, match="not registered"):
            TaskRegistry.create("nonexistent_tool_xyz")

    def test_get_returns_none_for_unknown(self):
        assert TaskRegistry.get("no_such_task") is None

    def test_get_by_category(self):
        port_tasks = TaskRegistry.get_by_category("port/")
        assert any(name == "nmap" for name, _ in port_tasks)

    def test_get_by_category_empty_returns_all(self):
        """Empty category prefix matches all tasks."""
        all_tasks = TaskRegistry.get_by_category("")
        assert len(all_tasks) == len(TaskRegistry.list_tasks())

    def test_register_duplicate_raises(self):
        # Register a fresh name then try to register it again
        name = "_test_dup_check"
        TaskRegistry.unregister(name)  # ensure clean

        @TaskRegistry.register(name)
        class FirstTool(Task):
            name = "first"
            cmd = "true"

            def parse_output(self, stdout, stderr, output_file=None):
                return []

        with pytest.raises(ValueError, match="already registered"):

            @TaskRegistry.register(name)
            class SecondTool(Task):
                name = "second"
                cmd = "true"

                def parse_output(self, stdout, stderr, output_file=None):
                    return []

        TaskRegistry.unregister(name)

    def test_unregister(self):
        @TaskRegistry.register("temp_test_tool")
        class TempTool(Task):
            name = "temp"
            cmd = "true"

            def parse_output(self, stdout, stderr, output_file=None):
                return []

        assert TaskRegistry.get("temp_test_tool") is not None
        TaskRegistry.unregister("temp_test_tool")
        assert TaskRegistry.get("temp_test_tool") is None


# ── Step Model Integration ─────────────────────────────────────────────────


class TestStepModelTask:
    def test_step_with_task_field(self):
        s = Step(task="nmap", **{"with": {"target": "1.2.3.4"}})
        assert s.get_run_type() == RunType.TASK
        assert s.task == "nmap"

    def test_step_task_exclusive(self):
        """task can't coexist with run/script/uses."""
        with pytest.raises(ValueError, match="exactly one"):
            Step(task="nmap", run="echo hi")

    def test_step_task_and_script_exclusive(self):
        with pytest.raises(ValueError, match="exactly one"):
            Step(task="nmap", script="print('hi')")

    def test_step_with_options(self):
        s = Step(
            task="nmap",
            **{
                "with": {
                    "target": "10.0.0.0/24",
                    "ports": "1-1000",
                    "version_detection": True,
                }
            },
        )
        assert s.run_with["target"] == "10.0.0.0/24"
        assert s.run_with["ports"] == "1-1000"

    def test_existing_run_types_still_work(self):
        s1 = Step(run="echo hi")
        assert s1.get_run_type() == RunType.COMMAND

        s2 = Step(script="print('hi')")
        assert s2.get_run_type() == RunType.SCRIPT

        s3 = Step(uses="./other.yml")
        assert s3.get_run_type() == RunType.WORKFLOW


# ── Command Building ──────────────────────────────────────────────────────


class TestCommandBuilding:
    def test_nmap_command(self):
        task = TaskRegistry.create("nmap")
        cmd, out = task.build_command(
            "192.168.1.0/24", ports="22,80,443", version_detection=True
        )
        assert "nmap" in cmd
        assert "-p 22,80,443" in cmd
        assert "-sV" in cmd
        assert "192.168.1.0/24" in cmd
        assert out is not None  # output file created for -oX

    def test_httpx_command(self):
        task = TaskRegistry.create("httpx")
        cmd, out = task.build_command("https://example.com", tech_detect=True)
        assert "httpx" in cmd
        assert "-json" in cmd
        assert "-tech-detect" in cmd

    def test_subfinder_command(self):
        task = TaskRegistry.create("subfinder")
        cmd, _ = task.build_command("example.com", all=True)
        assert "subfinder" in cmd
        assert "-all" in cmd
        assert "-d example.com" in cmd

    def test_nuclei_command(self):
        task = TaskRegistry.create("nuclei")
        cmd, _ = task.build_command("https://target.com", severity="critical,high")
        assert "nuclei" in cmd
        assert "-severity critical,high" in cmd

    def test_ffuf_command(self):
        task = TaskRegistry.create("ffuf")
        cmd, _ = task.build_command(
            "https://target.com/FUZZ",
            wordlist="/usr/share/wordlists/common.txt",
            threads=50,
        )
        assert "ffuf" in cmd
        assert "-w /usr/share/wordlists/common.txt" in cmd
        assert "-t 50" in cmd

    def test_output_file_cleanup(self):
        """Output files are temp files that exist on disk."""
        task = TaskRegistry.create("nmap")
        _, out = task.build_command("x.com")
        assert out is not None
        assert out.exists()
        out.unlink()  # cleanup


# ── Extra Flags Refactor ──────────────────────────────────────────────────


class TestExtraFlags:
    """Verify the DRY refactor: extra_flags are included in build_command."""

    def test_httpx_extra_flags(self):
        task = TaskRegistry.create("httpx")
        cmd, _ = task.build_command("https://example.com")
        assert "-json -silent" in cmd

    def test_subfinder_extra_flags(self):
        task = TaskRegistry.create("subfinder")
        cmd, _ = task.build_command("example.com")
        assert "-silent" in cmd

    def test_nuclei_extra_flags(self):
        task = TaskRegistry.create("nuclei")
        cmd, _ = task.build_command("https://target.com")
        assert "-jsonl -silent" in cmd

    def test_ffuf_extra_flags(self):
        task = TaskRegistry.create("ffuf")
        cmd, _ = task.build_command("https://target.com/FUZZ")
        assert "-noninteractive" in cmd
        assert "-of json" in cmd

    def test_nmap_no_extra_flags(self):
        """Nmap doesn't need extra_flags — it uses the base build_command."""
        task = TaskRegistry.create("nmap")
        cmd, _ = task.build_command("10.0.0.1")
        # Should start with just "nmap" — no extra flags
        assert cmd.startswith("nmap ")


# ── Registry — New Tools ──────────────────────────────────────────────────


class TestNewToolsRegistered:
    def test_all_tools_registered(self):
        expected = [
            "nmap", "httpx", "subfinder", "nuclei", "ffuf",
            "naabu", "katana", "dnsx", "wafw00f", "feroxbuster",
        ]
        for name in expected:
            assert TaskRegistry.get(name) is not None, f"Task '{name}' not registered"

    def test_categories(self):
        port_tasks = TaskRegistry.get_by_category("port/")
        assert len(port_tasks) >= 2  # nmap + naabu

        dns_tasks = TaskRegistry.get_by_category("dns/")
        assert len(dns_tasks) >= 2  # subfinder + dnsx

        url_tasks = TaskRegistry.get_by_category("url/")
        assert len(url_tasks) >= 3  # httpx + ffuf + katana + feroxbuster


# ── Mutable Default Isolation ─────────────────────────────────────────────


class TestMutableDefaults:
    """Verify __init_subclass__ prevents cross-class mutation."""

    def test_extra_flags_isolated_between_subclasses(self):
        """Mutating one task's extra_flags must not affect another."""
        httpx_cls = TaskRegistry.get("httpx")
        nmap_cls = TaskRegistry.get("nmap")
        assert httpx_cls is not None and nmap_cls is not None

        httpx = httpx_cls()
        nmap = nmap_cls()

        original_httpx_flags = list(httpx.extra_flags)
        original_nmap_flags = list(nmap.extra_flags)

        # Mutate httpx's extra_flags (on the class)
        httpx_cls.extra_flags.append("--SHOULD-NOT-LEAK")

        # nmap's extra_flags must be unaffected
        assert "--SHOULD-NOT-LEAK" not in nmap_cls.extra_flags
        assert nmap_cls.extra_flags == original_nmap_flags

        # Restore
        httpx_cls.extra_flags[:] = original_httpx_flags

    def test_opts_isolated_between_subclasses(self):
        """Mutating one task's opts must not affect another."""
        nmap_cls = TaskRegistry.get("nmap")
        subfinder_cls = TaskRegistry.get("subfinder")
        assert nmap_cls is not None and subfinder_cls is not None

        original_nmap_opts = set(nmap_cls.opts.keys())

        nmap_cls.opts["_test_key"] = OptDef(flag="--test")
        assert "_test_key" not in subfinder_cls.opts

        # Restore
        del nmap_cls.opts["_test_key"]
        assert set(nmap_cls.opts.keys()) == original_nmap_opts

    def test_base_task_defaults_unaffected(self):
        """Subclass mutations must not leak back to the Task base."""
        assert Task.extra_flags == []
        assert Task.opts == {}
        assert Task.output_types == []


# ── Pre-flight Binary Check ───────────────────────────────────────────────


class TestPreflightCheck:
    """Verify TaskRunner warns when tool binary is not installed."""

    def test_check_installed_returns_bool(self):
        task = TaskRegistry.create("nmap")
        # Just verify the method returns a bool (actual result depends on system)
        assert isinstance(task.check_installed(), bool)

    def test_get_install_command(self):
        task = TaskRegistry.create("nmap")
        assert task.get_install_command() == "apt install -y nmap"

    def test_get_install_command_none_when_empty(self):
        """A task with no install_cmd returns None."""

        class BareTask(Task):
            name = "bare"
            cmd = "bare"
            install_cmd = ""

            def parse_output(self, stdout, stderr, output_file=None):
                return []

        t = BareTask()
        assert t.get_install_command() is None


# ── OptDef Validation ──────────────────────────────────────────────────


class TestOptDefValidation:
    def test_valid_optdef(self):
        opt = OptDef(flag="-p", type=str, help="Port range")
        assert opt.flag == "-p"

    def test_empty_flag_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            OptDef(flag="")

    def test_whitespace_flag_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            OptDef(flag="   ")
