"""The look of the dark Macro Recorder window: colours, fonts, the dark theme for Tk and its
small widgets (switch, cards, timer at the top, dark message boxes), shared by modern_ui.py and
its parts (settings_pages, discord_ui, results_ui, settings_window, edit_window, video_ui).

Originally: the dark Macro Recorder window (started from macro_recorder.py).

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

# (some imports here aren't used in this file: the window's parts get them from here)
import datetime
import os
import shutil
import sys
import time
import tkinter as tk
from tkinter import filedialog, ttk
from tkinter import messagebox as _tk_messagebox

import backdrop
import diag
import icon_picture
import importers
import macro_recorder as core
import own_windows
import platform_keys
import stats
import window_tools
import macro_steps as workflow
from macro_recorder import (HOTKEY_ACTIONS, IS_MAC, IS_WIN, SCREEN_TARGET, SPEED_PRESETS, background,
                            format_speed, hotkey_name, image_watch, parse_speed)

import lazy
# loaded the first time they're used, so the window shows sooner (they bring the network and
# web server parts along; most of them aren't needed in the first seconds or at all)
discord_notify = lazy.module("discord_notify")
sounds = lazy.module("sounds")
text_styles = lazy.module("text_styles")
video_overlay = lazy.module("video_overlay")
updater = lazy.module("updater")
from version import APP_VERSION, HISTORY, WHATS_NEW

if IS_MAC:
    # Mac (2.9.2): "transient" glues a window to the one it was opened from (it moves along with it
    # and can't be put on its own). Windows still use it; on a Mac every window stays free, and the
    # window you click comes in front (the app's windows are all "on top" already).
    def _mac_transient(self, master=None):
        if master is None:
            return ""  # (asking which window it's glued to: none)
        return None
    tk.Wm.wm_transient = tk.Wm.transient = _mac_transient

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
ACCENT_HOVER = "#6a90ff"
# (Preview 4) accent colours to pick in Settings > Background > LOOK: (accent, dark, hover). White text on
# the accent has at least 3:1 contrast, and the accent as text on the dark window at least 4.5:1.
THEMES = {"Blue": ("#4f7cff", "#1c2648", "#6a90ff"), "Purple": ("#8f62f7", "#2a1f48", "#a07cf8"),
          "Green": ("#1f9d58", "#14331f", "#2bb56a"), "Orange": ("#d9661f", "#3a2312", "#e87d3a"),
          "Pink": ("#e0457f", "#401a2c", "#ea6a99"), "Red": ("#e2434f", "#3e1a1f", "#ea6370")}
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
    # boxes with a title show just the title, like the other sections (no frame line around them)
    style.configure("TLabelframe", background=BG, bordercolor=BG, lightcolor=BG, darkcolor=BG, relief="flat",
                    borderwidth=0)
    style.layout("TLabelframe", [])  # nothing drawn: no frame line
    style.configure("TLabelframe.Label", background=BG, foreground=MUTED, font=F_SECTION)
    style.configure("TButton", background=CARD, foreground=TEXT, padding=(12, 5), relief="flat",
                    bordercolor=BORDER)
    style.map("TButton", background=[("disabled", BG), ("active", CARD_HOVER)],
              bordercolor=[("active", "#4a4a56")])
    style.configure("Accent.TButton", background=ACCENT, foreground="white", bordercolor=ACCENT)
    style.map("Accent.TButton", background=[("active", ACCENT_HOVER)])
    style.configure("Danger.TButton", background=RED_DARK, foreground=RED, bordercolor="#5a2630")
    style.map("Danger.TButton", background=[("active", "#4a2028")])
    style.configure("TCheckbutton", background=BG, foreground=TEXT, indicatorbackground=FIELD,
                    indicatorforeground="white", indicatorcolor=FIELD)
    style.map("TCheckbutton", background=[("active", BG)],
              indicatorcolor=[("selected", ACCENT), ("disabled", BG)])
    # (2.12) round option buttons like the checkboxes: dark, also under the mouse (they turned white)
    style.configure("TRadiobutton", background=BG, foreground=TEXT, indicatorbackground=FIELD,
                    indicatorforeground="white", indicatorcolor=FIELD)
    style.map("TRadiobutton", background=[("active", BG)], foreground=[("active", TEXT)],
              indicatorcolor=[("selected", ACCENT), ("disabled", BG)])
    for name in ("TSpinbox", "TCombobox", "TEntry"):
        style.configure(name, fieldbackground=FIELD, background=CARD, foreground=TEXT, padding=3,
                        arrowsize=12)
        style.map(name, fieldbackground=[("readonly", FIELD), ("disabled", BG)],
                  foreground=[("disabled", DIM)], bordercolor=[("focus", ACCENT)])
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(12, 6, 12, 0))
    # the Settings window draws its own page names, so this notebook has no tabs and no frame line
    style.layout("Flat.TNotebook.Tab", [])
    style.layout("Flat.TNotebook", [("Notebook.client", {"sticky": "nswe"})])
    style.configure("Flat.TNotebook", background=BG, borderwidth=0, bordercolor=BG, lightcolor=BG,
                    darkcolor=BG, tabmargins=0, padding=0)
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


TITLE_BG = "#1d2125"  # Windows 11's dark title bar
CLOSE_HOVER = "#c42b1c"  # Windows 11's red behind the Close X


def only_close_button(win):
    """Windows: no Minimize or Maximize button, just Close (Windows' own title bar)."""
    if not IS_WIN:
        return
    try:
        import ctypes

        win.update_idletasks()
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(win.winfo_id())
        style = user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE
        new = style & ~0x00020000 & ~0x00010000  # WS_MINIMIZEBOX, WS_MAXIMIZEBOX
        if new != style:
            user32.SetWindowLongW(hwnd, -16, new)
            # SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x20 | 0x2 | 0x1 | 0x4 | 0x10)
    except Exception:
        pass


def build_title_bar(win, title, icon, on_close):
    """A title bar that looks like Windows 11's dark one, with only the Close button."""
    import tkinter.font as tkfont
    bar = tk.Frame(win, bg=TITLE_BG, height=30)
    bar.pack(fill="x", side="top")
    bar.pack_propagate(False)
    glyph_font = next(((f, 8) for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in tkfont.families()),
                      None)
    close = tk.Label(bar, text="" if glyph_font else "✕", font=glyph_font or (FAMILY, 10),
                     bg=TITLE_BG, fg="white", width=0)
    close.place(relx=1, x=0, y=0, anchor="ne", width=46, relheight=1)
    close.bind("<Enter>", lambda e: close.config(bg=CLOSE_HOVER))
    close.bind("<Leave>", lambda e: close.config(bg=TITLE_BG))
    close.bind("<ButtonRelease-1>", lambda e: on_close() if close.winfo_containing(e.x_root, e.y_root) is close
               else None)
    if icon is not None:
        small = icon.subsample(2) if icon.width() >= 32 else icon
        bar.icon_small = small
        tk.Label(bar, image=small, bg=TITLE_BG).pack(side="left", padx=(8, 6))
    text = tk.Label(bar, text=title, bg=TITLE_BG, fg="#ffffff", font=(FAMILY, 9))
    text.pack(side="left")

    def drag(event):  # move the window the Windows way (snapping works too)
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            ctypes.windll.user32.ReleaseCapture()
            ctypes.windll.user32.SendMessageW(hwnd, 0xA1, 2, 0)  # WM_NCLBUTTONDOWN, HTCAPTION
        except Exception:
            pass
    for w in bar.winfo_children() + [bar]:
        if w is not close:
            w.bind("<ButtonPress-1>", drag)
    return bar


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
    if IS_MAC:
        # Mac (2.9.2): runs when the mouse button is let go over it, like a real button. A box opened
        # while the button is still down froze the whole app on a Mac (the ⓘ icons).
        lab.bind("<ButtonRelease-1>", lambda e: command()
                 if 0 <= e.x < lab.winfo_width() and 0 <= e.y < lab.winfo_height() else None)
    else:
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


class ScrollArea(tk.Frame):
    """(Preview 4) A part of a window that gets scroll bars when the window is made smaller than what's
    inside it. Put things into .inner. natural=True: it asks for the size of what's inside (the window
    keeps its usual size until you drag its corner); False: it asks for almost nothing (the window's
    size is set by its owner). on_scroll: called (once things stand still) after scrolling or resizing."""

    SKIP_WHEEL = ("Scale", "TScale", "TCombobox", "TSpinbox", "Spinbox", "Listbox", "Treeview", "Text")

    def __init__(self, parent, bg, natural=True, on_scroll=None):
        super().__init__(parent, bg=bg)
        self.natural, self.on_scroll, self.job = natural, on_scroll, None
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, width=1, height=1)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self._yview)
        self.hbar = ttk.Scrollbar(self, orient="horizontal", command=self._xview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.item = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.inner.bind("<Configure>", lambda e: self._fit(), add="+")
        self.canvas.bind("<Configure>", lambda e: self._fit(), add="+")
        self.bind("<Configure>", lambda e: self._fit() if e.widget is self else None, add="+")

    def _fit(self):
        # (2.13 Mac fix) Which bars are needed is worked out from this area's own size (set by its window,
        # not by the bars), and a bar is only placed or taken away when that changes. Before, a hidden window
        # on a Mac kept placing its bars again, each time making a new layout: an endless loop.
        if getattr(self, "fitting", False):
            return
        self.fitting = True
        try:
            c, i = self.canvas, self.inner
            rw, rh = i.winfo_reqwidth(), i.winfo_reqheight()
            if self.natural and (int(c.cget("width")), int(c.cget("height"))) != (rw, rh):
                c.configure(width=rw, height=rh)
            if not self.winfo_ismapped():
                return  # (hidden: laid out once it shows)
            aw, ah = max(1, self.winfo_width()), max(1, self.winfo_height())
            bw = max(1, self.vbar.winfo_reqwidth())
            bh = max(1, self.hbar.winfo_reqheight())
            need_v = rh > ah + 1
            need_h = rw > aw - (bw if need_v else 0) + 1
            need_v = need_v or (need_h and rh > ah - bh + 1)
            cw, ch = aw - (bw if need_v else 0), ah - (bh if need_h else 0)
            w, h = max(cw, rw), max(ch, rh)
            c.itemconfigure(self.item, width=w, height=h)
            c.configure(scrollregion=(0, 0, w, h))
            for bar, need, where in ((self.vbar, need_v, dict(row=0, column=1, sticky="ns")),
                                     (self.hbar, need_h, dict(row=1, column=0, sticky="ew"))):
                shown = bool(bar.winfo_manager())
                if need and not shown:
                    bar.grid(**where)
                elif not need and shown:
                    bar.grid_remove()
            if not need_v:
                c.yview_moveto(0)
            if not need_h:
                c.xview_moveto(0)
        finally:
            self.fitting = False
        self._moved()

    def _yview(self, *args):
        self.canvas.yview(*args)
        self._moved()

    def _xview(self, *args):
        self.canvas.xview(*args)
        self._moved()

    def _moved(self):
        if self.on_scroll is None:
            return
        if self.job is not None:
            self.after_cancel(self.job)
        self.job = self.after(60, self._tell)

    def _tell(self):
        self.job = None
        try:
            self.on_scroll()
        except tk.TclError:
            pass

    def wheel(self, event):
        """Mouse wheel over this area (the window calls it): scrolls when there's more to see."""
        if event.widget.winfo_class() in self.SKIP_WHEEL or not self.vbar.winfo_ismapped():
            return
        steps = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(steps * 3, "units")
        self._moved()
        return "break"

    def see(self, widget):
        """Scroll so widget (somewhere inside) shows."""
        try:
            self.update_idletasks()
            self._fit()  # (a part that was just opened: its size counts now)
            self.update_idletasks()
            y = widget.winfo_rooty() - self.inner.winfo_rooty()
            total = max(1, self.inner.winfo_height())
            view = self.canvas.winfo_height()
            top = self.canvas.canvasy(0)
            if y < top or y + widget.winfo_height() > top + view:
                self.canvas.yview_moveto(max(0.0, (y - 20) / total))
                self._moved()
        except tk.TclError:
            pass


class PlainArea(tk.Frame):
    """(2.13 Mac fix) Stands in for ScrollArea where scrolling can't be used: just a frame (inner = itself).
    On a Mac, the Settings pages' scroll areas froze the app while a macro played (Tk's canvas with a page
    inside it, in a window that isn't on screen, kept the window busy forever; found with tests/mac_probe.py)."""

    def __init__(self, parent, bg, natural=True, on_scroll=None):
        super().__init__(parent, bg=bg)
        self.inner = self
        self.vbar = self.hbar = None

    def wheel(self, event):
        return None

    def see(self, widget):
        pass


def wheel_scrolls(window, area_of):
    """(Preview 4) The mouse wheel scrolls the scroll area under the pointer. area_of(): the area."""
    def on_wheel(event):
        area = area_of()
        if area is None or not hasattr(area, "wheel"):
            return None
        try:
            if not (str(event.widget) + ".").startswith(str(area) + "."):  # (".!scrollarea" is not ".!scrollarea2")
                return None
        except tk.TclError:
            return None
        return area.wheel(event)
    window.bind("<MouseWheel>", on_wheel, add="+")


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
        shown = (title, key, enabled, active)
        if shown == getattr(self, "shown", None):
            return  # nothing changed (hover redraws on its own)
        self.shown = shown
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
    if kind == "wait_picture":
        limit = ev.get("timeout", 30)
        bits = [f"up to {limit:g} s" if limit else "no time limit"]
        if ev.get("click"):
            bits.append("click it")
        if ev.get("otherwise") == "stop":
            bits.append("else stop")
        return "Wait for a picture", (ev.get("name") or "picture") + ": " + ", ".join(bits)
    return kind or "?", ""


MOUSE_DETAIL = {"Smooth": 0.01, "Normal": 0.025, "Light": 0.05}  # seconds between recorded moves


# ---------------------------------------------------------------- the app

class PlayOverlay:
    """A small always-on-top box at the top middle of the main screen: the countdown before playing,
    then how long it has been playing. It stays there the whole time the macro runs, so you can
    see it's still going while the app is minimized. Mouse clicks go straight through it."""

    def __init__(self, root, screen_w):
        # one dark colour all over (no grey frame, and no grey sides when the box is wider than its text)
        self.win = win = tk.Toplevel(root, bg=PANEL)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.93)
        except tk.TclError:
            pass
        inner = tk.Frame(win, bg=PANEL)
        inner.pack(fill="both", expand=True)
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

    def show(self, state, clock, note, color, keys=None, stop_word="Stop"):
        """keys: {"pause": "F10", "stop": "F12"} shows which keys pause and stop; None hides them.
        Called 4 times a second: it only redraws when something shown changed, and puts itself back
        on top every 2 seconds (in case the game covered it)."""
        now = time.monotonic()
        shown = (state, clock, note, color, tuple(sorted(keys.items())) if keys else None, stop_word)
        if shown == getattr(self, "last_shown", None) and self.win.state() != "withdrawn":
            if now - getattr(self, "last_raised", 0.0) >= 2.0:
                self.last_raised = now
                self.win.lift()
                self.win.attributes("-topmost", True)
            return
        self.last_shown = shown
        self.last_raised = now
        self.state.config(text=state)
        self.clock.config(text=clock)
        self.note.config(text=note)
        if keys:
            for action, (badge, text) in self.key_labels.items():
                badge.config(text=keys[action])
                if action == "pause":
                    text.config(text="Resume" if state.endswith("aused") else "Pause")
                else:
                    text.config(text=stop_word)
            self.keys_row.pack(padx=14, pady=(2, 8))
        else:
            self.keys_row.pack_forget()
        self.dot.delete("all")
        self.dot.create_oval(1, 1, 11, 11, fill=color, outline="")
        w = self.win
        w.update_idletasks()
        width, height = max(w.winfo_reqwidth(), 210), w.winfo_reqheight()  # same size, so it doesn't jump
        x = max(0, (self.screen_w - width) // 2)
        w.geometry(f"{width}x{height}+{x}+12")
        own_windows.set_rect("timer", (x, 12, x + width, 12 + height))  # (Picture watch doesn't look at it)
        if w.state() == "withdrawn":
            w.deiconify()
            self._click_through()
        w.lift()
        w.attributes("-topmost", True)

    def hide(self):
        self.last_shown = None
        self.win.withdraw()
        own_windows.set_rect("timer", None)
        self.front_button(None)

    def front_button(self, command, text="Bring it to front"):
        """(Preview 4) A small button just under the timer (the timer itself lets clicks through):
        command None hides it. It never takes the keyboard from the window you're in."""
        btn = getattr(self, "front_win", None)
        if command is None:
            own_windows.set_rect("front", None)
            if btn is not None:
                btn.withdraw()
            return
        if btn is None:
            btn = self.front_win = tk.Toplevel(self.win, bg=ACCENT)
            btn.withdraw()
            btn.overrideredirect(True)
            btn.attributes("-topmost", True)
            self.front_label = tk.Label(btn, bg=ACCENT, fg="white", font=(FAMILY, 9, "bold"), padx=12, pady=4,
                                        cursor="hand2")
            self.front_label.pack()
            self.front_label.bind("<ButtonRelease-1>", lambda e: self.front_command and self.front_command())
        self.front_command = command
        self.front_label.config(text=text)
        btn.update_idletasks()
        w = self.win
        x = w.winfo_rootx() + (w.winfo_width() - btn.winfo_reqwidth()) // 2
        y = w.winfo_rooty() + w.winfo_height() + 4
        btn.geometry(f"+{max(0, x)}+{y}")
        own_windows.set_rect("front", (max(0, x), y, max(0, x) + btn.winfo_reqwidth(), y + btn.winfo_reqheight()))
        if btn.state() == "withdrawn":
            btn.deiconify()
            if IS_WIN:
                try:
                    import ctypes

                    u = ctypes.windll.user32
                    hwnd = u.GetParent(btn.winfo_id()) or btn.winfo_id()
                    # TOOLWINDOW | NOACTIVATE: off the taskbar, and clicking it doesn't make this app the
                    # window in front (so the game can be put there)
                    u.SetWindowLongW(hwnd, -20, u.GetWindowLongW(hwnd, -20) | 0x80 | 0x8000000)
                except Exception:
                    pass
        btn.lift()
        btn.attributes("-topmost", True)


def format_clock(seconds):
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"


MAX_BACKGROUNDS = 5  # saved background pictures
MAX_MACROS = 20  # saved macros for the ◀ ▶ quick switch
VIDEO_THROUGH = ("While recording or playing", "Always")  # when clicks go through the video window
VIDEO_HINT = "Paste a YouTube video or playlist link"
SETTINGS_PAGES = ("General", "Recording", "Playback", "Picture watch", "Results", "Background", "Sounds",
                  "Discord", "About")
SHOT_SIZE = {"sharp": "Sharp", "smaller": "Smaller (about half the upload)"}
PING_WHEN = {"always": "Every message", "problems": "Only failed runs and stops", "never": "Never"}
CAPTURE_CHOICES = {"screen": "Main screen", "all": "All screens", "game": "The game's window",
                   "program": "A program's window:"}
RESULT_COLORS = {stats.WIN: 0x2ECC71, stats.LOSS: 0xFF4757, stats.UNKNOWN: 0x9B9BA6}
FIT_TO = {"screen": "The whole screen", "window": "The game window"}


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

    def load(self):
        """Show the saved options again (after Undo or Reset in the Settings window)."""
        s = self.app.settings
        self.dark_var.set(core.int_setting(s, self.prefix + "_darkness", 40, 0, 90))
        fit = s.get(self.prefix + "_fit")
        self.fit_var.set(fit if fit in backdrop.FITS else "Fill the window")
        pos = s.get(self.prefix + "_position", 0)
        pos = backdrop.POSITIONS.get(pos, 0) if isinstance(pos, str) else pos
        self.pos_var.set(max(0, min(100, pos if isinstance(pos, (int, float)) else 0)))
        if self.same_var is not None:
            self.same_var.set(bool(s.get(self.prefix + "_same", True)))

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
            self.changed()
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

    def changed(self, now=False, delay=50):
        """An option moved. While a slider is dragged the picture follows about 20 times a second
        (each change doesn't wait for the slider to stop moving any more)."""
        if self.built:
            self.dark_label.config(text=f"{int(float(self.dark_var.get()))}%")
        self.app._save_settings()
        if now and self.job is not None:
            self.app.root.after_cancel(self.job)
            self.job = None
        if self.job is None:
            # both windows, as the settings window may follow the main window's options
            self.job = self.app.root.after(0 if now else delay, self.apply_all)

    def apply_all(self):
        self.job = None
        self.app._apply_background()

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
        others = app.profiles_using_background(name) if hasattr(app, "profiles_using_background") else []
        also = ""
        if others:
            names = ", ".join(f"\"{p}\"" for p in others[:3]) + (" and more" if len(others) > 3 else "")
            also = (f"\n\nThe profile{'s' if len(others) > 1 else ''} {names} "
                    f"show{'' if len(others) > 1 else 's'} it too, and would have no picture.")
        if not messagebox.askyesno("Macro Recorder", f"Remove \"{self.picture_name()}\" from your saved "
                                   "pictures?" + also, parent=app.settings_win):
            return
        if hasattr(app, "forget_background_everywhere"):
            app.forget_background_everywhere(name)
        app.settings["background_library"] = [e for e in app.bg_library() if e["file"] != name]
        for key in list(app.settings):
            if key.endswith("_picture") and key.startswith(("background", "settings_background")) \
                    and app.settings[key] == name:
                app.settings[key] = ""
        # the file stays until the change is applied, so Undo in the Settings window can bring it back
        app._save_settings()
        app._apply_background()


class ThemedBoxes:
    """Message boxes in the app's own dark look (same colours and font), used instead of Windows'
    white ones: showinfo / showwarning / showerror / askyesno / askyesnocancel / askokcancel, plus
    asknumber. They take the same arguments as tkinter.messagebox."""

    ICONS = {"info": ("ⓘ", ACCENT), "warning": ("⚠", AMBER), "error": ("✕", RED), "question": ("?", ACCENT)}

    def __init__(self, app):
        self.app = app

    def _parent(self, parent):
        if parent is not None:
            try:
                if parent.winfo_exists():
                    return parent
            except tk.TclError:
                pass
        sw = getattr(self.app, "settings_win", None)
        try:
            if sw is not None and sw.winfo_viewable():
                return sw
        except tk.TclError:
            pass
        return self.app.root

    def _box(self, title, message, kind, buttons, default, cancel, parent=None, entry=None):
        """buttons: [(text, value)]. Returns the value of the button pressed (cancel's for the X / Esc)."""
        quiet = getattr(self, "quiet", None)
        if quiet is not None:  # (the phone remote is doing this: nobody is there to answer a box)
            quiet.append(str(message or ""))
            return (cancel, None) if entry is not None else cancel
        parent = self._parent(parent)
        win = tk.Toplevel(parent, bg=BG)
        win.withdraw()
        self.open_boxes = [w for w in getattr(self, "open_boxes", []) if w.winfo_exists()] + [win]
        win.title(title or "Macro Recorder")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        try:
            # (Mac: a transient box is glued to its window and could go behind it: 2.9.2)
            if parent.winfo_viewable() and not IS_MAC:
                win.transient(parent)
        except tk.TclError:
            pass
        icon_img = getattr(self.app, "icon_img", None)
        if icon_img is not None:
            try:
                win.iconphoto(False, icon_img)
            except tk.TclError:
                pass
        result = {"value": cancel}
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=(18, 10))
        glyph, color = self.ICONS.get(kind, self.ICONS["info"])
        tk.Label(body, text=glyph, bg=BG, fg=color, font=(FAMILY, 20, "bold")).pack(side="left", anchor="n",
                                                                                  padx=(0, 14))
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        heading = title if title and title != "Macro Recorder" else ""
        if heading:
            tk.Label(right, text=heading, bg=BG, fg=TEXT, font=(FAMILY, 11, "bold"), anchor="w",
                     justify="left").pack(fill="x", pady=(0, 6))
        tk.Label(right, text=str(message or ""), bg=BG, fg=MUTED if heading else TEXT, font=F_BASE, anchor="w",
                 justify="left", wraplength=460).pack(fill="x")
        tk.Frame(right, bg=BG, width=440, height=1).pack(anchor="w")  # (2.11: short boxes as wide as others)
        entry_var = None
        if entry is not None:
            entry_var = tk.StringVar(value=entry)
            e = tk.Entry(right, textvariable=entry_var, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat",
                         insertbackground=TEXT, highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT, width=14)
            e.pack(anchor="w", pady=(10, 0), ipady=3)
            e.select_range(0, "end")
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=20, pady=(6, 16))

        def done(value):
            result["value"] = value
            if entry_var is not None:
                result["text"] = entry_var.get()
            win.grab_release()
            win.destroy()
        first = None
        for text, value in reversed(buttons):
            b = ttk.Button(bottom, text=text, width=max(8, len(text) + 2), command=lambda v=value: done(v),
                           style="Accent.TButton" if value == default else "TButton")
            b.pack(side="right", padx=(8, 0))
            if value == default:
                first = b
        win.bind("<Return>", lambda e: done(default))
        win.bind("<Escape>", lambda e: done(cancel))
        win.protocol("WM_DELETE_WINDOW", lambda: done(cancel))
        win.update_idletasks()
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            if not parent.winfo_viewable() or pw < 50:
                raise tk.TclError
        except tk.TclError:
            px, py, pw, ph = 0, 0, win.winfo_screenwidth(), win.winfo_screenheight()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        win.geometry(f"+{max(0, px + (pw - w) // 2)}+{max(0, py + (ph - h) // 3)}")
        win.deiconify()
        dark_title_bar(win)
        only_close_button(win)
        win.lift()
        if IS_MAC:
            # Mac (2.9.2): no lock on the rest of the app. A locked app with the box out of sight
            # froze it for good; instead the box is kept in front of the app's other windows.
            self._mac_keep_in_front(win)
        else:
            try:
                win.grab_set()
            except tk.TclError:
                pass
        (e if entry is not None else (first or win)).focus_force()
        win.wait_window()
        if entry is not None:
            return result["value"], result.get("text")
        return result["value"]

    def _mac_keep_in_front(self, win):
        """Mac: while the box is open, put it back in front whenever another of the app's windows
        came over it (checked 3 times a second; other apps' windows aren't touched)."""
        def check():
            try:
                if not win.winfo_exists():
                    return
                order = win.tk.splitlist(win.tk.call("wm", "stackorder", self.app.root))
                if order and str(order[-1]) != str(win):
                    win.lift()
                win.after(300, check)
            except tk.TclError:
                pass
        win.after(100, check)

    def close_all(self):
        """Close every message box that's open, as if its X was pressed (the phone remote does this
        before it starts a macro: a box left open would sit over the game)."""
        for win in getattr(self, "open_boxes", []):
            try:
                if win.winfo_exists():
                    win.grab_release()
                    win.destroy()
            except tk.TclError:
                pass
        self.open_boxes = []

    def showinfo(self, title=None, message=None, parent=None, **_kw):
        return self._box(title, message, "info", [("OK", "ok")], "ok", "ok", parent)

    def showwarning(self, title=None, message=None, parent=None, **_kw):
        return self._box(title, message, "warning", [("OK", "ok")], "ok", "ok", parent)

    def showerror(self, title=None, message=None, parent=None, **_kw):
        return self._box(title, message, "error", [("OK", "ok")], "ok", "ok", parent)

    def askyesno(self, title=None, message=None, parent=None, **_kw):
        return self._box(title, message, "question", [("Yes", True), ("No", False)], True, False, parent)

    def askokcancel(self, title=None, message=None, parent=None, **_kw):
        return self._box(title, message, "question", [("OK", True), ("Cancel", False)], True, False, parent)

    def askyesnocancel(self, title=None, message=None, parent=None, **_kw):
        return self._box(title, message, "question", [("Yes", True), ("No", False), ("Cancel", None)],
                         True, None, parent)

    def askquestion(self, title=None, message=None, parent=None, **_kw):
        return "yes" if self.askyesno(title, message, parent) else "no"

    def askchoice(self, title, message, choices, default=None, parent=None):
        """Buttons with your own words: choices = [(text, value)]. Esc / X gives None."""
        return self._box(title, message, "question", choices, default, None, parent)

    def asknumber(self, title, message, initial=0.0, low=0.0, high=3600.0, parent=None):
        """A number typed in a box (None if cancelled or not a number in range)."""
        value, text = self._box(title, message, "question", [("OK", True), ("Cancel", False)], True, False,
                                parent, entry=f"{initial:g}")
        if not value:
            return None
        try:
            number = float(str(text).replace(",", ".").strip())
        except ValueError:
            return None
        return number if low <= number <= high else None


