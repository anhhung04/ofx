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


class TestScanTool:
    def test_requires_tool_and_target(self, tmp_path):
        from ofx.modules.builtins import scan

        with pytest.raises(ValueError, match="tool is required"):
            scan.run(_ctx(tmp_path, args={"target": "https://x", "args": [], "output": "o.txt", "output_arg": "-o"}))
        with pytest.raises(ValueError, match="target is required"):
            scan.run(_ctx(tmp_path, args={"tool": "echo", "args": [], "output": "o.txt", "output_arg": "-o"}))

    def test_missing_binary_fails_explicitly(self, tmp_path):
        from ofx.modules.builtins import scan

        with pytest.raises(RuntimeError, match="not installed"):
            scan.run(_ctx(tmp_path, args={
                "tool": "definitely-not-a-real-tool-xyz",
                "target": "https://x",
                "args": [],
                "output": "o.txt",
                "output_arg": "-o",
            }))

    def test_placeholder_expansion_and_output_arg(self, tmp_path):
        from ofx.modules.builtins import scan

        outputs = _Outputs()
        scan.run(_ctx(tmp_path, args={
            "tool": "printf",
            "target": "https://example.com",
            "args": [["%s", "{target}"]],
            "output": "report.txt",
            "output_arg": "--out",
        }, outputs=outputs))

        assert outputs.values == {"results_file": str(tmp_path / "report.txt")}

    def test_capture_stdout_writes_output_file(self, tmp_path):
        from ofx.modules.builtins import scan

        outputs = _Outputs()
        scan.run(_ctx(tmp_path, args={
            "tool": "echo",
            "target": "https://example.com",
            "args": ["{target}"],
            "output": "stdout.txt",
            "capture_stdout": True,
        }, outputs=outputs))

        out = tmp_path / "stdout.txt"
        assert out.read_text().strip() == "https://example.com"
        assert outputs.values == {"results_file": str(out)}

    def test_capture_stdout_without_output_arg_accepted(self, tmp_path):
        from ofx.modules.builtins import scan

        # No output_arg: capture_stdout path must not demand one
        scan.run(_ctx(tmp_path, args={
            "tool": "true",
            "target": "https://example.com",
            "args": [],
            "output": "empty.txt",
            "capture_stdout": True,
        }))
        assert (tmp_path / "empty.txt").read_text() == ""

    def test_nonzero_exit_surfaces_tool_output(self, tmp_path):
        from ofx.modules.builtins import scan

        with pytest.raises(RuntimeError, match="exited 1"):
            scan.run(_ctx(tmp_path, args={
                "tool": "false",
                "target": "https://example.com",
                "args": [],
                "output": "o.txt",
                "output_arg": "-o",
            }))

    def test_custom_results_output_key(self, tmp_path):
        from ofx.modules.builtins import scan

        outputs = _Outputs()
        scan.run(_ctx(tmp_path, args={
            "tool": "printf",
            "target": "https://example.com",
            "args": [["%s", "{target}"]],
            "output": "sqli",
            "output_arg": "--output-dir",
            "results_output_key": "results_dir",
        }, outputs=outputs))

        assert outputs.values == {"results_dir": str(tmp_path / "sqli")}


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
