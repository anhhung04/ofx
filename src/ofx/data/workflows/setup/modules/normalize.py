"""Normalize cloud provisioning inputs (provider + instance name)."""


def run(ctx):
    provider = str(ctx.inputs.get("provider", "aws")).strip().lower()
    if provider in {"do", "digitalocean", "digital-ocean"}:
        provider = "digitalocean"
    elif provider != "aws":
        raise RuntimeError(f"Unsupported provider: {provider}")

    name = str(ctx.inputs.get("target", "")).strip() or "ofx-attack-infra"
    ctx.add_outputs(provider=provider, instance_name=name)
    print(f"Provider: {provider}")
    print(f"Instance name: {name}")
