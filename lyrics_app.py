"""歌词下载器 —— 网易云音乐 / QQ音乐 / 酷狗音乐。

一个纯 Python + Tkinter 的桌面程序，搜索歌曲并下载 LRC 歌词。
"""

from __future__ import annotations

import ctypes
import json
import os
import queue
import re
import subprocess
import sys
import threading
import uuid
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

try:  # 作为包导入（测试）与作为脚本运行（PyInstaller 入口）都可用
    from .api_clients import (
        PAGE_SIZE,
        SOURCE_ACCENTS,
        SOURCE_LABELS,
        SOURCES,
        LyricsError,
        SearchPage,
        Track,
        fetch_lyric,
        search,
    )
except ImportError:
    from api_clients import (
        PAGE_SIZE,
        SOURCE_ACCENTS,
        SOURCE_LABELS,
        SOURCES,
        LyricsError,
        SearchPage,
        Track,
        fetch_lyric,
        search,
    )

APP_NAME = "歌词下载器"
APP_DATA_DIR = "LyricsFetcher"

# 配色
BG = "#F4F6FA"
CARD = "#FFFFFF"
INK = "#0F172A"
MUTED = "#64748B"
SUBTLE = "#94A3B8"
BORDER = "#E2E8F0"
HEADER_BG = "#0B1220"
HEADER_MUTED = "#94A3B8"
PRIMARY = "#2563EB"
PRIMARY_DARK = "#1D4ED8"
PRIMARY_SOFT = "#EFF6FF"
SUCCESS = "#10B981"
WARNING = "#F59E0B"
ERROR = "#DC2626"
TABLE_ALT = "#F8FAFC"
TABLE_SELECT = "#DBEAFE"


# ---------------------------------------------------------------------------
# 路径、设置与字体
# ---------------------------------------------------------------------------


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def default_save_dir() -> Path:
    return Path.home() / "Music" / "歌词"


def settings_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / APP_DATA_DIR / "settings.json"


def load_settings() -> dict[str, Any]:
    path = settings_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data: dict[str, Any]) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    temporary.replace(path)


def prepare_windows() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "LyricsFetcher.Desktop.1"
        )
    except Exception:
        pass


def choose_font(root: tk.Misc) -> str:
    available = set(tkfont.families(root))
    for family in (
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "微软雅黑",
        "PingFang SC",
        "Noto Sans CJK SC",
        "Segoe UI",
        "Arial",
    ):
        if family in available:
            return family
    return "TkDefaultFont"


def configure_fonts(root: tk.Misc, family: str) -> None:
    for name, size in (
        ("TkDefaultFont", 10),
        ("TkTextFont", 10),
        ("TkMenuFont", 10),
        ("TkHeadingFont", 9),
    ):
        try:
            font = tkfont.nametofont(name)
            font.configure(family=family, size=size)
        except tk.TclError:
            pass


def format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "—"
    minutes, remain = divmod(seconds, 60)
    return f"{minutes:02d}:{remain:02d}"


_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_filename(title: str) -> str:
    name = _INVALID_FILENAME.sub("_", title or "").replace("\u3000", " ")
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        name = "未命名歌词"
    if name.split(".", 1)[0].upper() in _RESERVED_NAMES:
        name = f"_{name}"
    name = name[:100].rstrip(" .")
    return name or "未命名歌词"


def write_lrc(directory: Path, title: str, lyric: str) -> Path:
    """原子式保存歌词；同名文件不覆盖，而是自动添加序号。"""
    directory.mkdir(parents=True, exist_ok=True)
    base = sanitize_filename(title)
    content = lyric.replace("\r\n", "\n").replace("\r", "\n")
    content = content.replace("\n", "\r\n")

    for index in range(1, 1000):
        suffix = "" if index == 1 else f" ({index})"
        target = directory / f"{base}{suffix}.lrc"
        try:
            with open(target, "x", encoding="utf-8-sig", newline="") as handle:
                handle.write(content)
            return target
        except FileExistsError:
            continue
    raise OSError("同名歌词文件过多，请清理保存目录后重试")


def shorten_path(path: Path, limit: int = 66) -> str:
    text = str(path)
    if len(text) <= limit:
        return text
    left = max(12, (limit - 3) // 2)
    right = max(12, limit - 3 - left)
    return f"{text[:left]}…{text[-right:]}"


# ---------------------------------------------------------------------------
# 小组件
# ---------------------------------------------------------------------------


class FlatButton(tk.Button):
    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        bg: str,
        fg: str,
        hover_bg: str,
        disabled_bg: str = "#E8EDF5",
        disabled_fg: str = "#94A3B8",
        font: tuple[Any, ...] | None = None,
        padx: int = 14,
        pady: int = 7,
        border: bool = False,
        cursor: str = "hand2",
    ) -> None:
        self._normal_bg = bg
        self._hover_bg = hover_bg
        self._disabled_bg = disabled_bg
        super().__init__(
            master,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=hover_bg,
            activeforeground=fg,
            disabledforeground=disabled_fg,
            relief="flat",
            bd=0,
            highlightthickness=1 if border else 0,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            font=font,
            padx=padx,
            pady=pady,
            cursor=cursor,
            takefocus=True,
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event: tk.Event[Any]) -> None:
        if str(self["state"]) == "normal":
            self.configure(bg=self._hover_bg)

    def _on_leave(self, _event: tk.Event[Any]) -> None:
        if str(self["state"]) == "normal":
            self.configure(bg=self._normal_bg)

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self.configure(state="normal", bg=self._normal_bg, cursor="hand2")
        else:
            self.configure(state="disabled", bg=self._disabled_bg, cursor="arrow")

    def set_busy(self, busy: bool, busy_text: str = "搜索中…") -> None:
        if busy:
            self.configure(state="disabled", bg="#93B4F5", cursor="arrow")
            self.configure(text=busy_text)
        else:
            self.configure(state="normal", bg=self._normal_bg, cursor="hand2")
            self.configure(text="搜索")


