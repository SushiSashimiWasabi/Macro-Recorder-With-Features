"""Milestones (Preview 4): goals for the all-time totals (runs, wins, divine fragments, win streak, hours
played). Settings > Results > MILESTONES: the usual four, and your own ones (Add a milestone). When one is
reached: the Milestone sound, a line in the main window, and (if turned on) a Discord message.

Kept in settings["milestones"] = [{"kind", "at", "name"?, "reached"? ("YYYY-MM-DD")}] (not in profiles).
Counted from the all-time results (Settings > Results), plus the session that's playing now."""
import datetime
import time
import tkinter as tk
from tkinter import ttk

import macro_recorder as core
import stats
from ui_common import *  # noqa: F401,F403

KINDS = {"runs": "Runs", "wins": "Wins", "fragments": "Divine fragments", "streak": "Wins in a row",
         "hours": "Hours played"}
DEFAULT_MILESTONES = [{"kind": "runs", "at": 1000}, {"kind": "fragments", "at": 50}, {"kind": "streak", "at": 500},
                      {"kind": "hours", "at": 500}]
MAX_MILESTONES = 30
MAX_AT = 1_000_000_000


def clean_milestone(m):
    """One milestone from the settings file, checked (None when it makes no sense)."""
    if not isinstance(m, dict) or m.get("kind") not in KINDS:
        return None
    try:
        at = int(m.get("at"))
    except (TypeError, ValueError, OverflowError):
        return None
    if not 1 <= at <= MAX_AT:
        return None
    out = {"kind": m["kind"], "at": at}
    name = " ".join(str(m.get("name") or "").split())[:40]
    if name:
        out["name"] = name
    reached = m.get("reached")
    try:
        out["reached"] = datetime.date.fromisoformat(reached).isoformat()  # (a made-up date would crash the window)
    except (TypeError, ValueError):
        pass
    return out


def milestone_name(m):
    if m.get("name"):
        return m["name"]
    n = f"{m['at']:,}"
    return {"runs": f"{n} runs", "wins": f"{n} wins", "fragments": f"{n} divine fragments",
            "streak": f"{n} wins in a row", "hours": f"{n} hours played"}[m["kind"]]


