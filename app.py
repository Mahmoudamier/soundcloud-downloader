# -*- coding: utf-8 -*-
"""SoundCloud Downloader - desktop GUI built on yt-dlp."""

import ctypes
import json
import os
import queue
import re
import shutil
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import yt_dlp
except ImportError:
    tk.messagebox.showerror(
        "مكتبة ناقصة", "yt-dlp غير مثبت. شغّل install.bat أولاً."
    )
    sys.exit(1)


APP_NAME = "SoundCloud Downloader"
try:
    # يخلي شريط المهام يظهر أيقونة البرنامج مش أيقونة بايثون/باورشيل
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Rakkeb.SoundCloudDownloader.1")
except Exception:
    pass

BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
SETTINGS_DIR = os.path.join(os.environ.get("APPDATA", BASE_DIR), "SoundCloudDownloader")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")


def find_ffmpeg():
    local = os.path.join(BASE_DIR, "ffmpeg", "bin", "ffmpeg.exe")
    if os.path.isfile(local):
        return local
    return shutil.which("ffmpeg")


def resource_path(name):
    """Find a file shipped next to the app (works frozen and from source)."""
    candidates = [
        os.path.join(BASE_DIR, name),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), name),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return candidates[0]


def safe_name(text, max_len=80):
    text = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", str(text or "")).strip()
    text = re.sub(r"\s+", " ", text)
    return (text[:max_len] or "playlist")


def extract_links(raw):
    """Pull links out of pasted text, even with labels or missing https://."""
    found = []
    patterns = (
        r"(?:https?://)?(?:www\.)?(?:on\.)?soundcloud\.com/[^\s<>\"'،؛]+",
        r"https?://[^\s<>\"'،؛]+",
    )
    for line in (raw or "").splitlines():
        line_links = []
        for pattern in patterns:
            for match in re.findall(pattern, line, flags=re.I):
                url = match.rstrip(".,;:!?)]}،؛")
                if not re.match(r"^https?://", url, re.I):
                    url = "https://" + url
                if url not in line_links:
                    line_links.append(url)
            if line_links:
                break
        for url in line_links:
            if url not in found:
                found.append(url)
    return found


class QueueLogger:
    def __init__(self, q):
        self.q = q

    def _send(self, msg, kind="log"):
        msg = str(msg).strip()
        if not msg:
            return
        if msg.startswith("[download]") or msg.startswith("[ExtractAudio]"):
            return
        self.q.put((kind, msg))

    def debug(self, msg):
        self._send(msg)

    def info(self, msg):
        self._send(msg)

    def warning(self, msg):
        self._send(msg, "warn")

    def error(self, msg):
        self._send(msg, "error")


