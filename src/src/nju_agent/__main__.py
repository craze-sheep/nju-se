import argparse
from pathlib import Path

from .agent import _finalize_snapshot_file, run_chat_session
from .config import load_settings


def main(argv: list[str] | None = None) -> int:
    try:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--finalize-snapshot")
        args, _ = parser.parse_known_args(argv)
        if args.finalize_snapshot:
            _finalize_snapshot_file(Path(args.finalize_snapshot))
            return 0
        settings = load_settings()
        run_chat_session(
            workspace_root=Path.cwd(),
            settings=settings,
            background_finalize=True,
        )
    except RuntimeError as exc:
        print(f"错误：{exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
