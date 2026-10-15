"""Split targets into clean and WAF/CDN-protected lists.

Fails closed: when a required detector produced no results the clean list is
deliberately left empty and ``detection_available`` is reported as ``false``,
so callers never mistake "could not check" for "not protected".
"""

from __future__ import annotations

import json
import os
import re

_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


def _artifact_dir(ctx):
    """Return the directory holding this workflow's artifacts."""
    explicit = str(ctx.inputs.get("output_dir") or "").strip()
    run_dir = (
        explicit
        or os.environ.get("OFX_RUN_DIR")
        or str(ctx.env.get("OFX_RUN_DIR") or "")
    )
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot locate run artifacts")
    return run_dir


def _canonical_keys(value):
    """Return comparable host keys for a bare host, host:port or URL.

    cdncheck echoes the input verbatim while wafw00f normalizes bare hosts to
    ``https://<host>``; comparing canonical hosts avoids classifying a detected
    target as clean just because the two tools spell it differently.
    """
    text = str(value or "").strip().lower()
    if not text:
        return set()
    text = _SCHEME_RE.sub("", text)
    text = text.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if "@" in text:
        text = text.rsplit("@", 1)[1]
    text = text.strip().rstrip(".")
    if not text:
        return set()
    keys = {text}
    host, sep, port = text.rpartition(":")
    if sep and host and port.isdigit():
        keys.add(host)
    return keys


def _record(protected, value, provider):
    for key in _canonical_keys(value):
        protected.setdefault(key, set()).add(provider)


def _load_cdncheck(rd, protected, detector_errors):
    path = os.path.join(rd, "cdncheck_results.txt")
    try:
        with open(path) as fh:
            lines = [line.strip() for line in fh]
    except FileNotFoundError:
        detector_errors.append("cdncheck produced no results")
        return
    for line in lines:
        if not line:
            continue
        # cdncheck output lines: <target> [provider,...]
        host, _, rest = line.partition(" ")
        providers = re.findall(r"[a-zA-Z0-9&]+", rest) or ["cdn/waf"]
        for provider in providers:
            _record(protected, host, provider)


def _load_wafw00f(rd, protected, detector_errors):
    path = os.path.join(rd, "wafw00f_results.json")
    try:
        with open(path) as fh:
            entries = json.load(fh)
    except FileNotFoundError:
        detector_errors.append("wafw00f produced no results")
        return
    except json.JSONDecodeError:
        detector_errors.append("wafw00f produced malformed JSON")
        return
    for entry in entries:
        url = entry.get("url") or entry.get("URL") or ""
        waf = entry.get("firewall") or ""
        if url and waf and str(waf).lower() not in ("none", "generic", ""):
            _record(protected, url, str(waf))


def run(ctx):
    rd = _artifact_dir(ctx)
    input_file = os.path.join(rd, "waf_input.txt")
    try:
        with open(input_file) as fh:
            targets = [line.strip() for line in fh if line.strip()]
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"waf-detect: {input_file} is missing; run the normalize step first"
        ) from exc

    protected = {}
    detector_errors = []
    _load_cdncheck(rd, protected, detector_errors)
    _load_wafw00f(rd, protected, detector_errors)

    waf_hosts, cdn_hosts, clean = [], [], []
    detection_available = not detector_errors
    for target in targets:
        keys = _canonical_keys(target)
        providers = sorted(
            {provider for key in keys for provider in protected.get(key, ())}
        )
        if not providers:
            clean.append(target)
            continue
        print(f"protected: {target} ({', '.join(providers)})")
        waf_hosts.append(target)
    if not detection_available:
        # Fail closed: unverified targets are not safe to scan aggressively.
        clean = []
        print(
            "WAF/CDN detection unavailable — treating no target as clean: "
            + "; ".join(detector_errors)
        )

    for name, items in (
        ("targets_waf.txt", waf_hosts),
        ("targets_cdn.txt", cdn_hosts),
        ("targets_clean.txt", clean),
    ):
        with open(os.path.join(rd, name), "w") as fh:
            if items:
                fh.write("\n".join(items) + "\n")

    print(f"clean: {len(clean)}, protected: {len(waf_hosts)}")
    if not clean and detection_available:
        print("all targets are WAF/CDN protected — aggressive scanning skipped")
    ctx.add_outputs(
        clean_targets=os.path.join(rd, "targets_clean.txt"),
        clean_count=len(clean),
        waf_count=len(waf_hosts),
        cdn_count=len(cdn_hosts),
        detection_available="true" if detection_available else "false",
        detector_errors="; ".join(detector_errors),
    )
