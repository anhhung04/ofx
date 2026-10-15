"""Generate a run-scoped SSH key pair for target persistence (manual install).

The previous implementation wrote to the operator's ``~/.ssh/id_rsa`` — erasing
a personal key would be unacceptable. Keys are now generated under
``OFX_RUN_DIR`` with 0600 permissions and only the public key plus install
instructions are published; nothing on the local host is overwritten.
"""

import os
import stat
import subprocess

KEY_NAME = "ofx_persistence_key"


def _run_dir(ctx) -> str:
    run_dir = os.environ.get("OFX_RUN_DIR") or str(ctx.env.get("OFX_RUN_DIR") or "")
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot write the persistence key")
    return run_dir


def run(ctx):
    username = str(ctx.inputs.get("username") or "").strip()
    if not username:
        raise ValueError("'username' is required")
    target = str(ctx.inputs.get("target") or "").strip()
    if not target:
        raise ValueError("'target' is required")

    run_dir = _run_dir(ctx)
    key_path = os.path.join(run_dir, KEY_NAME)
    if not os.path.isfile(key_path):
        subprocess.run(  # noqa: S603
            [
                "ssh-keygen",
                "-t",
                "ed25519",
                "-f",
                key_path,
                "-N",
                "",
                "-C",
                f"ofx-persistence-{target}",
                "-q",
            ],
            check=True,
        )
    os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)

    pub_path = key_path + ".pub"
    if not os.path.isfile(pub_path):
        raise RuntimeError(f"Public key was not generated: {pub_path}")
    with open(pub_path, encoding="utf-8") as handle:
        pubkey = handle.read().strip()

    instructions = os.path.join(run_dir, "ssh_key_persistence.txt")
    with open(instructions, "w", encoding="utf-8") as handle:
        handle.write("# SSH key persistence — MANUAL INSTALL REQUIRED\n")
        handle.write(f"# target: {username}@{target}\n\n")
        handle.write("# 1. Append the public key on the target:\n")
        handle.write(f"echo '{pubkey}' >> ~/.ssh/authorized_keys\n")
        handle.write("chmod 600 ~/.ssh/authorized_keys\n\n")
        handle.write("# 2. Connect (the private key stays on this host):\n")
        handle.write(f"ssh -i {key_path} {username}@{target}\n")

    print(f"[+] Public key: {pub_path}")
    print(f"[+] Install instructions: {instructions}")
    print("[!] No persistence is established by this workflow; install manually")
    ctx.add_outputs(
        ssh_key=key_path,
        pubkey=pubkey,
        pubkey_file=pub_path,
        instructions_file=instructions,
        username=username,
        target=target,
    )
