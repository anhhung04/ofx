"""Tests for miscellaneous utility modules with zero/low coverage."""

from __future__ import annotations

import json
import sys
import types
from enum import Enum
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# json_utils.py
# ---------------------------------------------------------------------------


class TestEnumEncoder:
    def test_encodes_enum_as_value(self):
        from ofx.utils.json_utils import EnumEncoder

        class Color(Enum):
            RED = "red"
            BLUE = 1

        assert json.dumps(Color.RED, cls=EnumEncoder) == '"red"'
        assert json.dumps(Color.BLUE, cls=EnumEncoder) == "1"

    def test_non_enum_uses_default(self):
        from ofx.utils.json_utils import EnumEncoder

        with pytest.raises(TypeError):
            json.dumps(object(), cls=EnumEncoder)

    def test_mixed_list(self):
        from ofx.utils.json_utils import EnumEncoder

        class Status(Enum):
            OK = "ok"

        data = [Status.OK, "plain", 42]
        result = json.loads(json.dumps(data, cls=EnumEncoder))
        assert result == ["ok", "plain", 42]


# ---------------------------------------------------------------------------
# module_loader.py
# ---------------------------------------------------------------------------


class TestModuleLoader:
    def test_module_name_is_stable(self):
        from ofx.utils.module_loader import module_name_for_path

        p = Path("/some/path/myplugin.py")
        name1 = module_name_for_path("mypkg", p)
        name2 = module_name_for_path("mypkg", p)
        assert name1 == name2
        assert name1.startswith("mypkg.")
        assert "myplugin" in name1

    def test_module_name_differs_for_different_paths(self):
        from ofx.utils.module_loader import module_name_for_path

        p1 = Path("/a/foo.py")
        p2 = Path("/b/foo.py")
        assert module_name_for_path("pkg", p1) != module_name_for_path("pkg", p2)

    def test_load_module_from_file(self, tmp_path):
        from ofx.utils.module_loader import load_module_from_file

        f = tmp_path / "testmod.py"
        f.write_text("X = 42\n")
        mod = load_module_from_file(f, "testprefix")
        assert mod is not None
        assert mod.X == 42  # type: ignore[attr-defined]

    def test_load_module_returns_none_for_missing_spec(self, tmp_path, monkeypatch):
        import importlib.util

        from ofx.utils.module_loader import load_module_from_file

        monkeypatch.setattr(
            importlib.util, "spec_from_file_location", lambda *a, **kw: None
        )
        f = tmp_path / "ghost.py"
        f.write_text("pass")
        result = load_module_from_file(f, "prefix")
        assert result is None

    def test_load_module_cached_in_sys_modules(self, tmp_path):
        from ofx.utils.module_loader import load_module_from_file, module_name_for_path

        f = tmp_path / "cached.py"
        f.write_text("VAL = 'hello'\n")
        _mod = load_module_from_file(f, "cache_test")
        mod_name = module_name_for_path("cache_test", f)
        assert mod_name in sys.modules

    def test_iter_subclasses(self):
        from ofx.utils.module_loader import iter_subclasses

        module = types.ModuleType("fake")

        class Base:
            pass

        class Child(Base):
            pass

        class Grandchild(Child):
            pass

        module.Base = Base  # type: ignore[attr-defined]
        module.Child = Child  # type: ignore[attr-defined]
        module.Grandchild = Grandchild  # type: ignore[attr-defined]
        module.not_a_class = 42  # type: ignore[attr-defined]

        results = iter_subclasses(module, Base)
        # Should find Child and Grandchild, not Base itself
        assert Base not in results
        assert Child in results
        assert Grandchild in results

    def test_iter_subclasses_empty(self):
        from ofx.utils.module_loader import iter_subclasses

        module = types.ModuleType("empty")

        class Base:
            pass

        results = iter_subclasses(module, Base)
        assert results == []


# ---------------------------------------------------------------------------
# utils/args.py
# ---------------------------------------------------------------------------


