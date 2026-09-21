#!/bin/bash
# 双击启动本地工作台；已经在跑就只打开浏览器
cd "$(dirname "$0")"
if lsof -nP -iTCP:8810 -sTCP:LISTEN >/dev/null 2>&1; then open "http://localhost:8810"; exit 0; fi
( sleep 1.2; open "http://localhost:8810" ) &
exec python3 工作台/app.py
