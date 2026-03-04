"""Tests for ofx.api.bundle – analyser, collector, builder, obfuscator, deliverer."""

from __future__ import annotations

import io
import sys
import textwrap
import zipfile
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# analyzer
# ---------------------------------------------------------------------------


class TestDetectOfxImports:
    """detect_ofx_imports() covers all four import patterns."""

    def _detect(self, source: str, **kw):
        from ofx.api.bundle.analyzer import detect_ofx_imports

        return detect_ofx_imports(textwrap.dedent(source), **kw)

    def test_plain_import(self):
        result = self._detect("import ofx.api.opsec")
        assert result == {"opsec"}

    def test_plain_import_deep(self):
        result = self._detect("import ofx.api.opsec.proxy")
        assert result == {"opsec"}

    def test_from_api_import(self):
        result = self._detect("from ofx.api import opsec, c2")
        assert result == {"opsec", "c2"}

    def test_from_submodule_import(self):
        result = self._detect("from ofx.api.evasion import xor_bytes")
        assert result == {"evasion"}

    def test_from_deep_submodule_import(self):
        result = self._detect("from ofx.api.evasion.encoding import xor_bytes")
        assert result == {"evasion"}

    def test_multiple_patterns_combined(self):
        src = """\
            import ofx.api.persistence
            from ofx.api import recon
            from ofx.api.opsec import clean_history_commands
            from ofx.api.ad.kerberos import kerberoast_command
        """
        result = self._detect(src)
        assert result == {"persistence", "recon", "opsec", "ad"}

    def test_unknown_module_silently_dropped(self):
        result = self._detect("from ofx.api import totally_unknown_module")
        assert result == set()

    def test_non_ofx_import_ignored(self):
        result = self._detect("import os\nimport requests")
        assert result == set()

    def test_extra_modules_included(self):
        result = self._detect("x = 1", extra_modules=["c2"])
        assert "c2" in result

    def test_extra_modules_invalid_warns(self, recwarn):
        self._detect("x = 1", extra_modules=["nonexistent_module"])
        assert any("nonexistent_module" in str(w.message) for w in recwarn.list)

    def test_syntax_error_raises_analysis_error(self):
        from ofx.api.bundle.analyzer import AnalysisError

        with pytest.raises(AnalysisError):
            self._detect("def broken(")

    def test_empty_script(self):
        result = self._detect("")
        assert result == set()


# ---------------------------------------------------------------------------
# collector
# ---------------------------------------------------------------------------


class TestCollectModules:
    def test_collect_opsec(self):
        from ofx.api.bundle.collector import collect_modules

        files = collect_modules({"opsec"})
        # Must include parent stubs and at least the opsec package
        assert "ofx/__init__.py" in files
        assert "ofx/api/__init__.py" in files
        opsec_keys = [k for k in files if "opsec" in k]
        assert opsec_keys, "Expected opsec module files in bundle"

    def test_collect_flat_module(self):
        from ofx.api.bundle.collector import collect_modules

        files = collect_modules({"persistence"})
        assert any("persistence" in k for k in files)

    def test_collect_returns_bytes(self):
        from ofx.api.bundle.collector import collect_modules

        files = collect_modules({"c2"})
        for v in files.values():
            assert isinstance(v, bytes)

    def test_empty_set_returns_stubs_only(self):
        from ofx.api.bundle.collector import collect_modules

        files = collect_modules(set())
        assert set(files.keys()) == {"ofx/__init__.py", "ofx/api/__init__.py"}

    def test_stub_content(self):
        from ofx.api.bundle.collector import collect_modules, _STUB_INIT

        files = collect_modules(set())
        assert files["ofx/__init__.py"] == _STUB_INIT


# ---------------------------------------------------------------------------
# builder
# ---------------------------------------------------------------------------


