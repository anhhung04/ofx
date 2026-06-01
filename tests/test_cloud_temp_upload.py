"""Tests for temporary upload helper cleanup."""

from __future__ import annotations

import os

from ofx.cloud.temp_upload import upload_temp_content


def test_upload_temp_content_removes_local_temp_file(tmp_path, monkeypatch):
    created = tmp_path / "upload.txt"
    captured: dict[str, str] = {}

    def fake_mkstemp(suffix: str = ""):
        assert suffix == ".py"
        fd = os.open(created, os.O_CREAT | os.O_RDWR)
        return fd, str(created)

    class _Remote:
        def upload(self, local_path: str, remote_path: str) -> None:
            captured["local_path"] = local_path
            captured["remote_path"] = remote_path
            assert created.exists()
            assert created.read_text() == "print('hi')"

    monkeypatch.setattr("ofx.cloud.temp_upload.tempfile.mkstemp", fake_mkstemp)

    upload_temp_content(_Remote(), "print('hi')", "/tmp/remote.py", suffix=".py")

    assert captured == {
        "local_path": str(created),
        "remote_path": "/tmp/remote.py",
    }
    assert not created.exists()
