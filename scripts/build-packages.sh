#!/bin/bash
#
# Build OFX Linux packages (deb, rpm, wheel) using Docker
#
# Usage:
#   ./scripts/build-packages.sh              # Build for current arch
#   ./scripts/build-packages.sh --multiarch  # Build for amd64 and arm64
#
# Note: Windows executable must be built on Windows using:
#   scripts\build-windows.bat
#   or: make pkg-windows
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Extract version from pyproject.toml
VERSION=$(grep '^version = ' pyproject.toml | head -1 | cut -d'"' -f2)

echo "=========================================="
echo "Building OFX v${VERSION} packages"
echo "=========================================="

# Create output directory
mkdir -p dist/packages

# Check for multiarch flag
if [[ "$1" == "--multiarch" ]] || [[ "$1" == "-m" ]]; then
    echo "Building for multiple architectures (amd64, arm64)..."
    
    # Setup buildx if needed
    if ! docker buildx inspect multiarch-builder &>/dev/null; then
        echo "Creating buildx builder..."
        docker buildx create --name multiarch-builder --use
        docker buildx inspect --bootstrap
    else
        docker buildx use multiarch-builder
    fi
    
    # Build for both architectures
    docker buildx build \
        -f Dockerfile.fpm \
        --platform linux/amd64,linux/arm64 \
        --target=export \
        --output type=local,dest=dist/packages \
        .
        
    # Organize and rename files from subdirectories
    echo "Organizing multiarch packages..."
    
    # Handle linux_amd64
    if [ -d "dist/packages/linux_amd64" ]; then
        echo "Processing amd64 packages..."
        # Rename and move debs
        find "dist/packages/linux_amd64" -name "*_all.deb" -exec sh -c 'mv "$1" "dist/packages/$(basename "$1" | sed "s/_all.deb/_amd64.deb/")"' _ {} \;
        # Rename and move rpms
        find "dist/packages/linux_amd64" -name "*.noarch.rpm" -exec sh -c 'mv "$1" "dist/packages/$(basename "$1" | sed "s/.noarch.rpm/.x86_64.rpm/")"' _ {} \;
        # Move wheels (overwrite since they are identical)
        find "dist/packages/linux_amd64" -name "*.whl" -exec mv {} "dist/packages/" \;
        
        # Cleanup
        rm -rf "dist/packages/linux_amd64"
    fi

    # Handle linux_arm64
    if [ -d "dist/packages/linux_arm64" ]; then
        echo "Processing arm64 packages..."
        # Rename and move debs
        find "dist/packages/linux_arm64" -name "*_all.deb" -exec sh -c 'mv "$1" "dist/packages/$(basename "$1" | sed "s/_all.deb/_arm64.deb/")"' _ {} \;
        # Rename and move rpms
        find "dist/packages/linux_arm64" -name "*.noarch.rpm" -exec sh -c 'mv "$1" "dist/packages/$(basename "$1" | sed "s/.noarch.rpm/.aarch64.rpm/")"' _ {} \;
        
        # Cleanup (wheel already moved from amd64 or will be overwritten, it's fine)
        rm -rf "dist/packages/linux_arm64"
    fi
else
    echo "Building for current architecture..."
    docker build \
        -f Dockerfile.fpm \
        --target=export \
        --output type=local,dest=dist/packages \
        .
fi

echo ""
echo "=========================================="
echo "Build complete!"
echo "=========================================="
echo ""
echo "Packages built:"
ls -la dist/packages/
echo ""
echo "Installation commands:"
echo ""
echo "  Debian/Ubuntu:"
echo "    sudo dpkg -i dist/packages/ofx_${VERSION}-1_all.deb"
echo "    sudo apt-get install -f"
echo ""
echo "  Fedora/RHEL:"
echo "    sudo rpm -i dist/packages/ofx-${VERSION}-1.noarch.rpm"
echo ""
echo "  Any platform (pip):"
echo "    pip install dist/packages/ofx-${VERSION}-py3-none-any.whl"
echo ""
echo "  Windows (build on Windows):"
echo "    scripts\\build-windows.bat"
echo "    or: make pkg-windows"
