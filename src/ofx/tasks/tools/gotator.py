"""gotator — subdomain permutation generator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Subdomain
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("gotator")
class GotatorTask(Task):
    name = "gotator"
    cmd = "gotator"
    description = "Subdomain permutation generator"
    category = "dns/permute"
    install_cmd = "GOBIN=~/Tools/bin go install -v github.com/Josue87/gotator@latest"
    output_types = [Subdomain]

    opts = {
        "perm": OptDef(flag="-perm", type=str, help="Permutation wordlist path"),
        "depth": OptDef(flag="-depth", type=int, help="Permutation depth"),
        "numbers": OptDef(flag="-numbers", type=int, help="Number suffix range"),
        "fast": OptDef(flag="-fast", is_flag=True, help="Fast mode"),
        "silent": OptDef(flag="-silent", is_flag=True, help="Silent mode"),
    }

    input_flag = "-sub"
    file_flag = "-sub"
    output_flag = None
    extra_flags = ["-depth", "1", "-numbers", "3", "-mindup", "-adv", "-md"]
    export_output = False

    def _output_suffix(self) -> str:
        return ".txt"

    def build_command(self, target: str, **kwargs: Any) -> tuple[str, Path | None]:
        """Gotator always requires a file via ``-sub``.

        If *target* is an existing file, pass it with ``-sub``.
        Otherwise skip the flag (the user should provide a file).
        """
        parts: list[str] = [self.cmd]

        # Collect extra_flags but allow kwargs to override depth/numbers
        depth_override = kwargs.get("depth")
        numbers_override = kwargs.get("numbers")

        extra = list(self.extra_flags)
        if depth_override is not None:
            idx = extra.index("-depth") if "-depth" in extra else -1
            if idx >= 0:
                extra[idx + 1] = str(depth_override)
        if numbers_override is not None:
            idx = extra.index("-numbers") if "-numbers" in extra else -1
            if idx >= 0:
                extra[idx + 1] = str(numbers_override)
        parts.extend(extra)

        for key, value in kwargs.items():
            if key.startswith("_") or key in ("depth", "numbers"):
                continue
            opt = self.opts.get(key)
            if opt is None:
                continue
            if opt.is_flag:
                if value:
                    parts.append(opt.flag)
            elif value is not None:
                parts.extend([opt.flag, str(value)])

        if target and Path(target).is_file():
            parts.extend(["-sub", target])
        elif target:
            parts.extend(["-sub", target])

        output_file = self._make_output_path()
        return f"{' '.join(parts)} > {output_file}", output_file

    def parse_line(self, line: str) -> list[Subdomain]:
        host = line.strip()
        if not host or host.startswith("#"):
            return []

        domain = ".".join(host.rsplit(".", 2)[-2:]) if "." in host else host
        return [Subdomain(host=host, domain=domain)]

