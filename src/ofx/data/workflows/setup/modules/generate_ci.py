"""Generate a GitHub Actions or GitLab CI pipeline for secret scanning."""

from __future__ import annotations

import pathlib

_GITLAB_CI = """stages:
  - security-scan

variables:
  GIT_DEPTH: '0'

secret-scan:
  stage: security-scan
  image:
    name: zricethezav/gitleaks:latest
    entrypoint: [""]
  script:
    - gitleaks detect --source=. --verbose --redact
  rules:
    - if: $CI_PIPELINE_SOURCE == "push"
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  allow_failure: false

trufflehog-scan:
  stage: security-scan
  image:
    name: trufflesecurity/trufflehog:latest
    entrypoint: [""]
  script:
    - trufflehog git file://. --fail --no-update
  rules:
    - if: $CI_PIPELINE_SOURCE == "push"
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  allow_failure: false
"""


def _github_workflow(branch: str) -> str:
    return f"""name: Secret Scan
on:
  push:
    branches: [{branch}]
  pull_request:
    branches: [{branch}]
  schedule:
    - cron: '0 6 * * 1'  # Weekly Monday 6am

jobs:
  secret-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Gitleaks Scan
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}

      - name: TruffleHog Scan
        uses: trufflesecurity/trufflehog@v3.67.0
        with:
          path: ./
"""


def run(ctx):
    repo_root = pathlib.Path(str(ctx.inputs.get("repo_root", "")).strip() or ".")
    if not repo_root.is_dir():
        raise RuntimeError(f"repository root not found: {repo_root}")

    platform = str(ctx.inputs.get("ci_platform", "github")).strip().lower()
    branch = str(ctx.inputs.get("default_branch", "main")).strip() or "main"

    if platform == "github":
        ci_path = repo_root / ".github" / "workflows" / "secret-scan.yml"
        content = _github_workflow(branch)
    elif platform == "gitlab":
        ci_path = repo_root / ".gitlab-ci.yml"
        content = _GITLAB_CI
    else:
        raise ValueError(f"Unsupported CI platform: {platform}")

    if ci_path.is_file():
        if ci_path.read_text() != content:
            raise RuntimeError(
                "refusing to overwrite existing CI file with different content: "
                f"{ci_path}"
            )
        print(f"CI pipeline already up to date: {ci_path}")
    else:
        ci_path.parent.mkdir(parents=True, exist_ok=True)
        ci_path.write_text(content)
        print(f"CI pipeline generated: {ci_path}")

    ctx.add_outputs(ci_file=str(ci_path), ci_platform=platform)
    print(f"Platform: {platform}")
