@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   PULSE Desktop -^> Windows single-file .exe
echo ============================================
python -m pip install --disable-pip-version-check -q pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "PULSE_Desktop" ^
  --add-data "resources/fonts;resources/fonts" ^
  --add-data "design-system;design-system" ^
  --hidden-import segno ^
  --hidden-import pulse_core ^
  --hidden-import pulse_pair_server ^
  --hidden-import pulse_events ^
  pulse_desktop.py
echo.
if exist "dist\PULSE_Desktop.exe" (
  echo [OK] dist\PULSE_Desktop.exe
) else (
  echo [FAIL] see PyInstaller output above.
  exit /b 1
)
