"""Profiles: named sets of settings you switch between with one click (Settings > General >
Profile), and that a macro can be linked to, so opening the macro switches to its settings.

A profile holds every setting except the ones that belong to this PC or to no profile at all
(saved macros, all-time results, the phone remote's token and accounts, the list of saved
background pictures, the icon, window positions). Since 2.9 a profile does hold which background
each window shows (and its darkness, fit and part); the picture files stay in one shared list. Profiles live in the settings file under "profiles"; the one in use
is "profile_active" and takes each change you make while it's in use."""
import copy
import time
import tkinter as tk
from tkinter import ttk

import macro_recorder as core
import run_history
import stats
from ui_common import *  # noqa: F401,F403

# never part of a profile
SKIP_KEYS = {"profiles", "profile_active", "macro_library", "stats_all", "last_seen_version", "last_game_exe",
             "builtin_failed_added", "check_updates", "app_icon_file", "app_logo_file", "app_logo_same",
             "video_history", "video_link", "first_start_done", "warn_big_pictures",
             "video_playlist_note"}
SKIP_PREFIXES = ("remote_", "video_rect")
SKIP_ENDINGS = ("_geometry",)
NO_PROFILE = "(none)"
# background options that belong to this PC, not to a profile: the saved pictures and how GIFs play
BG_SHARED_KEYS = {"background_library", "background_animate", "background_animate_focused",
                  "background_fps", "background_pause_others"}


def is_background_key(key):
    """Which background each window shows, and its darkness, fit and part (in a profile since 2.9)."""
    return key.startswith(("background_", "settings_background")) and key not in BG_SHARED_KEYS


def in_profile(key):
    if key.startswith(("background", "settings_background")):
        return is_background_key(key)
    return not (key in SKIP_KEYS or key.startswith(SKIP_PREFIXES) or key.endswith(SKIP_ENDINGS))


def profile_part(settings):
    return {k: copy.deepcopy(v) for k, v in settings.items() if in_profile(k)}


