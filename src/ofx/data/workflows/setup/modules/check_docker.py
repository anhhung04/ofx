"""Check whether Docker is installed and report its version."""
import subprocess


def run(ctx):
    cmd = 'if ! command -v docker 2 then echo "ERROR: Docker is not installed" exit 1 fi DOCKER_VERSION=$(docker --version | head -1) echo "docker_version=$DOCKER_VERSION" echo "Docker: $DOCKER_VERSION"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=__import__("sys").stderr)
