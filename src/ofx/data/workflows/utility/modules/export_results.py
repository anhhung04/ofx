"""Export the files of a results directory to a markdown/JSON/CSV report."""

from __future__ import annotations

import csv
import datetime
import io
import json
import pathlib

_FORMATS = ("markdown", "json", "csv")
_REPORT_NAMES = frozenset(f"report.{ext}" for ext in ("md", "json", "csv"))


def _collect(source: pathlib.Path, output_dir: pathlib.Path) -> list[dict]:
    """Return one row per file under *source*, excluding generated reports."""
    rows: list[dict] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        if path.parent == output_dir and path.name in _REPORT_NAMES:
            continue
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise RuntimeError(f"failed to stat {path}: {exc}") from exc
        rows.append({"path": str(path), "name": path.name, "size_bytes": size})
    return rows


def _markdown(target: str, rows: list[dict], generated_at: str) -> str:
    lines = [
        "# Scan Results Report",
        "",
        f"Target: {target}",
        f"Generated: {generated_at}",
        f"Files: {len(rows)}",
        "",
        "| File | Size (bytes) |",
        "| --- | --- |",
    ]
    lines += [f"| {row['path']} | {row['size_bytes']} |" for row in rows]
    return "\n".join(lines) + "\n"


def _csv(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["path", "size_bytes"])
    writer.writeheader()
    for row in rows:
        writer.writerow({"path": row["path"], "size_bytes": row["size_bytes"]})
    return buffer.getvalue()


def run(ctx):
    target = str(ctx.inputs.get("target", "")).strip()
    if not target:
        raise ValueError("target is required")

    fmt = str(ctx.inputs.get("format", "markdown")).strip().lower()
    if fmt not in _FORMATS:
        raise ValueError(
            f"unsupported format {fmt!r}; supported values: {', '.join(_FORMATS)}"
        )

    run_dir = str(ctx.env.get("OFX_RUN_DIR", "")).strip()
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot write the report")

    source = pathlib.Path(target).expanduser()
    if not source.is_dir():
        raise FileNotFoundError(f"results directory not found: {source}")

    output_dir = pathlib.Path(run_dir)
    rows = _collect(source, output_dir)
    generated_at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    if fmt == "markdown":
        report_path = output_dir / "report.md"
        content = _markdown(target, rows, generated_at)
    elif fmt == "json":
        report_path = output_dir / "report.json"
        content = json.dumps(
            {
                "target": target,
                "generated_at": generated_at,
                "file_count": len(rows),
                "files": rows,
            },
            indent=2,
        )
    else:
        report_path = output_dir / "report.csv"
        content = _csv(rows)

    report_path.write_text(content)
    ctx.add_outputs(report_path=str(report_path), file_count=str(len(rows)))
    print(f"Report ({fmt}): {report_path}")
    print(f"Files exported: {len(rows)}")
