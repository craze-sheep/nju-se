from dataclasses import dataclass
import hashlib
import os
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


_SANDBOX_IMAGE = "nju-agent-sandbox:latest"
_SANDBOX_WORKDIR = "/workspace"
_SANDBOX_CONTAINER_PREFIX = "nju_agent_sandbox"


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


def _sandbox_mode() -> str:
    return os.environ.get("NJU_AGENT_RUN_COMMAND_MODE", "docker").strip().lower()


def _sandbox_image() -> str:
    return os.environ.get("NJU_AGENT_SANDBOX_IMAGE", _SANDBOX_IMAGE).strip() or _SANDBOX_IMAGE


def _sandbox_dockerfile_path() -> Path:
    return Path(__file__).resolve().parents[2] / "docker" / "sandbox.Dockerfile"


def _workspace_hash(root: str) -> str:
    return hashlib.sha256(str(Path(root).resolve()).encode("utf-8")).hexdigest()[:12]


def _sandbox_container_name(root: str) -> str:
    return f"{_SANDBOX_CONTAINER_PREFIX}_{_workspace_hash(root)}"


def _docker(args: list[str], *, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return _subprocess_run(["docker", *args], timeout=timeout)


def _docker_inspect_text(args: list[str]) -> str | None:
    result = _docker(args, timeout=30)
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    return text or None


def _ensure_sandbox_image(image: str) -> None:
    if _docker(["image", "inspect", image], timeout=30).returncode == 0:
        return

    dockerfile = _sandbox_dockerfile_path()
    if not dockerfile.exists():
        raise RuntimeError(f"Sandbox Dockerfile not found: {dockerfile}")

    result = _docker(
        ["build", "-t", image, "-f", str(dockerfile), str(dockerfile.parent)],
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Failed to build sandbox image")


def _create_sandbox_container(root: str, image: str, container: str) -> None:
    base = Path(root).resolve()
    uid = getattr(os, "getuid", lambda: 0)()
    gid = getattr(os, "getgid", lambda: 0)()
    result = _docker(
        [
            "run",
            "-d",
            "--name",
            container,
            "--network",
            "none",
            "--cap-drop=ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "128",
            "--memory",
            "1g",
            "--cpus",
            "1",
            "--user",
            f"{uid}:{gid}",
            "-e",
            "HOME=/tmp",
            "-e",
            "TMPDIR=/tmp",
            "-v",
            f"{base}:/workspace:rw",
            "-w",
            _SANDBOX_WORKDIR,
            image,
            "sleep",
            "infinity",
        ],
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Failed to create sandbox container")


def _ensure_sandbox_container(root: str) -> str:
    image = _sandbox_image()
    container = _sandbox_container_name(root)
    _ensure_sandbox_image(image)

    existing_image = _docker_inspect_text(["container", "inspect", "--format", "{{.Config.Image}}", container])
    if existing_image and existing_image != image:
        _docker(["rm", "-f", container], timeout=30)
        existing_image = None

    status = None if existing_image is None else _docker_inspect_text(
        ["container", "inspect", "--format", "{{.State.Status}}", container]
    )
    if not status:
        _create_sandbox_container(root, image, container)
        return container

    if status != "running":
        result = _docker(["start", container], timeout=30)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"Failed to start sandbox container {container}")

    return container


def list_files(root: str) -> list[str]:
    base = Path(root).resolve()
    return sorted(path.name for path in base.iterdir())


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

    if not command:
        raise ValueError("Command cannot be empty")

    if _sandbox_mode() == "local":
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

    if _sandbox_mode() != "docker":
        raise RuntimeError("NJU_AGENT_RUN_COMMAND_MODE must be 'docker' or 'local'")

    container = _ensure_sandbox_container(str(base))
    uid = getattr(os, "getuid", lambda: 0)()
    gid = getattr(os, "getgid", lambda: 0)()
    docker_timeout = max(float(timeout) + 5.0, 10.0)
    result = _docker(
        [
            "exec",
            "-u",
            f"{uid}:{gid}",
            "-e",
            "HOME=/tmp",
            "-e",
            "TMPDIR=/tmp",
            "-w",
            _SANDBOX_WORKDIR,
            container,
            "timeout",
            "--kill-after=5s",
            "--signal=KILL",
            f"{float(timeout)}s",
            *command,
        ],
        timeout=docker_timeout,
    )
    if result.returncode in {124, 137}:
        raise TimeoutError(f"Command timed out after {timeout} seconds")

    if result.returncode < 0:
        raise RuntimeError(f"Sandbox command failed: {result.stderr.strip() or result.stdout.strip()}")

    try:
        stdout = result.stdout
        stderr = result.stderr
    except AttributeError as exc:
        raise RuntimeError("Sandbox command returned unexpected result") from exc

    return CommandResult(
        exit_code=result.returncode,
        stdout=stdout,
        stderr=stderr,
    )
