import subprocess
from dataclasses import asdict
import sys
from pathlib import Path

import pytest

from nju_agent.tools import list_files, read_file, revert_write_file, run_command, write_file


def _init_git_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True, capture_output=True, text=True)


def test_list_files_returns_sorted_names(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")

    assert list_files(str(tmp_path)) == ["a.txt", "b.txt"]


def test_read_and_write_file(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    result = write_file(str(tmp_path), "notes/hello.txt", "hello nju")

    assert read_file(str(tmp_path), "notes/hello.txt") == "hello nju"
    assert result.relative_path == "notes/hello.txt"
    assert result.existed_before is False
    assert "+hello nju" in result.diff


def test_write_file_diff_includes_before_and_after(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "hello.txt").write_text("old", encoding="utf-8")
    subprocess.run(["git", "add", "notes/hello.txt"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)

    result = write_file(str(tmp_path), "notes/hello.txt", "new")

    assert "-old" in result.diff
    assert "+new" in result.diff


def test_write_file_rejects_escape_outside_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_file(str(tmp_path), "../outside.txt", "nope")


def test_run_command_returns_exit_code_and_stdout(tmp_path: Path) -> None:
    result = run_command(str(tmp_path), [sys.executable, "-c", "print('hello nju')"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "hello nju"


def test_run_command_times_out(tmp_path: Path) -> None:
    with pytest.raises(TimeoutError):
        run_command(str(tmp_path), [sys.executable, "-c", "import time; time.sleep(1)"], timeout=0.1)


def test_write_file_uses_git_diff_and_restore_for_tracked_files(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)

    (tmp_path / "tracked.txt").write_text("old", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)

    result = write_file(str(tmp_path), "tracked.txt", "new")

    assert "diff --git" in result.diff
    revert_write_file(str(tmp_path), asdict(result))
    assert (tmp_path / "tracked.txt").read_text(encoding="utf-8") == "old"


def test_write_file_uses_git_clean_for_new_files(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)

    result = write_file(str(tmp_path), "new.txt", "hello")

    assert "new file mode" in result.diff or "diff --git" in result.diff
    revert_write_file(str(tmp_path), asdict(result))
    assert not (tmp_path / "new.txt").exists()
