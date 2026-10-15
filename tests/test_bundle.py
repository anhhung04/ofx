"""Tests for ofx.lib.bundle – analyser, collector, builder, obfuscator, deliverer."""

from __future__ import annotations

import base64
import io
import os
import re
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


class TestDetectOfxImports:
    """detect_ofx_imports() covers all four import patterns."""

    def _detect(self, source: str, **kw):
        from ofx.lib.bundle.analyzer import detect_ofx_imports

        return detect_ofx_imports(textwrap.dedent(source), **kw)

    def test_plain_import(self):
        result = self._detect("import ofx.lib.opsec")
        assert result == {"opsec"}

    def test_plain_import_deep(self):
        result = self._detect("import ofx.lib.opsec.proxy")
        assert result == {"opsec"}

    def test_from_api_import(self):
        result = self._detect("from ofx.lib import opsec, c2")
        assert result == {"opsec", "c2"}

    def test_from_submodule_import(self):
        result = self._detect("from ofx.lib.evasion import xor_bytes")
        assert result == {"evasion"}

    def test_from_deep_submodule_import(self):
        result = self._detect("from ofx.lib.evasion.encoding import xor_bytes")
        assert result == {"evasion"}

    def test_multiple_patterns_combined(self):
        src = """\
            import ofx.lib.persistence
            from ofx.lib import recon
            from ofx.lib.opsec import clean_history_commands
            from ofx.lib.ad.kerberos import kerberoast_command
        """
        result = self._detect(src)
        assert result == {"persistence", "recon", "opsec", "ad"}

    def test_unknown_module_silently_dropped(self):
        result = self._detect("from ofx.lib import totally_unknown_module")
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
        from ofx.lib.bundle.analyzer import AnalysisError

        with pytest.raises(AnalysisError):
            self._detect("def broken(")

    def test_empty_script(self):
        result = self._detect("")
        assert result == set()

class TestDetectOfxImportPaths:
    """detect_ofx_import_paths() returns dotted paths relative to ofx.lib."""

    def _detect(self, source: str, **kw):
        from ofx.lib.bundle.analyzer import detect_ofx_import_paths

        return detect_ofx_import_paths(textwrap.dedent(source), **kw)

    def test_plain_import(self):
        result = self._detect("import ofx.lib.opsec")
        assert result == {"opsec"}

    def test_plain_import_deep(self):
        result = self._detect("import ofx.lib.opsec.proxy")
        assert result == {"opsec.proxy"}

    def test_from_api_import(self):
        result = self._detect("from ofx.lib import opsec, c2")
        assert result == {"opsec", "c2"}

    def test_from_submodule_import(self):
        result = self._detect("from ofx.lib.evasion import xor_bytes")
        assert result == {"evasion"}

    def test_from_deep_submodule_import(self):
        result = self._detect("from ofx.lib.evasion.encoding import xor_bytes")
        assert result == {"evasion.encoding"}

    def test_acceptance_split_targets(self):
        """The granular acceptance case resolves to a single leaf path."""
        result = self._detect("from ofx.lib.recon.targets import split_targets")
        assert result == {"recon.targets"}

    def test_nested_package_path(self):
        result = self._detect(
            "from ofx.lib.exploitation.shellcode.connectors import get_registry"
        )
        assert result == {"exploitation.shellcode.connectors"}

    def test_bare_package_from_import(self):
        """from ofx.lib.recon import X keeps recon bare (attribute use unknown)."""
        result = self._detect("from ofx.lib.recon import split_targets")
        assert result == {"recon"}

    def test_unknown_module_silently_dropped(self):
        result = self._detect("from ofx.lib import totally_unknown_module")
        assert result == set()

    def test_unknown_deep_path_dropped(self):
        result = self._detect("from ofx.lib.recon.totally_unknown import x")
        assert result == set()

    def test_extra_dotted_path_honoured(self):
        result = self._detect("x = 1", extra_modules=["recon.targets"])
        assert result == {"recon.targets"}

    def test_extra_with_ofx_api_prefix(self):
        result = self._detect("x = 1", extra_modules=["ofx.lib.recon.targets"])
        assert result == {"recon.targets"}

    def test_extra_top_level_name(self):
        result = self._detect("x = 1", extra_modules=["c2"])
        assert result == {"c2"}

    def test_extra_invalid_warns(self, recwarn):
        self._detect("x = 1", extra_modules=["nonexistent_module"])
        assert any("nonexistent_module" in str(w.message) for w in recwarn.list)

    def test_backward_detect_ofx_imports_wrapper(self):
        from ofx.lib.bundle.analyzer import detect_ofx_imports

        assert detect_ofx_imports("import ofx.lib.opsec.proxy") == {"opsec"}
        assert detect_ofx_imports("from ofx.lib import opsec, c2") == {"opsec", "c2"}

    def test_syntax_error_raises_analysis_error(self):
        from ofx.lib.bundle.analyzer import AnalysisError

        with pytest.raises(AnalysisError):
            self._detect("def broken(")

