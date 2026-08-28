from pathlib import Path

from .agent import run_chat_session
from .config import load_settings


def main(argv: list[str] | None = None) -> int:
    try:
        settings = load_settings()
        run_chat_session(workspace_root=Path.cwd(), settings=settings)
    except RuntimeError as exc:
        print(f"错误：{exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