class TestBuildBundle:
    def test_build_bundle_no_imports(self):
        from ofx.api.bundle.builder import build_bundle

        result = build_bundle("x = 1 + 1")
        assert result.modules == frozenset()
        assert "x = 1 + 1" in result.script
        assert result.size_bytes == len(result.bootstrap.encode())

    def test_build_bundle_with_import(self):
        from ofx.api.bundle.builder import build_bundle

        script = "from ofx.api import opsec\nprint(opsec)"
        result = build_bundle(script)
        assert "opsec" in result.modules

    def test_bootstrap_is_valid_python(self):
        from ofx.api.bundle.builder import build_bundle
        import ast

        result = build_bundle("print('hello')")
        # Must parse without error
        ast.parse(result.bootstrap)

    def test_bootstrap_executes_correctly(self):
        """The bootstrap must extract the zip and execute the user script."""
        from ofx.api.bundle.builder import build_bundle

        script = "import sys; sys.stdout.write('bundle_ok')"
        result = build_bundle(script)

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            exec(compile(result.bootstrap, "<test_bootstrap>", "exec"), {"__name__": "__main__"})
        finally:
            sys.stdout = old_stdout

        assert "bundle_ok" in captured.getvalue()

    def test_bundle_result_frozen(self):
        from ofx.api.bundle.builder import build_bundle

        result = build_bundle("x = 1")
        with pytest.raises(Exception):
            result.script = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# obfuscator
# ---------------------------------------------------------------------------


class TestObfuscateBootstrap:
    def test_obfuscated_is_valid_python(self):
        import ast
        from ofx.api.bundle.obfuscator import obfuscate_bootstrap

        loader = obfuscate_bootstrap("x = 42")
        ast.parse(loader)  # must not raise

    def test_obfuscated_executes_correctly(self):
        from ofx.api.bundle.obfuscator import obfuscate_bootstrap

        script = "import sys; sys.stdout.write('obfuscated_ok')"
        loader = obfuscate_bootstrap(script)

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            exec(compile(loader, "<test_obf>", "exec"), {})
        finally:
            sys.stdout = old_stdout

        assert "obfuscated_ok" in captured.getvalue()

    def test_round_trip_with_bundle(self):
        from ofx.api.bundle.builder import build_bundle
        from ofx.api.bundle.obfuscator import obfuscate_bootstrap

        script = "import sys; sys.stdout.write('round_trip')"
        result = build_bundle(script)
        loader = obfuscate_bootstrap(result.bootstrap)

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            exec(compile(loader, "<test_rt>", "exec"), {})
        finally:
            sys.stdout = old_stdout

        assert "round_trip" in captured.getvalue()

    def test_explicit_key(self):
        from ofx.api.bundle.obfuscator import obfuscate_bootstrap

        key = b"\x01" * 16
        loader = obfuscate_bootstrap("x = 1", key=key)
        assert key.hex() in loader

    def test_empty_key_raises(self):
        from ofx.api.bundle.obfuscator import obfuscate_bootstrap

        with pytest.raises(ValueError):
            obfuscate_bootstrap("x = 1", key=b"")

    def test_different_keys_produce_different_output(self):
        from ofx.api.bundle.obfuscator import obfuscate_bootstrap

        k1, k2 = b"\xaa" * 16, b"\xbb" * 16
        l1 = obfuscate_bootstrap("x = 1", key=k1)
        l2 = obfuscate_bootstrap("x = 1", key=k2)
        assert l1 != l2

    def test_obfuscation_error_on_bad_source(self):
        from ofx.api.bundle.obfuscator import ObfuscationError, obfuscate_bootstrap

        with pytest.raises(ObfuscationError):
            obfuscate_bootstrap("def broken(")