class Downloader:
    def __init__(self, urls, out_dir, q, stop_event):
        self.urls = urls
        self.out_dir = out_dir
        self.q = q
        self.stop_event = stop_event
        self.ffmpeg = find_ffmpeg()
        self.ok = 0
        self.failed = 0
        self.last_pct = -1

    def log(self, msg, kind="log"):
        self.q.put((kind, msg))

    def base_opts(self, outtmpl, quiet=False):
        opts = {
            "outtmpl": outtmpl,
            "format": "bestaudio/best",
            "quiet": quiet,
            "no_warnings": quiet,
            "noplaylist": False,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 25,
            "logger": QueueLogger(self.q),
            "progress_hooks": [self.on_progress],
            "overwrites": False,
            "concurrent_fragment_downloads": 2,
        }
        # دايمًا MP3 بأعلى جودة متاحة من الملف الـ SoundCloud بيقدّمه
        opts["ffmpeg_location"] = self.ffmpeg
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320",
        }]
        return opts

    def on_progress(self, d):
        if self.stop_event.is_set():
            raise yt_dlp.DownloadError("تم الإيقاف من المستخدم")
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            pct = (done / total * 100) if total else 0
            now = time.monotonic()
            if abs(pct - self.last_pct) >= 0.5 or now - self.last_pct_time > 0.4:
                self.last_pct = pct
                self.last_pct_time = now
                info = d.get("info_dict") or {}
                self.q.put(("progress", {
                    "pct": pct,
                    "title": info.get("title") or "",
                    "speed": d.get("speed"),
                }))
        elif d.get("status") == "finished":
            info = d.get("info_dict") or {}
            self.q.put(("item_done", info.get("title") or ""))

    last_pct_time = 0.0

    def run(self):
        if not self.ffmpeg:
            self.log("ffmpeg غير موجود جوّه المجلد — التحويل لـ MP3 مش هيشتغل.", "error")
            self.q.put(("done", (0, len(self.urls), True)))
            return

        os.makedirs(self.out_dir, exist_ok=True)

        for index, url in enumerate(self.urls, 1):
            if self.stop_event.is_set():
                break
            self.q.put(("start_item", (index, len(self.urls), url)))

            try:
                # أولاً: نعرف لو الرابط قائمة تشغيل ولا مقطع مفرد عشان نختار مجلد الحفظ
                probe_opts = self.base_opts("%(title)s.%(ext)s", quiet=True)
                probe_opts.pop("progress_hooks", None)
                with yt_dlp.YoutubeDL(probe_opts) as probe_ydl:
                    probe = probe_ydl.extract_info(url, download=False, process=False)

                is_playlist = bool(probe and (probe.get("_type") == "playlist" or probe.get("entries")))
                if is_playlist:
                    folder = safe_name(probe.get("title") or "playlist")
                    outtmpl = os.path.join(self.out_dir, folder, "%(title)s.%(ext)s")
                    self.log("قائمة تشغيل: " + (probe.get("title") or folder))
                else:
                    outtmpl = os.path.join(self.out_dir, "%(title)s.%(ext)s")

                self.last_pct = -1
                with yt_dlp.YoutubeDL(self.base_opts(outtmpl)) as ydl:
                    ydl.extract_info(url, download=True)

                self.ok += 1
            except yt_dlp.DownloadError as exc:
                if self.stop_event.is_set():
                    self.log("تم إيقاف التنزيل.", "warn")
                    break
                self.failed += 1
                self.log("فشل: " + str(exc), "error")
            except Exception as exc:  # noqa: BLE001
                self.failed += 1
                self.log("خطأ غير متوقع: " + str(exc), "error")

        self.q.put(("done", (self.ok, self.failed, self.stop_event.is_set())))


