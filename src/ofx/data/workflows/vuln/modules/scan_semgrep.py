"""Run semgrep SAST over the resolved source tree and record the JSON report."""

from __future__ import annotations

import pathlib
import subprocess

_LANGUAGE_INCLUDES = {
    "python": "*.py",
    "javascript": "*.js",
    "typescript": "*.ts",
    "go": "*.go",
    "java": "*.java",
    "ruby": "*.rb",
    "php": "*.php",
    "csharp": "*.cs",
}


def run(ctx):
    source_path = str(ctx.inputs.get("source_path", "")).strip()
    if not source_path:
        raise ValueError("source_path is required (run resolve-source first)")

    run_dir = str(ctx.env.get("OFX_RUN_DIR", "")).strip()
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot write scan results")

    languages = [
        item.strip().lower()
        for item in str(ctx.inputs.get("languages", "")).split(",")
        if item.strip()
    ]
    includes = [_LANGUAGE_INCLUDES[item] for item in languages if item in _LANGUAGE_INCLUDES]
    unsupported = [item for item in languages if item not in _LANGUAGE_INCLUDES]
    if unsupported:
        print(f"Ignoring unsupported language(s): {', '.join(unsupported)}")

    output = pathlib.Path(run_dir) / "semgrep_results.json"
    cmd = ["semgrep", "--config", "auto", "--json", "-o", str(output)]
    for pattern in includes:
        cmd += ["--include", pattern]
    cmd.append(source_path)

    subprocess.run(cmd, capture_output=True, text=True, check=True)
    ctx.add_outputs(results_file=str(output))
    print(f"semgrep report: {output}")
