#!/bin/bash
#
# Bump OFX version across all files
#
# Usage:
#   ./scripts/bump-version.sh 0.3.2
#   ./scripts/bump-version.sh 0.4.0 "New feature release"
#
set -euo pipefail

UPDATED_FILES=()

if [ -z "${1:-}" ]; then
    echo "Usage: $0 <new-version> [changelog-message]"
    echo "Example: $0 0.3.2 'Bug fixes and improvements'"
    exit 1
fi

NEW_VERSION="$1"
CHANGELOG_MSG="${2:-Version $NEW_VERSION release}"
DATE=$(date -u +"%a, %d %b %Y %H:%M:%S %z")
DATE_SHORT=$(date -u +"%a %b %d %Y")

echo "=========================================="
echo "Bumping OFX version to ${NEW_VERSION}"
echo "=========================================="

CURRENT_VERSION=""
if [ -f "pyproject.toml" ]; then
    CURRENT_VERSION=$(grep '^version = ' pyproject.toml | head -1 | cut -d'"' -f2 || true)
fi
if [ -n "${CURRENT_VERSION}" ]; then
    echo "Current version: ${CURRENT_VERSION}"
else
    echo "Current version: (not found)"
fi
echo "New version: ${NEW_VERSION}"
echo ""

update_file() {
    local path="$1"
    local update_fn="$2"
    if [ -f "$path" ]; then
        eval "$update_fn"
        UPDATED_FILES+=("$path")
    else
        echo "  - Skipping missing file: $path"
    fi
}

echo "[1/6] Updating pyproject.toml..."
update_file "pyproject.toml" "sed -i \"s/^version = \\\".*\\\"/version = \\\"${NEW_VERSION}\\\"/\" pyproject.toml"

echo "[2/4] Updating Winget manifest (if present)..."
update_file "packaging/winget/redteam.OFX.yaml" "sed -i \"s/^PackageVersion: .*/PackageVersion: ${NEW_VERSION}/\" packaging/winget/redteam.OFX.yaml"
if [ -f "packaging/winget/redteam.OFX.yaml" ]; then
    sed -i "s|/tag/v[0-9.]*/|/tag/v${NEW_VERSION}/|g" packaging/winget/redteam.OFX.yaml
    sed -i "s|/download/v[0-9.]*/|/download/v${NEW_VERSION}/|g" packaging/winget/redteam.OFX.yaml
    sed -i "s/ofx-[0-9.]*-windows/ofx-${NEW_VERSION}-windows/g" packaging/winget/redteam.OFX.yaml
fi

echo "[3/4] Updating man page (OFX.1)..."
MANPAGE_PATH=""
for candidate in "packaging/OFX.1" "packaging/ofx.1" "packaging/debian/ofx.1" "debian/ofx.1"; do
    if [ -f "$candidate" ]; then
        MANPAGE_PATH="$candidate"
        break
    fi
done
if [ -n "$MANPAGE_PATH" ]; then
    MONTH_YEAR=$(date -u +"%B %Y")
    sed -i "s/^.TH OFX 1 \".*\" \"OFX .*\"/.TH OFX 1 \"${MONTH_YEAR}\" \"OFX ${NEW_VERSION}\"/" "$MANPAGE_PATH"
    UPDATED_FILES+=("$MANPAGE_PATH")
else
    echo "  - No man page found"
fi

echo "[4/4] Updating src/ofx/_version.py if it contains a literal version..."
if [ -f "src/ofx/_version.py" ]; then
    if grep -q "__version__ = \"" src/ofx/_version.py; then
        sed -i "s/__version__ = \".*\"/__version__ = \"${NEW_VERSION}\"/" src/ofx/_version.py
        UPDATED_FILES+=("src/ofx/_version.py")
    else
        echo "  - _version.py uses dynamic metadata (no change needed)"
    fi
else
    echo "  - _version.py not found"
fi

echo ""
echo "=========================================="
echo "Version bumped to ${NEW_VERSION}"
echo "=========================================="
echo ""
echo "Files updated:"
if [ ${#UPDATED_FILES[@]} -eq 0 ]; then
    echo "  (none)"
else
    for file in "${UPDATED_FILES[@]}"; do
        echo "  - ${file}"
    done
fi
echo ""
echo "Next steps:"
echo "  1. Review changes: git diff"
echo "  2. Commit: git add -A && git commit -m 'Bump version to ${NEW_VERSION}'"
echo "  3. Tag: git tag v${NEW_VERSION}"
echo "  4. Push: git push && git push --tags"
