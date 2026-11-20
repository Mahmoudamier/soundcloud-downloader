@echo off
cd /d "%~dp0"
if exist "ffmpeg\bin\ffmpeg.exe" (
  echo ffmpeg already installed.
  pause
  exit /b 0
)
echo Downloading ffmpeg (required for MP3 conversion, about 100 MB)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; try { $zip=Join-Path $env:TEMP 'ffmpeg-release-essentials.zip'; Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile $zip -UseBasicParsing; $tmp=Join-Path $env:TEMP 'ffmpeg-extract-scd'; Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue; Expand-Archive -Path $zip -DestinationPath $tmp -Force; $exe=Get-ChildItem $tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1; if(-not $exe){throw 'ffmpeg.exe not found in archive'}; New-Item -ItemType Directory -Force -Path 'ffmpeg\bin' | Out-Null; Copy-Item $exe.FullName 'ffmpeg\bin\ffmpeg.exe' -Force; Write-Host 'ffmpeg installed.' } catch { Write-Host ('Failed: ' + $_.Exception.Message) }"
pause
