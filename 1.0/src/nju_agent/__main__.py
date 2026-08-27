from pathlib import Path
import sys

from .agent import run_agent
from .config import load_settings


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    task = " ".join(args).strip()

    if not task:
        print("用法：python -m nju_agent \"你的编程任务\"")
        return 2

    try:
        settings = load_settings()
        run_agent(task, workspace_root=Path.cwd(), settings=settings)
    except RuntimeError as exc:
        print(f"错误：{exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
