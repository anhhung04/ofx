"""Build a self-extracting Python bootstrap from collected module files."""

from __future__ import annotations

import base64
import io
import zipfile
from dataclasses import dataclass

from .analyzer import detect_ofx_imports
from .collector import collect_modules
from .obfuscator import obfuscate_sources as obfuscate_sources_fn

__all__ = ["BundleResult", "build_bundle"]

# ---------------------------------------------------------------------------
# Bootstrap template
#
# Placeholders use repr() formatting so that arbitrary bytes in b64_data and
# arbitrary Python source in script survive embedding without escaping issues.
# ---------------------------------------------------------------------------

_BOOTSTRAP_TEMPLATE = """\
import base64 as _b64, io as _io, os as _os, shutil as _sh, sys as _sys, tempfile as _tmp, zipfile as _zf
_arch = _b64.b64decode({b64_data!r})
_tdir = _tmp.mkdtemp(prefix='.tmp_')
try:
    with _zf.ZipFile(_io.BytesIO(_arch)) as _z:
        _z.extractall(_tdir)
    _sys.path.insert(0, _tdir)
    exec(compile({script!r}, '<bundle>', 'exec'), {{'__name__': '__main__'}})
finally:
    _sys.path[:] = [p for p in _sys.path if p != _tdir]
    _sh.rmtree(_tdir, ignore_errors=True)
"""

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BundleResult:
    """Immutable result of a successful bundle build operation."""

    modules: frozenset[str]
    """Set of ``ofx.api`` module names included in the bundle."""

    script: str
    """Original user script source (unmodified)."""

    bootstrap: str
    """Self-extracting Python bootstrap ready for obfuscation or delivery."""

    size_bytes: int
    """Byte length of *bootstrap* (UTF-8 encoded)."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arc_path, data in sorted(files.items()):
            zf.writestr(arc_path, data)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_bundle(
    script: str,
    *,
    extra_modules: list[str] | None = None,
    source_name: str = "<script>",
    obfuscate_sources: bool = False,
) -> BundleResult:
    """Analyse *script*, collect required modules, and produce a bootstrap.

    Args:
        script: Python source code that may import ``ofx.api.*`` modules.
        extra_modules: Additional ``ofx.api`` module names to force-include
            beyond what the AST detects.
        source_name: Label used in error messages (e.g. a filename).
        obfuscate_sources: When ``True``, compile every collected ``.py`` file
            to marshalled bytecode before zipping.  The ``.py`` files inside
            the bundle archive are replaced with compact stubs so the raw
            source cannot be read after extraction.  Useful when you want to
            protect your tooling from other parties (e.g. opposing teams in a
            cyber-range contest) without changing import semantics.

    Returns:
        A :class:`BundleResult` with the ready-to-deliver bootstrap string.

    Raises:
        AnalysisError: If *script* cannot be parsed.
        CollectionError: If any required module file cannot be found.
        ObfuscationError: If source obfuscation is enabled and any file fails
            to compile.
    """
    modules = detect_ofx_imports(script, extra_modules=extra_modules, source_name=source_name)
    files = collect_modules(modules)
    if obfuscate_sources:
        files = obfuscate_sources_fn(files)
    zip_bytes = _build_zip(files)
    b64_data = base64.b64encode(zip_bytes).decode()
    bootstrap = _BOOTSTRAP_TEMPLATE.format(b64_data=b64_data, script=script)
    return BundleResult(
        modules=frozenset(modules),
        script=script,
        bootstrap=bootstrap,
        size_bytes=len(bootstrap.encode()),
    )
