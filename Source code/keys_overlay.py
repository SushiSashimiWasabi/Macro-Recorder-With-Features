"""Keys on screen (Preview 4): a small box in a corner of the main screen that shows the keys and clicks
being played or recorded ("W", "Shift + E", "Left click"), for videos and for checking a macro.

Settings > Playback > "Show keys on screen" (setting keys_on_screen, off at first; keys_corner). The box lets
clicks through and never takes the keyboard. It shows in screen recordings, and Picture watch / colour
checks don't see it (its place is blacked out of their screenshots: own_windows)."""
import collections
import time
import tkinter as tk

import macro_steps as workflow
import own_windows
from ui_common import *  # noqa: F401,F403

CORNERS = {"bottom_right": "Bottom right", "bottom_left": "Bottom left", "top_right": "Top right",
           "top_left": "Top left"}
SHOW_SECONDS = 2.5
MAX_LINES = 4
MODIFIERS = {"shift", "shift_l", "shift_r", "ctrl", "ctrl_l", "ctrl_r", "alt", "alt_l", "alt_r", "alt_gr", "cmd",
             "cmd_l", "cmd_r"}
MODIFIER_VKS = {16: "shift", 160: "shift", 161: "shift", 17: "ctrl", 162: "ctrl", 163: "ctrl", 18: "alt", 164: "alt",
                165: "alt"}  # (keys from other recorders' files)
BUTTONS = {"left": "Left click", "right": "Right click", "middle": "Middle click"}


def event_text(ev, held):
    """What the box shows for one recorded / played event (None for moves and letting go).
    held: the modifier keys held right now (names), changed here."""
    kind = ev.get("type")
    if kind == "key":
        key = ev.get("key") or {}
        special = str(key.get("special", "")).lower() or MODIFIER_VKS.get(key.get("vk"), "")
        if special in MODIFIERS:
            base = special.split("_")[0]
            if ev.get("pressed"):
                held.add(base)
            else:
                held.discard(base)
            return None
        if not ev.get("pressed"):
            return None
        mods = [m.title() for m in ("ctrl", "alt", "shift", "cmd") if m in held]
        return " + ".join(mods + [workflow.key_text(key)])
    if kind == "click" and ev.get("pressed"):
        return BUTTONS.get(str(ev.get("button", "")).split(".")[-1].lower(), "Click")
    if kind == "scroll":
        return "Scroll " + ("up" if ev.get("dy", 0) > 0 else "down")
    return None


class KeysOverlay:
    def __init__(self, root, corner="bottom_right"):
        self.root = root
        self.corner = corner if corner in CORNERS else "bottom_right"
        self.lines = collections.deque(maxlen=MAX_LINES)  # (text, time shown)
        self.held = set()
        self.pending = collections.deque(maxlen=50)  # (from the playback / recording threads)
        self.win = win = tk.Toplevel(root, bg=PANEL)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.9)
        except tk.TclError:
            pass
        self.label = tk.Label(win, bg=PANEL, fg=TEXT, font=(FAMILY, 14, "bold"), justify="right", padx=14, pady=8)
        self.label.pack()
        self.made_through = False
        self.job = None
        self.rect = None

    def add(self, ev):
        """Any thread: an event that was just played or recorded."""
        self.pending.append(ev)

    def tick(self):
        """The window's thread, a few times a second: take what came in, drop old lines, show the rest."""
        while self.pending:
            try:
                text = event_text(self.pending.popleft(), self.held)
            except Exception:  # (an odd event from an imported file: skip it, keep the box going)
                text = None
            if text:
                self.lines.append((text, time.monotonic()))
        now = time.monotonic()
        while self.lines and now - self.lines[0][1] > SHOW_SECONDS:
            self.lines.popleft()
        self._show("\n".join(t for t, _ in self.lines))

    def _show(self, text):
        w = self.win
        if not text:
            if w.state() != "withdrawn":
                w.withdraw()
                self._ignore(None)
            return
        if text != self.label.cget("text"):
            self.label.config(text=text)
        w.update_idletasks()
        width, height = max(w.winfo_reqwidth(), 120), w.winfo_reqheight()
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        x = 24 if self.corner.endswith("left") else sw - width - 24
        y = 24 if self.corner.startswith("top") else sh - height - 64  # (above the taskbar)
        w.geometry(f"{width}x{height}+{x}+{y}")
        if w.state() == "withdrawn":
            w.deiconify()
            self._click_through()
        w.lift()
        self._ignore((x, y, x + width, y + height))

    def _ignore(self, rect):
        """Picture watch and colour checks don't look at the box."""
        self.rect = rect
        own_windows.set_rect("keys", rect)

    def _click_through(self):
        if self.made_through or not IS_WIN:
            return
        try:
            import ctypes

            u = ctypes.windll.user32
            hwnd = u.GetParent(self.win.winfo_id()) or self.win.winfo_id()
            # LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE (like the timer at the top)
            u.SetWindowLongW(hwnd, -20, u.GetWindowLongW(hwnd, -20) | 0x80000 | 0x20 | 0x80 | 0x8000000)
            self.made_through = True
        except Exception:
            pass

    def hide(self):
        self.lines.clear()
        self.pending.clear()
        self.held.clear()
        self._show("")


class KeysOverlayMixin:
    def keys_on_screen_on(self):
        return bool(self.settings.get("keys_on_screen", False))

    def _keys_overlay(self):
        ov = getattr(self, "keys_overlay", None)
        if ov is None:
            ov = self.keys_overlay = KeysOverlay(self.root, self.settings.get("keys_corner", "bottom_right"))
        ov.corner = self.settings.get("keys_corner", "bottom_right") if \
            self.settings.get("keys_corner") in CORNERS else "bottom_right"
        return ov

    def _keys_seen(self, ev):
        """An event played or recorded (any thread)."""
        if self.keys_on_screen_on() and not getattr(self, "ghost", False):
            ov = getattr(self, "keys_overlay", None)
            if ov is not None:
                ov.add(ev)

    def _keys_tick(self):
        """While playing or recording: the box keeps up (5 times a second)."""
        self.keys_job = None
        busy = self.playing or self.recording
        ov = getattr(self, "keys_overlay", None)
        if not busy or not self.keys_on_screen_on():
            if ov is not None:
                ov.hide()
            return
        self._keys_overlay().tick()
        self.keys_job = self.root.after(200, self._keys_tick)

    def _keys_start(self):
        if self.keys_on_screen_on() and getattr(self, "keys_job", None) is None:
            self._keys_overlay()
            self.keys_job = self.root.after(50, self._keys_tick)
