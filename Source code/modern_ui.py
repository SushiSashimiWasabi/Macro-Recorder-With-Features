"""The dark Macro Recorder window (started from macro_recorder.py).

It reuses everything from macro_recorder.py (recording, playback, hotkeys, speed, countdown,
picture watch, screen size scaling, imports) and only changes the window around it:

  - a dark main window: status line, big Record / Pause / Play / Stop cards with their hotkeys,
    a "Repeat continuously" switch, the macro's name with Edit... / Open... / Save..., status bar
  - a Settings window with tabs: General, Recording, Playback, Picture watch, About
  - an Edit... window to look through a macro's actions and remove some
  - small sounds when recording or playback starts and stops
  - recording options: record mouse movement or not, and how detailed

Works on Windows and Mac (plain Tk, no extra packages).
"""

import datetime
import os
import shutil
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import backdrop
import macro_recorder as core
import platform_keys
import sounds
import video_overlay
from macro_recorder import (HOTKEY_ACTIONS, IS_MAC, IS_WIN, SCREEN_TARGET, SPEED_PRESETS, background,
                            format_speed, hotkey_name, image_watch, parse_speed)

APP_VERSION = "2.0"

# ---------------------------------------------------------------- look

if IS_WIN:
    FAMILY = "Segoe UI"
elif IS_MAC:
    FAMILY = "Helvetica Neue"
else:
    FAMILY = "Helvetica"

BG = "#111114"        # window
PANEL = "#18181c"     # main panel
CARD = "#1f1f25"      # cards and buttons
CARD_HOVER = "#2a2a33"
FIELD = "#16161a"     # text boxes
BORDER = "#33333d"
BADGE = "#2b2b33"
TEXT = "#f1f1f4"
MUTED = "#9b9ba6"
DIM = "#5a5a64"
ACCENT = "#4f7cff"    # blue
ACCENT_DARK = "#1c2648"
RED = "#ff4757"
RED_DARK = "#3a1a20"
GREEN = "#2ecc71"
AMBER = "#ffb238"

F_BASE = (FAMILY, 10)
F_SMALL = (FAMILY, 9)
F_BOLD = (FAMILY, 10, "bold")
F_CARD = (FAMILY, 12, "bold")
F_STATUS = (FAMILY, 13, "bold")
F_TITLE = (FAMILY, 18, "bold")
F_SECTION = (FAMILY, 9, "bold")
F_LINK = (FAMILY, 9, "underline")


def apply_theme(root):
    """Dark colours for every ttk widget (the boxes and buttons the old window used)."""
    root.configure(bg=BG)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=BG, foreground=TEXT, fieldbackground=FIELD, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, troughcolor=PANEL, selectbackground=ACCENT,
                    selectforeground="white", insertcolor=TEXT, arrowcolor=MUTED, font=F_BASE,
                    focuscolor=BORDER)
    style.map(".", foreground=[("disabled", DIM)], fieldbackground=[("disabled", BG)])
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("TLabelframe", background=BG, bordercolor=BORDER, relief="solid")
    style.configure("TLabelframe.Label", background=BG, foreground=MUTED, font=F_SECTION)
    style.configure("TButton", background=CARD, foreground=TEXT, padding=(12, 5), relief="flat",
                    bordercolor=BORDER)
    style.map("TButton", background=[("disabled", BG), ("active", CARD_HOVER)],
              bordercolor=[("active", "#4a4a56")])
    style.configure("Accent.TButton", background=ACCENT, foreground="white", bordercolor=ACCENT)
    style.map("Accent.TButton", background=[("active", "#6a90ff")])
    style.configure("Danger.TButton", background=RED_DARK, foreground=RED, bordercolor="#5a2630")
    style.map("Danger.TButton", background=[("active", "#4a2028")])
    style.configure("TCheckbutton", background=BG, foreground=TEXT, indicatorbackground=FIELD,
                    indicatorforeground="white", indicatorcolor=FIELD)
    style.map("TCheckbutton", background=[("active", BG)],
              indicatorcolor=[("selected", ACCENT), ("disabled", BG)])
    for name in ("TSpinbox", "TCombobox", "TEntry"):
        style.configure(name, fieldbackground=FIELD, background=CARD, foreground=TEXT, padding=3,
                        arrowsize=12)
        style.map(name, fieldbackground=[("readonly", FIELD), ("disabled", BG)],
                  foreground=[("disabled", DIM)], bordercolor=[("focus", ACCENT)])
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(12, 6, 12, 0))
    style.configure("TNotebook.Tab", background=BG, foreground=MUTED, padding=(14, 6), borderwidth=0,
                    font=(FAMILY, 10))
    style.map("TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", TEXT)],
              font=[("selected", (FAMILY, 10, "bold"))], lightcolor=[("selected", ACCENT)])
    style.configure("Treeview", background=FIELD, fieldbackground=FIELD, foreground=TEXT, rowheight=22,
                    bordercolor=BORDER)
    style.configure("Treeview.Heading", background=CARD, foreground=MUTED, relief="flat", font=F_SMALL)
    style.map("Treeview", background=[("selected", ACCENT_DARK)])
    style.map("Horizontal.TScale", troughcolor=[("disabled", BG)], background=[("disabled", BADGE)],
              lightcolor=[("disabled", BADGE)], darkcolor=[("disabled", BADGE)],
              bordercolor=[("disabled", BORDER)])
    style.configure("Vertical.TScrollbar", background=CARD, troughcolor=FIELD, bordercolor=FIELD,
                    arrowcolor=MUTED)
    # the drop-down lists of combo boxes are plain Tk lists
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", "white")
    root.option_add("*TCombobox*Listbox.font", F_BASE)


def dark_title_bar(win):
    """Windows 10/11: a dark title bar to match the window (no effect elsewhere)."""
    if not IS_WIN:
        return
    try:
        import ctypes

        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        on = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (newer, older Windows 10)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), 4) == 0:
                break
    except Exception:
        pass


def app_icon(size=32):
    """The window icon: a blue rounded square with a white dot (drawn here, no picture file)."""
    img = tk.PhotoImage(width=size, height=size)
    r, c = size * 0.25, size / 2
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            dx = max(r - x, 0, x - (size - 1 - r))
            dy = max(r - y, 0, y - (size - 1 - r))
            if dx * dx + dy * dy > r * r:
                row.append("{}")  # transparent corner
                continue
            row.append("#ffffff" if (x - c + 0.5) ** 2 + (y - c + 0.5) ** 2 <= (size * 0.2) ** 2 else ACCENT)
        rows.append("{" + " ".join(row) + "}")
    try:
        img.put(" ".join(rows))
    except tk.TclError:
        img.put(ACCENT, to=(0, 0, size, size))
    return img


def rounded_rect(canvas, x0, y0, x1, y1, r, **kw):
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
           x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return canvas.create_polygon(pts, smooth=True, **kw)


def link(parent, text, command, bg=BG, fg=MUTED, font=F_LINK):
    lab = tk.Label(parent, text=text, bg=bg, fg=fg, font=font, cursor="hand2")
    lab.bind("<Button-1>", lambda e: command())
    lab.bind("<Enter>", lambda e: lab.config(fg=TEXT))
    lab.bind("<Leave>", lambda e: lab.config(fg=fg))
    return lab


class Switch(tk.Canvas):
    """An on/off switch tied to a BooleanVar."""

    W, H = 42, 22

    def __init__(self, parent, variable, command=None, bg=BG):
        super().__init__(parent, width=self.W, height=self.H, bg=bg, highlightthickness=0, cursor="hand2")
        self.var = variable
        self.command = command
        self.enabled = True
        self.bind("<Button-1>", self._click)
        variable.trace_add("write", lambda *a: self.draw())
        self.draw()

    def _click(self, _e):
        if not self.enabled:
            return
        self.var.set(not self.var.get())
        if self.command:
            self.command()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.config(cursor="hand2" if enabled else "arrow")
        self.draw()

    def draw(self):
        self.delete("!bdimg")  # keeps the background picture's piece, if there is one
        on = bool(self.var.get())
        w, h = self.W, self.H
        if on:
            fill, knob, outline = (ACCENT if self.enabled else ACCENT_DARK), "white", ""
        else:
            fill, knob, outline = "#26262d", (MUTED if self.enabled else DIM), BORDER
        rounded_rect(self, 1, 1, w - 2, h - 2, (h - 2) // 2, fill=fill, outline=outline)
        x = w - h + 3 if on else 4
        self.create_oval(x, 4, x + h - 8, h - 4, fill=knob, outline="")


class Card(tk.Frame):
    """A big action button: icon, name and its hotkey."""

    def __init__(self, parent, kind, title, color, command):
        super().__init__(parent, bg=BORDER, cursor="hand2")
        self.kind, self.color, self.command = kind, color, command
        self.enabled, self.active, self.hover = True, False, False
        self.inner = tk.Frame(self, bg=CARD)
        self.inner.pack(fill="both", expand=True, padx=1, pady=1)
        self.icon = tk.Canvas(self.inner, width=24, height=24, bg=CARD, highlightthickness=0)
        self.icon.grid(row=0, column=0, sticky="nw", padx=(12, 0), pady=(12, 0))
        self.badge = tk.Label(self.inner, bg=BADGE, fg=MUTED, font=(FAMILY, 8, "bold"), padx=5, pady=1)
        self.badge.grid(row=0, column=1, sticky="ne", padx=(4, 9), pady=(10, 0))
        self.label = tk.Label(self.inner, text=title, bg=CARD, fg=TEXT, font=F_CARD, anchor="w")
        self.label.grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 12))
        self.inner.columnconfigure(1, weight=1)
        for w in (self, self.inner, self.icon, self.badge, self.label):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>", lambda e: self._hover(True))
            w.bind("<Leave>", lambda e: self._hover(False))
        self._draw()

    def _click(self, _e):
        if self.enabled:
            self.command()

    def _hover(self, on):
        self.hover = on
        self._draw()

    def update_card(self, title=None, key=None, enabled=True, active=False):
        if title is not None:
            self.label.config(text=title)
        if key is not None:
            self.badge.config(text=key)
        self.enabled, self.active = enabled, active
        self._draw()

    def _draw(self):
        if self.active:
            bg, border = (RED_DARK if self.color == RED else ACCENT_DARK), self.color
        elif self.enabled and self.hover:
            bg, border = CARD_HOVER, "#4a4a56"
        else:
            bg, border = (CARD if self.enabled else PANEL), BORDER
        fg = TEXT if self.enabled else DIM
        self.config(bg=border, cursor="hand2" if self.enabled else "arrow")
        for w in (self.inner, self.icon, self.label):
            w.config(bg=bg)
        self.label.config(fg=fg)
        self.badge.config(fg=MUTED if self.enabled else DIM, bg=BADGE if self.enabled else CARD)
        c = self.icon
        c.delete("all")
        col = self.color if self.enabled else DIM
        if self.kind == "record":
            c.create_oval(2, 2, 22, 22, outline=fg, width=2)
            c.create_oval(7, 7, 17, 17, fill=col, outline="")
        elif self.kind == "pause":
            c.create_rectangle(5, 4, 10, 20, fill=col, outline="")
            c.create_rectangle(14, 4, 19, 20, fill=col, outline="")
        elif self.kind == "play":
            c.create_polygon(6, 3, 21, 12, 6, 21, fill=col, outline="")
        elif self.kind == "stop":
            rounded_rect(c, 4, 4, 20, 20, 4, fill=col, outline="")


