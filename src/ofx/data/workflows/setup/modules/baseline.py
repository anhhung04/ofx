"""Run a baseline gitleaks secret scan and write the JSON report."""
import subprocess


def run(ctx):
    repo = str(ctx.inputs.get("repo_root", ""))
    cmd = f"""REPO="{repo}" BASELINE="$REPO/.gitleaks-baseline.json" BASELINE_CSV="$REPO/.gitleaks-baseline.csv" echo "[*] Running baseline gitleaks scan..." gitleaks detect \\ --source="$REPO" \\ --verbose \\ --report-format=json \\ --report-path="$BASELINE" || true FINDINGS=$(python3 -c "import json; d=json.load(open('$BASELINE')); print(len(d))" """
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=__import__("sys").stderr)
