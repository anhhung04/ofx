"""ASM (Attack Surface Management) integration module.

Provides functions to interact with the ASM platform from OFX workflows:
- List/query scopes and assets
- Start scans and monitor progress
- Export discovered entities to OFX typed outputs
- Push OFX findings back to ASM

Usage in OFX workflow scripts::

    from ofx.api.asm import ASMClient

    asm = ASMClient("https://asm.example.com", token="your-jwt-token")
    scopes = asm.list_scopes()
    assets = asm.list_assets(scope_id, asset_type="subdomain")
    run_id = asm.start_scan(scope_id, workflow="domain_recon")

    # Behind Cloudflare Access:
    asm = ASMClient(
        "https://asm.example.com",
        token="your-jwt-token",
        custom_headers={
            "CF-Access-Client-Id": "xxx.access",
            "CF-Access-Client-Secret": "yyy",
        },
    )
"""

from __future__ import annotations

from .client import ASMClient

__all__ = ["ASMClient"]
