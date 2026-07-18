"""Tests for cloud executor cleanup helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from ofx.runner.context import RunContext
from ofx.runner.context import context_for_step
from ofx.runner.executors.cloud import CloudExecutor

class _Provider:
    def __init__(self) -> None:
        self.destroyed: list[str] = []

    async def destroy_instance(self, instance_id: str) -> None:
        self.destroyed.append(instance_id)

class _Provisioner:
    def __init__(self) -> None:
        self.destroyed: list[tuple[_Provider, SimpleNamespace]] = []

    async def destroy(self, provider: _Provider, instance: SimpleNamespace) -> None:
        self.destroyed.append((provider, instance))

async def _run_sync_in_thread(func, *args, **kwargs):
    return func(*args, **kwargs)

def _make_runner(*, provider_name: str = "digitalocean", auto_destroy: bool = True):
    provider = _Provider()
    instance = SimpleNamespace(
        instance_id="i-123",
        name="scan-node",
        provider=provider_name,
    )
    return SimpleNamespace(
        _cloud_config=SimpleNamespace(
            provider=provider_name,
            auto_destroy=auto_destroy,
        ),
        _provider=provider,
        _instance=instance,
        _remote_runner=None,
        _log_info=lambda _message: None,
        _log_warning=lambda _message: None,
        _log_debug=lambda _message: None,
    )

@pytest.mark.asyncio
async def test_pre_run_resolves_cloud_config_and_registers_all_credentials(monkeypatch):
    from ofx.models.cloud import CloudConfig

    resolved_cfg = CloudConfig(
        provider="static",
        host="10.0.0.1",
        ssh_password="ssh-secret",
        extra={"token": "api-token", "aws_secret_access_key": "aws-secret"},
    )
    input_cfg = CloudConfig(provider="static", host="10.0.0.2")
    runner = SimpleNamespace(
        _cloud_config=input_cfg,
        model=SimpleNamespace(name="job-name", jid="job-1"),
        _instance=None,
        reg_set=lambda *_args, **_kwargs: None,
        _log_info=lambda _message: None,
    )
    executor = CloudExecutor()
    secret_calls: list[list[str]] = []

    monkeypatch.setattr(executor, "check_dependencies_and_run_if", lambda _runner: None)

    monkeypatch.setattr(
        "ofx.cloud.config.get_cloud_profile_manager",
        lambda: SimpleNamespace(
            resolve=lambda value: resolved_cfg if value == input_cfg else None
        ),
    )

    monkeypatch.setattr(executor, "_prepare_job_context", AsyncMock(return_value=None))
    monkeypatch.setattr(executor, "provision_instance", AsyncMock(return_value=None))
    monkeypatch.setattr(executor, "_store_job_model", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "ofx.runner.executors.cloud.register_secrets",
        lambda values: secret_calls.append(list(values)),
    )

    await executor.pre_run(runner)

    assert secret_calls == [["ssh-secret", "api-token", "aws-secret"]]
    assert runner._cloud_config is resolved_cfg

@pytest.mark.asyncio
async def test_pre_run_parses_string_cloud_config_before_resolution(monkeypatch):
    from ofx.models.cloud import CloudConfig

    parsed_cfg = CloudConfig(provider="static", host="10.0.0.3")
    resolved_cfg = CloudConfig(provider="static", host="10.0.0.4")
    runner = SimpleNamespace(
        _cloud_config="profile-a",
        model=SimpleNamespace(name="job-name", jid="job-1"),
        _instance=None,
        reg_set=lambda *_args, **_kwargs: None,
        _log_info=lambda _message: None,
    )
    executor = CloudExecutor()

    monkeypatch.setattr(executor, "check_dependencies_and_run_if", lambda _runner: None)

    monkeypatch.setattr("ofx.models.cloud.parse_cloud_field", lambda value: parsed_cfg if value == "profile-a" else None)

    monkeypatch.setattr(
        "ofx.cloud.config.get_cloud_profile_manager",
        lambda: SimpleNamespace(
            resolve=lambda value: resolved_cfg if value is parsed_cfg else None
        ),
    )
    monkeypatch.setattr(executor, "_prepare_job_context", AsyncMock(return_value=None))
    monkeypatch.setattr(executor, "provision_instance", AsyncMock(return_value=None))
    monkeypatch.setattr(executor, "_store_job_model", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "ofx.runner.executors.cloud.register_secrets",
        lambda _values: None,
    )

    await executor.pre_run(runner)

    assert runner._cloud_config is resolved_cfg

@pytest.mark.asyncio
async def test_destroy_instance_uses_provider_when_allowed():
    logs: list[str] = []
    runner = _make_runner()
    runner._log_info = logs.append

    await CloudExecutor().destroy_instance(runner)

    assert runner._provider.destroyed == ["i-123"]
    assert logs == ["Destroying instance 'scan-node'[i-123] (provider=digitalocean)"]

@pytest.mark.asyncio
async def test_pre_run_registers_cloud_credentials(monkeypatch):
    from ofx.models.cloud import CloudConfig

    cfg = CloudConfig(
        provider="static",
        host="10.0.0.1",
        ssh_password="ssh-secret",
        extra={"token": "api-token"},
    )
    runner = SimpleNamespace(
        _cloud_config=cfg,
        model=SimpleNamespace(name="job-name", jid="job-1"),
        _instance=None,
        reg_set=lambda *_args, **_kwargs: None,
        _log_info=lambda _message: None,
    )
    executor = CloudExecutor()
    secret_calls: list[list[str]] = []

    monkeypatch.setattr(executor, "check_dependencies_and_run_if", lambda _runner: None)

    monkeypatch.setattr(executor, "_prepare_job_context", AsyncMock(return_value=None))
    monkeypatch.setattr(executor, "provision_instance", AsyncMock(return_value=None))
    monkeypatch.setattr(executor, "_store_job_model", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "ofx.runner.executors.cloud.register_secrets",
        lambda values: secret_calls.append(list(values)),
    )

    await executor.pre_run(runner)

    assert secret_calls == [["ssh-secret", "api-token"]]

@pytest.mark.asyncio
async def test_pre_run_stores_cloud_instance_metadata(monkeypatch):
    from ofx.models.cloud import CloudConfig

    cfg = CloudConfig(provider="static", host="10.0.0.1")
    registry_updates: list[tuple[str, dict[str, str]]] = []
    runner = SimpleNamespace(
        _cloud_config=cfg,
        model=SimpleNamespace(name="job-name", jid="job-1"),
        _instance=None,
        _log_info=lambda _message: None,
    )
    executor = CloudExecutor()

    monkeypatch.setattr(executor, "check_dependencies_and_run_if", lambda _runner: None)

    async def _provision_instance(_runner, _cfg):
        _runner._instance = SimpleNamespace(
            instance_id="i-123",
            ip="10.0.0.1",
            provider="static",
            region="local",
        )

    async def _reg_set(key, value):
        registry_updates.append((key, value))

    runner.reg_set = _reg_set
    monkeypatch.setattr(executor, "_prepare_job_context", AsyncMock(return_value=None))
    monkeypatch.setattr(executor, "provision_instance", _provision_instance)
    monkeypatch.setattr(executor, "_store_job_model", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "ofx.runner.executors.cloud.register_secrets",
        lambda _values: None,
    )

    await executor.pre_run(runner)

    assert registry_updates == [(
        "cloud_instance",
        {
            "instance_id": "i-123",
            "ip": "10.0.0.1",
            "provider": "static",
            "region": "local",
        },
    )]

@pytest.mark.asyncio
async def test_pre_run_raises_clear_message_when_cloud_config_missing(monkeypatch):
    runner = SimpleNamespace(
        _cloud_config=None,
        model=SimpleNamespace(jid="job-1"),
    )
    executor = CloudExecutor()

    monkeypatch.setattr(executor, "_prepare_job_context", AsyncMock(return_value=None))

    with pytest.raises(RuntimeError, match="Cloud config is required for job 'job-1'"):
        await executor.pre_run(runner)

@pytest.mark.asyncio
async def test_post_run_downloads_then_tears_down(monkeypatch):
    calls: list[str] = []
    runner = SimpleNamespace()
    executor = CloudExecutor()

    monkeypatch.setattr(
        executor,
        "save_job_results",
        AsyncMock(side_effect=lambda _runner: calls.append("save")),
    )
    monkeypatch.setattr(
        executor,
        "download_outputs",
        AsyncMock(side_effect=lambda _runner: calls.append("download")),
    )
    monkeypatch.setattr(
        executor,
        "destroy_instance",
        AsyncMock(side_effect=lambda _runner: calls.append("destroy")),
    )
    monkeypatch.setattr(
        executor,
        "cleanup_remote",
        AsyncMock(side_effect=lambda _runner: calls.append("cleanup")),
    )

    await executor.post_run(runner)

    assert calls == ["save", "download", "destroy", "cleanup"]

@pytest.mark.asyncio
async def test_provision_instance_logs_connection_message(monkeypatch):
    executor = CloudExecutor(provisioner=SimpleNamespace())
    logs: list[str] = []
    commands: list[str] = []
    runner = SimpleNamespace(
        _log_info=logs.append,
        _remote_runner=SimpleNamespace(run=lambda command: commands.append(command)),
        _provider=None,
        _instance=None,
        _work_dir=None,
    )
    cfg = SimpleNamespace(connection_type="ssh")
    instance = SimpleNamespace(ip="10.0.0.1")

    async def _provision(_cfg):
        return SimpleNamespace(), instance, runner._remote_runner, "/tmp/work"

    executor._provisioner.provision = _provision
    monkeypatch.setattr("asyncio.to_thread", _run_sync_in_thread)

    await executor.provision_instance(runner, cfg)

    assert logs == ["Connected to 10.0.0.1 via SSH"]
    assert commands == ["mkdir -p /tmp/work"]
    assert runner._provider is not None
    assert runner._instance is instance
    assert runner._remote_runner is not None
    assert runner._work_dir == "/tmp/work"

@pytest.mark.asyncio
async def test_provision_instance_falls_back_when_work_dir_creation_fails(monkeypatch):
    executor = CloudExecutor(provisioner=SimpleNamespace())
    warnings: list[str] = []
    runner = SimpleNamespace(
        _log_info=lambda _message: None,
        _log_warning=warnings.append,
        _remote_runner=SimpleNamespace(run=lambda _command: (_ for _ in ()).throw(RuntimeError("boom"))),
        _provider=None,
        _instance=None,
        _work_dir=None,
    )
    cfg = SimpleNamespace(connection_type="ssh")
    instance = SimpleNamespace(ip="10.0.0.1")

    async def _provision(_cfg):
        return SimpleNamespace(), instance, runner._remote_runner, "/tmp/work"

    executor._provisioner.provision = _provision
    monkeypatch.setattr("asyncio.to_thread", _run_sync_in_thread)

    await executor.provision_instance(runner, cfg)

    assert runner._work_dir == "/tmp"
    assert warnings == ["Work dir creation failed, using /tmp: boom"]

@pytest.mark.asyncio
async def test_on_failure_warns_on_salvage_error_then_tears_down(monkeypatch):
    warnings: list[str] = []
    calls: list[str] = []
    runner = SimpleNamespace(_log_warning=warnings.append)
    executor = CloudExecutor()

    monkeypatch.setattr(
        executor,
        "download_outputs",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    monkeypatch.setattr(
        executor,
        "destroy_instance",
        AsyncMock(side_effect=lambda _runner: calls.append("destroy")),
    )
    monkeypatch.setattr(
        executor,
        "cleanup_remote",
        AsyncMock(side_effect=lambda _runner: calls.append("cleanup")),
    )

    await executor.on_failure(runner)

    assert warnings == ["Output salvage on failure failed: boom"]
    assert calls == ["destroy", "cleanup"]

@pytest.mark.asyncio
async def test_destroy_instance_uses_provisioner_when_injected():
    provisioner = _Provisioner()
    runner = _make_runner()

    await CloudExecutor(provisioner=provisioner).destroy_instance(runner)

    assert provisioner.destroyed == [(runner._provider, runner._instance)]
    assert runner._provider.destroyed == []

@pytest.mark.asyncio
async def test_destroy_instance_skips_static_and_auto_destroy_false():
    static_runner = _make_runner(provider_name="static")
    disabled_runner = _make_runner(auto_destroy=False)

    executor = CloudExecutor()
    await executor.destroy_instance(static_runner)
    await executor.destroy_instance(disabled_runner)

    assert static_runner._provider.destroyed == []
    assert disabled_runner._provider.destroyed == []

@pytest.mark.asyncio
async def test_emergency_deprovision_ignores_auto_destroy_but_skips_static():
    disabled_runner = _make_runner(auto_destroy=False)
    static_runner = _make_runner(provider_name="static", auto_destroy=False)

    executor = CloudExecutor()
    await executor.emergency_deprovision(disabled_runner)
    await executor.emergency_deprovision(static_runner)

    assert disabled_runner._provider.destroyed == ["i-123"]
    assert static_runner._provider.destroyed == []

def test_instance_helper_accessors_handle_missing_instance():
    runner = SimpleNamespace(_instance=None, _cloud_config=SimpleNamespace(provider="static"))

    state = CloudExecutor._cloud_instance_state(runner)

    assert state.instance_name == "unknown"
    assert state.instance_id == "unknown"
    assert state.instance_ip == ""

def test_instance_attr_and_connection_messages_cover_provisioning_helpers():
    runner = SimpleNamespace(
        _instance=SimpleNamespace(instance_id="i-1", name="node-1", ip="10.0.0.1"),
    )
    state = CloudExecutor._cloud_instance_state(
        SimpleNamespace(_instance=runner._instance, _cloud_config=SimpleNamespace(provider="static"))
    )
    assert state.instance_name == "node-1"
    assert CloudExecutor._cloud_instance_state(
        SimpleNamespace(_instance=None, _cloud_config=SimpleNamespace(provider="static"))
    ).instance_name == "unknown"

def test_destroyability_and_reportability_helpers_cover_runner_state():
    allowed_runner = _make_runner(provider_name="digitalocean", auto_destroy=True)
    disabled_runner = _make_runner(provider_name="digitalocean", auto_destroy=False)
    static_runner = _make_runner(provider_name="static", auto_destroy=True)
    missing_instance = SimpleNamespace(_provider=_Provider(), _instance=None, _cloud_config=SimpleNamespace(provider="digitalocean", auto_destroy=True))

    allowed_state = CloudExecutor._cloud_instance_state(allowed_runner)
    disabled_state = CloudExecutor._cloud_instance_state(disabled_runner)
    static_state = CloudExecutor._cloud_instance_state(static_runner)
    missing_state = CloudExecutor._cloud_instance_state(missing_instance)

    assert allowed_state.provider is allowed_runner._provider
    assert allowed_state.auto_destroy_enabled is True
    assert disabled_state.auto_destroy_enabled is False
    assert allowed_state.has_destroyable_instance is True
    assert static_state.has_destroyable_instance is False
    assert missing_state.has_destroyable_instance is False
    assert allowed_state.has_reportable_instance is False

    allowed_runner._instance.ip = "10.0.0.8"
    assert CloudExecutor._cloud_instance_state(allowed_runner).has_reportable_instance is True

@pytest.mark.asyncio
async def test_dispatch_remote_steps_merges_matrix_into_copied_context(monkeypatch):
    import ofx.runner.cloud_step as cloud_step_module
    from ofx.runner import RunContext

    captured_contexts = []

    monkeypatch.setattr(
        cloud_step_module,
        "CloudStepRunner",
        lambda step, ctx, *_args, **_kwargs: (
            captured_contexts.append((step.step_index, ctx))
            or SimpleNamespace(
                is_failed=False,
                run=AsyncMock(return_value=SimpleNamespace(error=None)),
            )
        ),
    )

    runner = SimpleNamespace(
        ctx=RunContext(vars={"matrix": {"region": "us-east-1"}}),
        model=SimpleNamespace(
            steps=[
                SimpleNamespace(
                    step_index=0,
                    secrets="inherit",
                    continue_on_error=False,
                    name="step-0",
                )
            ]
        ),
        _remote_runner=object(),
        _work_dir="/tmp/ofx-run",
        _runners={},
    )
    await CloudExecutor().dispatch_remote_steps(runner, {"tool": "nmap"})

    assert captured_contexts[0][1].vars["matrix"] == {
        "region": "us-east-1",
        "tool": "nmap",
    }
    assert runner.ctx.vars["matrix"] == {"region": "us-east-1"}

@pytest.mark.asyncio
async def test_dispatch_remote_steps_resets_non_inherited_step_secrets(monkeypatch):
    import ofx.runner.cloud_step as cloud_step_module
    from ofx.runner import RunContext

    captured_secrets = {}

    monkeypatch.setattr(
        cloud_step_module,
        "CloudStepRunner",
        lambda step, ctx, *_args, **_kwargs: (
            captured_secrets.__setitem__(step.step_index, dict(ctx.secrets))
            or SimpleNamespace(
                is_failed=False,
                run=AsyncMock(return_value=SimpleNamespace(error=None)),
            )
        ),
    )

    runner = SimpleNamespace(
        ctx=RunContext(secrets={"token": "secret"}),
        model=SimpleNamespace(
            steps=[
                SimpleNamespace(
                    step_index=0,
                    secrets="inherit",
                    continue_on_error=False,
                    name="step-0",
                ),
                SimpleNamespace(
                    step_index=1,
                    secrets="isolated",
                    continue_on_error=False,
                    name="step-1",
                ),
            ]
        ),
        _remote_runner=object(),
        _work_dir="/tmp/ofx-run",
        _runners={},
    )
    await CloudExecutor().dispatch_remote_steps(runner, None)

    assert captured_secrets[0] == {"token": "secret"}
    assert captured_secrets[1] == {}
    assert runner.ctx.secrets == {"token": "secret"}

@pytest.mark.asyncio
async def test_dispatch_remote_steps_merges_matrix_and_create_step_runner_kwargs(monkeypatch):
    executor = CloudExecutor()
    runner = SimpleNamespace(
        ctx=RunContext(vars={"matrix": {"region": "us-east-1"}}),
        _remote_runner="remote",
        _work_dir="/tmp/ofx-run",
    )
    captured: dict[str, object] = {}
    loop_contexts: list[RunContext] = []

    monkeypatch.setattr(
        "ofx.runner.cloud_step.CloudStepRunner",
        lambda step, step_ctx, parent, **kwargs: captured.update(
            {
                "step": step,
                "step_ctx": step_ctx,
                "parent": parent,
                **kwargs,
            }
        ),
    )

    async def _execute_steps(_runner, *, suffix="", loop_ctx=None):
        loop_contexts.append(loop_ctx)

    monkeypatch.setattr(executor, "_execute_steps", _execute_steps)

    await executor.dispatch_remote_steps(runner, {"tool": "nmap"})

    assert loop_contexts[0].vars["matrix"] == {
        "region": "us-east-1",
        "tool": "nmap",
    }

    step = SimpleNamespace(step_index=1)
    step_ctx = SimpleNamespace()
    executor._create_step_runner(runner, step, step_ctx)

    assert captured == {
        "step": step,
        "step_ctx": step_ctx,
        "parent": runner,
        "remote_runner": "remote",
        "work_dir": "/tmp/ofx-run",
        "executor": executor._step_executor,
        "handler_registry": executor._handler_registry,
    }

@pytest.mark.asyncio
async def test_cleanup_remote_runs_workdir_cleanup_and_runner_cleanup(monkeypatch):
    calls: list[tuple[str, tuple, dict]] = []

    monkeypatch.setattr("asyncio.to_thread", _run_sync_in_thread)

    runner = SimpleNamespace(
        _cloud_config=SimpleNamespace(connection_type="ssh"),
        _remote_runner=SimpleNamespace(
            run=lambda *args, **kwargs: calls.append(("run", args, kwargs)),
            cleanup=lambda: calls.append(("cleanup", (), {})),
        ),
        _work_dir="/tmp/ofx-run",
        _log_debug=lambda _message: None,
    )

    await CloudExecutor().cleanup_remote(runner)

    assert calls == [
        ("run", ("rm -rf /tmp/ofx-run", 15), {}),
        ("cleanup", (), {}),
    ]

@pytest.mark.asyncio
async def test_cleanup_remote_skips_default_workdir_cleanup(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr("asyncio.to_thread", _run_sync_in_thread)

    runner = SimpleNamespace(
        _cloud_config=SimpleNamespace(connection_type="winrm"),
        _remote_runner=SimpleNamespace(
            run=lambda *_args, **_kwargs: calls.append("run"),
            cleanup=lambda: calls.append("cleanup"),
        ),
        _work_dir="C:\\Windows\\Temp",
        _log_debug=lambda _message: None,
    )

    await CloudExecutor().cleanup_remote(runner)

    assert calls == ["cleanup"]

@pytest.mark.asyncio
async def test_cleanup_remote_returns_when_remote_runner_missing():
    runner = SimpleNamespace(_log_debug=lambda _message: None)

    await CloudExecutor().cleanup_remote(runner)

@pytest.mark.asyncio
async def test_cleanup_remote_uses_windows_cleanup_command_for_non_default_workdir(monkeypatch):
    calls: list[tuple[str, tuple, dict]] = []

    monkeypatch.setattr("asyncio.to_thread", _run_sync_in_thread)

    runner = SimpleNamespace(
        _cloud_config=SimpleNamespace(connection_type="winrm"),
        _remote_runner=SimpleNamespace(
            run=lambda *args, **kwargs: calls.append(("run", args, kwargs)),
            cleanup=lambda: calls.append(("cleanup", (), {})),
        ),
        _work_dir="C:\\Temp\\job",
        _log_debug=lambda _message: None,
    )

    await CloudExecutor().cleanup_remote(runner)

    assert calls == [
        (
            "run",
            (
                "powershell \"Remove-Item -Path 'C:\\Temp\\job' -Recurse -Force -ErrorAction SilentlyContinue\"",
                15,
            ),
            {},
        ),
        ("cleanup", (), {}),
    ]

@pytest.mark.asyncio
async def test_download_outputs_returns_when_remote_runner_or_output_path_missing(tmp_path):
    runner = SimpleNamespace(
        ctx=SimpleNamespace(output_path=tmp_path),
        model=SimpleNamespace(jid="job-1"),
        _remote_runner=None,
        _work_dir="/tmp/ofx-run",
        _cloud_config=SimpleNamespace(connection_type="ssh"),
        _log_debug=lambda _message: None,
    )

    await CloudExecutor().download_outputs(runner)

    runner._remote_runner = object()
    runner.ctx.output_path = None

    await CloudExecutor().download_outputs(runner)

@pytest.mark.asyncio
async def test_download_outputs_downloads_safe_files_only(tmp_path):
    downloads: list[tuple[str, str]] = []
    commands: list[str] = []

    runner = SimpleNamespace(
        ctx=SimpleNamespace(output_path=tmp_path),
        model=SimpleNamespace(jid="job-1"),
        _cloud_config=SimpleNamespace(connection_type="ssh"),
        _remote_runner=SimpleNamespace(
            run=lambda command: commands.append(command)
            or "nested/report.txt\n..\nsummary.json\n",
            download=lambda remote, local: downloads.append((remote, local)),
        ),
        _work_dir="/tmp/ofx-run",
        _log_debug=lambda _message: None,
    )

    with patch("asyncio.to_thread", _run_sync_in_thread):
        await CloudExecutor().download_outputs(runner)

    assert commands == ["ls -1 /tmp/ofx-run/output 2>/dev/null || true"]
    assert downloads == [
        ("/tmp/ofx-run/output/report.txt", str(tmp_path / "job-1" / "report.txt")),
        ("/tmp/ofx-run/output/summary.json", str(tmp_path / "job-1" / "summary.json")),
    ]

@pytest.mark.asyncio
async def test_download_outputs_uses_windows_list_command(tmp_path):
    commands: list[str] = []

    runner = SimpleNamespace(
        ctx=SimpleNamespace(output_path=tmp_path),
        model=SimpleNamespace(jid="job-1"),
        _cloud_config=SimpleNamespace(connection_type="winrm"),
        _remote_runner=SimpleNamespace(
            run=lambda command: commands.append(command) or "",
            download=lambda remote, local: (_ for _ in ()).throw(
                AssertionError("download should not be called")
            ),
        ),
        _work_dir="C:\\Temp\\job",
        _log_debug=lambda _message: None,
    )

    with patch("asyncio.to_thread", _run_sync_in_thread):
        await CloudExecutor().download_outputs(runner)

    assert commands == [
        "powershell \"Get-ChildItem -Path 'C:\\Temp\\job\\output' -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name\""
    ]
