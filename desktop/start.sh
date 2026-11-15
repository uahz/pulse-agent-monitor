#!/usr/bin/env bash
# PULSE · Agent Studio — Linux / macOS 启动脚本（v2.0.0 全新界面）
# 如需回退 v1.3.0 旧界面，请手动运行：python3 pulse_agent_console.py
set -e
cd "$(dirname "$0")"
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python
# 部分系统并存多个 Python，优先选已装 PySide6 的解释器
if ! "$PY" -c "import PySide6" >/dev/null 2>&1; then
  for cand in python3.12 python3.11 python3.10 python; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import PySide6" >/dev/null 2>&1; then
      PY="$cand"; break
    fi
  done
fi
if ! "$PY" -c "import PySide6" >/dev/null 2>&1; then
  echo "正在安装依赖 PySide6-Essentials ..."
  "$PY" -m pip install -q -r requirements.txt --break-system-packages 2>/dev/null \
    || "$PY" -m pip install -q -r requirements.txt --user
fi
exec "$PY" pulse_studio.py "$@"
