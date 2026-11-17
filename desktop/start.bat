@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   PULSE · Desktop  (Windows 启动)
echo ============================================
where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未检测到 Python。请安装 Python 3.10+ 并勾选 "Add Python to PATH"。
  pause
  exit /b 1
)
python -c "import PySide6" >nul 2>nul
if errorlevel 1 (
  echo 正在安装依赖 PySide6-Essentials ...
  python -m pip install --disable-pip-version-check -q -r requirements.txt
  if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
  )
)
echo 启动中 ...
python pulse_studio.py %*
if errorlevel 1 pause