class TestCollectModules:
    def test_collect_opsec(self):
        from ofx.lib.bundle.collector import collect_modules

        files = collect_modules({"opsec"})
        assert "ofx/__init__.py" in files
        assert "ofx/lib/__init__.py" in files
        opsec_keys = [k for k in files if "opsec" in k]
        assert opsec_keys, "Expected opsec module files in bundle"

    def test_collect_flat_module(self):
        from ofx.lib.bundle.collector import collect_modules

        files = collect_modules({"persistence"})
        assert any("persistence" in k for k in files)

    def test_collect_returns_bytes(self):
        from ofx.lib.bundle.collector import collect_modules

        files = collect_modules({"c2"})
        for v in files.values():
            assert isinstance(v, bytes)

    def test_empty_set_returns_stubs_only(self):
        from ofx.lib.bundle.collector import collect_modules

        files = collect_modules(set())
        assert set(files.keys()) == {
            "ofx/__init__.py",
            "ofx/lib/__init__.py",
            "ofx/lib/_compat.py",
        }

    def test_stub_content(self):
        from ofx.lib.bundle.collector import _STUB_INIT, collect_modules

        files = collect_modules(set())
        assert files["ofx/__init__.py"] == _STUB_INIT

class TestCollectModulesGranular:
    """collect_modules_granular() packs leaf modules with lazy stubs."""

    def test_split_targets_only(self):
        from ofx.lib.bundle.collector import collect_modules_granular

        files = collect_modules_granular({"recon.targets"})
        assert "ofx/__init__.py" in files
        assert "ofx/lib/__init__.py" in files
        assert "ofx/lib/_compat.py" in files
        assert "ofx/lib/recon/targets.py" in files
        # Lazy stub, not the eager real __init__.
        assert "ofx/lib/recon/__init__.py" in files
        # Sibling modules must NOT be packed.
        for sibling in ("osint", "portscan", "web"):
            assert not any(f"/{sibling}.py" in k for k in files), sibling

    def test_split_targets_stub_mapping(self):
        from ofx.lib.bundle.collector import collect_modules_granular

        files = collect_modules_granular({"recon.targets"})
        stub = files["ofx/lib/recon/__init__.py"].decode()
        assert "__getattr__" in stub  # PEP 562
        assert "__dir__" in stub
        assert "_importlib" in stub
        # Exported name maps to its submodule; direct submodules map to self.
        assert "'split_targets': 'targets'" in stub
        assert "'targets': 'targets'" in stub
        assert "'osint': 'osint'" in stub
        assert "__all__" in stub
        assert "'split_targets'" in stub  # __all__ preserved
        # Unknown names raise AttributeError.
        assert "has no attribute" in stub

    def test_api_root_stub_is_lazy(self):
        from ofx.lib.bundle.collector import collect_modules_granular

        files = collect_modules_granular({"recon.targets"})
        root = files["ofx/lib/__init__.py"].decode()
        assert "__getattr__" in root
        # The eager real __init__ imports every subpackage; the stub maps them.
        assert "'recon': 'recon'" in root
        assert "'opsec': 'opsec'" in root

    def test_bare_package_kept_whole(self):
        from ofx.lib.bundle.collector import collect_modules_granular

        files = collect_modules_granular({"recon"})
        names = {k for k in files if k.startswith("ofx/lib/recon")}
        assert any(k.endswith("/osint.py") for k in names)
        assert any(k.endswith("/portscan.py") for k in names)
        assert any(k.endswith("/web.py") for k in names)
        assert any(k.endswith("/targets.py") for k in names)
        # Real eager __init__ preserved for the whole package.
        init = files["ofx/lib/recon/__init__.py"].decode()
        assert "from .osint import" in init

    def test_nested_packages_get_stubs(self):
        from ofx.lib.bundle.collector import collect_modules_granular

        files = collect_modules_granular({"exploitation.exploit.connectors"})
        # Every package on the path is a pure re-exporter -> lazy stubs.
        for pkg in (
            "ofx/lib/exploitation/__init__.py",
            "ofx/lib/exploitation/exploit/__init__.py",
            "ofx/lib/exploitation/exploit/connectors/__init__.py",
        ):
            stub = files[pkg].decode()
            assert "__getattr__" in stub, pkg
        # exploitation maps its subpackages; exploit maps base/runner modules.
        exploitation_stub = files["ofx/lib/exploitation/__init__.py"].decode()
        assert "'exploit': 'exploit'" in exploitation_stub
        assert "'shellcode': 'shellcode'" in exploitation_stub
        assert "'webshell': 'webshell'" in exploitation_stub
        exploit_stub = files["ofx/lib/exploitation/exploit/__init__.py"].decode()
        assert "'base': 'base'" in exploit_stub
        assert "'runner': 'runner'" in exploit_stub
        # Namespaces dirs' own modules are not dragged in.
        assert not any("/shellcode/" in k for k in files)
        assert not any("/webshell/" in k for k in files)

    def test_side_effect_package_kept_whole(self):
        from ofx.lib.bundle.collector import collect_modules_granular

        files = collect_modules_granular({"exploitation.shellcode.connectors"})
        # connectors/__init__ builds a global registry at import time.
        init = files[
            "ofx/lib/exploitation/shellcode/connectors/__init__.py"
        ].decode()
        assert "ConnectorRegistry" in init
        assert "__getattr__" not in init
        # shellcode defines local API too -> whole.
        shellcode_init = files["ofx/lib/exploitation/shellcode/__init__.py"].decode()
        assert "__getattr__" not in shellcode_init
        assert "OSShellcodes" in shellcode_init
        # Unrelated exploitation modules are not dragged in.
        assert not any("/exploit/" in k for k in files)

    def test_transitive_closure_across_packages(self):
        from ofx.lib.bundle.collector import collect_modules_granular

        files = collect_modules_granular({"search.fofa"})
        assert "ofx/lib/search/fofa.py" in files
        # fofa.py imports ofx.lib.credential_config and ofx.lib.http.
        assert "ofx/lib/credential_config.py" in files
        assert "ofx/lib/http/__init__.py" in files
        # http is packed whole (locally-defined API).
        assert any(k.startswith("ofx/lib/http/") for k in files)
        # Sibling search modules remain excluded.
        assert "ofx/lib/search/shodan.py" not in files
        assert "ofx/lib/search/zoomeye.py" not in files

    def test_transitive_closure_flat_module(self):
        from ofx.lib.bundle.collector import collect_modules_granular

        files = collect_modules_granular({"lateral"})
        assert "ofx/lib/lateral.py" in files
        # lateral.py imports ofx.lib.post.registry (+ its TYPE_CHECKING dep).
        assert "ofx/lib/post/registry.py" in files
        assert "ofx/lib/post/base.py" in files
        # post gets a lazy stub; unrelated runners are not dragged in.
        stub = files["ofx/lib/post/__init__.py"].decode()
        assert "__getattr__" in stub
        assert not any("/runners/" in k for k in files)

    def test_empty_set_returns_root_stubs_only(self):
        from ofx.lib.bundle.collector import collect_modules_granular

        files = collect_modules_granular(set())
        assert set(files.keys()) == {
            "ofx/__init__.py",
            "ofx/lib/__init__.py",
            "ofx/lib/_compat.py",
        }
        assert "__getattr__" in files["ofx/lib/__init__.py"].decode()

