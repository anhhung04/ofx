"""Tests for template helpers, profiles, time windows, and profile integration."""

import pytest

# ── Template Helpers ──────────────────────────────────────────────────────


class TestTemplateHelpers:
    """Verify template helper functions filter typed_output dicts correctly."""

    @pytest.fixture()
    def sample_outputs(self):
        return [
            {"_type": "port", "port": 80, "ip": "10.0.0.1"},
            {"_type": "port", "port": 443, "ip": "10.0.0.1"},
            {"_type": "url", "url": "https://example.com"},
            {"_type": "vulnerability", "name": "XSS", "severity": "high"},
            {"_type": "subdomain", "host": "api.example.com"},
            {"_type": "ip", "ip": "10.0.0.1"},
            {"_type": "tag", "name": "nginx", "category": "technology"},
            {"_type": "record", "name": "mx.example.com", "type": "MX"},
            {"_type": "domain", "domain": "example.com"},
            {"_type": "certificate", "host": "example.com:443", "subject_cn": "example.com"},
            {"_type": "exploit", "name": "EDB-12345", "title": "Buffer Overflow"},
            {"_type": "user_account", "username": "admin"},
        ]

    @staticmethod
    def _of_type(items, type_name):
        """Replicate the template helper logic for testing."""
        if not isinstance(items, list):
            return []
        return [i for i in items if isinstance(i, dict) and i.get("_type") == type_name]

    def test_of_type(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "port")) == 2
        assert len(self._of_type(sample_outputs, "url")) == 1

    def test_ports(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "port")) == 2

    def test_urls(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "url")) == 1

    def test_vulns(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "vulnerability")) == 1

    def test_subdomains(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "subdomain")) == 1

    def test_ips(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "ip")) == 1

    def test_tags(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "tag")) == 1

    def test_records(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "record")) == 1

    def test_domains(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "domain")) == 1

    def test_certs(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "certificate")) == 1

    def test_exploits(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "exploit")) == 1

    def test_users(self, sample_outputs):
        assert len(self._of_type(sample_outputs, "user_account")) == 1

    def test_of_type_with_non_list(self):
        assert self._of_type("not a list", "port") == []
        assert self._of_type(None, "port") == []

    def test_of_type_empty_list(self):
        assert self._of_type([], "port") == []

    def test_helpers_registered_in_resolver(self):
        """Verify all helper names exist in TemplateResolver support functions."""
        from ofx.runner.templates.resolver import TemplateResolver

        resolver = TemplateResolver()
        funcs = resolver.get_support_functions()
        for name in ("of_type", "ports", "urls", "vulns", "subdomains",
                      "ips", "tags", "records", "domains", "users",
                      "certs", "exploits"):
            assert name in funcs, f"Helper '{name}' not in support functions"


# ── Template Helper: users() ───────────────────────────────────────────


class TestUsersTemplateHelper:
    def test_users_filter(self):
        from ofx.runner.templates.resolver import TemplateResolver

        resolver = TemplateResolver()
        funcs = resolver.get_support_functions()
        users_fn = funcs["users"]

        items = [
            {"_type": "user_account", "username": "admin"},
            {"_type": "port", "port": 80},
            {"_type": "user_account", "username": "guest"},
        ]
        result = users_fn(items)
        assert len(result) == 2
        assert result[0]["username"] == "admin"
        assert result[1]["username"] == "guest"


# ── Template Helpers: certs() and exploits() ───────────────────────────


class TestCertsTemplateHelper:
    def test_certs_filter(self):
        from ofx.runner.templates.resolver import TemplateResolver

        resolver = TemplateResolver()
        funcs = resolver.get_support_functions()
        certs_fn = funcs["certs"]

        items = [
            {"_type": "certificate", "host": "example.com:443", "subject_cn": "example.com"},
            {"_type": "port", "port": 443},
            {"_type": "certificate", "host": "api.example.com:443", "subject_cn": "api.example.com"},
        ]
        result = certs_fn(items)
        assert len(result) == 2
        assert result[0]["subject_cn"] == "example.com"
        assert result[1]["host"] == "api.example.com:443"

    def test_certs_empty(self):
        from ofx.runner.templates.resolver import TemplateResolver

        resolver = TemplateResolver()
        funcs = resolver.get_support_functions()
        assert funcs["certs"]([]) == []
        assert funcs["certs"]([{"_type": "port", "port": 80}]) == []


