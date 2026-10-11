"""Builtin ``merge_lists`` module: merge line-based artifacts into one list.

Replaces the per-workflow merge modules (``merge_brute``, ``merge_js``,
``merge_subdomain_lists``, ``merge_subdomains``, ``merge_urls``,
``merge_hosts``) with a single implementation: read every input file, drop
blank lines, de-duplicate, and write one output file.

An empty result must never be mistaken for "the producers found nothing", so
missing inputs are reported as failures unless ``fail_if`` says otherwise.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

NO_RUN_DIR_MESSAGE = "OFX_RUN_DIR is not set; cannot locate run artifacts"


def _arg(ctx, key):
    """Return a module argument from ``ctx.args`` (falling back to ``ctx.inputs``)."""
    if key in ctx.args:
        return ctx.args[key]
    return ctx.inputs.get(key)


def _text_arg(ctx, key):
    """Return a module argument as a stripped string (``""`` when unset)."""
    value = _arg(ctx, key)
    return "" if value is None else str(value).strip()


def _run_dir(ctx, override=""):
    """Return the artifact directory: explicit override, then ``OFX_RUN_DIR``."""
    candidate = (
        override
        or str(ctx.env.get("OFX_RUN_DIR") or "")
        or os.environ.get("OFX_RUN_DIR", "")
    )
    if not candidate:
        raise RuntimeError(NO_RUN_DIR_MESSAGE)
    return Path(candidate).expanduser()



name = "merge_lists"
description = "Merge line-based artifact files into one de-duplicated list file."
args_schema: dict[str, Any] = {
    "files": {
        "type": "array",
        "items": {"type": "string"},
        "description": (
            "Artifact files to merge (list, or a comma-separated string); "
            "relative paths resolve against output_dir/OFX_RUN_DIR"
        ),
        "required": True,
    },
    "output": {
        "type": "string",
        "description": "Output file name or path (relative paths land under output_dir)",
        "required": True,
    },
    "output_dir": {
        "type": "string",
        "description": "Directory holding the input artifacts and the output",
    },
    "fail_if": {
        "type": "string",
        "enum": ["all_missing", "any_missing", "never"],
        "description": "all_missing (default), any_missing, or never",
    },
    "sort": {
        "type": "boolean",
        "description": "Sort the merged lines (default true); false keeps first-seen order",
    },
    "required": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Subset of files that must exist; missing optional files are skipped",
    },
}

_FAIL_IF_MODES = ("all_missing", "any_missing", "never")


def _path_list(ctx, key: str) -> list[str]:
    """Return the ``files``/``required`` argument as a list of strings.

    Accepts a list or a comma-separated string (the form used in workflow
    ``with:`` blocks when a single scalar is more convenient).
    """
    value = _arg(ctx, key)
    if value is None or value == "":
        return []
    raw = value.split(",") if isinstance(value, str) else list(value)
    paths: list[str] = []
    for item in raw:
        text = str(item).strip()
        if text:
            paths.append(text)
    return paths


def _sort_enabled(ctx) -> bool:
    value = _arg(ctx, "sort")
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "off", "")
    return bool(value)


def _fail_if(ctx) -> str:
    mode = _text_arg(ctx, "fail_if").lower() or "all_missing"
    if mode not in _FAIL_IF_MODES:
        raise ValueError(
            f"unsupported fail_if {mode!r}; supported values: "
            + ", ".join(_FAIL_IF_MODES)
        )
    return mode


def _resolve_source(src: str, run_dir: Path) -> Path:
    path = Path(src).expanduser()
    return path if path.is_absolute() else run_dir / path


def _maybe_run_dir(ctx, override: str, paths: list[str]) -> Path:
    """Resolve the run dir only when a relative path actually needs it."""
    if all(Path(p).expanduser().is_absolute() for p in paths):
        return Path("/")
    return _run_dir(ctx, override)


def _ordered(lines: list[str], *, sort: bool) -> list[str]:
    if sort:
        return sorted(set(lines))
    seen: dict[str, None] = dict.fromkeys(lines)
    return list(seen)


def run(ctx):
    """Merge the configured files into a single de-duplicated output file."""
    files = _path_list(ctx, "files")
    if not files:
        raise ValueError(
            "merge_lists requires 'files' (one or more artifact paths; "
            "paths that template to empty are ignored)"
        )
    output = _text_arg(ctx, "output")
    if not output:
        raise ValueError("merge_lists requires 'output' (the merged file name)")

    fail_if = _fail_if(ctx)
    sort = _sort_enabled(ctx)
    out_dir = _maybe_run_dir(ctx, _text_arg(ctx, "output_dir"), [*files, output])
    required = {str(path).strip() for path in _path_list(ctx, "required")}

    lines: list[str] = []
    missing: list[str] = []
    present = 0
    for src in files:
        path = _resolve_source(src, out_dir)
        try:
            content = path.read_text()
        except OSError:
            content = None
        if content is None:
            missing.append(src)
            print(f"{src}: missing")
            continue
        found = [line.strip() for line in content.splitlines() if line.strip()]
        lines.extend(found)
        present += 1
        print(f"{src}: {len(found)} entries")

    absent_required = sorted(required.intersection(missing))
    if absent_required:
        raise RuntimeError(
            "required merge input(s) missing: " + ", ".join(absent_required)
        )
    if fail_if == "any_missing" and missing:
        raise RuntimeError(
            "merge input(s) missing: " + ", ".join(missing) + " (fail_if=any_missing)"
        )
    if fail_if == "all_missing" and present == 0:
        raise RuntimeError(
            "no merge inputs available: none of the configured files were "
            "readable (" + ", ".join(files) + ")"
        )

    merged = _ordered(lines, sort=sort)
    out_path = _resolve_source(output, out_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as handle:
        if merged:
            handle.write("\n".join(merged) + "\n")

    print(f"merged {len(merged)} unique entries -> {out_path}")
    ctx.add_outputs(output_file=str(out_path), count=len(merged))
    return None


__all__ = ["args_schema", "description", "name", "run"]
