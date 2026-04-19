"""ASM (Attack Surface Management) integration for OFX.

Provides a client library and CLI commands to interact with an ASM
server — loading scope targets, pushing scan results, and syncing
assets/findings between OFX workflows and the ASM platform.
"""

from ofx.asm.client import ASMClient
from ofx.asm.config import get_asm_client, get_asm_config
from ofx.asm.models import Asset, ExcludeRule, Finding, Scope, Target

__all__ = [
    "ASMClient",
    "Asset",
    "ExcludeRule",
    "Finding",
    "Scope",
    "Target",
    "get_asm_client",
    "get_asm_config",
]
