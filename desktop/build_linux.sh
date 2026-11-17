#!/usr/bin/env bash
# 打包为 Linux 单文件可执行程序
set -e
cd "$(dirname "$0")"
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python
if ! "$PY" -c "import PySide6" >/dev/null 2>&1; then
  for cand in python3.12 python3.11 python3.10 python; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import PySide6" >/dev/null 2>&1; then
      PY="$cand"; break
    fi
  done
fi
"$PY" -m pip install -q pyinstaller --break-system-packages 2>/dev/null \
  || "$PY" -m pip install -q pyinstaller --user
"$PY" -m pip install -q segno --break-system-packages 2>/dev/null \
  || "$PY" -m pip install -q segno --user
"$PY" -m PyInstaller --noconfirm --clean --onefile --windowed \
  --name "PULSE_Desktop" \
  --add-data "resources/fonts:resources/fonts" \
  --add-data "design-system:design-system" \
  --hidden-import segno \
  --hidden-import pulse_core \
  --hidden-import pulse_pair_server \
  --hidden-import pulse_events \
  pulse_desktop.py
echo "[完成] 成品：dist/PULSE_Desktop"