# ---------------------------------------------------------------- describing actions (Edit window)

def key_label(data):
    if "special" in data:
        return hotkey_name(data["special"])
    if "vk" in data:
        return platform_keys.win_vk_name(data["vk"]) or data.get("char") or f"Key {data['vk']}"
    if data.get("char"):
        return data["char"].upper()
    return "?"


def describe(ev):
    kind = ev.get("type")
    if kind == "move":
        return "Mouse move", f"{ev['x']}, {ev['y']}"
    if kind == "move_rel":
        return "Camera turn", f"{ev['dx']:+}, {ev['dy']:+}"
    if kind == "click":
        where = f"at {ev['x']}, {ev['y']}" if "x" in ev else ""
        return f"{ev['button'].title()} button {'down' if ev['pressed'] else 'up'}", where
    if kind == "scroll":
        return "Scroll", f"{'up' if ev['dy'] > 0 else 'down'} {abs(ev['dy'])}"
    if kind == "key":
        return f"Key {'down' if ev['pressed'] else 'up'}", key_label(ev["key"])
    return kind or "?", ""


MOUSE_DETAIL = {"Smooth": 0.01, "Normal": 0.025, "Light": 0.05}  # seconds between recorded moves


# ---------------------------------------------------------------- the app

class PlayOverlay:
    """A small always-on-top box at the top middle of the main screen: the countdown before playing,
    then how long it has been playing. It stays there the whole time the macro runs, so you can
    see it's still going while the app is minimized. Mouse clicks go straight through it."""

    def __init__(self, root, screen_w):
        self.win = win = tk.Toplevel(root, bg=BORDER)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.93)
        except tk.TclError:
            pass
        inner = tk.Frame(win, bg=PANEL)
        inner.pack(padx=1, pady=1)
        top = tk.Frame(inner, bg=PANEL)
        top.pack(padx=14, pady=(7, 0))
        self.dot = tk.Canvas(top, width=12, height=12, bg=PANEL, highlightthickness=0)
        self.dot.pack(side="left")
        self.state = tk.Label(top, bg=PANEL, fg=TEXT, font=(FAMILY, 11, "bold"))
        self.state.pack(side="left", padx=(7, 0))
        self.clock = tk.Label(top, bg=PANEL, fg=TEXT, font=(FAMILY, 15, "bold"))
        self.clock.pack(side="left", padx=(12, 0))
        self.note = tk.Label(inner, bg=PANEL, fg=MUTED, font=F_SMALL)
        self.note.pack(padx=14, pady=(0, 2))
        keys = tk.Frame(inner, bg=PANEL)
        keys.pack(padx=14, pady=(2, 8))
        self.key_labels = {}
        for action, word in (("pause", "Pause"), ("stop", "Stop")):
            badge = tk.Label(keys, bg=BADGE, fg=TEXT, font=(FAMILY, 8, "bold"), padx=5)
            badge.pack(side="left", padx=(10 if action == "stop" else 0, 4))
            text = tk.Label(keys, text=word, bg=PANEL, fg=MUTED, font=F_SMALL)
            text.pack(side="left")
            self.key_labels[action] = (badge, text)
        self.keys_row = keys
        self.screen_w = screen_w
        self.made_click_through = False

    def _click_through(self):
        """Windows: let clicks pass through and keep it off the taskbar and out of Alt-Tab."""
        if self.made_click_through or not IS_WIN:
            return
        try:
            import ctypes

            u = ctypes.windll.user32
            hwnd = u.GetParent(self.win.winfo_id()) or self.win.winfo_id()
            style = u.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
            # LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE
            u.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20 | 0x80 | 0x8000000)
            self.made_click_through = True
        except Exception:
            pass

    def show(self, state, clock, note, color, keys=None):
        """keys: {"pause": "F10", "stop": "F12"} shows which keys pause and stop; None hides them."""
        self.state.config(text=state)
        self.clock.config(text=clock)
        self.note.config(text=note)
        if keys:
            for action, (badge, text) in self.key_labels.items():
                badge.config(text=keys[action])
                if action == "pause":
                    text.config(text="Resume" if state == "Paused" else "Pause")
            self.keys_row.pack(padx=14, pady=(2, 8))
        else:
            self.keys_row.pack_forget()
        self.dot.delete("all")
        self.dot.create_oval(1, 1, 11, 11, fill=color, outline="")
        w = self.win
        w.update_idletasks()
        width, height = max(w.winfo_reqwidth(), 210), w.winfo_reqheight()  # same size, so it doesn't jump
        w.geometry(f"{width}x{height}+{max(0, (self.screen_w - width) // 2)}+12")
        if w.state() == "withdrawn":
            w.deiconify()
            self._click_through()
        w.lift()
        w.attributes("-topmost", True)

    def hide(self):
        self.win.withdraw()


def format_clock(seconds):
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"


MAX_BACKGROUNDS = 5  # saved background pictures
MAX_MACROS = 20  # saved macros for the ◀ ▶ quick switch
VIDEO_THROUGH = ("While recording or playing", "Always")  # when clicks go through the video window
VIDEO_HINT = "Paste a YouTube video or playlist link"
SETTINGS_PAGES = ("General", "Recording", "Playback", "Picture watch", "Background", "Sounds", "About")


