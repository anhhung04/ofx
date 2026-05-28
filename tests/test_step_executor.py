"""Tests for step executor orchestration."""

from ofx.runner.executors.step import StepExecutor


def test_create_runner_uses_runner_factory_when_available():
    """Specialized step runners can own their child runner construction."""
    expected = object()

    class RunnerWithFactory:
        def __init__(self):
            self.called = False

        def _create_runner(self):
            self.called = True
            return expected

    runner = RunnerWithFactory()

    assert StepExecutor().create_runner(runner) is expected
    assert runner.called is True


def test_cleanup_outputs_file_ignores_filesystem_errors():
    class BrokenOutputsFile:
        def __init__(self):
            self.called = False

        def unlink(self, *, missing_ok: bool = False):
            self.called = True
            assert missing_ok is True
            raise OSError("permission denied")

    outputs_file = BrokenOutputsFile()

    class Runner:
        _outputs_file = outputs_file

    StepExecutor()._cleanup_outputs_file(Runner())

    assert outputs_file.called is True