class TreeDrag:
    """(2.11) A list where you choose many by dragging over them (as well as Ctrl+click and Shift+click),
    and drag chosen ones to another place: a blue line shows where they'll go. on_drop(ids, target id,
    "before" / "after") does the moving."""

    def __init__(self, tree, on_drop, is_group=None, others=()):
        """others: [(another list, fn(ids, its row))]: a drop on that list calls fn (2.12)."""
        self.tree, self.on_drop, self.is_group, self.others = tree, on_drop, is_group, list(others)
        self.mode = None
        self.line = tk.Frame(tree, bg=ACCENT, height=2)
        self.lit = None  # a group row lit up: the drop goes inside it
        tree.tag_configure("drop_into", background="#2b3f7a")
        tree.bind("<ButtonPress-1>", self.press, add="+")
        tree.bind("<B1-Motion>", self.motion, add="+")
        tree.bind("<ButtonRelease-1>", self.release, add="+")

    def rows(self):
        out = []

        def go(parent):
            for iid in self.tree.get_children(parent):
                out.append(iid)
                if self.tree.item(iid, "open"):
                    go(iid)
        go("")
        return out

    def press(self, e):
        iid = self.tree.identify_row(e.y)
        self.start, self.start_y, self.mode = iid, e.y, None
        if e.state & 0x0005:  # (Shift or Ctrl: the list's own choosing)
            return None
        if iid and iid in self.tree.selection():
            self.mode = "maybe_move"
            return "break"  # (keep the others chosen: this may be the start of a move)
        self.mode = "select"
        return None

    def motion(self, e):
        iid = self.tree.identify_row(e.y)
        if self.mode == "maybe_move" and abs(e.y - self.start_y) > 6:
            self.mode = "move"
        if self.mode == "move":
            box = self.tree.bbox(iid) if iid else None
            where = self.where(iid, e.y) if box else None
            self.light(iid if where == "into" else None)
            if box and where != "into":
                x, y, w, h = box
                self.line.place(x=0, y=y + (h if where == "after" else 0) - 1, relwidth=1.0)
                self.line.lift()
            else:
                self.line.place_forget()
        elif self.mode == "select" and self.start and iid:
            rows = self.rows()
            if self.start in rows and iid in rows:
                a, b = sorted((rows.index(self.start), rows.index(iid)))
                self.tree.selection_set(rows[a:b + 1])

    def where(self, iid, y):
        """"before" / "after" the row, or "into" it (the middle half of a group's row)."""
        box = self.tree.bbox(iid)
        if not box:
            return None
        top, h = box[1], box[3]
        if self.is_group and iid not in self.tree.selection() and self.is_group(iid) \
                and top + h * 0.25 <= y <= top + h * 0.75:
            return "into"
        return "after" if y > top + h / 2 else "before"

    def light(self, iid):
        if self.lit == iid:
            return
        if self.lit and self.tree.exists(self.lit):
            self.tree.item(self.lit, tags=tuple(t for t in self.tree.item(self.lit, "tags") if t != "drop_into"))
        self.lit = iid
        if iid:
            self.tree.item(iid, tags=tuple(self.tree.item(iid, "tags")) + ("drop_into",))

    def release(self, e):
        mode, self.mode = self.mode, None
        self.line.place_forget()
        self.light(None)
        if mode == "maybe_move":  # just a click on a chosen one: only that one is chosen now
            if self.start:
                self.tree.selection_set(self.start)
                self.tree.focus(self.start)
            return
        if mode != "move":
            return
        under = self.tree.winfo_containing(e.x_root, e.y_root)
        for other, fn in self.others:
            if under is other:
                row = other.identify_row(e.y_root - other.winfo_rooty())
                if row:
                    fn(list(self.tree.selection()), row)
                return
        iid = self.tree.identify_row(e.y)
        box = self.tree.bbox(iid) if iid else None
        if not iid or not box or iid in self.tree.selection():
            return
        self.on_drop(list(self.tree.selection()), iid, self.where(iid, e.y))