class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.settings = self.load_settings()

        root.title(APP_NAME)
        root.geometry("900x700")
        root.minsize(760, 600)
        ico_path = resource_path("logo.ico")
        if os.path.isfile(ico_path):
            try:
                root.iconbitmap(ico_path)
            except Exception:
                pass

        self._setup_styles()
        self.build_ui()
        self.root.after(100, self.pump)

    # ---------- Styling ----------
    def _setup_styles(self):
        s = self.style = ttk.Style()
        try:
            s.theme_use("clam")
        except Exception:
            pass

        bg = "#F5F5F7"
        surface = "#FFFFFF"
        border = "#E0E0E5"
        text = "#1C1C1E"
        muted = "#6E6E73"
        orange = "#FF5500"
        self.status_colors = {
            "idle": muted,
            "busy": orange,
            "ok": "#107C10",
            "warn": "#9D6200",
            "error": "#C4314B",
        }

        self.font_ui = ("Segoe UI", 10)
        self.font_sm = ("Cairo", "IBM Plex Sans Arabic", "Segoe UI", 9)
        self.font_section = ("Cairo", "IBM Plex Sans Arabic", "Segoe UI", 10, "bold")
        self.font_title = ("Segoe UI", 16, "bold")
        self.font_mono = ("Consolas", 9)

        def cfg(name, **kw):
            try:
                s.configure(name, **kw)
            except tk.TclError:
                pass

        def mp(name, **kw):
            try:
                s.map(name, **kw)
            except tk.TclError:
                pass

        cfg(".", background=bg, foreground=text, font=self.font_ui)
        cfg("TFrame", background=bg)
        cfg("Surface.TFrame", background=surface)
        cfg("Card.TFrame", background=surface, bordercolor=border, borderwidth=1, relief="solid")
        cfg("Divider.TFrame", background=border)

        cfg("TLabel", background=bg, foreground=text, font=self.font_ui)
        cfg("Card.TLabel", background=surface, foreground=text, font=self.font_ui)
        cfg("Title.TLabel", background=bg, foreground=text, font=self.font_title)
        cfg("Subtitle.TLabel", background=bg, foreground=muted, font=self.font_sm)
        cfg("Section.TLabel", background=bg, foreground="#2C2C2E", font=self.font_section)
        cfg("CardSection.TLabel", background=surface, foreground="#2C2C2E", font=self.font_section)
        cfg("Hint.TLabel", background=bg, foreground="#8E8E93", font=self.font_sm)
        cfg("CardHint.TLabel", background=surface, foreground="#8E8E93", font=self.font_sm)

        cfg("TButton", font=self.font_ui, padding=(12, 7), background=surface,
            foreground=text, bordercolor="#C7C7CC", lightcolor="#C7C7CC",
            darkcolor="#C7C7CC", relief="solid", borderwidth=1)
        mp("TButton",
           background=[("active", "#F2F2F5"), ("disabled", "#F2F2F5")],
           foreground=[("disabled", "#AEAEB2")],
           bordercolor=[("disabled", "#E8E8ED")])

        cfg("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 8),
            background=orange, foreground="#FFFFFF", bordercolor=orange,
            lightcolor=orange, darkcolor=orange, relief="solid", borderwidth=1)
        mp("Accent.TButton",
           background=[("active", "#E64E00"), ("pressed", "#CC4400"), ("disabled", "#F6E3DA")],
           foreground=[("disabled", "#C4A99F")],
           bordercolor=[("disabled", "#F6E3DA")])

        cfg("Danger.TButton", font=self.font_ui, padding=(12, 7), background=surface,
            foreground="#C4314B", bordercolor="#E3B9C0", lightcolor="#E3B9C0",
            darkcolor="#E3B9C0", relief="solid", borderwidth=1)
        mp("Danger.TButton",
           background=[("active", "#FDECEF"), ("disabled", "#F2F2F5")],
           foreground=[("disabled", "#C9C9CE")],
           bordercolor=[("disabled", "#E8E8ED")])

        cfg("Subtle.TButton", font=self.font_sm, padding=(6, 4), background=bg,
            foreground=muted, bordercolor=bg, lightcolor=bg, darkcolor=bg,
            relief="flat", borderwidth=0)
        mp("Subtle.TButton",
           background=[("active", "#E8E8ED"), ("disabled", bg)],
           foreground=[("disabled", "#C7C7CC")])

        cfg("TEntry", fieldbackground=surface, foreground=text,
            bordercolor="#C7C7CC", lightcolor="#C7C7CC", darkcolor="#C7C7CC",
            insertcolor=text, borderwidth=1, padding=(10, 8))

        cfg("Horizontal.TProgressbar", troughcolor="#E8E8ED", background=orange,
            bordercolor="#E8E8ED", lightcolor="#E8E8ED", darkcolor="#E8E8ED",
            thickness=8, borderwidth=0)

        cfg("Vertical.TScrollbar", background="#C7C7CC", troughcolor="#F2F2F5",
            bordercolor="#F2F2F5", arrowcolor="#8E8E93", borderwidth=0)
        mp("Vertical.TScrollbar", background=[("active", "#AEAEB2")])
        cfg("Dark.Vertical.TScrollbar", background="#4A4A55", troughcolor="#1E1E24",
            bordercolor="#1E1E24", arrowcolor="#9A9AA5", borderwidth=0)
        mp("Dark.Vertical.TScrollbar", background=[("active", "#5E5E6B")])

    # ---------- UI ----------
    def build_ui(self):
        main = ttk.Frame(self.root, padding=(22, 18))
        main.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)

        # ---- Header ----
        header = ttk.Frame(main)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        text_block = ttk.Frame(header)
        text_block.grid(row=0, column=0, sticky="ew")
        text_block.columnconfigure(0, weight=1)
        ttk.Label(text_block, text=APP_NAME, style="Title.TLabel").grid(
            row=0, column=0, sticky="e"
        )
        ttk.Label(
            text_block,
            text="الصق روابط SoundCloud وحمّلها MP3 بأفضل جودة تلقائياً",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="e", pady=(3, 0))
        self.logo_img = None
        logo_path = resource_path("logo.png")
        if os.path.isfile(logo_path):
            try:
                self.logo_img = tk.PhotoImage(file=logo_path).subsample(5, 5)
                ttk.Label(header, image=self.logo_img, style="Card.TLabel").grid(
                    row=0, column=1, sticky="e", padx=(16, 0)
                )
            except Exception:
                self.logo_img = None

        ttk.Frame(main, style="Divider.TFrame", height=1).grid(
            row=1, column=0, sticky="ew"
        )

        # ---- Links (main focus) ----
        links = ttk.Frame(main, style="Card.TFrame")
        links.grid(row=2, column=0, sticky="nsew", pady=(16, 0))
        links.columnconfigure(0, weight=1)
        links.rowconfigure(0, weight=1)
        link_inner = ttk.Frame(links, style="Surface.TFrame", padding=(16, 14))
        link_inner.grid(row=0, column=0, sticky="nsew")
        link_inner.columnconfigure(1, weight=1)
        link_inner.rowconfigure(1, weight=1)

        ttk.Button(link_inner, text="لصق", command=self.paste_urls).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(link_inner, text="الروابط", style="CardSection.TLabel").grid(
            row=0, column=1, sticky="e"
        )
        self.url_text = tk.Text(
            link_inner, height=6, wrap="word", font=self.font_mono,
            bg="#FFFFFF", fg="#1C1C1E", insertbackground="#FF5500",
            relief="flat", borderwidth=0, highlightthickness=1,
            highlightbackground="#C7C7CC", highlightcolor="#FF5500",
            padx=12, pady=10, selectbackground="#FFD9CC",
        )
        self.url_text.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        self.url_text.focus_set()
        self.url_text.bind("<Control-Return>", lambda e: self.start_download())
        self.url_text.bind("<Control-v>", self.paste_urls)
        self.url_text.bind("<Control-V>", self.paste_urls)
        self.url_text.bind("<Shift-Insert>", self.paste_urls)
        self.root.bind("<Control-v>", lambda e: self._global_paste(e, quiet=True), add="+")
        self.root.bind("<Control-V>", lambda e: self._global_paste(e, quiet=True), add="+")
        self.root.bind("<Shift-Insert>", lambda e: self._global_paste(e, quiet=True), add="+")
        self.attach_context_menu(self.url_text)
        ttk.Label(
            link_inner,
            text="رابط في كل سطر   •   Ctrl+V للصق   •   Ctrl+Enter للبدء",
            style="CardHint.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="e", pady=(8, 0))

        # ---- Folder ----
        ttk.Label(main, text="مجلد الحفظ", style="Section.TLabel").grid(
            row=3, column=0, sticky="e", pady=(16, 6)
        )
        folder_row = ttk.Frame(main)
        folder_row.grid(row=4, column=0, sticky="ew")
        folder_row.columnconfigure(0, weight=1)
        self.out_var = tk.StringVar(
            value=self.settings.get("out_dir", os.path.join(os.path.expanduser("~"), "Desktop", "SoundCloud Downloads"))
        )
        self.out_entry = ttk.Entry(folder_row, textvariable=self.out_var)
        self.out_entry.grid(row=0, column=0, sticky="ew")
        self.attach_context_menu(self.out_entry)
        ttk.Button(folder_row, text="فتح", command=self.open_dir, width=8).grid(
            row=0, column=1, padx=(8, 0)
        )
        ttk.Button(folder_row, text="اختيار...", command=self.choose_dir, width=11).grid(
            row=0, column=2, padx=(8, 0)
        )

        ttk.Label(
            main,
            text="التنزيل دايمًا MP3 بأفضل جودة متاحة — من غير أي إعدادات",
            style="Hint.TLabel",
        ).grid(row=5, column=0, sticky="e", pady=(8, 0))

        # ---- Actions ----
        actions = ttk.Frame(main)
        actions.grid(row=6, column=0, sticky="ew", pady=(14, 10))
        actions.columnconfigure(0, weight=1)
        ttk.Button(
            actions, text="مسح السجل", style="Subtle.TButton",
            command=lambda: self.log_text.delete("1.0", "end"),
        ).grid(row=0, column=0, sticky="w")
        self.stop_btn = ttk.Button(
            actions, text="⏹ إيقاف", command=self.stop_download,
            style="Danger.TButton", state="disabled",
        )
        self.stop_btn.grid(row=0, column=1, padx=(8, 0))
        self.download_btn = ttk.Button(
            actions, text="⬇ تنزيل", command=self.start_download, style="Accent.TButton",
        )
        self.download_btn.grid(row=0, column=2, padx=(8, 0))

        # ---- Status + progress ----
        status_row = ttk.Frame(main)
        status_row.grid(row=7, column=0, sticky="ew")
        status_row.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="جاهز للتنزيل")
        ttk.Label(status_row, textvariable=self.status_var).grid(
            row=0, column=0, sticky="e"
        )
        self.status_dot = tk.Label(
            status_row, text="●", font=("Segoe UI", 11, "bold"),
            fg=self.status_colors["idle"], bg="#F5F5F7",
        )
        self.status_dot.grid(row=0, column=1, sticky="e", padx=(0, 8))
        self.pbar = ttk.Progressbar(main, mode="determinate", maximum=100)
        self.pbar.grid(row=8, column=0, sticky="ew", pady=(8, 0))

        # ---- Log ----
        ttk.Label(main, text="سجل التنزيل", style="Section.TLabel").grid(
            row=9, column=0, sticky="e", pady=(16, 6)
        )
        log_wrap = tk.Frame(
            main, bg="#1E1E24", highlightbackground="#2E2E35", highlightthickness=1
        )
        log_wrap.grid(row=10, column=0, sticky="nsew")
        log_wrap.columnconfigure(0, weight=1)
        log_wrap.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_wrap, height=10, wrap="word", font=self.font_mono,
            bg="#1E1E24", fg="#D4D4D8", insertbackground="#FFFFFF",
            relief="flat", borderwidth=0, padx=12, pady=10,
            selectbackground="#3A3A45",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(
            log_wrap, orient="vertical", command=self.log_text.yview,
            style="Dark.Vertical.TScrollbar",
        )
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.tag_config("error", foreground="#FF6B6B")
        self.log_text.tag_config("warn", foreground="#FFCC66")
        self.log_text.tag_config("ok", foreground="#6FE08A")
        self.log_text.tag_config("info", foreground="#8AB4F8")

        ttk.Label(
            main,
            text="استخدم البرنامج لتنزيل ما تملكه أو ما يسمح صاحبه بالتنزيل فقط.",
            style="Hint.TLabel",
        ).grid(row=11, column=0, sticky="e", pady=(10, 0))

        main.rowconfigure(2, weight=1)
        main.rowconfigure(10, weight=1)

    def set_status(self, text, kind="idle"):
        self.status_var.set(text)
        try:
            self.status_dot.configure(
                foreground=self.status_colors.get(kind, self.status_colors["idle"])
            )
        except Exception:
            pass

    # ---------- clipboard helpers ----------
    def attach_context_menu(self, widget):
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(label="لصق", command=lambda: self.paste_into(widget))
        menu.add_command(label="نسخ", command=lambda: self.copy_from(widget))
        menu.add_command(label="قص", command=lambda: self.cut_from(widget))
        menu.add_separator()
        menu.add_command(label="تحديد الكل", command=lambda: self.select_all(widget))
        widget.bind("<Button-3>", lambda e: self.popup_menu(e, menu))

    def popup_menu(self, event, menu):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def clipboard_text(self, quiet=False):
        try:
            return self.root.clipboard_get()
        except tk.TclError:
            if not quiet:
                messagebox.showwarning(APP_NAME, "الحافظة فاضية أو مش متاحة.")
            return ""

    def paste_into(self, widget):
        text = self.clipboard_text()
        if text:
            widget.insert("insert", text)

    def copy_from(self, widget):
        try:
            selected = widget.get(tk.SEL_FIRST, tk.SEL_LAST)
        except (tk.TclError, AttributeError):
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(selected)

    def cut_from(self, widget):
        try:
            selected = widget.get(tk.SEL_FIRST, tk.SEL_LAST)
            widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except (tk.TclError, AttributeError):
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(selected)

    def select_all(self, widget):
        if isinstance(widget, tk.Text):
            widget.tag_add("sel", "1.0", "end")
        else:
            widget.select_range(0, "end")

    def paste_urls(self, event=None, quiet=False):
        """Paste clipboard into the links box like a normal Ctrl+V would."""
        text = self.clipboard_text(quiet=quiet)
        if not text:
            return "break"
        lines = [line.strip() for line in text.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            return "break"

        widget = self.url_text
        try:
            if widget.tag_ranges("sel"):
                widget.delete("sel.first", "sel.last")
            pos = widget.index("insert")
        except tk.TclError:
            pos = "1.0"

        # tkinter Text keeps one final newline that cannot be deleted.
        # Insert just before it so we never end up with an extra blank line.
        if widget.compare(pos, "==", widget.index("end")):
            pos = widget.index("end-1c")

        line_no = pos.split(".")[0]
        before = widget.get(f"{line_no}.0", pos)
        after = widget.get(pos, f"{line_no}.end")
        prefix = "\n" if before.strip() else ""
        suffix = "\n" if after.strip() else ""
        payload = prefix + "\n".join(lines) + suffix
        widget.insert(pos, payload)
        widget.mark_set("insert", f"{pos}+{len(payload)}c")
        widget.see("insert")
        return "break"

    def _global_paste(self, event=None, quiet=False):
        """Make paste shortcuts work even when focus is on a button/elsewhere."""
        focused = self.root.focus_get()
        if focused is self.out_entry or isinstance(focused, (tk.Entry, ttk.Entry)):
            return None  # let the folder field handle its own native paste
        return self.paste_urls(event, quiet=quiet)

    def choose_dir(self):
        folder = filedialog.askdirectory(initialdir=self.out_var.get() or os.path.expanduser("~"))
        if folder:
            self.out_var.set(folder)

    def open_dir(self):
        path = self.out_var.get()
        if os.path.isdir(path):
            os.startfile(path)
        else:
            messagebox.showinfo(APP_NAME, "المجلد غير موجود بعد—سيتم إنشاؤه عند التنزيل.")

    # ---------- Logic ----------
    def start_download(self):
        if self.worker and self.worker.is_alive():
            return
        raw = self.url_text.get("1.0", "end").strip()
        urls = extract_links(raw)
        if not urls:
            messagebox.showwarning(
                APP_NAME,
                "ما لقيت رابط في النص.\n"
                "استخدم زر «لصق» أو Ctrl+V، ويفضل رابط مثل:\n"
                "https://soundcloud.com/username/track-name",
            )
            return
        # نعرض الروابط بعد تنظيفها عشان المستخدم يتأكد منها
        self.url_text.delete("1.0", "end")
        self.url_text.insert("1.0", "\n".join(urls))
        out_dir = self.out_var.get().strip()
        if not out_dir:
            messagebox.showwarning(APP_NAME, "اختر مجلد الحفظ.")
            return
        if not find_ffmpeg():
            messagebox.showerror(APP_NAME, "ffmpeg غير موجود جوّه المجلد. التحويل لـ MP3 مش هيشتغل.")

        self.save_settings()
        self.stop_event.clear()
        self.download_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.pbar["value"] = 0
        self.log_text.delete("1.0", "end")
        self.set_status("جاري التحضير...", "busy")
        self.log("بدأ التنزيل...", "info")

        self.worker = threading.Thread(
            target=Downloader(
                urls=urls,
                out_dir=out_dir,
                q=self.q,
                stop_event=self.stop_event,
            ).run,
            daemon=True,
        )
        self.worker.start()

    def stop_download(self):
        self.stop_event.set()
        self.set_status("جاري الإيقاف...", "warn")
        self.log("جاري الإيقاف بعد الملف الحالي...", "warn")
        self.stop_btn.configure(state="disabled")

    def log(self, msg, kind="log"):
        tag = "" if kind == "log" else kind
        self.log_text.insert("end", msg + "\n", tag)
        self.log_text.see("end")

    def pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log" or kind == "warn" or kind == "error":
                    self.log(payload, kind)
                elif kind == "start_item":
                    i, total, url = payload
                    self.set_status(f"جاري التنزيل {i}/{total}", "busy")
                    self.log(f"[{i}/{total}] {url}", "info")
                elif kind == "progress":
                    self.pbar["value"] = max(0, min(100, payload["pct"]))
                    title = payload["title"][:60]
                    speed = payload["speed"]
                    txt = f"{payload['pct']:.1f}%  {title}"
                    if speed:
                        txt += f"  —  {speed/1024/1024:.1f} MB/s"
                    self.set_status(txt, "busy")
                elif kind == "item_done":
                    self.log("تم: " + payload, "ok")
                    self.pbar["value"] = 0
                elif kind == "done":
                    ok, failed, stopped = payload
                    status_kind = "ok" if ok else ("error" if failed and not stopped else "warn")
                    self.set_status("تم" if not stopped else "تم الإيقاف", status_kind)
                    self.log(f"النتيجة: {ok} نجح، {failed} فشل" + (" (تم الإيقاف)" if stopped else ""), "ok" if ok else "warn")
                    self.download_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    # ---------- settings ----------
    def load_settings(self):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # الإصدار 4: MP3 تلقائي من غير خيارات جودة أو كوكيز
            if data.get("version") == 4:
                return data
        except Exception:
            pass
        return {}

    def save_settings(self):
        try:
            os.makedirs(SETTINGS_DIR, exist_ok=True)
            data = {
                "version": 4,
                "out_dir": self.out_var.get(),
            }
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