class TestParseKeyValuePairs:
    def test_empty_inputs(self):
        from ofx.utils.args import parse_key_value_pairs

        assert parse_key_value_pairs(None) == {}
        assert parse_key_value_pairs([]) == {}

    def test_simple_string_value(self):
        from ofx.utils.args import parse_key_value_pairs

        result = parse_key_value_pairs(["host=localhost"])
        assert result == {"host": "localhost"}

    def test_json_value_parsed(self):
        from ofx.utils.args import parse_key_value_pairs

        result = parse_key_value_pairs(["ports=[80,443]"])
        assert result == {"ports": [80, 443]}

    def test_non_json_string_kept(self):
        from ofx.utils.args import parse_key_value_pairs

        result = parse_key_value_pairs(["label=hello world"])
        assert result["label"] == "hello world"

    def test_multiple_values_for_same_key(self):
        from ofx.utils.args import parse_key_value_pairs

        result = parse_key_value_pairs(["tag=a", "tag=b", "tag=c"])
        assert result["tag"] == ["a", "b", "c"]

    def test_single_value_flattened(self):
        from ofx.utils.args import parse_key_value_pairs

        result = parse_key_value_pairs(["key=value"])
        # Single-element lists are flattened
        assert isinstance(result["key"], str)
        assert result["key"] == "value"

    def test_keep_string_skips_json_parse(self):
        from ofx.utils.args import parse_key_value_pairs

        result = parse_key_value_pairs(["n=42"], keep_string=True)
        assert result["n"] == "42"

    def test_invalid_format_raises(self):
        from ofx.utils.args import parse_key_value_pairs

        with pytest.raises(ValueError, match="Invalid input format"):
            parse_key_value_pairs(["noequalsign"])

    def test_value_with_equals_sign(self):
        from ofx.utils.args import parse_key_value_pairs

        result = parse_key_value_pairs(["url=http://host/path?a=1"])
        assert result["url"] == "http://host/path?a=1"


# ---------------------------------------------------------------------------
# utils/matrix.py — expand_jobs + get_expanded_job_ids fallback
# ---------------------------------------------------------------------------


class TestExpandJobs:
    def _make_job(self, matrix: dict | None = None, needs: list | None = None):
        from ofx.models.job import Job

        data: dict = {"steps": [{"run": "echo hi"}]}
        if matrix:
            data["strategy"] = {"matrix": matrix}
        if needs:
            data["needs"] = needs
        return Job.model_validate(data)

    def test_non_matrix_job_preserved(self):
        from ofx.utils.matrix import expand_jobs

        job = self._make_job()
        result = expand_jobs({"build": job})
        assert "build" in result
        assert result["build"].jid == "build"
        assert result["build"].matrix_values == {}
        assert result["build"].max_parallel is None

    def test_matrix_job_kept_as_single_unit(self):
        from ofx.utils.matrix import expand_jobs

        job = self._make_job(matrix={"os": ["linux", "windows"]})
        result = expand_jobs({"test": job})
        assert "test" in result
        # matrix job: max_parallel and fail_fast propagated from strategy
        assert result["test"].original_job_id == "test"

    def test_multiple_jobs(self):
        from ofx.utils.matrix import expand_jobs

        j1 = self._make_job()
        j2 = self._make_job(matrix={"env": ["prod", "dev"]})
        result = expand_jobs({"j1": j1, "j2": j2})
        assert set(result.keys()) == {"j1", "j2"}


class TestGetExpandedJobIds:
    def _make_expanded(self, original: str, jids: list[str]):
        from ofx.models.job import Job

        jobs = {}
        for jid in jids:
            j = Job.model_validate({"steps": [{"run": "echo"}]})
            j.jid = jid
            j.original_job_id = original
            jobs[jid] = j
        return jobs

    def test_returns_expanded_ids(self):
        from ofx.utils.matrix import get_expanded_job_ids

        expanded = self._make_expanded("build", ["build_0", "build_1"])
        result = get_expanded_job_ids(expanded, "build")
        assert set(result) == {"build_0", "build_1"}

    def test_fallback_when_not_found(self):
        from ofx.utils.matrix import get_expanded_job_ids

        expanded = self._make_expanded("other", ["other_0"])
        # 'missing' not in expanded → should return ["missing"]
        result = get_expanded_job_ids(expanded, "missing")
        assert result == ["missing"]
