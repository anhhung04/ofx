"""Tests for pipe (ETL) step execution."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ofx.models.pipe import PipeConfig
from ofx.models.step import RunType, Step
from ofx.runner.pipe import (
    _coerce_to_list,
    _execute_pipeline,
    _format_items,
    _safe_eval,
)

class TestPipeConfig:
    def test_minimal(self):
        cfg = PipeConfig(input="{{ steps.0.outputs.data }}")
        assert cfg.format == "json"
        assert cfg.filter is None
        assert cfg.map is None

    def test_full(self):
        cfg = PipeConfig(
            input="{{ x }}",
            filter="port > 80",
            map={"url": "'http://' + host"},
            sort="port",
            unique="host",
            limit=10,
            offset=5,
            format="lines",
            field="url",
        )
        assert cfg.limit == 10
        assert cfg.format == "lines"

    def test_sort_list(self):
        cfg = PipeConfig(input="{{ x }}", sort=["host", "port"])
        assert cfg.sort == ["host", "port"]

    def test_invalid_lines_groupby(self):
        with pytest.raises(ValueError, match="Cannot combine"):
            PipeConfig(
                input="{{ x }}", format="lines", group_by="svc"
            )

    def test_limit_zero_rejected(self):
        with pytest.raises(ValueError):
            PipeConfig(input="{{ x }}", limit=0)

class TestStepPipe:
    def test_pipe_run_type(self):
        step = Step(pipe={"input": "{{ x }}"})
        assert step.get_run_type() == RunType.PIPE

    def test_pipe_exclusive(self):
        with pytest.raises(ValueError, match="exactly one"):
            Step(pipe={"input": "{{ x }}"}, run="echo hi")

    def test_pipe_config_validated(self):
        step = Step(pipe={"input": "{{ x }}", "filter": "port > 80"})
        assert isinstance(step.pipe, PipeConfig)
        assert step.pipe.filter == "port > 80"

class TestCoerceToList:
    def test_list_passthrough(self):
        assert _coerce_to_list([1, 2, 3]) == [1, 2, 3]

    def test_json_array(self):
        assert _coerce_to_list('[1, 2, 3]') == [1, 2, 3]

    def test_json_object(self):
        result = _coerce_to_list('{"a": 1}')
        assert result == [{"a": 1}]

    def test_newline_separated(self):
        assert _coerce_to_list("a\nb\nc") == ["a", "b", "c"]

    def test_comma_separated(self):
        assert _coerce_to_list("a,b,c") == ["a", "b", "c"]

    def test_single_value(self):
        assert _coerce_to_list("hello") == ["hello"]

    def test_empty_string(self):
        assert _coerce_to_list("") == []

    def test_none(self):
        assert _coerce_to_list(None) == []

    def test_dict_wrapped(self):
        assert _coerce_to_list({"a": 1}) == [{"a": 1}]

class TestSafeEval:
    def test_simple_comparison(self):
        assert _safe_eval("port > 80", {"port": 443}) is True
        assert _safe_eval("port > 80", {"port": 22}) is False

    def test_string_ops(self):
        assert _safe_eval("state == 'open'", {"state": "open"}) is True

    def test_in_operator(self):
        assert _safe_eval("port in [80, 443]", {"port": 80}) is True
        assert _safe_eval("port in [80, 443]", {"port": 22}) is False

    def test_string_concat(self):
        result = _safe_eval("'http://' + host + ':' + str(port)", {"host": "x.com", "port": 80})
        assert result == "http://x.com:80"

    def test_forbidden_import(self):
        with pytest.raises(ValueError, match="Forbidden"):
            _safe_eval("__import__('os')", {})

    def test_forbidden_eval(self):
        with pytest.raises(ValueError, match="Forbidden"):
            _safe_eval("eval('1+1')", {})

    def test_builtins_available(self):
        assert _safe_eval("len([1,2,3])", {}) == 3
        assert _safe_eval("str(42)", {}) == "42"
        assert _safe_eval("int('42')", {}) == 42

    def test_boolean_operators(self):
        assert _safe_eval("a and b", {"a": True, "b": True}) is True
        assert _safe_eval("a or b", {"a": False, "b": True}) is True
        assert _safe_eval("not a", {"a": False}) is True

SAMPLE_DATA = [
    {"host": "10.0.0.1", "port": 22, "state": "open", "svc": "ssh"},
    {"host": "10.0.0.1", "port": 80, "state": "open", "svc": "http"},
    {"host": "10.0.0.2", "port": 22, "state": "open", "svc": "ssh"},
    {"host": "10.0.0.2", "port": 443, "state": "open", "svc": "https"},
    {"host": "10.0.0.3", "port": 22, "state": "closed", "svc": "ssh"},
]

class TestExecutePipeline:
    def test_filter(self):
        cfg = PipeConfig(input="{{ x }}", filter="state == 'open'")
        result = _execute_pipeline(SAMPLE_DATA.copy(), cfg)
        assert len(result) == 4

    def test_filter_complex(self):
        cfg = PipeConfig(
            input="{{ x }}",
            filter="state == 'open' and svc in ['http', 'https']",
        )
        result = _execute_pipeline(SAMPLE_DATA.copy(), cfg)
        assert len(result) == 2

    def test_map(self):
        cfg = PipeConfig(
            input="{{ x }}",
            map={"url": "'http://' + host + ':' + str(port)", "host": "host"},
        )
        result = _execute_pipeline(SAMPLE_DATA.copy(), cfg)
        assert result[0]["url"] == "http://10.0.0.1:22"
        assert "port" not in result[0]

    def test_sort(self):
        cfg = PipeConfig(input="{{ x }}", sort="port")
        result = _execute_pipeline(SAMPLE_DATA.copy(), cfg)
        ports = [r["port"] for r in result]
        assert ports == sorted(ports)

    def test_sort_reverse(self):
        cfg = PipeConfig(input="{{ x }}", sort="port", reverse=True)
        result = _execute_pipeline(SAMPLE_DATA.copy(), cfg)
        ports = [r["port"] for r in result]
        assert ports == sorted(ports, reverse=True)

    def test_sort_object_items_by_attribute(self):
        data = [SimpleNamespace(port=443), SimpleNamespace(port=80)]
        cfg = PipeConfig(input="{{ x }}", sort="port")

        result = _execute_pipeline(data, cfg)

        assert [item.port for item in result] == [80, 443]

    def test_unique(self):
        cfg = PipeConfig(input="{{ x }}", unique="host")
        result = _execute_pipeline(SAMPLE_DATA.copy(), cfg)
        hosts = [r["host"] for r in result]
        assert len(hosts) == len(set(hosts))
        assert len(result) == 3

    def test_unique_multi(self):
        cfg = PipeConfig(input="{{ x }}", unique=["host", "svc"])
        result = _execute_pipeline(SAMPLE_DATA.copy(), cfg)
        assert len(result) == 5

    def test_unique_object_items_by_attribute(self):
        data = [
            SimpleNamespace(host="a", port=80),
            SimpleNamespace(host="a", port=443),
            SimpleNamespace(host="b", port=80),
        ]
        cfg = PipeConfig(input="{{ x }}", unique="host")

        result = _execute_pipeline(data, cfg)

        assert [item.host for item in result] == ["a", "b"]

    def test_limit(self):
        cfg = PipeConfig(input="{{ x }}", limit=2)
        result = _execute_pipeline(SAMPLE_DATA.copy(), cfg)
        assert len(result) == 2

    def test_offset(self):
        cfg = PipeConfig(input="{{ x }}", offset=3)
        result = _execute_pipeline(SAMPLE_DATA.copy(), cfg)
        assert len(result) == 2

    def test_offset_limit(self):
        cfg = PipeConfig(input="{{ x }}", offset=1, limit=2)
        result = _execute_pipeline(SAMPLE_DATA.copy(), cfg)
        assert len(result) == 2
        assert result[0]["port"] == 80

    def test_group_by(self):
        cfg = PipeConfig(input="{{ x }}", group_by="host", format="json")
        result = _execute_pipeline(SAMPLE_DATA.copy(), cfg)
        assert isinstance(result, dict)
        assert "10.0.0.1" in result
        assert len(result["10.0.0.1"]) == 2

    def test_group_object_items_by_attribute(self):
        data = [SimpleNamespace(host="a"), SimpleNamespace(host="b")]
        cfg = PipeConfig(input="{{ x }}", group_by="host", format="json")

        result = _execute_pipeline(data, cfg)

        assert list(result) == ["a", "b"]

    def test_flatten(self):
        data = [
            {"host": "a", "ports": [80, 443]},
            {"host": "b", "ports": [22]},
        ]
        cfg = PipeConfig(input="{{ x }}", flatten="ports")
        result = _execute_pipeline(data, cfg)
        assert len(result) == 3
        assert result[0]["ports"] == 80
        assert result[0]["host"] == "a"

    def test_filter_map_sort_combined(self):
        cfg = PipeConfig(
            input="{{ x }}",
            filter="state == 'open'",
            map={"url": "'http://' + host + ':' + str(port)", "port": "port"},
            sort="port",
        )
        result = _execute_pipeline(SAMPLE_DATA.copy(), cfg)
        assert len(result) == 4
        assert result[0]["url"] == "http://10.0.0.1:22"
        ports = [r["port"] for r in result]
        assert ports == sorted(ports)

    def test_empty_input(self):
        cfg = PipeConfig(input="{{ x }}")
        result = _execute_pipeline([], cfg)
        assert result == []

class TestFormatItems:
    def test_json(self):
        cfg = PipeConfig(input="{{ x }}", format="json")
        result = _format_items([{"a": 1}], cfg)
        parsed = json.loads(result)
        assert parsed == [{"a": 1}]

    def test_jsonl(self):
        cfg = PipeConfig(input="{{ x }}", format="jsonl")
        result = _format_items([{"a": 1}, {"a": 2}], cfg)
        lines = result.strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"a": 1}

    def test_lines(self):
        cfg = PipeConfig(input="{{ x }}", format="lines", field="host")
        items = [{"host": "a"}, {"host": "b"}]
        result = _format_items(items, cfg)
        assert result == "a\nb"

    def test_lines_scalar(self):
        cfg = PipeConfig(input="{{ x }}", format="lines")
        result = _format_items(["a", "b", "c"], cfg)
        assert result == "a\nb\nc"

    def test_csv(self):
        cfg = PipeConfig(input="{{ x }}", format="csv")
        items = [{"host": "a", "port": "80"}, {"host": "b", "port": "443"}]
        result = _format_items(items, cfg)
        lines = result.split("\n")
        assert "host" in lines[0]
        assert len(lines) == 3

    def test_csv_no_headers(self):
        cfg = PipeConfig(input="{{ x }}", format="csv", headers=False)
        items = [{"host": "a", "port": "80"}]
        result = _format_items(items, cfg)
        assert "host" not in result
        assert "a" in result

    def test_empty(self):
        cfg = PipeConfig(input="{{ x }}", format="json")
        assert _format_items([], cfg) == "[]"

class TestPipeFlowRun:
    @pytest.mark.asyncio
    async def test_pipe_basic_workflow(self, tmp_path):
        """Run the pipe_basic.yml workflow end-to-end."""
        from ofx.runner import RunContext, RunnerStatus, WorkflowRunner
        from ofx.utils.workflow_utils import find_workflow

        flow_dir = Path(__file__).parent / "flows"
        workflow = find_workflow(
            str(flow_dir / "pipe_basic.yml"),
            (flow_dir, Path.cwd()),
        )
        ctx = RunContext(output_path=tmp_path, workflow_dirs=[flow_dir])
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        result = await runner.run()

        assert result.status == RunnerStatus.COMPLETED, (
            f"Pipe workflow failed: {result.error}"
        )

class TestSafeEvalEdgeCases:
    """Edge cases for the safe expression evaluator."""

    def test_syntax_error_in_filter(self):
        with pytest.raises((SyntaxError, ValueError)):
            _safe_eval("port >>>> 80", {"port": 80})

    def test_undefined_variable(self):
        with pytest.raises((NameError, ValueError)):
            _safe_eval("undefined_var > 0", {})

    def test_forbidden_exec(self):
        with pytest.raises(ValueError, match="Forbidden"):
            _safe_eval("exec('print(1)')", {})

    def test_forbidden_open(self):
        with pytest.raises(ValueError, match="Forbidden"):
            _safe_eval("open('/etc/passwd')", {})

    def test_forbidden_getattr(self):
        with pytest.raises(ValueError, match="Forbidden"):
            _safe_eval("getattr(object, '__class__')", {})

    def test_forbidden_compile(self):
        with pytest.raises(ValueError, match="Forbidden"):
            _safe_eval("compile('1+1', '', 'exec')", {})

    def test_dunder_access(self):
        with pytest.raises(ValueError, match="Forbidden"):
            _safe_eval("''.__class__.__mro__", {})

    def test_nested_forbidden(self):
        with pytest.raises(ValueError, match="Forbidden"):
            _safe_eval("(lambda: __import__('os'))()", {})

    def test_none_field_access(self):
        with pytest.raises(AttributeError):
            _safe_eval("x.nonexistent", {"x": None})

class TestPipelineEdgeCases:
    """Edge cases and combined operations."""

    def test_all_operations_combined(self):
        """Apply every operation in a single pipeline."""
        data = [
            {"host": "10.0.0.1", "port": 22, "state": "open"},
            {"host": "10.0.0.1", "port": 80, "state": "open"},
            {"host": "10.0.0.2", "port": 22, "state": "closed"},
            {"host": "10.0.0.2", "port": 443, "state": "open"},
            {"host": "10.0.0.3", "port": 80, "state": "open"},
        ]
        cfg = PipeConfig(
            input="{{ x }}",
            filter="state == 'open'",
            map={"host": "host", "port": "port"},
            sort="port",
            unique="host",
            limit=2,
            offset=0,
            format="jsonl",
        )
        result = _execute_pipeline(data.copy(), cfg)
        assert len(result) <= 2
        for item in result:
            assert "host" in item
            assert "port" in item

    def test_filter_removes_all(self):
        """Filter that removes every item produces empty result."""
        data = [{"port": 80}, {"port": 22}]
        cfg = PipeConfig(input="{{ x }}", filter="port > 9999")
        result = _execute_pipeline(data.copy(), cfg)
        assert result == []

    def test_map_expression_error_produces_none(self):
        """Map expression causing runtime error sets field to None."""
        data = [{"value": "not_a_number"}]
        cfg = PipeConfig(input="{{ x }}", map={"result": "int(value)"})
        result = _execute_pipeline(data.copy(), cfg)
        assert len(result) == 1
        assert result[0]["result"] is None

    def test_empty_input_with_all_ops(self):
        """All operations on empty input should produce empty result."""
        cfg = PipeConfig(
            input="{{ x }}",
            filter="port > 0",
            sort="port",
            unique="port",
            limit=10,
        )
        result = _execute_pipeline([], cfg)
        assert result == []

    def test_sort_with_reverse(self):
        data = [{"v": 1}, {"v": 3}, {"v": 2}]
        cfg = PipeConfig(input="{{ x }}", sort="v", reverse=True)
        result = _execute_pipeline(data.copy(), cfg)
        assert [r["v"] for r in result] == [3, 2, 1]

    def test_offset_beyond_length(self):
        data = [{"v": 1}, {"v": 2}]
        cfg = PipeConfig(input="{{ x }}", offset=10)
        result = _execute_pipeline(data.copy(), cfg)
        assert result == []

    def test_group_by_produces_dict(self):
        data = [
            {"team": "a", "val": 1},
            {"team": "b", "val": 2},
            {"team": "a", "val": 3},
        ]
        cfg = PipeConfig(input="{{ x }}", group_by="team")
        result = _execute_pipeline(data.copy(), cfg)
        assert isinstance(result, dict)
        assert set(result.keys()) == {"a", "b"}
        assert len(result["a"]) == 2
        assert len(result["b"]) == 1

class TestStepPipeEdgeCases:
    """Validate pipe step model constraints."""

    def test_pipe_task_mutual_exclusivity(self):
        with pytest.raises(ValueError, match="exactly one"):
            Step(pipe={"input": "{{ x }}"}, task="nmap")

    def test_pipe_script_mutual_exclusivity(self):
        with pytest.raises(ValueError, match="exactly one"):
            Step(pipe={"input": "{{ x }}"}, script="print(1)")

    def test_pipe_uses_mutual_exclusivity(self):
        with pytest.raises(ValueError, match="exactly one"):
            Step(pipe={"input": "{{ x }}"}, uses="other/workflow")

    def test_pipe_script_file_mutual_exclusivity(self):
        with pytest.raises(ValueError, match="exactly one"):
            Step(pipe={"input": "{{ x }}"}, script_file="test.py")
