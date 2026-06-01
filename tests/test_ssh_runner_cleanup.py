"""Tests for SSH temp-file cleanup helpers."""

from __future__ import annotations

from ofx.api.post.runners.ssh import PostSSH


def test_forget_remote_temp_file_removes_single_entry():
    runner = object.__new__(PostSSH)
    runner._remote_temp_files = ["/tmp/a", "/tmp/b"]

    runner._forget_remote_temp_file("/tmp/a")

    assert runner._remote_temp_files == ["/tmp/b"]


def test_cleanup_remote_temp_files_runs_single_rm_and_clears_list():
    runner = object.__new__(PostSSH)
    calls: list[tuple[str, int | None]] = []
    runner._remote_temp_files = ["/tmp/a", "/tmp/b"]
    runner._run_direct = lambda command, timeout=None: calls.append((command, timeout))

    runner._cleanup_remote_temp_files()

    assert calls == [("rm -f /tmp/a /tmp/b", 10)]
    assert runner._remote_temp_files == []
