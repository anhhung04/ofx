"""Evasion utilities for red team workflows.

Submodules
----------
bypass    -- AMSI/ETW bypass and Defender exclusion snippets
chunking  -- string chunking for payload splitting
encoding  -- XOR, ROT13, and basic transforms
jitter    -- random sleep and jitter helpers
payload   -- language-specific payload obfuscation
"""

from __future__ import annotations

from .bypass import (
    amsi_bypass,
    constrained_language_check,
    defender_exclusion_command,
    disable_defender_realtime,
    etw_bypass,
    scriptblock_logging_disable,
)
from .chunking import chunk_string
from .encoding import rot13, xor_bytes
from .jitter import jitter_delay, sleep_with_jitter
from .payload import obfuscate_cmd, obfuscate_payload

__all__ = [
    "amsi_bypass",
    "etw_bypass",
    "defender_exclusion_command",
    "disable_defender_realtime",
    "scriptblock_logging_disable",
    "constrained_language_check",
    "chunk_string",
    "rot13",
    "xor_bytes",
    "jitter_delay",
    "sleep_with_jitter",
    "obfuscate_payload",
    "obfuscate_cmd",
]