def short(text, n=26):
    return text if len(text) <= n else text[:n - 1] + "…"


def hover_text(widget, full):
    """Shows the whole text in a small box while the mouse is over widget, when it was cut short.
    full: the whole text, or a function giving it (shown only when it differs from what's shown)."""
    tip = {"win": None}

    def show(_e=None):
        text = full() if callable(full) else full
        try:
            shown = str(widget.cget("text"))
        except tk.TclError:
            shown = ""
        if not text or text == shown or tip["win"] is not None:
            return
        win = tip["win"] = tk.Toplevel(widget)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        tk.Label(win, text=text, bg=CARD, fg=TEXT, font=F_SMALL, justify="left", wraplength=420, padx=8,
                 pady=5, highlightthickness=1, highlightbackground=BORDER).pack()
        win.geometry(f"+{widget.winfo_rootx()}+{widget.winfo_rooty() + widget.winfo_height() + 2}")

    def hide(_e=None):
        if tip["win"] is not None:
            try:
                tip["win"].destroy()
            except tk.TclError:
                pass
            tip["win"] = None
    widget.bind("<Enter>", show, add="+")
    widget.bind("<Leave>", hide, add="+")
    widget.bind("<Destroy>", hide, add="+")
    return widget


def parse_time_text(text):
    """(2.12) "21:30", "21.30", "2130", "9:05", " 7 : 5 " -> ("21", "30") (two digits each, clamped to
    00-23 and 00-59), or None when it isn't a time."""
    import re

    t = str(text or "").strip()
    m = re.fullmatch(r"(\d{1,2})\s*[:.hH ]\s*(\d{1,2})", t) or re.fullmatch(r"(\d{1,2})(\d{2})", t)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return f"{min(h, 23):02d}", f"{min(mi, 59):02d}"


