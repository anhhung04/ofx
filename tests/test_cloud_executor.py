"""Tests for cloud executor cleanup helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

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
async def test_destroy_instance_uses_provider_when_allowed():
    runner = _make_runner()

    await CloudExecutor().destroy_instance(runner)

    assert runner._provider.destroyed == ["i-123"]


@pytest.mark.asyncio
async def test_destroy_instance_uses_provisioner_when_injected():
    provisioner = _Provisioner()
    runner = _make_runner()

    await CloudExecutor(provisioner=provisioner).destroy_instance(runner)  # type: ignore[arg-type]

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


@pytest.mark.asyncio
async def test_dispatch_remote_steps_merges_matrix_into_child_context(monkeypatch):
    import ofx.runner.cloud_step as cloud_step_module
    from ofx.runner import RunContext

    captured_contexts = []

    class _StepRunner:
        def __init__(self, step, ctx, *_args, **_kwargs) -> None:
            captured_contexts.append((step.step_index, ctx))
            self.is_failed = False

        async def run(self):
            return SimpleNamespace(error=None)

    class _Runner:
        def __init__(self) -> None:
            self.ctx = RunContext(vars={"matrix": {"region": "us-east-1"}})
            self.model = SimpleNamespace(
                steps=[
                    SimpleNamespace(
                        step_index=0,
                        secrets="inherit",
                        continue_on_error=False,
                        name="step-0",
                    )
                ]
            )
            self._remote_runner = object()
            self._work_dir = "/tmp/ofx-run"
            self._runners = {}

        def _child_context(self):
            return self.ctx.model_copy(deep=True)

    monkeypatch.setattr(cloud_step_module, "CloudStepRunner", _StepRunner)

    runner = _Runner()
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

    class _StepRunner:
        def __init__(self, step, ctx, *_args, **_kwargs) -> None:
            captured_secrets[step.step_index] = dict(ctx.secrets)
            self.is_failed = False

        async def run(self):
            return SimpleNamespace(error=None)

    class _Runner:
        def __init__(self) -> None:
            self.ctx = RunContext(secrets={"token": "secret"})
            self.model = SimpleNamespace(
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
            )
            self._remote_runner = object()
            self._work_dir = "/tmp/ofx-run"
            self._runners = {}

        def _child_context(self):
            return self.ctx.model_copy(deep=True)

    monkeypatch.setattr(cloud_step_module, "CloudStepRunner", _StepRunner)

    runner = _Runner()
    await CloudExecutor().dispatch_remote_steps(runner, None)

    assert captured_secrets[0] == {"token": "secret"}
    assert captured_secrets[1] == {}
    assert runner.ctx.secrets == {"token": "secret"}


def test_work_dir_commands_and_fallbacks_cover_windows_and_posix():
    windows_cfg = SimpleNamespace(connection_type="winrm")
    posix_cfg = SimpleNamespace(connection_type="ssh")

    assert CloudExecutor._create_work_dir_command(windows_cfg, "C:\\Temp\\job") == 'mkdir "C:\\Temp\\job" 2>nul'
    assert CloudExecutor._create_work_dir_command(posix_cfg, "/tmp/job dir") == "mkdir -p '/tmp/job dir'"

    assert "Remove-Item -Path 'C:\\Temp\\job'" in CloudExecutor._cleanup_work_dir_command(windows_cfg, "C:\\Temp\\job")
    assert CloudExecutor._cleanup_work_dir_command(posix_cfg, "/tmp/job dir") == "rm -rf '/tmp/job dir'"

    assert CloudExecutor._fallback_work_dir(windows_cfg) == "C:\\Windows\\Temp"
    assert CloudExecutor._fallback_work_dir(posix_cfg) == "/tmp"
    assert CloudExecutor._fallback_work_dir_label(windows_cfg) == "Temp"
    assert CloudExecutor._fallback_work_dir_label(posix_cfg) == "/tmp"
