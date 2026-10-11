"""Check Docker Compose availability and report its version."""
import subprocess


def run(ctx):
    cmd = 'COMPOSE_VERSION="" if docker compose version 2 then COMPOSE_VERSION=$(docker compose version --short'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=__import__("sys").stderr)
