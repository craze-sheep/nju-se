import subprocess
from dataclasses import asdict
import sys
from pathlib import Path

import pytest

import nju_agent.tools as tools_mod
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


def test_run_command_returns_exit_code_and_stdout_local_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NJU_AGENT_RUN_COMMAND_MODE", "local")
    result = run_command(str(tmp_path), [sys.executable, "-c", "print('hello nju')"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "hello nju"


def test_run_command_times_out_local_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NJU_AGENT_RUN_COMMAND_MODE", "local")
    with pytest.raises(TimeoutError):
        run_command(str(tmp_path), [sys.executable, "-c", "import time; time.sleep(1)"], timeout=0.1)


def test_run_command_uses_persistent_docker_container(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("NJU_AGENT_RUN_COMMAND_MODE", raising=False)

    calls: list[list[str]] = []
    state = {
        "image_built": False,
        "container_created": False,
        "container_running": False,
        "exec_calls": 0,
    }
    image_name = "nju-agent-sandbox:latest"
    container_name = f"nju_agent_sandbox_{tools_mod._workspace_hash(str(tmp_path))}"

    def fake_run(
        args,
        cwd=None,
        input=None,
        text=None,
        capture_output=None,
        timeout=None,
        check=None,
    ):
        calls.append(list(args))
        if args[:4] == ["docker", "image", "inspect", image_name]:
            if state["image_built"]:
                return subprocess.CompletedProcess(args, 0, "", "")
            return subprocess.CompletedProcess(args, 1, "", "missing")
        if args[:2] == ["docker", "build"]:
            state["image_built"] = True
            return subprocess.CompletedProcess(args, 0, "built", "")
        if args[:4] == ["docker", "container", "inspect", "--format"] and args[4] == "{{.Config.Image}}":
            if state["container_created"]:
                return subprocess.CompletedProcess(args, 0, image_name, "")
            return subprocess.CompletedProcess(args, 1, "", "missing")
        if args[:4] == ["docker", "container", "inspect", "--format"] and args[4] == "{{.State.Status}}":
            if state["container_running"]:
                return subprocess.CompletedProcess(args, 0, "running\n", "")
            if state["container_created"]:
                return subprocess.CompletedProcess(args, 0, "exited\n", "")
            return subprocess.CompletedProcess(args, 1, "", "missing")
        if args[:2] == ["docker", "rm"]:
            state["container_created"] = False
            state["container_running"] = False
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["docker", "run"]:
            state["container_created"] = True
            state["container_running"] = True
            return subprocess.CompletedProcess(args, 0, "container-id\n", "")
        if args[:2] == ["docker", "start"]:
            state["container_running"] = True
            return subprocess.CompletedProcess(args, 0, "container-id\n", "")
        if args[:2] == ["docker", "exec"]:
            state["exec_calls"] += 1
            return subprocess.CompletedProcess(args, 0, "hello nju\n", "")
        raise AssertionError(f"Unexpected command: {args}")

    monkeypatch.setattr(tools_mod.subprocess, "run", fake_run)

    first = run_command(str(tmp_path), [sys.executable, "-c", "print('hello nju')"], timeout=5)
    second = run_command(str(tmp_path), [sys.executable, "-c", "print('hello nju again')"], timeout=5)

    assert first.exit_code == 0
    assert first.stdout.strip() == "hello nju"
    assert second.exit_code == 0
    assert state["exec_calls"] == 2
    assert sum(1 for call in calls if call[:2] == ["docker", "build"]) == 1
    assert sum(1 for call in calls if call[:2] == ["docker", "run"]) == 1
    assert any(call[:3] == ["docker", "run", "-d"] and container_name in call for call in calls)
    assert any(call[:2] == ["docker", "exec"] and "timeout" in call for call in calls)


def test_run_command_docker_timeout_maps_to_timeout_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("NJU_AGENT_RUN_COMMAND_MODE", raising=False)
    monkeypatch.setenv("NJU_AGENT_SANDBOX_IMAGE", "nju-agent-sandbox:latest")

    def fake_run(
        args,
        cwd=None,
        input=None,
        text=None,
        capture_output=None,
        timeout=None,
        check=None,
    ):
        if args[:4] == ["docker", "image", "inspect", "nju-agent-sandbox:latest"]:
            return subprocess.CompletedProcess(args, 0, "exists", "")
        if args[:4] == ["docker", "container", "inspect", "--format"] and args[4] == "{{.Config.Image}}":
            return subprocess.CompletedProcess(args, 0, "nju-agent-sandbox:latest", "")
        if args[:4] == ["docker", "container", "inspect", "--format"] and args[4] == "{{.State.Status}}":
            return subprocess.CompletedProcess(args, 0, "running\n", "")
        if args[:2] == ["docker", "exec"]:
            return subprocess.CompletedProcess(args, 124, "", "")
        raise AssertionError(f"Unexpected command: {args}")

    monkeypatch.setattr(tools_mod.subprocess, "run", fake_run)

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
