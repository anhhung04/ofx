"""Executor for declarative pipe steps."""

from __future__ import annotations

import ast
import csv
import io
import json
import logging
from contextlib import suppress
from typing import Any

from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.models.pipe import PipeConfig
from ofx.runner.executors.base import Executor
from ofx.utils.file_cleanup import remove_file

logger = logging.getLogger("ofx.pipe")

_SAFE_BUILTINS: dict[str, Any] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "len": len,
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "sorted": sorted,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "any": any,
    "all": all,
    "round": round,
    "isinstance": isinstance,
    "True": True,
    "False": False,
    "None": None,
}

def _coerce_to_list(raw: Any) -> list[Any]:
    """Coerce a template-resolved value to a list of items."""
    if isinstance(raw, list):
        return raw

    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        if raw.startswith("[") or raw.startswith("{"):
            with suppress(json.JSONDecodeError):
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, list) else [parsed]
        if "\n" in raw:
            return [line.strip() for line in raw.splitlines() if line.strip()]
        if "," in raw:
            return [v.strip() for v in raw.split(",") if v.strip()]
        return [raw]

    if isinstance(raw, dict):
        return [raw]

    try:
        return list(raw)
    except TypeError:
        return [raw] if raw is not None else []

def _safe_eval(expr: str, namespace: dict[str, Any]) -> Any:
    """Evaluate *expr* with a restricted set of builtins."""
    code = compile(expr, "<pipe-expr>", "eval")
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in (
            "__import__",
            "exec",
            "eval",
            "open",
            "compile",
            "globals",
            "locals",
            "getattr",
            "setattr",
            "delattr",
            "__builtins__",
        ):
            raise ValueError(f"Forbidden name in pipe expression: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError(
                f"Forbidden dunder attribute access in pipe expression: {node.attr}"
            )

    safe_ns: dict[str, Any] = {"__builtins__": {}}
    safe_ns.update(_SAFE_BUILTINS)
    safe_ns.update(namespace)
    return eval(code, safe_ns)

def _item_namespace(item: Any) -> dict[str, Any]:
    """Build the evaluation namespace from a single pipeline item."""
    if isinstance(item, dict):
        return dict(item)
    ns: dict[str, Any] = {}
    for attr in dir(item):
        if not attr.startswith("_"):
            try:
                ns[attr] = getattr(item, attr)
            except Exception:
                logger.debug("Failed to read attribute %s from item", attr)
    return ns

def _format_items(items: list[Any], config: PipeConfig) -> str:
    """Serialize *items* according to [`PipeConfig.format`](src/ofx/models/pipe.py)."""
    fmt = config.format

    if fmt == "json":
        return json.dumps(items, indent=2, default=str)

    if fmt == "jsonl":
        return "\n".join(json.dumps(item, default=str) for item in items)

    if fmt == "lines":
        parts: list[str] = []
        for item in items:
            if isinstance(item, dict) and config.field:
                parts.append(str(item.get(config.field, "")))
            elif isinstance(item, dict):
                parts.append(str(next(iter(item.values()), "")))
            else:
                parts.append(str(item))
        return config.separator.join(parts)

    if fmt == "csv":
        if not items:
            return ""
        buf = io.StringIO()
        if isinstance(items[0], dict):
            fieldnames = list(items[0].keys())
            writer = csv.DictWriter(buf, fieldnames=fieldnames)
            if config.headers:
                writer.writeheader()
            for item in items:
                writer.writerow({k: str(v) for k, v in item.items()})
        else:
            writer_simple = csv.writer(buf)
            for item in items:
                writer_simple.writerow([str(item)])
        return buf.getvalue().rstrip("\r\n")

    if fmt == "yaml":
        try:
            import yaml

            return yaml.dump(items, default_flow_style=False)
        except ImportError:
            return json.dumps(items, indent=2, default=str)

    return json.dumps(items, indent=2, default=str)

