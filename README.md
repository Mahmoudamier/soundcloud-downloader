# SoundCloud Downloader

<div dir="rtl">

**رابط SoundCloud ← ملف MP3 على جهازك**

برنامج ويندوز صغير وخفيف: الصق رابط أو أكتر، اختار مجلد الحفظ، واضغط تنزيل.
بياخد **أفضل جودة صوت متاحة** ويحوّلها تلقائياً إلى **MP3** من غير أي إعدادات.
الواجهة عربية RTL بتصميم عصري شبيه بويندوز 11، والبرنامج **محمول** — من غير تثبيت أو بايثون أو PowerShell.

### الاستخدام
1. الصق الرابط في مربع الروابط (رابط في كل سطر).
2. اختار مجلد الحفظ.
3. اضغط **تنزيل**.

`Ctrl+V` و `Shift+Insert` بيشتغلوا من أي مكان في النافذة، و `Ctrl+Enter` يبدأ التنزيل مباشرة.

</div>

## Features

- Automatic best-quality audio → **MP3 (320 kbps)** using the bundled `ffmpeg`.
- Multiple links, one per line; playlists are saved into their own subfolder.
- Paste button, keyboard shortcuts, and right-click paste.
- Modern Windows 11-style light UI with proper Arabic RTL layout.
- Live progress, colored log panel, and Stop (finishes the current file).
- Remembers the last download folder in `%APPDATA%\SoundCloudDownloader\settings.json`.
- Portable: copy the whole folder to any Windows PC or USB drive and run it.

## Download (recommended)

Download **`SoundCloud-Downloader-portable.zip`** from the [latest release](../../releases/latest),
extract the **whole folder**, then double-click **`SoundCloud Downloader.exe`**.
Nothing needs to be installed. Do not delete `_internal` or `ffmpeg\bin\ffmpeg.exe`.

## Build from source

Requirements: Windows 10/11 and Python 3.10+.

```bat
install.bat
install_ffmpeg.bat
build_exe.bat
```

- `install.bat` creates `.venv` and installs `yt-dlp` + `PyInstaller`.
- `install_ffmpeg.bat` downloads `ffmpeg.exe` into `ffmpeg\bin` (skip if you already have it).
- `build_exe.bat` creates `dist\SoundCloud Downloader\`.

To run directly from source without building:

```bat
.venv\Scripts\python.exe app.py
```

## Project layout

| Path | Purpose |
|---|---|
| `app.py` | Full application (UI + download logic) |
| `logo.ico` / `logo.png` | Application icon (embedded in the exe and used in the UI) |
| `install.bat` | Creates the virtual environment and installs Python packages |
| `install_ffmpeg.bat` | Downloads `ffmpeg.exe` for MP3 conversion |
| `build_exe.bat` | Builds the portable Windows folder with PyInstaller |
| `requirements.txt` | Python dependencies |

> `ffmpeg.exe` is ~105 MB and is **not** stored in this repository (GitHub's 100 MB file limit).
> It is included in the portable ZIP attached to each release.

## Legal note

Use this tool only for tracks you own or that are explicitly allowed to be downloaded.
Respect copyright holders and SoundCloud's terms of service.
