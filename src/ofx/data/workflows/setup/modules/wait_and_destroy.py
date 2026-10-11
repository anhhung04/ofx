"""Wait for the teardown delay, then destroy the lab compose stack."""
import subprocess


def run(ctx):
    teardown_delay = int(ctx.inputs.get("teardown_delay", 3600))
    compose_path = str(ctx.inputs.get("compose_path", ""))
    lab_name = str(ctx.inputs.get("lab_name", "ofx-lab"))
    cmd = f"""echo "[*] Waiting {teardown_delay}s before teardown..." sleep {teardown_delay} cd "$(dirname "{compose_path}")" COMPOSE_CMD="docker compose" if ! docker compose version 2 then COMPOSE_CMD="docker-compose" fi $COMPOSE_CMD -p "{lab_name}" down -v --remove-orphans echo "[+] Lab '{lab_name}' destroyed" """
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=__import__("sys").stderr)
