import sys


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    task = " ".join(args).strip()

    if not task:
        print("用法：python -m nju_agent \"你的编程任务\"")
        return 2

    print(f"用户任务：{task}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
