import difflib
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
from typing import Iterable


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


_SEARCH_IGNORED_DIRS = {
    ".git",
    ".nju_agent",
    ".pytest_cache",
    ".mypy_cache",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
}


def _iter_searchable_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            name for name in dirnames if name not in _SEARCH_IGNORED_DIRS
        )
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            if path.name in _SEARCH_IGNORED_DIRS:
                continue
            yield path


def _search_preview(line: str, terms: list[str]) -> str:
    text = line.rstrip("\n")
    if len(text) <= 240:
        return text

    lower_text = text.casefold()
    match_index = -1
    for term in terms:
        position = lower_text.find(term)
        if position != -1 and (match_index == -1 or position < match_index):
            match_index = position

    if match_index == -1:
        return text[:237] + "..."

    start = max(0, match_index - 60)
    end = min(len(text), match_index + 140)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def search_files(root: str, query: str, limit: int = 20) -> list[dict[str, object]]:
    base = Path(root).resolve()
    terms = [part.casefold() for part in query.split() if part.strip()]
    if not terms or limit <= 0:
        return []

    results: list[dict[str, object]] = []
    for path in _iter_searchable_files(base):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        relative_path = path.relative_to(base).as_posix()
        path_lower = relative_path.casefold()
        if all(term in path_lower for term in terms):
            results.append(
                {
                    "relative_path": relative_path,
                    "line_number": 0,
                    "line_text": "",
                    "match_kind": "path",
                }
            )
            if len(results) >= limit:
                return results
            continue

        for line_number, line in enumerate(text.splitlines(), start=1):
            line_lower = line.casefold()
            if all(term in line_lower for term in terms):
                results.append(
                    {
                        "relative_path": relative_path,
                        "line_number": line_number,
                        "line_text": _search_preview(line, terms),
                        "match_kind": "content",
                    }
                )
                if len(results) >= limit:
                    return results
                break

    return results


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
