from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class WriteResult:
    relative_path: str
    existed_before: bool
    tracked_before: bool
    diff: str


def _safe_path(root: str, relative_path: str) -> Path:
    base = Path(root).resolve()
    target = (base / relative_path).resolve()

    if target != base and base not in target.parents:
        raise ValueError(f"Path escapes workspace: {relative_path}")

    return target


def list_files(root: str) -> list[str]:
    base = Path(root).resolve()
    return sorted(path.name for path in base.iterdir())


def read_file(root: str, relative_path: str) -> str:
    target = _safe_path(root, relative_path)
    return target.read_text(encoding="utf-8")


def _run_git(root: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", root, *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _git_repo_root(root: str) -> str | None:
    result = _run_git(root, ["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _git_is_tracked(root: str, relative_path: str) -> bool:
    result = _run_git(root, ["ls-files", "--error-unmatch", "--", relative_path])
    return result.returncode == 0


def _git_diff_text(
    root: str,
    target: Path,
    relative_path: str,
    *,
    existed_before: bool,
    tracked_before: bool,
) -> str:
    if tracked_before:
        result = _run_git(root, ["diff", "--no-ext-diff", "--no-color", "--", relative_path])
    elif not existed_before:
        result = _run_git(
            root,
            [
                "diff",
                "--no-ext-diff",
                "--no-color",
                "--no-index",
                "--",
                "/dev/null",
                str(target),
            ],
        )
    else:
        return ""

    if result.stdout:
        return result.stdout.rstrip()
    return ""


def write_file(root: str, relative_path: str, content: str) -> WriteResult:
    target = _safe_path(root, relative_path)
    existed_before = target.exists()
    git_root = _git_repo_root(root)
    tracked_before = bool(git_root) and _git_is_tracked(root, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    diff = (
        _git_diff_text(
            root,
            target,
            relative_path,
            existed_before=existed_before,
            tracked_before=tracked_before,
        )
        if git_root
        else ""
    )
    return WriteResult(
        relative_path=relative_path,
        existed_before=existed_before,
        tracked_before=tracked_before,
        diff=diff,
    )


def revert_write_file(root: str, change: dict[str, object]) -> None:
    relative_path = str(change.get("relative_path", ""))
    _safe_path(root, relative_path)
    existed_before = bool(change.get("existed_before", False))
    tracked_before = bool(change.get("tracked_before", False))
    git_root = _git_repo_root(root)
    if not git_root:
        raise RuntimeError("Git repository not found")

    if tracked_before:
        result = _run_git(
            root,
            ["restore", "--source=HEAD", "--worktree", "--staged", "--", relative_path],
        )
        if result.returncode == 0:
            return
        raise RuntimeError(result.stderr.strip() or f"git restore failed for {relative_path}")

    if not existed_before:
        result = _run_git(root, ["clean", "-f", "--", relative_path])
        if result.returncode == 0:
            return
        raise RuntimeError(result.stderr.strip() or f"git clean failed for {relative_path}")

    raise RuntimeError(f"无法仅用 Git 撤销未跟踪文件的修改：{relative_path}")


def run_command(root: str, command: list[str], timeout: float = 10.0) -> CommandResult:
    base = Path(root).resolve()

    try:
        result = subprocess.run(
            command,
            cwd=base,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"Command timed out after {timeout} seconds") from exc

    return CommandResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