class BackgroundControls:
    """The background picture options for one window (Settings > Background): the picture,
    Darkness, Fit and which part shows. Saved in settings as <prefix>_picture, <prefix>_darkness...

    same_as: the main window's controls; this window can use the same picture as that one."""

    def __init__(self, app, prefix, get_backdrop, window, same_as=None):
        """get_backdrop: the Backdrop to paint (None = not shown right now); window: its window."""
        self.app, self.prefix, self.get_backdrop, self.same_as = app, prefix, get_backdrop, same_as
        self.window = window
        s = app.settings
        self.dark_var = tk.IntVar(value=core.int_setting(s, prefix + "_darkness", 40, 0, 90))
        fit = s.get(prefix + "_fit")
        self.fit_var = tk.StringVar(value=fit if fit in backdrop.FITS else "Fill the window")
        pos = s.get(prefix + "_position", 0)
        pos = backdrop.POSITIONS.get(pos, 0) if isinstance(pos, str) else pos  # older "Top"/"Middle"/"Bottom"
        self.pos_var = tk.DoubleVar(value=max(0, min(100, pos if isinstance(pos, (int, float)) else 0)))
        self.same_var = tk.BooleanVar(value=bool(s.get(prefix + "_same", True))) if same_as else None
        self.job = None
        self.built = False

    def file(self):
        """The picture file to show ("" = none)."""
        if self.same_var is not None and self.same_var.get():
            return self.same_as.file()
        name = self.picture()
        return os.path.join(os.path.dirname(core.settings_path()), name) if name else ""

    def picture(self):
        """This window's own pick from the saved pictures (file name, "" = none)."""
        name = self.app.settings.get(self.prefix + "_picture") or ""
        return name if any(e["file"] == name for e in self.app.bg_library()) else ""

    def picture_name(self):
        if self.same_var is not None and self.same_var.get():
            return self.same_as.picture_name()
        for e in self.app.bg_library():
            if e["file"] == self.picture():
                return e.get("name") or e["file"]
        return ""

    def save(self, s):
        s[self.prefix + "_darkness"] = int(float(self.dark_var.get()))
        s[self.prefix + "_fit"] = self.fit_var.get()
        s[self.prefix + "_position"] = int(round(float(self.pos_var.get())))
        if self.same_var is not None:
            s[self.prefix + "_same"] = bool(self.same_var.get())

    def build(self, f):
        app = self.app
        if self.same_var is not None:
            app._switch_row(f, "Same as the main window", self.same_var, "picture and all options",
                            command=lambda: (app._save_settings(), self.apply()))
        row = app._row(f, "Picture")
        # arrows go through the saved pictures (and "none")
        self.prev = link(row, "◀", lambda: self.step(-1), fg=TEXT, font=(FAMILY, 11))
        self.prev.pack(side="left", padx=(12, 0))
        self.name_label = tk.Label(row, bg=BG, fg=MUTED, font=F_SMALL, width=30)
        self.name_label.pack(side="left", padx=4)
        self.next = link(row, "▶", lambda: self.step(1), fg=TEXT, font=(FAMILY, 11))
        self.next.pack(side="left")
        self.remove = link(row, "Remove", self.remove_picture)
        self.remove.pack(side="right")
        self.choose = ttk.Button(row, text="Add…", width=6, command=self.add_picture)
        self.choose.pack(side="right", padx=(0, 10))
        row = app._row(f, "Darkness")
        self.dark_label = tk.Label(row, bg=BG, fg=TEXT, font=F_SMALL, width=4, anchor="e")
        self.dark_label.pack(side="right")
        self.dark_scale = ttk.Scale(row, from_=0, to=90, length=150, variable=self.dark_var,
                                    command=lambda v: self.changed())
        self.dark_scale.pack(side="right", padx=(0, 6))
        row = app._row(f, "Fit")
        self.fit_box = ttk.Combobox(row, width=22, state="readonly", textvariable=self.fit_var,
                                    values=list(backdrop.FITS))
        self.fit_box.pack(side="right")
        self.fit_box.bind("<<ComboboxSelected>>", lambda e: self.changed(now=True))
        row = app._row(f, "Show which part", "slide or scroll")
        self.pos_end = tk.Label(row, bg=BG, fg=MUTED, font=F_SMALL, width=8, anchor="w")
        self.pos_end.pack(side="right")
        self.pos_scale = ttk.Scale(row, from_=0, to=100, length=150, variable=self.pos_var,
                                   command=lambda v: self.changed(delay=40))
        self.pos_scale.pack(side="right", padx=6)
        self.pos_start = tk.Label(row, bg=BG, fg=MUTED, font=F_SMALL, width=4, anchor="e")
        self.pos_start.pack(side="right")

        def wheel(event):
            if "disabled" in self.pos_scale.state():
                return
            step = -1 if (event.delta > 0 or event.num == 4) else 1  # wheel down = further down
            self.pos_var.set(max(0, min(100, int(float(self.pos_var.get())) + step * 5)))
            self.changed(delay=40)
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.pos_scale.bind(ev, wheel)
        if not backdrop.AVAILABLE:
            self.choose.config(state="disabled")
        self.built = True
        self.show_state()

    def show_state(self):
        if not self.built:
            return
        path = self.file()
        on = bool(path) and backdrop.AVAILABLE and os.path.isfile(path)
        same = self.same_var is not None and self.same_var.get()
        lib = self.app.bg_library()
        if same:
            text = "same as main window" + (f": {short(self.picture_name())}" if self.same_as.file() else "")
        elif on:
            n = [e["file"] for e in lib].index(self.picture()) + 1
            text = f"{n} of {len(lib)}:  {short(self.picture_name())}"
        else:
            text = "none (plain dark window)" + (f"  ·  {len(lib)} saved" if lib else "")
        self.name_label.config(text=text)
        arrows = not same and bool(lib)
        for a, sym in ((self.prev, "◀"), (self.next, "▶")):
            a.config(text=sym if arrows else "", cursor="hand2" if arrows else "arrow")
        self.choose.config(state="disabled" if same or not backdrop.AVAILABLE else "normal")
        self.remove.config(text="Remove" if on and not same else "",
                           cursor="hand2" if on and not same else "arrow")
        own = on and not same  # with "Same as the main window" the main window's options are used
        self.fit_box.config(state="readonly" if own else "disabled")
        self.dark_scale.state(["!disabled"] if own else ["disabled"])
        # the slider moves the picture along the side that gets cut off (none: it all fits)
        win = self.window()
        axis = backdrop.cut_axis_for(path, backdrop.FITS.get(self.fit_var.get(), "cover"),
                                     win.winfo_width(), win.winfo_height()) if own else None
        self.pos_scale.state(["!disabled"] if axis else ["disabled"])
        ends = {"y": ("Top", "Bottom"), "x": ("Left", "Right")}.get(axis, ("", "all shown" if own else ""))
        self.pos_start.config(text=ends[0])
        self.pos_end.config(text=ends[1])
        self.dark_label.config(text=f"{int(float(self.dark_var.get()))}%" if not same else "")

    def apply(self):
        self.job = None
        b = self.get_backdrop()
        if b is None:
            self.show_state()
            return
        src = self.same_as if (self.same_var is not None and self.same_var.get()) else self
        b.set_picture(self.file(), darkness=int(float(src.dark_var.get())),
                      fit=backdrop.FITS.get(src.fit_var.get(), "cover"),
                      position=float(src.pos_var.get()) / 100)
        self.show_state()

    def changed(self, now=False, delay=150):
        if self.built:
            self.dark_label.config(text=f"{int(float(self.dark_var.get()))}%")
        self.app._save_settings()
        if self.job is not None:
            self.app.root.after_cancel(self.job)
        # both windows, as the settings window may follow the main window's options
        self.job = self.app.root.after(0 if now else delay, self.app._apply_background)

    def step(self, d):
        """◀ / ▶: the previous or next saved picture (going past the ends gives "none")."""
        if self.same_var is not None and self.same_var.get():
            return
        files = [""] + [e["file"] for e in self.app.bg_library()]
        if len(files) < 2:
            return
        i = files.index(self.picture()) if self.picture() in files else 0
        self.app.settings[self.prefix + "_picture"] = files[(i + d) % len(files)]
        self.app._save_settings()
        self.app._apply_background()

    def add_picture(self):
        app = self.app
        lib = app.bg_library()
        if len(lib) >= MAX_BACKGROUNDS:
            messagebox.showinfo("Macro Recorder", f"You can save up to {MAX_BACKGROUNDS} pictures.\n"
                                "Pick one you don't need with the arrows and click Remove first.",
                                parent=app.settings_win)
            return
        path = filedialog.askopenfilename(parent=app.settings_win, title="Add a background picture",
                                          filetypes=backdrop.PICTURE_TYPES)
        if not path:
            return
        folder = os.path.dirname(core.settings_path())
        used = {e["file"] for e in lib}
        used_stems = {os.path.splitext(f)[0] for f in used}
        stem = next(f"background_{i}" for i in range(1, 100) if f"background_{i}" not in used_stems)
        fname = backdrop.store_any(path, folder, stem)  # an animated .gif is kept as a .gif
        if not fname:
            messagebox.showerror("Macro Recorder", "That file couldn't be opened as a picture.\n"
                                 "Try a .png, .jpg, .gif, .bmp or .webp file.", parent=app.settings_win)
            return
        lib.append({"file": fname, "name": os.path.basename(path)})
        app.settings[self.prefix + "_picture"] = fname  # and use it here right away
        app._save_settings()
        app._apply_background()

    def remove_picture(self):
        """Take the shown picture out of the saved pictures (every window using it goes plain)."""
        app = self.app
        name = self.picture()
        if not name:
            return
        if not messagebox.askyesno("Macro Recorder", f"Remove \"{self.picture_name()}\" from your saved "
                                   "pictures?", parent=app.settings_win):
            return
        app.settings["background_library"] = [e for e in app.bg_library() if e["file"] != name]
        for key in list(app.settings):
            if key.endswith("_picture") and key.startswith(("background", "settings_background")) \
                    and app.settings[key] == name:
                app.settings[key] = ""
        try:
            os.remove(os.path.join(os.path.dirname(core.settings_path()), name))
        except OSError:
            pass
        app._save_settings()
        app._apply_background()


def short(text, n=26):
    return text if len(text) <= n else text[:n - 1] + "…"


