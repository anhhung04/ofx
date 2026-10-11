"""Tests for namespaced module references (parsing, resolution, CLI).

Covers the design contract: the module spec forms table, registry
equivalence, remote GitHub resolution with a monkeypatched git layer (no
real network), manifest errors, cache-hit-no-reclone, and the
``ofx flow modules`` CLI subcommands.
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest
import yaml
from conftest import _FakeGitRepo, _install_fake_clone
from rich.console import Console
from typer.testing import CliRunner

from ofx.cloud.script_runtime import (
    build_udf_step_source,
    is_udf_module_step,
)
from ofx.models.step import Step
from ofx.modules import ModuleRegistry
from ofx.modules.refs import (
    BUILTIN_KIND,
    LOCAL_FILE_KIND,
    LOCAL_NAMED_KIND,
    REMOTE_KIND,
    parse_module_ref,
)
from ofx.modules.remote import (
    MANIFEST_FILENAME,
    ManifestError,
    cache_dir_for,
)

MANIFEST = """\
name: ofx-modules
version: 1.0.0
modules:
  parse_nmap:
    description: Parse nmap XML
    entry: modules/parse_nmap.py
  kerberoast:
    description: Kerberoast
"""

MODULE_BODY = """\
def run(ctx):
    return {"ok": True}

def analyze(ctx):
    return {"analyzed": True}
