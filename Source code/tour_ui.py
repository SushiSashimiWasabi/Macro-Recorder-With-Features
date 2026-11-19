"""Guided tours (Preview 4, more in 2.13 review): a few short steps, each pointing at a part of a window with
Next / Back / Skip. "main" is shown once to everyone (new users after the first-start questions, people who
already use the app after the update) and again from Settings > About > "Replay the tour". The other tours
(Settings, Edit, Picture watch, Recorded events) start from a "Tour" link in their own window.

A tour never takes over the app (no grab, Escape closes it). The main one only starts while this app is the
window in front and nothing plays or records, so it never pops up over a game. A tour hides while its window
is minimized, follows it when it moves, and ends when that window is closed or playing / recording starts."""
import os
import tkinter as tk
from tkinter import ttk

import macro_recorder as core
import own_windows
import window_tools
from ui_common import *  # noqa: F401,F403


def _w(name):
    """A step's target: the main window's part with this name."""
    return lambda a: getattr(a, name, None)


def _ed(name):
    return lambda a: getattr(getattr(a, "macro_editor", None), name, None)


def _pw(name):
    return lambda a: getattr(getattr(a, "picture_win", None), name, None)


def _tab(name):
    """Settings: open this page, then point at it."""
    return (lambda a: getattr(a, "tab_areas", {}).get(name),
            lambda a: a.tabs.select(a.tab_areas[name]))


def _ev(name):
    return lambda a: (getattr(getattr(a, "events_win", None), "tour", None) or {}).get(name)


def _settings_step(name, title, text):
    target, prep = _tab(name)
    return (target, title, text, prep)


