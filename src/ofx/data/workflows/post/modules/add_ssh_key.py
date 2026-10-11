"""Generate an SSH key pair and instructions for target persistence."""

import os
import subprocess


def run(ctx):
    ssh_dir = os.path.expanduser("~/.ssh")
    os.makedirs(ssh_dir, exist_ok=True)
    key_path = os.path.join(ssh_dir, "id_rsa")
    if not os.path.exists(key_path):
        subprocess.run(
            ["ssh-keygen", "-t", "rsa", "-b", "4096", "-f", key_path, "-N", "", "-q"]
        )

    # Read public key
    with open(key_path + ".pub") as f:
        pubkey = f.read().strip()

    print("Add this key to authorized_keys on target:")
    print(f"echo '{pubkey}' >> ~/.ssh/authorized_keys")
    print(
        f"\nConnect: ssh -i {key_path} {ctx.inputs.get('username')}@{ctx.inputs.get('target')}"
    )
    ctx.add_outputs(ssh_key=key_path, pubkey=pubkey)
