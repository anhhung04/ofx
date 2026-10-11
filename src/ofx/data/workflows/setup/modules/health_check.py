"""Check container health statuses for the running lab."""
import subprocess


def run(ctx):
    lab_name = str(ctx.inputs.get("lab_name", "ofx-lab"))
    cmd = f"""HEALTHY=0 FAILED=0 for c in $(docker ps --filter "name={lab_name}" --format '{{{{.Names}}}}'); do STATE=$(docker inspect -f '{{{{.State.Health.Status}}}}' "$c" """
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=__import__("sys").stderr)