class TestBuildBundle:
    def test_build_bundle_no_imports(self):
        from ofx.lib.bundle.builder import build_bundle

        result = build_bundle("x = 1 + 1")
        assert result.modules == frozenset()
        assert "x = 1 + 1" in result.script
        assert result.size_bytes == len(result.bootstrap.encode())

    def test_build_bundle_with_import(self):
        from ofx.lib.bundle.builder import build_bundle

        script = "from ofx.lib import opsec\nprint(opsec)"
        result = build_bundle(script)
        assert "opsec" in result.modules

    def test_bootstrap_is_valid_python(self):
        import ast

        from ofx.lib.bundle.builder import build_bundle

        result = build_bundle("print('hello')")
        ast.parse(result.bootstrap)

    def test_bootstrap_executes_correctly(self):
        """The bootstrap must extract the zip and execute the user script."""
        from ofx.lib.bundle.builder import build_bundle

        script = "import sys; sys.stdout.write('bundle_ok')"
        result = build_bundle(script)

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            exec(
                compile(result.bootstrap, "<test_bootstrap>", "exec"),
                {"__name__": "__main__"},
            )
        finally:
            sys.stdout = old_stdout

        assert "bundle_ok" in captured.getvalue()

    def test_bundle_result_frozen(self):
        from ofx.lib.bundle.builder import build_bundle

        result = build_bundle("x = 1")
        with pytest.raises(AttributeError):
            result.script = "changed"

