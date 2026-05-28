"""Tests for shared temporary remote upload helpers."""

from __future__ import annotations

from pathlib import Path

from ofx.cloud.temp_upload import upload_temp_content


class _Remote:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def upload(self, local_path: str, remote_path: str) -> None:
        self.calls.append((local_path, remote_path, Path(local_path).read_text()))


def test_upload_temp_content_uploads_and_cleans_local_file(tmp_path):
    remote = _Remote()

    upload_temp_content(remote, "hello", "/tmp/remote.py", suffix=".py")

    assert len(remote.calls) == 1
    local_path, remote_path, content = remote.calls[0]
    assert remote_path == "/tmp/remote.py"
    assert content == "hello"
    assert local_path.endswith(".py")
    assert not Path(local_path).exists()
