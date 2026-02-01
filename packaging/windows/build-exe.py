#!/usr/bin/env python3
"""Build Windows executable for OFX using PyInstaller.

This script creates standalone Windows executables for both x64 and arm64.

Usage:
    python packaging/windows/build-exe.py          # Build for current arch
    python packaging/windows/build-exe.py --all    # Build for all archs
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path


def get_version() -> str:
    """Extract version from pyproject.toml."""
    pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
    for line in pyproject.read_text().splitlines():
        if line.startswith("version = "):
            return line.split('"')[1]
    return "0.0.0"


def build_exe(arch: str | None = None) -> Path:
    """Build Windows executable using PyInstaller.
    
    Args:
        arch: Target architecture (x64, arm64, or None for current)
        
    Returns:
        Path to built executable
    """
    version = get_version()
    current_arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    target_arch = arch or current_arch
    
    output_name = f"ofx-{version}-windows-{target_arch}"
    
    print(f"Building OFX v{version} for Windows {target_arch}...")
    
    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", output_name,
        "--console",
        "--clean",
        "--noconfirm",
        # Add hidden imports for dynamic modules
        "--hidden-import", "ofx.api.post.runners",
        "--hidden-import", "ofx.api.post.runners.ssh",
        "--hidden-import", "ofx.api.post.runners.webshell",
        "--hidden-import", "ofx.api.post.runners.winrm",
        "--hidden-import", "ofx.api.post.runners.smbexec",
        "--hidden-import", "ofx.api.post.runners.wmiexec",
        "--hidden-import", "ofx.commands",
        # Main entry
        "src/ofx/__init__.py",
    ]
    
    subprocess.run(cmd, check=True)
    
    output_path = Path("dist") / f"{output_name}.exe"
    print(f"Built: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Build Windows executable for OFX")
    parser.add_argument("--all", action="store_true", help="Build for all architectures")
    parser.add_argument("--arch", choices=["x64", "arm64"], help="Target architecture")
    args = parser.parse_args()
    
    if args.all:
        # Note: Cross-compilation requires wine or actual ARM64 Windows
        print("Building for current architecture only.")
        print("For cross-compilation, use GitHub Actions with matrix builds.")
        build_exe()
    elif args.arch:
        build_exe(args.arch)
    else:
        build_exe()


if __name__ == "__main__":
    main()