class TestBuildBundleGranular:
    """End-to-end file-granular bundling (acceptance cases)."""

    _B64_RE = re.compile(r"_b64\.b64decode\('([^']+)'\)")

    @staticmethod
    def _zip_bytes(bootstrap: str) -> bytes:
        match = TestBuildBundleGranular._B64_RE.search(bootstrap)
        assert match, "bootstrap should embed the base64 zip archive"
        return base64.b64decode(match.group(1))

    def _members(self, result) -> list[str]:
        with zipfile.ZipFile(io.BytesIO(self._zip_bytes(result.bootstrap))) as zf:
            return zf.namelist()

    def _extract(self, result, tmp_path: Path) -> Path:
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with zipfile.ZipFile(io.BytesIO(self._zip_bytes(result.bootstrap))) as zf:
            zf.extractall(extract_dir)
        return extract_dir

    @staticmethod
    def _run_code(extract_dir: Path, code: str) -> subprocess.CompletedProcess[str]:
        """Run *code* in a fresh subprocess with PYTHONPATH=extract_dir."""
        env = dict(os.environ)
        env["PYTHONPATH"] = str(extract_dir)
        return subprocess.run(
            [sys.executable, "-S", "-c", code],
            capture_output=True,
            text=True,
            cwd=str(extract_dir),
            env=env,
        )

    def test_split_targets_bundle_packs_only_leaf(self):
        from ofx.lib.bundle.builder import build_bundle

        result = build_bundle("from ofx.lib.recon.targets import split_targets")
        members = self._members(result)
        assert "ofx/lib/recon/targets.py" in members
        assert "ofx/lib/recon/__init__.py" in members
        assert "ofx/lib/__init__.py" in members
        assert "ofx/__init__.py" in members
        assert "ofx/lib/_compat.py" in members
        # Siblings must NOT be packed.
        for sibling in ("osint", "portscan", "web"):
            assert not any(f"/{sibling}.py" in m for m in members), sibling
        # Lazy stubs, not the eager real __init__ files.
        with zipfile.ZipFile(io.BytesIO(self._zip_bytes(result.bootstrap))) as zf:
            recon_init = zf.read("ofx/lib/recon/__init__.py").decode()
            api_init = zf.read("ofx/lib/__init__.py").decode()
        assert "__getattr__" in recon_init
        assert "__getattr__" in api_init

    def test_bare_package_bundle_packs_whole(self):
        from ofx.lib.bundle.builder import build_bundle

        result = build_bundle("import ofx.lib.recon")
        members = self._members(result)
        for sibling in ("osint", "portscan", "web", "targets"):
            assert any(f"/{sibling}.py" in m for m in members), sibling

    def test_all_import_forms_execute_from_extracted_bundle(self, tmp_path):
        """All four import forms + package-attribute form work remotely."""
        from ofx.lib.bundle.builder import build_bundle

        result = build_bundle("from ofx.lib.recon.targets import split_targets")
        extract_dir = self._extract(result, tmp_path)
        expected = (
            "{'domain': ['a.com'], 'subdomain': [], 'cidr': [], 'ip': [], "
            "'url': [], 'unknown': []}"
        )

        forms = [
            # 1: plain import of the deep module.
            (
                "import ofx.lib.recon.targets\n"
                "print(ofx.lib.recon.targets.split_targets(['a.com']))"
            ),
            # 2: from ofx.lib import <package>.
            (
                "from ofx.lib import recon\n"
                "print(recon.targets.split_targets(['a.com']))"
            ),
            # 3: from <package> import <exported name> (package-attribute form).
            (
                "from ofx.lib.recon import split_targets\n"
                "print(split_targets(['a.com']))"
            ),
            # 4: from deep module import <name>.
            (
                "from ofx.lib.recon.targets import split_targets\n"
                "print(split_targets(['a.com']))"
            ),
            # + package-attribute access after a plain package import.
            (
                "import ofx.lib.recon\n"
                "print(ofx.lib.recon.split_targets(['a.com']))"
            ),
        ]
        for code in forms:
            proc = self._run_code(extract_dir, code)
            assert proc.returncode == 0, f"form failed:\n{code}\n{proc.stderr}"
            assert proc.stdout.strip() == expected, f"form:\n{code}\n{proc.stdout}"

    def test_subprocess_uses_extracted_ofx(self, tmp_path):
        """PYTHONPATH=extract_dir must win over any installed ofx."""
        from ofx.lib.bundle.builder import build_bundle

        result = build_bundle("from ofx.lib.recon.targets import split_targets")
        extract_dir = self._extract(result, tmp_path)
        proc = self._run_code(
            extract_dir,
            "import ofx\n"
            f"assert ofx.__file__.startswith({str(extract_dir)!r}), ofx.__file__\n"
            "from ofx.lib.recon.targets import split_targets\n"
            "print('ok')",
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "ok"

    def test_transitive_dependency_bundled(self):
        """A packed module importing another ofx.lib module pulls it in."""
        from ofx.lib.bundle.builder import build_bundle

        result = build_bundle("from ofx.lib.search.fofa import Fofa")
        members = self._members(result)
        assert "ofx/lib/search/fofa.py" in members
        # fofa.py's transitive ofx.lib imports are bundled.
        assert "ofx/lib/credential_config.py" in members
        assert "ofx/lib/http/__init__.py" in members
        # Siblings not referenced stay out.
        assert "ofx/lib/search/shodan.py" not in members

    def test_obfuscated_granular_bundle_executes(self, tmp_path):
        """obfuscate_sources=True still works on a granular bundle."""
        from ofx.lib.bundle.builder import build_bundle

        script = "from ofx.lib.recon.targets import split_targets\n"
        result = build_bundle(script, obfuscate_sources=True)
        members = self._members(result)
        assert "ofx/lib/recon/targets.py" in members
        extract_dir = self._extract(result, tmp_path)
        proc = self._run_code(
            extract_dir,
            "from ofx.lib.recon.targets import split_targets\n"
            "print(split_targets(['a.com']))",
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == (
            "{'domain': ['a.com'], 'subdomain': [], 'cidr': [], 'ip': [], "
            "'url': [], 'unknown': []}"
        )

    def test_obfuscated_bundle_hides_split_targets_source(self):
        from ofx.lib.bundle.builder import build_bundle

        result = build_bundle(
            "from ofx.lib.recon.targets import split_targets",
            obfuscate_sources=True,
        )
        with zipfile.ZipFile(io.BytesIO(self._zip_bytes(result.bootstrap))) as zf:
            raw = zf.read("ofx/lib/recon/targets.py")
        assert b"def split_targets" not in raw
        assert b"marshal" in raw

class TestObfuscateBootstrap:
    def test_obfuscated_is_valid_python(self):
        import ast

        from ofx.lib.bundle.obfuscator import obfuscate_bootstrap

        loader = obfuscate_bootstrap("x = 42")
        ast.parse(loader)

    def test_obfuscated_executes_correctly(self):
        from ofx.lib.bundle.obfuscator import obfuscate_bootstrap

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
        from ofx.lib.bundle.builder import build_bundle
        from ofx.lib.bundle.obfuscator import obfuscate_bootstrap

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
        from ofx.lib.bundle.obfuscator import obfuscate_bootstrap

        key = b"\x01" * 16
        loader = obfuscate_bootstrap("x = 1", key=key)
        assert key.hex() in loader

    def test_empty_key_raises(self):
        from ofx.lib.bundle.obfuscator import obfuscate_bootstrap

        with pytest.raises(ValueError):
            obfuscate_bootstrap("x = 1", key=b"")

    def test_different_keys_produce_different_output(self):
        from ofx.lib.bundle.obfuscator import obfuscate_bootstrap

        k1, k2 = b"\xaa" * 16, b"\xbb" * 16
        l1 = obfuscate_bootstrap("x = 1", key=k1)
        l2 = obfuscate_bootstrap("x = 1", key=k2)
        assert l1 != l2

    def test_obfuscation_error_on_bad_source(self):
        from ofx.lib.bundle.obfuscator import ObfuscationError, obfuscate_bootstrap

        with pytest.raises(ObfuscationError):
            obfuscate_bootstrap("def broken(")

class TestObfuscateSources:
    def _make_files(self) -> dict[str, bytes]:
        return {
            "ofx/__init__.py": b"# stub\n",
            "ofx/lib/__init__.py": b"# stub\n",
            "ofx/lib/opsec/__init__.py": b"def hello():\n    return 'hi'\n",
            "ofx/lib/opsec/utils.py": b"X = 42\n",
        }

    def test_keys_unchanged(self):
        from ofx.lib.bundle.obfuscator import obfuscate_sources

        result = obfuscate_sources(self._make_files())
        assert set(result.keys()) == {
            "ofx/__init__.py",
            "ofx/lib/__init__.py",
            "ofx/lib/opsec/__init__.py",
            "ofx/lib/opsec/utils.py",
        }

    def test_values_are_bytes(self):
        from ofx.lib.bundle.obfuscator import obfuscate_sources

        result = obfuscate_sources(self._make_files())
        for v in result.values():
            assert isinstance(v, bytes)

    def test_source_not_present_in_output(self):
        """Raw source text must not appear in obfuscated stub bytes."""
        from ofx.lib.bundle.obfuscator import obfuscate_sources

        result = obfuscate_sources(self._make_files())
        assert b"def hello" not in result["ofx/lib/opsec/__init__.py"]
        assert b"X = 42" not in result["ofx/lib/opsec/utils.py"]

    def test_stub_contains_marshal_loader(self):
        from ofx.lib.bundle.obfuscator import obfuscate_sources

        result = obfuscate_sources(self._make_files())
        stub = result["ofx/lib/opsec/__init__.py"].decode()
        assert "marshal" in stub
        assert "fromhex" in stub

    def test_obfuscated_module_executes_correctly(self):
        """exec()-ing the stub in a fresh namespace must populate names."""
        from ofx.lib.bundle.obfuscator import obfuscate_sources

        files = {"mod.py": b"answer = 6 * 7\n"}
        result = obfuscate_sources(files)
        ns: dict = {}
        exec(compile(result["mod.py"], "mod.py", "exec"), ns)
        assert ns["answer"] == 42

    def test_non_py_files_passed_through(self):
        from ofx.lib.bundle.obfuscator import obfuscate_sources

        files = {"data.txt": b"hello", "ofx/__init__.py": b"x=1\n"}
        result = obfuscate_sources(files)
        assert result["data.txt"] == b"hello"

    def test_empty_dict_returns_empty(self):
        from ofx.lib.bundle.obfuscator import obfuscate_sources

        assert obfuscate_sources({}) == {}

    def test_syntax_error_raises_obfuscation_error(self):
        from ofx.lib.bundle.obfuscator import ObfuscationError, obfuscate_sources

        with pytest.raises(ObfuscationError, match="bad.py"):
            obfuscate_sources({"bad.py": b"def broken("})

    def test_build_bundle_obfuscate_sources_flag(self):
        """build_bundle(obfuscate_sources=True) must produce a working bootstrap."""
        from ofx.lib.bundle.builder import build_bundle

        script = "import sys; sys.stdout.write('src_obf_ok')"
        result = build_bundle(script, obfuscate_sources=True)

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            exec(
                compile(result.bootstrap, "<test_src_obf>", "exec"),
                {"__name__": "__main__"},
            )
        finally:
            sys.stdout = old_stdout

        assert "src_obf_ok" in captured.getvalue()

    def test_xor_produces_different_output_each_run(self):
        """Each call uses a random key, so identical input → different stubs."""
        from ofx.lib.bundle.obfuscator import obfuscate_sources

        files = {"mod.py": b"x = 1\n"}
        r1 = obfuscate_sources(files)
        r2 = obfuscate_sources(files)
        assert r1["mod.py"] != r2["mod.py"]

    def test_stub_contains_xor_decryption(self):
        """Stub must contain both a key hex and encrypted data hex."""
        from ofx.lib.bundle.obfuscator import obfuscate_sources

        result = obfuscate_sources({"mod.py": b"x = 1\n"})
        stub = result["mod.py"].decode()
        assert stub.count("fromhex") == 2

    def test_metadata_stripped_filename(self):
        """co_filename in the bytecode must not contain the original path."""
        from ofx.lib.bundle.obfuscator import _strip_code

        code = compile(b"x = 1", "secret/path/mod.py", "exec")
        stripped = _strip_code(code)
        assert "secret" not in stripped.co_filename
        assert stripped.co_filename == "<module>"

    def test_metadata_stripped_docstrings(self):
        """Module and function docstrings must be removed."""
        from ofx.lib.bundle.obfuscator import _strip_code

        src = b'"""Module doc."""\ndef foo():\n    """Func doc."""\n    return 1\n'
        code = compile(src, "mod.py", "exec")
        stripped = _strip_code(code)
        assert stripped.co_consts[0] is None
        func_code = [c for c in stripped.co_consts if hasattr(c, "co_code")][0]
        assert func_code.co_consts[0] is None

class TestUploadAdapter:
    def _make_runner(self, upload_side_effect=None, run_return="ok"):
        runner = MagicMock()
        runner.upload.side_effect = upload_side_effect
        runner.run.return_value = run_return
        return runner

    def test_deliver_calls_upload_and_run(self):
        from ofx.lib.bundle.deliverer import UploadAdapter

        runner = self._make_runner()
        adapter = UploadAdapter(runner, remote_tmp="/tmp/t.py")
        result = adapter.deliver("print('hi')")

        runner.upload.assert_called_once()
        assert runner.run.call_count == 2
        assert result == "ok"

    def test_deliver_uses_python3_by_default(self):
        from ofx.lib.bundle.deliverer import UploadAdapter

        runner = self._make_runner()
        adapter = UploadAdapter(runner, remote_tmp="/tmp/t.py")
        adapter.deliver("x = 1")

        exec_call = runner.run.call_args_list[0]
        assert "python3 /tmp/t.py" in exec_call[0][0]

    def test_windows_mode_uses_python_and_del(self):
        from ofx.lib.bundle.deliverer import UploadAdapter

        runner = self._make_runner()
        adapter = UploadAdapter(runner, remote_tmp="C:\\Temp\\t.py", windows=True)
        adapter.deliver("x = 1")

        exec_call = runner.run.call_args_list[0][0][0]
        cleanup_call = runner.run.call_args_list[1][0][0]
        assert "python C:\\Temp\\t.py" in exec_call
        assert "del /f /q" in cleanup_call

    def test_custom_python_name(self):
        from ofx.lib.bundle.deliverer import UploadAdapter

        runner = self._make_runner()
        adapter = UploadAdapter(runner, python="python3.11", remote_tmp="/tmp/t.py")
        adapter.deliver("x = 1")
        assert "python3.11 /tmp/t.py" in runner.run.call_args_list[0][0][0]

    def test_upload_failure_propagates(self):
        from ofx.lib.bundle.deliverer import UploadAdapter

        runner = self._make_runner(upload_side_effect=RuntimeError("conn fail"))
        adapter = UploadAdapter(runner, remote_tmp="/tmp/t.py")
        with pytest.raises(RuntimeError, match="conn fail"):
            adapter.deliver("x = 1")

    def test_upload_adapter_removes_local_temp_file_on_upload_failure(self):
        from ofx.lib.bundle.deliverer import UploadAdapter

        captured: dict[str, str] = {}

        def _upload(local_path, _remote_path):
            captured["local_path"] = local_path
            raise RuntimeError("conn fail")

        runner = MagicMock()
        runner.upload.side_effect = _upload
        adapter = UploadAdapter(runner, remote_tmp="/tmp/t.py")

        with pytest.raises(RuntimeError, match="conn fail"):
            adapter.deliver("x = 1")

        assert captured["local_path"]
        assert not Path(captured["local_path"]).exists()

class TestInlineAdapter:
    def test_deliver_runs_base64_python_command(self):
        from ofx.lib.bundle.deliverer import InlineAdapter

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
        from ofx.lib.bundle.deliverer import InlineAdapter

        runner = MagicMock()
        runner.run.return_value = "ok"
        adapter = InlineAdapter(runner, windows=True)
        adapter.deliver("x = 1")

        cmd = runner.run.call_args[0][0]
        assert cmd.startswith("python -c")

class TestMakeAdapter:
    def test_upload_method_returns_upload_adapter(self):
        from ofx.lib.bundle.deliverer import UploadAdapter, make_adapter

        runner = MagicMock()
        adapter = make_adapter(runner, "upload")
        assert isinstance(adapter, UploadAdapter)

    def test_http_method_returns_http_adapter(self):
        from ofx.lib.bundle.deliverer import HttpAdapter, make_adapter

        runner = MagicMock()
        adapter = make_adapter(runner, "http")
        assert isinstance(adapter, HttpAdapter)

    def test_inline_method_returns_inline_adapter(self):
        from ofx.lib.bundle.deliverer import InlineAdapter, make_adapter

        runner = MagicMock()
        adapter = make_adapter(runner, "inline")
        assert isinstance(adapter, InlineAdapter)

    def test_unknown_method_raises(self):
        from ofx.lib.bundle.deliverer import make_adapter

        with pytest.raises(ValueError, match="Unknown delivery method"):
            make_adapter(MagicMock(), "ftp")

    def test_auto_with_upload_runner(self):
        """auto should pick UploadAdapter when runner has real upload()."""
        from ofx.lib.bundle.deliverer import UploadAdapter, make_adapter

        runner = MagicMock()
        adapter = make_adapter(runner, "auto")
        assert isinstance(adapter, UploadAdapter)

    def test_windows_flag_propagated(self):
        from ofx.lib.bundle.deliverer import UploadAdapter, make_adapter

        runner = MagicMock()
        adapter = make_adapter(runner, "upload", windows=True)
        assert isinstance(adapter, UploadAdapter)
        assert adapter.windows is True
        assert adapter.python == "python"

class TestCustomAdapter:
    def test_custom_adapter_used_directly(self):
        from ofx.lib.bundle.deliverer import deliver_and_run

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
        runner.upload.assert_not_called()
        runner.run.assert_not_called()

    def test_custom_adapter_satisfies_protocol(self):
        from ofx.lib.bundle.deliverer import BundleAdapter

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
        from ofx.lib.bundle.deliverer import deliver_and_run

        runner = self._make_runner()
        result = deliver_and_run(
            runner, "print('hi')", method="upload", remote_tmp="/tmp/t.py"
        )

        runner.upload.assert_called_once()
        assert runner.run.call_count == 2
        assert result == "ok"

    def test_upload_failure_raises_delivery_error(self):
        from ofx.lib.bundle.deliverer import DeliveryError, deliver_and_run

        runner = self._make_runner(upload_side_effect=RuntimeError("conn failed"))
        with pytest.raises(DeliveryError, match="Delivery failed"):
            deliver_and_run(runner, "x = 1", method="upload")

    def test_unknown_method_raises_value_error(self):
        from ofx.lib.bundle.deliverer import deliver_and_run

        runner = self._make_runner()
        with pytest.raises(ValueError, match="Unknown delivery method"):
            deliver_and_run(runner, "x = 1", method="ftp")

    def test_adapter_kwarg_overrides_method(self):
        """When adapter= is given, method= is ignored."""
        from ofx.lib.bundle.deliverer import deliver_and_run

        class StubAdapter:
            def deliver(self, bootstrap: str) -> str:
                return "stub"

        runner = self._make_runner()
        result = deliver_and_run(runner, "x=1", adapter=StubAdapter(), method="upload")
        assert result == "stub"
        runner.upload.assert_not_called()

class TestRunRemote:
    def test_run_remote_upload_no_obfuscation(self):
        from ofx.lib.bundle import run_remote

        runner = MagicMock()
        runner.run.return_value = "done"

        result = run_remote("x = 1", runner, obfuscate=False, method="upload")

        runner.upload.assert_called_once()
        assert result == "done"

    def test_run_remote_with_obfuscation(self):
        from ofx.lib.bundle import run_remote

        runner = MagicMock()
        runner.run.return_value = "done_obf"

        result = run_remote("x = 1", runner, obfuscate=True, method="upload")

        runner.upload.assert_called_once()
        assert result == "done_obf"

    def test_run_remote_with_custom_adapter(self):
        from ofx.lib.bundle import run_remote

        class MyAdapter:
            def deliver(self, bootstrap: str) -> str:
                return "custom_done"

        runner = MagicMock()
        result = run_remote("x = 1", runner, adapter=MyAdapter(), obfuscate=False)
        assert result == "custom_done"
        runner.upload.assert_not_called()

    def test_run_remote_windows_mode(self):
        from ofx.lib.bundle import run_remote

        runner = MagicMock()
        runner.run.return_value = "win_ok"

        result = run_remote(
            "x = 1", runner, obfuscate=False, method="upload", windows=True
        )

        exec_cmd = runner.run.call_args_list[0][0][0]
        assert "python " in exec_cmd
        assert result == "win_ok"
