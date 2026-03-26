#!/usr/bin/env bash
# Build compiled OFX distribution with Cython.
#
# This script:
# 1. Compiles all .py modules → .so/.pyd extensions
# 2. Strips .py source files from the output (keeps __init__.py, _version.py)
# 3. Builds a wheel containing only compiled extensions + data files
#
# Usage:
#   ./scripts/build_compiled.sh          # build compiled wheel
#   ./scripts/build_compiled.sh --keep   # keep .py alongside .so (debug)
#   ./scripts/build_compiled.sh --clean  # clean build artifacts only
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_ROOT/build"
DIST_DIR="$PROJECT_ROOT/dist"
SRC_DIR="$PROJECT_ROOT/src"
STAGING_DIR="$BUILD_DIR/compiled_staging"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[build]${NC} $*"; }
ok()    { echo -e "${GREEN}[build]${NC} $*"; }
warn()  { echo -e "${YELLOW}[build]${NC} $*"; }
err()   { echo -e "${RED}[build]${NC} $*" >&2; }

KEEP_SOURCE=0
CLEAN_ONLY=0

for arg in "$@"; do
    case "$arg" in
        --keep)  KEEP_SOURCE=1 ;;
        --clean) CLEAN_ONLY=1 ;;
        --help|-h)
            echo "Usage: $0 [--keep] [--clean]"
            echo "  --keep   Keep .py source files alongside .so (for debugging)"
            echo "  --clean  Clean build artifacts only"
            exit 0
            ;;
        *) err "Unknown option: $arg"; exit 1 ;;
    esac
done

clean_artifacts() {
    info "Cleaning build artifacts..."
    rm -rf "$BUILD_DIR" "$DIST_DIR"
    find "$SRC_DIR" -type f -name "*.c" -delete 2>/dev/null || true
    find "$SRC_DIR" -type f -name "*.so" -delete 2>/dev/null || true
    find "$SRC_DIR" -type f -name "*.pyd" -delete 2>/dev/null || true
    find "$SRC_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    ok "Clean complete"
}

if [ "$CLEAN_ONLY" -eq 1 ]; then
    clean_artifacts
    exit 0
fi

# ── Preflight checks ─────────────────────────────────────────────
command -v python3 >/dev/null 2>&1 || { err "python3 not found"; exit 1; }
python3 -c "import Cython" 2>/dev/null || {
    warn "Cython not installed, installing..."
    pip install cython 2>/dev/null || uv pip install cython
}

# ── Step 1: Compile with Cython ──────────────────────────────────
info "Compiling Python modules with Cython..."
cd "$PROJECT_ROOT"
python3 setup_cython.py build_ext --inplace 2>&1

COMPILED=$(find "$SRC_DIR" -name "*.so" -o -name "*.pyd" | wc -l)
if [ "$COMPILED" -eq 0 ]; then
    err "No compiled modules found — compilation may have failed"
    exit 1
fi
ok "Compiled $COMPILED modules"

# ── Step 2: Prepare staging directory ────────────────────────────
info "Preparing staging directory..."
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR/src"

# Copy the entire src/ofx tree
cp -a "$SRC_DIR/ofx" "$STAGING_DIR/src/ofx"

if [ "$KEEP_SOURCE" -eq 0 ]; then
    info "Stripping .py source files (keeping __init__.py, _version.py)..."
    find "$STAGING_DIR/src/ofx" -name "*.py" \
        ! -name "__init__.py" \
        ! -name "_version.py" \
        ! -path "*/data/*" \
        -delete

    STRIPPED=$(find "$STAGING_DIR/src/ofx" -name "*.py" | wc -l)
    EXTENSIONS=$(find "$STAGING_DIR/src/ofx" \( -name "*.so" -o -name "*.pyd" \) | wc -l)
    info "Retained: $STRIPPED .py files, $EXTENSIONS compiled extensions"
fi

# Remove .c intermediates from staging
find "$STAGING_DIR" -name "*.c" -delete

# ── Step 3: Copy packaging files ─────────────────────────────────
info "Copying packaging metadata..."
cp "$PROJECT_ROOT/pyproject.toml" "$STAGING_DIR/"
cp "$PROJECT_ROOT/README.md" "$STAGING_DIR/" 2>/dev/null || true
cp "$PROJECT_ROOT/MANIFEST.in" "$STAGING_DIR/" 2>/dev/null || true
cp "$PROJECT_ROOT/LICENSE" "$STAGING_DIR/" 2>/dev/null || true

# ── Step 4: Build wheel ──────────────────────────────────────────
info "Building wheel..."
mkdir -p "$DIST_DIR"

cd "$STAGING_DIR"
python3 -m build --wheel --outdir "$DIST_DIR" 2>&1 || {
    # Fallback: use pip wheel
    warn "python-build failed, trying pip wheel..."
    pip wheel --no-deps --wheel-dir "$DIST_DIR" . 2>&1
}

WHEEL=$(ls "$DIST_DIR"/*.whl 2>/dev/null | head -1)
if [ -n "$WHEEL" ]; then
    ok "Built: $(basename "$WHEEL")"
    ok "Size: $(du -h "$WHEEL" | cut -f1)"
else
    warn "Wheel build skipped (python-build not available). Compiled .so files are in-place."
fi

# ── Step 5: Clean intermediates from source tree ─────────────────
info "Cleaning C intermediates from source tree..."
find "$SRC_DIR" -name "*.c" -delete 2>/dev/null || true

ok "Build complete!"
echo ""
echo "  Compiled extensions are in-place under src/ofx/"
if [ -n "${WHEEL:-}" ]; then
    echo "  Distribution wheel: $WHEEL"
fi
echo ""
echo "  To test:  python3 -c 'from ofx import main; main()' -- --version"
echo "  To clean: $0 --clean"