class TestObfuscateSources:
    def _make_files(self) -> dict[str, bytes]:
        return {
            "ofx/__init__.py": b"# stub\n",
            "ofx/api/__init__.py": b"# stub\n",
            "ofx/api/opsec/__init__.py": b"def hello():\n    return 'hi'\n",
            "ofx/api/opsec/utils.py": b"X = 42\n",
        }

    def test_keys_unchanged(self):
        from ofx.api.bundle.obfuscator import obfuscate_sources

        result = obfuscate_sources(self._make_files())
        assert set(result.keys()) == {
            "ofx/__init__.py",
            "ofx/api/__init__.py",
            "ofx/api/opsec/__init__.py",
            "ofx/api/opsec/utils.py",
        }

    def test_values_are_bytes(self):
        from ofx.api.bundle.obfuscator import obfuscate_sources

        result = obfuscate_sources(self._make_files())
        for v in result.values():
            assert isinstance(v, bytes)

    def test_source_not_present_in_output(self):
        """Raw source text must not appear in obfuscated stub bytes."""
        from ofx.api.bundle.obfuscator import obfuscate_sources

        result = obfuscate_sources(self._make_files())
        assert b"def hello" not in result["ofx/api/opsec/__init__.py"]
        assert b"X = 42" not in result["ofx/api/opsec/utils.py"]

    def test_stub_contains_marshal_loader(self):
        from ofx.api.bundle.obfuscator import obfuscate_sources

        result = obfuscate_sources(self._make_files())
        stub = result["ofx/api/opsec/__init__.py"].decode()
        assert "marshal" in stub
        assert "fromhex" in stub

    def test_obfuscated_module_executes_correctly(self):
        """exec()-ing the stub in a fresh namespace must populate names."""
        from ofx.api.bundle.obfuscator import obfuscate_sources

        files = {"mod.py": b"answer = 6 * 7\n"}
        result = obfuscate_sources(files)
        ns: dict = {}
        exec(compile(result["mod.py"], "mod.py", "exec"), ns)
        assert ns["answer"] == 42

    def test_non_py_files_passed_through(self):
        from ofx.api.bundle.obfuscator import obfuscate_sources

        files = {"data.txt": b"hello", "ofx/__init__.py": b"x=1\n"}
        result = obfuscate_sources(files)
        assert result["data.txt"] == b"hello"

    def test_empty_dict_returns_empty(self):
        from ofx.api.bundle.obfuscator import obfuscate_sources

        assert obfuscate_sources({}) == {}

    def test_syntax_error_raises_obfuscation_error(self):
        from ofx.api.bundle.obfuscator import ObfuscationError, obfuscate_sources

        with pytest.raises(ObfuscationError, match="bad.py"):
            obfuscate_sources({"bad.py": b"def broken("})

    def test_build_bundle_obfuscate_sources_flag(self):
        """build_bundle(obfuscate_sources=True) must produce a working bootstrap."""
        from ofx.api.bundle.builder import build_bundle

        script = "import sys; sys.stdout.write('src_obf_ok')"
        result = build_bundle(script, obfuscate_sources=True)

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            exec(compile(result.bootstrap, "<test_src_obf>", "exec"), {"__name__": "__main__"})
        finally:
            sys.stdout = old_stdout

        assert "src_obf_ok" in captured.getvalue()

    def test_xor_produces_different_output_each_run(self):
        """Each call uses a random key, so identical input → different stubs."""
        from ofx.api.bundle.obfuscator import obfuscate_sources

        files = {"mod.py": b"x = 1\n"}
        r1 = obfuscate_sources(files)
        r2 = obfuscate_sources(files)
        assert r1["mod.py"] != r2["mod.py"]

    def test_stub_contains_xor_decryption(self):
        """Stub must contain both a key hex and encrypted data hex."""
        from ofx.api.bundle.obfuscator import obfuscate_sources

        result = obfuscate_sources({"mod.py": b"x = 1\n"})
        stub = result["mod.py"].decode()
        # Two fromhex calls: one for key, one for encrypted data
        assert stub.count("fromhex") == 2

    def test_metadata_stripped_filename(self):
        """co_filename in the bytecode must not contain the original path."""
        import marshal
        from ofx.api.bundle.obfuscator import _strip_code

        code = compile(b"x = 1", "secret/path/mod.py", "exec")
        stripped = _strip_code(code)
        assert "secret" not in stripped.co_filename
        assert stripped.co_filename == "<module>"

    def test_metadata_stripped_docstrings(self):
        """Module and function docstrings must be removed."""
        import marshal
        from ofx.api.bundle.obfuscator import _strip_code

        src = b'"""Module doc."""\ndef foo():\n    """Func doc."""\n    return 1\n'
        code = compile(src, "mod.py", "exec")
        stripped = _strip_code(code)
        # Module docstring (first const) should be None
        assert stripped.co_consts[0] is None
        # Function code object's docstring should also be None
        func_code = [c for c in stripped.co_consts if hasattr(c, "co_code")][0]
        assert func_code.co_consts[0] is None


# ---------------------------------------------------------------------------
# deliverer — adapters
# ---------------------------------------------------------------------------


