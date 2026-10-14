"""Shared helpers for post-exploitation runners."""

from __future__ import annotations


class RemoteTempFilesMixin:
    """Mixin for runners that track remote temp file paths.

    Subclasses must expose a ``_remote_temp_files`` list attribute. This mixin
    provides :meth:`_forget_remote_temp_file` to drop a single path from
    tracking once it has been cleaned up.
    """

    _remote_temp_files: list[str]

    def _forget_remote_temp_file(self, remote_tmp: str) -> None:
        if remote_tmp in self._remote_temp_files:
            self._remote_temp_files.remove(remote_tmp)
