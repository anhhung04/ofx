"""Launch the Docker Compose lab and count running containers."""
import os
import subprocess


def run(ctx):
    compose_path = str(ctx.inputs.get("compose_path", ""))
    compose_dir = os.path.dirname(compose_path)
    lab_name = str(ctx.inputs.get("lab_name", "ofx-lab"))
    cmd = f"""set -euo pipefail cd "{compose_dir}" COMPOSE_CMD="docker compose" if ! docker compose version 2 then COMPOSE_CMD="docker-compose" fi echo "[*] Pulling images..." $COMPOSE_CMD pull -q || true echo "[*] Starting lab..." $COMPOSE_CMD -p "{lab_name}" up -d --wait --wait-timeout 120 2 RUNNING=$(docker ps --filter "name={lab_name}" --format '{{{{.Names}}}}' | wc -l) echo "containers=$RUNNING" echo "Running containers: $RUNNING" """
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=__import__("sys").stderr)
