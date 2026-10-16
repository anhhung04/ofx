"""Reject cloud providers that are not implemented by this workflow."""

from __future__ import annotations

SUPPORTED_PROVIDERS = ("aws",)


def run(ctx):
    provider = str(ctx.inputs.get("provider") or "aws").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise RuntimeError(
            f"unsupported provider {provider!r}: cloud-enum only implements "
            f"{', '.join(SUPPORTED_PROVIDERS)} enumeration"
        )
    print(f"provider {provider} accepted")
    ctx.add_outputs(provider=provider)