"""


_KERBEROAST_BODY = "def run(ctx):\n    return {'krb': True}\n"

_REPO_MODULES = {
    "parse_nmap.py": MODULE_BODY,
    "kerberoast.py": _KERBEROAST_BODY,
}


def _write_repo(target: Path, manifest: str = MANIFEST) -> Path:
    """Create a fake cloned repo layout (manifest + modules)."""
    target.mkdir(parents=True, exist_ok=True)
    (target / MANIFEST_FILENAME).write_text(manifest)
    modules_dir = target / "modules"
    modules_dir.mkdir(exist_ok=True)
    for name, source in _REPO_MODULES.items():
        (modules_dir / name).write_text(source)
    return target


def _install_fake_git(monkeypatch, *, fail_clone: bool = False, clone_hook=None):
    """Patch ``ofx.modules.remote.git`` with a no-network clone layer.

    Thin wrapper over the shared ``_install_fake_clone`` helper that supplies
    the standard fake repo layout (manifest + ``modules/`` files). Returns
    ``(clone_calls, checkout_calls)`` lists for assertions.
    """
    return _install_fake_clone(
        monkeypatch,
        MANIFEST,
        modules=_REPO_MODULES,
        fail_clone=fail_clone,
        clone_hook=clone_hook,
    )


def _use_modules_dir(monkeypatch, tmp_path: Path) -> Path:
    modules_dir = tmp_path / "modules"
    monkeypatch.setattr("ofx.modules.remote.MODULES_DIR", modules_dir)
    return modules_dir


@pytest.fixture
def modules_dir(monkeypatch, tmp_path: Path) -> Path:
    return _use_modules_dir(monkeypatch, tmp_path)


class TestParseModuleRef:
    """Every spec form in the design table + malformed specs."""

    def test_builtin_forms(self):
        for spec in ("shell", "builtin.shell", "local.builtin.shell"):
            ref = parse_module_ref(spec)
            assert ref.kind == BUILTIN_KIND
            assert ref.name == "shell"
        ref = parse_module_ref("python")
        assert ref.kind == BUILTIN_KIND
        assert ref.name == "python"
        assert ref.function is None

    def test_local_file_forms(self):
        ref = parse_module_ref("mod.py")
        assert ref.kind == LOCAL_FILE_KIND
        assert ref.file == "mod.py"
        assert ref.function is None

        ref = parse_module_ref("path/to/mod.py::helper")
        assert ref.kind == LOCAL_FILE_KIND
        assert ref.file == "path/to/mod.py"
        assert ref.function == "helper"

    def test_local_named_forms(self):
        ref = parse_module_ref("local.scan")
        assert ref.kind == LOCAL_NAMED_KIND
        assert ref.name == "scan"
        assert ref.function is None

        ref = parse_module_ref("local.scan::run")
        assert ref.kind == LOCAL_NAMED_KIND
        assert ref.name == "scan"
        assert ref.function == "run"

    def test_remote_forms(self):
        ref = parse_module_ref("anhhung04.ofx-modules.parse_nmap")
        assert ref.kind == REMOTE_KIND
        assert ref.owner == "anhhung04"
        assert ref.repo == "ofx-modules"
        assert ref.module == "parse_nmap"
        assert ref.ref is None
        assert ref.function is None

        ref = parse_module_ref("anhhung04.ofx-modules.parse_nmap@v1.2.0")
        assert ref.ref == "v1.2.0"

        ref = parse_module_ref("anhhung04.ofx-modules.parse_nmap@v1.2.0::analyze")
        assert ref.ref == "v1.2.0"
        assert ref.function == "analyze"

        ref = parse_module_ref("a.b.c.d::f")
        assert ref.owner == "a"
        assert ref.repo == "b"
        assert ref.module == "c.d"
        assert ref.function == "f"

    def test_remote_display_label(self):
        ref = parse_module_ref("anhhung04.ofx-modules.parse_nmap@v1.2.0::analyze")
        assert ref.display == "anhhung04.ofx-modules.parse_nmap@v1.2.0::analyze"

    def test_empty_spec(self):
        for spec in ("", "   "):
            with pytest.raises(ValueError, match="cannot be empty"):
                parse_module_ref(spec)

    def test_two_segment_spec_unknown(self):
        with pytest.raises(ValueError, match="Unknown module reference"):
            parse_module_ref("a.b")

    def test_at_without_ref(self):
        with pytest.raises(ValueError, match="missing ref after '@'"):
            parse_module_ref("owner.repo.mod@")

    def test_double_at(self):
        with pytest.raises(ValueError, match="at most once"):
            parse_module_ref("owner.repo.mod@v1@v2")

    def test_double_colon(self):
        with pytest.raises(ValueError, match="at most once"):
            parse_module_ref("mod.py::a::b")

    def test_colon_without_function(self):
        with pytest.raises(ValueError, match="missing function after '::'"):
            parse_module_ref("mod.py::")

    def test_empty_segments(self):
        for spec in ("a..c", "a.b.", ".a.b", "..a.b"):
            with pytest.raises(ValueError, match="Unknown module reference"):
                parse_module_ref(spec)

    def test_local_builtin_missing_name(self):
        with pytest.raises(ValueError, match="missing builtin name"):
            parse_module_ref("local.builtin.")

    def test_local_missing_name(self):
        with pytest.raises(ValueError, match="missing name after 'local.'"):
            parse_module_ref("local.")

    def test_local_nested_unknown(self):
        with pytest.raises(ValueError, match="Unknown module reference"):
            parse_module_ref("local.a.b")

    def test_ref_on_non_remote_rejected(self):
        with pytest.raises(ValueError, match="'@<ref>' is only valid on remote"):
            parse_module_ref("shell@v1")
        with pytest.raises(ValueError, match="'@<ref>' is only valid on remote"):
            parse_module_ref("mod.py@v1")
        with pytest.raises(ValueError, match="'@<ref>' is only valid on remote"):
            parse_module_ref("local.scan@v1")

    def test_function_on_builtin_rejected(self):
        with pytest.raises(ValueError, match="do not take"):
            parse_module_ref("shell::run")


class TestParseRemoteRepo:
    def test_valid(self):
        ref = parse_module_ref("a.b.c")  # sanity: remote module ref
        from ofx.modules.refs import parse_remote_repo

        ref = parse_remote_repo("anhhung04.ofx-modules@v1.2.0")
        assert ref.kind == REMOTE_KIND
        assert ref.owner == "anhhung04"
        assert ref.repo == "ofx-modules"
        assert ref.ref == "v1.2.0"
        assert ref.module == ""

        ref = parse_remote_repo("anhhung04.ofx-modules")
        assert ref.ref is None

    def test_invalid(self):
        from ofx.modules.refs import parse_remote_repo

        for spec in ("", "a", "a.b.c", "a..b"):
            with pytest.raises(ValueError, match="Invalid module repo"):
                parse_remote_repo(spec)


class TestRegistryBuiltinEquivalence:
    def test_all_builtin_forms_equivalent(self):
        registry = ModuleRegistry()
        for spec in ("shell", "builtin.shell", "local.builtin.shell"):
            resolved = registry.resolve(spec)
            assert resolved.kind == "builtin"
            assert resolved.name == "shell"
        for spec in ("python", "builtin.python", "local.builtin.python"):
            resolved = registry.resolve(spec)
            assert resolved.kind == "builtin"
            assert resolved.name == "python"

    def test_unknown_bare_name_lists_builtins_and_hint(self):
        with pytest.raises(ValueError, match="Unknown module: 'nope'"):
            ModuleRegistry().resolve("nope")
        with pytest.raises(ValueError, match="shell"):
            ModuleRegistry().resolve("nope")
        with pytest.raises(ValueError, match="<owner>.<repo>.<module>"):
            ModuleRegistry().resolve("nope")

    def test_unknown_dotted_form_lists_builtins_and_hint(self):
        with pytest.raises(ValueError, match="Available builtin modules"):
            ModuleRegistry().resolve("a.b")
        with pytest.raises(ValueError, match="<owner>.<repo>.<module>"):
            ModuleRegistry().resolve("a.b")


class TestRegistryLocalNamed:
    def test_local_named_resolves_modules_dir(self, tmp_path: Path):
        modules = tmp_path / "modules"
        modules.mkdir()
        (modules / "scan.py").write_text(MODULE_BODY)
        registry = ModuleRegistry(workflow_dir=tmp_path)
        spec = registry.resolve("local.scan")
        assert spec.kind == "udf"
        assert spec.file == modules / "scan.py"
        assert spec.function == "run"
        assert spec.callable is not None

    def test_local_named_explicit_function(self, tmp_path: Path):
        modules = tmp_path / "modules"
        modules.mkdir()
        (modules / "scan.py").write_text(MODULE_BODY)
        spec = ModuleRegistry(workflow_dir=tmp_path).resolve("local.scan::analyze")
        assert spec.function == "analyze"

    def test_local_named_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="local.ghost"):
            ModuleRegistry(workflow_dir=tmp_path).resolve("local.ghost")

    def test_local_named_uses_workflow_dir_arg(self, tmp_path: Path):
        modules = tmp_path / "modules"
        modules.mkdir()
        (modules / "scan.py").write_text(MODULE_BODY)
        spec = ModuleRegistry().resolve("local.scan", workflow_dir=tmp_path)
        assert spec.file == modules / "scan.py"


class TestRemoteResolution:
    def test_remote_resolves_entry_file(self, monkeypatch, tmp_path: Path, modules_dir: Path):
        clone_calls, _checkouts = _install_fake_git(monkeypatch)
        spec = ModuleRegistry().resolve("anhhung04.ofx-modules.parse_nmap")
        assert spec.kind == "udf"
        assert spec.function == "run"
        assert spec.name == "anhhung04.ofx-modules.parse_nmap"
        assert spec.file == (
            modules_dir / "anhhung04" / "ofx-modules" / "modules" / "parse_nmap.py"
        )
        assert spec.callable is not None
        assert clone_calls[0][0] == "https://github.com/anhhung04/ofx-modules"
        assert clone_calls[0][1] == str(modules_dir / "anhhung04" / "ofx-modules")

    def test_remote_pinned_ref_checkout_and_dir(self, monkeypatch, tmp_path: Path, modules_dir: Path):
        _clone_calls, checkouts = _install_fake_git(monkeypatch)
        spec = ModuleRegistry().resolve(
            "anhhung04.ofx-modules.parse_nmap@v1.2.0::analyze"
        )
        assert spec.function == "analyze"
        assert spec.file == (
            modules_dir / "anhhung04" / "ofx-modules@v1.2.0" / "modules" / "parse_nmap.py"
        )
        assert checkouts == ["v1.2.0"]

    def test_remote_manifest_function_fallback(self, monkeypatch, tmp_path: Path, modules_dir: Path):
        manifest = """\