class TimeBox(tk.Frame):
    """(2.12) A time typed as HH : MM: two small boxes with the ":" always there. Only digits; after two
    hour digits the cursor jumps to the minutes, Backspace in empty minutes jumps back to the hours, ← / →
    move between them, and pasting "21:30" or "2130" fills both. Hours stay 00-23, minutes 00-59.

    .var holds the whole time: "HH:MM", "" when both are empty, or something half like "21:" while it's
    being typed (so a form can tell). on_change(text) is called with the same after each change."""

    def __init__(self, parent, value="", on_change=None, hh_var=None, mm_var=None, bg=BG):
        super().__init__(parent, bg=bg)
        parts = parse_time_text(value) or ("", "")
        self.hh = hh_var or tk.StringVar()
        self.mm = mm_var or tk.StringVar()
        if not hh_var:
            self.hh.set(parts[0])
        if not mm_var:
            self.mm.set(parts[1])
        self.var = tk.StringVar()
        self.on_change = on_change
        self._busy = False
        check = (self.register(lambda p: p == "" or (p.isdigit() and len(p) <= 2)), "%P")

        def box(var):
            return tk.Entry(self, textvariable=var, width=3, justify="center", bg=FIELD, fg=TEXT, font=F_BASE,
                            relief="flat", insertbackground=TEXT, highlightthickness=1,
                            highlightbackground=BORDER, highlightcolor=ACCENT, validate="key",
                            validatecommand=check)
        self.hh_box = box(self.hh)
        self.hh_box.pack(side="left", ipady=3)
        tk.Label(self, text=":", bg=bg, fg=TEXT, font=F_BOLD).pack(side="left", padx=2)
        self.mm_box = box(self.mm)
        self.mm_box.pack(side="left", ipady=3)
        self.hh.trace_add("write", lambda *a: self._typed("hh"))
        self.mm.trace_add("write", lambda *a: self._typed("mm"))
        self.var.trace_add("write", lambda *a: self._var_set())
        self.mm_box.bind("<BackSpace>", self._back)
        self.hh_box.bind("<Right>", lambda e: self._jump(self.mm_box, 0) if self.hh_box.index("insert")
                         >= len(self.hh.get()) else None)
        self.mm_box.bind("<Left>", lambda e: self._jump(self.hh_box, "end") if self.mm_box.index("insert") == 0
                         else None)
        for b in (self.hh_box, self.mm_box):
            b.bind("<<Paste>>", self._paste)
            b.bind("<FocusOut>", lambda e: self._pad(), add="+")
        self._update_var()

    def _jump(self, box, where):
        box.focus_set()
        box.icursor(where)
        return "break"

    def _typed(self, which):
        if self._busy:
            return
        if which == "hh":
            h = self.hh.get()
            if len(h) == 2:
                if int(h) > 23:
                    self._set(self.hh, "23")
                if self.focus_get() is self.hh_box:
                    self._jump(self.mm_box, "end")
        else:
            m = self.mm.get()
            if len(m) == 2 and int(m) > 59:
                self._set(self.mm, "59")
        self._update_var()

    def _back(self, _e):
        if self.mm.get() == "" or (self.mm_box.index("insert") == 0 and not self.mm_box.selection_present()):
            if self.mm.get() == "":
                return self._jump(self.hh_box, "end")
            return None
        self.after_idle(lambda: self.mm.get() == "" and self._jump(self.hh_box, "end"))
        return None

    def _paste(self, _e):
        try:
            parts = parse_time_text(self.clipboard_get())
        except tk.TclError:
            parts = None
        if parts:
            self.set("%s:%s" % parts)
        return "break"

    def _pad(self):
        for var in (self.hh, self.mm):
            if len(var.get()) == 1:
                self._set(var, "0" + var.get())
        self._update_var()

    def _set(self, var, value):
        self._busy = True
        try:
            var.set(value)
        finally:
            self._busy = False

    def _update_var(self):
        h, m = self.hh.get(), self.mm.get()
        text = "" if not h and not m else f"{h}:{m}"
        if self.var.get() != text:
            self._busy = True
            try:
                self.var.set(text)
            finally:
                self._busy = False
        if self.on_change is not None:
            self.on_change(self.value())

    def _var_set(self):
        """Something set .var from outside (like a test): fill the boxes from it."""
        if self._busy:
            return
        text = self.var.get()
        parts = parse_time_text(text)
        self._set(self.hh, parts[0] if parts else "")
        self._set(self.mm, parts[1] if parts else "")
        self._update_var()

    def set(self, text):
        self.var.set(text)

    def value(self):
        """"HH:MM" (padded) when both are filled, "" when both are empty, else None (half typed)."""
        h, m = self.hh.get(), self.mm.get()
        if not h and not m:
            return ""
        if not h or not m:
            return None
        return f"{int(h):02d}:{int(m):02d}"


