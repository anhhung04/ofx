"""Generate a GitHub Actions or GitLab CI pipeline for secret scanning."""
import pathlib


def run(ctx):
    repo_root = pathlib.Path(str(ctx.inputs.get("repo_root", "")))
    platform = str(ctx.inputs.get("ci_platform", "github"))
    branch = str(ctx.inputs.get("default_branch", "main"))

    if platform == "github":
        ci_dir = repo_root / ".github" / "workflows"
        ci_dir.mkdir(parents=True, exist_ok=True)
        ci_path = ci_dir / "secret-scan.yml"

        ci_content = f"""name: Secret Scan
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
        uses: trufflesecurity/trufflehog-action@v1
        with:
          path: ./
          base: ${{{{ github.event.before }}}}
          head: ${{{{ github.sha }}}}
"""
    else:
        ci_path = repo_root / ".gitlab-ci.yml"
        ci_content = """stages:
  - security-scan

secret-scan:
  stage: security-scan
  image:
    name: zricethezav/gitleaks:latest
    entrypoint: [""]
  script:
    - gitleaks detect --source=. --verbose
  rules:
    - if: $CI_PIPELINE_SOURCE == "push"
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  allow_failure: true

trufflehog-scan:
  stage: security-scan
  image:
    name: trufflesecurity/trufflehog:latest
    entrypoint: [""]
  script:
    - trufflehog git file://. --since-commit HEAD --fail --no-update
  rules:
    - if: $CI_PIPELINE_SOURCE == "push"
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  allow_failure: true
"""

    ci_path.write_text(ci_content)
    ctx.add_outputs(ci_file=str(ci_path), ci_platform=platform)
    print(f"CI pipeline generated: {ci_path}")
    print(f"Platform: {platform}")
