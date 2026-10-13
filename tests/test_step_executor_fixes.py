"""Regression tests for StepExecutor fixes (findings H4, H5, L6, L8, L11).

Each test here exercises a behavior that regressed before its fix:
- H4: step timeouts now count as retryable attempts instead of aborting early.
- H5: the cloud network grace is applied at the outer wrapper so it is reachable.
- L6: the debug-log get_result() deep copy is gated behind the debug level.
- L8: _RemoteHandlerRunner.is_success reflects the actual result status.
- L11: a child that finished as CANCELED is not retried.
"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ofx.runner.cloud_step import _RemoteHandlerRunner
from ofx.runner.context import ConditionNotMetError, RunnerStatus, RunResult
from ofx.runner.executors.step import StepExecutor
from ofx.runner.registry_keys import RunnerRegistryKeys


def _completed_result():
    return SimpleNamespace(
        status=RunnerStatus.COMPLETED,
        error=None,
        outputs={"ok": True},
        model_dump=lambda exclude=None: {"status": RunnerStatus.COMPLETED, "error": None},
    )


def _base_runner(*, retry: int, create_runner, log_level=logging.DEBUG):
    return SimpleNamespace(
        _log_level=log_level,
        model=SimpleNamespace(
            retry=retry,
            timeout=1,
            retry_delay=2,
            name="step-2",
            step_index=2,
        ),
        ctx=SimpleNamespace(vars={}),
        _retry_delay_seconds=lambda *, attempt, base_delay: 0.5,
        _log_info=lambda _message: None,
        _log_debug=lambda _message: None,
        reg_set=AsyncMock(),
        get_result=AsyncMock(return_value=_completed_result()),
        _create_runner=create_runner,
    )


class TestTimeoutRetryH4:
    @pytest.mark.asyncio
    async def test_timeout_counts_as_attempt_then_succeeds(self, monkeypatch):
        """retry=2, child times out twice then succeeds -> 3 attempts total."""
        sleep_delays: list[float] = []
        logs: list[str] = []
        created = iter(
            [
                SimpleNamespace(is_success=False, run=AsyncMock(side_effect=TimeoutError)),
                SimpleNamespace(is_success=False, run=AsyncMock(side_effect=TimeoutError)),
                SimpleNamespace(is_success=True, run=AsyncMock(return_value=_completed_result())),
            ]
        )

        runner = _base_runner(retry=2, create_runner=lambda: next(created))
        runner._log_info = logs.append

        monkeypatch.setattr(
            "asyncio.sleep",
            AsyncMock(side_effect=lambda delay: sleep_delays.append(delay)),
        )

        await StepExecutor().do_run(runner)

        # Two retries happened between the three attempts.
        assert sleep_delays == [0.5, 0.5]
        # The timeout attempts are recorded in the retry logs using the
        # timeout wording, and eventually a success is stored.
        assert logs[0].startswith("Retry 2/3 in 0.5s - Step timed out after 1 minute(s)")
        assert logs[1].startswith("Retry 3/3 in 0.5s - Step timed out after 1 minute(s)")
        runner.reg_set.assert_awaited()

    @pytest.mark.asyncio
    async def test_always_times_out_raises_timeout_error_after_final_attempt(self, monkeypatch):
        """retry=2, child always times out -> timeout error after 3 attempts."""
        sleep_delays: list[float] = []
        created = iter(
            [
                SimpleNamespace(is_success=False, run=AsyncMock(side_effect=TimeoutError)),
                SimpleNamespace(is_success=False, run=AsyncMock(side_effect=TimeoutError)),
                SimpleNamespace(is_success=False, run=AsyncMock(side_effect=TimeoutError)),
            ]
        )

        runner = _base_runner(retry=2, create_runner=lambda: next(created))

        monkeypatch.setattr(
            "asyncio.sleep",
            AsyncMock(side_effect=lambda delay: sleep_delays.append(delay)),
        )

        with pytest.raises(RuntimeError, match=r"Step timed out after 1 minute\(s\)"):
            await StepExecutor().do_run(runner)

        assert sleep_delays == [0.5, 0.5]


class TestNetworkGraceH5:
    @pytest.mark.asyncio
    async def test_cloud_handler_child_budget_includes_grace(self, monkeypatch):
        """A cloud remote handler extends the outer wait_for by the grace."""
        timeouts: list[float] = []

        async def fake_wait_for(coro, timeout):
            timeouts.append(timeout)
            return await coro

        monkeypatch.setattr("asyncio.wait_for", fake_wait_for)

        child_runner = SimpleNamespace(
            _network_grace_seconds=30,
            is_success=True,
            run=AsyncMock(return_value=_completed_result()),
        )
        runner = _base_runner(retry=0, create_runner=lambda: child_runner)

        await StepExecutor().do_run(runner)

        # timeout=1min -> 60s, plus the 30s network grace.
        assert timeouts == [90]

    @pytest.mark.asyncio
    async def test_local_child_budget_keeps_plain_timeout(self, monkeypatch):
        """Local handler children get no grace — budget stays at the step timeout."""
        timeouts: list[float] = []

        async def fake_wait_for(coro, timeout):
            timeouts.append(timeout)
            return await coro

        monkeypatch.setattr("asyncio.wait_for", fake_wait_for)

        child_runner = SimpleNamespace(
            is_success=True,
            run=AsyncMock(return_value=_completed_result()),
        )
        runner = _base_runner(retry=0, create_runner=lambda: child_runner)

        await StepExecutor().do_run(runner)

        assert timeouts == [60]


class TestDebugLogGatingL6:
    @pytest.mark.asyncio
    async def test_get_result_not_fetched_when_debug_disabled(self):
        """L6: the debug result deep copy is skipped unless DEBUG is enabled."""
        runner = _base_runner(
            retry=0,
            log_level=logging.INFO,
            create_runner=lambda: SimpleNamespace(
                is_success=True,
                run=AsyncMock(return_value=_completed_result()),
            ),
        )

        await StepExecutor().do_run(runner)

        runner.get_result.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_result_fetched_when_debug_enabled(self):
        """L6: the debug result is still logged when DEBUG is enabled."""
        runner = _base_runner(
            retry=0,
            log_level=logging.DEBUG,
            create_runner=lambda: SimpleNamespace(
                is_success=True,
                run=AsyncMock(return_value=_completed_result()),
            ),
        )

        await StepExecutor().do_run(runner)

        runner.get_result.assert_awaited_once()


class TestRemoteHandlerIsSuccessL8:
    @pytest.mark.asyncio
    async def test_is_success_before_run_is_false(self):
        bridge = _RemoteHandlerRunner(SimpleNamespace())
        assert bridge.is_success is False

    @pytest.mark.asyncio
    async def test_is_success_reflects_completed_result(self):
        outer = SimpleNamespace(
            _run_type=None,
            model=SimpleNamespace(timeout=1, get_run_type=lambda: "module"),
            outputs_registry={},
        )

        async def execute(run_type, *, timeout_seconds):
            return "output\n"

        async def reg_set(key, value):
            outer.outputs_registry[key] = value

        async def get_result():
            return RunResult(
                name="step",
                run_id="r1",
                status=RunnerStatus.RUNNING,
                outputs=outer.outputs_registry.get("outputs", {}),
            )

        outer._execute_remote_run_type = execute
        outer.reg_set = reg_set
        outer.get_result = get_result

        bridge = _RemoteHandlerRunner(outer)
        result = await bridge.run()

        # The remote run completed; the outer FSM being mid-flight (RUNNING)
        # must not leak into the success decision (L8).
        assert result.status == RunnerStatus.COMPLETED
        assert bridge.is_success is True

    @pytest.mark.asyncio
    async def test_is_success_reflects_failed_result(self):
        outer = SimpleNamespace(
            _run_type=None,
            model=SimpleNamespace(timeout=1, get_run_type=lambda: "module"),
            outputs_registry={},
        )

        async def execute(run_type, *, timeout_seconds):
            return "output\n"

        async def reg_set(key, value):
            outer.outputs_registry[key] = value

        async def get_result():
            return RunResult(
                name="step",
                run_id="r1",
                status=RunnerStatus.FAILED,
                error="boom",
                outputs=outer.outputs_registry.get("outputs", {}),
            )

        outer._execute_remote_run_type = execute
        outer.reg_set = reg_set
        outer.get_result = get_result

        bridge = _RemoteHandlerRunner(outer)
        result = await bridge.run()

        assert result.status == RunnerStatus.FAILED
        assert bridge.is_success is False


class TestCanceledChildNoRetryL11:
    @pytest.mark.asyncio
    async def test_canceled_child_propagates_without_retry(self, monkeypatch):
        """L11: a CANCELED child raises immediately — no retries, no storage."""
        sleep_delays: list[float] = []
        created = iter(
            [
                SimpleNamespace(
                    is_success=False,
                    run=AsyncMock(
                        return_value=SimpleNamespace(
                            status=RunnerStatus.CANCELED,
                            error="step condition not met",
                            outputs={},
                        )
                    ),
                )
            ]
        )
        runner = _base_runner(retry=3, create_runner=lambda: next(created))

        monkeypatch.setattr(
            "asyncio.sleep",
            AsyncMock(side_effect=lambda delay: sleep_delays.append(delay)),
        )

        with pytest.raises(ConditionNotMetError, match="step condition not met"):
            await StepExecutor().do_run(runner)

        # retry=3 but only one attempt happened — cancellation is not retried.
        assert sleep_delays == []
        runner.reg_set.assert_not_awaited()


class TestPayloadKeyOrder:
    """Guard the locked step payload key order on the success path."""

    @pytest.mark.asyncio
    async def test_success_stores_outputs_then_result(self):
        recorded: list[tuple[str, dict]] = []
        runner = _base_runner(
            retry=0,
            create_runner=lambda: SimpleNamespace(
                is_success=True,
                run=AsyncMock(return_value=_completed_result()),
            ),
        )
        runner.reg_set = AsyncMock(
            side_effect=lambda key, value: recorded.append((key, value))
        )

        await StepExecutor().do_run(runner)

        assert [key for key, _value in recorded] == [
            RunnerRegistryKeys.OUTPUTS,
            RunnerRegistryKeys.RESULT,
        ]
