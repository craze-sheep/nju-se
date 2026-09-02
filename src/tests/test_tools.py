import subprocess
from dataclasses import asdict
import sys
from pathlib import Path

import pytest

from nju_agent.tools import list_files, read_file, revert_write_file, run_command, search_files, write_file


def _init_git_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True, capture_output=True, text=True)


def test_list_files_returns_sorted_names(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")

    assert list_files(str(tmp_path)) == ["a.txt", "b.txt"]


def test_list_files_keeps_non_blacklisted_dotfiles(tmp_path: Path) -> None:
    (tmp_path / "visible.txt").write_text("v", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".env").write_text("secret", encoding="utf-8")

    assert list_files(str(tmp_path)) == [".env", "visible.txt"]


def test_search_files_returns_matching_path_and_content(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def play_game():\n    return '2048'\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("This project is about 2048.", encoding="utf-8")

    results = search_files(str(tmp_path), "2048", limit=10)

    assert results[0]["relative_path"] == "README.md"
    assert any(item["relative_path"] == "src/main.py" for item in results)
    assert any(item["match_kind"] == "content" for item in results)


def test_search_files_keeps_content_hits_when_path_hits_are_many(tmp_path: Path) -> None:
    (tmp_path / "a_test.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "b_test.txt").write_text("beta", encoding="utf-8")
    (tmp_path / "zzz_notes.md").write_text("contains the test word", encoding="utf-8")

    results = search_files(str(tmp_path), "test", limit=1)

    assert len(results) == 1
    assert results[0]["relative_path"] == "zzz_notes.md"
    assert any(item["match_kind"] == "content" for item in results)


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


def test_write_file_diff_includes_untracked_existing_file(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "hello.txt").write_text("old", encoding="utf-8")

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


def test_revert_write_file_restores_dirty_tracked_snapshot(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)

    tracked = tmp_path / "tracked.txt"
    tracked.write_text("committed", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    tracked.write_text("uncommitted edit", encoding="utf-8")

    result = write_file(str(tmp_path), "tracked.txt", "new")

    revert_write_file(str(tmp_path), asdict(result))
    assert tracked.read_text(encoding="utf-8") == "uncommitted edit"


def test_write_file_uses_git_clean_for_new_files(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)

    result = write_file(str(tmp_path), "new.txt", "hello")

    assert "new file mode" in result.diff or "diff --git" in result.diff
    revert_write_file(str(tmp_path), asdict(result))
    assert not (tmp_path / "new.txt").exists()


def test_revert_write_file_prunes_empty_parent_dirs(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)

    result = write_file(str(tmp_path), "notes/deep/hello.txt", "hello")
    revert_write_file(str(tmp_path), asdict(result))

    assert not (tmp_path / "notes" / "deep").exists()
    assert not (tmp_path / "notes").exists()
