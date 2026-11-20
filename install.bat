@echo off
cd /d "%~dp0"
echo Setting up Python environment...
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
  echo Install failed.
  pause
  exit /b 1
)
echo.
echo Done. Next steps:
echo   1) install_ffmpeg.bat  (needed only if ffmpeg is not already in ffmpeg\bin)
echo   2) build_exe.bat       (builds the portable folder)
echo Or run directly:  .venv\Scripts\python.exe app.py
pause
