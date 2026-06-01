"""Tests for shared filesystem cleanup helpers."""

from __future__ import annotations

from pathlib import Path

from ofx.utils.file_cleanup import (
    remove_empty_dirs,
    remove_file,
    remove_files_and_parent_dir,
    remove_tree,
)


def test_remove_file_respects_required_substring(tmp_path):
    temp_file = tmp_path / ".ofx_task_output.json"
    temp_file.write_text("{}")

    assert remove_file(temp_file, required_substring=".ofx_task_") is None
    assert not temp_file.exists()

    other_file = tmp_path / "report.json"
    other_file.write_text("{}")

    assert remove_file(other_file, required_substring=".ofx_task_") is None
    assert other_file.exists()


def test_remove_files_and_parent_dir_clears_tracked_files(tmp_path):
    parent = tmp_path / "chunks"
    parent.mkdir()
    first = parent / "a.txt"
    second = parent / "b.txt"
    first.write_text("a")
    second.write_text("b")
    tracked = [first, second]
    logs: list[str] = []

    remove_files_and_parent_dir(
        tracked,
        on_error=logs.append,
        file_label="chunk file",
        dir_label="chunk dir",
        clear=tracked,
    )

    assert logs == []
    assert tracked == []
    assert not parent.exists()


def test_remove_tree_logs_failure_with_context(tmp_path):
    messages: list[str] = []
    missing = Path(tmp_path / "missing")

    remove_tree(missing, on_error=messages.append, label="run dir")

    assert messages == []


def test_remove_empty_dirs_removes_empty_parents_only(tmp_path):
    root = tmp_path / "root"
    empty = root / "empty" / "nested"
    non_empty = root / "keep"
    empty.mkdir(parents=True)
    non_empty.mkdir(parents=True)
    (non_empty / "file.txt").write_text("keep")

    remove_empty_dirs(root)

    assert not empty.exists()
    assert non_empty.exists()