name: ofx-modules
modules:
  parse_nmap:
    entry: modules/parse_nmap.py
    function: analyze
"""
        clone_calls, _checkouts = _install_fake_git(monkeypatch)
        monkeypatch.setattr(
            "ofx.modules.remote._load_manifest",
            lambda ref, repo_dir: yaml.safe_load(manifest),
        )
        spec = ModuleRegistry().resolve("anhhung04.ofx-modules.parse_nmap")
        assert spec.function == "analyze"

    def test_cache_hit_no_reclone(self, monkeypatch, tmp_path: Path, modules_dir: Path):
        clone_calls, _checkouts = _install_fake_git(monkeypatch)
        registry = ModuleRegistry()
        registry.resolve("anhhung04.ofx-modules.parse_nmap")
        registry.resolve("anhhung04.ofx-modules.parse_nmap")
        assert len(clone_calls) == 1

    def test_cache_dir_pinned_vs_unpinned(self, modules_dir: Path):
        unpinned = parse_module_ref("a.b.mod")
        pinned = parse_module_ref("a.b.mod@v1.2.0")
        assert cache_dir_for(unpinned) == modules_dir / "a" / "b"
        assert cache_dir_for(pinned) == modules_dir / "a" / "b@v1.2.0"

    def test_missing_manifest_raises_manifest_error(self, monkeypatch, tmp_path: Path, modules_dir: Path):
        def no_manifest_clone(url, target, multi_options=None):
            Path(target).mkdir(parents=True, exist_ok=True)
            return _FakeGitRepo()

        fake_git = types.SimpleNamespace(
            Repo=types.SimpleNamespace(clone_from=no_manifest_clone)
        )
        monkeypatch.setattr("ofx.modules.remote.git", fake_git)
        with pytest.raises(ManifestError, match="ofx-modules.yml"):
            ModuleRegistry().resolve("anhhung04.ofx-modules.parse_nmap")

    def test_invalid_manifest_yaml_raises_manifest_error(self, monkeypatch, tmp_path: Path, modules_dir: Path):
        def bad_manifest_clone(url, target, multi_options=None):
            target_path = Path(target)
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / MANIFEST_FILENAME).write_text("::: not yaml")
            return _FakeGitRepo()

        fake_git = types.SimpleNamespace(
            Repo=types.SimpleNamespace(clone_from=bad_manifest_clone)
        )
        monkeypatch.setattr("ofx.modules.remote.git", fake_git)
        with pytest.raises(ManifestError, match="Invalid"):
            ModuleRegistry().resolve("anhhung04.ofx-modules.parse_nmap")

    def test_missing_module_in_manifest(self, monkeypatch, tmp_path: Path, modules_dir: Path):
        manifest = "name: ofx-modules\nmodules:\n  other:\n"
        _clone_calls, _checkouts = _install_fake_git(monkeypatch)
        monkeypatch.setattr(
            "ofx.modules.remote._load_manifest",
            lambda ref, repo_dir: yaml.safe_load(manifest),
        )
        with pytest.raises(ValueError) as excinfo:
            ModuleRegistry().resolve("anhhung04.ofx-modules.parse_nmap")
        message = str(excinfo.value)
        assert "parse_nmap" in message
        assert "https://github.com/anhhung04/ofx-modules" in message
        assert "other" in message

    def test_clone_failure_names_url(self, monkeypatch, tmp_path: Path, modules_dir: Path):
        from git.exc import GitCommandError

        def failing_clone(url, target, multi_options=None):
            raise GitCommandError("clone", "boom")

        fake_git = types.SimpleNamespace(
            Repo=types.SimpleNamespace(clone_from=failing_clone)
        )
        monkeypatch.setattr("ofx.modules.remote.git", fake_git)
        with pytest.raises(ValueError, match="anhhung04.ofx-modules.parse_nmap"):
            ModuleRegistry().resolve("anhhung04.ofx-modules.parse_nmap")
        with pytest.raises(ValueError, match="https://github.com/anhhung04/ofx-modules"):
            ModuleRegistry().resolve("anhhung04.ofx-modules.parse_nmap")


class TestCloudStreamingIntegration:
    """Remote refs are UDF-like for cloud/session source bundling."""

    def test_is_udf_module_step_remote(self):
        assert is_udf_module_step(
            Step(module="anhhung04.ofx-modules.parse_nmap", run_with={})
        )
        assert is_udf_module_step(
            Step(module="anhhung04.ofx-modules.parse_nmap@v1.0.0::analyze", run_with={})
        )
        assert not is_udf_module_step(
            Step(module="local.builtin.shell", run_with={"cmd": "x"})
        )
        assert is_udf_module_step(
            Step(module="local.scan::run", run_with={})
        )

    def test_build_udf_step_source_remote(self, monkeypatch, tmp_path: Path, modules_dir: Path):
        clone_calls, _checkouts = _install_fake_git(monkeypatch)
        step = Step(module="anhhung04.ofx-modules.parse_nmap", run_with={})
        wrapper = build_udf_step_source(
            step,
            workflow_dir=tmp_path,
            inputs={},
            secrets={},
        )
        assert "def run(ctx):" in wrapper
        assert "_UDF_FUNCTION = 'run'" in wrapper
        assert len(clone_calls) == 1


class TestFlowModulesCli:
    def test_list_shows_builtins(self, monkeypatch, modules_dir: Path):
        from ofx.commands.flow.modules import app

        console = Console(record=True, width=120)
        monkeypatch.setattr("ofx.commands.flow.modules.MODULES_DIR", modules_dir)
        monkeypatch.setattr("ofx.commands.flow.modules.get_console", lambda: console)

        result = CliRunner().invoke(app, ["list"])
        assert result.exit_code == 0
        output = console.export_text()
        assert "shell" in output
        assert "python" in output

    def test_list_shows_cached_remotes_and_local(self, monkeypatch, tmp_path: Path, modules_dir: Path):
        from ofx.commands.flow.modules import app

        console = Console(record=True, width=120)
        monkeypatch.setattr("ofx.commands.flow.modules.MODULES_DIR", modules_dir)
        monkeypatch.setattr("ofx.commands.flow.modules.get_console", lambda: console)
        _write_repo(modules_dir / "anhhung04" / "ofx-modules")
        (modules_dir / "local_mod.py").write_text("def run(ctx):\n    pass\n")
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(app, ["list"])
        assert result.exit_code == 0
        output = console.export_text()
        assert "anhhung04.ofx-modules" in output
        assert "local_mod" in output

    def test_add_preclones(self, monkeypatch, tmp_path: Path, modules_dir: Path):
        from ofx.commands.flow.modules import app

        console = Console(record=True, width=120)
        monkeypatch.setattr("ofx.commands.flow.modules.MODULES_DIR", modules_dir)
        monkeypatch.setattr("ofx.commands.flow.modules.get_console", lambda: console)
        clone_calls, _checkouts = _install_fake_git(monkeypatch)

        result = CliRunner().invoke(app, ["add", "anhhung04.ofx-modules@v1.2.0"])
        assert result.exit_code == 0
        assert clone_calls[0][0] == "https://github.com/anhhung04/ofx-modules"
        assert clone_calls[0][1] == str(modules_dir / "anhhung04" / "ofx-modules@v1.2.0")
        assert (modules_dir / "anhhung04" / "ofx-modules@v1.2.0").is_dir()

    def test_add_rejects_missing_manifest(self, monkeypatch, tmp_path: Path, modules_dir: Path):
        from ofx.commands.flow.modules import app

        console = Console(record=True, width=120)
        monkeypatch.setattr("ofx.commands.flow.modules.MODULES_DIR", modules_dir)
        monkeypatch.setattr("ofx.commands.flow.modules.get_console", lambda: console)

        def no_manifest_clone(url, target, multi_options=None):
            Path(target).mkdir(parents=True, exist_ok=True)
            return _FakeGitRepo()

        fake_git = types.SimpleNamespace(
            Repo=types.SimpleNamespace(clone_from=no_manifest_clone)
        )
        monkeypatch.setattr("ofx.modules.remote.git", fake_git)

        result = CliRunner().invoke(app, ["add", "anhhung04.ofx-modules"])
        assert result.exit_code != 0
        assert not (modules_dir / "anhhung04" / "ofx-modules").exists()

    def test_remove_deletes_cache_dir(self, monkeypatch, tmp_path: Path, modules_dir: Path):
        from ofx.commands.flow.modules import app

        console = Console(record=True, width=120)
        monkeypatch.setattr("ofx.commands.flow.modules.MODULES_DIR", modules_dir)
        monkeypatch.setattr("ofx.commands.flow.modules.get_console", lambda: console)
        target = _write_repo(modules_dir / "anhhung04" / "ofx-modules@v1.2.0")

        result = CliRunner().invoke(app, ["remove", "anhhung04.ofx-modules@v1.2.0"])
        assert result.exit_code == 0
        assert not target.exists()

    def test_remove_missing_is_nonzero(self, monkeypatch, tmp_path: Path, modules_dir: Path):
        from ofx.commands.flow.modules import app

        console = Console(record=True, width=120)
        monkeypatch.setattr("ofx.commands.flow.modules.MODULES_DIR", modules_dir)
        monkeypatch.setattr("ofx.commands.flow.modules.get_console", lambda: console)

        result = CliRunner().invoke(app, ["remove", "anhhung04.ofx-modules"])
        assert result.exit_code != 0

    def test_update_pulls_unpinned_clones(self, monkeypatch, tmp_path: Path, modules_dir: Path):
        from ofx.commands.flow.modules import app

        console = Console(record=True, width=120)
        monkeypatch.setattr("ofx.commands.flow.modules.MODULES_DIR", modules_dir)
        monkeypatch.setattr("ofx.commands.flow.modules.get_console", lambda: console)

        pulled: list[str] = []

        class FakeRemote:
            def pull(self):
                pulled.append("pull")

        class FakeOrigin:
            remote = FakeRemote()
            origin = remote

        class FakeRepo:
            def __init__(self, path):
                self.remotes = types.SimpleNamespace(origin=FakeRemote())

        _write_repo(modules_dir / "anhhung04" / "ofx-modules")
        _write_repo(modules_dir / "anhhung04" / "ofx-modules@v1.2.0")
        monkeypatch.setattr("ofx.modules.remote.git", types.SimpleNamespace(Repo=FakeRepo))

        result = CliRunner().invoke(app, ["update"])
        assert result.exit_code == 0
        assert pulled == ["pull"]

    def test_update_pinned_rejected(self, monkeypatch, tmp_path: Path, modules_dir: Path):
        from ofx.commands.flow.modules import app

        console = Console(record=True, width=120)
        monkeypatch.setattr("ofx.commands.flow.modules.MODULES_DIR", modules_dir)
        monkeypatch.setattr("ofx.commands.flow.modules.get_console", lambda: console)

        result = CliRunner().invoke(app, ["update", "anhhung04.ofx-modules@v1.2.0"])
        assert result.exit_code != 0
        assert "immutable" in result.output
