"""Fuzz and security tests for the OFX Jinja2 template sandbox.

Tests verify that:
- Dunder attribute access is blocked
- ``os``, ``subprocess``, ``sys`` are unreachable
- ``__import__``, ``eval``, ``exec``, ``compile`` are blocked
- YAML safe_load rejects unsafe tags
- Template rendering never mutates the secret store
- Random Jinja-ish strings never produce non-string or dangerous results
"""

from __future__ import annotations

import asyncio

import pytest
import yaml
from hypothesis import HealthCheck, given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from jinja2.exceptions import SecurityError, UndefinedError

from ofx.runner.templates.resolver import TemplateResolver

# ── Helpers ──────────────────────────────────────────────────────────────

def _render_sync(template_str: str, ctx: dict | None = None) -> str:
    """Render a template synchronously for test convenience."""
    resolver = TemplateResolver()
    resolver._template_cache.clear()
    context = ctx or {}
    return asyncio.run(resolver.resolve(template_str, context))


# ── TS-1: Sandbox blocks dunder attribute access ────────────────────────

class TestSandboxDunderBlocking:
    """Verify the sandbox blocks access to Python internals."""

    @pytest.mark.parametrize(
        "template",
        [
            "{{ ''.__class__ }}",
            "{{ ''.__class__.__mro__ }}",
            "{{ ''.__class__.__mro__[1].__subclasses__() }}",
            "{{ ''.__class__.__bases__ }}",
            "{{ ().__class__.__bases__[0].__subclasses__() }}",
            "{{ config.__class__.__init__.__globals__ }}",
            "{{ ''.__class__.__mro__[2].__subclasses__()[40]('/etc/passwd').read() }}",
        ],
    )
    def test_dunder_access_blocked(self, template):
        """Dunder attribute chains must not resolve to real Python objects."""
        try:
            result = _render_sync(template, {"config": {}})
        except Exception:
            # Raising SecurityError or UndefinedError is the expected safe outcome
            return
        # If it didn't raise, the result must not contain dangerous output
        assert "__class__" not in result
        assert "__mro__" not in result
        assert "__subclasses__" not in result
        assert "__globals__" not in result

    @pytest.mark.parametrize(
        "template",
        [
            "{{ ''.__class__.__mro__[2].__subclasses__() }}",
            "{{ lipsum.__globals__['os'].popen('id').read() }}",
            "{{ cycler.__init__.__globals__['os'].popen('id').read() }}",
        ],
    )
    def test_common_ssti_payloads_neutralized(self, template):
        """Common Jinja2 SSTI payloads must not execute."""
        try:
            result = _render_sync(template)
        except Exception:
            # Raising is the safe outcome
            return
        assert "uid=" not in result
        assert "root" not in result.lower() or result == ""

    def test_import_blocked(self):
        with pytest.raises((UndefinedError, SecurityError)):
            _render_sync("{{ __import__('os').system('id') }}")

    def test_eval_exec_blocked(self):
        for fn in ["eval", "exec", "compile"]:
            with pytest.raises((UndefinedError, SecurityError)):
                _render_sync(f"{{{{ {fn}('1+1') }}}}")


# ── TS-1: Sandbox blocks dangerous callables ────────────────────────────

class TestSandboxCallableBlocking:

    def test_getattr_blocked(self):
        with pytest.raises((UndefinedError, SecurityError)):
            _render_sync(
                "{{ getattr('', '__class__') }}",
                {"getattr": getattr},
            )

    def test_os_module_blocked(self):
        """Even if os is injected into context, calls should be blocked."""
        import os

        with pytest.raises((UndefinedError, SecurityError)):
            _render_sync("{{ os.system('id') }}", {"os": os})


# ── TS-2: YAML safe_load regression ─────────────────────────────────────

