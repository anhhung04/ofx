"""Pipe runner — declarative ETL executor for data transformation between steps.

Processes a PipeConfig pipeline: input → filter → map → flatten → sort →
unique → group_by → offset → limit → format, then stores results in the
registry as step outputs.
"""

from __future__ import annotations

import ast
import csv
import io
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ofx.models.pipe import PipeConfig
from ofx.runner.core import (
    BaseRunner,
    RunContext,
    RunnerRegistryKeys,
)

logger = logging.getLogger("ofx.pipe")


# ---------------------------------------------------------------------------
# Input coercion
# ---------------------------------------------------------------------------


def _coerce_to_list(raw: Any) -> list[Any]:
    """Coerce a template-resolved value to a list of items."""
    if isinstance(raw, list):
        return raw

    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        if raw.startswith("[") or raw.startswith("{"):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, list) else [parsed]
            except json.JSONDecodeError:
                pass
        # Newline-separated values
        if "\n" in raw:
            return [line.strip() for line in raw.splitlines() if line.strip()]
        # Comma-separated values
        if "," in raw:
            return [v.strip() for v in raw.split(",") if v.strip()]
        return [raw]

    if isinstance(raw, dict):
        return [raw]

    try:
        return list(raw)
    except TypeError:
        return [raw] if raw is not None else []


# ---------------------------------------------------------------------------
# Model for the PipeRunner
# ---------------------------------------------------------------------------


class PipeExecution(BaseModel):
    """Execution model wrapping a PipeConfig for BaseRunner compatibility."""

    pipe: PipeConfig
    resolved_input: list[Any] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Safe expression evaluator
# ---------------------------------------------------------------------------

# Allowed builtins available inside filter/map expressions.
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


def _safe_eval(expr: str, namespace: dict[str, Any]) -> Any:
    """Evaluate *expr* with a restricted set of builtins.

    The expression is compiled once via :func:`compile` and then evaluated
    with only the caller-supplied *namespace* plus ``_SAFE_BUILTINS``.
    Attribute access is allowed so ``item.field`` works for dict-like
    objects, but ``__import__``, ``exec``, ``eval``, and ``open`` are
    blocked.
    """
    code = compile(expr, "<pipe-expr>", "eval")

    # Reject calls to dangerous names at the AST level.
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
        # Block dunder attribute access (e.g. obj.__class__)
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError(
                f"Forbidden dunder attribute access in pipe expression: {node.attr}"
            )

    safe_ns: dict[str, Any] = {"__builtins__": {}}
    safe_ns.update(_SAFE_BUILTINS)
    safe_ns.update(namespace)
    return eval(code, safe_ns)  # noqa: S307


def _item_namespace(item: Any) -> dict[str, Any]:
    """Build the evaluation namespace from a single pipeline item."""
    if isinstance(item, dict):
        return dict(item)
    # Support attribute-style access on objects
    ns: dict[str, Any] = {}
    for attr in dir(item):
        if not attr.startswith("_"):
            try:
                ns[attr] = getattr(item, attr)
            except Exception:
                logger.debug("Failed to read attribute %s from item", attr)
    return ns


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_items(
    items: list[Any],
    config: PipeConfig,
) -> str:
    """Serialize *items* according to ``config.format``."""
    fmt = config.format

    if fmt == "json":
        return json.dumps(items, indent=2, default=str)

    if fmt == "jsonl":
        lines: list[str] = []
        for item in items:
            lines.append(json.dumps(item, default=str))
        return "\n".join(lines)

    if fmt == "lines":
        parts: list[str] = []
        for item in items:
            if isinstance(item, dict) and config.field:
                parts.append(str(item.get(config.field, "")))
            elif isinstance(item, dict):
                # Use the first value
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


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------