def _execute_pipeline(items: list[Any], config: PipeConfig) -> list[Any] | dict:
    """Run the ETL operations on *items* and return the processed result."""
    def item_field_value(item: Any, field: str) -> Any:
        if isinstance(item, dict):
            return item.get(field)
        return getattr(item, field, None)

    if config.filter:
        expr = config.filter
        filtered: list[Any] = []
        for item in items:
            ns = _item_namespace(item)
            try:
                if _safe_eval(expr, ns):
                    filtered.append(item)
            except Exception as exc:
                logger.debug("Filter expression failed for item: %s", exc)
        items = filtered

    if config.map:
        mapped: list[Any] = []
        for item in items:
            ns = _item_namespace(item)
            new_item: dict[str, Any] = {}
            for key, expr in config.map.items():
                try:
                    new_item[key] = _safe_eval(expr, ns)
                except Exception as exc:
                    logger.debug("Map expression '%s' failed: %s", key, exc)
                    new_item[key] = None
            mapped.append(new_item)
        items = mapped

    if config.flatten:
        field = config.flatten
        flat: list[Any] = []
        for item in items:
            if isinstance(item, dict) and isinstance(item.get(field), list):
                for sub in item[field]:
                    if isinstance(sub, dict):
                        merged = {k: v for k, v in item.items() if k != field}
                        merged.update(sub)
                        flat.append(merged)
                    else:
                        new_entry = {k: v for k, v in item.items() if k != field}
                        new_entry[field] = sub
                        flat.append(new_entry)
            else:
                flat.append(item)
        items = flat

    if config.sort:
        sort_fields = (
            [config.sort] if isinstance(config.sort, str) else list(config.sort)
        )

        def _sort_key(item: Any) -> tuple:
            normalized_values: list[tuple[int, Any, str]] = []
            for field in sort_fields:
                value = item_field_value(item, field)
                if value is None:
                    normalized_values.append((0, "", ""))
                    continue
                if isinstance(value, (int, float)):
                    normalized_values.append((0, value, ""))
                    continue
                try:
                    normalized_values.append((0, float(value), ""))
                except (ValueError, TypeError):
                    normalized_values.append((1, 0, str(value)))
            return tuple(normalized_values)

        with suppress(TypeError):
            items = sorted(items, key=_sort_key, reverse=config.reverse)

    if config.unique:
        unique_fields = (
            [config.unique] if isinstance(config.unique, str) else list(config.unique)
        )
        seen: set[tuple] = set()
        unique_items: list[Any] = []
        for item in items:
            key = (
                tuple(item_field_value(item, field) for field in unique_fields)
                if isinstance(item, dict)
                or any(hasattr(item, field) for field in unique_fields)
                else (item,)
            )
            if key not in seen:
                seen.add(key)
                unique_items.append(item)
        items = unique_items

    if config.group_by:
        field = config.group_by
        groups: dict[str, list] = {}
        for item in items:
            raw = item_field_value(item, field)
            key_val = str(raw) if raw is not None else "__none__"
            groups.setdefault(key_val, []).append(item)
        return groups

    if config.offset:
        items = items[config.offset :]
    if config.limit:
        items = items[: config.limit]

    return items

class PipeExecutor(Executor):
    """Execution strategy for pipe runners."""

    async def pre_run(self, runner) -> None:
        raw = await runner._resolve_template(runner.model.pipe.input)
        runner.model.resolved_input = _coerce_to_list(raw)

    async def do_run(self, runner) -> None:
        items = list(runner.model.resolved_input)
        config = runner.model.pipe
        result = _execute_pipeline(items, config)

        flat_items = (
            [item for group in result.values() for item in group]
            if isinstance(result, dict)
            else result
        )
        formatted = _format_items(flat_items, config)
        output_items = result

        from ofx.utils.tempfiles import make_temp_file

        runner._temp_file = make_temp_file(prefix=".pipe_", suffix=f".{config.format}")
        runner._temp_file.write_text(formatted)

        outputs: dict[str, Any] = {
            "items": output_items,
            "count": len(flat_items),
            "data": formatted,
            "file": str(runner._temp_file),
            "stdout": f"pipe: {len(flat_items)} items → {config.format}",
        }
        await runner.reg_set(RunnerRegistryKeys.OUTPUTS, outputs)

    async def on_failure(self, runner) -> None:
        remove_file(runner._temp_file)

__all__ = [
    "PipeExecutor",
    "_coerce_to_list",
    "_execute_pipeline",
    "_format_items",
    "_item_namespace",
    "_safe_eval",
]