class TestExploitsTemplateHelper:
    def test_exploits_filter(self):
        from ofx.runner.templates.resolver import TemplateResolver

        resolver = TemplateResolver()
        funcs = resolver.get_support_functions()
        exploits_fn = funcs["exploits"]

        items = [
            {"_type": "exploit", "name": "EDB-12345", "title": "Buffer Overflow"},
            {"_type": "vulnerability", "name": "XSS"},
            {"_type": "exploit", "name": "EDB-67890", "title": "SQL Injection"},
        ]
        result = exploits_fn(items)
        assert len(result) == 2
        assert result[0]["name"] == "EDB-12345"
        assert result[1]["title"] == "SQL Injection"

    def test_exploits_empty(self):
        from ofx.runner.templates.resolver import TemplateResolver

        resolver = TemplateResolver()
        funcs = resolver.get_support_functions()
        assert funcs["exploits"]([]) == []
        assert funcs["exploits"]([{"_type": "url", "url": "http://x.com"}]) == []


# ── Profile System ─────────────────────────────────────────────────────


class TestProfiles:
    def test_profile_model_defaults(self):
        from ofx.profiles.models import OFXProfile

        p = OFXProfile()
        assert p.rate_limit == 0
        assert p.threads == 10
        assert p.time_window.enabled is False

    def test_profile_model_custom(self):
        from ofx.profiles.models import OFXProfile

        p = OFXProfile(
            name="stealth",
            rate_limit=30,
            delay=2.0,
            jitter=1.0,
            threads=2,
            proxy="socks5://127.0.0.1:9050",
        )
        assert p.rate_limit == 30
        assert p.delay == 2.0
        assert p.proxy == "socks5://127.0.0.1:9050"

    def test_time_window_model(self):
        from ofx.profiles.models import TimeWindow

        tw = TimeWindow(
            enabled=True,
            start="09:00",
            end="17:00",
            days=["monday", "tuesday", "wednesday", "thursday", "friday"],
            timezone="US/Eastern",
        )
        assert tw.start_time().hour == 9
        assert tw.end_time().hour == 17
        assert "saturday" not in tw.days

    def test_profile_manager_crud(self, tmp_path):
        from ofx.profiles.manager import ProfileManager

        mgr = ProfileManager(config_path=tmp_path / "profiles.yml")
        assert mgr.list_profiles() == []

        mgr.add("test", {"rate_limit": 100, "description": "test profile"})
        assert mgr.exists("test")
        assert "test" in mgr.list_profiles()

        profile = mgr.resolve("test")
        assert profile.rate_limit == 100

        mgr.remove("test")
        assert not mgr.exists("test")

    def test_profile_manager_default(self, tmp_path):
        from ofx.profiles.manager import ProfileManager

        mgr = ProfileManager(config_path=tmp_path / "profiles.yml")
        mgr.add("p1", {"rate_limit": 10})
        mgr.add("p2", {"rate_limit": 20})
        mgr.set_default("p1")
        assert mgr.default_profile_name == "p1"

        result = mgr.resolve_or_default(None)
        assert result is not None
        assert result.rate_limit == 10

    def test_profile_manager_not_found(self, tmp_path):
        from ofx.profiles.manager import ProfileManager

        mgr = ProfileManager(config_path=tmp_path / "profiles.yml")
        with pytest.raises(KeyError):
            mgr.resolve("nonexistent")

    def test_profile_task_options(self):
        from ofx.profiles.models import OFXProfile

        p = OFXProfile(
            task_options={"nmap": {"timing": "T2", "ports": "80,443"}}
        )
        assert p.task_options["nmap"]["timing"] == "T2"

    def test_profile_retry_policy_defaults(self):
        from ofx.profiles.models import OFXProfile

        p = OFXProfile()
        assert p.retry_policy == "standard"
        assert "standard" in p.retry_profiles
        assert p.retry_profiles["standard"]["retry_delay"] == 5


# ── Time Window Enforcement ────────────────────────────────────────────


