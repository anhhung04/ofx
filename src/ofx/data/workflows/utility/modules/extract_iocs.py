"""Extract IOCs (IPs, URLs, domains, emails, hashes) from scan results."""

from __future__ import annotations

import ipaddress
import json
import pathlib
import re

_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6_RE = re.compile(r"\b(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}\b")
_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_DOMAIN_RE = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b"
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_HASH_RE = re.compile(r"\b(?:[a-fA-F0-9]{64}|[a-fA-F0-9]{40}|[a-fA-F0-9]{32})\b")

_IOC_FILES = {
    "ips": "ioc_ips.txt",
    "urls": "ioc_urls.txt",
    "domains": "ioc_domains.txt",
    "emails": "ioc_emails.txt",
    "hashes": "ioc_hashes.txt",
}


def _iter_files(target: pathlib.Path) -> list[pathlib.Path]:
    if target.is_dir():
        return sorted(path for path in target.rglob("*") if path.is_file())
    if target.is_file():
        return [target]
    raise FileNotFoundError(f"scan results not found: {target}")


def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError as exc:
        raise RuntimeError(f"failed to read {path}: {exc}") from exc


def _valid_ips(text: str) -> set[str]:
    found: set[str] = set()
    for match in _IPV4_RE.finditer(text):
        try:
            found.add(str(ipaddress.IPv4Address(match.group())))
        except ipaddress.AddressValueError:
            continue
    for match in _IPV6_RE.finditer(text):
        try:
            found.add(str(ipaddress.IPv6Address(match.group())))
        except ipaddress.AddressValueError:
            continue
    return found


def run(ctx):
    target = str(ctx.inputs.get("target", "")).strip()
    if not target:
        raise ValueError("target is required")

    run_dir = str(ctx.env.get("OFX_RUN_DIR", "")).strip()
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot write the IOC files")

    files = _iter_files(pathlib.Path(target).expanduser())
    text = "\n".join(_read(path) for path in files)

    results = {
        "ips": _valid_ips(text),
        "urls": set(_URL_RE.findall(text)),
        "domains": set(_DOMAIN_RE.findall(text)),
        "emails": set(_EMAIL_RE.findall(text)),
        "hashes": set(_HASH_RE.findall(text)),
    }

    paths: dict[str, str] = {}
    counts: dict[str, int] = {}
    for kind, values in results.items():
        output = pathlib.Path(run_dir) / _IOC_FILES[kind]
        output.write_text("\n".join(sorted(values)) + ("\n" if values else ""))
        paths[kind] = str(output)
        counts[kind] = len(values)
        print(f"{kind}: {len(values)} -> {output}")

    ctx.add_outputs(
        files=json.dumps(paths, sort_keys=True),
        counts=json.dumps(counts, sort_keys=True),
        total=str(sum(counts.values())),
    )
    print(f"Scanned {len(files)} file(s); {sum(counts.values())} IOC(s) extracted")