class ProfilesMixin:
    def profiles(self):
        saved = self.settings.get("profiles")
        if not isinstance(saved, dict):
            saved = self.settings["profiles"] = {}
        return saved

    def profile_active(self):
        name = self.settings.get("profile_active")
        return name if name in self.profiles() else None

    def profile_summary(self):
        return self.profile_active() or "None yet"

    def _keep_active_profile(self):
        """The profile in use takes the settings as they are now."""
        name = self.profile_active()
        if name:
            self.profiles()[name] = profile_part(self.settings)

    def _profiles_take_background(self):
        """Profiles made before 2.9 hold no background yet: each takes the one showing now (once), so
        switching to it doesn't take the picture away."""
        now = {k: copy.deepcopy(v) for k, v in self.settings.items() if is_background_key(k)}
        changed = False
        for part in self.profiles().values():
            if isinstance(part, dict) and not any(is_background_key(k) for k in part):
                part.update(copy.deepcopy(now))
                changed = True
        if changed:
            core.save_settings(self.settings)

    def profiles_using_background(self, name):
        """Names of the profiles other than the one in use that show the background picture name."""
        active = self.profile_active()
        return [p for p, part in self.profiles().items() if p != active and isinstance(part, dict) and any(
            is_background_key(k) and k.endswith("_picture") and v == name for k, v in part.items())]

    def forget_background_everywhere(self, name):
        """A removed background picture: no profile shows it anymore."""
        for part in self.profiles().values():
            if isinstance(part, dict):
                for k in list(part):
                    if is_background_key(k) and k.endswith("_picture") and part[k] == name:
                        part[k] = ""

    def save_profile(self, name):
        """A new profile from the settings as they are now (or the same name written over)."""
        name = " ".join(str(name).split())[:40]
        if not name or name == NO_PROFILE:
            return None
        self._save_settings()
        self.profiles()[name] = profile_part(self.settings)
        self.settings["profile_active"] = name
        core.save_settings(self.settings)
        self._show_automation()
        return name

    def switch_profile(self, name):
        """Switch to a profile: every setting it holds is put in place. False if it can't be now."""
        if name not in self.profiles() or self.playing or self.recording:
            return False
        if name == self.profile_active():
            return True
        self._save_settings()
        self._keep_active_profile()
        if self.profile_active() is None:
            # no profile was in use: the settings as they are now are kept as one, so nothing is lost
            keep = "My settings"
            n = 2
            while keep in self.profiles():
                keep = f"My settings {n}"
                n += 1
            self.profiles()[keep] = profile_part(self.settings)
            core.diag.info(f"Kept the settings in use as the profile \"{keep}\"")
        if hasattr(self, "sort_profile_pictures"):
            try:  # (a profile from before 2.9: its pictures are sorted into groups first)
                self.sort_profile_pictures(self.profiles()[name])
            except Exception as exc:
                core.diag.error("Couldn't sort the profile's pictures", exc)
        for key in [k for k in self.settings if in_profile(k)]:
            del self.settings[key]
        self.settings.update(copy.deepcopy(self.profiles()[name]))
        self.settings["profile_active"] = name
        self._apply_settings_everywhere()
        core.save_settings(self.settings)
        core.diag.info(f"Switched to the profile \"{name}\"")
        self.sub_note = f"Profile: {name}"
        self._refresh()
        return True

    def _apply_settings_everywhere(self):
        """After self.settings changed as a whole: every control and everything made from them."""
        s = self.settings
        self.loop_var.set(bool(s.get("loop", True)))
        self.speed_var.set(core.format_speed(core.parse_speed(s.get("speed", 1)) or 1.0))
        self.repeat_var.set(core.int_setting(s, "repeat_count", 1, 1, 9999))
        self._load_result_pictures()
        self._load_page_settings()
        self._show_automation()
        self._show_picture_summary()
        self._picture_window_reload()
        if getattr(self, "settings_saved_state", None) is not None:
            self.settings_saved_state = self._page_settings()  # (a switch isn't something to Undo)
            self.settings_history, self.settings_redo = [], []

    def delete_profile(self, name):
        if name in self.profiles():
            del self.profiles()[name]
            if self.settings.get("profile_active") == name:
                self.settings.pop("profile_active", None)
            core.save_settings(self.settings)
            self._show_automation()

    def rename_profile(self, old, new):
        new = " ".join(str(new).split())[:40]
        if old not in self.profiles() or not new or new in self.profiles() or new == NO_PROFILE:
            return False
        self.profiles()[new] = self.profiles().pop(old)
        if self.settings.get("profile_active") == old:
            self.settings["profile_active"] = new
        if getattr(self, "macro_profile", None) == old:
            self.macro_profile = new
        core.save_settings(self.settings)
        self._show_automation()
        return True

    def _pictures_in_use(self):
        """Pictures another profile watches for must stay on disk too."""
        watch, own = super()._pictures_in_use()
        for part in self.profiles().values():
            for key in ("watch_pictures", "result_pictures"):
                for e in part.get(key) or []:
                    if isinstance(e, dict):
                        watch |= {e.get(k) for k in ("file", "confirm_file") if e.get(k)}
        return watch, own

    def load(self, path=None, quiet=False):
        ok = super().load(path, quiet=quiet)
        linked = getattr(self, "macro_profile", None)
        if ok and linked and linked in self.profiles() and linked != self.profile_active():
            if self.switch_profile(linked):
                self.sub_note = f"Macro opened, profile: {linked}"
                self.show_profile_notice(f"Profile switched to \"{short(linked, 24)}\" (linked to this macro)")
                self._refresh()
                return ok
        if ok:
            self.show_profile_notice(None)
        return ok

    def show_profile_notice(self, text):
        """The line under Saved macros that says the profile was switched (None hides it)."""
        row = getattr(self, "profile_notice_row", None)
        if row is None:
            return
        self.profile_notice_text = text
        # (only the text changes: the line keeps its place and height, so nothing else moves)
        if self.profile_notice.cget("text") != (text or ""):
            self.profile_notice.config(text=text or "")
            self.profile_notice_ok.config(text="OK" if text else "")
            self._refresh()

    PROFILE_HELP = (
        "A profile is a named set of all your settings: speed, repeat, countdown, picture watch and its "
        "pictures, results, Discord, sounds, stop by itself and so on. Make one for each way you play "
        "(say \"Farming\" and \"Testing\") and switch with one click here, or with /profile from the phone "
        "remote.\n\n"
        "The profile in use keeps every change you make. \"Link to the open macro\" writes the profile's "
        "name into that macro (when you save it), so opening the macro switches to it. In a chain, each "
        "\"Play another macro\" step can name a profile too: its speed and random timing are used for "
        "that part.\n\n"
        "Each profile also remembers its background: which picture each window shows, its darkness, "
        "fit and part. The saved background pictures themselves are shared by every profile.\n\n"
        "Not part of a profile: saved macros, all-time results and run stats, the phone remote, "
        "the list of saved background pictures, how animated pictures play, and the app icon.")

    def open_profiles(self):
        parent = self.settings_win if self.settings_win is not None else self.root
        win = tk.Toplevel(parent, bg=BG)
        win.title("Profiles")
        win.transient(parent)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=18, pady=14)
        head = tk.Frame(body, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="Profiles: named sets of all your settings", bg=BG, fg=TEXT, font=F_BOLD).pack(
            side="left")
        link(head, "ⓘ", lambda: self.boxes.showinfo("Profiles", self.PROFILE_HELP, parent=win), bg=BG).pack(
            side="left", padx=(6, 0))
        lst = ttk.Treeview(body, show="tree", selectmode="browse", height=6)
        lst.pack(fill="x", pady=(8, 6))
        name_var = tk.StringVar()
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x")
        tk.Label(row, text="Name", bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
        entry = tk.Entry(row, textvariable=name_var, width=28, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat",
                         insertbackground=TEXT, highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT)
        entry.pack(side="left", padx=8, ipady=3)
        link_var = tk.BooleanVar()
        link_row = tk.Frame(body, bg=BG)
        link_row.pack(fill="x", pady=(10, 0))
        link_label = tk.Label(link_row, text="", bg=BG, fg=TEXT, font=F_BASE)
        link_label.pack(side="left")

        def selected():
            sel = lst.selection()
            return sel[0] if sel else None

        def fill(select=None):
            lst.delete(*lst.get_children())
            active = self.profile_active()
            for name in sorted(self.profiles(), key=str.lower):
                lst.insert("", "end", iid=name, text=name + ("   (in use)" if name == active else ""))
            pick = select or active
            if pick and lst.exists(pick):
                lst.selection_set(pick)
            macro = self.name_var.get().strip()
            linked = getattr(self, "macro_profile", None)
            link_var.set(bool(linked) and linked == selected())
            link_label.config(text=f"Link the chosen profile to the open macro ({macro})" if macro
                              else "Link to the open macro (no macro is open)")

        def picked(_e=None):
            link_var.set(bool(selected()) and getattr(self, "macro_profile", None) == selected())

        def new():
            name = self.save_profile(name_var.get())
            if not name:
                self.boxes.showinfo("Profiles", "Type a name for the new profile first.", parent=win)
                return
            name_var.set("")
            fill(name)

        def use():
            name = selected()
            if name and not self.switch_profile(name):
                self.boxes.showinfo("Profiles", "Stop the macro first, then switch.", parent=win)
            fill(name)

        def rename():
            name = selected()
            if name and not self.rename_profile(name, name_var.get()):
                self.boxes.showinfo("Profiles", "Type a new name that isn't used yet.", parent=win)
                return
            new_name = " ".join(name_var.get().split())[:40]
            name_var.set("")
            fill(new_name)

        def delete():
            name = selected()
            if name and self.boxes.askyesno("Profiles", f"Delete the profile \"{name}\"? Your settings stay as "
                                            "they are now.", parent=win):
                self.delete_profile(name)
                fill()

        def link_changed():
            name = selected()
            if not (self.events or self.actions):
                link_var.set(False)
                return
            self.macro_profile = name if link_var.get() and name else None
            self.unsaved = True
            self.sub_note = "Save the macro to keep its profile link"
            self._refresh()
        Switch(link_row, link_var, command=link_changed).pack(side="right")
        lst.bind("<<TreeviewSelect>>", picked)
        lst.bind("<Double-1>", lambda e: use())
        buttons = tk.Frame(body, bg=BG)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="New from my settings now", command=new).pack(side="left")
        ttk.Button(buttons, text="Rename", command=rename).pack(side="left", padx=6)
        ttk.Button(buttons, text="Delete", command=delete).pack(side="left")
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(0, 14))
        ttk.Button(bottom, text="Close", width=8, command=win.destroy).pack(side="right")
        ttk.Button(bottom, text="Switch to it", style="Accent.TButton", command=use).pack(side="right", padx=6)
        dark_title_bar(win)
        fill()
        win.fill, win.lst, win.name_var, win.new, win.use = fill, lst, name_var, new, use
        return win

    # ------------------------------------------------------------ for the phone remote

    def remote_stats_text(self):
        """Today's and this session's numbers, for /stats."""
        _date, d = run_history.days(1)[0]
        today = [r for r in run_history.runs() if run_history.day_of(r["t"]) == run_history.day_of()]
        s = run_history.summary(today)
        rate = f"{s['winrate']:.1f}%" if s["winrate"] is not None else "-"
        lines = [f"**Today** {s['runs']} runs · {s['wins']} won · {s['losses']} failed · win rate {rate}"]
        if s["runs"]:
            lines.append(f"Average run {stats.duration_text(s['average'])} · best "
                         f"{stats.duration_text(s['best']) if s['best'] is not None else '-'} · "
                         f"{s['fragments']} fragment{'s' if s['fragments'] != 1 else ''} "
                         f"({s['fragments_per_hour']:.2f} an hour)")
        if d.get("reconnects"):
            lines.append(f"Reconnects today: {d['reconnects']}")
        if self.playing and getattr(self, "auto_stop", None) and not self.auto_stop["cancelled"]:
            lines.append(f"Stops by itself: {self.auto_stop_summary()} (/keepgoing cancels it)")
        lines.append(f"Profile: {self.profile_active() or 'none'}")
        return "\n".join(lines)

    def remote_profile(self, wanted):
        names = list(self.profiles())
        if not wanted:
            return ("Profiles: " + ", ".join(sorted(names, key=str.lower)) + f". In use: {self.profile_active() or 'none'}."
                    if names else "No profiles yet. Make one on the PC: Settings > General > Profile.")
        match = next((n for n in names if n.lower() == str(wanted).lower()), None) \
            or next((n for n in names if str(wanted).lower() in n.lower()), None)
        if not match:
            return f"There's no profile called \"{wanted}\"."
        if not self.switch_profile(match):
            return "Stop the macro first, then switch the profile."
        return f"Switched to the profile \"{match}\"."

    # ------------------------------------------------------------ the emergency stop

    def emergency_stop(self):
        """Ctrl+Alt+End: stop everything, whatever the app is doing (see core._on_key_press)."""
        super().emergency_stop()
        self.sub_note = "Emergency stop (Ctrl+Alt+End)"
        self._refresh()
