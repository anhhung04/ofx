"""Golden test: secrets must never leak into logs, registry output, or rendered templates."""

from __future__ import annotations

import logging

import pytest

from ofx.runner.templates.resolver import TemplateResolver
from ofx.utils.log import SecretRedactFilter


@pytest.fixture(autouse=True)
def _clean_redact_filter():
    """Reset the singleton between tests."""
    filt = SecretRedactFilter.get_instance()
    filt.clear()
    yield
    filt.clear()


@pytest.fixture
def resolver():
    r = TemplateResolver()
    r.clear_cache()
    r._support_funcs_cache = None
    return r


# ---------------------------------------------------------------------------
# Golden: secret value never appears in rendered output
# ---------------------------------------------------------------------------


class TestSecretGolden:
    """Secrets referenced via {{ secrets.X }} must render as the actual value
    for step execution, but the literal value must never reach a log handler
    when the redaction filter is active."""

    SECRET_VALUE = "s3cr3t-API-k3y-do-not-leak-THIS"

    async def test_secret_renders_for_step_execution(self, resolver):
        ctx = {"secrets": {"API_KEY": self.SECRET_VALUE}}
        result = await resolver.resolve("{{ secrets.API_KEY }}", ctx)
        assert result == self.SECRET_VALUE

    def test_secret_redacted_in_log_message(self):
        filt = SecretRedactFilter.get_instance()
        filt.register_values({self.SECRET_VALUE})

        record = logging.LogRecord(
            "ofx", logging.INFO, "", 0,
            f"Step output: {self.SECRET_VALUE}", (), None,
        )
        filt.filter(record)
        assert self.SECRET_VALUE not in record.msg
        assert "***" in record.msg

    def test_secret_redacted_in_log_args(self):
        filt = SecretRedactFilter.get_instance()
        filt.register_values({self.SECRET_VALUE})

        record = logging.LogRecord(
            "ofx", logging.INFO, "", 0,
            "Step output: %s", (self.SECRET_VALUE,), None,
        )
        filt.filter(record)
        assert self.SECRET_VALUE not in str(record.args)

    def test_secret_redacted_in_tuple_args(self):
        filt = SecretRedactFilter.get_instance()
        filt.register_values({self.SECRET_VALUE})

        record = logging.LogRecord(
            "ofx", logging.INFO, "", 0,
            "Result: %s %s", ("ok", self.SECRET_VALUE), None,
        )
        filt.filter(record)
        assert self.SECRET_VALUE not in str(record.args)

    async def test_secret_not_in_error_messages(self, resolver):
        """If a template error occurs, the secret value should not appear
        in the error message (it gets redacted by the resolver error handler)."""
        filt = SecretRedactFilter.get_instance()
        filt.register_values({self.SECRET_VALUE})

        ctx = {"secrets": {"API_KEY": self.SECRET_VALUE}}
        # Cause a Jinja error by dividing by zero after referencing the secret
        with pytest.raises(Exception) as exc_info:
            await resolver.resolve("{{ 1 / 0 }}", ctx)
        error_text = str(exc_info.value)
        assert self.SECRET_VALUE not in error_text

    async def test_multiple_secrets_all_redacted_in_logs(self):
        secrets = {
            "DB_PASS": "database_password_very_long",
            "TOKEN": "bearer_token_xyz_1234567890",
            "SSH_KEY": "private_key_content_abcdef",
        }
        filt = SecretRedactFilter.get_instance()
        filt.register_values(set(secrets.values()))

        combined = " ".join(secrets.values())
        record = logging.LogRecord(
            "ofx", logging.INFO, "", 0, f"Output: {combined}", (), None,
        )
        filt.filter(record)
        for val in secrets.values():
            assert val not in record.msg

    def test_secret_not_in_formatted_message(self):
        filt = SecretRedactFilter.get_instance()
        filt.register_values({self.SECRET_VALUE})

        logger = logging.getLogger("test.golden.secret")
        logger.addFilter(filt)
        logger.setLevel(logging.DEBUG)

        handler = logging.Handler()
        captured_records: list[logging.LogRecord] = []
        handler.emit = lambda record: captured_records.append(record)
        logger.addHandler(handler)

        try:
            logger.info("Result: %s", self.SECRET_VALUE)
            assert len(captured_records) == 1
            rec = captured_records[0]
            assert self.SECRET_VALUE not in rec.msg
            assert self.SECRET_VALUE not in str(rec.args)
        finally:
            logger.removeHandler(handler)
            logger.removeFilter(filt)


# ---------------------------------------------------------------------------
# LRU cache: hit/miss counting and eviction order
# ---------------------------------------------------------------------------


class TestLRUCacheMetrics:
    """Verify that the template resolver LRU cache tracks hits, misses,
    and evicts in the correct (least-recently-used) order."""

    async def test_cache_miss_then_hit(self, resolver):
        info_before = resolver.cache_info()
        assert info_before["hits"] == 0
        assert info_before["misses"] == 0

        await resolver.resolve("{{ x }}", {"x": "1"})
        info = resolver.cache_info()
        assert info["misses"] == 1
        assert info["hits"] == 0

        await resolver.resolve("{{ x }}", {"x": "2"})
        info = resolver.cache_info()
        assert info["misses"] == 1
        assert info["hits"] == 1

    async def test_eviction_removes_lru_entry(self, resolver):
        resolver._template_cache_max_size = 3

        await resolver.resolve("{{ a }}", {"a": "1"})
        await resolver.resolve("{{ b }}", {"b": "1"})
        await resolver.resolve("{{ c }}", {"c": "1"})

        # Re-access "a" to make it most-recently-used
        await resolver.resolve("{{ a }}", {"a": "2"})

        # Adding a 4th should evict "b" (LRU)
        await resolver.resolve("{{ d }}", {"d": "1"})

        assert "{{ a }}" in resolver._template_cache
        assert "{{ b }}" not in resolver._template_cache
        assert "{{ c }}" in resolver._template_cache
        assert "{{ d }}" in resolver._template_cache

    async def test_cache_size_bounded(self, resolver):
        resolver._template_cache_max_size = 5
        for i in range(20):
            await resolver.resolve(f"{{{{ v{i} }}}}", {f"v{i}": str(i)})
        assert len(resolver._template_cache) <= 5

    async def test_cache_info_reflects_maxsize(self, resolver):
        resolver._template_cache_max_size = 42
        info = resolver.cache_info()
        assert info["maxsize"] == 42

    async def test_clear_cache_resets_counters(self, resolver):
        await resolver.resolve("{{ x }}", {"x": "1"})
        resolver.clear_cache()
        info = resolver.cache_info()
        assert info["hits"] == 0
        assert info["misses"] == 0
        assert info["size"] == 0
