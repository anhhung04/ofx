"""Split targets into clean and WAF/CDN-protected lists."""

from __future__ import annotations

import json
import os
import re


def run(ctx):
    rd = ctx.env.get("OFX_RUN_DIR", "")

    targets = open(os.path.join(rd, "waf_input.txt")).read().splitlines()
    protected = {}

    # cdncheck output lines: <target> [provider,...]
    try:
        for line in open(os.path.join(rd, "cdncheck_results.txt")):
            line = line.strip()
            if not line:
                continue
            host, _, rest = line.partition(" ")
            providers = re.findall(r"[a-zA-Z0-9&]+", rest)
            protected.setdefault(host, set()).update(providers or {"cdn/waf"})
    except FileNotFoundError:
        pass

    try:
        for entry in json.load(open(os.path.join(rd, "wafw00f_results.json"))):
            url = entry.get("url") or entry.get("URL") or ""
            waf = entry.get("firewall") or ""
            if url and waf and waf.lower() not in ("none", "generic", ""):
                protected.setdefault(url, set()).add(waf)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    waf_hosts, cdn_hosts, clean = [], [], []
    for t in targets:
        if t in protected:
            providers = sorted(protected[t])
            print(f"protected: {t} ({', '.join(providers)})")
            waf_hosts.append(t)
        else:
            clean.append(t)

    for name, items in (
        ("targets_waf.txt", waf_hosts),
        ("targets_cdn.txt", cdn_hosts),
        ("targets_clean.txt", clean),
    ):
        with open(os.path.join(rd, name), "w") as fh:
            fh.write("\n".join(items))

    print(f"clean: {len(clean)}, protected: {len(waf_hosts)}")
    if not clean:
        print("all targets are WAF/CDN protected — aggressive scanning skipped")
    ctx.add_outputs(
        clean_targets=os.path.join(rd, "targets_clean.txt"),
        clean_count=len(clean),
        waf_count=len(waf_hosts),
        cdn_count=len(cdn_hosts),
    )
