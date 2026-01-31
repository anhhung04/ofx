#!/bin/bash
#
# Build OFX packages for all platforms using Docker
#
# Usage:
#   ./scripts/build-packages.sh              # Build for current arch
#   ./scripts/build-packages.sh --multiarch  # Build for amd64 and arm64
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
        -f Dockerfile.pkg \
        --platform linux/amd64,linux/arm64 \
        --target=export \
        --output type=local,dest=dist/packages \
        .
else
    echo "Building for current architecture..."
    docker build \
        -f Dockerfile.pkg \
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
