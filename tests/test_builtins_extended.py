"""Tests for the pure-Python builtin modules.

Covers ``merge_lists``, ``normalize_targets`` and ``classify_targets``: their
``fail_if`` modes, file-vs-literal handling, published outputs, and the
``ModuleRunner`` dispatch that routes them through the ``ModuleContext`` path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ofx.modules import ModuleInvocation, ModuleRegistry, ModuleRunner
from ofx.modules.base import ModuleContext
from ofx.runner import RunContext, RunnerStatus
from ofx.runner.registry_keys import RunnerRegistryKeys


class _Outputs:
    """Collect ``ctx.add_outputs`` calls."""

    def __init__(self) -> None:
        self.values: dict = {}

    def add(self, **kwargs) -> None:
        self.values.update(kwargs)


def _ctx(
    run_dir: Path,
    *,
    args: dict | None = None,
    inputs: dict | None = None,
    outputs: _Outputs | None = None,
) -> ModuleContext:
    collector = outputs or _Outputs()
    return ModuleContext(
        args=dict(args or {}),
        inputs=dict(inputs or {}),
        env={"OFX_RUN_DIR": str(run_dir)},
        working_directory=run_dir,
        add_outputs=collector.add,
    )


def _lines(path: Path) -> list[str]:
    return path.read_text().splitlines()


class TestMergeListsRegistration:
    def test_resolves_under_every_builtin_prefix(self):
        registry = ModuleRegistry()
        for spec in ("merge_lists", "builtin.merge_lists", "local.builtin.merge_lists"):
            resolved = registry.resolve(spec)
            assert resolved.kind == "builtin"
            assert resolved.name == "merge_lists"
            assert resolved.callable is not None


class TestMergeLists:
    def test_merges_and_dedupes_sorted(self, tmp_path):
        from ofx.modules.builtins import merge

        (tmp_path / "a.txt").write_text("b.example\na.example\n\n")
        (tmp_path / "b.txt").write_text("c.example\na.example\n")
        outputs = _Outputs()

        merge.run(
            _ctx(
                tmp_path,
                args={"files": ["a.txt", "b.txt"], "output": "all.txt"},
                outputs=outputs,
            )
        )

        out = tmp_path / "all.txt"
        assert _lines(out) == ["a.example", "b.example", "c.example"]
        assert outputs.values == {"output_file": str(out), "count": 3}

    def test_comma_separated_files_and_first_seen_order(self, tmp_path):
        from ofx.modules.builtins import merge

        (tmp_path / "z.txt").write_text("z\nb\n")
        (tmp_path / "a.txt").write_text("b\na\n")
        outputs = _Outputs()

        merge.run(
            _ctx(
                tmp_path,
                args={
                    "files": "z.txt, a.txt",
                    "output": "all.txt",
                    "sort": False,
                },
                outputs=outputs,
            )
        )

        assert _lines(tmp_path / "all.txt") == ["z", "b", "a"]
        assert outputs.values["count"] == 3

    def test_absolute_paths_and_output_dir_override(self, tmp_path):
        from ofx.modules.builtins import merge

        run_dir = tmp_path / "run"
        artifacts = tmp_path / "artifacts"
        run_dir.mkdir()
        artifacts.mkdir()
        (artifacts / "a.txt").write_text("one\n")
        outputs = _Outputs()

        merge.run(
            _ctx(
                run_dir,
                args={
                    "files": [str(artifacts / "a.txt")],
                    "output": "out/merged.txt",
                    "output_dir": str(artifacts),
                },
                outputs=outputs,
            )
        )

        out = artifacts / "out" / "merged.txt"
        assert _lines(out) == ["one"]
        assert outputs.values == {"output_file": str(out), "count": 1}

    def test_fail_if_all_missing_default(self, tmp_path):
        from ofx.modules.builtins import merge

        with pytest.raises(RuntimeError, match="no merge inputs available"):
            merge.run(
                _ctx(
                    tmp_path,
                    args={"files": ["a.txt", "b.txt"], "output": "all.txt"},
                )
            )

    def test_partial_results_are_kept(self, tmp_path):
        from ofx.modules.builtins import merge

        (tmp_path / "a.txt").write_text("kept\n")
        outputs = _Outputs()

        merge.run(
            _ctx(
                tmp_path,
                args={"files": ["a.txt", "missing.txt"], "output": "all.txt"},
                outputs=outputs,
            )
        )

        assert _lines(tmp_path / "all.txt") == ["kept"]
        assert outputs.values["count"] == 1

    def test_fail_if_any_missing(self, tmp_path):
        from ofx.modules.builtins import merge

        (tmp_path / "a.txt").write_text("kept\n")
        with pytest.raises(RuntimeError, match="missing.txt.*fail_if=any_missing"):
            merge.run(
                _ctx(
                    tmp_path,
                    args={
                        "files": ["a.txt", "missing.txt"],
                        "output": "all.txt",
                        "fail_if": "any_missing",
                    },
                )
            )

    def test_fail_if_never_writes_empty_file(self, tmp_path):
        from ofx.modules.builtins import merge

        outputs = _Outputs()
        merge.run(
            _ctx(
                tmp_path,
                args={
                    "files": ["a.txt"],
                    "output": "all.txt",
                    "fail_if": "never",
                },
                outputs=outputs,
            )
        )

        assert _lines(tmp_path / "all.txt") == []
        assert outputs.values["count"] == 0

    def test_required_file_missing_raises_even_when_optional_present(self, tmp_path):
        from ofx.modules.builtins import merge

        (tmp_path / "optional.txt").write_text("katana\n")
        with pytest.raises(
            RuntimeError, match="required merge input\\(s\\) missing: subjs.txt"
        ):
            merge.run(
                _ctx(
                    tmp_path,
                    args={
                        "files": ["subjs.txt", "optional.txt"],
                        "required": ["subjs.txt"],
                        "output": "js.txt",
                    },
                )
            )

    def test_required_file_missing_skips_absent_optional(self, tmp_path):
        from ofx.modules.builtins import merge

        (tmp_path / "subjs.txt").write_text("app.js\n")
        outputs = _Outputs()

        merge.run(
            _ctx(
                tmp_path,
                args={
                    "files": ["subjs.txt", "katana.txt"],
                    "required": ["subjs.txt"],
                    "output": "js.txt",
                },
                outputs=outputs,
            )
        )

        assert _lines(tmp_path / "js.txt") == ["app.js"]
        assert outputs.values["count"] == 1

    def test_blank_file_entries_count_as_missing(self, tmp_path):
        from ofx.modules.builtins import merge

        (tmp_path / "a.txt").write_text("one\n")
        outputs = _Outputs()

        merge.run(
            _ctx(
                tmp_path,
                args={"files": ["a.txt", ""], "output": "all.txt"},
                outputs=outputs,
            )
        )

        assert _lines(tmp_path / "all.txt") == ["one"]

    def test_missing_files_raises(self, tmp_path):
        from ofx.modules.builtins import merge

        with pytest.raises(ValueError, match="requires 'files'"):
            merge.run(_ctx(tmp_path, args={"output": "all.txt"}))

    def test_missing_output_raises(self, tmp_path):
        from ofx.modules.builtins import merge

        with pytest.raises(ValueError, match="requires 'output'"):
            merge.run(_ctx(tmp_path, args={"files": ["a.txt"]}))

    def test_bad_fail_if_raises(self, tmp_path):
        from ofx.modules.builtins import merge

        with pytest.raises(ValueError, match="unsupported fail_if"):
            merge.run(
                _ctx(
                    tmp_path,
                    args={
                        "files": ["a.txt"],
                        "output": "all.txt",
                        "fail_if": "sometimes",
                    },
                )
            )

    def test_run_dir_missing_raises(self):
        from ofx.modules.builtins import merge

        ctx = ModuleContext(
            args={"files": ["a.txt"], "output": "all.txt"},
            env={},
        )
        with pytest.raises(RuntimeError, match="OFX_RUN_DIR is not set"):
            merge.run(ctx)


class TestNormalizeTargets:
    def test_resolves_under_every_builtin_prefix(self):
        registry = ModuleRegistry()
        for spec in (
            "normalize_targets",
            "builtin.normalize_targets",
            "local.builtin.normalize_targets",
        ):
            assert registry.resolve(spec).name == "normalize_targets"

    def test_literal_written_under_run_dir(self, tmp_path):
        from ofx.modules.builtins import normalize

        outputs = _Outputs()
        normalize.run(
            _ctx(
                tmp_path,
                args={"target": "10.0.0.1", "output": "targets.txt"},
                outputs=outputs,
            )
        )

        out = tmp_path / "targets.txt"
        assert _lines(out) == ["10.0.0.1"]
        assert outputs.values == {"target_file": str(out), "count": 1}

    def test_comma_list_and_newlines_are_split(self, tmp_path):
        from ofx.modules.builtins import normalize

        outputs = _Outputs()
        normalize.run(
            _ctx(
                tmp_path,
                args={"target": "a.example, b.example\nc.example,\n"},
                outputs=outputs,
            )
        )

        assert _lines(tmp_path / "targets_normalized.txt") == [
            "a.example",
            "b.example",
            "c.example",
        ]
        assert outputs.values["count"] == 3

    def test_existing_file_is_published_in_place(self, tmp_path):
        from ofx.modules.builtins import normalize

        run_dir = tmp_path / "run"
        run_dir.mkdir()
        source = tmp_path / "hosts.txt"
        source.write_text("a.example\n\nb.example\n")
        outputs = _Outputs()

        normalize.run(
            _ctx(
                run_dir,
                args={"target": str(source), "output": "ignored.txt"},
                outputs=outputs,
            )
        )

        assert outputs.values == {"target_file": str(source.resolve()), "count": 2}
        assert not (run_dir / "ignored.txt").exists()

    def test_empty_file_raises(self, tmp_path):
        from ofx.modules.builtins import normalize

        source = tmp_path / "empty.txt"
        source.write_text("\n\n")
        with pytest.raises(RuntimeError, match="contains no targets"):
            normalize.run(_ctx(tmp_path, args={"target": str(source)}))

    def test_missing_target_raises(self, tmp_path):
        from ofx.modules.builtins import normalize

        with pytest.raises(ValueError, match="requires a 'target'"):
            normalize.run(_ctx(tmp_path, args={}))

    def test_run_dir_missing_raises(self):
        from ofx.modules.builtins import normalize

        with pytest.raises(RuntimeError, match="OFX_RUN_DIR is not set"):
            normalize.run(ModuleContext(args={"target": "10.0.0.1"}, env={}))


class TestClassifyTargets:
    @pytest.fixture(autouse=True)
    def _pin_cwd(self, tmp_path, monkeypatch):
        """Run in an empty directory: relative target paths are CWD-relative."""
        monkeypatch.chdir(tmp_path)

    def test_resolves_under_every_builtin_prefix(self):
        registry = ModuleRegistry()
        for spec in (
            "classify_targets",
            "builtin.classify_targets",
            "local.builtin.classify_targets",
        ):
            assert registry.resolve(spec).name == "classify_targets"

    def test_single_literal_publishes_type(self, tmp_path):
        from ofx.modules.builtins import classify

        outputs = _Outputs()
        classify.run(_ctx(tmp_path, args={"target": "10.0.0.1"}, outputs=outputs))

        assert outputs.values["target_type"] == "ip"
        assert json.loads(outputs.values["counts"]) == {"ip": 1}
        files = json.loads(outputs.values["target_files"])
        assert _lines(Path(files["ip"])) == ["10.0.0.1"]
        assert files["ip"] == str(tmp_path / "targets_ip.txt")

    def test_multiple_types_report_mixed(self, tmp_path):
        from ofx.modules.builtins import classify

        source = tmp_path / "mixed.txt"
        source.write_text("example.com\napi.example.com\n10.0.0.0/24\n10.0.0.1\n")
        outputs = _Outputs()

        classify.run(_ctx(tmp_path, args={"target": str(source)}, outputs=outputs))

        counts = json.loads(outputs.values["counts"])
        assert counts == {"cidr": 1, "domain": 1, "ip": 1, "subdomain": 1}
        assert outputs.values["target_type"] == "mixed"
        files = json.loads(outputs.values["target_files"])
        assert _lines(Path(files["subdomain"])) == ["api.example.com"]

    def test_empty_result_reports_unknown(self, tmp_path):
        from ofx.modules.builtins import classify

        outputs = _Outputs()
        classify.run(
            _ctx(
                tmp_path,
                args={"target": "not a target!"},
                outputs=outputs,
            )
        )

        assert outputs.values["target_type"] == "unknown"
        assert json.loads(outputs.values["counts"]) == {"unknown": 1}

    def test_source_type_target_skips_path_detection(self, tmp_path):
        from ofx.modules.builtins import classify

        outputs = _Outputs()
        classify.run(
            _ctx(
                tmp_path,
                args={"target": "example.com", "source_type": "target"},
                outputs=outputs,
            )
        )

        assert outputs.values["target_type"] == "domain"

    def test_source_type_file_requires_existing_file(self, tmp_path):
        from ofx.modules.builtins import classify

        with pytest.raises(FileNotFoundError, match="target file not found"):
            classify.run(
                _ctx(
                    tmp_path,
                    args={"target": "example.com", "source_type": "file"},
                )
            )

    def test_auto_rejects_path_like_missing_file(self, tmp_path):
        from ofx.modules.builtins import classify

        with pytest.raises(FileNotFoundError, match="looks like a file path"):
            classify.run(_ctx(tmp_path, args={"target": "targets.txt"}))

    def test_auto_rejects_relative_path_like_missing_file(self, tmp_path):
        from ofx.modules.builtins import classify

        with pytest.raises(FileNotFoundError, match="looks like a file path"):
            classify.run(_ctx(tmp_path, args={"target": "./hosts.list"}))

    @pytest.mark.parametrize(
        ("target", "expected"),
        [
            ("10.0.0.0/24", "cidr"),
            ("https://example.com/admin", "url"),
            ("example.com", "domain"),
        ],
    )
    def test_auto_keeps_target_literals_containing_path_markers(
        self, tmp_path, target, expected
    ):
        from ofx.modules.builtins import classify

        outputs = _Outputs()
        classify.run(_ctx(tmp_path, args={"target": target}, outputs=outputs))

        assert outputs.values["target_type"] == expected
        files = json.loads(outputs.values["target_files"])
        assert _lines(Path(files[expected])) == [target]

    def test_unsupported_source_type_raises(self, tmp_path):
        from ofx.modules.builtins import classify

        with pytest.raises(ValueError, match="unsupported source_type"):
            classify.run(
                _ctx(tmp_path, args={"target": "example.com", "source_type": "glob"})
            )

    def test_missing_target_raises(self, tmp_path):
        from ofx.modules.builtins import classify

        with pytest.raises(ValueError, match="target is required"):
            classify.run(_ctx(tmp_path, args={}))

    def test_run_dir_missing_raises(self):
        from ofx.modules.builtins import classify

        with pytest.raises(RuntimeError, match="OFX_RUN_DIR is not set"):
            classify.run(ModuleContext(args={"target": "example.com"}, env={}))


class TestBuiltinDispatch:
    """ModuleRunner routes pure-Python builtins through the ModuleContext path."""

    @pytest.mark.asyncio
    async def test_merge_lists_runs_through_module_runner(self, tmp_path):
        (tmp_path / "a.txt").write_text("one\ntwo\n")
        (tmp_path / "b.txt").write_text("two\n")
        invocation = ModuleInvocation(
            name="merge_lists",
            args={"files": ["a.txt", "b.txt"], "output": "merged.txt"},
        )
        ctx = RunContext(envs={"OFX_RUN_DIR": str(tmp_path)})
        runner = ModuleRunner(invocation, ctx)

        result = await runner.run()

        assert result.status == RunnerStatus.COMPLETED
        outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS)
        assert outputs["count"] == 2
        assert Path(outputs["output_file"]).read_text().splitlines() == ["one", "two"]

    @pytest.mark.asyncio
    async def test_classify_targets_runs_through_module_runner(self, tmp_path):
        invocation = ModuleInvocation(
            name="local.builtin.classify_targets",
            args={"target": "example.com"},
        )
        ctx = RunContext(envs={"OFX_RUN_DIR": str(tmp_path)})
        runner = ModuleRunner(invocation, ctx)

        result = await runner.run()

        assert result.status == RunnerStatus.COMPLETED
        outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS)
        assert outputs["target_type"] == "domain"
        assert (tmp_path / "targets_domain.txt").read_text() == "example.com"

    @pytest.mark.asyncio
    async def test_builtin_failure_surfaces_as_failed_module(self, tmp_path):
        invocation = ModuleInvocation(
            name="normalize_targets",
            args={"target": "10.0.0.1"},
        )
        runner = ModuleRunner(invocation, RunContext())

        result = await runner.run()

        assert result.status == RunnerStatus.FAILED
        assert result.error is not None
        assert "OFX_RUN_DIR is not set" in result.error

class TestRequireArtifacts:
    def test_fails_when_nothing_produced(self, tmp_path):
        from ofx.modules.builtins import artifacts

        with pytest.raises(RuntimeError, match="every scanner failed"):
            artifacts.run(_ctx(tmp_path, args={"files": ["a.txt", "b.txt"], "label": "scanner"}))

    def test_empty_files_count_as_missing(self, tmp_path):
        from ofx.modules.builtins import artifacts

        (tmp_path / "empty.txt").write_text("")
        with pytest.raises(RuntimeError, match="every scanner failed"):
            artifacts.run(_ctx(tmp_path, args={"files": ["empty.txt"], "label": "scanner"}))

    def test_passes_with_one_produced(self, tmp_path):
        from ofx.modules.builtins import artifacts

        (tmp_path / "a.txt").write_text("data\n")
        outputs = _Outputs()
        artifacts.run(_ctx(tmp_path, args={
            "files": ["a.txt", "b.txt"],
            "label": "provider",
        }, outputs=outputs))

        assert outputs.values["produced_count"] == 1
        assert outputs.values["produced_files"] == str(tmp_path / "a.txt")

    def test_min_count_enforced(self, tmp_path):
        from ofx.modules.builtins import artifacts

        (tmp_path / "a.txt").write_text("data\n")
        with pytest.raises(RuntimeError, match="fewer than 2"):
            artifacts.run(_ctx(tmp_path, args={"files": ["a.txt", "b.txt"], "min_count": 2}))

    def test_output_dir_override(self, tmp_path):
        from ofx.modules.builtins import artifacts

        other = tmp_path / "elsewhere"
        other.mkdir()
        (other / "x.txt").write_text("data\n")
        outputs = _Outputs()
        artifacts.run(_ctx(tmp_path, args={"files": ["x.txt"], "output_dir": str(other)}, outputs=outputs))
        assert outputs.values["produced_files"] == str(other / "x.txt")


class TestToolModules:
    """Declared ``local.tool.*`` modules: registry resolution and argv build."""

    def test_tool_names_sorted(self):
        registry = ModuleRegistry()
        assert registry.tool_names == (
            "dalfox",
            "dirsearch",
            "ffuf",
            "sqlmap",
            "tplmap",
        )

    def test_tool_resolves_via_prefix(self):
        registry = ModuleRegistry()
        for name in registry.tool_names:
            resolved = registry.resolve(f"local.tool.{name}")
            assert resolved.kind == "tool"
            assert resolved.name == name
            assert resolved.callable is not None

    def test_unknown_tool_rejected(self):
        registry = ModuleRegistry()
        with pytest.raises(ValueError, match="Unknown tool"):
            registry.resolve("local.tool.nosuchtool")

    def test_tool_ref_rejects_func_suffix(self):
        from ofx.modules.refs import parse_module_ref

        with pytest.raises(ValueError, match="do not take a '::<func>' suffix"):
            parse_module_ref("local.tool.dalfox::run")

    def test_tool_ref_rejects_at_ref(self):
        from ofx.modules.refs import parse_module_ref

        with pytest.raises(ValueError, match="'@<ref>' is only valid on remote"):
            parse_module_ref("local.tool.dalfox@v1")

    def test_tool_ref_missing_name_rejected(self):
        from ofx.modules.refs import parse_module_ref

        with pytest.raises(ValueError, match="missing tool name"):
            parse_module_ref("local.tool")

    def test_missing_binary_fails_explicitly(self, tmp_path):
        import shutil
        from unittest.mock import patch

        from ofx.modules.tools import dalfox

        with patch.object(shutil, "which", return_value=None):
            with pytest.raises(RuntimeError, match="dalfox is not installed"):
                dalfox.run(_ctx(tmp_path, args={"target": "https://x"}))

    def test_dalfox_builds_expected_argv(self, tmp_path):
        import shutil
        import subprocess
        from unittest.mock import MagicMock, patch

        from ofx.modules.tools import dalfox

        captured = {}
        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(shutil, "which", return_value="/usr/bin/dalfox"), \
             patch.object(subprocess, "run", side_effect=fake_run):
            outputs = _Outputs()
            dalfox.run(_ctx(tmp_path, args={"target": "https://x"}, outputs=outputs))

        assert captured["cmd"][:4] == ["dalfox", "url", "https://x", "--silence"]
        assert "-o" in captured["cmd"]
        assert outputs.values["results_file"].endswith("dalfox_results.jsonl")

    def test_sqlmap_uses_results_dir_key(self, tmp_path):
        import shutil
        import subprocess
        from unittest.mock import MagicMock, patch

        from ofx.modules.tools import sqlmap

        def fake_run(cmd, **kwargs):
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(shutil, "which", return_value="/usr/bin/sqlmap"), \
             patch.object(subprocess, "run", side_effect=fake_run):
            outputs = _Outputs()
            sqlmap.run(_ctx(tmp_path, args={"target": "https://x"}, outputs=outputs))

        assert outputs.values["results_dir"].endswith("sqlmap")

    def test_tool_streams_own_source_for_remote(self):
        """Remote payload: tool module source is bundled, not the api wrapper."""
        from ofx.cloud.module_source import resolve_api_step_target, resolve_udf_source
        from ofx.models.step import Step

        step = Step(name="t", module="local.tool.dalfox", run_with={"target": "https://x"})
        assert resolve_api_step_target(step) is None
        src = resolve_udf_source(step)
        assert 'name = "dalfox"' in src
        assert "from ofx" not in src  # self-contained for remote streaming


class TestBuiltinHelperSync:
    """Builtin inline helpers must match the canonical _common.py logic.

    Builtins are self-contained for remote streaming (the bundler only packs
    ofx.lib modules), so each inlines its own _arg/_text_arg/_run_dir. This
    test catches drift: if _common.py changes, the inline copies must too.
    """

    # common.py uses public names; builtins inline underscore-prefixed copies
    _NAME_MAP = {"arg": "_arg", "text_arg": "_text_arg", "run_dir": "_run_dir"}

    def _get_body_statements(self, source: str, names: set[str]) -> dict[str, str]:
        """Extract function body statements (not signature) keyed by name."""
        import ast

        tree = ast.parse(source)
        result = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in names:
                # Only compare body statements, not the signature
                body_src = "\n".join(
                    ast.get_source_segment(source, stmt) or ""
                    for stmt in node.body
                    if not isinstance(stmt, ast.Expr)  # skip docstrings
                )
                result[node.name] = "\n".join(
                    line for line in body_src.splitlines() if line.strip()
                )
        return result

    def test_builtins_have_required_helpers(self):
        """Every self-contained builtin must define its own helpers."""
        from pathlib import Path

        for builtin_file in sorted(Path("src/ofx/modules/builtins").glob("*.py")):
            if builtin_file.name in ("__init__.py", "_common.py", "shell.py", "python.py"):
                continue
            src = builtin_file.read_text()
            assert "_arg" in src or "arg(" in src, f"{builtin_file.name} missing arg helper"
            assert "_run_dir" in src or "run_dir(" in src, f"{builtin_file.name} missing run_dir helper"

    def test_tools_have_required_helpers(self):
        """Every tool module must define its own helpers."""
        from pathlib import Path

        for tool_file in sorted(Path("src/ofx/modules/tools").glob("*.py")):
            if tool_file.name == "__init__.py":
                continue
            src = tool_file.read_text()
            assert "_text_arg" in src, f"{tool_file.name} missing _text_arg helper"
            assert "_run_dir" in src, f"{tool_file.name} missing _run_dir helper"
            assert "_require_target" in src, f"{tool_file.name} missing _require_target helper"



class TestLibraryModules:
    """Auto-generated library wrappers for ofx.lib functions."""

    def test_library_registered(self):
        registry = ModuleRegistry()
        names = registry.library_names
        assert len(names) > 100, f"expected 100+ library modules, got {len(names)}"

    def test_library_resolves_via_prefix(self):
        registry = ModuleRegistry()
        spec = registry.resolve("local.builtin.recon.targets.split_targets")
        assert spec.kind == "lib"
        assert "values" in spec.args_schema
        assert spec.args_schema["values"].get("required") is True

    def test_library_resolves_c2(self):
        registry = ModuleRegistry()
        spec = registry.resolve("local.builtin.c2.bash_reverse_shell")
        assert spec.kind == "lib"
        assert "lhost" in spec.args_schema
        assert "lport" in spec.args_schema

    def test_registered_builtins_win_over_library(self):
        """Registered builtins (shell, python, merge_lists) take precedence."""
        registry = ModuleRegistry()
        spec = registry.resolve("local.builtin.shell")
        assert spec.kind == "builtin"  # not api

    def test_library_execution(self, tmp_path):
        """A library module actually executes via ModuleRunner."""
        import asyncio

        from ofx.modules import ModuleInvocation, ModuleRunner
        from ofx.runner import RunContext, RunnerStatus

        inv = ModuleInvocation(
            name="local.builtin.c2.bash_reverse_shell",
            args={"lhost": "10.0.0.1", "lport": "4444"},
        )
        runner = ModuleRunner(inv, RunContext(output_path=tmp_path))
        result = asyncio.run(runner.run())
        assert result.status == RunnerStatus.COMPLETED
        assert "result" in result.outputs
        assert "10.0.0.1" in result.outputs["result"]

    def test_library_no_args_function(self, tmp_path):
        """A zero-arg library module (suid_commands) works."""
        import asyncio

        from ofx.modules import ModuleInvocation, ModuleRunner
        from ofx.runner import RunContext, RunnerStatus

        inv = ModuleInvocation(name="local.builtin.privesc.linux.suid_commands", args={})
        runner = ModuleRunner(inv, RunContext(output_path=tmp_path))
        result = asyncio.run(runner.run())
        assert result.status == RunnerStatus.COMPLETED
        assert "result" in result.outputs