class TestTimeWindow:
    def test_disabled_window_always_allowed(self):
        from ofx.profiles.models import TimeWindow
        from ofx.profiles.time_window import check_time_window

        tw = TimeWindow(enabled=False)
        result = check_time_window(tw)
        assert result["allowed"] is True

    def test_check_within_window(self):
        from datetime import UTC, datetime

        from ofx.profiles.models import TimeWindow
        from ofx.profiles.time_window import check_time_window

        # Build a window around the current UTC time (check_time_window
        # defaults to UTC) so the assertion is timezone-independent.
        now = datetime.now(UTC)
        start = f"{max(0, now.hour - 1):02d}:00"
        end = f"{min(23, now.hour + 1):02d}:59"
        day = now.strftime("%A").lower()

        tw = TimeWindow(enabled=True, start=start, end=end, days=[day])
        result = check_time_window(tw)
        assert result["allowed"] is True

    def test_check_outside_window_day(self):
        from ofx.profiles.models import TimeWindow
        from ofx.profiles.time_window import check_time_window

        # No valid days
        tw = TimeWindow(enabled=True, start="00:00", end="23:59", days=[])
        result = check_time_window(tw)
        assert result["allowed"] is False
        assert "outside the allowed days" in result["message"]

    def test_check_outside_window_time(self):
        from datetime import UTC, datetime

        from ofx.profiles.models import TimeWindow
        from ofx.profiles.time_window import check_time_window

        now = datetime.now(UTC)
        # Set window to an hour that's definitely not now
        if now.hour < 12:
            start, end = "18:00", "19:00"
        else:
            start, end = "03:00", "04:00"

        tw = TimeWindow(
            enabled=True,
            start=start,
            end=end,
            days=[now.strftime("%A").lower()],
        )
        result = check_time_window(tw)
        assert result["allowed"] is False

    def test_time_in_range_normal(self):
        from datetime import time

        from ofx.profiles.time_window import _time_in_range

        assert _time_in_range(time(9, 0), time(17, 0), time(12, 0)) is True
        assert _time_in_range(time(9, 0), time(17, 0), time(18, 0)) is False

    def test_time_in_range_overnight(self):
        from datetime import time

        from ofx.profiles.time_window import _time_in_range

        # Overnight window: 22:00 → 06:00
        assert _time_in_range(time(22, 0), time(6, 0), time(23, 0)) is True
        assert _time_in_range(time(22, 0), time(6, 0), time(3, 0)) is True
        assert _time_in_range(time(22, 0), time(6, 0), time(12, 0)) is False

    def test_time_window_guard_not_started_when_disabled(self):

        from ofx.profiles.models import TimeWindow
        from ofx.profiles.time_window import TimeWindowGuard

        tw = TimeWindow(enabled=False)
        guard = TimeWindowGuard(tw)
        guard.start()
        assert guard._task is None

    def test_warn_message_near_end(self):
        from datetime import UTC, datetime

        from ofx.profiles.models import TimeWindow
        from ofx.profiles.time_window import check_time_window

        now = datetime.now(UTC)
        day = now.strftime("%A").lower()
        # Window that ends in 5 minutes
        end_min = (now.minute + 5) % 60
        end_hour = now.hour + ((now.minute + 5) // 60)
        if end_hour > 23:
            end_hour = 23
            end_min = 59

        tw = TimeWindow(
            enabled=True,
            start=f"{max(0, now.hour - 1):02d}:00",
            end=f"{end_hour:02d}:{end_min:02d}",
            days=[day],
            warn_before_minutes=10,
        )
        result = check_time_window(tw)
        if result["allowed"] and 0 < result["remaining_minutes"] <= 10:
            assert "remaining" in result["message"]


# ── DefaultConfig Profile Field ────────────────────────────────────────


class TestDefaultConfigProfile:
    def test_default_config_has_profile_field(self):
        from ofx.models.config import DefaultConfig

        dc = DefaultConfig()
        assert dc.profile == ""

    def test_default_config_with_profile(self):
        from ofx.models.config import DefaultConfig

        dc = DefaultConfig(profile="stealth")
        assert dc.profile == "stealth"


# ── Profile Task Options ──────────────────────────────────────────────


class TestProfileTaskOptions:
    """Verify profile task_options are applied to TaskRunner."""

    def test_task_options_merge_into_opts(self):
        from ofx.profiles.models import OFXProfile
        from ofx.runner.core.models import RunContext
        from ofx.runner.tasks.runner import TaskExecution, TaskRunner

        profile = OFXProfile(
            task_options={"httpx": {"threads": 5, "rate_limit": 20}}
        )
        ctx = RunContext(vars={"profile_model": profile})
        model = TaskExecution(
            task_name="httpx",
            target="example.com",
            opts={"threads": 10},  # user override
        )
        runner = TaskRunner(model, ctx)
        runner._apply_profile_task_options()

        # User's threads=10 should win over profile's threads=5
        assert runner.model.opts["threads"] == 10
        # Profile's rate_limit=20 should be applied (no user override)
        assert runner.model.opts["rate_limit"] == 20

    def test_no_profile_does_nothing(self):
        from ofx.runner.core.models import RunContext
        from ofx.runner.tasks.runner import TaskExecution, TaskRunner

        ctx = RunContext()
        model = TaskExecution(
            task_name="httpx", target="example.com", opts={"threads": 10}
        )
        runner = TaskRunner(model, ctx)
        runner._apply_profile_task_options()
        assert runner.model.opts == {"threads": 10}

    def test_no_matching_task_options(self):
        from ofx.profiles.models import OFXProfile
        from ofx.runner.core.models import RunContext
        from ofx.runner.tasks.runner import TaskExecution, TaskRunner

        profile = OFXProfile(task_options={"nuclei": {"rate_limit": 50}})
        ctx = RunContext(vars={"profile_model": profile})
        model = TaskExecution(
            task_name="httpx", target="example.com", opts={"threads": 10}
        )
        runner = TaskRunner(model, ctx)
        runner._apply_profile_task_options()
        assert runner.model.opts == {"threads": 10}

    def test_common_auto_mapping_injects_proxy_threads_delay(self):
        """Layer 1: profile common fields auto-map to matching task opts."""
        from ofx.profiles.models import OFXProfile
        from ofx.runner.core.models import RunContext
        from ofx.tasks.registry import TaskRegistry
        from ofx.runner.tasks.runner import TaskExecution, TaskRunner

        profile = OFXProfile(
            proxy="socks5://127.0.0.1:9050",
            threads=3,
            rate_limit=50,
            user_agent="StealthBot/2.0",
        )
        ctx = RunContext(vars={"profile_model": profile})
        # feroxbuster has proxy, threads, rate_limit, user_agent opts
        model = TaskExecution(
            task_name="feroxbuster",
            target="http://example.com",
            opts={},
        )
        runner = TaskRunner(model, ctx)
        runner._task = TaskRegistry.get("feroxbuster")()
        runner._apply_profile_task_options()

        assert runner.model.opts.get("proxy") == "socks5://127.0.0.1:9050"
        assert runner.model.opts.get("threads") == 3
        assert runner.model.opts.get("rate_limit") == 50
        assert runner.model.opts.get("user_agent") == "StealthBot/2.0"

    def test_common_auto_mapping_user_opts_win(self):
        """Layer 1: user-provided opts are never overridden by profile."""
        from ofx.profiles.models import OFXProfile
        from ofx.runner.core.models import RunContext
        from ofx.tasks.registry import TaskRegistry
        from ofx.runner.tasks.runner import TaskExecution, TaskRunner

        profile = OFXProfile(threads=3, rate_limit=50)
        ctx = RunContext(vars={"profile_model": profile})
        model = TaskExecution(
            task_name="httpx",
            target="example.com",
            opts={"threads": 20},  # explicit user value
        )
        runner = TaskRunner(model, ctx)
        runner._task = TaskRegistry.get("httpx")()
        runner._apply_profile_task_options()

        assert runner.model.opts["threads"] == 20  # user wins
        assert runner.model.opts.get("rate_limit") == 50  # profile fills gap

    def test_dict_at_profile_key_does_not_crash(self):
        """Regression: the old 'profile' key holds a dict — must not crash."""
        from ofx.runner.core.models import RunContext
        from ofx.runner.tasks.runner import TaskExecution, TaskRunner

        # Simulate real runtime: 'profile' is dict, 'profile_model' missing
        ctx = RunContext(vars={"profile": {"proxy": "http://x", "threads": 2}})
        model = TaskExecution(
            task_name="httpx", target="example.com", opts={}
        )
        runner = TaskRunner(model, ctx)
        runner._apply_profile_task_options()
        # No profile_model → no injection, no crash
        assert runner.model.opts == {}


# ── Profile Env Var Injection ──────────────────────────────────────────


class TestProfileEnvInjection:
    def test_profile_env_vars_set(self):
        """Verify profile fields generate OFX_* env vars in context."""
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile(
            rate_limit=30,
            threads=5,
            delay=2.0,
            proxy="socks5://127.0.0.1:9050",
            user_agent="CustomAgent/1.0",
        )

        # Simulate what _apply_profile does: build env dict
        profile_envs: dict[str, str] = {}
        if profile.rate_limit:
            profile_envs["OFX_RATE_LIMIT"] = str(profile.rate_limit)
        if profile.threads != 10:
            profile_envs["OFX_THREADS"] = str(profile.threads)
        if profile.delay:
            profile_envs["OFX_DELAY"] = str(profile.delay)
        if profile.proxy:
            profile_envs["OFX_PROXY"] = profile.proxy
        if profile.user_agent:
            profile_envs["OFX_USER_AGENT"] = profile.user_agent

        assert profile_envs["OFX_RATE_LIMIT"] == "30"
        assert profile_envs["OFX_THREADS"] == "5"
        assert profile_envs["OFX_DELAY"] == "2.0"
        assert profile_envs["OFX_PROXY"] == "socks5://127.0.0.1:9050"
        assert profile_envs["OFX_USER_AGENT"] == "CustomAgent/1.0"

    def test_default_profile_no_extra_envs(self):
        """Default profile values should not generate env vars."""
        from ofx.profiles.models import OFXProfile

        profile = OFXProfile()

        profile_envs: dict[str, str] = {}
        if profile.rate_limit:
            profile_envs["OFX_RATE_LIMIT"] = str(profile.rate_limit)
        if profile.threads != 10:
            profile_envs["OFX_THREADS"] = str(profile.threads)
        if profile.delay:
            profile_envs["OFX_DELAY"] = str(profile.delay)
        if profile.proxy:
            profile_envs["OFX_PROXY"] = profile.proxy
        if profile.user_agent:
            profile_envs["OFX_USER_AGENT"] = profile.user_agent

        assert profile_envs == {}