class PlaceholderEntry(tk.Entry):
    def __init__(
        self,
        master: tk.Misc,
        placeholder: str,
        *,
        font: tuple[Any, ...],
        bg: str,
        fg: str,
        placeholder_fg: str,
    ) -> None:
        self.placeholder = placeholder
        self._normal_fg = fg
        self._placeholder_fg = placeholder_fg
        self._showing_placeholder = False
        super().__init__(
            master,
            font=font,
            bg=bg,
            fg=fg,
            relief="flat",
            bd=0,
            highlightthickness=0,
            insertbackground=INK,
            selectbackground="#BFDBFE",
            selectforeground=INK,
        )
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self._show_placeholder()

    def _show_placeholder(self) -> None:
        if not super().get():
            self._showing_placeholder = True
            self.insert(0, self.placeholder)
            self.configure(fg=self._placeholder_fg)
            self.icursor(0)

    def _on_focus_in(self, _event: tk.Event[Any]) -> None:
        if self._showing_placeholder:
            self.delete(0, "end")
            self._showing_placeholder = False
            self.configure(fg=self._normal_fg)

    def _on_focus_out(self, _event: tk.Event[Any]) -> None:
        if not super().get():
            self._show_placeholder()

    def get_value(self) -> str:
        if self._showing_placeholder:
            return ""
        return super().get().strip()

    def focus_entry(self) -> None:
        self.focus_set()
        self.selection_range(0, "end")


class SearchGlyph(tk.Canvas):
    def __init__(self, master: tk.Misc, bg: str) -> None:
        super().__init__(
            master,
            width=20,
            height=20,
            bg=bg,
            highlightthickness=0,
            bd=0,
        )
        self.create_oval(2, 2, 13, 13, outline=MUTED, width=2)
        self.create_line(12, 12, 18, 18, fill=MUTED, width=2, capstyle="round")


