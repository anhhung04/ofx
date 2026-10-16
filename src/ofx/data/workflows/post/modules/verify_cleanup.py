"""Verify that requested OPSEC artifacts were actually cleared.

Replaces the unconditional "cleared" echos: after the best-effort cleanup
steps, this module checks each requested artifact and reports cleared/failed
counts, failing when any requested artifact still exists.
"""

import os

# artifact key -> (path, kind). ``kind`` is 'file' for paths that must be gone
# and 'history' for shell history files that must be empty or absent.
LINUX_ARTIFACTS = {
    "bash_history": (os.path.expanduser("~/.bash_history"), "file"),
    "zsh_history": (os.path.expanduser("~/.zsh_history"), "file"),
    "mysql_history": (os.path.expanduser("~/.mysql_history"), "file"),
    "psql_history": (os.path.expanduser("~/.psql_history"), "file"),
    "python_history": (os.path.expanduser("~/.python_history"), "file"),
    "auth_log": ("/var/log/auth.log", "size"),
    "secure_log": ("/var/log/secure", "size"),
    "syslog": ("/var/log/syslog", "size"),
    "messages_log": ("/var/log/messages", "size"),
    "kern_log": ("/var/log/kern.log", "size"),
    "ssh_known_hosts": (os.path.expanduser("~/.ssh/known_hosts"), "file"),
}

AGGRESSIVE_ARTIFACTS = {
    "wtmp": ("/var/log/wtmp", "size"),
    "btmp": ("/var/log/btmp", "size"),
    "lastlog": ("/var/log/lastlog", "size"),
    "utmp": ("/run/utmp", "size"),
}

WINDOWS_ARTIFACTS = {
    "ps_history": (
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\PowerShell\PSReadLine"
                           r"\ConsoleHost_history.txt"),
        "file",
    ),
    "temp_dir": (os.environ.get("TEMP") or os.environ.get("TMP") or "", "dir_empty"),
}


def _check(path: str, kind: str) -> bool:
    """Return True when the artifact is considered cleared."""
    if not path:
        return True
    if kind == "file":
        return not os.path.exists(path)
    if kind == "size":
        if not os.path.exists(path):
            return True
        try:
            return os.path.getsize(path) == 0
        except OSError:
            return False
    if kind == "dir_empty":
        if not os.path.isdir(path):
            return True
        try:
            return not any(os.scandir(path))
        except OSError:
            return False
    return False


def run(ctx):
    os_type = str(ctx.inputs.get("os_type") or "linux").strip().lower()
    aggressive = bool(ctx.inputs.get("aggressive"))

    if os_type == "windows":
        artifacts = dict(WINDOWS_ARTIFACTS)
    elif os_type == "linux":
        artifacts = dict(LINUX_ARTIFACTS)
        if aggressive:
            artifacts.update(AGGRESSIVE_ARTIFACTS)
    else:
        raise ValueError(f"Unsupported os_type: '{os_type}' (expected linux or windows)")

    cleared: list[str] = []
    failed: list[str] = []
    for key, (path, kind) in artifacts.items():
        if _check(path, kind):
            cleared.append(key)
        else:
            failed.append(f"{key} ({path})")

    print(f"[+] Cleanup verification ({os_type}): {len(cleared)} cleared")
    for key in cleared:
        print(f"    [ok] {key}")
    for entry in failed:
        print(f"    [failed] {entry}")

    ctx.add_outputs(
        os_type=os_type,
        cleared=cleared,
        failed=failed,
        cleared_count=len(cleared),
        failed_count=len(failed),
    )

    if failed:
        raise RuntimeError(
            f"{len(failed)} requested artifact(s) still present after cleanup: "
            + "; ".join(failed)
        )
