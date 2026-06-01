import asyncio
import signal
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from ofx.runner import RunContext, RunnerStatus, WorkflowRunner
from ofx.models.workflow import Workflow
from ofx.utils.workflow_utils import find_workflow


def _workflow_from_yaml(yaml_str: str, workflow_path: Path) -> Workflow:
    workflow = Workflow.model_validate(yaml.safe_load(yaml_str))
    workflow.workflow_path = workflow_path
    return workflow


class TestFlowRun:
    @pytest.mark.asyncio
    async def test_build_run_runner_merges_explicit_env_and_workflow_dir(
        self, tmp_path, monkeypatch
    ):
        from ofx.runner.api import _build_run_runner

        workflow_model = SimpleNamespace(
            defaults=SimpleNamespace(durable=None),
            workflow_path=tmp_path / "child" / "workflow.yml",
            env={},
        )
        built_runner = SimpleNamespace()
        built_contexts: list[RunContext] = []

        monkeypatch.setattr(
            "ofx.runner.api.find_workflow",
            lambda workflow, search_paths: workflow_model,
        )
        monkeypatch.setattr("ofx.runner.api.register_secrets", lambda _values: None)
        monkeypatch.setattr("ofx.runner.api.register_sensitive_env", lambda _env: None)
        monkeypatch.setattr(
            "ofx.runner.api.RegistryFactory.create",
            lambda backend, **config: "registry",
        )
        monkeypatch.setattr("ofx.runner.api.WorkflowExecutor", lambda: "executor")
        monkeypatch.setattr(
            "ofx.runner.api.WorkflowRunner",
            lambda workflow, **kwargs: built_contexts.append(kwargs["ctx"]) or built_runner,
        )

        runner, output_dir = await _build_run_runner(
            "wf.yml",
            inputs={"target": "example.com"},
            secrets={"API_KEY": "secret"},
            env={"OFX_TEST_FLAG": "1"},
            output_path=tmp_path,
            workflow_search_paths=[tmp_path / "search"],
            durable_overrides=None,
            vars={"project": "demo"},
            event_sink_path=tmp_path / "events.ndjson",
            registry_backend="memory",
            registry_config=None,
        )

        ctx = built_contexts[0]
        assert runner is built_runner
        assert output_dir == tmp_path
        assert ctx.inputs == {"target": "example.com"}
        assert ctx.secrets == {"API_KEY": "secret"}
        assert ctx.vars == {"project": "demo"}
        assert ctx.envs["OFX_TEST_FLAG"] == "1"
        assert (tmp_path / "search").absolute() in ctx.workflow_dirs
        assert workflow_model.workflow_path.parent.absolute() in ctx.workflow_dirs
        assert ctx.output_path == tmp_path

    @pytest.mark.asyncio
    async def test_build_run_runner_normalizes_search_paths(self, tmp_path, monkeypatch):
        from ofx.runner.api import _build_run_runner

        workflow_model = SimpleNamespace(
            defaults=SimpleNamespace(durable=None),
            workflow_path=tmp_path / "flows" / "wf.yml",
            env={},
        )
        built_runner = SimpleNamespace()
        seen: list[tuple[str, tuple[Path, ...]]] = []

        def _find_workflow(workflow: str, search_paths: tuple[Path, ...]):
            seen.append((workflow, search_paths))
            return workflow_model

        monkeypatch.setattr("ofx.runner.api.find_workflow", _find_workflow)
        monkeypatch.setattr("ofx.runner.api.register_secrets", lambda _values: None)
        monkeypatch.setattr("ofx.runner.api.register_sensitive_env", lambda _env: None)
        monkeypatch.setattr("ofx.runner.api.RegistryFactory.create", lambda backend, **config: "registry")
        monkeypatch.setattr("ofx.runner.api.WorkflowExecutor", lambda: "executor")
        monkeypatch.setattr("ofx.runner.api.WorkflowRunner", lambda workflow, **kwargs: built_runner)

        result = await _build_run_runner(
            "wf.yml",
            inputs=None,
            secrets={},
            env=None,
            output_path=tmp_path,
            workflow_search_paths=[tmp_path, str(tmp_path / "extra")],
            durable_overrides=None,
            vars=None,
            event_sink_path=None,
            registry_backend="memory",
            registry_config=None,
        )

        assert result[0] is built_runner
        assert seen == [("wf.yml", (tmp_path, tmp_path / "extra"))]

    @pytest.mark.asyncio
    async def test_build_run_runner_handles_explicit_and_generated_output_dirs(self, tmp_path, monkeypatch):
        from ofx.runner.api import _build_run_runner

        workflow_model = SimpleNamespace(
            defaults=SimpleNamespace(durable=None),
            workflow_path=tmp_path / "flows" / "wf.yml",
            env={},
        )
        built_runner = SimpleNamespace()

        monkeypatch.setattr("ofx.runner.api.find_workflow", lambda workflow, search_paths: workflow_model)

        monkeypatch.setattr("ofx.runner.api.register_secrets", lambda _values: None)
        monkeypatch.setattr("ofx.runner.api.register_sensitive_env", lambda _env: None)
        monkeypatch.setattr("ofx.runner.api.RegistryFactory.create", lambda backend, **config: "registry")
        monkeypatch.setattr("ofx.runner.api.WorkflowExecutor", lambda: "executor")
        monkeypatch.setattr("ofx.runner.api.WorkflowRunner", lambda workflow, **kwargs: built_runner)

        explicit = tmp_path / "explicit"
        result = await _build_run_runner(
            "wf.yml",
            inputs=None,
            secrets={},
            env=None,
            output_path=explicit,
            workflow_search_paths=[tmp_path],
            durable_overrides=None,
            vars=None,
            event_sink_path=None,
            registry_backend="memory",
            registry_config=None,
        )
        assert result == (built_runner, explicit)
        assert explicit.is_dir()

        class _FrozenNow:
            @staticmethod
            def now():
                class _Stamp:
                    @staticmethod
                    def strftime(_fmt: str) -> str:
                        return "01-02-2026_030405"

                return _Stamp()

        monkeypatch.setattr("ofx.runner.api.datetime", _FrozenNow)
        monkeypatch.setattr("ofx.runner.api.ensure_dir", lambda _path: tmp_path)
        result = await _build_run_runner(
            "wf.yml",
            inputs=None,
            secrets={},
            env=None,
            output_path=None,
            workflow_search_paths=[tmp_path],
            durable_overrides=None,
            vars=None,
            event_sink_path=None,
            registry_backend="memory",
            registry_config=None,
        )
        generated = result[1]
        assert generated.name.startswith("run_01-02-2026_030405_")

    @pytest.mark.asyncio
    async def test_build_run_runner_loads_declared_and_template_secrets(
        self, monkeypatch, tmp_path
    ):
        from ofx.runner.api import _build_run_runner

        workflow = _workflow_from_yaml(
            """
            name: test
            call:
              secrets:
                API_KEY:
                  required: true
            env:
              AUTH: "${{ secrets.API_KEY }}"
            jobs:
              scan:
                steps:
                  - run: "echo ${{ secrets.DB_PASS }} ${{ secrets['TOKEN'] }}"
            """,
            tmp_path / "flows" / "wf.yml",
        )
        needed_calls: list[set[str]] = []

        monkeypatch.setattr("ofx.runner.api.find_workflow", lambda workflow_name, search_paths: workflow)
        monkeypatch.setattr(
            "ofx.runner.api.load_secrets_by_keys",
            lambda needed, secrets_dir=None: needed_calls.append(set(needed)) or {},
        )
        monkeypatch.setattr("ofx.runner.api.register_secrets", lambda _values: None)
        monkeypatch.setattr("ofx.runner.api.register_sensitive_env", lambda _env: None)
        monkeypatch.setattr("ofx.runner.api.RegistryFactory.create", lambda backend, **config: "registry")
        monkeypatch.setattr("ofx.runner.api.WorkflowExecutor", lambda: "executor")
        monkeypatch.setattr("ofx.runner.api.WorkflowRunner", lambda workflow, **kwargs: SimpleNamespace())

        await _build_run_runner(
            "wf.yml",
            inputs=None,
            secrets=None,
            env=None,
            output_path=tmp_path,
            workflow_search_paths=[tmp_path],
            durable_overrides=None,
            vars=None,
            event_sink_path=None,
            registry_backend="memory",
            registry_config=None,
        )

        assert needed_calls == [{"API_KEY", "DB_PASS", "TOKEN"}]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("workflow_yaml", "expected_needed"),
        [
            (
                """
                name: test
                jobs:
                  a:
                    steps:
                      - run: "echo ${{ secrets.API_KEY }}"
                """,
                {"API_KEY"},
            ),
            (
                """
                name: test
                jobs:
                  a:
                    steps:
                      - run: 'echo ${{ secrets["DB_PASS"] }}'
                """,
                {"DB_PASS"},
            ),
            (
                """
                name: test
                jobs:
                  a:
                    steps:
                      - run: "curl -H 'Authorization: ${{ secrets.TOKEN }}' ${{ secrets.URL }}"
                  b:
                    steps:
                      - run: "psql ${{ secrets.DB_CONN }}"
                """,
                {"TOKEN", "URL", "DB_CONN"},
            ),
            (
                """
                name: test
                env:
                  API_KEY: "${{ secrets.MY_API_KEY }}"
                jobs:
                  a:
                    steps:
                      - run: echo $API_KEY
                """,
                {"MY_API_KEY"},
            ),
            (
                """
                name: test
                jobs:
                  a:
                    steps:
                      - run: echo $TOKEN
                        env:
                          TOKEN: "${{ secrets.GH_TOKEN }}"
                """,
                {"GH_TOKEN"},
            ),
            (
                """
                name: test
                jobs:
                  a:
                    steps:
                      - run: "${{ secrets.KEY }} and ${{ secrets.KEY }}"
                  b:
                    steps:
                      - run: "${{ secrets.KEY }}"
                """,
                {"KEY"},
            ),
        ],
    )
    async def test_build_run_runner_loads_template_secret_refs(
        self, monkeypatch, tmp_path, workflow_yaml, expected_needed
    ):
        from ofx.runner.api import _build_run_runner

        workflow = _workflow_from_yaml(
            workflow_yaml,
            tmp_path / "flows" / "wf.yml",
        )
        needed_calls: list[set[str]] = []

        monkeypatch.setattr("ofx.runner.api.find_workflow", lambda workflow_name, search_paths: workflow)
        monkeypatch.setattr(
            "ofx.runner.api.load_secrets_by_keys",
            lambda needed, secrets_dir=None: needed_calls.append(set(needed)) or {},
        )
        monkeypatch.setattr("ofx.runner.api.register_secrets", lambda _values: None)
        monkeypatch.setattr("ofx.runner.api.register_sensitive_env", lambda _env: None)
        monkeypatch.setattr("ofx.runner.api.RegistryFactory.create", lambda backend, **config: "registry")
        monkeypatch.setattr("ofx.runner.api.WorkflowExecutor", lambda: "executor")
        monkeypatch.setattr("ofx.runner.api.WorkflowRunner", lambda workflow, **kwargs: SimpleNamespace())

        await _build_run_runner(
            "wf.yml",
            inputs=None,
            secrets=None,
            env=None,
            output_path=tmp_path,
            workflow_search_paths=[tmp_path],
            durable_overrides=None,
            vars=None,
            event_sink_path=None,
            registry_backend="memory",
            registry_config=None,
        )

        assert needed_calls == [expected_needed]

    @pytest.mark.asyncio
    async def test_build_run_runner_uses_secret_overrides_or_empty_on_failure(self, monkeypatch, tmp_path):
        from ofx.runner.api import _build_run_runner

        workflow = _workflow_from_yaml(
            """
            name: test
            env:
              API_TOKEN: secret
            jobs:
              scan:
                steps:
                  - run: "echo ${{ secrets.API_KEY }}"
            """,
            tmp_path / "flows" / "wf.yml",
        )
        built_runner = SimpleNamespace()
        built_contexts: list[RunContext] = []
        secret_calls: list[dict[str, str]] = []
        env_calls: list[dict[str, str]] = []

        warnings: list[tuple[str, Exception]] = []
        monkeypatch.setattr("ofx.runner.api.load_secrets_by_keys", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
        monkeypatch.setattr("ofx.runner.api.logger.warning", lambda fmt, exc: warnings.append((fmt, exc)))
        monkeypatch.setattr("ofx.runner.api.find_workflow", lambda workflow_name, search_paths: workflow)
        monkeypatch.setattr("ofx.runner.api.register_secrets", lambda values: secret_calls.append(dict(values)))
        monkeypatch.setattr("ofx.runner.api.register_sensitive_env", lambda env: env_calls.append(dict(env)))
        monkeypatch.setattr("ofx.runner.api.RegistryFactory.create", lambda backend, **config: "registry")
        monkeypatch.setattr("ofx.runner.api.WorkflowExecutor", lambda: "executor")
        monkeypatch.setattr(
            "ofx.runner.api.WorkflowRunner",
            lambda workflow_obj, **kwargs: built_contexts.append(kwargs["ctx"]) or built_runner,
        )

        result = await _build_run_runner(
            "wf.yml",
            inputs=None,
            secrets=None,
            env=None,
            output_path=tmp_path,
            workflow_search_paths=[tmp_path],
            durable_overrides=None,
            vars=None,
            event_sink_path=None,
            registry_backend="memory",
            registry_config=None,
        )

        assert result == (built_runner, tmp_path)
        assert built_contexts[0].secrets == {}
        assert secret_calls == []
        assert env_calls == [{"API_TOKEN": "secret"}]
        assert tmp_path.exists()
        assert warnings[0][0] == "Failed to load secrets: %s (continuing without secrets)"

    def test_run_workflow_registers_signal_handlers_and_returns_partial_result(
        self, monkeypatch
    ):
        from ofx.runner.api import run_workflow

        warnings: list[object] = []
        monkeypatch.setattr("ofx.runner.api.logger.warning", lambda *args: warnings.append(args if len(args) > 1 else args[0]))

        loop_calls: list[tuple[str, int]] = []
        installed: list[tuple[object, int]] = []

        class _Loop:
            def add_signal_handler(self, sig, callback, arg):
                loop_calls.append(("add", sig))
                installed.append((callback, arg))

            def remove_signal_handler(self, sig):
                loop_calls.append(("remove", sig))

        loop = _Loop()
        thread = object()
        monkeypatch.setattr("threading.current_thread", lambda: thread)
        monkeypatch.setattr("threading.main_thread", lambda: thread)
        monkeypatch.setattr("ofx.runner.api.asyncio.get_running_loop", lambda: loop)

        async def _build_runner(*args, **kwargs):
            return (_Runner(), Path.cwd())

        monkeypatch.setattr("ofx.runner.api._build_run_runner", _build_runner)
        monkeypatch.setattr("ofx.runner.channels.close_channel_store", lambda: None)
        monkeypatch.setattr("ofx.runner.api.remove_empty_dirs", lambda _path: None)
        monkeypatch.setattr("ofx.runner.api.TEMP_DIR", Path("/tmp/ofx-missing-cleanup-dir"))

        class _Runner:
            log_level = 0

            async def run(self):
                callback, arg = installed[0]
                callback(arg)
                await asyncio.sleep(0)

            async def get_result(self):
                return "partial"

        assert asyncio.run(run_workflow("wf.yml", quiet=False)) == "partial"
        assert warnings[0] == ("Received %s — initiating graceful shutdown...", "SIGINT")
        assert warnings[1] == "Workflow execution cancelled — collecting partial results"
        assert loop_calls == [
            ("add", signal.SIGINT),
            ("add", signal.SIGTERM),
            ("remove", signal.SIGINT),
            ("remove", signal.SIGTERM),
        ]

    @pytest.mark.asyncio
    async def test_run_workflow_returns_partial_result_on_cancel(
        self, monkeypatch, tmp_path
    ):
        from ofx.runner.api import run_workflow

        class _Runner:
            log_level = 0

            async def run(self):
                raise asyncio.CancelledError

            async def get_result(self):
                return "partial"

        warnings: list[str] = []
        cleanup_calls: list[Path] = []
        monkeypatch.setattr("ofx.runner.api.logger.warning", lambda message: warnings.append(message))

        async def _build_runner(*args, **kwargs):
            return (_Runner(), tmp_path)

        monkeypatch.setattr("ofx.runner.api._build_run_runner", _build_runner)
        monkeypatch.setattr("threading.current_thread", lambda: object())
        monkeypatch.setattr("threading.main_thread", lambda: object())
        monkeypatch.setattr("ofx.runner.channels.close_channel_store", lambda: None)
        monkeypatch.setattr("ofx.runner.api.remove_empty_dirs", lambda path: cleanup_calls.append(path))
        monkeypatch.setattr("ofx.runner.api.TEMP_DIR", tmp_path / "missing-temp-dir")

        assert await run_workflow("wf.yml", quiet=False, output_path=tmp_path) == "partial"
        assert warnings == ["Workflow execution cancelled — collecting partial results"]
        assert cleanup_calls == [tmp_path, tmp_path / "missing-temp-dir"]

    @pytest.mark.asyncio
    async def test_run_workflow_assembles_runner_applies_quiet_and_cleans_up(
        self, monkeypatch, tmp_path
    ):
        from ofx.runner.api import run_workflow

        workflow_model = _workflow_from_yaml(
            """
            name: test
            jobs:
              scan:
                steps:
                  - run: "echo ${{ secrets.API_KEY }}"
            """,
            tmp_path / "flows" / "wf.yml",
        )
        built_runner = SimpleNamespace()
        built_contexts: list[RunContext] = []

        monkeypatch.setattr("ofx.runner.api.find_workflow", lambda workflow, search_paths: workflow_model)

        monkeypatch.setattr("ofx.runner.api.load_secrets_by_keys", lambda needed, secrets_dir=None: {"API_KEY": "secret"})
        monkeypatch.setattr("ofx.runner.api.register_secrets", lambda _values: None)
        monkeypatch.setattr("ofx.runner.api.register_sensitive_env", lambda _env: None)
        monkeypatch.setattr("ofx.runner.api.RegistryFactory.create", lambda backend, **config: "registry")
        monkeypatch.setattr("ofx.runner.api.WorkflowExecutor", lambda: "executor")
        monkeypatch.setattr(
            "ofx.runner.api.WorkflowRunner",
            lambda workflow, **kwargs: built_contexts.append(kwargs["ctx"]) or built_runner,
        )

        async def _build_runner(*args, **kwargs):
            return (built_runner, tmp_path)

        monkeypatch.setattr("ofx.runner.api._build_run_runner", _build_runner)

        cleanup_calls: list[Path] = []
        loop_thread = object()
        monkeypatch.setattr("threading.current_thread", lambda: loop_thread)
        monkeypatch.setattr("threading.main_thread", lambda: loop_thread)
        monkeypatch.setattr("ofx.runner.channels.close_channel_store", lambda: None)
        monkeypatch.setattr("ofx.runner.api.remove_empty_dirs", lambda path: cleanup_calls.append(path))
        monkeypatch.setattr("ofx.runner.api.TEMP_DIR", tmp_path / "missing-temp-dir")

        execution_calls: list[str] = []
        loop_calls: list[tuple[str, int]] = []

        class _Loop:
            def add_signal_handler(self, sig, callback, arg):
                loop_calls.append(("add", sig))

            def remove_signal_handler(self, sig):
                loop_calls.append(("remove", sig))

        monkeypatch.setattr("ofx.runner.api.asyncio.get_running_loop", lambda: _Loop())
        monkeypatch.setattr("ofx.runner.api.asyncio.current_task", lambda: "task")

        async def _run():
            execution_calls.extend(["run", str(built_runner)])
            return "result"

        built_runner.run = _run

        built_runner.log_level = 0
        result = await run_workflow(
            "wf.yml",
            inputs={"target": "example.com"},
            env={"X": "1"},
            output_path=tmp_path,
            workflow_search_paths=[tmp_path],
            vars={"project": "demo"},
            event_sink_path=tmp_path / "events.ndjson",
            quiet=True,
        )

        assert result == "result"
        assert execution_calls == ["run", str(built_runner)]
        import logging
        assert built_runner.log_level == logging.ERROR
        assert cleanup_calls == [tmp_path, tmp_path / "missing-temp-dir"]
        assert loop_calls == [
            ("add", signal.SIGINT),
            ("add", signal.SIGTERM),
            ("remove", signal.SIGINT),
            ("remove", signal.SIGTERM),
        ]

    @pytest.mark.asyncio
    async def test_flow(self, caplog):
        with caplog.at_level("DEBUG"):
            import tempfile
            from pathlib import Path

            test_workflow = Path(__file__).parent / "flows" / "test.yml"

            tmpdir = tempfile.mkdtemp()
            try:
                workflow_dirs = [Path(__file__).parent / "flows", Path.cwd().absolute()]
                workflow = find_workflow(str(test_workflow), tuple(workflow_dirs))

                ctx = RunContext(output_path=Path(tmpdir), workflow_dirs=workflow_dirs)
                runner = WorkflowRunner(workflow=workflow, ctx=ctx)
                result = await runner.run()

                assert "command test output" in caplog.text, "Expected output in logs"

                assert result.status == RunnerStatus.COMPLETED
            finally:
                import shutil

                shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_flow_structured_events(self, tmp_path):
        from ofx.runner import run_workflow

        test_workflow = Path(__file__).parent / "flows" / "test.yml"
        event_file = tmp_path / "events.ndjson"
        result = await run_workflow(
            workflow=str(test_workflow),
            output_path=tmp_path,
            event_sink_path=event_file,
        )
        assert result.status == RunnerStatus.COMPLETED
        assert event_file.exists()
        lines = [ln for ln in event_file.read_text().splitlines() if ln.strip()]
        assert lines, "expected structured events"

    # ── new integration tests ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_parallel_jobs(self, tmp_path):
        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-parallel
jobs:
  job1:
    steps:
      - run: echo "job1"
  job2:
    steps:
      - run: echo "job2"
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_job_dependencies(self, tmp_path):
        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-deps
jobs:
  setup:
    steps:
      - run: echo "setup done"
  main:
    needs: [setup]
    steps:
      - run: echo "main done"
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_step_failure_stops_job(self, tmp_path):
        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-failure
jobs:
  failing:
    steps:
      - run: exit 1
      - run: echo "should not reach"
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.FAILED

    @pytest.mark.asyncio
    async def test_continue_on_error(self, tmp_path):
        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-continue
jobs:
  resilient:
    steps:
      - run: exit 1
        continue-on-error: true
      - run: echo "continued"
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_step_outputs(self, tmp_path, caplog):
        import logging

        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-outputs
jobs:
  outputs_job:
    steps:
      - name: produce
        run: echo "greeting=hello" >> "$OFX_OUTPUTS"
      - name: consume
        run: echo "Got {{ steps.0.outputs.greeting }}"
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        with caplog.at_level(logging.DEBUG):
            result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        assert "Got hello" in caplog.text

    @pytest.mark.asyncio
    async def test_matrix_expansion(self, tmp_path):
        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-matrix
jobs:
  scan:
    strategy:
      matrix:
        target: [a, b, c]
    steps:
      - run: echo "target={{ matrix.target }}"
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_env_vars(self, tmp_path, caplog):
        import logging

        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-env
env:
  MY_VAR: hello_world
jobs:
  check_env:
    steps:
      - run: echo "$MY_VAR"
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        with caplog.at_level(logging.DEBUG):
            result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        assert "hello_world" in caplog.text

    @pytest.mark.asyncio
    async def test_run_if_false_skips(self, tmp_path):
        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-runif
jobs:
  conditional:
    steps:
      - run: echo "always runs"
      - run: echo "skipped"
        run_if: "False"
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_inline_python_script(self, tmp_path):
        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-script
jobs:
  script_job:
    steps:
      - script: |
          print("hello from python")
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_working_directory(self, tmp_path):
        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-workdir
jobs:
  wd_job:
    steps:
      - run: pwd
        working-directory: /tmp
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
