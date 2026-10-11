"""Print SSH SOCKS and port-forward commands for network pivoting."""


def run(ctx):
    lhost = str(ctx.inputs.get("lhost"))
    lport = str(ctx.inputs.get("lport"))
    pivot = str(ctx.inputs.get("pivot_host") or "")
    target_host = str(ctx.inputs.get("target_host") or "")
    target_port = str(ctx.inputs.get("target_port"))

    print("[+] SSH Dynamic SOCKS Tunnel")
    if pivot:
        print(f"    ssh -D {lport} -N -f user@{pivot}")
        print(f"    Then configure proxychains: socks5 127.0.0.1 {lport}")
    else:
        print(f"    ssh -D {lport} -N -f {lhost}")

    print("\n[+] SSH Remote Port Forward")
    if pivot and target_host:
        print(
            f"    ssh -R {target_port}:{target_host}:{target_port} -N -f user@{pivot}"
        )

    print("\n[+] SSH Local Port Forward")
    if target_host:
        print(
            f"    ssh -L {lport}:{target_host}:{target_port} -N -f user@{pivot or lhost}"
        )

    ctx.add_outputs(method="ssh", socks_port=lport)