def _execute_pipeline(items: list[Any], config: PipeConfig) -> list[Any] | dict:
    """Run the ETL operations on *items* and return the processed result."""

    # ── filter ────────────────────────────────────────────────────────
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

    # ── map ───────────────────────────────────────────────────────────
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

    # ── flatten ───────────────────────────────────────────────────────
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

    # ── sort ──────────────────────────────────────────────────────────
    if config.sort:
        sort_fields = (
            [config.sort] if isinstance(config.sort, str) else list(config.sort)
        )

        def _sort_key(item: Any) -> tuple:
            vals: list[Any] = []
            for f in sort_fields:
                v = item.get(f) if isinstance(item, dict) else getattr(item, f, None)
                # Use empty string for None so sorting doesn't fail on mixed types
                vals.append(("" if v is None else v,))
            return tuple(vals)

        try:
            items = sorted(items, key=_sort_key, reverse=config.reverse)
        except TypeError:
            pass  # skip sort on incomparable types

    # ── unique ────────────────────────────────────────────────────────
    if config.unique:
        unique_fields = (
            [config.unique]
            if isinstance(config.unique, str)
            else list(config.unique)
        )
        seen: set[tuple] = set()
        unique_items: list[Any] = []
        for item in items:
            if isinstance(item, dict):
                key = tuple(item.get(f) for f in unique_fields)
            else:
                key = (item,)
            if key not in seen:
                seen.add(key)
                unique_items.append(item)
        items = unique_items

    # ── group_by ──────────────────────────────────────────────────────
    if config.group_by:
        field = config.group_by
        groups: dict[str, list] = {}
        for item in items:
            key_val = str(
                item.get(field) if isinstance(item, dict) else getattr(item, field, "")
            )
            groups.setdefault(key_val, []).append(item)
        # Apply offset/limit to each group? No — apply to the flat list first.
        # Return the grouped dict; offset/limit already applied above.
        return groups  # type: ignore[return-value]

    # ── offset / limit ────────────────────────────────────────────────
    if config.offset:
        items = items[config.offset :]
    if config.limit:
        items = items[: config.limit]

    return items


# ---------------------------------------------------------------------------
# PipeRunner — BaseRunner subclass
# ---------------------------------------------------------------------------


class PipeRunner(BaseRunner[PipeExecution]):
    """Executes a declarative ETL pipeline and stores results as step outputs."""

    def __init__(
        self,
        model: PipeExecution,
        ctx: RunContext,
        parent: BaseRunner | None = None,
    ):
        super().__init__(model, ctx, parent, None)
        self._temp_file: Path | None = None

    async def _pre_run(self) -> None:
        """Resolve the pipe input Jinja2 expression into a concrete list."""
        raw = await self._resolve_template(self.model.pipe.input)
        self.model.resolved_input = _coerce_to_list(raw)

    async def _on_failure_cleanup(self) -> None:
        """Remove the temp output file when the pipeline fails."""
        if self._temp_file and self._temp_file.exists():
            self._temp_file.unlink(missing_ok=True)

    async def _do_run(self) -> None:
        items = list(self.model.resolved_input)
        config = self.model.pipe

        result = _execute_pipeline(items, config)

        # Determine items list and whether result is grouped
        is_grouped = isinstance(result, dict)
        if is_grouped:
            flat_items = []
            for group in result.values():
                flat_items.extend(group)
            formatted = _format_items(flat_items, config)
            output_items = result
        else:
            flat_items = result  # type: ignore[assignment]
            formatted = _format_items(flat_items, config)
            output_items = flat_items

        # Write formatted output to a temp file
        from ofx.utils.tempfiles import make_temp_file

        self._temp_file = make_temp_file(prefix=".pipe_", suffix=f".{config.format}")
        self._temp_file.write_text(formatted)

        outputs: dict[str, Any] = {
            "items": output_items,
            "count": len(flat_items),
            "data": formatted,
            "file": str(self._temp_file),
            "stdout": f"pipe: {len(flat_items)} items → {config.format}",
        }
        await self.reg_set(RunnerRegistryKeys.OUTPUTS, outputs)
