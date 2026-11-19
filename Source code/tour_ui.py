"""Guided tour (Preview 4): 6 short steps, each pointing at a part of the main window with Next / Back /
Skip. Shown once to everyone (new users after the first-start questions, people who already use the app
after the update), and again from Settings > About > "Replay the tour".

The tour never takes over the app (no grab, Escape closes it), and it only starts while this app is the
window in front and nothing plays or records, so it never pops up over a game."""
import os
import tkinter as tk
from tkinter import ttk

import macro_recorder as core
import window_tools
from ui_common import *  # noqa: F401,F403

STEPS = (
    ("card_record", "Record", "Press Record (or F9) and do what the macro should do. Press it again to stop. "
                              "It asks which window to record in, so the game comes to the front first."),
    ("card_play", "Play", "Play (F11) plays the macro. Repeat continuously and Speed are just under these buttons. "
                          "Stop (F12) stops it, and Ctrl+Alt+End always stops everything."),
    ("mac_label", "Saved macros", "Every macro you open or save is listed here. ◀ ▶ switch between them, and "
                                  "\"All ▾\" can show one folder only."),
    ("btn_edit", "Edit", "Edit… opens the macro as a list of actions: add waits, picture checks, If, Repeat, "
                         "counters and more. Right-click a macro on its left to put it in a folder or give it tags."),
    ("picture_link", "Picture watch", "Picture watch looks for pictures on the screen while playing, like "
                                      "MISSION COMPLETED or Disconnected, and does what you choose when one shows."),
    ("gear_link", "Settings", "Everything else is in Settings: hotkeys, Discord, sounds, backgrounds, colours, "
                              "milestones. Use its Search box to find an option."),
)
WAIT_MS = 2000  # how often it looks whether it may start
WAIT_TRIES = 300  # (10 minutes)


class TourMixin:
    def tour_due(self):
        return not self.settings.get("tour_done") and not self.first_start_due()

    def tour_when_ready(self, tries=0):
        """Start the tour once this app is in front and nothing plays or records (looks every 2 s)."""
        if not self.tour_due() or tries > WAIT_TRIES:
            return
        busy = self.playing or self.recording or getattr(self, "countdown_left", 0) > 0
        fs = getattr(self, "first_start_win", None)
        busy = busy or (fs is not None and fs.winfo_exists())
        front = True
        if window_tools.IS_WIN:
            fg = window_tools.foreground()
            front = fg is not None and window_tools.pid_of(fg) == os.getpid()
        if busy or not front or not self.root.winfo_viewable():
            self.root.after(WAIT_MS, lambda: self.tour_when_ready(tries + 1))
            return
        self.start_tour()

    def start_tour(self):
        self.end_tour(done=False)
        if self.settings_win is not None and self.settings_win.winfo_viewable():
            self.close_settings()
        self.tour_step = 0
        win = self.tour_win = tk.Toplevel(self.root, bg=ACCENT)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        inner = tk.Frame(win, bg=PANEL)
        inner.pack(padx=2, pady=2)
        self.tour_title = tk.Label(inner, bg=PANEL, fg=TEXT, font=F_BOLD, anchor="w")
        self.tour_title.pack(fill="x", padx=14, pady=(12, 2))
        self.tour_text = tk.Label(inner, bg=PANEL, fg=MUTED, font=F_BASE, anchor="w", justify="left",
                                  wraplength=300)
        self.tour_text.pack(fill="x", padx=14)
        bottom = tk.Frame(inner, bg=PANEL)
        bottom.pack(fill="x", padx=14, pady=(10, 12))
        self.tour_count = tk.Label(bottom, bg=PANEL, fg=DIM, font=F_SMALL)
        self.tour_count.pack(side="left")
        self.tour_next = ttk.Button(bottom, text="Next", style="Accent.TButton", width=7,
                                    command=lambda: self._tour_go(1))
        self.tour_next.pack(side="right")
        self.tour_back = ttk.Button(bottom, text="Back", width=6, command=lambda: self._tour_go(-1))
        self.tour_back.pack(side="right", padx=(0, 6))
        link(bottom, "Skip the tour", lambda: self.end_tour(), bg=PANEL).pack(side="right", padx=(0, 10))
        win.bind("<Escape>", lambda e: self.end_tour())
        self.root.bind("<Escape>", lambda e: self.end_tour() if getattr(self, "tour_win", None) else None, add="+")
        self.tour_marks = []
        for _ in range(4):  # a frame of 4 thin bars around the part it talks about
            bar = tk.Toplevel(self.root, bg=ACCENT)
            bar.withdraw()
            bar.overrideredirect(True)
            bar.attributes("-topmost", True)
            self.tour_marks.append(bar)
        core.diag.info("Guided tour started")
        self._tour_show()
        return win

    def _tour_go(self, d):
        self.tour_step += d
        if self.tour_step >= len(STEPS):
            self.end_tour()
            return
        self.tour_step = max(0, self.tour_step)
        self._tour_show()

    def _tour_show(self):
        name, title, text = STEPS[self.tour_step]
        target = getattr(self, name, None)
        win = self.tour_win
        self.tour_title.config(text=title)
        self.tour_text.config(text=text)
        self.tour_count.config(text=f"{self.tour_step + 1} of {len(STEPS)}")
        self.tour_next.config(text="Done" if self.tour_step == len(STEPS) - 1 else "Next")
        self.tour_back.config(state="normal" if self.tour_step else "disabled")
        self.root.update_idletasks()
        win.update_idletasks()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        ww, wh = win.winfo_reqwidth(), win.winfo_reqheight()
        if target is not None and target.winfo_ismapped():
            x, y, w, h = target.winfo_rootx(), target.winfo_rooty(), target.winfo_width(), target.winfo_height()
            for bar, geo in zip(self.tour_marks, ((x - 4, y - 4, w + 8, 3), (x - 4, y + h + 1, w + 8, 3),
                                                  (x - 4, y - 4, 3, h + 8), (x + w + 1, y - 4, 3, h + 8))):
                bar.configure(bg=ACCENT)
                bar.geometry(f"{geo[2]}x{geo[3]}+{geo[0]}+{geo[1]}")
                bar.deiconify()
                bar.lift()
            bx, by = x, y + h + 12  # (under it, or over it near the bottom of the screen)
            if by + wh > sh - 40:
                by = y - wh - 12
            bx = max(8, min(bx, sw - ww - 8))
            by = max(8, by)
        else:
            for bar in self.tour_marks:
                bar.withdraw()
            bx = self.root.winfo_rootx() + (self.root.winfo_width() - ww) // 2
            by = self.root.winfo_rooty() + (self.root.winfo_height() - wh) // 2
        win.geometry(f"+{bx}+{by}")
        win.deiconify()
        win.lift()
        try:
            win.focus_force()
        except tk.TclError:
            pass

    def end_tour(self, done=True):
        for w in [getattr(self, "tour_win", None)] + list(getattr(self, "tour_marks", [])):
            if w is not None and w.winfo_exists():
                w.destroy()
        self.tour_win, self.tour_marks = None, []
        if done:
            self.settings["tour_done"] = True
            core.save_settings(self.settings)
            core.diag.info("Guided tour closed")
