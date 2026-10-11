"""Print TOR SOCKS endpoint information and a test command."""


def run(ctx):
    socks_addr = str(ctx.inputs.get("tor_socks", ""))
    if not socks_addr:
        print("TOR SOCKS address not available")
    else:
        host, port = socks_addr.split(":")
        print(f"TOR endpoint: {host}:{port}")
        print(
            "Test with: curl --socks5-hostname {host}:{port} https://check.torproject.org/api/ip"
        )
