from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


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


def write_file(root: str, relative_path: str, content: str) -> None:
    target = _safe_path(root, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


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
