"""Verify VPN connectivity and resolve the external IP when active."""
import subprocess


def run(ctx):
    cmd = r'''VPN_ACTIVE="false" EXTERNAL_IP="" # Check common VPN interfaces for iface in tun0 utun0 ppp0 wg0; do if ip link show "$iface" 2 then VPN_ACTIVE="true" EXTERNAL_IP=$(ip -4 addr show "$iface" | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1) break fi done # Fallback: check via external service if [ "$VPN_ACTIVE" != "true" ]; then EXTERNAL_IP=$(curl -s --max-time 5 https://ifconfig.me'''
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=__import__("sys").stderr)
