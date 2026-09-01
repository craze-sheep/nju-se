#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2048 —— 终端小游戏

玩法：用方向键（或 WASD）滑动所有方块，相邻且相同的方块碰撞后合并为它们的和，
每合并一次得分增加对应数值，目标是合成 2048。

运行：
    python game_show/2048.py
自测：
    python game_show/2048.py --selftest
"""

from __future__ import annotations

import os
import random
import sys

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    RICH_AVAILABLE = True
except Exception:  # rich 为可选依赖，缺失时降级为纯文本界面
    RICH_AVAILABLE = False

SIZE = 4
WIN_TILE = 2048
NEW_TILE_FOUR_PROB = 0.1  # 新方块为 4 的概率，其余为 2

# 数字 -> rich 样式（颜色随数值增大由深蓝过渡到亮黄）
TILE_STYLES = {
    0: "dim",
    2: "white on color(23)",
    4: "white on color(24)",
    8: "white on color(26)",
    16: "white on color(27)",
    32: "white on color(61)",
    64: "white on color(63)",
    128: "white on color(92)",
    256: "white on color(129)",
    512: "white on color(135)",
    1024: "white on color(178)",
    2048: "black on color(226)",
}

_console = Console() if RICH_AVAILABLE else None


# --------------------------------------------------------------------------
# 输入（跨平台单键读取）
# --------------------------------------------------------------------------

def _getch() -> str:
    """无回显地读取单个字符。"""
    if os.name == "nt":
        import msvcrt

        return msvcrt.getwch()
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch


def _has_more_input() -> bool:
    """判断 stdin 是否还有可读数据（用于解析方向键转义序列）。"""
    if os.name == "nt":
        import msvcrt

        return msvcrt.kbhit()
    import select

    return bool(select.select([sys.stdin], [], [], 0.05)[0])


def get_key() -> str:
    """返回规范化按键：w/a/s/d、up/down/left/right、r、q，无法识别时返回空串。"""
    ch = _getch()
    if ch in ("\x00", "\xe0"):  # Windows 功能键前缀
        ch = _getch()
        return {"H": "up", "P": "down", "M": "right", "K": "left"}.get(ch, "")
    if ch == "\x1b" and _has_more_input():  # Unix 方向键转义序列 ESC [ A/B/C/D
        seq = _getch()
        if seq == "[":
            seq += _getch()
            return {"A": "up", "B": "down", "C": "right", "D": "left"}.get(seq[1], "")
        return ""
    return ch.lower()


# --------------------------------------------------------------------------
# 核心逻辑
# --------------------------------------------------------------------------

def new_board() -> list[list[int]]:
    return [[0] * SIZE for _ in range(SIZE)]


def empty_cells(board: list[list[int]]) -> list[tuple[int, int]]:
    return [(r, c) for r in range(SIZE) for c in range(SIZE) if board[r][c] == 0]


def add_random_tile(board: list[list[int]]) -> None:
    """在随机空位放入一个 2 或 4（原地修改）。"""
    empty = empty_cells(board)
    if not empty:
        return
    r, c = random.choice(empty)
    board[r][c] = 4 if random.random() < NEW_TILE_FOUR_PROB else 2


def new_game() -> tuple[list[list[int]], int]:
    board = new_board()
    add_random_tile(board)
    add_random_tile(board)
    return board, 0


def merge_line(line: list[int]) -> tuple[list[int], int]:
    """把一行视为“向左”：先去零、再合并相邻相同值（每个值只合并一次），返回新行与得分。"""
    vals = [v for v in line if v != 0]
    out: list[int] = []
    gained = 0
    i = 0
    while i < len(vals):
        if i + 1 < len(vals) and vals[i] == vals[i + 1]:
            out.append(vals[i] * 2)
            gained += vals[i] * 2
            i += 2
        else:
            out.append(vals[i])
            i += 1
    out.extend([0] * (SIZE - len(out)))
    return out, gained


def move_left(board: list[list[int]]) -> tuple[list[list[int]], int, bool]:
    nb: list[list[int]] = []
    total = 0
    moved = False
    for row in board:
        merged, gained = merge_line(row)
        total += gained
        if merged != row:
            moved = True
        nb.append(merged)
    return nb, total, moved


def move_right(board: list[list[int]]) -> tuple[list[list[int]], int, bool]:
    rev = [list(reversed(row)) for row in board]
    nb, gained, moved = move_left(rev)
    return [list(reversed(row)) for row in nb], gained, moved


def move_up(board: list[list[int]]) -> tuple[list[list[int]], int, bool]:
    t = [list(col) for col in zip(*board)]
    nb, gained, moved = move_left(t)
    return [list(col) for col in zip(*nb)], gained, moved


def move_down(board: list[list[int]]) -> tuple[list[list[int]], int, bool]:
    flipped = list(reversed(board))
    nb, gained, moved = move_up(flipped)
    return list(reversed(nb)), gained, moved


def can_move(board: list[list[int]]) -> bool:
    """是否存在空位或可合并的相邻相同方块。"""
    for r in range(SIZE):
        for c in range(SIZE):
            if board[r][c] == 0:
                return True
            if r + 1 < SIZE and board[r][c] == board[r + 1][c]:
                return True
            if c + 1 < SIZE and board[r][c] == board[r][c + 1]:
                return True
    return False


def max_tile(board: list[list[int]]) -> int:
    return max(max(row) for row in board)


# --------------------------------------------------------------------------
# 渲染
# --------------------------------------------------------------------------

def _tile_cell(v: int) -> Text:
    if v == 0:
        return Text("·", style="dim")
    style = TILE_STYLES.get(v, TILE_STYLES[WIN_TILE])
    return Text(str(v), style=style)


def _render_plain(board: list[list[int]], score: int, best: int, status: str = "") -> None:
    os.system("cls" if os.name == "nt" else "clear")
    header = f"2048  得分 {score}  最高 {best}"
    if status:
        header += f"  {status}"
    print(header)
    cell = 6
    sep = "+" + "+".join(["-" * cell] * SIZE) + "+"
    for row in board:
        print(sep)
        print("|" + "|".join(f"{v if v else '':^{cell}}" for v in row) + "|")
    print(sep)
    print("WASD / 方向键移动 · R 重开 · Q 退出")


def render(board: list[list[int]], score: int, best: int, status: str = "") -> None:
    if RICH_AVAILABLE:
        _console.clear()
        title = f"2048  得分 {score}  最高 {best}"
        if status:
            title = f"{title}  {status}"
        table = Table(show_header=False, box=box.HEAVY, border_style="bright_black", pad_edge=False)
        for _ in range(SIZE):
            table.add_column(justify="center", width=6, vertical="middle")
        for row in board:
            table.add_row(*[_tile_cell(v) for v in row])
        _console.print(
            Panel(
                table,
                title=title,
                subtitle="WASD / 方向键移动 · R 重开 · Q 退出",
                border_style="blue",
            )
        )
    else:
        _render_plain(board, score, best, status)


# --------------------------------------------------------------------------
# 最高分持久化（存到用户目录）
# --------------------------------------------------------------------------

def _best_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".2048_best")


def load_best() -> int:
    try:
        with open(_best_path(), "r", encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def save_best(value: int) -> None:
    try:
        with open(_best_path(), "w", encoding="utf-8") as f:
            f.write(str(value))
    except OSError:
        pass


# --------------------------------------------------------------------------
# 主循环
# --------------------------------------------------------------------------

KEY_TO_DIR = {
    "w": "up", "k": "up", "up": "up",
    "s": "down", "j": "down", "down": "down",
    "a": "left", "h": "left", "left": "left",
    "d": "right", "l": "right", "right": "right",
}


def main() -> int:
    if not sys.stdin.isatty():
        print("检测到非交互式终端，无法游玩。")
        print("请直接运行：python game_show/2048.py")
        return 0

    board, score = new_game()
    best = max(load_best(), score)
    won = False
    over = False

    while True:
        status = ""
        if over:
            status = "💀 无路可走，游戏结束！按 R 重开，按 Q 退出"
        elif won:
            status = "🎉 已达成 2048！继续冲更高分？"
        render(board, score, best, status)

        key = get_key()
        if key in ("q", "\x03"):  # Q 或 Ctrl+C
            break
        if key == "r":
            board, score = new_game()
            best = max(best, score)
            won = False
            over = False
            continue

        direction = KEY_TO_DIR.get(key)
        if direction is None or over:
            continue

        new_board_, gained, moved = move(board, direction)
        if not moved:
            continue
        board, score = new_board_, score + gained
        best = max(best, score)
        add_random_tile(board)

        if not won and max_tile(board) >= WIN_TILE:
            won = True
        if not can_move(board):
            over = True

    save_best(best)
    print("再见！")
    return 0


# --------------------------------------------------------------------------
# 自测
# --------------------------------------------------------------------------

def _selftest() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        if not cond:
            failures.append(name)

    # ---- merge_line ----
    check("merge basic", merge_line([2, 2, 0, 0]) == ([4, 0, 0, 0], 4))
    check("merge four", merge_line([2, 2, 2, 2]) == ([4, 4, 0, 0], 8))
    check("merge triple", merge_line([2, 2, 2, 0]) == ([4, 2, 0, 0], 4))
    check("merge gap", merge_line([2, 0, 2, 2]) == ([4, 2, 0, 0], 4))
    check("merge distinct", merge_line([2, 4, 8, 16]) == ([2, 4, 8, 16], 0))
    check("merge empty", merge_line([0, 0, 0, 0]) == ([0, 0, 0, 0], 0))
    check("merge adjacent", merge_line([4, 4, 8, 0]) == ([8, 8, 0, 0], 8))

    # ---- move ----
    b = [[2, 2, 4, 0], [0, 0, 0, 0], [2, 0, 2, 4], [0, 0, 0, 0]]
    nb, gained, moved = move_left(b)
    check("left board", nb[0] == [4, 4, 0, 0] and nb[2] == [4, 4, 0, 0])
    check("left gain", gained == 8)
    check("left moved", moved is True)

    nb, gained, moved = move_right([[2, 2, 4, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
    check("right board", nb[0] == [0, 0, 4, 4])
    check("right gain", gained == 4)
    check("right moved", moved is True)

    b = [[2, 0, 0, 0], [2, 4, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    nb, gained, moved = move_up(b)
    check("up board", nb[0] == [4, 4, 0, 0] and nb[1][0] == 0)
    check("up gain", gained == 4)
    check("up moved", moved is True)

    b = [[2, 0, 0, 0], [2, 4, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    nb, gained, moved = move_down(b)
    check("down board", nb[3] == [4, 4, 0, 0] and nb[0][0] == 0)
    check("down gain", gained == 4)
    check("down moved", moved is True)

    check(
        "no-move left",
        move_left([[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]])[2] is False,
    )

    # ---- can_move ----
    check(
        "can_move full-blocked",
        can_move([[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]]) is False,
    )
    check(
        "can_move adjacent",
        can_move([[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 4]]) is True,
    )
    check(
        "can_move empty",
        can_move([[2, 4, 2, 4], [4, 2, 4, 2], [2, 0, 2, 4], [4, 2, 4, 2]]) is True,
    )

    # ---- add_random_tile ----
    b = [[0] * SIZE for _ in range(SIZE)]
    add_random_tile(b)
    check("tile inserted once", sum(sum(row) for row in b) in (2, 4))

    # ---- max_tile ----
    check(
        "max_tile",
        max_tile([[2, 8, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]) == 8,
    )

    if failures:
        print(f"[FAIL] {len(failures)} 项未通过: {failures}")
        return 1
    print("[OK] 全部断言通过 ✓")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        sys.exit(_selftest())
    sys.exit(main())
