"""Check my macro (2.10): before a macro plays (and from "Check" in the main window), look for things
that would make it go wrong: a macro that a "Play another macro" step plays is gone, a picture is
missing, a picture's rejoin macro is gone (sure problems), or the game isn't open or the screen is very
different from the one it was recorded on (maybe problems).

Nothing here ever stops Play: problems show as a line in the main window ("See…" lists them) and in the
log. Each warning can be turned off for one macro ("Don't warn me again for this macro"); the Check
window shows those too, with "Warn me again"."""
import os
import tkinter as tk
from tkinter import ttk

import macro_checks
import macro_recorder as core
import macro_versions
import window_tools
from macro_checks import MAYBE, SURE, screen_far_off  # noqa: F401  (tests use check_ui.SURE / screen_far_off)
from macro_checks import macro_name as _name
from ui_common import *  # noqa: F401,F403


class CheckMixin:
    # ------------------------------------------------------------ finding problems

    def check_macro(self, play_on=None):
        """The problems of the open macro: [{"id", "level" (SURE/MAYBE), "text"}] (plain words)."""
        problems = []
        seen = set()

        def add(pid, level, text):
            if pid not in seen:
                seen.add(pid)
                problems.append({"id": pid, "level": level, "text": text})

        try:
            steps = self.macro_steps() if (self.events or self.actions) else []
        except Exception:
            steps = []
        for problem in macro_checks.step_problems(
                steps, self._find_macro_file, lambda found: self._read_macro_file(found)["steps"],
                window_tools.windows_of if window_tools.IS_WIN else None, core.MAX_MACRO_DEPTH):
            add(*problem)
        # Picture watch: the pictures on for this macro, and the macros they play
        for n, pic in enumerate(self._active_watch_pictures(), start=1):
            path = getattr(pic, "path", None)
            pname = core.watch_name(pic, n)
            if path and not os.path.isfile(path):
                add(f"watchpic:{pic.get('file')}", SURE,
                    f"The picture file of {pname} (Picture watch) is gone, so it can't be looked for.")
            macro = pic.get("macro")
            if pic.get("action", "restart") in core.WATCH_NEED_MACRO and macro \
                    and not self._find_macro_file(macro):
                what = "rejoin macro" if pic.get("action") == "recover" else "macro"
                add(f"watchmacro:{pic.get('file')}:{_name(macro).lower()}", SURE,
                    f"The {what} of {pname} (Picture watch), \"{_name(macro)}\", isn't there any more. "
                    "The picture will do nothing else when it shows.")
        closed = self._closed_settings()
        if closed["action"] == "reopen" and closed["macro"] and not self._find_macro_file(closed["macro"]):
            add(f"closedmacro:{_name(closed['macro']).lower()}", SURE,
                f"The rejoin macro of \"If the game closes\" (Settings > Playback), \"{_name(closed['macro'])}\", "
                "isn't there any more. Only the game is opened again.")
        # maybe problems
        if closed["action"] == "reopen" and window_tools.IS_WIN:
            _target, gone_note = self._game_open_target(closed)
            if gone_note:
                add("closedopen", MAYBE, gone_note + ". Choose the game file again in Settings > Playback > "
                                         "If the game closes > Change…")
        exe = (self.macro_program or {}).get("exe")
        if not exe and window_tools.IS_WIN and self.events \
                and (self.switch_prog_var.get() or self.settings.get("pause_when_away", True)):
            add("nogame", MAYBE, "This macro doesn't know which program it belongs to, so Play can't switch to the game, "
                                 "and \"Pause when the macro's window isn't in front\" watches whichever window is in "
                                 "front. Pick the game in Edit (Game window > Change…). Try Show without playing "
                                 "first: clicks may land differently.")
        if exe and window_tools.IS_WIN and not window_tools.windows_of(exe):
            add("game", MAYBE, f"This macro was recorded in {self._program_name()} ({exe}), which doesn't "
                               "seem to be open.")
        if play_on and self.macro_screen and not self._fits_game_window() \
                and screen_far_off(self.macro_screen, play_on):
            (w1, h1), (w2, h2) = self.macro_screen, play_on
            add("screen", MAYBE, f"This macro was recorded on a {w1}x{h1} screen and this one is {w2}x{h2}. "
                                 "Clicks may land in the wrong places.")
        return problems

    def _fits_game_window(self):
        """Clicks are fitted to the game's window (then the screen's size doesn't matter)."""
        if self.settings.get("fit_to", "window") != "window":
            return False
        src = (self.macro_program or {}).get("client")
        try:
            return bool(src and len(src) == 4 and self._game_client_rect())
        except Exception:
            return False

    # ------------------------------------------------------------ "Don't warn me again"

    def _check_key(self):
        return macro_versions._key(self.current_file) if self.current_file else ""

    def check_ignored(self, key=None):
        return macro_checks.ignored(self.settings.get("check_ignore"), key if key is not None else self._check_key())

    def set_check_ignored(self, pid, ignore, key=None):
        key = key if key is not None else self._check_key()
        if not key:
            return
        store = self.settings.get("check_ignore")
        if not isinstance(store, dict):
            store = self.settings["check_ignore"] = {}
        macro_checks.set_ignored(store, key, pid, ignore)
        core.save_settings(self.settings)

    def rename_check_ignored(self, old_key, new_key):
        """A macro renamed in the app keeps its turned-off warnings."""
        macro_checks.rename_ignored(self.settings.get("check_ignore"), old_key, new_key)

    # ------------------------------------------------------------ on Play

    def check_on_play(self, play_on, skip=()):
        """Called as Play starts: tells about problems that weren't turned off. Never stops Play."""
        try:
            problems = [p for p in self.check_macro(play_on) if p["id"] not in skip]
        except Exception as exc:
            core.diag.error("Couldn't check the macro", exc)
            return []
        ignored = self.check_ignored()
        shown = [p for p in problems if p["id"] not in ignored]
        for p in shown:
            core.diag.info(f"Check my macro ({p['level']}): {p['text']}")
        self.check_problems = shown
        if shown:
            n = len(shown)
            sure = any(p["level"] == SURE for p in shown)
            self.show_check_notice(f"⚠ {n} thing{'s' if n != 1 else ''} to check in this macro"
                                   + ("" if sure else " (maybe)"))
        elif getattr(self, "check_notice_see", None) is not None and self.check_notice_see.cget("text"):
            self.show_check_notice(None)  # (the last notice was about something that's fixed now)
        return shown

    def show_check_notice(self, text):
        """Uses the always-there line under Saved macros (the window keeps its size)."""
        if getattr(self, "profile_notice_row", None) is None:
            return
        self.show_profile_notice(text)
        self.check_notice_see.config(text="See…" if text else "")

    # ------------------------------------------------------------ the Check window

    def open_check(self):
        old = getattr(self, "check_win", None)
        if old is not None and old.winfo_exists():
            old.destroy()
        win = self.check_win = tk.Toplevel(self.root, bg=BG)
        win.title("Check my macro")
        win.transient(self.root)
        win.resizable(False, False)
        dark_title_bar(win)
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=18, pady=14)
        self._fill_check(win, body)
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(0, 14))
        ttk.Button(bottom, text="Close", command=win.destroy).pack(side="right")
        ttk.Button(bottom, text="Check again", command=lambda: self._fill_check(win, body)).pack(side="right",
                                                                                                padx=(0, 6))
        return win

    def _fill_check(self, win, body):
        for w in body.winfo_children():
            w.destroy()
        name = self.name_var.get().strip() or "this macro"
        tk.Label(body, text=f"Check: {short(name, 40)}", bg=BG, fg=TEXT, font=F_BOLD, anchor="w").pack(fill="x")
        tk.Label(body, text="Nothing here stops Play. It's only a heads-up.", bg=BG, fg=DIM, font=F_SMALL,
                 anchor="w").pack(fill="x", pady=(0, 8))
        if not (self.events or self.actions):
            tk.Label(body, text="No macro is open.", bg=BG, fg=MUTED, font=F_BASE, anchor="w").pack(fill="x")
            return
        try:
            play_on = self._read_play_on(quiet=True)
        except Exception:
            play_on = None
        problems = self.check_macro(play_on)
        ignored = self.check_ignored()
        if not problems:
            tk.Label(body, text="✓ Nothing found. The macro looks ready to play.", bg=BG, fg=GREEN,
                     font=F_BASE, anchor="w").pack(fill="x")
        for p in problems:
            off = p["id"] in ignored
            row = tk.Frame(body, bg=BG)
            row.pack(fill="x", pady=(0, 8))
            color = DIM if off else (RED if p["level"] == SURE else AMBER)
            word = "Problem" if p["level"] == SURE else "Maybe a problem"
            tk.Label(row, text=f"● {word}" + ("  (warning turned off)" if off else ""), bg=BG, fg=color,
                     font=F_SMALL, anchor="w").pack(fill="x")
            tk.Label(row, text=p["text"], bg=BG, fg=MUTED if off else TEXT, font=F_BASE, anchor="w",
                     justify="left", wraplength=440).pack(fill="x")
            if p["id"] in ("game", "nogame") and IS_WIN:  # (Preview 4: Edit can pick another window for the macro)
                link(row, "Pick another window in Edit (Game window > Change…)",
                     lambda: (win.destroy(), self.open_editor()), bg=BG).pack(anchor="w")
            if self.current_file:
                link(row, "Warn me again" if off else "Don't warn me again for this macro",
                     lambda pid=p["id"], o=off: (self.set_check_ignored(pid, not o), self._fill_check(win, body)),
                     bg=BG).pack(anchor="w")
