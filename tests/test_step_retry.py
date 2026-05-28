"""Tests for step retry logic, exponential backoff, and continue-on-error."""

import pytest

from ofx.runner.step_mixin import (
    _JITTER_MAX,
    _JITTER_MIN,
    _MAX_BACKOFF_SECONDS,
    StepRunnerMixin,
)


class TestRetryDelayFormula:
    """Verify the exponential backoff with jitter formula."""

    def test_base_delay_at_attempt_zero(self):
        """attempt=0 → base_delay * 2^0 = base_delay (before jitter)."""
        for _ in range(50):
            delay = StepRunnerMixin._retry_delay_seconds(0, base_delay=10)
            # 10 * 2^0 = 10, jitter [0.5, 1.0] → [5.0, 10.0]
            assert 5.0 <= delay <= 10.0

    def test_exponential_growth(self):
        """Each attempt doubles the base backoff."""
        base = 5
        for attempt in range(6):
            raw_backoff = base * (2**attempt)
            expected_cap = min(raw_backoff, _MAX_BACKOFF_SECONDS)
            for _ in range(20):
                delay = StepRunnerMixin._retry_delay_seconds(attempt, base_delay=base)
                assert expected_cap * _JITTER_MIN <= delay <= expected_cap * _JITTER_MAX

    def test_capped_at_max_backoff(self):
        """Very large attempts should be capped at 5 minutes."""
        for attempt in [8, 10, 15, 20]:
            for _ in range(20):
                delay = StepRunnerMixin._retry_delay_seconds(attempt, base_delay=10)
                assert delay <= _MAX_BACKOFF_SECONDS * _JITTER_MAX

    def test_zero_base_delay(self):
        """base_delay=0 should produce zero delay (no backoff)."""
        delay = StepRunnerMixin._retry_delay_seconds(0, base_delay=0)
        assert delay == 0.0

    def test_large_base_delay_still_capped(self):
        """Even a large base delay is capped at _MAX_BACKOFF_SECONDS."""
        for _ in range(20):
            delay = StepRunnerMixin._retry_delay_seconds(0, base_delay=1000)
            assert delay <= _MAX_BACKOFF_SECONDS * _JITTER_MAX

    def test_jitter_adds_randomness(self):
        """Multiple calls with same arguments produce different delays."""
        delays = {
            StepRunnerMixin._retry_delay_seconds(2, base_delay=10) for _ in range(100)
        }
        # With jitter, we should get multiple distinct values
        assert len(delays) > 1


class TestRetryDelayTable:
    """Verify specific expected backoff values at each attempt level."""

    @pytest.mark.parametrize(
        "attempt, base, expected_raw",
        [
            (0, 10, 10),
            (1, 10, 20),
            (2, 10, 40),
            (3, 10, 80),
            (4, 10, 160),
            (5, 10, 300),  # 320 capped to 300
            (0, 1, 1),
            (1, 1, 2),
            (2, 1, 4),
            (10, 1, 300),  # 1024 capped to 300
        ],
    )
    def test_backoff_at_level(self, attempt, base, expected_raw):
        """Verify raw backoff (before jitter) matches expected value."""
        expected_capped = min(expected_raw, _MAX_BACKOFF_SECONDS)
        for _ in range(20):
            delay = StepRunnerMixin._retry_delay_seconds(attempt, base_delay=base)
            assert expected_capped * _JITTER_MIN <= delay <= expected_capped * _JITTER_MAX


class TestRetryProfileDefaults:
    """Test _apply_retry_profile_defaults behavior."""

    def _make_mock_runner(self, *, retry=0, retry_delay=0, timeout=60, profile=None):
        """Create a minimal mock that satisfies StepRunnerMixin expectations."""

        class MockModel:
            def __init__(self):
                self.retry = retry
                self.retry_delay = retry_delay
                self.timeout = timeout

        class MockCtx:
            def __init__(self):
                self.vars = {}
                if profile is not None:
                    self.vars["profile_model"] = profile

        class MockRunner(StepRunnerMixin):
            def __init__(self):
                self.model = MockModel()
                self.ctx = MockCtx()

        return MockRunner()

    def test_no_profile_no_changes(self):
        """Without a profile, step values are untouched."""
        runner = self._make_mock_runner(retry=3, retry_delay=5, timeout=30)
        runner._apply_retry_profile_defaults()
        assert runner.model.retry == 3
        assert runner.model.retry_delay == 5
        assert runner.model.timeout == 30

    def test_profile_max_retries_overrides(self):
        """Profile-level max_retries overrides step value."""

        class Profile:
            max_retries = 5
            retry_policy = "standard"
            retry_profiles = {}
            timeout_minutes = None

        runner = self._make_mock_runner(retry=1, profile=Profile())
        runner._apply_retry_profile_defaults()
        assert runner.model.retry == 5

    def test_profile_timeout_overrides(self):
        """Profile-level timeout overrides step value."""

        class Profile:
            max_retries = None
            retry_policy = "standard"
            retry_profiles = {}
            timeout_minutes = 120

        runner = self._make_mock_runner(timeout=30, profile=Profile())
        runner._apply_retry_profile_defaults()
        assert runner.model.timeout == 120

    def test_policy_retry_delay_overrides(self):
        """Retry delay from policy overrides step value."""

        class Profile:
            max_retries = None
            retry_policy = "standard"
            retry_profiles = {"standard": {"retry_delay": 30}}
            timeout_minutes = None

        runner = self._make_mock_runner(retry_delay=5, profile=Profile())
        runner._apply_retry_profile_defaults()
        assert runner.model.retry_delay == 30

    def test_policy_with_all_fields(self):
        """A policy with all fields overrides everything."""

        class Profile:
            max_retries = 10
            retry_policy = "aggressive"
            retry_profiles = {
                "aggressive": {"retry": 8, "retry_delay": 2, "timeout": 5}
            }
            timeout_minutes = 15

        runner = self._make_mock_runner(retry=0, retry_delay=0, timeout=60, profile=Profile())
        runner._apply_retry_profile_defaults()
        # max_retries (10) wins over policy retry (8)
        assert runner.model.retry == 10
        assert runner.model.retry_delay == 2
        # timeout_minutes (15) wins over policy timeout (5)
        assert runner.model.timeout == 15

    def test_default_max_retries_ignored(self):
        """max_retries=3 (the default) is treated as 'not set'."""

        class Profile:
            max_retries = 3  # default value, should be ignored
            retry_policy = "standard"
            retry_profiles = {"standard": {"retry": 5}}
            timeout_minutes = None

        runner = self._make_mock_runner(retry=0, profile=Profile())
        runner._apply_retry_profile_defaults()
        # Policy retry=5 should apply since max_retries==3 is the default
        assert runner.model.retry == 5
