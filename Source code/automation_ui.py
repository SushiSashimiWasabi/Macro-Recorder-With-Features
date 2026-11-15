"""Stop by itself, small random timing, the Discord daily / weekly summary and the Stats window.

Each of the first three is one line in Settings (what's chosen now, and Change…) that opens a
small window; the choice is kept as one settings entry ("auto_stop", "vary", "discord_summary")."""
import time
import tkinter as tk
from tkinter import ttk

import macro_recorder as core
import run_history
import stats
from ui_common import *  # noqa: F401,F403

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
VARY_MODES = {"usual": "The usual setting (above)", "off": "Never for this macro", "own": "Its own amounts"}
PERIODS = {"today": "Today", "7": "Last 7 days", "30": "Last 30 days", "all": "Everything kept"}


def clock_text(seconds):
    return "-" if seconds is None else stats.duration_text(seconds)


CHOICE_WORDS = 44  # (letters) a Settings row's summary next to Change… is cut short after this

class AutomationMixin:
    # ------------------------------------------------------------ a small window of options

    def _form_window(self, title, fields, values, on_save, intro=None):
        """A small window with one row per field and Save / Cancel.
        fields: (key, label, grey words, kind, extra); kind is "switch", "int", "float", "text",
        "choice" (extra = {stored: shown}) or "head" (a section title). on_save(new values)."""
        parent = self.settings_win if self.settings_win is not None else self.root
        win = tk.Toplevel(parent, bg=BG)
        win.title(title)
        win.transient(parent)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=18, pady=14)
        if intro:
            tk.Label(body, text=intro, bg=BG, fg=MUTED, font=F_SMALL, anchor="w", justify="left",
                     wraplength=480).pack(fill="x", pady=(0, 8))
        variables = {}
        for key, label, tip, kind, extra in fields:
            if kind == "head":
                tk.Label(body, text=label, bg=BG, fg=MUTED, font=F_SECTION, anchor="w").pack(fill="x", pady=(10, 2))
                continue
            row = tk.Frame(body, bg=BG)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label, bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
            if tip:
                tk.Label(row, text=tip, bg=BG, fg=DIM, font=F_SMALL).pack(side="left", padx=(8, 0))
            value = values.get(key)
            if kind == "switch":
                var = tk.BooleanVar(value=bool(value))
                Switch(row, var).pack(side="right")
            elif kind == "choice":
                var = tk.StringVar(value=extra.get(value, next(iter(extra.values()))))
                ttk.Combobox(row, textvariable=var, state="readonly", width=26,
                             values=list(extra.values())).pack(side="right", padx=(16, 0))
            else:
                shown = "" if value in (None, "") else (f"{value:g}" if isinstance(value, float) else str(value))
                var = tk.StringVar(value=shown)
                tk.Entry(row, textvariable=var, width=extra or 8, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat",
                         insertbackground=TEXT, highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT).pack(side="right", ipady=3, padx=(16, 0))
            variables[key] = (var, kind, extra)

        def read():
            out = {}
            for key, (var, kind, extra) in variables.items():
                if kind == "switch":
                    out[key] = bool(var.get())
                elif kind == "choice":
                    out[key] = next(k for k, v in extra.items() if v == var.get())
                elif kind in ("int", "float"):
                    try:
                        number = float(var.get().strip().replace(",", ".") or 0)
                    except ValueError:
                        number = 0
                    out[key] = int(number) if kind == "int" else number
                else:
                    out[key] = var.get().strip()
            return out

        def save():
            if on_save(read()) is not False:
                win.destroy()
                self._save_settings()
                self._show_automation()

        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(0, 14))
        ttk.Button(bottom, text="Save", style="Accent.TButton", width=8, command=save).pack(side="right")
        ttk.Button(bottom, text="Cancel", width=8, command=win.destroy).pack(side="right", padx=6)
        dark_title_bar(win)
        win.focus_force()
        win.save, win.variables, win.body = save, {k: v[0] for k, v in variables.items()}, body
        return win

    def _choice_row(self, parent, text, summary, command, info=None, tip=None):
        """A Settings row: its name, what's chosen now (grey) and Change…."""
        row = self._row(parent, text, tip, info=info)
        ttk.Button(row, text="Change…", command=command).pack(side="right")
        # a long summary is cut short (all of it shows when the mouse is over it), so it never
        # pushes the row's name or the Change… button aside
        var = tk.StringVar(value=short(summary(), CHOICE_WORDS))
        var.trace_add("write", lambda *a: self.root.after_idle(self._settings_text_changed))
        hover_text(tk.Label(row, textvariable=var, bg=BG, fg=MUTED, font=F_SMALL), summary).pack(
            side="right", padx=(0, 10))
        if not hasattr(self, "choice_rows"):
            self.choice_rows = []
        self.choice_rows.append((var, summary))
        return row

    def _show_automation(self):
        for var, summary in getattr(self, "choice_rows", []):
            try:
                var.set(short(summary(), CHOICE_WORDS))
            except tk.TclError:
                pass

    # ------------------------------------------------------------ stop by itself

    AUTO_STOP_HELP = (
        "The macro stops by itself when the first of these happens: a number of runs, a number of divine "
        "fragments this session, a number of minutes, or a time of day. Leave the ones you don't want at 0 "
        "(or the time empty).\n\n"
        "\"Finish the run first\" lets the run that's playing end before it stops (so it stops while idle, "
        "on the results screen), instead of in the middle of a mission.\n\n"
        "Afterwards it can close the game, put the PC to sleep or shut it down (sleep and shut down show a "
        "30 second countdown you can cancel).\n\n"
        "With Discord on, you're told 5 minutes before a timed stop. From the phone remote, /keepgoing "
        "cancels the stop for that playback.")

    def auto_stop_summary(self):
        a = self._auto_stop_settings()
        parts = []
        if a["runs"]:
            parts.append(f"{a['runs']} runs")
        if a["fragments"]:
            parts.append(f"{a['fragments']} fragments")
        if a["minutes"]:
            parts.append(f"{a['minutes']:g} min")
        if a["at"]:
            parts.append(f"at {a['at']}")
        if not a["on"] or not parts:
            return "Off"
        then = {"nothing": "", "close": ", then close the game", "sleep": ", then sleep",
                "shutdown": ", then shut down"}[a["then"]]
        return ("After " + " or ".join(parts)).replace("After at", "At") + then

    def open_auto_stop(self):
        a = self._auto_stop_settings()
        fields = [
            ("on", "Stop by itself", None, "switch", None),
            (None, "STOP AFTER (THE FIRST THAT HAPPENS)", None, "head", None),
            ("runs", "Runs", "0 = not used", "int", 8),
            ("fragments", "Divine fragments this session", "0 = not used", "int", 8),
            ("minutes", "Minutes of playing", "0 = not used", "float", 8),
            ("at", "At this time", "like 03:30; empty = not used", "text", 8),
            ("finish_run", "Finish the run first", "stop between runs, not mid-mission", "switch", None),
            (None, "AFTERWARDS", None, "head", None),
            ("then", "Then", None, "choice", core.AUTO_STOP_THEN),
            ("warn", "Tell Discord 5 minutes before", "for a timed stop", "switch", None),
        ]

        def save(new):
            at = new["at"]
            if at:
                try:
                    hh, mm = at.replace(".", ":").split(":")
                    new["at"] = f"{int(hh) % 24:02}:{int(mm) % 60:02}"
                except ValueError:
                    self.boxes.showinfo("Stop by itself", "Write the time like 03:30, or leave it empty.",
                                        parent=win)
                    return False
            self.settings["auto_stop"] = new
        win = self._form_window("Stop by itself", fields, a, save, intro=None)
        return win

    def _auto_stop_warning(self, minutes):
        super()._auto_stop_warning(minutes)
        if not self.settings.get("discord_enabled"):
            return
        try:
            values = self.session.values(self._ping_for(False))
            remote = " Send /keepgoing from the phone remote to cancel." if self.settings.get("remote_enabled") else ""
            card = {"title": f"{values['macro']} · Stopping soon",
                    "description": f"The macro stops by itself in about {minutes} min "
                                   f"({self.auto_stop_summary()}).{remote}", "color": 0xFFB238}
            self._send_card(values["ping"], card, None)
        except Exception as exc:
            core.diag.error("Couldn't tell Discord about the stop", exc)

    def _auto_stop_then(self):
        """Sleep and shut down wait 30 seconds first, with a box to cancel."""
        then = (getattr(self, "auto_stop", None) or {}).get("then", "nothing")
        if then not in ("sleep", "shutdown"):
            return super()._auto_stop_then()
        win = tk.Toplevel(self.root, bg=BG)
        win.title("Macro Recorder")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        what = "goes to sleep" if then == "sleep" else "shuts down"
        text = tk.StringVar()
        tk.Label(win, textvariable=text, bg=BG, fg=TEXT, font=F_BOLD, padx=24, pady=16).pack()
        state = {"left": 30, "job": None}

        def cancel():
            if state["job"] is not None:
                self.root.after_cancel(state["job"])
            win.destroy()
            self.sub_note = "Cancelled: the PC stays on"
            self._refresh()

        def tick():
            if state["left"] <= 0:
                win.destroy()
                core.MacroRecorder._auto_stop_then(self)
                return
            text.set(f"The macro stopped by itself. The PC {what} in {state['left']} s.")
            state["left"] -= 1
            state["job"] = self.root.after(1000, tick)
        ttk.Button(win, text="Cancel", command=cancel).pack(pady=(0, 14))
        win.protocol("WM_DELETE_WINDOW", cancel)
        dark_title_bar(win)
        self.power_win = win
        tick()

    # ------------------------------------------------------------ small random timing

    VARY_HELP = (
        "Plays every action a tiny bit earlier or later, and lets clicks land a few pixels from their spot, "
        "a little differently each run. A macro that loops for hours then doesn't repeat the exact same "
        "tiny timing error every single run, which can keep a long loop steadier.\n\n"
        "It's off unless you turn it on, the amounts are small, and actions never change order. Keep the "
        "pixels at 0 for macros that click very small buttons.\n\n"
        "Each macro can have its own choice (kept in its file): the usual setting, never, or its own "
        "amounts. Trim a macro first (Edit > More > Trim), then add this.")

    def vary_summary(self):
        v = self._vary_settings()
        own = getattr(self, "macro_vary", None) or {}
        note = {"off": "; off for this macro", "own": "; this macro has its own"}.get(own.get("mode"), "")
        return (f"±{v['ms']} ms, {v['px']} px" if v["on"] else "Off") + note

    def open_vary(self):
        v = self._vary_settings()
        own = dict(getattr(self, "macro_vary", None) or {})
        values = dict(v, mode=own.get("mode", "usual"), own_ms=own.get("ms", v["ms"]), own_px=own.get("px", v["px"]))
        name = self.name_var.get().strip() or "the open macro"
        fields = [
            ("on", "Small random timing", "off = played exactly as recorded", "switch", None),
            ("ms", "Each action earlier or later by up to (ms)", None, "int", 6),
            ("px", "Clicks land within (pixels)", "0 = exactly on the spot", "int", 6),
            (None, f"FOR {name.upper()}", None, "head", None),
            ("mode", "This macro uses", None, "choice", VARY_MODES),
            ("own_ms", "Its own: up to (ms)", None, "int", 6),
            ("own_px", "Its own: within (pixels)", None, "int", 6),
        ]

        def save(new):
            self.settings["vary"] = {"on": new["on"], "ms": max(0, min(500, new["ms"])),
                                     "px": max(0, min(50, new["px"]))}
            before = getattr(self, "macro_vary", None)
            if new["mode"] == "usual":
                self.macro_vary = None
            elif new["mode"] == "off":
                self.macro_vary = {"mode": "off"}
            else:
                self.macro_vary = {"mode": "own", "ms": max(0, min(500, new["own_ms"])),
                                   "px": max(0, min(50, new["own_px"]))}
            if self.macro_vary != before and (self.events or self.actions):
                self.unsaved = True  # (kept in the macro's file the next time it's saved)

        win = self._form_window("Small random timing", fields, values, save,
                                intro="For steadier long loops. It doesn't hide anything from a game.")
        sample = tk.Label(win.body, text="", bg=BG, fg=MUTED, font=F_SMALL, anchor="w", justify="left",
                          wraplength=480)
        sample.pack(fill="x", pady=(8, 0))

        def preview(*_a):
            import random

            try:
                ms = max(0, min(500, int(float(win.variables["ms"].get() or 0))))
                px = max(0, min(50, int(float(win.variables["px"].get() or 0))))
            except (ValueError, tk.TclError):
                return
            waits = ", ".join(f"{1000 + random.randint(-ms, ms)}" for _ in range(5))
            spots = ", ".join(f"({960 + random.randint(-px, px)}, {540 + random.randint(-px, px)})" for _ in range(3))
            sample.config(text=f"Example: a 1000 ms wait would be {waits} ms.\n"
                               f"A click at (960, 540) would land at {spots}.")
        for key in ("ms", "px"):
            win.variables[key].trace_add("write", preview)
        preview()
        return win

    # ------------------------------------------------------------ Discord daily / weekly summary

    def _summary_settings(self):
        saved = self.settings.get("discord_summary")
        saved = saved if isinstance(saved, dict) else {}
        at = str(saved.get("at") or "22:00")
        try:
            hh, mm = at.split(":")
            at = f"{int(hh) % 24:02}:{int(mm) % 60:02}"
        except ValueError:
            at = "22:00"
        weekday = saved.get("weekday") if saved.get("weekday") in WEEKDAYS else "Sunday"
        return {"daily": bool(saved.get("daily", False)), "at": at, "weekly": bool(saved.get("weekly", False)),
                "weekday": weekday, "last_daily": saved.get("last_daily"), "last_weekly": saved.get("last_weekly")}

    def summary_summary(self):
        s = self._summary_settings()
        parts = (["every day"] if s["daily"] else []) + ([f"every {s['weekday']}"] if s["weekly"] else [])
        text = " and ".join(parts) + f" at {s['at']}"
        return text[0].upper() + text[1:] if parts else "Off"

    def open_summary_options(self):
        s = self._summary_settings()
        fields = [
            ("daily", "Daily summary", "runs, wins and losses, fragments, time, best run", "switch", None),
            ("weekly", "Weekly summary", "with a chart of the week, and records", "switch", None),
            ("weekday", "Weekly on", None, "choice", {d: d for d in WEEKDAYS}),
            ("at", "At this time", "like 22:00", "text", 8),
        ]

        def save(new):
            try:
                hh, mm = new["at"].replace(".", ":").split(":")
                new["at"] = f"{int(hh) % 24:02}:{int(mm) % 60:02}"
            except ValueError:
                self.boxes.showinfo("Discord summary", "Write the time like 22:00.", parent=win)
                return False
            old = self._summary_settings()
            # (turned on after today's time has passed: the first one comes tomorrow)
            today = run_history.day_of()
            passed = time.strftime("%H:%M") >= new["at"]
            new["last_daily"] = old["last_daily"] if old["daily"] else (today if passed else None)
            new["last_weekly"] = old["last_weekly"] if old["weekly"] else (today if passed else None)
            self.settings["discord_summary"] = new
        win = self._form_window("Discord summary", fields, s, save,
                                intro="Sent to your Discord channel while the app is open (Discord must be on). "
                                      "A day with no runs sends nothing.")
        row = tk.Frame(win.body, bg=BG)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Send today's now", command=lambda: self.send_summary("daily", test=True)).pack(
            side="left")
        ttk.Button(row, text="Send this week's now", command=lambda: self.send_summary("weekly", test=True)).pack(
            side="left", padx=6)
        return win

    def summary_card(self, kind, now=None):
        """(card, picture bytes or None) for the daily or weekly summary; None when there were no runs."""
        now = time.time() if now is None else now
        if kind == "daily":
            date, d = run_history.days(1, now)[0]
            title, day_list = f"Today's summary · {date}", None
            reconnects = d.get("reconnects", 0)
            rs = [r for r in run_history.runs() if run_history.day_of(r["t"]) == date]
        else:
            day_list = run_history.days(7, now)
            title = f"This week's summary · {day_list[0][0]} to {day_list[-1][0]}"
            reconnects = sum(d.get("reconnects", 0) for _date, d in day_list)
            first = time.mktime(time.strptime(day_list[0][0], "%Y-%m-%d"))
            rs = run_history.runs(since=first)
            d = {"runs": sum(x["runs"] for _d, x in day_list)}
        if not d["runs"]:
            return None
        s = run_history.summary(rs) if rs else None
        lines = []
        if s:
            rate = f"{s['winrate']:.1f}%" if s["winrate"] is not None else "-"
            lines += [f"**Runs** {s['runs']}  ·  **Won** {s['wins']}  ·  **Failed** {s['losses']}  ·  "
                      f"**Unknown** {s['unknown']}",
                      f"**Win rate** {rate}  ·  **Average run** {clock_text(s['average'])}",
                      f"**Best run** {clock_text(s['best'])}  ·  **Longest** {clock_text(s['worst'])}",
                      f"**Divine fragments** {s['fragments']}  ({s['fragments_per_hour']:.2f} an hour)",
                      f"**Time in runs** {clock_text(s['seconds'])}"]
            if s["slow"]:
                lines.append(f"**Unusually slow runs** {s['slow']}")
        else:
            lines.append(f"**Runs** {d['runs']}")
        if reconnects:
            lines.append(f"**Reconnects** {reconnects}")
        png = None
        if kind == "weekly":
            best = max(day_list, key=lambda kv: kv[1]["runs"])
            lines.append(f"**Best day this week** {best[0]} with {best[1]['runs']} runs")
            rec = run_history.records()
            if rec.get("runs"):
                lines.append(f"**Record day** {rec['runs'][0]}: {rec['runs'][1]} runs"
                             + (f"  ·  most fragments {rec['fragments'][0]}: {rec['fragments'][1]}"
                                if rec.get("fragments") else ""))
            png = run_history.chart_png(day_list, "Runs each day (green won, red failed)")
        return {"title": title, "description": "\n".join(lines), "color": 0x4F7CFF}, png

    def send_summary(self, kind, test=False):
        if not self.settings.get("discord_enabled"):
            if test:
                self.boxes.showinfo("Discord summary", "Turn Discord on first (Settings > Discord).",
                                    parent=self.settings_win or self.root)
            return False
        made = self.summary_card(kind)
        if made is None:
            if test:
                self.boxes.showinfo("Discord summary", "No runs yet in that time, so there's nothing to send.",
                                    parent=self.settings_win or self.root)
            return False
        self._send_card("", made[0], made[1])
        return True

    def _summary_tick(self):
        """Every half minute: is it time for the daily or weekly summary?"""
        try:
            s = self._summary_settings()
            today = run_history.day_of()
            if (s["daily"] or s["weekly"]) and time.strftime("%H:%M") >= s["at"]:
                saved = self.settings.get("discord_summary")
                if s["daily"] and s["last_daily"] != today:
                    saved["last_daily"] = today
                    run_history.save()
                    self.send_summary("daily")
                    core.save_settings(self.settings)
                if s["weekly"] and s["last_weekly"] != today \
                        and WEEKDAYS[time.localtime().tm_wday] == s["weekday"]:
                    saved["last_weekly"] = today
                    self.send_summary("weekly")
                    core.save_settings(self.settings)
        except Exception as exc:
            core.diag.error("The Discord summary couldn't be sent", exc)
        self.root.after(30000, self._summary_tick)

    # ------------------------------------------------------------ the Stats window

    def stats_numbers(self, macro=None, period="all"):
        since = None
        if period == "today":
            since = time.mktime(time.strptime(run_history.day_of(), "%Y-%m-%d"))
        elif period in ("7", "30"):
            since = time.time() - int(period) * 86400
        return run_history.summary(run_history.runs(macro, since))

    @staticmethod
    def stats_lines(s):
        rate = f"{s['winrate']:.1f}%" if s["winrate"] is not None else "-"
        return [("Runs", str(s["runs"])), ("Won", str(s["wins"])), ("Failed", str(s["losses"])),
                ("Unknown", str(s["unknown"])), ("Win rate", rate),
                ("Average run", clock_text(s["average"]) if s["runs"] else "-"),
                ("Usual run (middle)", clock_text(s["usual"]) if s["runs"] else "-"),
                ("Best run", clock_text(s["best"])), ("Longest run", clock_text(s["worst"])),
                ("Unusually slow runs", str(s["slow"])),
                ("Divine fragments", str(s["fragments"])),
                ("Fragments an hour", f"{s['fragments_per_hour']:.2f}" if s["runs"] else "-"),
                ("Time in runs", clock_text(s["seconds"]) if s["runs"] else "-")]

    def open_stats(self):
        """Run stats: numbers for one macro (or all), next to another macro to compare, the last 14
        days as a chart, and the latest runs with unusually slow ones marked."""
        old = getattr(self, "stats_win", None)
        if old is not None and old.winfo_exists():
            old.lift()
            return old
        parent = self.settings_win if self.settings_win is not None else self.root
        win = tk.Toplevel(parent, bg=BG)
        win.title("Run stats")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        self.stats_win = win
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=18, pady=14)
        everything = "All macros"
        names = [everything] + run_history.macros()
        macro_var = tk.StringVar(value=everything)
        other_var = tk.StringVar(value="(nothing)")
        period_var = tk.StringVar(value=PERIODS["7"])
        top = tk.Frame(body, bg=BG)
        top.pack(fill="x")
        tk.Label(top, text="Macro", bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
        b1 = ttk.Combobox(top, textvariable=macro_var, state="readonly", width=20, values=names)
        b1.pack(side="left", padx=(6, 14))
        tk.Label(top, text="Compare with", bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
        b2 = ttk.Combobox(top, textvariable=other_var, state="readonly", width=20, values=["(nothing)"] + names)
        b2.pack(side="left", padx=(6, 14))
        b3 = ttk.Combobox(top, textvariable=period_var, state="readonly", width=14, values=list(PERIODS.values()))
        b3.pack(side="left")
        grid = tk.Frame(body, bg=BG)
        grid.pack(fill="x", pady=(12, 0))
        tk.Label(body, text="RUNS EACH DAY, LAST 14 DAYS  (green won, red failed, grey unknown; +n = fragments)",
                 bg=BG, fg=MUTED, font=F_SECTION, anchor="w").pack(fill="x", pady=(14, 4))
        chart = tk.Canvas(body, width=640, height=170, bg=FIELD, highlightthickness=0)
        chart.pack()
        tk.Label(body, text="LATEST RUNS", bg=BG, fg=MUTED, font=F_SECTION, anchor="w").pack(fill="x", pady=(14, 4))
        latest = tk.Text(body, height=8, width=78, bg=FIELD, fg=TEXT, font=F_SMALL, relief="flat", wrap="none")
        latest.pack(fill="x")
        latest.tag_configure("slow", foreground=AMBER)
        latest.tag_configure("loss", foreground=RED)
        latest.tag_configure("dim", foreground=MUTED)

        def pick(var):
            return None if var.get() in (everything, "(nothing)") else var.get()

        def show(_e=None):
            for b in (b1, b2, b3):
                b.selection_clear()
            period = next(k for k, v in PERIODS.items() if v == period_var.get())
            for child in grid.winfo_children():
                child.destroy()
            columns = [(macro_var.get(), self.stats_numbers(pick(macro_var), period))]
            if other_var.get() != "(nothing)":
                columns.append((other_var.get(), self.stats_numbers(pick(other_var), period)))
            for c, (name, _s) in enumerate(columns, start=1):
                tk.Label(grid, text=short(name, 24), bg=BG, fg=ACCENT, font=F_BOLD).grid(row=0, column=c, sticky="e",
                                                                                         padx=(24, 0))
            for r, (label, _v) in enumerate(self.stats_lines(columns[0][1]), start=1):
                tk.Label(grid, text=label, bg=BG, fg=MUTED, font=F_BASE).grid(row=r, column=0, sticky="w")
                for c, (_name, s) in enumerate(columns, start=1):
                    value = self.stats_lines(s)[r - 1][1]
                    tk.Label(grid, text=value, bg=BG, fg=TEXT, font=F_BASE).grid(row=r, column=c, sticky="e",
                                                                                 padx=(24, 0))
            # the chart
            chart.delete("all")
            day_list = run_history.days(14)
            biggest = max([d["runs"] for _date, d in day_list] + [1])
            slot = 640 / len(day_list)
            for i, (date, d) in enumerate(day_list):
                x0, x1, y = i * slot + 8, (i + 1) * slot - 8, 140
                for key, colour in (("wins", GREEN), ("losses", RED), ("unknown", DIM)):
                    part = 110 * d.get(key, 0) / biggest
                    if part:
                        chart.create_rectangle(x0, y - part, x1, y, fill=colour, outline="")
                        y -= part
                if d["runs"]:
                    chart.create_text((x0 + x1) / 2, y - 8, text=str(d["runs"]), fill=TEXT, font=F_SMALL)
                chart.create_text((x0 + x1) / 2, 150, text=date[8:], fill=MUTED, font=F_SMALL)
                if d.get("fragments"):
                    chart.create_text((x0 + x1) / 2, 162, text=f"+{d['fragments']}", fill=ACCENT, font=F_SMALL)
            # the latest runs
            rs = run_history.runs(pick(macro_var))[-60:]
            usual = {}
            for name in {r["macro"] for r in rs}:
                usual[name] = run_history.summary(run_history.runs(name))["usual"]
            latest.config(state="normal")
            latest.delete("1.0", "end")
            if not rs:
                latest.insert("end", "No runs yet. They're kept from this version on.", "dim")
            for r in reversed(rs):
                slow = run_history.is_slow(r, usual.get(r["macro"]))
                when = time.strftime("%d %b %H:%M", time.localtime(r["t"]))
                line = (f"{when}   {stats.STATUS_TEXT.get(r['status'], '?'):8} {clock_text(r['s']):>8}   "
                        f"{short(r['macro'], 28)}" + (f"   +{r['f']} fragment{'s' if r['f'] != 1 else ''}" if r["f"]
                                                      else "")
                        + ("   unusually slow" if slow else "") + "\n")
                latest.insert("end", line, "slow" if slow else ("loss" if r["status"] == stats.LOSS else ""))
            latest.config(state="disabled")
        for b in (b1, b2, b3):
            b.bind("<<ComboboxSelected>>", show)

        def clear():
            if self.boxes.askyesno("Run stats", "Forget every kept run and day? This can't be undone.",
                                   parent=win):
                run_history.clear()
                show()
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(0, 14))
        ttk.Button(bottom, text="Close", width=8, command=win.destroy).pack(side="right")
        ttk.Button(bottom, text="Refresh", width=8, command=show).pack(side="right", padx=6)
        link(bottom, "Forget all runs", clear, bg=BG).pack(side="left")
        dark_title_bar(win)
        show()
        win.show, win.vars = show, {"macro": macro_var, "other": other_var, "period": period_var}
        return win
