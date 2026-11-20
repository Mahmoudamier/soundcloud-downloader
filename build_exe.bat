@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run install.bat first.
  pause
  exit /b 1
)
echo Building Windows executable...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --icon "logo.ico" --name "SoundCloud Downloader" app.py
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)

set "OUT=dist\SoundCloud Downloader"
if exist "ffmpeg\bin\ffmpeg.exe" (
  if not exist "%OUT%\ffmpeg\bin" mkdir "%OUT%\ffmpeg\bin"
  copy /Y "ffmpeg\bin\ffmpeg.exe" "%OUT%\ffmpeg\bin\ffmpeg.exe" >nul
) else (
  echo Warning: ffmpeg\bin\ffmpeg.exe not found. MP3 conversion will not work.
)
copy /Y "logo.ico" "%OUT%\" >nul
copy /Y "logo.png" "%OUT%\" >nul
copy /Y "README.md" "%OUT%\" >nul
echo.
echo Built: %OUT%\SoundCloud Downloader.exe
echo Copy the whole "%OUT%" folder to any Windows PC - it is fully portable.
pause
