"""Settings > Playback > "If a run gets stuck" (2.12): the stuck run guard's switch and its window.

When neither MISSION COMPLETED nor MISSION FAILED shows for some minutes (about 3 runs, from Run stats),
playback starts the run over, or plays a macro you pick first (to get unstuck), or only tells Discord.
If it stays stuck, each new try waits longer, and after the last try the macro stops and Discord is
told. The logic itself is in macro_recorder.py (_stuck_watcher)."""
import tkinter as tk
from tkinter import filedialog, ttk

import macro_recorder as core
from ui_common import *  # noqa: F401,F403

STUCK_CHOICES = {"restart": "Start the run over", "macro": "Play a macro, then start over",
                 "ping": "Only tell me on Discord"}


def _label(path):
    import os

    return os.path.splitext(os.path.basename(path or ""))[0]


class StuckMixin:
    STUCK_HELP = (
        "Sometimes a run gets stuck: the character is caught somewhere, a menu stays open, and neither "
        "MISSION COMPLETED nor MISSION FAILED ever shows. This watches for that.\n\n"
        "When neither result has shown for the minutes you set, it does what you choose: start the run "
        "over, play a macro of yours first (for example one that walks out of a corner or rejoins), or "
        "only tell you on Discord. If it's still stuck, it tries again after a longer wait each time, and "
        "after the last try it stops the macro and tells Discord.\n\n"
        "The minutes don't count while paused, while the game isn't in front, while getting back after a "
        "disconnect or a game close, or in test plays. It needs Results (MISSION COMPLETED / FAILED) on. "
        "Everything it does is written to the log.")

    def stuck_summary(self):
        opts = self._stuck_settings()
        if not opts["on"]:
            return "Off"
        minutes = opts["minutes"] or self.stuck_minutes_suggested()
        text = f"After {minutes} min: " + STUCK_CHOICES[opts["action"]].lower()
        if opts["action"] == "macro" and opts["macro"]:
            text += f" (\"{short(_label(opts['macro']), 18)}\")"
        return text

    def stuck_switched(self):
        saved = self.settings.get("stuck_guard")
        saved = dict(saved) if isinstance(saved, dict) else {}
        saved["on"] = bool(self.stuck_on_var.get())
        self.settings["stuck_guard"] = saved
        self._save_settings()
        self._show_stuck_choice()

    LOOKED_FOR = (("completed", "MISSION COMPLETED"), ("failed", "MISSION FAILED"), ("retry", "RETRY"))

    def stuck_looks_for(self):
        """(text, all fine): what the guard looks for, and whether each built-in picture is on."""
        results_on = self.settings.get("results_enabled", True)
        try:
            watch_on = bool(self.watch_var.get())
        except Exception:
            watch_on = True
        bits, off = [], []
        for key, title in self.LOOKED_FOR:
            pics = self.watch_pictures if key == "retry" else self.result_pictures
            p = next((x for x in pics if x.get("builtin") == key), None)
            on = p is not None and self._picture_active(p) and (watch_on if key == "retry" else results_on)
            bits.append(f"{title} {'✓' if on else '✗'}")
            if not on:
                off.append(title + (" is missing" if p is None else " is off"))
        own = [p.get("name") or "a picture" for p in self.result_pictures
               if not p.get("builtin") and self._picture_active(p) and results_on]
        text = "Looks for: " + ", ".join(bits) + " (built-in pictures in Picture watch > AOT:R)"
        if own:
            text += ". Also your own: " + ", ".join(short(n, 20) for n in own[:4])
        if off:
            text += ". " + "; ".join(off) + ": the guard can't see it."
        return text, not off

    def _show_stuck_choice(self):
        if getattr(self, "stuck_var", None) is not None:
            self.stuck_var.set(self.stuck_summary())
        if getattr(self, "stuck_on_var", None) is not None:
            self.stuck_on_var.set(self._stuck_settings()["on"])
        label = getattr(self, "stuck_looks_label", None)
        if label is not None:
            try:
                text, ok = self.stuck_looks_for()
                label.config(text=text, fg=DIM if ok else AMBER)
            except tk.TclError:
                pass

    def open_stuck(self):
        opts = self._stuck_settings()
        parent = self.settings_win if self.settings_win is not None else self.root
        win = tk.Toplevel(parent, bg=BG)
        win.title("If a run gets stuck")
        win.transient(parent)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=18, pady=14)

        def row(text, tip=None):
            f = tk.Frame(body, bg=BG)
            f.pack(fill="x", pady=4)
            tk.Label(f, text=text, bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
            if tip:
                tk.Label(f, text=tip, bg=BG, fg=DIM, font=F_SMALL).pack(side="left", padx=(8, 0))
            return f

        suggested = self.stuck_minutes_suggested()
        r = row("No MISSION COMPLETED / FAILED for", f"minutes (suggested: {suggested}, about 3 runs)")
        link(r, "ⓘ", lambda: self.boxes.showinfo("If a run gets stuck", self.STUCK_HELP, parent=win), bg=BG).pack(
            side="left", padx=(6, 0))
        minutes_var = tk.StringVar(value=str(opts["minutes"] or suggested))
        tk.Entry(r, textvariable=minutes_var, width=6, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat",
                 insertbackground=TEXT, highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side="right", ipady=3)
        action_var = tk.StringVar(value=STUCK_CHOICES[opts["action"]])
        r = row("Then")
        ttk.Combobox(r, textvariable=action_var, state="readonly", width=28,
                     values=list(STUCK_CHOICES.values())).pack(side="right")
        macros = {_label(p): p for p in self._saved_macro_paths()}
        if opts["macro"]:
            macros.setdefault(_label(opts["macro"]), opts["macro"])
        macros = dict({"(none)": ""}, **macros)
        macro_var = tk.StringVar(value=_label(opts["macro"]) or "(none)")
        r = row("The macro to play", "to get unstuck (or to rejoin)")
        ttk.Button(r, text="A macro file…", command=lambda: pick()).pack(side="right")
        macro_box = ttk.Combobox(r, textvariable=macro_var, state="readonly", width=22, values=list(macros))
        macro_box.pack(side="right", padx=(0, 6))

        def pick():
            path = filedialog.askopenfilename(parent=win, filetypes=core.OPEN_FILE_TYPES)
            if path:
                macros[_label(path)] = path
                macro_box.config(values=list(macros))
                macro_var.set(_label(path))

        tries_var = tk.StringVar(value=str(opts["tries"]))
        r = row("How many tries", "each one waits longer; then it stops")
        tk.Entry(r, textvariable=tries_var, width=6, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat",
                 insertbackground=TEXT, highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side="right", ipady=3)
        if not self.settings.get("results_enabled", True):
            tk.Label(body, text="Results (MISSION COMPLETED / FAILED) are off in Settings > Results: this only "
                                "works when they're on.", bg=BG, fg=AMBER, font=F_SMALL, anchor="w", justify="left",
                     wraplength=480).pack(fill="x", pady=(6, 0))

        def whole(var, default, low, high):
            try:
                return max(low, min(high, int(float(var.get().strip()))))
            except ValueError:
                return default

        def save():
            action = next(k for k, v in STUCK_CHOICES.items() if v == action_var.get())
            macro = macros.get(macro_var.get(), "")
            if action == "macro" and not macro:
                self.boxes.showinfo("If a run gets stuck", "Choose the macro to play first.", parent=win)
                return
            minutes = whole(minutes_var, suggested, 1, 600)
            self.settings["stuck_guard"] = {"on": opts["on"], "minutes": 0 if minutes == suggested else minutes,
                                            "action": action, "macro": macro,
                                            "tries": whole(tries_var, 3, 1, 20)}
            win.destroy()
            self._save_settings()
            self._show_stuck_choice()

        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(0, 14))
        ttk.Button(bottom, text="Save", style="Accent.TButton", width=8, command=save).pack(side="right")
        ttk.Button(bottom, text="Cancel", width=8, command=win.destroy).pack(side="right", padx=6)
        dark_title_bar(win)
        win.focus_force()
        win.save, win.vars = save, {"minutes": minutes_var, "action": action_var, "macro": macro_var,
                                    "tries": tries_var, "macros": macros}
        return win
