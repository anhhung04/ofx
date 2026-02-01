#!/bin/bash
#
# Build OFX Debian package
#
# Usage: ./scripts/build-deb.sh
#
# Requirements (install on Debian/Ubuntu):
#   sudo apt-get install build-essential devscripts debhelper dh-python pybuild-plugin-pyproject python3-all python3-pip python3-build
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Extract version from pyproject.toml
VERSION=$(grep '^version = ' pyproject.toml | head -1 | cut -d'"' -f2)
echo "=========================================="
echo "Building OFX v${VERSION} Debian package"
echo "=========================================="

# Check for required tools
check_cmd() {
    if ! command -v "$1" &> /dev/null; then
        echo "Error: $1 is not installed."
        echo "Install with: sudo apt-get install $2"
        exit 1
    fi
}

check_cmd dpkg-buildpackage devscripts
check_cmd dh debhelper
check_cmd python3 python3

# Create symlink for debian directory (dpkg-buildpackage expects it in root)
if [ ! -L "debian" ] && [ ! -d "debian" ]; then
    ln -s packaging/debian debian
fi

# Ensure debian/rules is executable
chmod +x packaging/debian/rules

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf packaging/debian/.debhelper packaging/debian/ofx packaging/debian/files packaging/debian/*.debhelper* packaging/debian/*.substvars
rm -f ../ofx_*.deb ../ofx_*.changes ../ofx_*.buildinfo 2>/dev/null || true

# Build the package
echo "Building package..."
dpkg-buildpackage -us -uc -b

# Remove symlink
rm -f debian 2>/dev/null || true

# Move built package to project directory
echo ""
echo "=========================================="
echo "Build complete!"
echo "=========================================="
echo ""
echo "Package location:"
ls -la ../ofx_*.deb 2>/dev/null || echo "  (check parent directory)"
echo ""
echo "To install:"
echo "  sudo dpkg -i ../ofx_${VERSION}-1_all.deb"
echo "  sudo apt-get install -f  # Fix any missing dependencies"
echo ""
echo "To verify installation:"
echo "  ofx --version"
echo "  ofx --help"