class TestUploadAdapter:
    def _make_runner(self, upload_side_effect=None, run_return="ok"):
        runner = MagicMock()
        runner.upload.side_effect = upload_side_effect
        runner.run.return_value = run_return
        return runner

    def test_deliver_calls_upload_and_run(self):
        from ofx.api.bundle.deliverer import UploadAdapter

        runner = self._make_runner()
        adapter = UploadAdapter(runner, remote_tmp="/tmp/t.py")
        result = adapter.deliver("print('hi')")

        runner.upload.assert_called_once()
        # Two run calls: execute the script + rm cleanup
        assert runner.run.call_count == 2
        assert result == "ok"

    def test_deliver_uses_python3_by_default(self):
        from ofx.api.bundle.deliverer import UploadAdapter

        runner = self._make_runner()
        adapter = UploadAdapter(runner, remote_tmp="/tmp/t.py")
        adapter.deliver("x = 1")

        exec_call = runner.run.call_args_list[0]
        assert "python3 /tmp/t.py" in exec_call[0][0]

    def test_windows_mode_uses_python_and_del(self):
        from ofx.api.bundle.deliverer import UploadAdapter

        runner = self._make_runner()
        adapter = UploadAdapter(runner, remote_tmp="C:\\Temp\\t.py", windows=True)
        adapter.deliver("x = 1")

        exec_call = runner.run.call_args_list[0][0][0]
        cleanup_call = runner.run.call_args_list[1][0][0]
        assert "python C:\\Temp\\t.py" in exec_call
        assert "del /f /q" in cleanup_call

    def test_custom_python_name(self):
        from ofx.api.bundle.deliverer import UploadAdapter

        runner = self._make_runner()
        adapter = UploadAdapter(runner, python="python3.11", remote_tmp="/tmp/t.py")
        adapter.deliver("x = 1")
        assert "python3.11 /tmp/t.py" in runner.run.call_args_list[0][0][0]

    def test_upload_failure_propagates(self):
        from ofx.api.bundle.deliverer import UploadAdapter

        runner = self._make_runner(upload_side_effect=RuntimeError("conn fail"))
        adapter = UploadAdapter(runner, remote_tmp="/tmp/t.py")
        with pytest.raises(RuntimeError, match="conn fail"):
            adapter.deliver("x = 1")


class TestInlineAdapter:
    def test_deliver_runs_base64_python_command(self):
        from ofx.api.bundle.deliverer import InlineAdapter

        runner = MagicMock()
        runner.run.return_value = "inline_ok"
        adapter = InlineAdapter(runner)
        result = adapter.deliver("print('hello')")

        runner.run.assert_called_once()
        cmd = runner.run.call_args[0][0]
        assert "python3" in cmd
        assert "base64" in cmd
        assert result == "inline_ok"

    def test_windows_mode(self):
        from ofx.api.bundle.deliverer import InlineAdapter

        runner = MagicMock()
        runner.run.return_value = "ok"
        adapter = InlineAdapter(runner, windows=True)
        adapter.deliver("x = 1")

        cmd = runner.run.call_args[0][0]
        assert cmd.startswith("python -c")


class TestMakeAdapter:
    def test_upload_method_returns_upload_adapter(self):
        from ofx.api.bundle.deliverer import UploadAdapter, make_adapter

        runner = MagicMock()
        adapter = make_adapter(runner, "upload")
        assert isinstance(adapter, UploadAdapter)

    def test_http_method_returns_http_adapter(self):
        from ofx.api.bundle.deliverer import HttpAdapter, make_adapter

        runner = MagicMock()
        adapter = make_adapter(runner, "http")
        assert isinstance(adapter, HttpAdapter)

    def test_inline_method_returns_inline_adapter(self):
        from ofx.api.bundle.deliverer import InlineAdapter, make_adapter

        runner = MagicMock()
        adapter = make_adapter(runner, "inline")
        assert isinstance(adapter, InlineAdapter)

    def test_unknown_method_raises(self):
        from ofx.api.bundle.deliverer import make_adapter

        with pytest.raises(ValueError, match="Unknown delivery method"):
            make_adapter(MagicMock(), "ftp")

    def test_auto_with_upload_runner(self):
        """auto should pick UploadAdapter when runner has real upload()."""
        from ofx.api.bundle.deliverer import UploadAdapter, make_adapter

        runner = MagicMock()
        # MagicMock has upload attr, and _runner_has_upload falls back to hasattr check
        adapter = make_adapter(runner, "auto")
        assert isinstance(adapter, UploadAdapter)

    def test_windows_flag_propagated(self):
        from ofx.api.bundle.deliverer import UploadAdapter, make_adapter

        runner = MagicMock()
        adapter = make_adapter(runner, "upload", windows=True)
        assert isinstance(adapter, UploadAdapter)
        assert adapter.windows is True
        assert adapter.python == "python"


