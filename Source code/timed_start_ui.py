"""Timed start and start-up (2.12).

- "Start playing later": at HH:MM or in X minutes (also from the phone remote's /schedule).
- Settings > General: "Open Macro Recorder when Windows starts" (a start-up entry in this Windows
  user's settings, removed again when the switch is turned off) and "When it opens": do nothing, play
  the open macro, or open the game first (like "If the game closes": open it, play the rejoin macro,
  check, try again) and then play a chosen macro.

Before any timed or start-up play: the "Timed start warning" sound, then a countdown window with a
sound each second and Cancel (Ctrl+Alt+End cancels too). It only plays once the game's window is
found, and gives up after the minutes chosen. It never wakes the PC from sleep (a sleeping PC simply
starts late, or not at all, and says so in the log). Only one copy of the app runs from start-up.
The Mac start-up entry isn't made (untested there)."""
import os
import sys
import time
import tkinter as tk
from tkinter import ttk

import macro_recorder as core
import start_later
import window_tools
from start_later import clean_hhmm, parse_when  # noqa: F401  (others import them from here)
from ui_common import *  # noqa: F401,F403

STARTUP_WHEN = {"nothing": "Do nothing", "play": "Play the open macro",
                "game": "Open the game, then play a macro"}
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_FLAG = "--startup"


def _label(path):
    return os.path.splitext(os.path.basename(path or ""))[0]


def single_copy(preview=False, name=None):
    """True when this is the only copy of the app (start-up must not open a second one). name: for tests."""
    if not IS_WIN:
        return True
    try:
        import ctypes

        name = name or "MacroRecorderOneCopy" + ("Preview" if preview else "")
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, name)
        single_copy.handle = handle  # (kept open while the app runs)
        return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return True


