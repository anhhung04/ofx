"""Start an SSH dynamic SOCKS5 tunnel to the configured jump host."""
import subprocess


def run(ctx):
    ssh_host = str(ctx.inputs.get("ssh_host", ""))
    ssh_port = str(ctx.inputs.get("ssh_port", "22"))
    ssh_user = str(ctx.inputs.get("ssh_user", "root"))
    cmd = f"""SSH_HOST="{ssh_host}" SSH_PORT="{ssh_port}" SSH_USER="{ssh_user}" LOCAL_PORT=1080 echo "[*] Establishing SSH dynamic tunnel to $SSH_USER@$SSH_HOST:$SSH_PORT" ssh -f -N -D $LOCAL_PORT \\ -p "$SSH_PORT" \\ -o StrictHostKeyChecking=accept-new \\ -o ServerAliveInterval=60 \\ "$SSH_USER@$SSH_HOST" TUNNEL_PID=$(pgrep -f "ssh.*-D $LOCAL_PORT" | head -1) if [ -n "$TUNNEL_PID" ]; then echo "tunnel_pid=$TUNNEL_PID" echo "local_port=$LOCAL_PORT" echo "[+] SSH tunnel active: SOCKS5 on localhost:$LOCAL_PORT (PID: $TUNNEL_PID)" else echo "[!] Failed to establish SSH tunnel" fi"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=__import__("sys").stderr)
