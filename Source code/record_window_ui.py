"""Record in which window? (2.11): when Record is pressed in this app (not with the Record key from a
game), a dark box lists the open windows; the chosen one is brought to the front and the countdown
starts, so there's time to get ready. A line under the list can link the new macro to a profile (an existing one or
a new one made from the settings in use), which only happens when the macro is saved.

Window titles are only shown in the box, never saved; only the chosen program's file name is
remembered (to choose it again next time). Windows only (elsewhere Record works as before)."""
import os
import time
import tkinter as tk
from tkinter import ttk

import macro_recorder as core
import window_tools
from ui_common import *  # noqa: F401,F403

DESKTOP = "desktop"
NEW_PROFILE = "New profile…"
NO_LINK = "(none)"


class RecordWindowMixin:
    def _before_record(self):
        """Called just before the countdown before recording: False = don't record."""
        self.record_window = None
        if not self._ask_record_window_now():
            return True
        choice = self.ask_record_window()
        if choice is None:
            core.diag.info("Recording cancelled in \"Record in which window?\"")
            done, self.record_into = self.record_into, None
            if done is not None:  # (recording for Edit: it gets nothing, and its window comes back)
                self.root.after(0, lambda: done([]))
            return False
        target, profile = choice
        self.pending_profile = profile if self.record_into is None else None
        if target == DESKTOP:
            self.record_window = {"desktop": True, "title": "the desktop"}
            if self.record_into is None:
                self.root.iconify()
                self.record_iconified = True
            return True
        hwnd, title, exe = target
        self.record_window = {"hwnd": hwnd, "title": title, "exe": exe}
        self.settings["record_last_exe"] = exe
        core.save_settings(self.settings)
        try:
            if window_tools.IS_WIN:
                import ctypes

                if ctypes.windll.user32.IsIconic(hwnd):
                    ctypes.windll.user32.ShowWindow(hwnd, 9)  # (minimized: restore it first)
            window_tools.force_to_front(hwnd)
        except Exception as exc:
            core.diag.error("Couldn't bring the window to the front for recording", exc)
        self.root.after(600, self._check_record_front)
        return True

    def _ask_record_window_now(self):
        """Only when Record is pressed inside this app (the Record key from a game records there)."""
        if not window_tools.IS_WIN or not self.settings.get("record_ask_window", True):
            return False
        fg = window_tools.foreground()
        return fg is not None and window_tools.pid_of(fg) == os.getpid()

    def _check_record_front(self):
        w = getattr(self, "record_window", None)
        if not w or w.get("desktop") or self.record_countdown_left <= 0:
            return
        if window_tools.foreground() != w["hwnd"]:
            w["note"] = "Click into it now"

    def record_window_text(self):
        """For the countdown at the top of the screen: "· Roblox" (and what to do, if needed)."""
        w = getattr(self, "record_window", None)
        if not w:
            return ""
        return "  ·  " + short(w["title"], 30) + (f"  ·  {w['note']}" if w.get("note") else "")

    def _record_window_gone(self):
        """During the countdown: the chosen window was closed. True (and recording is cancelled)."""
        w = getattr(self, "record_window", None)
        if not w or w.get("desktop") or window_tools.is_window(w["hwnd"]):
            return False
        self._cancel_record_countdown()
        self.record_window = None
        self.boxes.showwarning("Record", f"The window you chose to record in ({short(w['title'], 40)}) was "
                               "closed, so recording was cancelled.", parent=self.root)
        return True

    def _record_stopped_here(self):
        """Recording ended or was cancelled: the main window comes back if it was put away."""
        if getattr(self, "record_iconified", False):
            self.record_iconified = False
            self.root.deiconify()

    # ------------------------------------------------------------ the box

    def ask_record_window(self):
        """(window or DESKTOP, profile link or None), or None when cancelled. Profile link:
        ("existing", name) or ("new", name)."""
        own = os.getpid()
        wins = [(h, t, e) for h, t, e in window_tools.app_windows() if window_tools.pid_of(h) != own]
        # (2.11 fix: never attached to a window that isn't on screen. "Record keys and mouse…" hides the
        # Edit window first; a box attached to it was hidden too, and still held the whole app)
        candidates = [self.edit_win] if self.record_into is not None and getattr(self, "edit_win", None) else []
        parent = next((w for w in candidates + [self.root]
                       if w is not None and w.winfo_exists() and w.winfo_viewable()), None)
        win = tk.Toplevel(parent or self.root, bg=BG)
        win.withdraw()
        win.title("Record in which window?")
        if parent is not None:
            win.transient(parent)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=20, pady=(16, 8))
        tk.Label(body, text="Record in which window?", bg=BG, fg=TEXT, font=F_BOLD, anchor="w").pack(fill="x")
        tk.Label(body, text="It comes to the front and the countdown starts, so you have time to get ready.",
                 bg=BG, fg=MUTED, font=F_SMALL, anchor="w").pack(fill="x", pady=(2, 8))
        lst = ttk.Treeview(body, show="tree", selectmode="browse", height=min(10, len(wins) + 1))
        lst.column("#0", width=470)
        lst.pack(fill="x")
        lst.insert("", "end", iid="desktop", text="The desktop (no window)")
        last = self.settings.get("record_last_exe")
        pick = None
        for k, (_h, title, exe) in enumerate(wins):
            name = os.path.splitext(exe or "")[0]
            lst.insert("", "end", iid=str(k), text=f"{short(title, 52)}   ({name})" if name else short(title, 60))
            if pick is None and exe and last and exe.lower() == str(last).lower():
                pick = str(k)
        pick = pick or ("0" if wins else "desktop")
        lst.selection_set(pick)
        lst.see(pick)
        # link the new macro to a profile (only for a new macro, not a recording for Edit)
        more = tk.Frame(body, bg=BG)
        profile_var = tk.StringVar(value=NO_LINK)
        if self.record_into is None and hasattr(self, "profiles"):
            more.pack(fill="x", pady=(10, 0))  # (shown at once: 16 Nov)
            row = tk.Frame(more, bg=BG)
            row.pack(fill="x", pady=(4, 0))
            tk.Label(row, text="Link the new macro to the profile", bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
            names = [NO_LINK] + sorted(self.profiles(), key=str.lower) + [NEW_PROFILE]
            box = ttk.Combobox(row, textvariable=profile_var, values=names, state="readonly", width=20)
            box.pack(side="right")
            tk.Label(more, text="Opening the macro then switches to that profile. A new profile uses your "
                                "settings as they are now. It's only made and linked when you save the macro.",
                     bg=BG, fg=DIM, font=F_SMALL, anchor="w", justify="left", wraplength=470).pack(fill="x",
                                                                                                    pady=(4, 0))
            new_name = {"name": None}

            def picked(_e=None):
                box.selection_clear()
                if profile_var.get() == NEW_PROFILE:
                    ok, text = self.boxes._box("New profile", "A name for the new profile (it uses your settings "
                                               "as they are now):", "question", [("OK", True), ("Cancel", False)],
                                               True, False, win, entry="")
                    text = " ".join(str(text or "").split())[:40]
                    if ok and text and text != NO_LINK:
                        new_name["name"] = text
                        box.config(values=names[:-1] + [f"New: {text}", NEW_PROFILE])
                        profile_var.set(f"New: {text}")
                    else:
                        profile_var.set(NO_LINK)
            box.bind("<<ComboboxSelected>>", picked)
        tk.Label(body, text="(Settings > Recording can turn this question off.)", bg=BG, fg=DIM, font=F_SMALL,
                 anchor="w").pack(fill="x", side="bottom", pady=(8, 0))
        result = {"value": None}

        def start(_e=None):
            sel = lst.selection()
            if not sel:
                return
            target = DESKTOP if sel[0] == "desktop" else wins[int(sel[0])]
            chosen = profile_var.get()
            profile = None
            if chosen.startswith("New: "):
                profile = ("new", chosen[5:])
            elif chosen not in (NO_LINK, NEW_PROFILE):
                profile = ("existing", chosen)
            result["value"] = (target, profile)
            win.destroy()
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=20, pady=(4, 16))
        ttk.Button(bottom, text="Cancel", width=8, command=win.destroy).pack(side="right")
        ttk.Button(bottom, text="Start", width=8, style="Accent.TButton", command=start).pack(side="right",
                                                                                             padx=(0, 8))
        lst.bind("<Double-1>", start)
        win.bind("<Return>", start)
        win.bind("<Escape>", lambda e: win.destroy())
        dark_title_bar(win)
        win.update_idletasks()
        if parent is not None:
            x = parent.winfo_rootx() + max(0, (parent.winfo_width() - win.winfo_reqwidth()) // 2)
            y = parent.winfo_rooty() + max(0, (parent.winfo_height() - win.winfo_reqheight()) // 3)
        else:  # (no window of this app is showing: the middle of the screen)
            x = max(0, (win.winfo_screenwidth() - win.winfo_reqwidth()) // 2)
            y = max(0, (win.winfo_screenheight() - win.winfo_reqheight()) // 3)
        win.geometry(f"+{x}+{y}")
        win.deiconify()
        self.record_window_box = win  # (for tests)
        # it only takes over the app once it's really on screen; if Windows hasn't shown it within a
        # second, it's shown and brought forward again, and never holds the app while unseen
        for attempt in range(2):
            end = time.monotonic() + 1.0
            while win.winfo_exists() and not win.winfo_viewable() and time.monotonic() < end:
                win.update()
                time.sleep(0.02)
            if not win.winfo_exists() or win.winfo_viewable():
                break
            core.diag.info("\"Record in which window?\" wasn't on screen: shown again")
            win.transient("")
            win.deiconify()
            win.lift()
            win.attributes("-topmost", True)
        if win.winfo_exists():
            win.lift()
            try:
                win.focus_force()
            except tk.TclError:
                pass
            lst.focus_set()
            if win.winfo_viewable():
                win.grab_set()
            win.wait_window()
        self.record_window_box = None
        return result["value"]

    # ------------------------------------------------------------ the profile link, when saving

    def apply_pending_profile(self):
        """Saving a new recording that was to be linked to a profile: make it (if new) and link it."""
        pending, self.pending_profile = getattr(self, "pending_profile", None), None
        if not pending:
            return
        kind, name = pending
        if kind == "new":
            name = self.save_profile(name)
            core.diag.info(f"Made the profile \"{name}\" for a new recording")
        if name and name in self.profiles():
            self.macro_profile = name