# every tour: (which window it is in, [(the part it points at, title, text, what to do first or None)])
TOURS = {
    "main": ("main", [
        (_w("card_record"), "Record", "Press Record (or F9) and do what the macro should do. Press it again to stop. "
                                      "It asks which window to record in, so the game comes to the front first.", None),
        (_w("card_play"), "Play", "Play (F11) plays the macro. Repeat continuously and Speed are just under these "
                                  "buttons. Stop (F12) stops it, and Ctrl+Alt+End always stops everything.", None),
        (_w("mac_label"), "Saved macros", "Every macro you open or save is listed here. ◀ ▶ switch between them, "
                                          "and \"All ▾\" can show one folder only.", None),
        (_w("btn_edit"), "Edit", "Edit… opens the macro as a list of actions: add waits, picture checks, If, Repeat, "
                                 "counters and more. Right-click a macro on its left to put it in a folder or give "
                                 "it tags. The Edit window has its own Tour link.", None),
        (_w("picture_link"), "Picture watch", "Picture watch looks for pictures on the screen while playing, like "
                                              "MISSION COMPLETED or Disconnected, and does what you choose when "
                                              "one shows. Its window has its own Tour link.", None),
        (_w("gear_link"), "Settings", "Everything else is in Settings: hotkeys, Discord, sounds, backgrounds, "
                                      "colours, milestones. Use its Search box to find an option. Settings has its "
                                      "own Tour link.", None),
    ]),
    "settings": ("settings", [
        (_w("search_box"), "Search", "Type a word to find any option, even by its old name. Click a result to go "
                                     "straight to it.", None),
        (_w("tab_bar"), "The pages", "Settings has 9 pages: General, Playback, Picture watch, Recording, Results, "
                                     "Background, Sounds, Discord and About. Click a name to open it.", None),
        _settings_step("General", "General", "Hotkeys, keep the window on top, the status line, window sizes, your "
                                             "own icon and logo, and opening .macro files with this app."),
        _settings_step("Playback", "Playback", "How a macro plays: pause when its window isn't in front, what to do "
                                               "if the game closes or a run gets stuck, stop by itself, start "
                                               "playing later, small random timing and keys on screen."),
        _settings_step("Recording", "Recording", "Which window to record in, the countdown before recording, mouse "
                                                 "movement detail and recording the game camera."),
        _settings_step("Results", "Results", "Run stats (wins, losses, run times), divine fragments and your "
                                             "milestones."),
        _settings_step("Background", "Background", "The accent colour and the background pictures for each window."),
        _settings_step("Discord", "Discord", "The results card, pings, daily or weekly summaries and messages sent "
                                             "from macros."),
        _settings_step("About", "About", "What's new, Replay the tour, Make a report (the best thing to send when "
                                        "something goes wrong) and Reports and logs."),
    ]),
    "edit": ("edit", [
        (_ed("macros"), "Your macros", "Every saved macro. Click one to edit it. Right-click for folders and tags, "
                                       "and use the filter above for a name, a folder or a #tag.", None),
        (lambda a: a.macro_editor.game_label.master, "Game window", "The window the macro plays in. Change… picks "
                                                                    "another one; its clicks are fitted to it.", None),
        (_ed("btn_add"), "Add action", "Opens a list in sections: keys and mouse, waiting, groups, counters and "
                                       "maths, jumps, chain, tell me, macro, record or copy in.", None),
        (_ed("tree"), "The actions", "The macro, in the order it plays. If, Repeat and Retry hold other actions. "
                                     "Ctrl or Shift choose many, drag to move, and right-click for Play from here "
                                     "or Show without playing.", None),
        (_ed("detail"), "Details", "The options of the chosen action. Changes light up Apply.", None),
        (_ed("bottom"), "Duplicate, Remove, More", "More has Trim, Restore an older version and more. ⇤ Out and "
                                                   "In ⇥ move an action out of or into a group. An If and its Else "
                                                   "always move together.", None),
        (lambda a: a.macro_editor.btn_apply.master, "Apply", "Apply saves the changes. Undo, Redo and Reset go "
                                                              "back; nothing is kept until you Apply.", None),
    ]),
    "picture": ("picture", [
        (_pw("groups_tree"), "Groups", "Pictures live in groups. AOT:R has the built-in ones (RETRY, Disconnected, "
                                       "MISSION COMPLETED, MISSION FAILED). Make your own with New group.", None),
        (_pw("pics_tree"), "Pictures", "The pictures of the chosen group, and what each does when it shows. Ctrl or "
                                       "Shift choose many; drag onto a group to move; right-click for Copy, Paste, "
                                       "Duplicate and Turn on / off.", None),
        (lambda a: a.picture_win.btn_from_screen.master, "Add", "Add from screen…, Picture file…, Add built-in ▾, or "
                                                                "Colour… to look for a colour instead.", None),
        (_pw("detail"), "Options", "What the chosen picture does when it shows: start over, play a macro, switch "
                                   "macro, press a key, wait, stop or add to a counter. Also click on it, its own "
                                   "Match % and a cooldown.", None),
        (lambda a: a.picture_win.name_entry.master, "Apply", "Undo, Redo, Reset and Apply. Nothing is kept until "
                                                              "you Apply.", None),
    ]),
    "events": ("events", [
        (_ev("summary"), "The recording", "How many actions and how long. Each row below is one recorded action "
                                          "with its time.", None),
        (_ev("table"), "The actions", "Choose many with Ctrl+click, Shift+click or by dragging. Drag rows to move "
                                      "them, and right-click to try them.", None),
        (_ev("tools0"), "Add and try", "Add action ▾, Record here… and Preview ▾ (play only the chosen rows, or "
                                       "show them without playing). Undo and Redo are here too.", None),
        (_ev("tools_many"), "The chosen rows", "Duplicate, Copy, Cut, Paste, and move them Up or Down.", None),
        (_ev("tools"), "Clean up", "Remove selected, Remove all mouse moves, Cut the wait at the start. The row "
                                   "below adds and changes waits and Wait for a picture steps.", None),
        (_ev("bottom"), "Apply", "Apply gives the changes back to the macro. Cancel throws them away.", None),
    ]),
}
WAIT_MS = 2000  # how often it looks whether it may start
WAIT_TRIES = 300  # (10 minutes)
WATCH_MS = 300  # how often a running tour looks at its window