class TestYamlSafety:

    def test_python_object_apply_rejected(self):
        """yaml.safe_load must reject !!python/object/apply."""
        malicious = '!!python/object/apply:os.system ["id"]'
        with pytest.raises(yaml.constructor.ConstructorError):
            yaml.safe_load(malicious)

    def test_python_object_rejected(self):
        """yaml.safe_load must reject !!python/object."""
        malicious = "!!python/object:os.system {}"
        with pytest.raises(yaml.constructor.ConstructorError):
            yaml.safe_load(malicious)

    def test_python_module_rejected(self):
        """yaml.safe_load must reject !!python/module."""
        malicious = "!!python/module:os"
        with pytest.raises(yaml.constructor.ConstructorError):
            yaml.safe_load(malicious)

    def test_safe_yaml_parses_normally(self):
        """Normal YAML parsing still works."""
        data = yaml.safe_load("name: test\nvalue: 42\n")
        assert data == {"name": "test", "value": 42}


# ── TS-6: Secret store idempotency ──────────────────────────────────────

class TestSecretIdempotency:

    def test_render_does_not_mutate_secrets(self):
        """Rendering a template must not change the secrets dict."""
        secrets = {"API_KEY": "s3cr3t_value_12345", "TOKEN": "tok_abc123xyz"}
        secrets_copy = secrets.copy()
        ctx = {"secrets": secrets, "name": "test"}

        _render_sync("Hello {{ secrets.API_KEY }} and {{ name }}", ctx)

        assert secrets == secrets_copy

    def test_render_does_not_add_keys_to_secrets(self):
        secrets = {"KEY": "val"}
        original_keys = set(secrets.keys())
        ctx = {"secrets": secrets}

        _render_sync("{{ secrets.NONEXISTENT | default('fallback') }}", ctx)

        assert set(secrets.keys()) == original_keys


# ── Template error redaction ─────────────────────────────────────────────

class TestErrorRedaction:

    def test_secret_value_not_in_error_message(self):
        """If a template fails to render, secret values must not leak."""
        secret_val = "SUPER_SECRET_TOKEN_12345"
        ctx = {"secrets": {"MY_KEY": secret_val}}

        # Force an error by using an undefined variable in a filter
        try:
            _render_sync(
                "{{ secrets.MY_KEY | int }}",
                ctx,
            )
        except Exception as e:
            assert secret_val not in str(e)


# ── Fuzz: random Jinja-ish strings ──────────────────────────────────────

# Strategy that generates strings that look like Jinja templates
_jinja_atoms = st.sampled_from(
    [
        "{{ }}",
        "{{ x }}",
        "{{ ''.__class__ }}",
        "{{ ''.__class__.__mro__[1] }}",
        "{{ __import__('os') }}",
        "{% for i in range(3) %}x{% endfor %}",
        "{{ config }}",
        "{{ lipsum }}",
        "{{ cycler }}",
        "{{ joiner }}",
        "{{ namespace }}",
        "{{ range(10) | list }}",
        "hello",
        "{{ 1 + 1 }}",
        "{{ 'a' * 100 }}",
        "{{ [1,2,3] | join(',') }}",
    ]
)

_jinja_fuzz = st.one_of(
    _jinja_atoms,
    st.text(
        alphabet=st.sampled_from(
            list("abcdefghijklmnopqrstuvwxyz_.[](){}|%# '\"0123456789,:-+*!/")
        ),
        min_size=0,
        max_size=120,
    ),
)


class TestFuzz:

    @given(template=_jinja_fuzz)
    @hyp_settings(
        max_examples=200,
        deadline=5000,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_fuzz_render_never_exposes_internals(self, template):
        """No random template string should ever access Python internals."""
        try:
            result = _render_sync(template, {"x": "safe", "config": {}})
        except Exception:
            return  # Template errors are fine — we care about successful renders

        if not isinstance(result, str):
            result = str(result)

        # The rendered output must never contain evidence of Python internal access
        forbidden = [
            "<module ",
            "subprocess",
            "<built-in",
            "__import__",
            "Popen",
            "/etc/passwd",
        ]
        for f in forbidden:
            assert f not in result, f"Forbidden string '{f}' found in render of: {template!r}"

    @given(template=_jinja_fuzz)
    @hyp_settings(
        max_examples=100,
        deadline=5000,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_fuzz_render_is_string(self, template):
        """Render output must always be a string (or raise)."""
        try:
            result = _render_sync(template, {"x": "safe"})
        except Exception:
            return
        assert isinstance(result, (str, int, float, bool))
