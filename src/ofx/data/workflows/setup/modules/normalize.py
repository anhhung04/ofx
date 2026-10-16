"""Normalize cloud provisioning inputs (provider, region, instance name)."""

from __future__ import annotations

import re

AWS_DEFAULT_REGION = "us-east-1"
DO_DEFAULT_REGION = "nyc3"

_DO_REGIONS = frozenset(
    {
        "nyc1",
        "nyc2",
        "nyc3",
        "sfo2",
        "sfo3",
        "ams3",
        "sgp1",
        "lon1",
        "fra1",
        "tor1",
        "blr1",
        "syd1",
    }
)
_AWS_REGION_RE = re.compile(r"^[a-z]{2}(-[a-z]+)+-\d$")


def run(ctx):
    provider = str(ctx.inputs.get("provider", "aws")).strip().lower()
    if provider in {"do", "digitalocean", "digital-ocean"}:
        provider = "digitalocean"
    elif provider != "aws":
        raise RuntimeError(f"Unsupported provider: {provider}")

    name = str(ctx.inputs.get("target", "")).strip() or "ofx-attack-infra"
    region = str(ctx.inputs.get("region", "")).strip().lower()

    if provider == "digitalocean":
        if not region or region == AWS_DEFAULT_REGION:
            region = DO_DEFAULT_REGION
        elif _AWS_REGION_RE.match(region):
            raise RuntimeError(
                f"Region '{region}' is an AWS region; use a DigitalOcean region "
                f"(e.g. {DO_DEFAULT_REGION}) or leave region unset"
            )
    else:
        if region in _DO_REGIONS:
            raise RuntimeError(
                f"Region '{region}' is a DigitalOcean region; use an AWS region "
                f"(e.g. {AWS_DEFAULT_REGION}) or leave region unset"
            )
        if not region:
            region = AWS_DEFAULT_REGION

    ctx.add_outputs(provider=provider, instance_name=name, region=region)
    print(f"Provider: {provider}")
    print(f"Instance name: {name}")
    print(f"Region: {region}")