def entry_hint(entry, var, text, size=12):
    """A grey hint shown over an empty text box (like "Type a name for this picture"). It goes away
    with the first letter typed and comes back when the box is emptied; it never shows while the box
    is greyed out. The hint is laid over the box, not typed into it, so the box's text (a name) stays
    empty and nothing counts as changed. text: the words, or a function giving them.

    Returns update(): call it after the box was greyed out or turned back on."""
    hint = tk.Label(entry, text="", fg=MUTED, font=(FAMILY, size), bd=0, padx=0, pady=0, anchor="w",
                    cursor="xterm")

    def update(*_a):
        try:
            words = text() if callable(text) else text
            show = bool(words) and not var.get() and str(entry.cget("state")) != "disabled"
            if show:
                hint.config(text=words, bg=entry.cget("bg"))
                hint.place(x=3, rely=0.5, anchor="w")
            else:
                hint.place_forget()
        except Exception:  # (the window is closing, or isn't ready yet): no hint
            try:
                hint.place_forget()
            except tk.TclError:
                pass

    def focus_box(_e=None):
        if str(entry.cget("state")) != "disabled":
            entry.focus_set()
            entry.icursor("end")
        return "break"
    hint.bind("<Button-1>", focus_box)
    var.trace_add("write", update)
    entry.after_idle(update)
    return update


