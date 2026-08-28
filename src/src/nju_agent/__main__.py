from pathlib import Path
import sys

from .agent import run_chat_session
from .config import load_settings


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv

    try:
        settings = load_settings()
        if args:
            print("当前版本只支持直接启动交互式对话：python -m nju_agent")
        run_chat_session(workspace_root=Path.cwd(), settings=settings)
    except RuntimeError as exc:
        print(f"错误：{exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
