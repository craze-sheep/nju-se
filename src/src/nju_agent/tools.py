import difflib
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
    before_content: str | None
    diff: str


def _safe_path(root: str, relative_path: str) -> Path:
    base = Path(root).resolve()
    target = (base / relative_path).resolve()

    if target != base and base not in target.parents:
        raise ValueError(f"Path escapes workspace: {relative_path}")

    return target


def _subprocess_run(
    args: list[str],
    *,
    cwd: str | None = None,
    timeout: float | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required executable not found: {args[0]}") from exc


def list_files(root: str) -> list[str]:
    base = Path(root).resolve()
    return sorted(
        path.name
        for path in base.iterdir()
        if path.name not in {".git", ".nju_agent"}
    )


def read_file(root: str, relative_path: str) -> str:
    target = _safe_path(root, relative_path)
    return target.read_text(encoding="utf-8")


def _run_git(root: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    return _subprocess_run(["git", "-C", root, *args])


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


def _text_diff(relative_path: str, before: str, after: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            lineterm="",
        )
    ).rstrip()


def _prune_empty_parent_dirs(path: Path, stop_at: Path) -> None:
    current = path
    while current != stop_at:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def write_file(root: str, relative_path: str, content: str) -> WriteResult:
    target = _safe_path(root, relative_path)
    existed_before = target.exists()
    if existed_before:
        try:
            before_content = target.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            before_content = None
    else:
        before_content = None
    git_root = _git_repo_root(root)
    tracked_before = bool(git_root) and _git_is_tracked(root, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    if git_root and tracked_before:
        diff = _git_diff_text(
            root,
            target,
            relative_path,
            existed_before=existed_before,
            tracked_before=tracked_before,
        )
    elif existed_before:
        diff = _text_diff(relative_path, before_content or "", content)
    elif git_root:
        diff = _git_diff_text(
            root,
            target,
            relative_path,
            existed_before=existed_before,
            tracked_before=tracked_before,
        )
    else:
        diff = _text_diff(relative_path, "", content)
    return WriteResult(
        relative_path=relative_path,
        existed_before=existed_before,
        tracked_before=tracked_before,
        before_content=before_content,
        diff=diff,
    )


def revert_write_file(root: str, change: dict[str, object]) -> None:
    relative_path = str(change.get("relative_path", ""))
    _safe_path(root, relative_path)
    existed_before = bool(change.get("existed_before", False))
    tracked_before = bool(change.get("tracked_before", False))
    before_content = change.get("before_content", None)
    git_root = _git_repo_root(root)
    if tracked_before:
        if not git_root:
            raise RuntimeError("Git repository not found")
        result = _run_git(
            root,
            ["restore", "--source=HEAD", "--worktree", "--staged", "--", relative_path],
        )
        if result.returncode == 0:
            return
        raise RuntimeError(result.stderr.strip() or f"git restore failed for {relative_path}")

    target = _safe_path(root, relative_path)
    if existed_before:
        if before_content is None:
            raise RuntimeError(f"缺少写前快照，无法撤销：{relative_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(before_content), encoding="utf-8")
        return

    if target.exists():
        target.unlink()
    _prune_empty_parent_dirs(target.parent, Path(root).resolve())


def run_command(root: str, command: list[str], timeout: float = 10.0) -> CommandResult:
    base = Path(root).resolve()

    if not command:
        raise ValueError("Command cannot be empty")

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