class TimedStartMixin:
    TIMED_HELP = (
        "Plays the open macro later: at a time (21:30) or in some minutes. First the \"Timed start warning\" "
        "sound, then a countdown you can cancel (also with Ctrl+Alt+End). It only plays once the game's window "
        "is found, and gives up after the minutes you set. The PC isn't woken from sleep for it.")
    STARTUP_HELP = (
        "Open Macro Recorder when Windows starts: the app adds itself to this Windows user's start-up list "
        "(and takes itself off again when you turn this off). When it opens it can do nothing, play the open "
        "macro, or open the game first (like \"If the game closes\": it opens the game, plays your rejoin macro, "
        "checks and tries again) and then play the macro you choose. There's always the warning sound and a "
        "countdown you can cancel first. Only one copy of the app opens. (Mac: not tried yet.)")

    # ------------------------------------------------------------ settings

    def _startup_settings(self):
        saved = self.settings.get("startup")
        saved = saved if isinstance(saved, dict) else {}
        return {"when": saved.get("when") if saved.get("when") in STARTUP_WHEN else "nothing",
                "macro": str(saved.get("macro") or ""),
                "give_up": core.int_setting(saved, "give_up", 10, 1, 240),
                "countdown": core.int_setting(saved, "countdown", 10, 3, 120)}

    def _set_startup_setting(self, **kw):
        s = dict(self._startup_settings(), **kw)
        self.settings["startup"] = s
        core.save_settings(self.settings)

    # ------------------------------------------------------------ the start-up entry (Windows)

    def _run_value_name(self):
        return "Macro Recorder Preview" if getattr(self, "preview", False) else "Macro Recorder"

    def _startup_command(self):
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}" {STARTUP_FLAG}'
        script = os.path.join(os.path.dirname(os.path.abspath(core.__file__)), "modern_ui.py")
        exe = sys.executable.replace("python.exe", "pythonw.exe")
        return f'"{exe}" "{script}" {STARTUP_FLAG}'

    def startup_enabled(self):
        if not IS_WIN:
            return False
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, self._run_value_name())
            return True
        except OSError:
            return False

    def set_startup(self, on):
        """Add or remove this app in Windows' start-up list. True when it worked."""
        if not IS_WIN:
            return False
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                if on:
                    winreg.SetValueEx(key, self._run_value_name(), 0, winreg.REG_SZ, self._startup_command())
                else:
                    try:
                        winreg.DeleteValue(key, self._run_value_name())
                    except FileNotFoundError:
                        pass
            core.diag.info("Open when Windows starts: " + ("on" if on else "off"))
            return True
        except OSError as exc:
            core.diag.error("Couldn't change the Windows start-up entry", exc)
            return False

    def startup_switched(self):
        on = bool(self.startup_var.get())
        if not self.set_startup(on):
            self.startup_var.set(self.startup_enabled())
            self.boxes.showerror("Start with Windows", "Windows didn't allow changing the start-up list.",
                                 parent=self.settings_win or self.root)

    def startup_summary(self):
        s = self._startup_settings()
        text = STARTUP_WHEN[s["when"]]
        if s["when"] == "game":
            text += f" (\"{short(_label(s['macro']), 18)}\")" if s["macro"] else " (no macro chosen yet)"
        return text

    def open_startup_when(self):
        s = self._startup_settings()
        parent = self.settings_win if self.settings_win is not None else self.root
        win = tk.Toplevel(parent, bg=BG)
        win.title("When it opens")
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
        when_var = tk.StringVar(value=STARTUP_WHEN[s["when"]])
        ttk.Combobox(row("When Macro Recorder opens at start-up"), textvariable=when_var, state="readonly",
                     width=30, values=list(STARTUP_WHEN.values())).pack(side="right")
        macros = {_label(p): p for p in self._saved_macro_paths()}
        if s["macro"]:
            macros.setdefault(_label(s["macro"]), s["macro"])
        macro_var = tk.StringVar(value=_label(s["macro"]) or (next(iter(macros), "")))
        ttk.Combobox(row("The macro to play", "for \"Open the game, then play a macro\""), textvariable=macro_var,
                     state="readonly", width=22, values=list(macros)).pack(side="right")
        tk.Label(body, text="Opening the game uses Settings > Playback > \"If the game closes\": what to open "
                            "and your rejoin macro.", bg=BG, fg=DIM, font=F_SMALL, anchor="w", justify="left",
                 wraplength=460).pack(fill="x", pady=(4, 0))

        def save():
            when = next(k for k, v in STARTUP_WHEN.items() if v == when_var.get())
            if when == "game":
                closed = self._closed_settings()
                if not macros.get(macro_var.get()):
                    self.boxes.showinfo("When it opens", "Choose the macro to play.", parent=win)
                    return
                if not closed["open"] and not closed["macro"]:
                    self.boxes.showinfo("When it opens", "First fill in Settings > Playback > \"If the game "
                                        "closes\" > Change…: what to open, and your rejoin macro.", parent=win)
                    return
            self._set_startup_setting(when=when, macro=macros.get(macro_var.get(), ""))
            win.destroy()
            self._refresh_choice_rows()
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(0, 14))
        ttk.Button(bottom, text="Save", style="Accent.TButton", width=8, command=save).pack(side="right")
        ttk.Button(bottom, text="Cancel", width=8, command=win.destroy).pack(side="right", padx=6)
        dark_title_bar(win)
        win.save, win.vars = save, {"when": when_var, "macro": macro_var}
        return win

    def _refresh_choice_rows(self):
        for var, summary in getattr(self, "choice_rows", []):
            try:
                var.set(short(summary(), 46))
            except tk.TclError:
                pass

    # ------------------------------------------------------------ a planned start

    def timed_summary(self):
        bits = []
        plan = getattr(self, "timed_plan", None)
        if plan and plan.get("why") not in ("alarm", "timer"):
            bits.append("Plays at " + time.strftime("%H:%M", time.localtime(plan["at"])))
        sc = self._schedule()
        if sc["alarm_on"]:
            bits.append(f"Alarm {sc['alarm']}" + (" every day" if sc["daily"] else ""))
        if sc["timer_on"]:
            left = max(0, int((sc["timer_from"] + sc["timer_min"] * 60 - time.time()) // 60))
            bits.append((f"Timer every {sc['timer_min']} min" if sc["timer_repeat"] else f"Timer {sc['timer_min']} min")
                        + f" ({left} min left)")
        if bits and sc["when"] == "game":
            bits.append("opens the game first")
        return " · ".join(bits) if bits else "Not planned"

    # ------------------------------------------------------------ (2.12) the alarm and the timer

    SCHEDULE_DEFAULTS = start_later.SCHEDULE_DEFAULTS
    TIMER_REPEAT_MIN = start_later.TIMER_REPEAT_MIN

    def _schedule(self):
        """Settings > Playback > Start playing later (the rules: start_later.clean_schedule)."""
        return start_later.clean_schedule(self.settings.get("schedule"))

    def _set_schedule(self, **kw):
        sc = dict(self._schedule(), **kw)
        self.settings["schedule"] = sc
        core.save_settings(self.settings)
        self._refresh_choice_rows()
        return sc

    def schedule_start(self):
        """When the app opens: a timer that ran out while it was closed is started again (or turned off),
        then the alarm and the timer are looked at every few seconds."""
        changes, ran_out = start_later.on_open(self._schedule(), time.time())
        if ran_out:
            core.diag.info("Timer: it ran out while the app was closed")
        if changes:
            self._set_schedule(**changes)
        self._schedule_tick()

    def _schedule_due(self, now=None):
        """Which of the alarm and the timer is due now: (alarm, timer)."""
        now = now or time.time()
        alarm, timer, clock_back = start_later.due(self._schedule(), now)
        if clock_back:
            core.diag.info("Timer: the PC clock went back; the timer counts from now")
            self._set_schedule(timer_from=now)
        return alarm, timer

    def _schedule_tick(self):
        job = getattr(self, "schedule_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self.schedule_job = None
        try:
            self._schedule_check()
        except Exception as exc:
            core.diag.error("The alarm / timer check failed", exc)
        self.schedule_job = self.root.after(5000, self._schedule_tick)

    def _schedule_check(self, now=None):
        now = now or time.time()
        alarm, timer = self._schedule_due(now)
        if not (alarm or timer):
            return None
        sc = self._schedule()
        alarm, timer, changes = start_later.one_start(sc, alarm, timer, now)
        self._set_schedule(**changes)
        why = "alarm" if alarm else "timer"
        core.diag.info(f"{'Alarm' if alarm else 'Timer'}: time to play" + (" (the alarm and the timer together)"
                                                                         if alarm and timer else ""))
        if not (self.events or self.actions):
            core.diag.info("Alarm / timer: no macro is open to play")
            return why
        if getattr(self, "timed_plan", None) and self.timed_plan.get("phase"):
            return why  # (a start is already on its way)
        self.plan_timed_start(now, why, open_game=sc["when"] == "game", open=sc["open"], rejoin=sc["macro"])
        return why

    def plan_timed_start(self, at, why="timed", **extra):
        """Play the open macro at `at` (seconds since 1970). why: "timed", "startup" or "remote"."""
        self.timed_plan = dict({"at": float(at), "why": why}, **extra)
        core.diag.info(f"Timed start planned for {time.strftime('%H:%M:%S', time.localtime(at))} ({why})")
        self._refresh_choice_rows()
        self._timed_tick()
        return self.timed_plan

    def cancel_timed_start(self, why="cancelled"):
        had = bool(getattr(self, "timed_plan", None)) or bool(getattr(self, "timed_box", None)) \
            or bool(getattr(self, "restart_after_run", None))
        self.timed_plan = None
        self.restart_after_run = None  # (also the wait for a playing run's end)
        box, self.timed_box = getattr(self, "timed_box", None), None
        if box is not None:
            try:
                box.destroy()
            except tk.TclError:
                pass
        if had:
            core.diag.info(f"Timed start {why}")
        self._refresh_choice_rows()
        return had

    def _timed_tick(self):
        job = getattr(self, "timed_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self.timed_job = None
        plan = getattr(self, "timed_plan", None)
        if not plan or plan.get("phase"):
            return
        if time.time() >= plan["at"]:
            self._timed_countdown(plan)
            return
        self.timed_job = self.root.after(1000, self._timed_tick)

    def _timed_countdown(self, plan):
        """The warning sound, then the countdown window (Cancel, or Ctrl+Alt+End)."""
        if self.recording or self.record_countdown_left > 0:
            core.diag.info("Timed start skipped: the app was recording")
            self.timed_plan = None
            return
        if self.playing:  # (2.12: never cut a run: wait for it to end, then start again)
            if getattr(self, "restart_after_run", None) is not plan:
                core.diag.info("Timed start: waiting for the run that's playing to end, then it starts again")
            self.restart_after_run = plan
            return
        plan["phase"] = "countdown"
        self._sound("timed_warning")
        seconds = self._startup_settings()["countdown"]
        parent = self.root if self.root.winfo_viewable() else None
        win = self.timed_box = tk.Toplevel(parent or self.root, bg=BG)
        win.title("Starting soon")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        what = short(self.name_var.get().strip() or _label(plan.get("macro")) or "the macro", 30)
        tk.Label(win, text=f"\"{what}\" starts playing in", bg=BG, fg=TEXT, font=F_BOLD).pack(padx=24, pady=(16, 0))
        left_var = tk.StringVar(value=str(seconds))
        tk.Label(win, textvariable=left_var, bg=BG, fg=AMBER, font=(FAMILY, 28, "bold")).pack()
        tk.Label(win, text="Cancel, or Ctrl+Alt+End, stops it.", bg=BG, fg=MUTED, font=F_SMALL).pack(padx=24)
        ttk.Button(win, text="Cancel", command=lambda: self.cancel_timed_start("cancelled in the countdown")).pack(
            pady=(8, 16))
        dark_title_bar(win)
        win.update_idletasks()
        win.geometry(f"+{(win.winfo_screenwidth() - win.winfo_reqwidth()) // 2}+120")
        state = {"left": seconds}

        def tick():
            if getattr(self, "timed_plan", None) is not plan or not win.winfo_exists():
                return
            state["left"] -= 1
            if state["left"] <= 0:
                self.timed_box = None
                win.destroy()
                plan["phase"] = "waiting"
                plan["give_up_at"] = time.time() + self._startup_settings()["give_up"] * 60
                self._timed_go(plan)
                return
            left_var.set(str(state["left"]))
            self._sound("timed_countdown")
            win.after(1000, tick)
        self._sound("timed_countdown")
        win.after(1000, tick)

    def _timed_game_exe(self):
        return (self.macro_program or {}).get("exe") or self.settings.get("last_game_exe")

    def _timed_go(self, plan):
        """After the countdown: play once the game's window is there (or give up after a while)."""
        if getattr(self, "timed_plan", None) is not plan:
            return
        if plan.get("open_game"):  # (open the game first, like "If the game closes")
            self.timed_plan = None
            self.start_rejoin_first = True
            self.start_rejoin_opts = {"open": plan.get("open") or "", "macro": plan.get("rejoin") or ""} \
                if (plan.get("open") or plan.get("rejoin")) else None
            note = self._remote_start("start-up")
            core.diag.info("Start-up: " + str(note))
            if not self.playing:
                self.start_rejoin_first = False
            return
        exe = self._timed_game_exe()
        if exe and IS_WIN and not window_tools.windows_of(exe):
            if time.time() >= plan["give_up_at"]:
                self.timed_plan = None
                text = (f"Timed start gave up: the game ({os.path.splitext(exe)[0]}) didn't open within "
                        f"{self._startup_settings()['give_up']} min.")
                core.diag.info(text)
                self.sub_note = short(text, 60)
                self._refresh()
                return
            if not plan.get("told"):
                plan["told"] = True
                core.diag.info(f"Timed start: waiting for the game ({os.path.splitext(exe)[0]}) to open")
            self.timed_job = self.root.after(3000, lambda: self._timed_go(plan))
            return
        self.timed_plan = None
        note = self._remote_start("a timed start")
        core.diag.info("Timed start: " + str(note))
        if self.playing:
            self.sub_note = "Started by the timed start"
            self._refresh()
        self._refresh_choice_rows()

    def startup_action(self):
        """Started by Windows at start-up: do what "When it opens" says (always with the countdown)."""
        s = self._startup_settings()
        core.diag.info(f"Opened at Windows start-up: {STARTUP_WHEN[s['when']].lower()}")
        if s["when"] == "nothing":
            return
        if s["when"] == "game":
            if not s["macro"] or not self._find_macro_file(s["macro"]):
                core.diag.info("Start-up: the macro to play isn't there any more")
                return
            if not self.load(self._find_macro_file(s["macro"]), quiet=True):
                return
            self.plan_timed_start(time.time(), "startup", open_game=True, macro=s["macro"])
            return
        if not (self.events or self.actions):
            core.diag.info("Start-up: no macro is open to play")
            return
        self.plan_timed_start(time.time(), "startup")

    def emergency_stop(self):
        self.cancel_timed_start("cancelled with Ctrl+Alt+End")
        super().emergency_stop()

    # ------------------------------------------------------------ the "Start playing later" window

    def open_timed_start(self):
        sc = self._schedule()
        parent = self.settings_win if self.settings_win is not None and self.settings_win.winfo_viewable() \
            else self.root
        win = tk.Toplevel(parent, bg=BG)
        win.title("Start playing later")
        win.transient(parent)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=18, pady=14)
        tk.Label(body, text="Play the open macro later", bg=BG, fg=TEXT, font=F_BOLD, anchor="w").pack(fill="x")
        tk.Label(body, text="Tick the alarm, the timer, or both. Both are remembered, also after the app is closed.",
                 bg=BG, fg=MUTED, font=F_SMALL, anchor="w").pack(fill="x", pady=(2, 8))

        def line():
            r = tk.Frame(body, bg=BG)
            r.pack(fill="x", pady=4)
            return r
        h0, m0 = sc["alarm"].split(":")
        alarm_on = tk.BooleanVar(value=sc["alarm_on"])
        hour_var, min_var = tk.StringVar(value=h0), tk.StringVar(value=m0)
        daily = tk.BooleanVar(value=sc["daily"])
        r = line()
        ttk.Checkbutton(r, text="Alarm at", variable=alarm_on).pack(side="left")
        # (2.12) HH : MM with the ":" always there (jumps to the minutes after two hour digits)
        TimeBox(r, hh_var=hour_var, mm_var=min_var).pack(side="left", padx=(8, 12))
        ttk.Checkbutton(r, text="Every day", variable=daily).pack(side="left")
        timer_on = tk.BooleanVar(value=sc["timer_on"])
        timer_var = tk.StringVar(value=str(sc["timer_min"]))
        repeat = tk.BooleanVar(value=sc["timer_repeat"])
        r = line()
        ttk.Checkbutton(r, text="Timer:", variable=timer_on).pack(side="left")
        ttk.Spinbox(r, from_=1, to=1440, width=5, textvariable=timer_var).pack(side="left", padx=(8, 4))
        tk.Label(r, text="minutes", bg=BG, fg=TEXT, font=F_BASE).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(r, text="Again every time (at least 5 min)", variable=repeat).pack(side="left")
        tk.Label(body, text="WHEN IT STARTS", bg=BG, fg=MUTED, font=F_SECTION, anchor="w").pack(fill="x", pady=(12, 2))
        when = tk.StringVar(value=sc["when"])
        ttk.Radiobutton(body, text="Play the open macro", value="play", variable=when).pack(anchor="w")
        ttk.Radiobutton(body, text="Open the game first, join with the rejoin macro, then play the open macro",
                        value="game", variable=when).pack(anchor="w")
        closed = self._closed_settings()
        open_var = tk.StringVar(value=sc["open"] or closed["open"])
        r = line()
        tk.Label(r, text="Open this", bg=BG, fg=TEXT, font=F_BASE).pack(side="left", padx=(22, 0))
        tk.Label(r, text="the game's link, or a file", bg=BG, fg=DIM, font=F_SMALL).pack(side="left", padx=(8, 0))
        ttk.Button(r, text="File…", command=lambda: pick_open()).pack(side="right")
        tk.Entry(r, textvariable=open_var, width=30, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat",
                 insertbackground=TEXT, highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side="right", padx=(0, 6), ipady=3)

        def pick_open():
            from tkinter import filedialog

            path = filedialog.askopenfilename(parent=win)
            if path:
                open_var.set(path)
        macros = {_label(p): p for p in self._saved_macro_paths()}
        rejoin = sc["macro"] or closed["macro"]
        if rejoin:
            macros.setdefault(_label(rejoin), rejoin)
        macros = dict({"(none)": ""}, **macros)
        macro_var = tk.StringVar(value=_label(rejoin) or "(none)")
        r = line()
        tk.Label(r, text="Rejoin macro", bg=BG, fg=TEXT, font=F_BASE).pack(side="left", padx=(22, 0))
        tk.Label(r, text="played once the game is open", bg=BG, fg=DIM, font=F_SMALL).pack(side="left", padx=(8, 0))
        box = ttk.Combobox(r, textvariable=macro_var, state="readonly", width=22, values=list(macros))
        box.pack(side="right")
        s0 = self._startup_settings()
        count_var = tk.StringVar(value=str(s0["countdown"]))
        give_var = tk.StringVar(value=str(s0["give_up"]))
        for text, var in (("Countdown before it plays (seconds)", count_var),
                          ("Give up if the game isn't open after (minutes)", give_var)):
            r = line()
            tk.Label(r, text=text, bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
            tk.Entry(r, textvariable=var, width=6, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat",
                     insertbackground=TEXT, highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=ACCENT).pack(side="right", ipady=3)
        tk.Label(body, text="If a macro is playing then, it waits for that run to end and starts again. There's "
                            "always the warning sound and a countdown you can cancel (also Ctrl+Alt+End).",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w", justify="left", wraplength=500).pack(fill="x", pady=(8, 0))
        status = tk.StringVar(value=self.timed_summary())
        tk.Label(body, textvariable=status, bg=BG, fg=ACCENT, font=F_BASE, anchor="w", wraplength=500,
                 justify="left").pack(fill="x", pady=(8, 0))

        def whole(var, default, low, high):
            try:
                return max(low, min(high, int(float(var.get().strip()))))
            except ValueError:
                return default

        def save():
            if alarm_on.get() and not (hour_var.get().strip() and min_var.get().strip()):
                self.boxes.showinfo("Start playing later", "Write the alarm's time: the hours, then the minutes "
                                    "(like 07 : 30).", parent=win)
                return False
            alarm = f"{whole(hour_var, 7, 0, 23):02d}:{whole(min_var, 0, 0, 59):02d}"
            minutes = whole(timer_var, 30, 1, 1440)
            if repeat.get():
                minutes = max(self.TIMER_REPEAT_MIN, minutes)
            if when.get() == "game" and not open_var.get().strip() and not macros.get(macro_var.get()):
                self.boxes.showinfo("Start playing later", "Fill in what to open, or choose a rejoin macro that "
                                    "opens the game itself.", parent=win)
                return False
            old = self._schedule()
            timer_from = old["timer_from"]
            if timer_on.get() and (not old["timer_on"] or minutes != old["timer_min"] or not timer_from):
                timer_from = time.time()  # (the timer starts counting now)
            alarm_last = old["alarm_last"] if (alarm == old["alarm"] and old["alarm_on"]) else ""
            self._set_schedule(alarm_on=bool(alarm_on.get()), alarm=alarm, daily=bool(daily.get()),
                               timer_on=bool(timer_on.get()), timer_min=minutes, timer_repeat=bool(repeat.get()),
                               timer_from=timer_from, when=when.get(), open=open_var.get().strip(),
                               macro=macros.get(macro_var.get(), ""), alarm_last=alarm_last)
            self._set_startup_setting(countdown=whole(count_var, 10, 3, 120), give_up=whole(give_var, 10, 1, 240))
            core.diag.info("Start playing later: " + self.timed_summary())
            status.set(self.timed_summary())
            return True
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(0, 14))
        ttk.Button(bottom, text="Close", width=8, command=win.destroy).pack(side="right")
        ttk.Button(bottom, text="Save", style="Accent.TButton", width=8, command=save).pack(side="right", padx=6)
        dark_title_bar(win)
        win.save, win.vars = save, {"alarm_on": alarm_on, "hour": hour_var, "minute": min_var, "daily": daily,
                                    "timer_on": timer_on, "timer": timer_var, "repeat": repeat, "when": when,
                                    "open": open_var, "macro": macro_var, "countdown": count_var, "give_up": give_var}
        return win
