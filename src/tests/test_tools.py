import sys
from pathlib import Path

import pytest

from nju_agent.tools import list_files, read_file, run_command, write_file


def test_list_files_returns_sorted_names(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")

    assert list_files(str(tmp_path)) == ["a.txt", "b.txt"]


def test_read_and_write_file(tmp_path: Path) -> None:
    write_file(str(tmp_path), "notes/hello.txt", "hello nju")

    assert read_file(str(tmp_path), "notes/hello.txt") == "hello nju"


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
