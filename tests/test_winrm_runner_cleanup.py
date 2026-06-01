"""Tests for WinRM temp-file cleanup helpers."""

from __future__ import annotations

from ofx.api.post.runners.winrm import PostWinRM


def test_remove_remote_temp_file_logs_and_does_not_raise(monkeypatch):
    runner = object.__new__(PostWinRM)
    calls: list[str] = []

    def _run_ps(command: str):
        calls.append(command)
        raise RuntimeError("boom")

    runner.run_ps = _run_ps

    runner._remove_remote_temp_file("C:\\Temp\\x.bat")

    assert calls == ['Remove-Item -Force "C:\\Temp\\x.bat" -ErrorAction SilentlyContinue']


def test_cleanup_clears_tracked_remote_temp_files():
    runner = object.__new__(PostWinRM)
    calls: list[str] = []
    runner._remote_temp_files = ["C:\\Temp\\a.bat", "C:\\Temp\\b.bat"]
    runner.run_ps = lambda command: calls.append(command)

    runner.cleanup()

    assert calls == [
        'Remove-Item -Force "C:\\Temp\\a.bat" -ErrorAction SilentlyContinue',
        'Remove-Item -Force "C:\\Temp\\b.bat" -ErrorAction SilentlyContinue',
    ]
    assert runner._remote_temp_files == []
