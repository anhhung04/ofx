#!/usr/bin/env bash
# Build compiled OFX distribution with Cython.
#
# This script:
# 1. Compiles all .py modules → .so/.pyd extensions
# 2. Strips .py source files from the output (keeps __init__.py, _version.py,
#    and any .py file that has no corresponding .so — i.e., Cython-incompatible)
# 3. Builds a platform-tagged wheel containing compiled extensions + data files
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
command -v uv >/dev/null 2>&1 || { err "uv not found"; exit 1; }

# ── Step 1: Compile with Cython ──────────────────────────────────
info "Compiling Python modules with Cython..."
cd "$PROJECT_ROOT"
uv run --extra compile setup_cython.py build_ext --inplace 2>&1

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

# Verify data directory survived copy
if [ ! -d "$STAGING_DIR/src/ofx/data" ]; then
    err "Data directory missing from staging — build would be incomplete"
    exit 1
fi
DATA_COUNT=$(find "$STAGING_DIR/src/ofx/data" -type f | wc -l)
info "Data directory: $DATA_COUNT files (workflows, assets)"

if [ "$KEEP_SOURCE" -eq 0 ]; then
    info "Stripping .py source files where .so exists..."
    # Only remove .py files that have a compiled .so counterpart.
    # Files that Cython couldn't compile (match/case, PEP 695, Pydantic, etc.)
    # MUST be kept as .py — they are the only copy.
    # Data directory (YAML workflows, static assets) is never touched.
    REMOVED=0
    while IFS= read -r -d '' so_file; do
        # .so name: module.cpython-3XX-ARCH.so → derive the .py basename
        base_dir="$(dirname "$so_file")"
        # Skip data directory — it contains no .so files anyway but be explicit
        case "$base_dir" in */data/*) continue ;; esac
        # Extract module name: everything before .cpython-
        so_name="$(basename "$so_file")"
        py_name="${so_name%%.*}.py"
        py_file="$base_dir/$py_name"
        if [ -f "$py_file" ]; then
            rm "$py_file"
            REMOVED=$((REMOVED + 1))
        fi
    done < <(find "$STAGING_DIR/src/ofx" \( -name "*.so" -o -name "*.pyd" \) -print0)

    KEPT_PY=$(find "$STAGING_DIR/src/ofx" -name "*.py" | wc -l)
    EXTENSIONS=$(find "$STAGING_DIR/src/ofx" \( -name "*.so" -o -name "*.pyd" \) | wc -l)
    DATA_FILES=$(find "$STAGING_DIR/src/ofx/data" -type f 2>/dev/null | wc -l)
    info "Removed $REMOVED .py files with .so counterparts"
    info "Retained: $KEPT_PY .py files (init/incompatible), $EXTENSIONS compiled extensions, $DATA_FILES data files"
fi

# Remove .c intermediates from staging
find "$STAGING_DIR" -name "*.c" -delete
find "$STAGING_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# ── Step 3: Build platform-tagged wheel ──────────────────────────
info "Building platform-tagged wheel..."
mkdir -p "$DIST_DIR"

cd "$PROJECT_ROOT"
uv run --extra compile python3 -c "
import sys, os, sysconfig, hashlib, csv, io, zipfile, email.generator
from pathlib import Path

staging = Path('$STAGING_DIR')
dist_dir = Path('$DIST_DIR')

# Read version from pyproject.toml
import re
pyproject = Path('pyproject.toml').read_text()
version = re.search(r'version\s*=\s*\"([^\"]+)\"', pyproject).group(1)
name = 'ofx'

# Platform tag
python_tag = f'cp{sys.version_info.major}{sys.version_info.minor}'
abi_tag = sysconfig.get_config_var('SOABI') or python_tag
# Normalize abi tag
abi_tag = abi_tag.replace('-', '_').replace('.', '_')
if not abi_tag.startswith('cpython'):
    abi_tag = python_tag
else:
    abi_tag = abi_tag.replace('cpython_', 'cp')
platform_tag = sysconfig.get_platform().replace('-', '_').replace('.', '_')
if platform_tag.startswith('linux_'):
    platform_tag = f'manylinux_2_17_{platform_tag.removeprefix("linux_")}'

wheel_name = f'{name}-{version}-{python_tag}-{abi_tag}-{platform_tag}'
wheel_path = dist_dir / f'{wheel_name}.whl'
dist_info = f'{name}-{version}.dist-info'

print(f'  Wheel: {wheel_name}.whl')

# Collect files
records = []
with zipfile.ZipFile(wheel_path, 'w', zipfile.ZIP_STORED, allowZip64=True) as whl:
    # Package files from staging
    src_ofx = staging / 'src' / 'ofx'
    for fpath in sorted(src_ofx.rglob('*')):
        if fpath.is_dir():
            continue
        arcname = str(fpath.relative_to(staging / 'src'))
        data = fpath.read_bytes()
        whl.writestr(arcname, data)
        h = hashlib.sha256(data).hexdigest()
        records.append((arcname, f'sha256={h}', str(len(data))))

    # METADATA
    metadata = f'''Metadata-Version: 2.1
Name: {name}
Version: {version}
Summary: Offensive Flow Executor
Requires-Python: >=3.12
'''
    whl.writestr(f'{dist_info}/METADATA', metadata)
    h = hashlib.sha256(metadata.encode()).hexdigest()
    records.append((f'{dist_info}/METADATA', f'sha256={h}', str(len(metadata.encode()))))

    # WHEEL
    wheel_meta = f'''Wheel-Version: 1.0
Generator: ofx-cython-build
Root-Is-Purelib: false
Tag: {python_tag}-{abi_tag}-{platform_tag}
'''
    whl.writestr(f'{dist_info}/WHEEL', wheel_meta)
    h = hashlib.sha256(wheel_meta.encode()).hexdigest()
    records.append((f'{dist_info}/WHEEL', f'sha256={h}', str(len(wheel_meta.encode()))))

    # entry_points.txt
    entry_points = '[console_scripts]\nofx = ofx:main\n'
    whl.writestr(f'{dist_info}/entry_points.txt', entry_points)
    h = hashlib.sha256(entry_points.encode()).hexdigest()
    records.append((f'{dist_info}/entry_points.txt', f'sha256={h}', str(len(entry_points.encode()))))

    # top_level.txt
    whl.writestr(f'{dist_info}/top_level.txt', 'ofx\n')

    # RECORD (must be last, no hash for itself)
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in records:
        writer.writerow(row)
    writer.writerow((f'{dist_info}/RECORD', '', ''))
    whl.writestr(f'{dist_info}/RECORD', buf.getvalue())

print(f'  Done: {wheel_path}')
print(f'  Size: {wheel_path.stat().st_size / 1024 / 1024:.1f} MB')
"

WHEEL=$(ls "$DIST_DIR"/*.whl 2>/dev/null | head -1)
if [ -z "$WHEEL" ]; then
    err "Wheel build failed"
    exit 1
fi
ok "Built: $(basename "$WHEEL")"
ok "Size: $(du -h "$WHEEL" | cut -f1)"

# ── Step 4: Clean intermediates from source tree ─────────────────
info "Cleaning C intermediates from source tree..."
find "$SRC_DIR" -name "*.c" -delete 2>/dev/null || true

ok "Build complete!"
echo ""
echo "  Compiled extensions are in-place under src/ofx/"
echo "  Distribution wheel: $WHEEL"
echo ""
echo "  Install:  pip install $WHEEL"
echo "  Test:     python3 -c 'from ofx import main; main()'"
echo "  Clean:    $0 --clean"
