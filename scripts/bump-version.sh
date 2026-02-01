#!/bin/bash
#
# Bump OFX version across all files
#
# Usage:
#   ./scripts/bump-version.sh 0.3.2
#   ./scripts/bump-version.sh 0.4.0 "New feature release"
#
set -e

if [ -z "$1" ]; then
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

# Get current version
CURRENT_VERSION=$(grep '^version = ' pyproject.toml | head -1 | cut -d'"' -f2)
echo "Current version: ${CURRENT_VERSION}"
echo "New version: ${NEW_VERSION}"
echo ""

# 1. Update pyproject.toml
echo "[1/6] Updating pyproject.toml..."
sed -i "s/^version = \".*\"/version = \"${NEW_VERSION}\"/" pyproject.toml

# 2. Update packaging/debian/changelog
echo "[2/6] Updating packaging/debian/changelog..."
cat > packaging/debian/changelog.new << EOF
ofx (${NEW_VERSION}-1) unstable; urgency=medium

  * ${CHANGELOG_MSG}

 -- OFX Developer <dev.hah4@gmail.com>  ${DATE}

EOF
cat packaging/debian/changelog >> packaging/debian/changelog.new
mv packaging/debian/changelog.new packaging/debian/changelog

# 3. Update packaging/rpm/ofx.spec
echo "[3/6] Updating packaging/rpm/ofx.spec..."
sed -i "s/^Version:        .*/Version:        ${NEW_VERSION}/" packaging/rpm/ofx.spec
# Add changelog entry
sed -i "/^%changelog/a\\
* ${DATE_SHORT} OFX Developer <dev.hah4@gmail.com> - ${NEW_VERSION}-1\\
- ${CHANGELOG_MSG}\\
" packaging/rpm/ofx.spec

# 4. Update packaging/winget/redteam.OFX.yaml
echo "[4/6] Updating packaging/winget/redteam.OFX.yaml..."
sed -i "s/^PackageVersion: .*/PackageVersion: ${NEW_VERSION}/" packaging/winget/redteam.OFX.yaml
sed -i "s|/v[0-9.]*-1/|/v${NEW_VERSION}/|g" packaging/winget/redteam.OFX.yaml
sed -i "s|/v[0-9.]*/|/v${NEW_VERSION}/|g" packaging/winget/redteam.OFX.yaml
sed -i "s/ofx-[0-9.]*-windows/ofx-${NEW_VERSION}-windows/g" packaging/winget/redteam.OFX.yaml

# 5. Update packaging/debian/ofx.1 (man page)
echo "[5/6] Updating packaging/debian/ofx.1..."
MONTH_YEAR=$(date -u +"%B %Y")
sed -i "s/^.TH OFX 1 \".*\" \"OFX .*\"/.TH OFX 1 \"${MONTH_YEAR}\" \"OFX ${NEW_VERSION}\"/" packaging/debian/ofx.1

# 6. Update src/ofx/_version.py if it exists
echo "[6/6] Updating src/ofx/_version.py..."
if [ -f "src/ofx/_version.py" ]; then
    sed -i "s/__version__ = \".*\"/__version__ = \"${NEW_VERSION}\"/" src/ofx/_version.py
fi

echo ""
echo "=========================================="
echo "Version bumped to ${NEW_VERSION}"
echo "=========================================="
echo ""
echo "Files updated:"
echo "  - pyproject.toml"
echo "  - packaging/debian/changelog"
echo "  - packaging/rpm/ofx.spec"
echo "  - packaging/winget/redteam.OFX.yaml"
echo "  - packaging/debian/ofx.1"
echo "  - src/ofx/_version.py"
echo ""
echo "Next steps:"
echo "  1. Review changes: git diff"
echo "  2. Commit: git add -A && git commit -m 'Bump version to ${NEW_VERSION}'"
echo "  3. Tag: git tag v${NEW_VERSION}"
echo "  4. Push: git push && git push --tags"