def _alive(w):
    try:
        return w is not None and bool(w.winfo_exists())
    except tk.TclError:
        return False


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

    def tour_first_scan(self):
        """Every 1.5 s (real app only: `tours_auto`): a window that has a tour and is open for the first time gets
        its tour by itself, once per tour, also for people who finished the main tour long ago. The window gets one
        look to appear first, and nothing starts while a macro plays or records or another tour runs."""
        if not getattr(self, "tours_auto", False):
            return
        seen = self.settings.get("tours_seen")
        seen = seen if isinstance(seen, list) else []
        sighted = self.__dict__.setdefault("tour_sighted", set())
        busy = self.playing or self.recording or getattr(self, "countdown_left", 0) > 0 \
            or getattr(self, "tour_win", None) is not None or getattr(self, "first_start_due", lambda: False)()
        for name, (which, _steps) in TOURS.items():
            if name == "main" or name in seen:
                continue
            host = self._tour_host(which)
            if host is None or not host.winfo_viewable():
                sighted.discard(name)
            elif name not in sighted:
                sighted.add(name)
            elif not busy:
                self.settings["tours_seen"] = seen + [name]
                core.save_settings(self.settings)
                self.start_tour(name)
                return

    def tour_first_tick(self):
        """The real app's loop around `tour_first_scan` (tests call the scan by hand)."""
        self.tours_auto = True
        try:
            self.tour_first_scan()
        finally:
            self.root.after(1500, self.tour_first_tick)

    def _tour_host(self, which):
        """The window a tour is about (None when it isn't open)."""
        if which == "main":
            return self.root
        host = {"settings": lambda: self.settings_win,
                "edit": lambda: getattr(getattr(self, "macro_editor", None), "win", None),
                "picture": lambda: getattr(getattr(self, "picture_win", None), "win", None),
                "events": lambda: getattr(self, "events_win", None)}[which]()
        return host if _alive(host) and host.state() != "withdrawn" else None

    def start_tour(self, name="main"):
        self.end_tour(done=False)
        which, steps = TOURS[name]
        host = self._tour_host(which)
        if host is None:
            return None
        if name == "main" and self.settings_win is not None and self.settings_win.winfo_viewable():
            self.close_settings()
        self.tour_name, self.tour_steps, self.tour_host = name, steps, host
        self.tour_step, self.tour_hidden, self.tour_at = 0, False, None
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
        if not getattr(host, "tour_escape_bound", False):  # (bound once per window, not on every Replay)
            host.tour_escape_bound = True
            host.bind("<Escape>", lambda e: self.end_tour() if getattr(self, "tour_win", None) else None, add="+")
        self.tour_marks = []
        for _ in range(4):  # a frame of 4 thin bars around the part it talks about
            bar = tk.Toplevel(self.root, bg=ACCENT)
            bar.withdraw()
            bar.overrideredirect(True)
            bar.attributes("-topmost", True)
            self.tour_marks.append(bar)
        core.diag.info(f"Guided tour started: {name}")
        self._tour_show()
        self.tour_job = self.root.after(WATCH_MS, self._tour_watch)
        return win

    def _tour_go(self, d):
        self.tour_step += d
        if self.tour_step >= len(self.tour_steps):
            self.end_tour()
            return
        self.tour_step = max(0, self.tour_step)
        self._tour_show()

    def _tour_show(self, focus=True):
        target_fn, title, text, prep = self.tour_steps[self.tour_step]
        win, host = self.tour_win, self.tour_host
        if prep is not None:
            try:
                prep(self)
                host.update_idletasks()
            except (tk.TclError, KeyError, AttributeError):
                pass
        try:
            target = target_fn(self)
        except (AttributeError, KeyError, tk.TclError):
            target = None
        self.tour_title.config(text=title)
        self.tour_text.config(text=text)
        self.tour_count.config(text=f"{self.tour_step + 1} of {len(self.tour_steps)}")
        self.tour_next.config(text="Done" if self.tour_step == len(self.tour_steps) - 1 else "Next")
        self.tour_back.config(state="normal" if self.tour_step else "disabled")
        host.update_idletasks()
        win.update_idletasks()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        ww, wh = win.winfo_reqwidth(), win.winfo_reqheight()
        if _alive(target) and target.winfo_ismapped():
            x, y, w, h = target.winfo_rootx(), target.winfo_rooty(), target.winfo_width(), target.winfo_height()
            for n, (bar, geo) in enumerate(zip(self.tour_marks, ((x - 4, y - 4, w + 8, 3), (x - 4, y + h + 1, w + 8, 3),
                                                                 (x - 4, y - 4, 3, h + 8), (x + w + 1, y - 4, 3, h + 8)))):
                bar.configure(bg=ACCENT)
                bar.geometry(f"{geo[2]}x{geo[3]}+{geo[0]}+{geo[1]}")
                own_windows.set_rect(f"tour_bar{n}", (geo[0], geo[1], geo[0] + geo[2], geo[1] + geo[3]))
                bar.deiconify()
                bar.lift()
            bx, by = x, y + h + 12  # (under it, or over it near the bottom of the screen)
            if by + wh > sh - 40:
                by = y - wh - 12
            bx = max(8, min(bx, sw - ww - 8))
            by = max(8, by)
        else:
            for n, bar in enumerate(self.tour_marks):
                bar.withdraw()
                own_windows.set_rect(f"tour_bar{n}", None)
            bx = host.winfo_rootx() + (host.winfo_width() - ww) // 2
            by = host.winfo_rooty() + (host.winfo_height() - wh) // 2
        win.geometry(f"+{bx}+{by}")
        own_windows.set_rect("tour", (bx, by, bx + ww, by + wh))
        win.deiconify()
        win.lift()
        self.tour_at = self._tour_host_at()
        if focus:
            try:
                win.focus_force()
            except tk.TclError:
                pass

    def tour_to_front(self):
        """Something raised another window (a Settings page change): the tour box and its bars go back on top."""
        for w in [getattr(self, "tour_win", None)] + list(getattr(self, "tour_marks", [])):
            if _alive(w) and w.winfo_ismapped():
                w.lift()

    def _tour_host_at(self):
        h = self.tour_host
        return (h.winfo_rootx(), h.winfo_rooty(), h.winfo_width(), h.winfo_height())

    def _tour_hide(self):
        """Its window is minimized: the tour waits out of sight."""
        for w in [self.tour_win] + list(self.tour_marks):
            if _alive(w):
                w.withdraw()
        for name in ("tour", "tour_bar0", "tour_bar1", "tour_bar2", "tour_bar3"):
            own_windows.set_rect(name, None)

    def _tour_watch(self):
        """Every 0.3 s: the tour ends when its window is gone or hidden, waits while it is minimized, and
        goes with it when it moves or changes size."""
        self.tour_job = None
        if getattr(self, "tour_win", None) is None:
            return
        host = self.tour_host
        try:
            state = host.state() if _alive(host) else "gone"
        except tk.TclError:
            state = "gone"
        if state in ("gone", "withdrawn"):
            self.end_tour(done=False)
            return
        if state == "iconic":
            if not self.tour_hidden:
                self.tour_hidden = True
                self._tour_hide()
        else:
            moved = self.tour_at != self._tour_host_at()
            if self.tour_hidden or moved:
                self.tour_hidden = False
                self._tour_show(focus=False)
        self.tour_job = self.root.after(WATCH_MS, self._tour_watch)

    def tour_stop_if_busy(self):
        """Playing or recording started: its boxes are topmost and Picture watch would see them, so close
        the tour (not marked done: it comes back next start)."""
        if getattr(self, "tour_win", None) is not None and (self.playing or self.recording):
            self.end_tour(done=False)

    def end_tour(self, done=True):
        job, self.tour_job = getattr(self, "tour_job", None), None
        if job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        for w in [getattr(self, "tour_win", None)] + list(getattr(self, "tour_marks", [])):
            if w is not None and w.winfo_exists():
                w.destroy()
        self.tour_win, self.tour_marks = None, []
        for name in ("tour", "tour_bar0", "tour_bar1", "tour_bar2", "tour_bar3"):
            own_windows.set_rect(name, None)
        if done and getattr(self, "tour_name", "main") == "main":
            self.settings["tour_done"] = True
            core.save_settings(self.settings)
            core.diag.info("Guided tour closed")
