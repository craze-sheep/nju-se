from pathlib import Path

from nju_agent.tools import list_files


def test_list_files_returns_sorted_names(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")

    assert list_files(str(tmp_path)) == ["a.txt", "b.txt"]