class TestCustomAdapter:
    def test_custom_adapter_used_directly(self):
        from ofx.api.bundle.deliverer import deliver_and_run

        class MyAdapter:
            def __init__(self):
                self.called = False

            def deliver(self, bootstrap: str) -> str:
                self.called = True
                return f"custom:{bootstrap[:5]}"

        adapter = MyAdapter()
        runner = MagicMock()
        result = deliver_and_run(runner, "print('hi')", adapter=adapter)

        assert adapter.called
        assert result.startswith("custom:")
        # Runner methods should NOT be called if custom adapter is used
        runner.upload.assert_not_called()
        runner.run.assert_not_called()

    def test_custom_adapter_satisfies_protocol(self):
        from ofx.api.bundle.deliverer import BundleAdapter

        class GoodAdapter:
            def deliver(self, bootstrap: str) -> str:
                return "ok"

        assert isinstance(GoodAdapter(), BundleAdapter)


class TestDeliverAndRun:
    def _make_runner(self, upload_side_effect=None, run_return="ok"):
        runner = MagicMock()
        runner.upload.side_effect = upload_side_effect
        runner.run.return_value = run_return
        return runner

    def test_upload_method_calls_runner(self):
        from ofx.api.bundle.deliverer import deliver_and_run

        runner = self._make_runner()
        result = deliver_and_run(runner, "print('hi')", method="upload", remote_tmp="/tmp/t.py")

        runner.upload.assert_called_once()
        assert runner.run.call_count == 2  # exec + rm
        assert result == "ok"

    def test_upload_failure_raises_delivery_error(self):
        from ofx.api.bundle.deliverer import DeliveryError, deliver_and_run

        runner = self._make_runner(upload_side_effect=RuntimeError("conn failed"))
        with pytest.raises(DeliveryError, match="Delivery failed"):
            deliver_and_run(runner, "x = 1", method="upload")

    def test_unknown_method_raises_value_error(self):
        from ofx.api.bundle.deliverer import deliver_and_run

        runner = self._make_runner()
        with pytest.raises(ValueError, match="Unknown delivery method"):
            deliver_and_run(runner, "x = 1", method="ftp")

    def test_adapter_kwarg_overrides_method(self):
        """When adapter= is given, method= is ignored."""
        from ofx.api.bundle.deliverer import deliver_and_run

        class StubAdapter:
            def deliver(self, bootstrap: str) -> str:
                return "stub"

        runner = self._make_runner()
        result = deliver_and_run(runner, "x=1", adapter=StubAdapter(), method="upload")
        assert result == "stub"
        runner.upload.assert_not_called()


# ---------------------------------------------------------------------------
# run_remote convenience wrapper
# ---------------------------------------------------------------------------


class TestRunRemote:
    def test_run_remote_upload_no_obfuscation(self):
        from ofx.api.bundle import run_remote

        runner = MagicMock()
        runner.run.return_value = "done"

        result = run_remote("x = 1", runner, obfuscate=False, method="upload")

        runner.upload.assert_called_once()
        assert result == "done"

    def test_run_remote_with_obfuscation(self):
        from ofx.api.bundle import run_remote

        runner = MagicMock()
        runner.run.return_value = "done_obf"

        result = run_remote("x = 1", runner, obfuscate=True, method="upload")

        runner.upload.assert_called_once()
        assert result == "done_obf"

    def test_run_remote_with_custom_adapter(self):
        from ofx.api.bundle import run_remote

        class MyAdapter:
            def deliver(self, bootstrap: str) -> str:
                return "custom_done"

        runner = MagicMock()
        result = run_remote("x = 1", runner, adapter=MyAdapter(), obfuscate=False)
        assert result == "custom_done"
        runner.upload.assert_not_called()

    def test_run_remote_windows_mode(self):
        from ofx.api.bundle import run_remote

        runner = MagicMock()
        runner.run.return_value = "win_ok"

        result = run_remote("x = 1", runner, obfuscate=False, method="upload", windows=True)

        exec_cmd = runner.run.call_args_list[0][0][0]
        assert "python " in exec_cmd  # not python3
        assert result == "win_ok"