class Toast:
    def __init__(self, app: "LyricsApp", title: str, detail: str) -> None:
        self.app = app
        window = tk.Toplevel(app.root)
        self.window = window
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg="#A7F3D0")

        panel = tk.Frame(window, bg="#ECFDF5")
        panel.pack(fill="both", expand=True, padx=1, pady=1)
        inner = tk.Frame(panel, bg="#ECFDF5")
        inner.pack(fill="both", expand=True, padx=16, pady=12)

        tk.Label(
            inner,
            text="✓",
            bg="#D1FAE5",
            fg="#047857",
            font=(app.font_family, 12, "bold"),
            width=2,
            height=1,
        ).pack(side="left", padx=(0, 11))
        text_box = tk.Frame(inner, bg="#ECFDF5")
        text_box.pack(side="left", fill="x", expand=True)
        tk.Label(
            text_box,
            text=title,
            bg="#ECFDF5",
            fg="#065F46",
            font=(app.font_family, 10, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            text_box,
            text=detail,
            bg="#ECFDF5",
            fg="#047857",
            font=(app.font_family, 9),
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        window.update_idletasks()
        width = max(280, window.winfo_reqwidth())
        height = window.winfo_reqheight()
        root = app.root
        x = root.winfo_rootx() + root.winfo_width() - width - 26
        y = root.winfo_rooty() + root.winfo_height() - height - 26
        window.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        window.after(3200, window.destroy)


class SettingsDialog:
    def __init__(self, app: "LyricsApp") -> None:
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("设置")
        self.window.configure(bg=BG)
        self.window.resizable(False, False)
        self.window.transient(app.root)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())

        width, height = 590, 292
        self.window.geometry(f"{width}x{height}")
        self.window.update_idletasks()
        x = app.root.winfo_rootx() + (app.root.winfo_width() - width) // 2
        y = app.root.winfo_rooty() + (app.root.winfo_height() - height) // 2
        self.window.geometry(f"+{max(0, x)}+{max(0, y)}")

        card = tk.Frame(self.window, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True, padx=18, pady=18)
        body = tk.Frame(card, bg=CARD)
        body.pack(fill="both", expand=True, padx=24, pady=21)

        tk.Label(
            body,
            text="下载设置",
            bg=CARD,
            fg=INK,
            font=(app.font_family, 15, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            body,
            text="歌词以 .lrc 格式保存；同名文件会自动添加序号，不会覆盖原文件。",
            bg=CARD,
            fg=MUTED,
            font=(app.font_family, 9),
            anchor="w",
        ).pack(fill="x", pady=(6, 18))

        tk.Label(
            body,
            text="歌词保存目录",
            bg=CARD,
            fg="#475569",
            font=(app.font_family, 9, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        row = tk.Frame(body, bg=CARD)
        row.pack(fill="x")
        field = tk.Frame(row, bg="#F8FAFC", highlightbackground=BORDER, highlightthickness=1)
        field.pack(side="left", fill="x", expand=True)
        self.path_var = tk.StringVar(value=str(app.save_dir))
        self.path_entry = tk.Entry(
            field,
            textvariable=self.path_var,
            bg="#F8FAFC",
            fg=INK,
            relief="flat",
            bd=0,
            highlightthickness=0,
            insertbackground=INK,
            font=(app.font_family, 10),
        )
        self.path_entry.pack(fill="x", padx=11, pady=9)
        FlatButton(
            row,
            "浏览…",
            self.browse,
            bg="#F1F5F9",
            fg="#334155",
            hover_bg="#E2E8F0",
            font=(app.font_family, 9),
            padx=14,
            pady=8,
        ).pack(side="left", padx=(8, 0))

        actions = tk.Frame(body, bg=CARD)
        actions.pack(fill="x", pady=(18, 0))
        FlatButton(
            actions,
            "恢复默认",
            self.restore_default,
            bg=CARD,
            fg=PRIMARY,
            hover_bg=PRIMARY_SOFT,
            font=(app.font_family, 9),
            padx=8,
            pady=7,
        ).pack(side="left")
        FlatButton(
            actions,
            "取消",
            self.close,
            bg="#F1F5F9",
            fg="#334155",
            hover_bg="#E2E8F0",
            font=(app.font_family, 9),
            padx=18,
            pady=8,
        ).pack(side="right")
        FlatButton(
            actions,
            "保存",
            self.save,
            bg=PRIMARY,
            fg=CARD,
            hover_bg=PRIMARY_DARK,
            font=(app.font_family, 9, "bold"),
            padx=22,
            pady=8,
        ).pack(side="right", padx=(0, 8))

        self.path_entry.focus_set()
        self.path_entry.icursor("end")
        self.window.bind("<Return>", lambda _event: self.save())

    def browse(self) -> None:
        selected = filedialog.askdirectory(
            parent=self.window,
            title="选择歌词保存目录",
            initialdir=self.path_var.get() or str(Path.home()),
        )
        if selected:
            self.path_var.set(selected)

    def restore_default(self) -> None:
        self.path_var.set(str(default_save_dir()))

    def save(self) -> None:
        raw = self.path_var.get().strip().strip('"')
        if not raw:
            messagebox.showerror("路径无效", "请输入一个保存目录。", parent=self.window)
            return
        expanded = os.path.expandvars(os.path.expanduser(raw))
        target = Path(expanded)
        try:
            if not target.is_absolute():
                target = (Path.cwd() / target).resolve()
            target.mkdir(parents=True, exist_ok=True)
            probe = target / f".lyrics_writer_{os.getpid()}_{uuid.uuid4().hex[:8]}.tmp"
            with open(probe, "x", encoding="utf-8") as handle:
                handle.write("test")
            probe.unlink()
        except OSError as exc:
            messagebox.showerror(
                "无法使用该目录",
                f"无法写入：\n{target}\n\n{exc}",
                parent=self.window,
            )
            return

        settings = load_settings()
        settings["save_dir"] = str(target)
        try:
            save_settings(settings)
        except OSError as exc:
            messagebox.showerror(
                "设置保存失败",
                f"无法写入设置文件：\n{exc}",
                parent=self.window,
            )
            return

        self.app.save_dir = target
        self.app.refresh_path_label()
        self.app.set_status("保存目录已更新", "ready")
        self.close()

    def close(self) -> None:
        try:
            self.window.grab_release()
        except tk.TclError:
            pass
        self.window.destroy()
        self.app.settings_dialog = None


# ---------------------------------------------------------------------------
# 单个平台的搜索结果页
# ---------------------------------------------------------------------------


class ResultTab:
    def __init__(self, app: "LyricsApp", parent: tk.Misc, source: str) -> None:
        self.app = app
        self.source = source
        self.name = SOURCE_LABELS[source]
        self.accent = SOURCE_ACCENTS[source]
        self.query = ""
        self.next_page = 1
        self.exhausted = False
        self.total = 0
        self.tracks: list[Track] = []
        self.item_tracks: dict[str, Track] = {}
        self.request_id = 0
        self.loading = False
        self.loaded = False
        self.had_error = False
        self.current_message = "输入歌曲名，按回车开始搜索"

        self.frame = tk.Frame(parent, bg=CARD)
        self.frame.grid(row=0, column=0, sticky="nsew")
        self.frame.grid_rowconfigure(0, weight=1)
        self.frame.grid_columnconfigure(0, weight=1)

        table_area = tk.Frame(self.frame, bg=CARD)
        table_area.grid(row=0, column=0, sticky="nsew", padx=16, pady=(13, 0))
        table_area.grid_rowconfigure(0, weight=1)
        table_area.grid_columnconfigure(0, weight=1)

        border = tk.Frame(table_area, bg=BORDER)
        border.grid(row=0, column=0, sticky="nsew")
        border.grid_rowconfigure(0, weight=1)
        border.grid_columnconfigure(0, weight=1)
        inner = tk.Frame(border, bg=CARD)
        inner.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        inner.grid_rowconfigure(0, weight=1)
        inner.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            inner,
            columns=("index", "title", "artist", "album", "duration"),
            show="headings",
            style="Lyrics.Treeview",
            selectmode="browse",
        )
        headings = (
            ("index", "#", 46, "center"),
            ("title", "歌曲名", 286, "w"),
            ("artist", "歌手", 170, "w"),
            ("album", "专辑", 258, "w"),
            ("duration", "时长", 72, "center"),
        )
        for column, label, width, anchor in headings:
            self.tree.heading(column, text=label)
            self.tree.column(
                column,
                width=width,
                minwidth=44,
                anchor=anchor,
                stretch=column in ("title", "album"),
            )
        self.tree.tag_configure("odd", background=CARD)
        self.tree.tag_configure("even", background=TABLE_ALT)
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            inner,
            orient="vertical",
            command=self.tree.yview,
            style="Lyrics.Vertical.TScrollbar",
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 1), pady=1)

        self.overlay = tk.Frame(inner, bg=CARD)
        self.overlay_label = tk.Label(
            self.overlay,
            text=self.current_message,
            bg=CARD,
            fg=MUTED,
            font=(app.font_family, 10),
            justify="center",
            wraplength=520,
        )
        self.overlay_label.pack(padx=20, pady=15)
        self.overlay.place(relx=0.5, rely=0.5, anchor="center")

        separator = tk.Frame(self.frame, bg=BORDER, height=1)
        separator.grid(row=1, column=0, sticky="ew")

        footer = tk.Frame(self.frame, bg=CARD)
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=12)
        footer.grid_columnconfigure(0, weight=1)

        meta = tk.Frame(footer, bg=CARD)
        meta.grid(row=0, column=0, sticky="w")
        self.total_label = tk.Label(
            meta,
            text="共 0 首",
            bg=CARD,
            fg=MUTED,
            font=(app.font_family, 9),
        )
        self.total_label.pack(side="left")
        tk.Label(meta, text="·", bg=CARD, fg=SUBTLE, font=(app.font_family, 9)).pack(
            side="left", padx=7
        )
        self.shown_label = tk.Label(
            meta,
            text="已显示 0 首",
            bg=CARD,
            fg="#475569",
            font=(app.font_family, 9),
        )
        self.shown_label.pack(side="left")

        actions = tk.Frame(footer, bg=CARD)
        actions.grid(row=0, column=1, sticky="e")

        self.load_more_button = FlatButton(
            actions,
            "加载更多",
            lambda: app.load_more(self.source),
            bg=PRIMARY_SOFT,
            fg=PRIMARY_DARK,
            hover_bg="#DBEAFE",
            font=(app.font_family, 9),
            padx=15,
            pady=6,
        )
        self.load_more_button.pack(side="left", padx=(0, 10))
        self.download_button = FlatButton(
            actions,
            "下载所选歌词",
            lambda: app.download_from_tab(self.source),
            bg=PRIMARY,
            fg=CARD,
            hover_bg=PRIMARY_DARK,
            font=(app.font_family, 9, "bold"),
            padx=16,
            pady=6,
        )
        self.download_button.pack(side="left")

        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._sync_download_button())
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Return>", lambda _event: app.download_from_tab(self.source))
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Configure>", lambda _event: self._place_overlay())

        self.context_menu = tk.Menu(
            self.tree,
            tearoff=False,
            bg=CARD,
            fg=INK,
            activebackground=PRIMARY_SOFT,
            activeforeground=INK,
            font=(app.font_family, 9),
        )
        self.context_menu.add_command(
            label="下载歌词", command=lambda: app.download_from_tab(self.source)
        )
        self.context_menu.add_command(label="复制歌曲信息", command=self.copy_track_info)

        self._update_footer()
        self._sync_download_button()

    def _place_overlay(self) -> None:
        self.overlay.place(relx=0.5, rely=0.5, anchor="center")

    def _set_overlay(self, message: str, color: str = MUTED) -> None:
        self.current_message = message
        self.overlay_label.configure(text=message, fg=color)
        self.overlay.place(relx=0.5, rely=0.5, anchor="center")

    def _hide_overlay(self) -> None:
        self.overlay.place_forget()

    def selected_track(self) -> Track | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self.item_tracks.get(selection[0])

    def _sync_download_button(self) -> None:
        enabled = self.selected_track() is not None and not self.loading
        self.download_button.set_enabled(enabled)

    def _update_footer(self) -> None:
        self.total_label.configure(text=f"共 {self.total:,} 首" if self.total else "共 0 首")
        self.shown_label.configure(text=f"已显示 {len(self.tracks):,} 首")

        all_loaded = self.loaded and (
            self.exhausted or (self.total > 0 and len(self.tracks) >= self.total)
        )
        if self.loading:
            text, enabled = "加载中…", False
        elif all_loaded:
            text, enabled = "已加载全部", False
        else:
            text = "加载更多"
            enabled = (
                self.loaded
                and not self.had_error
                and not self.exhausted
                and len(self.tracks) < self.total
            )
        self.load_more_button.configure(text=text)
        self.load_more_button.set_enabled(enabled)

    def begin_loading(self, message: str, clear: bool = True) -> None:
        self.loading = True
        self.had_error = False
        if clear:
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.item_tracks.clear()
            self.tracks = []
            self.total = 0
            self.next_page = 1
            self.exhausted = False
            self._set_overlay(message)
        self._update_footer()
        self._sync_download_button()

    def _append_tracks(self, new_tracks: list[Track], start_index: int) -> str | None:
        first_item: str | None = None
        for offset, track in enumerate(new_tracks, start=start_index):
            item = self.tree.insert(
                "",
                "end",
                values=(
                    f"{offset + 1}",
                    track.title,
                    track.artists,
                    track.album,
                    format_duration(track.duration),
                ),
                tags=("even" if offset % 2 else "odd",),
            )
            self.item_tracks[item] = track
            if first_item is None:
                first_item = item
        return first_item

    def set_results(self, result: SearchPage, append: bool = False) -> None:
        self.loading = False
        self.loaded = True
        self.had_error = False

        if not append:
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.item_tracks.clear()
            self.tracks = []
            self.total = 0
            self.next_page = 1
            self.exhausted = False

        self.total = max(self.total, result.total)
        seen = {(track.source, track.track_id) for track in self.tracks}
        new_tracks: list[Track] = []
        for track in result.tracks[:PAGE_SIZE]:
            key = (track.source, track.track_id)
            if key in seen:
                continue
            seen.add(key)
            new_tracks.append(track)

        start_index = len(self.tracks)
        first_item = self._append_tracks(new_tracks, start_index)
        self.tracks.extend(new_tracks)
        self.next_page = max(self.next_page, result.page + 1)

        if not result.tracks or not new_tracks:
            self.exhausted = True
        if self.total and len(self.tracks) >= self.total:
            self.exhausted = True

        if not append:
            if self.tracks:
                self._hide_overlay()
            else:
                self._set_overlay("没有找到相关歌曲，换个关键词试试", MUTED)
        elif first_item:
            self.tree.see(first_item)

        self._update_footer()
        self._sync_download_button()
        self.app.update_tab_label(self.source, self.total)

    def set_error(self, message: str, append: bool = False) -> None:
        self.loading = False
        self.loaded = True

        # 加载更多失败时保留已有结果，按钮恢复可用，用户可以重试。
        if append and self.tracks:
            self._update_footer()
            self._sync_download_button()
            return

        self.had_error = True
        self.total = 0
        self.next_page = 1
        self.exhausted = False
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.item_tracks.clear()
        self.tracks = []
        self._set_overlay(f"加载失败\n{message}", ERROR)
        self._update_footer()
        self._sync_download_button()
        self.app.update_tab_label(self.source, None)

    def _on_double_click(self, event: tk.Event[Any]) -> None:
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.app.download_from_tab(self.source)

    def _show_context_menu(self, event: tk.Event[Any]) -> None:
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self.tree.selection_set(row)
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def copy_track_info(self) -> None:
        track = self.selected_track()
        if not track:
            return
        text = f"{track.title} - {track.artists}（{track.album}）"
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(text)
        self.app.set_status("歌曲信息已复制", "ready")


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------


class LyricsApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.font_family = choose_font(root)
        configure_fonts(root, self.font_family)

        settings = load_settings()
        configured = str(settings.get("save_dir") or "").strip()
        self.save_dir = Path(configured).expanduser() if configured else default_save_dir()

        self.search_active = False
        self.closing = False
        self.events: queue.Queue[tuple[Callable[..., None], tuple[Any, ...]]] = queue.Queue()
        self.tabs: dict[str, ResultTab] = {}
        self.active_source = "netease"
        self.downloading: set[tuple[str, str]] = set()
        self.toast: Toast | None = None
        self.settings_dialog: SettingsDialog | None = None
        self._poll_job: str | None = None

        self._configure_window()
        self._configure_style()
        self._build_header()
        self._build_footer()
        self._build_body()
        self._select_tab("netease", initial=True)
        self._poll_events()

        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-f>", self._focus_search)
        root.bind("<F5>", lambda _event: self.start_search())
        root.bind("<Control-Key-1>", lambda _event: self._select_tab("netease"))
        root.bind("<Control-Key-2>", lambda _event: self._select_tab("qq"))
        root.bind("<Control-Key-3>", lambda _event: self._select_tab("kugou"))
        self.set_status("就绪 · 输入歌曲名开始搜索", "ready")

    # -- 窗口与样式 --------------------------------------------------------

    def _configure_window(self) -> None:
        self.root.title(f"{APP_NAME} · 网易云音乐 / QQ音乐 / 酷狗音乐")
        self.root.configure(bg=BG)
        self.root.minsize(960, 660)
        width, height = 1080, 760
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = min(width, max(960, screen_w - 100))
        height = min(height, max(660, screen_h - 120))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 12)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        icon = resource_path("assets/app.ico")
        if icon.exists():
            try:
                self.root.iconbitmap(default=str(icon))
            except tk.TclError:
                pass

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        line_height = tkfont.Font(family=self.font_family, size=10).metrics("linespace")
        row_height = max(35, line_height + 15)
        style.configure(
            "Lyrics.Treeview",
            background=CARD,
            fieldbackground=CARD,
            foreground=INK,
            rowheight=row_height,
            borderwidth=0,
            relief="flat",
            font=(self.font_family, 10),
        )
        style.configure(
            "Lyrics.Treeview.Heading",
            background="#F8FAFC",
            foreground="#475569",
            relief="flat",
            borderwidth=0,
            font=(self.font_family, 9, "bold"),
            padding=(9, 10),
        )
        style.map(
            "Lyrics.Treeview",
            background=[("selected", TABLE_SELECT)],
            foreground=[("selected", INK)],
        )
        style.map(
            "Lyrics.Treeview.Heading",
            background=[("active", "#F1F5F9")],
            relief=[("active", "flat")],
        )
        style.layout(
            "Lyrics.Treeview",
            [("Lyrics.Treeview.treearea", {"sticky": "nswe"})],
        )
        style.configure(
            "Lyrics.Vertical.TScrollbar",
            gripcount=0,
            background="#CBD5E1",
            darkcolor="#CBD5E1",
            lightcolor="#CBD5E1",
            troughcolor=CARD,
            bordercolor=CARD,
            arrowcolor=MUTED,
            relief="flat",
            arrowsize=11,
        )
        style.map(
            "Lyrics.Vertical.TScrollbar",
            background=[("active", "#94A3B8"), ("pressed", "#94A3B8")],
        )

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=HEADER_BG, height=112)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)

        left = tk.Frame(header, bg=HEADER_BG)
        left.pack(side="left", padx=(28, 0), pady=22)

        logo = tk.Frame(left, bg=PRIMARY, width=50, height=50)
        logo.pack(side="left")
        logo.pack_propagate(False)
        tk.Label(
            logo,
            text="♪",
            bg=PRIMARY,
            fg=CARD,
            font=(self.font_family, 24, "bold"),
        ).pack(expand=True)

        titles = tk.Frame(left, bg=HEADER_BG)
        titles.pack(side="left", padx=(15, 0))
        tk.Label(
            titles,
            text=APP_NAME,
            bg=HEADER_BG,
            fg="#F8FAFC",
            font=(self.font_family, 19, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            titles,
            text="一站式搜索三方平台歌词 · 保存为 LRC",
            bg=HEADER_BG,
            fg=HEADER_MUTED,
            font=(self.font_family, 9),
            anchor="w",
        ).pack(fill="x", pady=(5, 0))

        status_box = tk.Frame(header, bg=HEADER_BG)
        status_box.pack(side="right", padx=(20, 28), pady=22)
        self.status_dot = tk.Canvas(
            status_box,
            width=10,
            height=10,
            bg=HEADER_BG,
            highlightthickness=0,
            bd=0,
        )
        self.status_dot.pack(side="left", padx=(0, 8))
        self.dot_item = self.status_dot.create_oval(1, 1, 9, 9, fill=SUCCESS, outline="")
        self.status_text = tk.Label(
            status_box,
            text="就绪",
            bg=HEADER_BG,
            fg="#CBD5E1",
            font=(self.font_family, 9),
        )
        self.status_text.pack(side="left")

        tk.Frame(self.root, bg=PRIMARY, height=3).pack(side="top", fill="x")

    def _build_footer(self) -> None:
        footer = tk.Frame(self.root, bg=CARD, height=58)
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)
        tk.Frame(self.root, bg=BORDER, height=1).pack(side="bottom", fill="x")

        inner = tk.Frame(footer, bg=CARD)
        inner.pack(fill="both", expand=True, padx=28, pady=10)

        path_box = tk.Frame(inner, bg=CARD)
        path_box.pack(side="left", fill="x", expand=True)
        tk.Label(
            path_box,
            text="保存位置",
            bg=CARD,
            fg=SUBTLE,
            font=(self.font_family, 8, "bold"),
            anchor="w",
        ).pack(fill="x")
        self.path_label = tk.Label(
            path_box,
            text=shorten_path(self.save_dir),
            bg=CARD,
            fg="#475569",
            font=(self.font_family, 9),
            anchor="w",
        )
        self.path_label.pack(fill="x", pady=(2, 0))

        buttons = tk.Frame(inner, bg=CARD)
        buttons.pack(side="right", padx=(18, 0))
        FlatButton(
            buttons,
            "打开保存目录",
            self.open_save_dir,
            bg=PRIMARY_SOFT,
            fg=PRIMARY,
            hover_bg="#DBEAFE",
            font=(self.font_family, 9),
            padx=15,
            pady=7,
        ).pack(side="left")
        FlatButton(
            buttons,
            "设置",
            self.show_settings,
            bg="#F1F5F9",
            fg="#334155",
            hover_bg="#E2E8F0",
            font=(self.font_family, 9),
            padx=18,
            pady=7,
        ).pack(side="left", padx=(8, 0))

    def _build_body(self) -> None:
        body = tk.Frame(self.root, bg=BG)
        body.pack(side="top", fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        # 搜索卡片
        search_border = tk.Frame(body, bg=BORDER)
        search_border.grid(row=0, column=0, sticky="ew", padx=28, pady=(18, 12))
        search_card = tk.Frame(search_border, bg=CARD)
        search_card.pack(fill="both", expand=True, padx=1, pady=1)
        search_inner = tk.Frame(search_card, bg=CARD)
        search_inner.pack(fill="x", padx=16, pady=(13, 10))

        row = tk.Frame(search_inner, bg=CARD)
        row.pack(fill="x")
        field = tk.Frame(row, bg="#F8FAFC", highlightbackground=BORDER, highlightthickness=1)
        field.pack(side="left", fill="x", expand=True)
        SearchGlyph(field, "#F8FAFC").pack(side="left", padx=(12, 7))
        self.search_entry = PlaceholderEntry(
            field,
            "输入歌曲名或歌手，例如：晴天 / 周杰伦",
            font=(self.font_family, 10),
            bg="#F8FAFC",
            fg=INK,
            placeholder_fg="#94A3B8",
        )
        self.search_entry.pack(side="left", fill="x", expand=True, pady=10, padx=(0, 10))
        self.search_entry.bind("<Return>", lambda _event: self.start_search())

        self.search_button = FlatButton(
            row,
            "搜索",
            self.start_search,
            bg=PRIMARY,
            fg=CARD,
            hover_bg=PRIMARY_DARK,
            font=(self.font_family, 10, "bold"),
            padx=29,
            pady=9,
        )
        self.search_button.pack(side="left", padx=(10, 0))

        self.search_hint = tk.Label(
            search_inner,
            text="",
            bg=CARD,
            fg=SUBTLE,
            font=(self.font_family, 8),
            anchor="w",
        )
        self.search_hint.pack(fill="x", pady=(7, 0))

        # 平台标签栏
        self.tabbar = tk.Frame(body, bg=BG, height=45)
        self.tabbar.grid(row=1, column=0, sticky="ew", padx=28)
        self.tabbar.grid_propagate(False)
        self.tabbar.bind("<Configure>", lambda _event: self.root.after_idle(self._position_indicator))

        self.tab_buttons: dict[str, tk.Button] = {}
        for source in SOURCES:
            button = tk.Button(
                self.tabbar,
                text=SOURCE_LABELS[source],
                command=lambda s=source: self._select_tab(s),
                bg=BG,
                fg=MUTED,
                activebackground="#E9EEF7",
                activeforeground=INK,
                relief="flat",
                bd=0,
                highlightthickness=0,
                font=(self.font_family, 10, "bold"),
                padx=18,
                pady=10,
                cursor="hand2",
                takefocus=True,
            )
            button.pack(side="left", fill="y")
            self.tab_buttons[source] = button

        self.tab_indicator = tk.Frame(self.tabbar, bg=PRIMARY, height=3)
        self.tab_indicator.place(x=0, y=42, width=1, height=3)

        # 搜索结果卡片
        content_border = tk.Frame(body, bg=BORDER)
        content_border.grid(row=2, column=0, sticky="nsew", padx=28, pady=(0, 16))
        content_border.grid_rowconfigure(0, weight=1)
        content_border.grid_columnconfigure(0, weight=1)
        self.tab_host = tk.Frame(content_border, bg=CARD)
        self.tab_host.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        self.tab_host.grid_rowconfigure(0, weight=1)
        self.tab_host.grid_columnconfigure(0, weight=1)

        for source in SOURCES:
            tab = ResultTab(self, self.tab_host, source)
            self.tabs[source] = tab
            tab.frame.grid_remove()

        self.tab_indicator.lift()
        self.root.after(100, self._position_indicator)

    # -- 状态与标签 --------------------------------------------------------

    def set_status(self, message: str, kind: str = "ready") -> None:
        color = {
            "ready": SUCCESS,
            "busy": WARNING,
            "error": ERROR,
            "idle": SUBTLE,
        }.get(kind, SUCCESS)
        self.status_text.configure(text=message)
        self.status_dot.itemconfigure(self.dot_item, fill=color)

    def update_tab_label(self, source: str, count: int | None) -> None:
        button = self.tab_buttons.get(source)
        if not button:
            return
        base = SOURCE_LABELS[source]
        text = f"{base} · {count:,}" if count not in (None, 0) else base
        button.configure(text=text)
        self.root.after_idle(self._position_indicator)

    def _position_indicator(self) -> None:
        button = self.tab_buttons.get(self.active_source)
        if not button or not button.winfo_exists():
            return
        try:
            x = button.winfo_x()
            width = button.winfo_width()
            height = self.tabbar.winfo_height()
        except tk.TclError:
            return
        self.tab_indicator.place(x=x, y=max(0, height - 3), width=max(1, width), height=3)
        self.tab_indicator.lift()

    def _select_tab(self, source: str, initial: bool = False) -> None:
        if source not in self.tabs:
            return
        self.active_source = source
        for name, tab in self.tabs.items():
            if name == source:
                tab.frame.grid()
            else:
                tab.frame.grid_remove()
        for name, button in self.tab_buttons.items():
            active = name == source
            button.configure(
                bg=CARD if active else BG,
                fg=SOURCE_ACCENTS[name] if active else MUTED,
                activebackground=PRIMARY_SOFT if active else "#E9EEF7",
            )
        self.search_hint.configure(
            text=f"当前只搜索「{SOURCE_LABELS[source]}」；双击结果下载歌词，底部可加载更多。"
        )
        self.root.after_idle(self._position_indicator)
        if not initial:
            tab = self.tabs[source]
            if tab.loading:
                self.set_status(f"正在处理 {tab.name} 的请求…", "busy")
            elif tab.loaded and tab.tracks:
                self.set_status(
                    f"{tab.name} · 已显示 {len(tab.tracks):,} / 共 {tab.total:,} 首",
                    "ready",
                )
            elif tab.loaded:
                self.set_status("当前标签页还没有搜索结果", "idle")

    # -- 搜索流程 ----------------------------------------------------------

    def _focus_search(self, _event: tk.Event[Any] | None = None) -> str:
        self.search_entry.focus_entry()
        return "break"

    def start_search(self) -> None:
        if self.search_active:
            return
        query = self.search_entry.get_value().strip()
        if not query:
            self.set_status("请先输入歌曲名或歌手名", "error")
            self.search_entry.focus_set()
            return

        source = self.active_source
        tab = self.tabs[source]
        tab.query = query
        self.search_active = True
        self.search_button.set_busy(True)
        self.set_status(f"正在搜索{tab.name}…", "busy")

        # 只重置当前标签页，其他平台的结果保持不变。
        tab.request_id += 1
        tab.loaded = False
        tab.had_error = False
        tab.begin_loading(f"正在搜索「{query}」…")
        self.update_tab_label(source, None)
        self._start_search(source, query, 1, append=False)

    def _start_search(self, source: str, query: str, page: int, *, append: bool) -> None:
        tab = self.tabs[source]
        request_id = tab.request_id
        thread = threading.Thread(
            target=self._search_worker,
            args=(source, query, page, request_id, append),
            daemon=True,
            name=f"search-{source}",
        )
        thread.start()

    def _search_worker(
        self,
        source: str,
        query: str,
        page: int,
        request_id: int,
        append: bool,
    ) -> None:
        try:
            result = search(source, query, page)
        except Exception as exc:
            message = str(exc) if isinstance(exc, LyricsError) else f"搜索失败：{exc}"
            self._post(self._on_search_error, source, request_id, message, append)
        else:
            self._post(self._on_search_done, source, request_id, result, append)

    def _on_search_done(
        self,
        source: str,
        request_id: int,
        result: SearchPage,
        append: bool,
    ) -> None:
        if self.closing:
            return
        tab = self.tabs[source]
        if request_id != tab.request_id:
            return
        try:
            tab.set_results(result, append=append)
            if append and tab.tracks:
                self.set_status(
                    f"{tab.name} · 已加载更多，当前显示 {len(tab.tracks):,} 首",
                    "ready",
                )
            elif tab.tracks:
                self.set_status(
                    f"{tab.name} · 已显示 {len(tab.tracks):,} / 共 {tab.total:,} 首",
                    "ready",
                )
            else:
                self.set_status("没有找到相关歌曲，换个关键词试试", "idle")
        finally:
            self.search_active = False
            self.search_button.set_busy(False)

    def _on_search_error(
        self,
        source: str,
        request_id: int,
        message: str,
        append: bool,
    ) -> None:
        if self.closing:
            return
        tab = self.tabs[source]
        if request_id != tab.request_id:
            return
        try:
            tab.set_error(message, append=append)
            if append and tab.tracks:
                self.set_status(f"加载更多失败：{message}", "error")
            else:
                self.set_status(f"{tab.name} 搜索失败", "error")
        finally:
            self.search_active = False
            self.search_button.set_busy(False)

    def load_more(self, source: str) -> None:
        if self.search_active:
            self.set_status("请等待当前请求完成", "busy")
            return
        tab = self.tabs[source]
        if tab.loading or not tab.loaded or tab.exhausted or not tab.query:
            return
        if not tab.tracks or (tab.total and len(tab.tracks) >= tab.total):
            return

        tab.request_id += 1
        tab.begin_loading("", clear=False)
        self.search_active = True
        self.search_button.set_busy(True, "加载中…")
        self.set_status(f"正在加载更多{tab.name}结果…", "busy")
        self._start_search(source, tab.query, tab.next_page, append=True)

    # -- 下载 --------------------------------------------------------------

    def download_from_tab(self, source: str) -> None:
        if self.search_active:
            self.set_status("请等待搜索完成后再下载", "busy")
            return
        tab = self.tabs[source]
        track = tab.selected_track()
        if not track:
            self.set_status("请先选中一首歌曲", "error")
            return
        self._download(track)

    def _download(self, track: Track) -> None:
        key = (track.source, track.track_id)
        if key in self.downloading:
            self.set_status("这首歌正在下载中…", "busy")
            return
        self.downloading.add(key)
        self.set_status(f"正在获取《{track.title}》的歌词…", "busy")
        target_dir = self.save_dir
        thread = threading.Thread(
            target=self._download_worker,
            args=(track, target_dir),
            daemon=True,
            name=f"download-{track.source}",
        )
        thread.start()

    def _download_worker(self, track: Track, target_dir: Path) -> None:
        try:
            lyric = fetch_lyric(track)
            path = write_lrc(target_dir, track.title, lyric)
        except Exception as exc:
            message = str(exc) if isinstance(exc, LyricsError) else f"保存失败：{exc}"
            self._post(self._on_download_error, track, message)
        else:
            self._post(self._on_download_done, track, path)

    def _on_download_done(self, track: Track, path: Path) -> None:
        if self.closing:
            return
        self.downloading.discard((track.source, track.track_id))
        self.set_status(f"已保存：{path.name}", "ready")
        self.show_toast("歌词已保存", path.name)

    def _on_download_error(self, track: Track, message: str) -> None:
        if self.closing:
            return
        self.downloading.discard((track.source, track.track_id))
        self.set_status("歌词下载失败", "error")
        messagebox.showerror(
            "下载失败",
            f"《{track.title}》\n\n{message}",
            parent=self.root,
        )

    def show_toast(self, title: str, detail: str) -> None:
        if self.toast is not None:
            try:
                self.toast.window.destroy()
            except tk.TclError:
                pass
        self.toast = Toast(self, title, detail)

    # -- 目录与设置 --------------------------------------------------------

    def refresh_path_label(self) -> None:
        self.path_label.configure(text=shorten_path(self.save_dir))

    def open_save_dir(self) -> None:
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                "无法打开目录",
                f"无法创建目录：\n{self.save_dir}\n\n{exc}",
                parent=self.root,
            )
            return
        try:
            if os.name == "nt":
                os.startfile(self.save_dir)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(
                    ["open", str(self.save_dir)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(
                    ["xdg-open", str(self.save_dir)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except OSError as exc:
            messagebox.showerror("无法打开目录", str(exc), parent=self.root)

    def show_settings(self) -> None:
        if self.settings_dialog is not None:
            try:
                self.settings_dialog.window.lift()
                self.settings_dialog.window.focus_set()
                return
            except tk.TclError:
                self.settings_dialog = None
        self.settings_dialog = SettingsDialog(self)

    # -- 事件循环 ----------------------------------------------------------

    def _post(self, callback: Callable[..., None], *args: Any) -> None:
        self.events.put((callback, args))

    def _poll_events(self) -> None:
        try:
            while True:
                callback, args = self.events.get_nowait()
                if not self.closing:
                    callback(*args)
        except queue.Empty:
            pass
        except Exception:
            # 单个 UI 回调异常不应终止整个事件轮询。
            import traceback

            traceback.print_exc()
        if not self.closing:
            self._poll_job = self.root.after(70, self._poll_events)

    def close(self) -> None:
        self.closing = True
        if self._poll_job is not None:
            try:
                self.root.after_cancel(self._poll_job)
            except tk.TclError:
                pass
            self._poll_job = None
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def main() -> None:
    prepare_windows()
    root = tk.Tk()
    app = LyricsApp(root)
    root.mainloop()
    del app


if __name__ == "__main__":
    main()
