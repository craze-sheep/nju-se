# 2048（game_show）

`game_show/` 下的 2048 小游戏，提供**网页版**和**终端版**两种玩法。

## 文件

| 文件 | 说明 |
| --- | --- |
| `2048.html` | 网页版（单文件，内联 CSS/JS，无任何依赖） |
| `2048.py` | 终端版（纯 Python，rich 可选） |
| `serve.sh` | SSH 远程一键启动网页版静态服务器 |
| `tests/core.test.js` | 网页版核心逻辑单元测试（node） |
| `README.md` | 本说明 |

---

## 场景一：本机（有图形界面）

**网页版** —— 直接双击 `game_show/2048.html`，或：

```bash
python3 -m http.server 8000
# 浏览器打开 http://localhost:8000/game_show/2048.html
```

**终端版**：

```bash
python3 game_show/2048.py
```

---

## 场景二：SSH 远程（无图形界面，推荐用终端版）

**终端版（无需任何转发，直接在 SSH 会话里玩）**：

```bash
cd /home/lzy/project/nju-逮捕在逃offer
python3 game_show/2048.py
```
- 操作：`W`/`S`/`A`/`D` 或方向键移动，`R` 重开，`Q`/`Ctrl+C` 退出
- 最高分保存在 `~/.2048_best`
- 注意：必须在**真实 SSH 交互终端**中运行（有 TTY）；在管道/脚本等非交互环境会提示"无法游玩"

**网页版（需端口转发，在本地浏览器玩）**：

远程：
```bash
bash game_show/serve.sh          # 或 python3 -m http.server 8000
```

本地（另开一个终端）：
```bash
ssh -L 8000:localhost:8000 用户名@服务器IP
```

本地浏览器打开：`http://localhost:8000/game_show/2048.html`

---

## 玩法

- 每次移动，所有方块朝指定方向滑动；相邻且相同的方块合并为它们的和。
- 每次有效移动后，在随机空位生成一个 `2` 或 `4`（`4` 的概率为 10%）。
- 合成 `2048` 即胜利；棋盘填满且无相邻相同方块时游戏结束。

## 自测

终端版核心逻辑：

```bash
python3 game_show/2048.py --selftest
```

网页版核心逻辑：

```bash
node game_show/tests/core.test.js
```

## 依赖

- 网页版：无（现代浏览器即可）
- 终端版：Python 3.9+，可选 `rich`（缺失时自动降级纯文本）