class MilestonesMixin:
    def milestones(self):
        """The milestones (the usual four the first time)."""
        saved = self.settings.get("milestones")
        if not isinstance(saved, list):
            saved = [dict(m) for m in DEFAULT_MILESTONES]
            self.settings["milestones"] = saved
            self._mark_reached_quietly()
        out = [m for m in (clean_milestone(m) for m in saved[:MAX_MILESTONES]) if m]
        if out != saved:
            self.settings["milestones"] = out
        return out

    def milestone_totals(self):
        """All-time totals now: what the saved all-time results hold plus the session that's playing."""
        a = self.settings.get("stats_all") if isinstance(self.settings.get("stats_all"), dict) else {}
        sess = getattr(self, "session", None)
        counted = sess is not None and sess.runs and not getattr(sess, "added", False)
        totals = {"runs": int(a.get("runs", 0)), "wins": int(a.get("wins", 0)),
                  "fragments": int(a.get("fragments", 0)), "streak": int(a.get("best_streak", 0)),
                  "hours": float(a.get("seconds", 0)) / 3600}
        if counted:
            totals["runs"] += len(sess.runs)
            totals["wins"] += sess.count(stats.WIN)
            totals["fragments"] += sum(sess.fragments)
            totals["hours"] += max(0.0, time.time() - sess.started) / 3600
        return totals

    def _mark_reached_quietly(self):
        """Milestones you had already passed when they were made count as reached, without a sound."""
        totals = self.milestone_totals()
        today = datetime.date.today().isoformat()
        for m in self.settings.get("milestones", []):
            if isinstance(m, dict) and m.get("kind") in KINDS and not m.get("reached"):
                try:
                    if totals[m["kind"]] >= int(m.get("at", 0)):
                        m["reached"] = today
                except (TypeError, ValueError):
                    pass

    def _note_streak(self):
        """Wins in a row over every session (a loss ends it, an unknown run doesn't). Worked out again from
        the session's runs each time, starting from what it was when the session began, so noting the same
        runs twice, or an Unknown run that gets its result late, never skews it."""
        a = self.settings.get("stats_all")
        if not isinstance(a, dict):
            a = self.settings["stats_all"] = {}
        sess = self.session
        now, best = int(getattr(sess, "streak_before", 0)), int(getattr(sess, "best_streak_before", 0))
        for status, _seconds in sess.runs:
            if status == stats.WIN:
                now += 1
            elif status == stats.LOSS:
                now = 0
            best = max(best, now)
        a["streak_now"], a["best_streak"] = now, max(best, int(getattr(sess, "best_streak_before", 0)))

    def check_milestones(self):
        """After each run (on the window's thread): tell about every milestone just reached."""
        if getattr(self, "session", None) is not None and self.session.runs:
            self._note_streak()
        self.milestones()  # (cleans the saved list)
        totals = self.milestone_totals()
        reached = []
        for m in self.settings["milestones"]:
            if not m.get("reached") and totals.get(m["kind"], 0) >= m["at"]:
                m["reached"] = datetime.date.today().isoformat()
                reached.append(m)
        core.save_settings(self.settings)
        for m in reached:
            name = milestone_name(m)
            core.diag.info(f"Milestone reached: {name}")
            self._sound("milestone")
            if hasattr(self, "show_profile_notice"):
                self.show_profile_notice(f"🏆 Milestone reached: {name}!")
            if self.settings.get("milestones_discord", True) and self.settings.get("discord_enabled"):
                self._send_card(str(self.settings.get("discord_ping", "")).strip()
                                if self.settings.get("milestones_ping") else "",
                                {"title": "🏆 Milestone reached", "description": name, "color": 0xF1C40F}, None)
        self._show_milestones()
        return reached

    # ------------------------------------------------------------ Settings > Results

    def milestones_summary(self):
        ms = self.milestones()
        done = sum(1 for m in ms if m.get("reached"))
        nxt = next((m for m in ms if not m.get("reached")), None)
        text = f"{done} of {len(ms)} reached"
        if nxt is not None:
            text += f" · next: {milestone_name(nxt)}"
        return text

    def _show_milestones(self):
        var = getattr(self, "milestones_var", None)
        if var is not None:
            var.set(self.milestones_summary())
        win = getattr(self, "milestones_win", None)
        if win is not None and win.winfo_exists():
            self._fill_milestones(win)

    def _build_milestones_rows(self, f):
        self._section(f, "MILESTONES")
        self.milestones_var = tk.StringVar(value=self.milestones_summary())
        row = self._row(f, "Milestones", info=self.MILESTONES_HELP)
        ttk.Button(row, text="Change…", command=self.open_milestones).pack(side="right")
        tk.Label(row, textvariable=self.milestones_var, bg=BG, fg=MUTED, font=F_SMALL).pack(side="right",
                                                                                          padx=(0, 10))
        self.milestones_var.trace_add("write", lambda *a: self.root.after_idle(self._settings_text_changed))

    MILESTONES_HELP = ("Goals for your all-time results: runs, wins, divine fragments, wins in a row and hours "
                       "played. When one is reached you hear the Milestone sound (Settings > Sounds), the main "
                       "window says so, and Discord gets a message if you turned that on.\n\n"
                       "They count from your all-time results (Settings > Results), so a Reset there starts them "
                       "again from 0. Add your own with \"Add a milestone\".")

    def open_milestones(self):
        old = getattr(self, "milestones_win", None)
        if old is not None and old.winfo_exists():
            old.lift()
            return old
        parent = self.settings_win if self.settings_win is not None and self.settings_win.winfo_viewable() \
            else self.root
        win = self.milestones_win = tk.Toplevel(parent, bg=BG)
        win.title("Milestones")
        win.transient(parent)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        dark_title_bar(win)
        win.body = tk.Frame(win, bg=BG)
        win.body.pack(fill="both", padx=18, pady=(14, 4))
        add = tk.Frame(win, bg=BG)
        add.pack(fill="x", padx=18, pady=(6, 0))
        tk.Label(add, text="Add a milestone", bg=BG, fg=TEXT, font=F_BOLD).pack(anchor="w")
        r = tk.Frame(add, bg=BG)
        r.pack(fill="x", pady=(4, 0))
        kind_var = tk.StringVar(value=KINDS["wins"])
        ttk.Combobox(r, textvariable=kind_var, values=list(KINDS.values()), state="readonly", width=16).pack(
            side="left")
        at_var = tk.StringVar(value="100")
        tk.Entry(r, textvariable=at_var, width=10, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat", insertbackground=TEXT,
                 highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT).pack(side="left", padx=6,
                                                                                               ipady=3)
        name_var = tk.StringVar(value="")
        name = tk.Entry(r, textvariable=name_var, width=22, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat",
                        insertbackground=TEXT, highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT)
        name.pack(side="left", ipady=3)
        entry_hint(name, name_var, "Name (optional)", size=10)
        win.add_note = tk.Label(add, text="", bg=BG, fg=RED, font=F_SMALL, anchor="w")
        win.add_note.pack(fill="x")

        def do_add():
            kind = next((k for k, v in KINDS.items() if v == kind_var.get()), None)
            ok, note = self.add_milestone(kind, at_var.get(), name_var.get())
            win.add_note.config(text=note, fg=GREEN if ok else RED)
            if ok:
                name_var.set("")
        ttk.Button(r, text="Add", style="Accent.TButton", width=6, command=do_add).pack(side="left", padx=(6, 0))
        opts = tk.Frame(win, bg=BG)
        opts.pack(fill="x", padx=18, pady=(8, 0))
        self.milestones_discord_var = tk.BooleanVar(value=self.settings.get("milestones_discord", True) is not False)

        def discord_flip():
            self.settings["milestones_discord"] = bool(self.milestones_discord_var.get())
            core.save_settings(self.settings)
        r = tk.Frame(opts, bg=BG)
        r.pack(fill="x", pady=3)
        tk.Label(r, text="Send a Discord message when one is reached", bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
        tk.Label(r, text="if Discord is on", bg=BG, fg=DIM, font=F_SMALL).pack(side="left", padx=(8, 0))
        Switch(r, self.milestones_discord_var, command=discord_flip).pack(side="right")
        self.milestones_ping_var = tk.BooleanVar(value=bool(self.settings.get("milestones_ping", False)))

        def ping_flip():
            self.settings["milestones_ping"] = bool(self.milestones_ping_var.get())
            core.save_settings(self.settings)
        r = tk.Frame(opts, bg=BG)
        r.pack(fill="x", pady=3)
        tk.Label(r, text="… and ping me", bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
        tk.Label(r, text="the @ping in Settings > Discord", bg=BG, fg=DIM, font=F_SMALL).pack(side="left", padx=(8, 0))
        Switch(r, self.milestones_ping_var, command=ping_flip).pack(side="right")
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(10, 14))
        ttk.Button(bottom, text="Close", command=win.destroy).pack(side="right")
        link(bottom, "Put back the usual four", self.reset_milestones, bg=BG).pack(side="left")
        win.bind("<Escape>", lambda e: win.destroy())
        self._fill_milestones(win)
        win.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - win.winfo_reqwidth()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - win.winfo_reqheight()) // 3)
        win.geometry(f"+{x}+{y}")
        return win

    def _fill_milestones(self, win):
        for w in win.body.winfo_children():
            w.destroy()
        tk.Label(win.body, text="Milestones", bg=BG, fg=TEXT, font=F_BOLD, anchor="w").pack(fill="x")
        tk.Label(win.body, text="Counted from your all-time results (Settings > Results), since version 2.4 or "
                                "its last Reset.", bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x",
                                                                                                pady=(0, 8))
        totals = self.milestone_totals()
        ms = self.milestones()
        if not ms:
            tk.Label(win.body, text="No milestones. Add one below.", bg=BG, fg=MUTED, font=F_BASE,
                     anchor="w").pack(fill="x")
        for i, m in enumerate(ms):
            r = tk.Frame(win.body, bg=BG)
            r.pack(fill="x", pady=2)
            now = totals[m["kind"]]
            shown = f"{now:,.1f}" if m["kind"] == "hours" else f"{int(now):,}"
            if m.get("reached"):
                when = datetime.date.fromisoformat(m["reached"]).strftime("%d %B %Y").lstrip("0")
                text, color = f"✓ reached {when}", GREEN
            else:
                text, color = f"{shown} / {m['at']:,}  ({min(99, int(100 * now / m['at']))}%)", MUTED
            link(r, "Remove", lambda i=i: self.remove_milestone(i), bg=BG).pack(side="right")
            tk.Label(r, text=short(milestone_name(m), 34), bg=BG, fg=TEXT, font=F_BASE, width=34,
                     anchor="w").pack(side="left")
            tk.Label(r, text=text, bg=BG, fg=color, font=F_SMALL, anchor="w").pack(side="left", padx=(8, 12))

    def add_milestone(self, kind, at, name=""):
        """Your own milestone. Returns (ok, the note to show)."""
        if kind not in KINDS:
            return False, "Choose what it counts."
        try:
            at = int(str(at).replace(",", "").strip())
        except ValueError:
            return False, "Type a whole number, like 250."
        if not 1 <= at <= MAX_AT:
            return False, "Type a number from 1 to 1,000,000,000."
        ms = self.milestones()
        if len(ms) >= MAX_MILESTONES:
            return False, f"There can be {MAX_MILESTONES} milestones at most. Remove one first."
        if any(m["kind"] == kind and m["at"] == at for m in ms):
            return False, "That milestone is already in the list."
        m = clean_milestone({"kind": kind, "at": at, "name": name})
        if self.milestone_totals()[kind] >= at:
            m["reached"] = datetime.date.today().isoformat()  # (already passed: no sound for it)
        ms.append(m)
        ms.sort(key=lambda x: (list(KINDS).index(x["kind"]), x["at"]))
        self.settings["milestones"] = ms
        core.save_settings(self.settings)
        core.diag.info(f"Milestone added: {milestone_name(m)}")
        self._show_milestones()
        return True, "Added." + (" You had already reached it." if m.get("reached") else "")

    def remove_milestone(self, i):
        ms = self.milestones()
        if 0 <= i < len(ms):
            del ms[i]
            self.settings["milestones"] = ms
            core.save_settings(self.settings)
            self._show_milestones()

    def reset_milestones(self):
        self.settings["milestones"] = [dict(m) for m in DEFAULT_MILESTONES]
        self._mark_reached_quietly()
        core.save_settings(self.settings)
        self._show_milestones()
