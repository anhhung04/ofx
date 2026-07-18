"""Tests for ``ofx flow tasks run`` CLI command and TaskRunHandler."""

from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

from rich.console import Console
from typer.testing import CliRunner

class TestParseOptArgs:
    """Verify CLI --opt parsing into a dict."""

    def test_key_value_string(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["key=value"])
        assert result == {"key": "value"}

    def test_key_value_int(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["ports=1000"])
        assert result == {"ports": 1000}

    def test_key_value_float(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["delay=2.5"])
        assert result == {"delay": 2.5}

    def test_key_value_bool_true(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["verbose=true"])
        assert result == {"verbose": True}

    def test_key_value_bool_false(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["verbose=false"])
        assert result == {"verbose": False}

    def test_bare_key_is_true(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["verbose"])
        assert result == {"verbose": True}

    def test_multiple_opts(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["threads=50", "verbose", "target=10.0.0.1"])
        assert result == {"threads": 50, "verbose": True, "target": "10.0.0.1"}

    def test_empty_list(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args([])
        assert result == {}

    def test_string_with_equals_in_value(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["header=X-Auth=secret123"])
        assert result == {"header": "X-Auth=secret123"}

    def test_whitespace_handling(self):
        from ofx.commands.flow.run_task import parse_opt_args

        result = parse_opt_args(["  key = value  "])
        assert result == {"key": "value"}

class TestTaskRunHandler:
    """Test the task run handler logic."""

    def _patch_success_run(self, monkeypatch, *, typed_outputs=None, stdout=""):
        import ofx.commands.flow.run_task as run_task

        console = Console(record=True, width=120)
        typed_outputs = typed_outputs or []

        class FakeTask:
            pass

        class FakeRunner:
            def __init__(self, model, ctx):
                self.model = model
                self.ctx = ctx

            async def run(self):
                return SimpleNamespace(status=SimpleNamespace(value="completed"), error="")

            async def reg_get(self, _key):
                return {
                    "typed_outputs": typed_outputs,
                    "stdout": stdout,
                    "exit_code": 0,
                }

        monkeypatch.setattr(run_task, "TaskRunner", FakeRunner)
        monkeypatch.setattr("ofx.tasks.TaskRegistry.get", lambda _name: FakeTask)
        monkeypatch.setattr("ofx.settings.get_console", lambda: console)
        monkeypatch.setattr(
            "ofx.profiles.manager.get_profile_manager",
            lambda: SimpleNamespace(resolve_or_default=lambda _name: None),
        )
        return console

    def test_unknown_task_returns_error(self):
        from ofx.commands.flow.run_task import TaskRunHandler

        handler = TaskRunHandler(
            task_name="nonexistent_tool_xyz",
            target="example.com",
            opts={},
        )
        result = asyncio.run(handler.run())
        assert result == 1

    def test_run_displays_useful_columns_for_typed_outputs(self, monkeypatch):
        from ofx.commands.flow.run_task import TaskRunHandler

        console = self._patch_success_run(
            monkeypatch,
            typed_outputs=[
                {"_type": "port", "ip": "10.0.0.1", "port": 80, "protocol": "tcp"}
            ],
        )

        result = asyncio.run(TaskRunHandler("nmap", "10.0.0.1", {}).run())

        assert result == 0
        output = console.export_text()
        assert "port (1)" in output
        assert "ip" in output
        assert "port" in output
        assert "protocol" in output
        assert "10.0.0.1" in output

    def test_run_falls_back_to_item_keys_for_unknown_output_type(self, monkeypatch):
        from ofx.commands.flow.run_task import TaskRunHandler

        console = self._patch_success_run(
            monkeypatch,
            typed_outputs=[{"_type": "custom", "foo": "bar", "baz": 42, "_internal": "skip"}],
        )

        result = asyncio.run(TaskRunHandler("nmap", "10.0.0.1", {}).run())

        assert result == 0
        output = console.export_text()
        assert "custom (1)" in output
        assert "foo" in output
        assert "baz" in output
        assert "_internal" not in output

    def test_handler_creates_with_defaults(self):
        from ofx.commands.flow.run_task import TaskRunHandler

        handler = TaskRunHandler(
            task_name="nmap",
            target="10.0.0.1",
            opts={"ports": "80,443"},
        )
        assert handler.task_name == "nmap"
        assert handler.target == "10.0.0.1"
        assert handler.opts == {"ports": "80,443"}
        assert handler.timeout == 60
        assert handler.store_creds is False
        assert handler.json_output is False

    def test_handler_with_all_options(self):
        from ofx.commands.flow.run_task import TaskRunHandler

        handler = TaskRunHandler(
            task_name="httpx",
            target="targets.txt",
            opts={"threads": 50},
            profile="stealth",
            timeout=30,
            output="/tmp/results",
            store_creds=True,
            json_output=True,
        )
        assert handler.profile_name == "stealth"
        assert handler.timeout == 30
        assert handler.output == "/tmp/results"
        assert handler.store_creds is True
        assert handler.json_output is True

    def test_profile_time_window_blocks_task_run(self, monkeypatch):
        from ofx.commands.flow.run_task import TaskRunHandler

        console = Console(record=True, width=120)
        profile = SimpleNamespace(
            time_window=SimpleNamespace(enabled=True),
            model_dump=lambda: {"name": "stealth"},
        )

        monkeypatch.setattr("ofx.tasks.TaskRegistry.get", lambda _name: object)
        monkeypatch.setattr("ofx.settings.get_console", lambda: console)
        monkeypatch.setattr(
            "ofx.profiles.manager.get_profile_manager",
            lambda: SimpleNamespace(resolve_or_default=lambda _name: profile),
        )
        monkeypatch.setattr(
            "ofx.profiles.time_window.check_time_window",
            lambda _window: {
                "allowed": False,
                "remaining_minutes": 0,
                "message": "Current time is outside the allowed window",
            },
        )

        result = asyncio.run(TaskRunHandler("nmap", "10.0.0.1", {}, profile="stealth").run())

        assert result == 1
        assert "outside the allowed window" in console.export_text()

class TestTaskRunCommand:
    def test_run_command_uses_module_parse_and_handler(self, monkeypatch):
        task_commands = importlib.import_module("ofx.commands.flow.task_commands")
        calls: list[tuple[list[str], dict]] = []

        class FakeHandler:
            def __init__(self, **kwargs):
                calls.append(([], kwargs))

            async def run(self):
                return 0

        def broken_parse(_opts):
            raise RuntimeError("should not use ofx.commands.flow.run_task.parse_opt_args")

        def broken_handler(**_kwargs):
            raise RuntimeError("should not use ofx.commands.flow.run_task.TaskRunHandler")

        monkeypatch.setattr(task_commands, "parse_opt_args", lambda opts: {"mode": "patched"}, raising=False)
        monkeypatch.setattr(task_commands, "TaskRunHandler", FakeHandler, raising=False)
        monkeypatch.setattr("ofx.commands.flow.run_task.parse_opt_args", broken_parse)
        monkeypatch.setattr("ofx.commands.flow.run_task.TaskRunHandler", broken_handler)

        result = CliRunner().invoke(
            task_commands.app,
            ["run", "httpx", "example.com", "--opt", "mode=cli"],
        )

        assert result.exit_code == 0
        assert calls == [
            (
                [],
                {
                    "task_name": "httpx",
                    "target": "example.com",
                    "opts": {"mode": "patched"},
                    "profile": "",
                    "timeout": 60,
                    "output": "",
                    "store_creds": False,
                    "json_output": False,
                },
            )
        ]

    def test_run_command_exits_with_handler_code(self, monkeypatch):
        task_commands = importlib.import_module("ofx.commands.flow.task_commands")

        class FakeHandler:
            def __init__(self, **kwargs):
                pass

            async def run(self):
                return 3

        def broken_parse(_opts):
            raise RuntimeError("should not use ofx.commands.flow.run_task.parse_opt_args")

        def broken_handler(**_kwargs):
            raise RuntimeError("should not use ofx.commands.flow.run_task.TaskRunHandler")

        monkeypatch.setattr(task_commands, "parse_opt_args", lambda opts: {}, raising=False)
        monkeypatch.setattr(task_commands, "TaskRunHandler", FakeHandler, raising=False)
        monkeypatch.setattr("ofx.commands.flow.run_task.parse_opt_args", broken_parse)
        monkeypatch.setattr("ofx.commands.flow.run_task.TaskRunHandler", broken_handler)

        result = CliRunner().invoke(task_commands.app, ["run", "httpx", "example.com"])

        assert result.exit_code == 3

    def test_list_command_uses_module_registry_and_console(self, monkeypatch):
        task_commands = importlib.import_module("ofx.commands.flow.task_commands")
        console = Console(record=True, width=120)

        class FakeTask:
            def __init__(self):
                self.category = "web/"
                self.description = "Fake task"

            def check_installed(self):
                return True

        fake_registry = SimpleNamespace(
            list_tasks=lambda: ["fake"],
            get=lambda name: FakeTask if name == "fake" else None,
            get_by_category=lambda category: [("fake", FakeTask)] if category == "web/" else [],
        )

        monkeypatch.setattr(task_commands, "get_console", lambda: console, raising=False)
        monkeypatch.setattr(task_commands, "TaskRegistry", fake_registry, raising=False)
        monkeypatch.setattr("ofx.settings.get_console", lambda: None)
        monkeypatch.setattr("ofx.tasks.TaskRegistry", SimpleNamespace(list_tasks=lambda: (_ for _ in ()).throw(RuntimeError("wrong registry"))), raising=False)

        result = CliRunner().invoke(task_commands.app, ["list", "--category", "web/"])

        assert result.exit_code == 0
        output = console.export_text()
        assert "Registered Tasks" in output
        assert "fake" in output
        assert "Fake task" in output

    def test_info_command_uses_module_registry_and_console(self, monkeypatch):
        task_commands = importlib.import_module("ofx.commands.flow.task_commands")
        console = Console(record=True, width=120)

        fake_opt = SimpleNamespace(flag="--threads", is_flag=False, type=int, help="Thread count")

        class FakeTask:
            def __init__(self):
                self.name = "fake"
                self.description = "Fake task"
                self.category = "web/"
                self.cmd = "fakebin"
                self.output_types = []
                self.opts = {"threads": fake_opt}
                self.install_cmd = "brew install fake"
                self.supports_streaming = False
                self.export_output = False
                self.extra_flags = []
                self.success_codes = [0]

            def check_installed(self):
                return True

        fake_registry = SimpleNamespace(
            get=lambda name: FakeTask if name == "fake" else None,
            list_tasks=lambda: ["fake"],
        )

        monkeypatch.setattr(task_commands, "get_console", lambda: console, raising=False)
        monkeypatch.setattr(task_commands, "TaskRegistry", fake_registry, raising=False)
        monkeypatch.setattr("ofx.settings.get_console", lambda: None)
        monkeypatch.setattr("ofx.tasks.TaskRegistry", SimpleNamespace(get=lambda _name: (_ for _ in ()).throw(RuntimeError("wrong registry"))), raising=False)

        result = CliRunner().invoke(task_commands.app, ["info", "fake"])

        assert result.exit_code == 0
        output = console.export_text()
        assert "Task: fake" in output
        assert "Fake task" in output
        assert "fakebin" in output
        assert "threads" in output

class TestProfileCommonOptInjection:
    """Verify that profile-level settings auto-map to task opts."""

    def _make_runner(self, profile, task_name="httpx", user_opts=None):
        from ofx.runner.context import RunContext
        from ofx.runner.tasks.runner import TaskExecution, TaskRunner

        ctx = RunContext(vars={"profile_model": profile})
        model = TaskExecution(
            task_name=task_name,
            target="example.com",
            opts=user_opts or {},
        )
        runner = TaskRunner(model, ctx)
        from ofx.tasks import TaskRegistry

        task_cls = TaskRegistry.get(task_name)
        if task_cls:
            runner._task = task_cls()
        return runner

    def test_proxy_injected(self):
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(proxy="socks5://127.0.0.1:9050")
        runner = self._make_runner(profile, task_name="feroxbuster")
        runner._apply_profile_task_options()
        assert runner.model.opts.get("proxy") == "socks5://127.0.0.1:9050"

    def test_threads_injected(self):
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(threads=5)
        runner = self._make_runner(profile)
        runner._apply_profile_task_options()
        assert runner.model.opts.get("threads") == 5

    def test_rate_limit_injected(self):
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(rate_limit=30)
        runner = self._make_runner(profile)
        runner._apply_profile_task_options()
        assert runner.model.opts.get("rate_limit") == 30

    def test_delay_injected(self):
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(delay=2.0)
        runner = self._make_runner(profile, task_name="katana")
        runner._apply_profile_task_options()
        assert runner.model.opts.get("delay") == 2.0

    def test_user_opts_win_over_profile(self):
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(threads=5, rate_limit=30)
        runner = self._make_runner(profile, user_opts={"threads": 100})
        runner._apply_profile_task_options()
        assert runner.model.opts["threads"] == 100
        assert runner.model.opts.get("rate_limit") == 30

    def test_zero_values_not_injected(self):
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(threads=0, rate_limit=0)
        runner = self._make_runner(profile)
        runner._apply_profile_task_options()
        assert "threads" not in runner.model.opts
        assert "rate_limit" not in runner.model.opts

    def test_empty_string_not_injected(self):
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(proxy="")
        runner = self._make_runner(profile)
        runner._apply_profile_task_options()
        assert "proxy" not in runner.model.opts

    def test_task_without_matching_opt_skipped(self):
        """Profile proxy is not injected into tasks that don't declare a proxy opt."""
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(proxy="socks5://127.0.0.1:9050")
        runner = self._make_runner(profile, task_name="whois")
        runner._apply_profile_task_options()
        assert "proxy" not in runner.model.opts

    def test_combined_profile_and_task_options(self):
        """Profile common fields + per-task overrides merge correctly."""
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(
            threads=5,
            proxy="socks5://127.0.0.1:9050",
            task_options={"feroxbuster": {"insecure": True}},
        )
        runner = self._make_runner(profile, task_name="feroxbuster")
        runner._apply_profile_task_options()
        assert runner.model.opts.get("threads") == 5
        assert runner.model.opts.get("proxy") == "socks5://127.0.0.1:9050"
        assert runner.model.opts.get("insecure") is True

class TestListTasks:
    """Verify the ``ofx flow tasks list`` command logic."""

    def test_list_returns_all_registered(self):
        from ofx.tasks import TaskRegistry

        names = TaskRegistry.list_tasks()
        assert len(names) > 20, "Expected many registered tasks"
        assert "nmap" in names
        assert "httpx" in names

    def test_get_by_category_filters(self):
        from ofx.tasks import TaskRegistry

        port_tasks = TaskRegistry.get_by_category("port/")
        names = [n for n, _ in port_tasks]
        assert "nmap" in names
        for _name, cls in port_tasks:
            assert cls is not None
            assert cls().category.startswith("port/")

    def test_get_by_category_empty(self):
        from ofx.tasks import TaskRegistry

        results = TaskRegistry.get_by_category("nonexistent_category_xyz/")
        assert results == []

class TestTaskInfo:
    """Verify task info display data for key tasks."""

    def test_nmap_basic_info(self):
        from ofx.tasks import TaskRegistry

        cls = TaskRegistry.get("nmap")
        assert cls is not None
        task = cls()
        assert task.name == "nmap"
        assert task.cmd == "nmap"
        assert task.category.startswith("port/")
        assert len(task.opts) > 0
        assert len(task.output_types) > 0

    def test_httpx_has_streaming(self):
        from ofx.tasks import TaskRegistry

        cls = TaskRegistry.get("httpx")
        assert cls is not None
        task = cls()
        assert task.supports_streaming is True

    def test_nmap_no_streaming(self):
        from ofx.tasks import TaskRegistry

        cls = TaskRegistry.get("nmap")
        assert cls is not None
        task = cls()
        assert task.supports_streaming is False

    def test_task_capabilities_section_data(self):
        """Verify the data that powers the capabilities section in task_info CLI."""
        from ofx.tasks import TaskRegistry

        cls = TaskRegistry.get("nuclei")
        assert cls is not None
        task = cls()
        assert task.supports_streaming is True
        assert len(task.output_types) > 0
        assert isinstance(task.success_codes, list)

    def test_unknown_task_returns_none(self):
        from ofx.tasks import TaskRegistry

        cls = TaskRegistry.get("nonexistent_tool_xyz_abc")
        assert cls is None

    def test_task_extra_flags(self):
        """Tasks with extra_flags should expose them for CLI display."""
        from ofx.tasks import TaskRegistry

        for name in TaskRegistry.list_tasks():
            cls = TaskRegistry.get(name)
            if cls is not None:
                task = cls()
                if task.extra_flags:
                    assert isinstance(task.extra_flags, list)
                    assert all(isinstance(f, str) for f in task.extra_flags)
                    return
        cls = TaskRegistry.get("nmap")
        task = cls()
        assert hasattr(task, "extra_flags")
