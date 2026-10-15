"""Translate the ``ports`` input into naabu/rustscan arguments.

The advertised port specs (``top-N``, ``N-M``, ``all``) are not valid
``rustscan --range`` values, and ``top-N`` is not a valid naabu ``-p`` value
either, so the spec is translated once here instead of being passed through
verbatim.
"""

from __future__ import annotations

import re

_TOP_RE = re.compile(r"^top-(\d+)$")
_RANGE_RE = re.compile(r"^(\d+)-(\d+)$")
_PORTS_RE = re.compile(r"^\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$")

MAX_PORT = 65535


def _validate_range(start, end, spec):
    if start < 1 or end > MAX_PORT or start > end:
        raise RuntimeError(f"invalid port range in ports={spec!r} (expected 1-{MAX_PORT})")


def run(ctx):
    spec = str(ctx.inputs.get("ports") or "").strip().lower()
    if not spec:
        raise RuntimeError("ports must not be empty")

    naabu_args = ""
    rustscan_args = ""
    top = _TOP_RE.match(spec)
    port_range = _RANGE_RE.match(spec)
    if top:
        count = int(top.group(1))
        if count < 1 or count > MAX_PORT:
            raise RuntimeError(f"invalid ports={spec!r} (expected top-1..top-{MAX_PORT})")
        naabu_args = f"-top-ports {count}"
    elif port_range:
        start, end = int(port_range.group(1)), int(port_range.group(2))
        _validate_range(start, end, spec)
        naabu_args = f"-p {start}-{end}"
        rustscan_args = f"--range {start}-{end}"
    elif spec in ("all", "-"):
        naabu_args = "-p -"
    elif _PORTS_RE.match(spec):
        for token in spec.split(","):
            parts = _RANGE_RE.match(token)
            if parts:
                _validate_range(int(parts.group(1)), int(parts.group(2)), spec)
        naabu_args = f"-p {spec}"
        rustscan_args = f"-p {spec}"
    else:
        raise RuntimeError(
            f"unsupported ports={spec!r}; use top-N, N-M, a comma separated "
            "list, or 'all'"
        )

    print(f"port spec {spec!r}: naabu {naabu_args or '(default)'}")
    ctx.add_outputs(
        naabu_args=naabu_args,
        rustscan_args=rustscan_args,
        port_spec=spec,
    )