class WindowStack:
    """Which window is in front (2.9). The window you switch to (a click, dragging it, Alt+Tab) comes
    to the front and stays there until you switch to another one; nothing is pushed back in front of
    it. A new window shows in front of the window it was opened from, and windows hidden for a
    moment (while picking a picture from the screen) come back with the one you were using in
    front."""

    def __init__(self, root):
        self.root = root

    def bring_back(self, windows):
        """Windows that were hidden for a moment: shown again, the first one (the one in use) in
        front of the others."""
        windows = [w for w in windows if w is not None]
        for w in reversed(windows):  # (the last one shown ends up in front: the first one)
            try:
                w.deiconify()
                w.lift()
            except tk.TclError:
                pass
        if windows:
            try:
                windows[0].focus_force()
            except tk.TclError:
                pass


class _MessageBoxes:
    """The message boxes every part of the window uses: Windows' own at first, the dark ones
    (ThemedBoxes) as soon as the window exists (use_boxes)."""

    def __init__(self, target):
        object.__setattr__(self, "target", target)

    def use(self, target):
        object.__setattr__(self, "target", target)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "target"), name)

    def __setattr__(self, name, value):  # (tests replace a box with their own)
        setattr(object.__getattribute__(self, "target"), name, value)


messagebox = _MessageBoxes(_tk_messagebox)

