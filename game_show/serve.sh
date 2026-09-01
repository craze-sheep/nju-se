#!/usr/bin/env bash
# 在远程（SSH）环境启动 2048 网页版静态服务器。
# 用法：
#   远程：bash game_show/serve.sh
#   本地：ssh -L 8000:localhost:8000 用户@服务器IP
#   然后浏览器打开 http://localhost:8000/game_show/2048.html
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${1:-8000}"
echo "2048 网页版已启动: http://localhost:${PORT}/game_show/2048.html"
echo "（本地浏览器访问前，请先在本机执行 ssh -L ${PORT}:localhost:${PORT} 用户@服务器IP）"
exec python3 -m http.server "${PORT}" --bind 0.0.0.0
