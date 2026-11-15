@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   打包为 Windows 单文件可执行程序 (.exe)
echo ============================================
python -m pip install --disable-pip-version-check -q pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "PULSE_Agent_Studio" ^
  --add-data "resources/fonts;resources/fonts" ^
  --add-data "design-system;design-system" ^
  --hidden-import segno ^
  --hidden-import pulse_core ^
  --hidden-import pulse_glass ^
  --hidden-import pulse_pair_server ^
  pulse_studio.py
echo.
if exist "dist\PULSE_Agent_Studio.exe" (
  echo [完成] 成品：dist\PULSE_Agent_Studio.exe
  echo 可直接双击运行，无需安装 Python。
) else (
  echo [失败] 请查看上方 PyInstaller 输出。
)
pause