class ModernMacroRecorder(core.MacroRecorder):
    def __init__(self, root, preview=False):
        self.preview = preview
        self.sub_note = "Record something, or open a macro"
        self.settings_win = None
        self.edit_win = None
        self.unsaved = False  # the open macro was edited and not saved since
        super().__init__(root)

    # ------------------------------------------------------------ main window

    def _build_ui(self):
        root = self.root
        s = self.settings
        root.title("Macro Recorder (preview)" if self.preview else "Macro Recorder")
        root.resizable(False, False)
        root.attributes("-topmost", bool(s.get("always_on_top", True)))
        apply_theme(root)
        try:
            self.icon_img = app_icon()
            root.iconphoto(True, self.icon_img)
        except Exception:
            pass
        dark_title_bar(root)

        # settings that the old window kept on its main screen (used by playback)
        self.repeat_var = tk.IntVar(value=core.int_setting(s, "repeat_count", 1, 1, 9999))
        self.loop_var = tk.BooleanVar(value=bool(s.get("loop", True)))
        self.speed_var = tk.StringVar(value=format_speed(parse_speed(s.get("speed", 1)) or 1.0))
        self.ready_var = tk.IntVar(value=core.int_setting(s, "ready_seconds", 3, 0, 600))
        self.target_windows = []
        self.target_var = tk.StringVar(value=SCREEN_TARGET)
        self.name_var = tk.StringVar(value="Untitled macro")
        self.sounds_var = tk.BooleanVar(value=bool(s.get("sounds", True)))
        self.player = sounds.Player()
        self.last_sound = 0.0
        root.bind_all("<Button-1>", self._click_sound, add="+")
        self.volume_var = tk.IntVar(value=sounds.volume_number(s.get("sound_volume", sounds.DEFAULT_VOLUME)))
        self.statusbar_var = tk.BooleanVar(value=bool(s.get("status_bar", True)))
        self.ontop_var = tk.BooleanVar(value=bool(s.get("always_on_top", True)))
        self.overlay_var = tk.BooleanVar(value=bool(s.get("play_overlay", True)))
        self.overlay = None
        self.overlay_job = None
        self.play_began = None
        self.play_paused_at = None  # when playback was paused (None = not paused)
        self.play_pause_total = 0.0
        self.held_now = None  # the keys and buttons the macro is holding down right now
        self.rec_moves_var = tk.BooleanVar(value=bool(s.get("record_mouse_moves", True)))
        self.detail_var = tk.StringVar(value=s.get("mouse_detail", "Smooth")
                                       if s.get("mouse_detail") in MOUSE_DETAIL else "Smooth")
        # the YouTube video window over the game
        self.video_var = tk.StringVar(value=str(s.get("video_link", "")))
        self.video_through_var = tk.StringVar(
            value=s.get("video_click_through") if s.get("video_click_through") in VIDEO_THROUGH
            else VIDEO_THROUGH[0])
        self.video_opacity_var = tk.IntVar(value=core.int_setting(s, "video_opacity", 100, 20, 100))
        def setup_video_window(win):
            dark_title_bar(win)
            if getattr(self, "icon_img", None) is not None:
                win.iconphoto(False, self.icon_img)
        self.video = video_overlay.make_overlay(
            os.path.join(os.path.dirname(core.settings_path()), "video_browser"), root=root,
            on_closed=lambda: self._video_closed(), setup_window=setup_video_window)
        r = s.get("video_rect")
        if isinstance(r, list) and len(r) == 4 and all(isinstance(v, int) for v in r):
            self.video.rect = tuple(r)
        self.video.opacity = self.video_opacity_var.get()
        self.video_job = None

        outer = tk.Frame(root, bg=BG)
        outer.pack(fill="both", expand=True)

        # header: name of the app + settings
        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x", padx=18, pady=(14, 10))
        mark = tk.Canvas(head, width=30, height=30, bg=BG, highlightthickness=0)
        rounded_rect(mark, 1, 1, 29, 29, 8, fill=ACCENT, outline="")
        mark.create_oval(9, 9, 21, 21, fill="white", outline="")
        mark.pack(side="left")
        tk.Label(head, text="Macro Recorder", bg=BG, fg=TEXT, font=F_TITLE).pack(side="left", padx=(10, 0))
        if self.preview:
            tk.Label(head, text="PREVIEW", bg=AMBER, fg="#111", font=(FAMILY, 7, "bold"),
                     padx=4).pack(side="left", padx=(8, 0), pady=(4, 0))
        gear = link(head, "⚙  Settings", self.open_settings, fg=MUTED, font=(FAMILY, 10))
        gear.pack(side="right")

        panel = tk.Frame(outer, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        panel.pack(fill="both", expand=True, padx=12)
        body = tk.Frame(panel, bg=PANEL)
        body.pack(fill="both", expand=True, padx=16, pady=14)

        # status
        st = tk.Frame(body, bg=PANEL)
        st.pack(fill="x")
        self.status_dot = tk.Canvas(st, width=16, height=16, bg=PANEL, highlightthickness=0)
        self.status_dot.pack(side="left")
        self.status_var = tk.StringVar()
        tk.Label(st, textvariable=self.status_var, bg=PANEL, fg=TEXT, font=F_STATUS).pack(side="left", padx=(8, 0))
        self.sub_var = tk.StringVar()
        tk.Label(body, textvariable=self.sub_var, bg=PANEL, fg=MUTED, font=F_BASE, anchor="w").pack(
            anchor="w", pady=(4, 14))

        # the four big buttons
        cards = tk.Frame(body, bg=PANEL)
        cards.pack(fill="x")
        self.card_record = Card(cards, "record", "Record", RED, self.toggle_record)
        self.card_pause = Card(cards, "pause", "Pause", AMBER, self.toggle_pause)
        self.card_play = Card(cards, "play", "Play", ACCENT, self.play)
        self.card_stop = Card(cards, "stop", "Stop", MUTED, self.stop_playback)
        for i, c in enumerate((self.card_record, self.card_pause, self.card_play, self.card_stop)):
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            cards.columnconfigure(i, weight=1, uniform="cards", minsize=118)

        # repeat + speed
        rep = tk.Frame(body, bg=PANEL)
        rep.pack(fill="x", pady=(14, 0))
        self.loop_switch = Switch(rep, self.loop_var, command=self._loop_changed, bg=PANEL)
        self.loop_switch.pack(side="left")
        tk.Label(rep, text="Repeat continuously", bg=PANEL, fg=TEXT, font=F_BASE).pack(side="left", padx=(10, 0))
        self.times_frame = tk.Frame(rep, bg=PANEL)
        tk.Label(self.times_frame, text="   or play", bg=PANEL, fg=MUTED, font=F_BASE).pack(side="left")
        self.repeat_box = ttk.Spinbox(self.times_frame, from_=1, to=9999, width=5, textvariable=self.repeat_var,
                                      command=self._save_settings)
        self.repeat_box.pack(side="left", padx=4)
        tk.Label(self.times_frame, text="times", bg=PANEL, fg=MUTED, font=F_BASE).pack(side="left")
        self.speed_box = ttk.Combobox(rep, width=6, textvariable=self.speed_var, values=SPEED_PRESETS)
        self.speed_box.pack(side="right")
        tk.Label(rep, text="Speed", bg=PANEL, fg=MUTED, font=F_BASE).pack(side="right", padx=(0, 6))
        for ev in ("<FocusOut>", "<Return>", "<<ComboboxSelected>>"):
            self.speed_box.bind(ev, lambda e: self._check_speed(quiet=True))
        self._loop_changed(save=False)

        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=14)

        # quick switch: ◀ ▶ go through the saved macros (every macro opened or saved goes in the list)
        sw = tk.Frame(body, bg=PANEL)
        sw.pack(fill="x", pady=(0, 8))
        tk.Label(sw, text="Saved macros", bg=PANEL, fg=MUTED, font=F_SMALL).pack(side="left")
        self.mac_prev = link(sw, "◀", lambda: self.step_macro(-1), bg=PANEL, fg=TEXT, font=(FAMILY, 11))
        self.mac_prev.pack(side="left", padx=(10, 0))
        self.mac_label = tk.Label(sw, bg=PANEL, fg=MUTED, font=F_SMALL, width=34)
        self.mac_label.pack(side="left", padx=4)
        self.mac_next = link(sw, "▶", lambda: self.step_macro(1), bg=PANEL, fg=TEXT, font=(FAMILY, 11))
        self.mac_next.pack(side="left")
        self.mac_remove = link(sw, "Remove", self.remove_macro_from_list, bg=PANEL)
        self.mac_remove.pack(side="right")

        # a YouTube video or playlist in a window over the game
        vid = tk.Frame(body, bg=PANEL)
        vid.pack(fill="x", pady=(0, 8))
        tk.Label(vid, text="Video", bg=PANEL, fg=MUTED, font=F_SMALL).pack(side="left")
        self.video_entry = tk.Entry(vid, textvariable=self.video_var, bg=FIELD, fg=TEXT, font=F_SMALL,
                                    relief="flat", insertbackground=TEXT, highlightthickness=1,
                                    highlightbackground=BORDER, highlightcolor=ACCENT)
        self.video_entry.pack(side="left", fill="x", expand=True, padx=(10, 6), ipady=3)
        self.video_entry.bind("<Return>", lambda e: self.show_video())
        self.btn_video = ttk.Button(vid, text="Show", width=7, command=self.toggle_video)
        self.btn_video.pack(side="right")
        self._video_hint()

        # the macro: its name, size and file buttons
        mac = tk.Frame(body, bg=PANEL)
        mac.pack(fill="x")
        self.name_entry = tk.Entry(mac, textvariable=self.name_var, bg=PANEL, fg=TEXT, font=(FAMILY, 11, "bold"),
                                   relief="flat", insertbackground=TEXT, highlightthickness=0, width=22)
        self.name_entry.pack(side="left", fill="x", expand=True)
        self.name_entry.bind("<Return>", lambda e: self.root.focus_set())
        self.btn_save = ttk.Button(mac, text="Save…", command=self.save)
        self.btn_load = ttk.Button(mac, text="Open…", command=self.load)
        self.btn_edit = ttk.Button(mac, text="Edit…", command=self.open_editor)
        for b in (self.btn_save, self.btn_load, self.btn_edit):
            b.pack(side="right", padx=(6, 0))
        self.info_var = tk.StringVar()
        tk.Label(body, textvariable=self.info_var, bg=PANEL, fg=MUTED, font=F_SMALL, anchor="w").pack(
            anchor="w", pady=(2, 0))

        # footer: status bar + version
        foot = tk.Frame(outer, bg=BG)
        foot.pack(fill="x", padx=18, pady=(8, 10))
        self.statusbar_label = tk.Label(foot, bg=BG, fg=DIM, font=F_SMALL, anchor="w")
        self.statusbar_label.pack(side="left")
        link(foot, "About", lambda: self.open_settings("About"), fg=MUTED).pack(side="right")
        tk.Label(foot, text=f"v{APP_VERSION}", bg=BG, fg=DIM, font=F_SMALL).pack(side="right", padx=(0, 8))

        # an optional picture behind the window (Settings > Background)
        self.backdrop = backdrop.Backdrop(
            root, see_through=(BG, PANEL), base_color=BG, glass=panel, glass_color=PANEL,
            skip=(self.card_record, self.card_pause, self.card_play, self.card_stop),
            lift_colors={DIM: MUTED, MUTED: "#c2c2cc"})
        self._bg_library_upgrade()
        self.bg_main = BackgroundControls(self, "background", lambda: self.backdrop, lambda: self.root)
        # the settings window: one background for every page, or one for each page
        self.bg_per_page_var = tk.BooleanVar(value=bool(s.get("settings_background_per_page", False)))
        self.bg_page_var = tk.StringVar(value=SETTINGS_PAGES[0])
        self.bg_animate_var = tk.BooleanVar(value=bool(s.get("background_animate", True)))

        def settings_controls(prefix):
            c = BackgroundControls(self, prefix, None, self._settings_page, same_as=self.bg_main)
            c.get_backdrop = lambda: (getattr(self, "settings_backdrop", None)
                                      if self._settings_bg_controls() is c else None)
            return c
        self.bg_settings = settings_controls("settings_background")
        self.bg_pages = {page: settings_controls("settings_background_" + page.lower().replace(" ", "_"))
                         for page in SETTINGS_PAGES}
        root.after(80, self._apply_background)

        self._build_settings_window()

    def _loop_changed(self, save=True):
        if self.loop_var.get():
            self.times_frame.pack_forget()
        else:
            self.times_frame.pack(side="left")
        if getattr(self, "backdrop", None) is not None:
            self.root.after_idle(self.backdrop.refresh)
        if save:
            self._save_settings()

    # ------------------------------------------------------------ settings window

    def _build_settings_window(self):
        win = tk.Toplevel(self.root, bg=BG)
        win.withdraw()
        self.settings_win = win
        win.title("Settings - Macro Recorder")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", self.close_settings)
        self.tabs = ttk.Notebook(win)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.tab_frames = {}
        for name in SETTINGS_PAGES:
            f = ttk.Frame(self.tabs, padding=(18, 14))
            self.tabs.add(f, text=name)
            self.tab_frames[name] = f
        self._build_general_tab(self.tab_frames["General"])
        self._build_recording_tab(self.tab_frames["Recording"])
        self._build_playback_tab(self.tab_frames["Playback"])
        watch = self.tab_frames["Picture watch"]
        self._build_watch_ui(watch)
        self._build_background_tab(self.tab_frames["Background"])
        self._build_sounds_tab(self.tab_frames["Sounds"])
        self._build_about_tab(self.tab_frames["About"])
        self._recolor_notes(win)
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=12)
        ttk.Button(bottom, text="Done", style="Accent.TButton", command=self.close_settings).pack(side="right")
        self._title_labels(win)
        # every page the same size (the biggest page, with a little room for lists that grow), so the
        # window doesn't change size between pages
        win.update_idletasks()
        self.tabs.configure(width=max(f.winfo_reqwidth() for f in self.tab_frames.values()),
                            height=max(f.winfo_reqheight() for f in self.tab_frames.values()) + 40)
        # the background picture shows here too (darker behind the pages, as there's more text)
        self.settings_backdrop = backdrop.Backdrop(
            win, see_through=(BG,), base_color=BG, glass=self.tabs, glass_color=BG, glass_mix=0.55,
            area=self._settings_page,  # only behind the page, not the tabs or the Done button
            lift_colors={DIM: MUTED, MUTED: "#c2c2cc"})
        self.tabs.bind("<<NotebookTabChanged>>", lambda e: win.after(10, self._settings_tab_changed), add="+")

    def _settings_page(self):
        """The settings page that's open (the area the background picture fills)."""
        try:
            return self.tabs.nametowidget(str(self.tabs.select()))
        except (AttributeError, KeyError, tk.TclError):
            return self.settings_win

    def _settings_tab_changed(self):
        if self.bg_per_page_var.get():  # each page may have its own background
            self._settings_bg_controls().apply()
        self.settings_backdrop.repaint()

    def _title_labels(self, widget):
        """Boxes with a title get it as a separate label, so the background picture can go behind it."""
        for child in widget.winfo_children():
            if isinstance(child, ttk.Labelframe) and not str(child.cget("labelwidget")):
                child.config(labelwidget=tk.Label(child, text=child.cget("text"), bg=BG, fg=MUTED,
                                                  font=F_SECTION))
            self._title_labels(child)

    def _recolor_notes(self, widget):
        """The old option boxes used dark-red and grey notes made for a white window."""
        for child in widget.winfo_children():
            if isinstance(child, ttk.Label):
                fg = str(child.cget("foreground"))
                if fg == "#b00000":
                    child.config(foreground=RED)
                elif fg == "gray":
                    child.config(foreground=MUTED)
            self._recolor_notes(child)

    def _section(self, parent, text, first=False):
        if not first:
            ttk.Separator(parent).pack(fill="x", pady=(12, 10))
        tk.Label(parent, text=text, bg=BG, fg=MUTED, font=F_SECTION, anchor="w").pack(fill="x", pady=(0, 6))

    def _row(self, parent, text, tip=None):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=text, bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
        if tip:
            tk.Label(row, text=tip, bg=BG, fg=DIM, font=F_SMALL).pack(side="left", padx=(8, 0))
        return row

    def _switch_row(self, parent, text, var, tip=None, command=None):
        row = self._row(parent, text, tip)
        sw = Switch(row, var, command=command or self._save_settings)
        sw.pack(side="right")
        return sw

    def _build_general_tab(self, f):
        self._section(f, "SHORTCUTS", first=True)
        self.key_badges = {}
        self.change_links = {}
        for action in HOTKEY_ACTIONS:
            row = self._row(f, core.HOTKEY_LABELS[action])
            ch = link(row, "Change", lambda a=action: self._capture_hotkey(a))
            ch.pack(side="right")
            badge = tk.Label(row, bg=BADGE, fg=TEXT, font=(FAMILY, 9, "bold"), padx=8, pady=2, width=10)
            badge.pack(side="right", padx=(0, 10))
            self.key_badges[action] = badge
            self.change_links[action] = ch
        r = tk.Frame(f, bg=BG)
        r.pack(fill="x")
        link(r, "Reset to F9 - F12", self._reset_hotkeys).pack(side="right")
        tk.Label(f, text="Pick keys you don't use in the game: a shortcut is never recorded or sent.",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x", pady=(4, 0))

        self._section(f, "INTERFACE")
        self._switch_row(f, "Status bar", self.statusbar_var, "shortcuts and options at the bottom",
                         command=lambda: (self._save_settings(), self._refresh()))
        self._switch_row(f, "Keep window on top", self.ontop_var,
                         command=lambda: (self._save_settings(),
                                          self.root.attributes("-topmost", bool(self.ontop_var.get()))))
        if IS_WIN:
            self._section(f, "FILES")
            row = self._row(f, "Open .macro files with a double-click")
            b = ttk.Button(row, text="Link .macro files", command=self.link_file_type)
            b.pack(side="right")
            if self.preview:
                b.config(state="disabled")  # the preview must not take over your real app's files
                tk.Label(f, text="Turned off in the preview, so your .macro files keep opening your real app.",
                         bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x")

    # ------------------------------------------------------------ sounds

    SOUND_DEFAULT, SOUND_OFF, SOUND_CHOOSE = "Default sound", "No sound", "Choose a file…"

    def _build_sounds_tab(self, f):
        self._section(f, "SOUNDS", first=True)
        self._switch_row(f, "Sounds", self.sounds_var, "off = the app is completely quiet")
        row = self._row(f, "Volume", "slide or scroll")
        self.volume_label = tk.Label(row, bg=BG, fg=TEXT, font=F_SMALL, width=5, anchor="e")
        self.volume_label.pack(side="right")
        tk.Label(row, text="High", bg=BG, fg=MUTED, font=F_SMALL).pack(side="right")
        vol = ttk.Scale(row, from_=0, to=100, length=170, command=lambda v: self._volume_moved(v))
        vol.set(self.volume_var.get())
        vol.pack(side="right", padx=6)
        tk.Label(row, text="Low", bg=BG, fg=MUTED, font=F_SMALL).pack(side="right")
        self.volume_scale = vol
        # letting go of the bar plays a sound, so you hear how loud it is now
        vol.bind("<ButtonRelease-1>", lambda e: self._volume_chosen())

        def wheel(event):
            step = 5 if (event.delta > 0 or event.num == 4) else -5  # wheel up = louder
            vol.set(max(0, min(100, self.volume_var.get() + step)))
            if getattr(self, "volume_job", None) is not None:
                self.root.after_cancel(self.volume_job)
            self.volume_job = self.root.after(250, self._volume_chosen)
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            vol.bind(ev, wheel)
        self._volume_moved(self.volume_var.get())
        self._section(f, "YOUR SOUNDS")
        self.sound_vars, self.sound_boxes = {}, {}
        for event, label, tip, _on in sounds.EVENTS:
            row = self._row(f, label, tip or None)
            box_var = tk.StringVar()
            box = ttk.Combobox(row, width=24, state="readonly", textvariable=box_var)
            box.pack(side="right")
            box.bind("<<ComboboxSelected>>", lambda e, ev=event: self._sound_picked(ev))
            link(row, "▶ Try", lambda ev=event: self._sound(ev, test=True), fg=TEXT,
                 font=F_SMALL).pack(side="right", padx=(0, 10))
            self.sound_vars[event], self.sound_boxes[event] = box_var, box
        r = tk.Frame(f, bg=BG)
        r.pack(fill="x", pady=(4, 0))
        link(r, "Set all back to how they were", self._reset_sounds).pack(side="right")
        tk.Label(f, text="Pick \"Choose a file…\" to use a sound of your own (.wav or .mp3). "
                         "Your sounds stay on this computer.",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x", pady=(6, 0))
        self._show_sounds()

    def _volume_moved(self, value):
        self.volume_var.set(sounds.volume_number(value))
        v = self.volume_var.get()
        self.volume_label.config(text=f"{v}%" if v else "off")

    def _volume_chosen(self):
        self.volume_job = None
        self._save_settings()
        self._sound("play_start", test=True, even_if_off=True)

    def sound_choice(self, event):
        """What an event sounds like: {"mode": "default" / "off" / "custom", "file": stored file name,
        "name": the name of the file you picked}."""
        choices = self.settings.get("sound_choices")
        if not isinstance(choices, dict):
            choices = self.settings["sound_choices"] = {}
        c = choices.get(event)
        if not isinstance(c, dict) or c.get("mode") not in ("default", "off", "custom"):
            c = choices[event] = {"mode": "default" if self._sound_on_at_first(event) else "off"}
        return c

    @staticmethod
    def _sound_on_at_first(event):
        return next((on for ev, _l, _t, on in sounds.EVENTS if ev == event), True)

    def _sound_folder(self):
        return os.path.join(os.path.dirname(core.settings_path()), "sounds")

    def _sound_file(self, event):
        """Your own sound file for an event ("" = there isn't one)."""
        name = self.sound_choice(event).get("file") or ""
        path = os.path.join(self._sound_folder(), os.path.basename(name)) if name else ""
        return path if path and os.path.isfile(path) else ""

    def _show_sounds(self):
        for event, box in self.sound_boxes.items():
            c = self.sound_choice(event)
            own = short(c.get("name") or "", 30) if self._sound_file(event) else ""
            values = [self.SOUND_DEFAULT, self.SOUND_OFF] + ([own] if own else []) + [self.SOUND_CHOOSE]
            box.config(values=values)
            mode = c["mode"] if (c["mode"] != "custom" or own) else "default"
            self.sound_vars[event].set({"default": self.SOUND_DEFAULT, "off": self.SOUND_OFF}.get(mode, own))

    def _sound_picked(self, event):
        picked = self.sound_vars[event].get()
        self.sound_boxes[event].selection_clear()
        c = self.sound_choice(event)
        if picked == self.SOUND_CHOOSE:
            self._show_sounds()  # (the box shows what it was while the file window is open)
            self._choose_sound(event)
            return
        if picked == self.SOUND_DEFAULT:
            c["mode"] = "default"
        elif picked == self.SOUND_OFF:
            c["mode"] = "off"
        else:
            c["mode"] = "custom"
        self._save_settings()
        self._show_sounds()
        if picked != self.SOUND_OFF:
            self._sound(event, test=True)

    def _choose_sound(self, event):
        path = filedialog.askopenfilename(parent=self.settings_win, title="Choose a sound",
                                          filetypes=sounds.SOUND_TYPES)
        if not path:
            return
        if not self.player.can_play(path):
            messagebox.showerror("Macro Recorder", "That file couldn't be played as a sound.\n"
                                 "Try a .wav or .mp3 file.", parent=self.settings_win)
            return
        c = self.sound_choice(event)
        folder = self._sound_folder()
        stored = event + os.path.splitext(path)[1].lower()
        try:
            self.player.stop()  # lets go of the old file, so it can be replaced
            os.makedirs(folder, exist_ok=True)
            old = self._sound_file(event)
            if old and os.path.basename(old) != stored:
                os.remove(old)
            shutil.copyfile(path, os.path.join(folder, stored))
        except OSError as exc:
            messagebox.showerror("Macro Recorder", f"Couldn't copy the sound:\n{exc}", parent=self.settings_win)
            return
        c.update(mode="custom", file=stored, name=os.path.basename(path))
        self._save_settings()
        self._show_sounds()
        self._sound(event, test=True)

    def _reset_sounds(self):
        """Every event back to its built-in beep (or silence, for the ones that start silent).
        Your own files stay in the lists, so you can pick them again."""
        for event in sounds.EVENT_IDS:
            self.sound_choice(event)["mode"] = "default" if self._sound_on_at_first(event) else "off"
        self._save_settings()
        self._show_sounds()

    def _sound(self, name, test=False, even_if_off=False):
        """Play an event's sound. test: also when Sounds is switched off (the Try buttons);
        even_if_off: an event set to "No sound" plays its beep (to hear the volume)."""
        if not (test or self.sounds_var.get()):
            return
        mode = self.sound_choice(name)["mode"]
        if mode == "off" and not even_if_off:
            return
        self.last_sound = time.perf_counter()
        volume = self.volume_var.get()
        path = self._sound_file(name) if mode == "custom" else ""
        if path:
            self.player.play_file(path, volume, fallback=name)
        else:
            self.player.beep(name, volume)

    def _click_sound(self, event):
        """A click on a button, switch or link in this app (if "Button click" has a sound)."""
        if not self.sounds_var.get() or self.sound_choice("click")["mode"] == "off":
            return
        w = event.widget
        try:
            clickable = w.winfo_class() in ("TButton", "TCheckbutton") or str(w.cget("cursor")) == "hand2"
        except (AttributeError, tk.TclError):
            return
        asked = time.perf_counter()
        if clickable and asked - self.last_sound > 0.05:
            # the click's own sound (say, "Recording starts") goes first
            self.root.after(30, lambda: self._sound("click") if self.last_sound < asked else None)

    # ------------------------------------------------------------ background picture

    def _build_background_tab(self, f):
        self._section(f, "MAIN WINDOW", first=True)
        self.bg_main.build(f)
        self._section(f, "SETTINGS WINDOW")
        self._switch_row(f, "A different background for each page", self.bg_per_page_var,
                         command=self._bg_pages_changed)
        page_holder = tk.Frame(f, bg=BG)
        page_holder.pack(fill="x")
        self.bg_page_row = tk.Frame(page_holder, bg=BG)
        tk.Label(self.bg_page_row, text="Page", bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
        tk.Label(self.bg_page_row, text="the options below are for this page", bg=BG, fg=DIM,
                 font=F_SMALL).pack(side="left", padx=(8, 0))
        box = ttk.Combobox(self.bg_page_row, width=14, state="readonly", textvariable=self.bg_page_var,
                           values=list(SETTINGS_PAGES))
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>", lambda e: self._bg_show_controls())
        holder = tk.Frame(f, bg=BG)
        holder.pack(fill="x")
        self.bg_frames = {}
        for c in [self.bg_settings] + list(self.bg_pages.values()):
            frame = tk.Frame(holder, bg=BG)
            c.build(frame)
            self.bg_frames[c] = frame
        self._section(f, "ANIMATED PICTURES (.GIF)")
        self._switch_row(f, "Play animated pictures", self.bg_animate_var,
                         "they stand still while recording or playing",
                         command=lambda: (self._save_settings(), self._apply_animation()))
        tk.Label(f, text="Darker = easier to read. Your pictures stay on this computer.",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x", pady=(10, 0))
        if not backdrop.AVAILABLE:
            tk.Label(f, text="Needs the picture tools (numpy + opencv), which aren't installed.",
                     bg=BG, fg=RED, font=F_SMALL, anchor="w").pack(fill="x")
        self._bg_show_controls()

    def bg_library(self):
        """The saved background pictures: [{"file": stored file name, "name": original name}], up to 5."""
        lib = self.settings.get("background_library")
        if not isinstance(lib, list):
            lib = self.settings["background_library"] = []
        return lib

    def _bg_library_upgrade(self):
        """Pictures chosen before there was a list of saved pictures go into the list."""
        if isinstance(self.settings.get("background_library"), list):
            return
        lib = self.bg_library()
        folder = os.path.dirname(core.settings_path())
        for key in [k for k in self.settings if k.endswith("_picture") and
                    k.startswith(("background", "settings_background"))]:
            name = self.settings.get(key)
            if name and os.path.isfile(os.path.join(folder, name)) and len(lib) < MAX_BACKGROUNDS \
                    and all(e["file"] != name for e in lib):
                original = self.settings.get(key[:-len("_picture")] + "_original") or name
                lib.append({"file": name, "name": original})

    def _settings_bg_controls(self):
        """The options the settings window shows right now: the shared ones, or the open page's."""
        if not self.bg_per_page_var.get():
            return self.bg_settings
        try:
            page = self.tabs.tab(self.tabs.select(), "text")
        except (AttributeError, tk.TclError):
            page = SETTINGS_PAGES[0]
        return self.bg_pages.get(page, self.bg_settings)

    def _bg_show_controls(self):
        """Show the options of every page together, or of the page picked in the Page box."""
        per_page = self.bg_per_page_var.get()
        if per_page:
            self.bg_page_row.pack(fill="x", pady=4)
        else:
            self.bg_page_row.pack_forget()
        shown = self.bg_pages.get(self.bg_page_var.get(), self.bg_settings) if per_page else self.bg_settings
        for c, frame in self.bg_frames.items():
            if c is shown:
                frame.pack(fill="x")
            else:
                frame.pack_forget()
        shown.show_state()
        if getattr(self, "settings_backdrop", None) is not None:
            self.settings_win.after_idle(self.settings_backdrop.refresh)

    def _bg_pages_changed(self):
        self._save_settings()
        self._bg_show_controls()
        self._apply_background()

    def _apply_animation(self):
        """Animated pictures play, unless that's switched off or a macro is recording or playing
        (then nothing else is going on in the app, so the macro's timing stays exact)."""
        for b in (getattr(self, "backdrop", None), getattr(self, "settings_backdrop", None)):
            if b is not None:
                b.set_animate(self.bg_animate_var.get())
                b.set_paused(self.recording or self.playing)

    def _apply_background(self):
        self._apply_animation()
        self.bg_main.apply()
        self._settings_bg_controls().apply()
        for c in [self.bg_settings] + list(self.bg_pages.values()):
            c.show_state()

    def _build_recording_tab(self, f):
        self._section(f, "MOUSE", first=True)
        self._switch_row(f, "Record mouse movement", self.rec_moves_var,
                         "off = only clicks, scrolls and keys")
        row = self._row(f, "Mouse detail")
        box = ttk.Combobox(row, width=9, state="readonly", textvariable=self.detail_var, values=list(MOUSE_DETAIL))
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>", lambda e: self._save_settings())
        tk.Label(f, text="Smooth keeps every small movement (bigger files). Light keeps fewer points.",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x")
        self._section(f, "GOOD TO KNOW")
        tk.Label(f, justify="left", bg=BG, fg=MUTED, font=F_BASE, anchor="w", text=(
            "Your shortcut keys are never recorded.\n"
            "Clicks on this app's window are not recorded.\n"
            "Pause stops recording for a moment without making a gap in the macro.")).pack(fill="x")
        self._section(f, "THIS RECORDING")
        row = self._row(f, "Start over with an empty macro")
        self.btn_clear = ttk.Button(row, text="Clear", style="Danger.TButton", command=self.clear)
        self.btn_clear.pack(side="right")

    def _build_playback_tab(self, f):
        self._section(f, "BEFORE PLAYING", first=True)
        row = self._row(f, "Countdown", "seconds to switch to the game (0 = start at once)")
        ttk.Spinbox(row, from_=0, to=600, width=5, textvariable=self.ready_var,
                    command=self._save_settings).pack(side="right")
        self._switch_row(f, "Timer at the top of the screen", self.overlay_var,
                         "countdown, then how long it's been playing")
        self._section(f, "HOW TO PLAY")
        row = self._row(f, "Play into")
        self.target_box = ttk.Combobox(row, width=30, state="readonly", textvariable=self.target_var,
                                       postcommand=self._refresh_windows)
        self.target_box.pack(side="right")
        if background is None:
            self.target_box.config(state="disabled")
        self._refresh_windows()
        tk.Label(f, text="Background playback is experimental and can't turn a game's camera.",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x")
        holder = ttk.Frame(f)
        holder.pack(fill="x", pady=(12, 0))
        self._build_resolution_ui(holder)
        self._section(f, "VIDEO WINDOW")
        row = self._row(f, "Clicks go through it", "so the macro and the game don't notice it")
        box = ttk.Combobox(row, width=24, state="readonly", textvariable=self.video_through_var,
                           values=VIDEO_THROUGH)
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>", lambda e: (self._save_settings(), self._video_mode()))
        row = self._row(f, "See-through", "lower shows more of the game")
        scale = ttk.Scale(row, from_=20, to=100, length=160, variable=self.video_opacity_var,
                          command=lambda v: self._video_opacity())
        scale.pack(side="right")
        scale.bind("<ButtonRelease-1>", lambda e: self._save_settings())

    def _build_about_tab(self, f):
        tk.Label(f, text="Macro Recorder", bg=BG, fg=TEXT, font=(FAMILY, 14, "bold"), anchor="w").pack(fill="x")
        tk.Label(f, text=f"Version {APP_VERSION}" + (" (preview)" if self.preview else ""), bg=BG, fg=MUTED,
                 font=F_BASE, anchor="w").pack(fill="x", pady=(2, 10))
        tk.Label(f, justify="left", bg=BG, fg=MUTED, font=F_BASE, anchor="w", text=(
            "Records your mouse and keyboard and plays them back.\n\n"
            "Opens .macro files, and also .luvmacro, TinyTask .rec, Jitbit .mcr\n"
            "and simple AutoHotkey .ahk files.\n\n"
            "Settings are kept in:")).pack(fill="x")
        tk.Label(f, text=os.path.dirname(core.settings_path()), bg=BG, fg=TEXT, font=F_SMALL, anchor="w",
                 wraplength=420, justify="left").pack(fill="x", pady=(2, 0))

    def open_settings(self, tab=None):
        if self.recording or self.playing:
            return
        win = self.settings_win
        win.deiconify()
        dark_title_bar(win)
        win.lift()
        if tab in self.tab_frames:
            self.tabs.select(self.tab_frames[tab])
        self._refresh()
        win.after(60, lambda: (self.settings_backdrop.repaint(), self._bg_show_controls()))

    def close_settings(self):
        self.capture_callback = None
        self._read_play_on(quiet=True)
        self._read_made_for(quiet=True)
        self._save_settings()
        self.settings_win.withdraw()
        self._refresh()

    def open_hotkeys(self):  # the old "Hotkeys..." window is now Settings > General
        self.open_settings("General")

    def _capture_hotkey(self, action):
        if self.capture_callback is not None:
            return
        self.key_badges[action].config(text="Press a key…", fg=AMBER)

        def got_key(key_id):  # runs on the Tk thread
            self.capture_callback = None
            if key_id and key_id != "esc":
                for other in HOTKEY_ACTIONS:
                    if other != action and self.hotkeys[other] == key_id:
                        self.hotkeys[other] = self.hotkeys[action]  # swap: two actions never share a key
                self.hotkeys[action] = key_id
                self._save_settings()
            self._refresh()

        self.capture_callback = got_key

    def _reset_hotkeys(self):
        self.capture_callback = None
        self.hotkeys = dict(core.DEFAULT_HOTKEYS)
        self._save_settings()
        self._refresh()

    # ------------------------------------------------------------ Edit window

    def open_editor(self):
        if self.recording or self.playing:
            return
        if not self.events:
            messagebox.showinfo("Macro Recorder", "There's nothing to edit yet. Record or open a macro first.")
            return
        if self.edit_win is not None and self.edit_win.winfo_exists():
            self.edit_win.lift()
            return
        events = [dict(ev) for ev in self.events]
        win = tk.Toplevel(self.root, bg=BG)
        self.edit_win = win
        win.title(f"Edit - {self.name_var.get()}")
        win.attributes("-topmost", True)
        win.geometry("560x520")
        win.minsize(460, 360)
        dark_title_bar(win)

        top = tk.Frame(win, bg=BG)
        top.pack(fill="x", padx=14, pady=(12, 6))
        summary = tk.StringVar()
        tk.Label(top, textvariable=summary, bg=BG, fg=MUTED, font=F_BASE, anchor="w").pack(side="left")

        table = tk.Frame(win, bg=BG)
        table.pack(fill="both", expand=True, padx=14)
        tree = ttk.Treeview(table, columns=("time", "action", "detail"), show="headings", selectmode="extended")
        for col, text, width in (("time", "Time", 80), ("action", "Action", 160), ("detail", "Details", 220)):
            tree.heading(col, text=text, anchor="w")
            tree.column(col, width=width, anchor="w", stretch=col == "detail")
        bar = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=bar.set)
        tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        tree.tag_configure("move", foreground=MUTED)

        def fill():
            tree.delete(*tree.get_children())
            for i, ev in enumerate(events):
                action, detail = describe(ev)
                tags = ("move",) if ev.get("type") in ("move", "move_rel") else ()
                tree.insert("", "end", iid=str(i), values=(f"{ev['t']:.2f} s", action, detail), tags=tags)
            length = events[-1]["t"] if events else 0
            summary.set(f"{len(events)} actions, {length:.1f} s. Select rows (Ctrl/Shift for more) to remove them.")

        def remove_selected():
            picked = {int(i) for i in tree.selection()}
            if not picked:
                return
            events[:] = [ev for i, ev in enumerate(events) if i not in picked]
            fill()

        def remove_moves():
            n = sum(1 for ev in events if ev.get("type") == "move")
            if not n:
                messagebox.showinfo("Macro Recorder", "There are no mouse moves to remove.", parent=win)
                return
            if messagebox.askyesno("Macro Recorder", f"Remove all {n} mouse moves? Clicks keep their position, "
                                   "and camera turns are kept.", parent=win):
                events[:] = [ev for ev in events if ev.get("type") != "move"]
                fill()

        def trim_start():
            if not events or events[0]["t"] <= 0:
                return
            gap = events[0]["t"]
            for ev in events:
                ev["t"] = round(ev["t"] - gap, 4)
            fill()

        def apply():
            if not events:
                messagebox.showinfo("Macro Recorder", "That would leave the macro empty. Use Clear in "
                                    "Settings > Recording for that.", parent=win)
                return
            self.events = events
            self.unsaved = True
            self.sub_note = "Macro edited (Save… to keep the changes in the file)"
            win.destroy()
            self._refresh()

        tools = tk.Frame(win, bg=BG)
        tools.pack(fill="x", padx=14, pady=(8, 0))
        ttk.Button(tools, text="Remove selected", command=remove_selected).pack(side="left")
        ttk.Button(tools, text="Remove all mouse moves", command=remove_moves).pack(side="left", padx=6)
        ttk.Button(tools, text="Cut the wait at the start", command=trim_start).pack(side="left")
        tree.bind("<Delete>", lambda e: remove_selected())

        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=14, pady=12)
        ttk.Button(bottom, text="Apply", style="Accent.TButton", command=apply).pack(side="right")
        ttk.Button(bottom, text="Cancel", command=win.destroy).pack(side="right", padx=6)
        fill()

    # ------------------------------------------------------------ state shown on screen

    def _refresh(self):
        if not hasattr(self, "card_play") or not hasattr(self, "key_badges"):
            return  # still building the window
        if self.recording:
            state, color = ("Recording paused", AMBER) if self.paused else ("Recording", RED)
            sub = "Press Record again when you're done" if not self.paused else "Press Pause again to go on"
        elif self.playing and self.countdown_left > 0:
            state, color = f"Starting in {self.countdown_left}…", AMBER
            sub = "Switch to the game window now"
        elif self.playing and self.play_paused_at is not None:
            state, color = "Paused", AMBER
            sub = "Press " + hotkey_name(self.hotkeys["pause"]) + " or Resume to go on"
        elif self.playing:
            state, color = "Playing", ACCENT
            sub = self.play_note or "Playing the macro"
        else:
            state, color = "Ready", GREEN if self.events else MUTED
            sub = self.sub_note
        self.status_var.set(state)
        self.sub_var.set(sub)
        d = self.status_dot
        d.delete("!bdimg")
        d.create_oval(1, 1, 15, 15, outline=color, width=2)
        d.create_oval(5, 5, 11, 11, fill=color, outline="")

        k = {action: hotkey_name(self.hotkeys[action]) for action in HOTKEY_ACTIONS}
        busy = self.recording or self.playing
        self.card_record.update_card("Stop rec." if self.recording else "Record", k["record"],
                                     enabled=not self.playing, active=self.recording)
        play_paused = self.playing and self.play_paused_at is not None
        self.card_pause.update_card("Resume" if self.paused or play_paused else "Pause", k["pause"],
                                    enabled=self.recording or (self.playing and self.countdown_left == 0),
                                    active=self.paused or play_paused)
        self.card_play.update_card("Play", k["play"], enabled=not busy and bool(self.events),
                                   active=self.playing)
        self.card_stop.update_card("Stop", k["stop"], enabled=self.playing)

        length = self.events[-1]["t"] if self.events else 0.0
        parts = [f"{len(self.events)} actions", f"{length:.1f} s"]
        if self.macro_screen:
            parts.append(f"made for {core.format_resolution(self.macro_screen)}")
        if self.current_file and os.path.splitext(os.path.basename(self.current_file))[0] != self.name_var.get():
            parts.append(os.path.basename(self.current_file))
        self.info_var.set("  ·  ".join(parts))
        self._show_macro_list(busy)

        for b in (self.btn_save, self.btn_load, self.btn_edit, self.btn_clear):
            b.config(state="disabled" if busy else "normal")
        self.speed_box.config(state="disabled" if busy else "normal")
        # opening the video takes the keyboard for a moment, so not while a macro runs (closing is fine)
        self.btn_video.config(state="disabled" if busy and not self.video.is_open() else "normal")
        self.repeat_box.config(state="disabled" if busy else "normal")
        self.loop_switch.set_enabled(not busy)
        self.name_entry.config(state="disabled" if busy else "normal", disabledbackground=self.name_entry.cget("bg"),
                               disabledforeground=MUTED)
        for b in (self.made_for_box, self.play_on_box):
            b.config(state="disabled" if busy else "normal")
        for b in self.watch_widgets + self.watch_remove_buttons:
            b.config(state="disabled" if busy or image_watch is None else "normal")

        for action, badge in self.key_badges.items():
            if self.capture_callback is None or badge.cget("text") != "Press a key…":
                badge.config(text=k[action], fg=TEXT)

        if self.statusbar_var.get():
            bits = [f"{k['record']} record", f"{k['play']} play", f"{k['stop']} stop",
                    f"speed {self.speed_var.get()}"]
            if image_watch is not None and self.watch_var.get():
                n = len(self.watch_pictures)
                bits.append(f"watching {n} picture{'s' if n != 1 else ''}")
            self.statusbar_label.config(text="   ·   ".join(bits))
        else:
            self.statusbar_label.config(text="")
        if hasattr(self, "bg_animate_var"):
            self._apply_animation()
        self._video_mode()
        for b in (getattr(self, "backdrop", None), getattr(self, "settings_backdrop", None)):
            if b is not None:
                b.refresh()

    # ------------------------------------------------------------ settings

    def _save_settings(self):
        if hasattr(self, "sounds_var"):
            s = self.settings
            s["sounds"] = bool(self.sounds_var.get())
            s["sound_volume"] = int(self.volume_var.get())
            s["status_bar"] = bool(self.statusbar_var.get())
            s["always_on_top"] = bool(self.ontop_var.get())
            s["record_mouse_moves"] = bool(self.rec_moves_var.get())
            s["mouse_detail"] = self.detail_var.get()
            s["play_overlay"] = bool(self.overlay_var.get())
            if hasattr(self, "video_entry"):
                s["video_link"] = self.video_link_text()
                s["video_click_through"] = self.video_through_var.get()
                s["video_opacity"] = int(self.video_opacity_var.get())
                if self.video.rect:
                    s["video_rect"] = [int(v) for v in self.video.rect]
            if hasattr(self, "bg_settings"):
                for c in [self.bg_main, self.bg_settings] + list(self.bg_pages.values()):
                    c.save(s)
                s["settings_background_per_page"] = bool(self.bg_per_page_var.get())
                s["background_animate"] = bool(self.bg_animate_var.get())
            try:
                s["repeat_count"] = max(1, min(9999, int(self.repeat_var.get())))
            except (tk.TclError, ValueError):
                pass
        super()._save_settings()

    # ------------------------------------------------------------ actions with sounds and notes

    def toggle_record(self):
        was = self.recording
        super().toggle_record()
        if self.recording and not was:
            self.name_var.set("Recording " + datetime.datetime.now().strftime("%Y-%m-%d %H.%M"))
            self._sound("record_start")
        elif was and not self.recording:
            self.sub_note = f"Recorded {len(self.events)} actions"
            self._sound("record_stop")
            self._refresh()

    def _on_move(self, x, y):
        if not self._capturing() or not self.settings.get("record_mouse_moves", True):
            return
        now = time.perf_counter()
        if now - self.last_move < MOUSE_DETAIL.get(self.settings.get("mouse_detail"), 0.01):
            return
        self.last_move = now
        self._add({"type": "move", "x": x, "y": y})

    def play(self):
        super().play()
        if self.playing:
            if self.settings_win is not None:
                self.close_settings()  # its picture list must not be seen as the picture on screen
            if self.edit_win is not None and self.edit_win.winfo_exists():
                self.edit_win.destroy()
            self.stopped_by_user = False
            self.play_began = None
            self.play_paused_at = None
            self.play_pause_total = 0.0
            self.held_now = None
            self._tick_overlay()
            self._sound("play_start")

    def stop_playback(self):
        if self.playing:
            self.stopped_by_user = True
        super().stop_playback()

    def _play_clock(self):
        """Playback's clock: it stands still while playback is paused."""
        now = self.play_paused_at if self.play_paused_at is not None else time.perf_counter()
        return now - self.play_pause_total

    def _replay_event(self, ev, held_keys, held_buttons):
        self.held_now = (held_keys, held_buttons)
        super()._replay_event(ev, held_keys, held_buttons)

    def toggle_pause(self):
        """While recording: pause the recording. While playing: pause playback, or go on."""
        if not self.playing:
            was = self.paused
            super().toggle_pause()
            if self.recording and self.paused != was:
                self._sound("pause" if self.paused else "resume")
            return
        if self.countdown_left > 0:
            return
        if self.play_paused_at is None:
            self.play_paused_at = time.perf_counter()
            if self.held_now is not None:
                # let go of everything, so the character doesn't keep walking while paused
                self._release_held(None, *self.held_now)
            self._sound("pause")
        else:
            self.play_pause_total += time.perf_counter() - self.play_paused_at
            self.play_paused_at = None
            self._sound("resume")
        self._refresh()

    def _set_countdown(self, seconds):
        def tick():  # (not for the first second: "Playing starts" is sounding then)
            if 0 < seconds != self.countdown_left:
                self._sound("countdown")
        self._call_ui(tick)
        super()._set_countdown(seconds)

    def _picture_seen(self):
        self._sound("picture_seen")

    def _tick_overlay(self):
        """Keep the top-of-screen timer up to date while playing (every quarter second)."""
        self.overlay_job = None
        if not self.playing:
            return
        if not self.overlay_var.get():
            if self.overlay is not None:
                self.overlay.hide()
        else:
            if self.overlay is None:
                self.overlay = PlayOverlay(self.root, self.screen_w)
            name = self.name_var.get()
            keys = {a: hotkey_name(self.hotkeys[a]) for a in ("pause", "stop")}
            if self.countdown_left > 0:
                self.overlay.show("Starting in", str(self.countdown_left), name, AMBER, keys)
            else:
                if self.play_began is None:
                    self.play_began = self._play_clock()
                note = self.play_note.rstrip(".").replace("…", "").replace("Playing run", "Run") or name
                clock = format_clock(self._play_clock() - self.play_began)
                if self.play_paused_at is not None:
                    self.overlay.show("Paused", clock, note, AMBER, keys)
                else:
                    self.overlay.show("Playing", clock, note, ACCENT, keys)
        self.overlay_job = self.root.after(250, self._tick_overlay)

    def _finish_overlay(self):
        if self.overlay is None or not self.overlay_var.get() or self.play_began is None:
            if self.overlay is not None:
                self.overlay.hide()
            return
        took = format_clock(self._play_clock() - self.play_began)
        word = "Stopped" if getattr(self, "stopped_by_user", False) else "Finished"
        self.overlay.show(word, took, self.name_var.get(), MUTED if word == "Stopped" else GREEN)
        self.root.after(4000, lambda: None if self.playing else self.overlay.hide())

    def _playback_done(self):
        if self.play_paused_at is not None:  # stopped while paused
            self.play_pause_total += time.perf_counter() - self.play_paused_at
            self.play_paused_at = None
        super()._playback_done()
        if self.overlay_job is not None:
            self.root.after_cancel(self.overlay_job)
            self.overlay_job = None
        self._finish_overlay()
        self.sub_note = "Stopped" if getattr(self, "stopped_by_user", False) else "Finished playing"
        self._sound("play_end")
        self._refresh()

    def load(self, path=None, quiet=False):
        ok = super().load(path, quiet=quiet)
        if ok:
            self.name_var.set(os.path.splitext(os.path.basename(self.current_file))[0])
            self.sub_note = "Macro opened"
            self.unsaved = False
            self._remember_macro(self.current_file)
            self._refresh()
        return ok

    # ------------------------------------------------------------ the video window

    def _video_hint(self):
        """Grey "Paste a YouTube…" text in the empty link box (gone as soon as you click into it)."""
        e = self.video_entry
        self.video_hint_on = False

        def show(_e=None):
            if not self.video_var.get().strip() and self.root.focus_get() is not e:
                self.video_hint_on = True
                self.video_var.set(VIDEO_HINT)
                e.config(fg=DIM)

        def hide(_e=None):
            if self.video_hint_on:
                self.video_hint_on = False
                self.video_var.set("")
                e.config(fg=TEXT)
        e.bind("<FocusIn>", hide, add="+")
        e.bind("<FocusOut>", show, add="+")
        show()

    def video_link_text(self):
        return "" if getattr(self, "video_hint_on", False) else self.video_var.get().strip()

    def toggle_video(self):
        if self.video.is_open():
            self.close_video()
        else:
            self.show_video()

    def show_video(self):
        text = self.video_link_text()
        link = video_overlay.parse_link(text)
        if link is None:
            messagebox.showinfo("Video", "Paste a YouTube link first, like\n"
                                "https://www.youtube.com/watch?v=…  or  https://www.youtube.com/playlist?list=…",
                                parent=self.root)
            return
        self.settings["video_link"] = text
        self.video.opacity = self.video_opacity_var.get()
        self.video.click_through = self._video_should_click_through()
        if not self.video.open(link):
            messagebox.showwarning("Video", self.video.error, parent=self.root)
            return
        self.btn_video.config(text="Close")
        self._save_settings()
        if self.video_job is None:
            self.video_job = self.root.after(300, self._tick_video)

    def close_video(self):
        self.video.close()
        self._video_closed()

    def _video_closed(self):
        if self.video_job is not None:
            self.root.after_cancel(self.video_job)
            self.video_job = None
        self.btn_video.config(text="Show")
        self._save_video_rect()

    def _save_video_rect(self):
        if self.video.rect and list(self.video.rect) != self.settings.get("video_rect"):
            self.settings["video_rect"] = [int(v) for v in self.video.rect]
            self._save_settings()

    def _tick_video(self):
        """About twice a second while the video window is open: keep it on top, switch clicking
        through it on or off, and notice when it gets closed with its X."""
        self.video_job = None
        if not self.video.poll():
            self._video_closed()
            return
        self._video_mode()
        n = getattr(self, "video_ticks", 0) + 1
        self.video_ticks = n
        if n % 20 == 0:  # remember where it is and how big, every 10 seconds
            self._save_video_rect()
        self.video_job = self.root.after(500, self._tick_video)

    def _video_should_click_through(self):
        if self.video_through_var.get() == "Always":
            return True
        if self.recording:
            return not self.paused
        if self.playing:
            return self.play_paused_at is None  # paused: you can use the video's buttons again
        return False

    def _video_mode(self):
        if hasattr(self, "video") and self.video.is_open():
            want = self._video_should_click_through()
            if want != self.video.click_through:
                self.video.set_click_through(want)

    def _video_opacity(self):
        self.video.set_opacity(self.video_opacity_var.get())

    def _on_close(self):
        try:
            self.video.close(wait=True)
        except Exception:
            pass
        super()._on_close()

    # ------------------------------------------------------------ saved macros (◀ ▶ quick switch)

    def macro_list(self):
        """The saved macros: file paths, in the order they were added (up to MAX_MACROS)."""
        lib = self.settings.get("macro_library")
        if not isinstance(lib, list):
            lib = self.settings["macro_library"] = []
        lib[:] = [p for p in lib if isinstance(p, str) and p]
        return lib

    def _list_index(self, path):
        key = os.path.normcase(os.path.abspath(path)) if path else None
        for i, p in enumerate(self.macro_list()):
            if os.path.normcase(os.path.abspath(p)) == key:
                return i
        return None

    def _remember_macro(self, path):
        """Put an opened or saved macro in the list (the oldest one goes when it's full)."""
        if not path or self._list_index(path) is not None:
            return
        lib = self.macro_list()
        lib.append(os.path.abspath(path))
        del lib[:-MAX_MACROS]
        self._save_settings()

    def _show_macro_list(self, busy=False):
        lib = self.macro_list()
        i = self._list_index(self.current_file)
        if i is not None:
            name = os.path.splitext(os.path.basename(lib[i]))[0]
            text = f"{i + 1} of {len(lib)}:  {short(name, 28)}"
        elif lib:
            text = f"{len(lib)} saved  ·  this one isn't in the list"
        else:
            text = "macros you open or save show up here"
        self.mac_label.config(text=text)
        arrows = len(lib) > (0 if i is None else 1) and not busy
        for a, sym in ((self.mac_prev, "◀"), (self.mac_next, "▶")):
            a.config(text=sym if arrows else "", cursor="hand2" if arrows else "arrow")
        rem = i is not None and not busy
        self.mac_remove.config(text="Remove" if rem else "", cursor="hand2" if rem else "arrow")

    def _has_unsaved_macro(self):
        return bool(self.events) and (self.current_file is None or getattr(self, "unsaved", False))

    def step_macro(self, d):
        """◀ / ▶: open the previous or next saved macro."""
        lib = self.macro_list()
        if self.recording or self.playing or not lib:
            return
        i = self._list_index(self.current_file)
        if i is not None and len(lib) < 2:
            return
        if self._has_unsaved_macro() and not messagebox.askyesno(
                "Macro Recorder", "This macro isn't saved. Switch to another one anyway?\n\n"
                "(Click No, then Save…, to keep it.)", parent=self.root):
            return
        if i is None:  # not in the list: ▶ starts at the first one, ◀ at the last
            order = lib[:] if d > 0 else lib[::-1]
        else:
            order = [lib[(i + d * n) % len(lib)] for n in range(1, len(lib))]
        missing = []
        for path in order:  # skip files that were moved or deleted
            if not os.path.isfile(path):
                missing.append(path)
                continue
            if self.load(path, quiet=True):
                self.sub_note = "Switched macro" + (f" (skipped {len(missing)} missing file"
                                                    f"{'s' if len(missing) != 1 else ''})" if missing else "")
            else:
                self.sub_note = "Couldn't open " + os.path.basename(path)
            self._refresh()
            return
        self.sub_note = "None of the other saved macros could be found"
        self._refresh()

    def remove_macro_from_list(self):
        """Take the open macro out of the list (the file itself stays where it is)."""
        i = self._list_index(self.current_file)
        if i is None or self.recording or self.playing:
            return
        del self.macro_list()[i]
        self._save_settings()
        self.sub_note = "Taken out of the list (the file wasn't deleted)"
        self._refresh()

    def clear(self):
        had = bool(self.events)
        super().clear()
        if had and not self.events:
            self.unsaved = False
            self.name_var.set("Untitled macro")
            self.sub_note = "Record something, or open a macro"
            self._refresh()

    def save(self):
        if not self.events:
            messagebox.showinfo("Macro Recorder", "Nothing to save yet. Record something first.")
            return
        name = "".join(c for c in self.name_var.get().strip() if c not in '\\/:*?"<>|') or "my_macro"
        path = filedialog.asksaveasfilename(defaultextension=core.FILE_EXT, filetypes=core.FILE_TYPES,
                                            initialfile=name + core.FILE_EXT)
        if not path:
            return
        self._read_made_for(quiet=True)
        data = {"app": "macro_recorder", "version": core.FILE_VERSION, "name": self.name_var.get().strip(),
                "events": self.events}
        if self.macro_screen:
            data["screen"] = {"width": self.macro_screen[0], "height": self.macro_screen[1]}
        import json

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        self.current_file = path
        self.unsaved = False
        self.name_var.set(os.path.splitext(os.path.basename(path))[0])
        self.sub_note = "Saved"
        self._remember_macro(path)
        self._refresh()


# ---------------------------------------------------------------- start

def use_preview_settings():
    """The preview keeps its own settings folder (a copy of the real one on first start), so trying
    it never changes the real app's hotkeys or pictures."""
    real_dir = os.path.dirname(core.settings_path())
    preview_dir = real_dir + " Preview"
    if not os.path.exists(os.path.join(preview_dir, "settings.json")) and os.path.isdir(real_dir):
        try:
            shutil.copytree(real_dir, preview_dir, dirs_exist_ok=True)
        except Exception:
            pass
    core.settings_path = lambda: os.path.join(preview_dir, "settings.json")


def main(preview=False):
    if preview:
        use_preview_settings()
    core.make_dpi_aware()
    if IS_MAC:
        try:
            core.mac_prepare_pynput()
        except Exception:
            pass
    root = tk.Tk()
    app = ModernMacroRecorder(root, preview=preview)
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        root.after(100, lambda: app.load(sys.argv[1]))
    if IS_MAC:
        def open_documents(*paths):
            if paths:
                app.load(paths[0])
        root.createcommand("::tk::mac::OpenDocument", open_documents)
        missing = core.mac_missing_permissions()
        if missing:
            root.after(300, lambda: messagebox.showwarning(
                "Macro Recorder", core.MAC_PERMISSION_HELP.format(missing=", ".join(missing))))
    root.mainloop()


if __name__ == "__main__":
    main()
