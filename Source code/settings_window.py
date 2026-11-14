"""Settings > About (help, updates, what's new), opening and closing Settings, Undo / Reset /
Apply, and changing the shortcut keys.

Part of the dark window: ModernMacroRecorder (modern_ui.py) inherits this class.
"""

from ui_common import *  # noqa: F401,F403  (colours, fonts, widgets, tk, core, the other modules)


class SettingsWindowMixin:
    def _report_text(self):
        return diag.report(APP_VERSION, self.settings, (self.screen_w, self.screen_h),
                           extra=[f"Macro: {len(self.events)} actions"
                                  + (f", program {self.macro_program.get('exe')}" if self.macro_program and
                                     self.macro_program.get("exe") else "")])

    def make_report(self):
        """Settings > About > Make a report: save the report as a file (kept in the reports folder)
        and show the reports window (where it can be copied, if wanted)."""
        try:
            path = diag.save_report(self._report_text())
        except OSError as exc:
            diag.error("Couldn't save a report", exc)
            self.boxes.showerror("Macro Recorder", f"Couldn't save the report:\n{exc}")
            return
        self.open_reports(path)

    def _copy_report(self, path, status):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            status.set("That report file is gone.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        status.set("Copied. Paste it with Ctrl+V.")

    @staticmethod
    def _show_in_folder(path):
        """Open the folder in File Explorer (or Finder) with the file selected."""
        import subprocess
        try:
            if IS_WIN:
                if os.path.isfile(path):
                    subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
                else:
                    os.startfile(path)
            elif IS_MAC:
                subprocess.Popen(["open", "-R", path] if os.path.isfile(path) else ["open", path])
        except OSError:
            pass

    def open_reports(self, new_report=None):
        """The reports window: the report just made (show it in its folder, copy it again), where
        reports are kept, how much room reports and logs take, and Clear."""
        old = getattr(self, "reports_win", None)
        if old is not None and old.winfo_exists():
            old.destroy()
        parent = self.settings_win if self.settings_win.winfo_viewable() else self.root
        win = self.reports_win = tk.Toplevel(parent, bg=BG)
        win.title("Reports - Macro Recorder")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.transient(parent)
        if getattr(self, "icon_img", None) is not None:
            win.iconphoto(False, self.icon_img)
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=22, pady=(18, 6))
        folder = diag.reports_dir() or os.path.dirname(core.settings_path())

        def heading(text, color=TEXT):
            tk.Label(body, text=text, bg=BG, fg=color, font=(FAMILY, 13, "bold"), anchor="w").pack(fill="x")

        def para(text, color=MUTED, top=4):
            tk.Label(body, text=text, bg=BG, fg=color, font=F_BASE, anchor="w", justify="left",
                     wraplength=470).pack(fill="x", pady=(top, 0))

        if new_report:
            heading("✓  Report saved", GREEN)
            para("Send the file to whoever helps you, for example by dragging it into Discord. Or copy "
                 "its text to paste it in a message.", top=6)
            tk.Label(body, text=os.path.basename(new_report), bg=FIELD, fg=TEXT, font=F_SMALL, anchor="w",
                     padx=8, pady=5).pack(fill="x", pady=(10, 0))
            row = tk.Frame(body, bg=BG)
            row.pack(fill="x", pady=(8, 0))
            ttk.Button(row, text="Show the file", style="Accent.TButton",
                       command=lambda: self._show_in_folder(new_report)).pack(side="left")
            ttk.Button(row, text="Copy the text",
                       command=lambda: self._copy_report(new_report, status)).pack(side="left", padx=6)
        else:
            heading("Reports and logs")
            para("A report has the app's version, your system, screen sizes, a few settings and the end of "
                 "the log. Make one when something goes wrong, and send it to whoever helps you.", top=6)
        para("What's in it: no macros, keys, pictures or Discord link, and your user folder name is "
             "hidden. Nothing is ever sent by itself.", DIM, top=10)

        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=(14, 10))
        tk.Label(body, text="KEPT ON THIS COMPUTER", bg=BG, fg=MUTED, font=F_SECTION, anchor="w").pack(fill="x")
        usage = tk.StringVar()
        para("Reports are kept in:", top=4)
        tk.Label(body, text=folder, bg=BG, fg=TEXT, font=F_SMALL, anchor="w", justify="left",
                 wraplength=470).pack(fill="x")
        tk.Label(body, textvariable=usage, bg=BG, fg=MUTED, font=F_BASE, anchor="w", justify="left",
                 wraplength=470).pack(fill="x", pady=(8, 0))
        para("They don't grow much: the log keeps at most about 2 MB (older lines are dropped by "
             f"themselves) and only the last {diag.MAX_REPORTS} reports are kept. Clear empties both.", DIM)
        status = tk.StringVar(value="")
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x", pady=(10, 0))
        ttk.Button(row, text="Open the folder", command=lambda: (
            os.makedirs(folder, exist_ok=True), self._show_in_folder(folder))).pack(side="left")
        if not new_report:
            ttk.Button(row, text="Make a report", command=self.make_report).pack(side="left", padx=6)
        ttk.Button(row, text="Clear reports and logs", style="Danger.TButton",
                   command=lambda: clear()).pack(side="right")
        tk.Label(body, textvariable=status, bg=BG, fg=GREEN, font=F_SMALL, anchor="w").pack(fill="x", pady=(6, 0))

        def show_usage():
            count, size = diag.storage()
            usage.set(f"Now: {count} report{'s' if count != 1 else ''}, {diag.size_text(size)} in all "
                      "(reports and logs).")

        def clear():
            count, size = diag.storage()
            if not self.boxes.askyesno(
                    "Clear reports and logs", f"Delete {count} report file{'s' if count != 1 else ''} and empty "
                    f"the log ({diag.size_text(size)} in all)?\n\nThis can't be undone. Your macros and settings "
                    "aren't touched.", parent=win):
                return
            freed = diag.clear()
            status.set(f"Cleared: {diag.size_text(freed)} freed.")
            show_usage()

        show_usage()
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=22, pady=(8, 16))
        ttk.Button(bottom, text="Close", width=8, command=win.destroy).pack(side="right")
        dark_title_bar(win)
        only_close_button(win)
        win.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - win.winfo_reqwidth()) // 2
        y = parent.winfo_rooty() + 60
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
        win.focus_force()

    def _build_about_tab(self, f):
        tk.Label(f, text="Macro Recorder", bg=BG, fg=TEXT, font=(FAMILY, 14, "bold"), anchor="w").pack(fill="x")
        tk.Label(f, text=f"Version {APP_VERSION}" + (" (preview)" if self.preview else ""), bg=BG, fg=MUTED,
                 font=F_BASE, anchor="w").pack(fill="x", pady=(2, 4))
        page = f"https://github.com/{updater.REPO}"

        def open_page():
            import webbrowser
            webbrowser.open(page)
        gh = link(f, "GitHub page: " + page.replace("https://", ""), open_page, fg=ACCENT)
        gh.config(anchor="w")
        gh.pack(fill="x", pady=(0, 10))
        tk.Label(f, justify="left", bg=BG, fg=MUTED, font=F_BASE, anchor="w", text=(
            "Records your mouse and keyboard and plays them back.\n\n"
            "Opens .macro files, and also .luvmacro, TinyTask .rec, Jitbit .mcr\n"
            "and simple AutoHotkey .ahk files.\n\n"
            "Settings are kept in:")).pack(fill="x")
        tk.Label(f, text=os.path.dirname(core.settings_path()), bg=BG, fg=TEXT, font=F_SMALL, anchor="w",
                 wraplength=420, justify="left").pack(fill="x", pady=(2, 0))
        self._section(f, "UPDATES")
        self._switch_row(f, "Check for updates when the app starts", self.update_check_var,
                         "asks before installing")
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", pady=4)
        self.btn_update = ttk.Button(row, text="Check now", command=lambda: self.check_for_update(manual=True))
        self.btn_update.pack(side="left")
        tk.Label(row, textvariable=self.update_status_var, bg=BG, fg=MUTED, font=F_SMALL, anchor="w",
                 wraplength=330, justify="left").pack(side="left", fill="x", padx=(10, 0))
        link(f, "What's new (every version)", self.show_whats_new, fg=ACCENT).pack(anchor="w", pady=(4, 0))
        self._section(f, "HELP")
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", pady=4)
        ttk.Button(row, text="Make a report", command=self.make_report).pack(side="left")
        ttk.Button(row, text="Reports and logs…", command=self.open_reports).pack(side="left", padx=(6, 0))
        self.report_status_var = tk.StringVar(value="")
        self.report_status_var.trace_add("write", lambda *a: self.root.after_idle(self._settings_text_changed))
        tk.Label(row, textvariable=self.report_status_var, bg=BG, fg=MUTED, font=F_SMALL, anchor="w",
                 wraplength=260, justify="left").pack(side="left", fill="x", padx=(10, 0))
        tk.Label(f, text="The report has the version, your system, screen sizes, a few settings and the log. "
                         "No macros, keys or links. Nothing is sent: you paste it yourself.",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w", wraplength=440, justify="left").pack(fill="x")

    # ------------------------------------------------------------ updates from GitHub

    def _settings_text_changed(self):
        bd = getattr(self, "settings_backdrop", None)
        if bd is not None:
            try:
                bd.text_changed()
            except tk.TclError:
                pass

    def _in_background(self, work, done):
        """Runs work() on a helper thread and done(result, error) back on the window's thread."""
        import threading
        box = {}

        def run():
            try:
                box["result"] = work()
            except Exception as e:
                box["error"] = e
            box["finished"] = True

        def poll():
            if box.get("finished"):
                done(box.get("result"), box.get("error"))
            else:
                self.root.after(150, poll)

        threading.Thread(target=run, daemon=True).start()
        self.root.after(150, poll)

    def check_for_update(self, manual=False):
        if self.update_busy:
            return
        if not manual and getattr(self, "update_checked", False):
            return  # "Check now" was already pressed since the app started
        self.update_busy = True
        self.update_checked = True
        if manual:  # the startup check works quietly and never touches the text
            self.update_status_var.set("Checking…")

        def done(info, error):
            self.update_busy = False
            if error is not None:
                if manual:
                    self.update_status_var.set(str(error))
                return
            if info is None:
                if manual:
                    self.update_status_var.set(f"You have the newest version ({APP_VERSION}).")
                return
            self.update_status_var.set(f"Version {info['version']} is available.")
            self._offer_update(info)

        self._in_background(updater.check, done)

    def _offer_update(self, info):
        if self.recording or self.playing:  # never in the middle of a macro: ask once it's done
            self.root.after(3000, lambda: self._offer_update(info))
            return
        parent = self.settings_win if self.settings_win.winfo_viewable() else self.root
        notes = info["notes"]
        if len(notes) > 600:
            notes = notes[:600].rstrip() + "…"
        text = f"Macro Recorder {info['version']} is out (you have {APP_VERSION})."
        if notes:
            text += "\n\nWhat's new:\n" + notes
        if not updater.can_install():
            messagebox.showinfo("Update available", text + "\n\nYou're running from the source code, so "
                                "get it with git pull or from:\n" + info["page"], parent=parent)
            return
        text += "\n\nDownload and install it now? Macro Recorder will restart by itself."
        if self.preview:
            text += "\n\n(Preview: this replaces the preview exe.)"
        if messagebox.askyesno("Update available", text, parent=parent):
            self._install_update(info)

    def _install_update(self, info):
        self.update_busy = True
        win = tk.Toplevel(self.root)
        win.title("Updating Macro Recorder")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", lambda: None)  # finishes by itself
        msg = tk.StringVar(value=f"Downloading version {info['version']}…")
        tk.Label(win, textvariable=msg, bg=BG, fg=TEXT, font=F_BASE, padx=24, pady=18,
                 width=40, anchor="w").pack()
        dark_title_bar(win)
        progress = {"done": 0, "total": info.get("size") or 0}
        path = updater.download_path()

        def tick():
            if win.winfo_exists() and self.update_busy:
                if progress.get("stage"):
                    msg.set(progress["stage"])
                elif progress["total"]:
                    pct = int(progress["done"] * 100 / progress["total"])
                    msg.set(f"Downloading version {info['version']}…  {pct}%")
                win.after(200, tick)

        def work():
            updater.download(info, path, lambda d, t: progress.update(done=d, total=t or progress["total"]))
            progress["stage"] = "Installing…"
            return updater.install(path)

        def done(proc, error):
            self.update_busy = False
            if error is not None:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
                win.destroy()
                self.update_status_var.set(str(error))
                messagebox.showerror("Update failed", f"{error}\n\nYour current version still works. "
                                     f"You can also download it from:\n{info['page']}", parent=self.root)
                return
            msg.set("Restarting…")
            self.root.after(300, self._on_close)

        tick()
        self._in_background(work, done)

    # ------------------------------------------------------------ what's new, and errors

    def show_whats_new(self, after_update=False):
        """Every version's changes, newest first, in a window you can scroll and resize (after an
        update it opens at the top, with the new version)."""
        old = getattr(self, "whats_new_win", None)
        if old is not None and old.winfo_exists():
            old.deiconify()
            old.lift()
            return
        win = self.whats_new_win = tk.Toplevel(self.root, bg=BG)
        win.title("What's new - Macro Recorder")
        win.attributes("-topmost", True)
        win.minsize(460, 320)
        win.geometry("640x620")
        if getattr(self, "icon_img", None) is not None:
            win.iconphoto(False, self.icon_img)
        head = f"Updated to version {APP_VERSION}" if after_update else "What's new"
        tk.Label(win, text=head, bg=BG, fg=TEXT, font=(FAMILY, 14, "bold"), anchor="w").pack(
            fill="x", padx=20, pady=(16, 2))
        tk.Label(win, text=f"You have version {APP_VERSION}. Every change since the first version, newest first.",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x", padx=20, pady=(0, 8))
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(side="bottom", fill="x", padx=20, pady=14)
        ttk.Button(bottom, text="OK", style="Accent.TButton", width=8, command=win.destroy).pack(side="right")
        box = tk.Frame(win, bg=BG)
        box.pack(fill="both", expand=True, padx=(20, 8))
        text = tk.Text(box, bg=BG, fg=MUTED, relief="flat", font=F_BASE, wrap="word", highlightthickness=0,
                       padx=0, pady=0, cursor="arrow", spacing1=2, spacing3=2)
        bar = ttk.Scrollbar(box, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        text.tag_configure("version", foreground=TEXT, font=(FAMILY, 12, "bold"), spacing1=14, spacing3=2)
        text.tag_configure("current", foreground=ACCENT)
        text.tag_configure("date", foreground=DIM, font=F_SMALL, spacing3=6)
        text.tag_configure("item", lmargin1=4, lmargin2=20, spacing3=5)
        for i, (version, date, changes) in enumerate(HISTORY):
            named = version[:1].isdigit()
            title = ("Version " + version) if named else version
            text.insert("end", ("" if i == 0 else "\n") + title, ("version",))
            if version == APP_VERSION:
                text.insert("end", "   your version", ("version", "current"))
            when = date if date.startswith("not ") else "Finalized " + date
            text.insert("end", "\n" + when + "\n", ("date",))
            for change in changes:
                text.insert("end", "•  " + change + "\n", ("item",))
        text.config(state="disabled")
        text.bind("<MouseWheel>", lambda e: text.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        dark_title_bar(win)
        win.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
        y = self.root.winfo_rooty() + 20
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
        win.focus_force()

    def _whats_new_on_start(self):
        """Once after an update: show what's new in this version."""
        s = self.settings
        last = s.get("last_seen_version")
        updated = last != APP_VERSION and (last is not None or "speed" in s or "hotkeys" in s)
        s["last_seen_version"] = APP_VERSION
        core.save_settings(s)
        if updated and APP_VERSION in WHATS_NEW and not self.preview:
            self.root.after(1500, lambda: self.show_whats_new(after_update=True))

    def report_error(self, exc_type, exc, tb):
        """Something went wrong in the window: write it in the log and say so (at most every 5 s)."""
        exc = exc if exc is not None else exc_type()
        exc.__traceback__ = tb
        diag.error("Error in the window", exc)
        now = time.perf_counter()
        if now - getattr(self, "last_error_box", -10) < 5:
            return
        self.last_error_box = now
        self._sound("error")
        try:
            messagebox.showerror(
                "Macro Recorder", f"Something went wrong:\n{exc}\n\nThe app keeps running. Settings > About > "
                "Make a report saves the details in a file, to send to whoever helps you.", parent=self.root)
        except tk.TclError:
            pass

    def open_settings(self, tab=None):
        if self.recording or self.playing:
            return
        win = self.settings_win
        self._finish_settings_window()
        win.deiconify()
        dark_title_bar(win)
        win.lift()
        only_close_button(win)
        if tab in self.tab_frames:
            self.tabs.select(self.tab_frames[tab])
        self._show_tab_bar()
        win.focus_set()
        self._refresh()
        win.after(60, lambda: (self.settings_backdrop.repaint(), self._bg_show_controls()))
        self._save_settings()
        self.settings_saved_state = self._page_settings()
        self.settings_history = []
        self.settings_redo = []
        self.pictures_seen = None
        self._note_pictures()
        self._show_settings_buttons()
        if self.settings_watch_job is None:
            self.settings_watch_job = self.root.after(300, self._watch_settings)

    def close_settings(self):
        self.capture_callback = None
        self._read_play_on(quiet=True)
        self._read_made_for(quiet=True)
        self._save_settings()
        if self.settings_watch_job is not None:
            self.root.after_cancel(self.settings_watch_job)
            self.settings_watch_job = None
        self._forget_removed_pictures()
        self.settings_win.withdraw()
        self._refresh()

    def _dialogs_over_settings(self):
        """Message boxes from the shared code (like Picture watch > Test now) have no parent window,
        so Windows tied them to the main window and brought it in front of Settings. While
        Settings is open they now belong to Settings instead."""
        app = self

        class Boxes:
            def __init__(self, real):
                self.real = real

            def __getattr__(self, name):
                fn = getattr(self.real, name)
                if not callable(fn) or not (name.startswith("show") or name.startswith("ask")):
                    return fn

                def call(*args, **kw):
                    win = app.settings_win
                    if "parent" not in kw and win is not None and win.winfo_viewable():
                        kw["parent"] = win
                    return fn(*args, **kw)
                return call
        core.messagebox = self.boxes  # (the dark boxes already go in front of Settings when it's open)
        core.filedialog = Boxes(filedialog)  # (picking a picture file too)

    def _apply_on_top(self):
        """"Keep window on top" for the main window."""
        if getattr(self, "holding_main", False):
            return  # _main_held_behind_settings puts it back when it's done
        want = bool(self.ontop_var.get())
        if bool(self.root.attributes("-topmost")) != want:  # setting it again would bring it forward
            self.root.attributes("-topmost", want)
        if self.settings_win is not None and self.settings_win.winfo_viewable():
            self.settings_win.lift()

    def _main_held_behind_settings(self, work):
        """Run work() (Undo / Reset) without the main window coming in front of Settings.
        Redrawing the main window's background picture brings it forward for a moment while it's
        "on top"; so for that moment it's an ordinary window (still above other apps' windows,
        below Settings), and afterwards it's put back on top right under Settings."""
        if not IS_WIN or not self.root.attributes("-topmost"):
            return work()
        import ctypes
        user32 = ctypes.windll.user32
        main = user32.GetParent(self.root.winfo_id())
        sett = user32.GetParent(self.settings_win.winfo_id())
        flags = 0x2 | 0x1 | 0x10  # SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        main, sett = ctypes.c_void_p(main), ctypes.c_void_p(sett)  # full 64-bit handles
        user32.SetWindowPos(main, ctypes.c_void_p(-2), 0, 0, 0, 0, flags)  # HWND_NOTOPMOST
        self.holding_main = True
        try:
            return work()
        finally:
            self.holding_main = False
            if self.ontop_var.get():  # (Undo may just have turned "Keep window on top" off)
                # placed right after a topmost window, it becomes topmost again, without coming forward
                user32.SetWindowPos(main, sett, 0, 0, 0, 0, flags)

    def close_settings_x(self):
        """The window's Close (X) button: with changes that weren't applied, ask what to do."""
        self._save_settings()
        if self._page_settings() != self.settings_saved_state:
            answer = messagebox.askyesnocancel(
                "Macro Recorder", "Keep the changes you made?\n\nYes = apply them, No = undo them.",
                parent=self.settings_win)
            if answer is None:
                return
            if not answer:
                self.reset_settings_changes()
        self.close_settings()

    # ------------------------------------------------------------ Undo / Reset / Apply

    # settings the Settings window's pages change (the ones Undo and Reset put back)
    PAGE_SETTINGS = ("hotkeys", "status_bar", "always_on_top", "record_mouse_moves", "mouse_detail",
                     "ready_seconds", "play_overlay", "play_resolution", "video_click_through", "video_opacity",
                     "watch_enabled", "watch_ignore_bg", "watch_click", "watch_wait", "watch_match",
                     "watch_end_wait", "watch_pictures", "sounds", "sound_volume", "sound_choices",
                     "check_updates", "background_animate", "settings_background_per_page",
                     "app_icon_file", "app_logo_file", "app_logo_same", "record_camera", "pause_when_away",
                     "away_stop_seconds", "switch_to_program", "fit_to", "discord_enabled", "discord_webhook",
                     "discord_runs", "discord_ping_fragments", "discord_screenshot", "discord_stops", "watch_limit_count",
                     "watch_limit_seconds", "watch_shift_lock", "watch_save_with_macro", "discord_name",
                     "discord_ping", "discord_ping_when", "discord_capture", "discord_title", "discord_content",
                     "discord_message", "results_enabled", "drops_enabled", "simplify_moves", "results_match", "result_pictures")

    def _is_page_setting(self, key):
        if key in self.PAGE_SETTINGS:
            return True
        # the background options of every window and the list of saved pictures (a removed
        # picture's file is only deleted once the change is applied)
        return key.startswith(("background_", "settings_background_"))

    def _page_settings(self):
        import copy
        return {k: copy.deepcopy(v) for k, v in self.settings.items() if self._is_page_setting(k)}

    def _settings_maybe_changed(self):
        """Something was saved while Settings is open: look for a change (for Undo) right away."""
        if getattr(self, "settings_check_soon", False) or self.settings_saved_state is None:
            return
        try:
            if not self.settings_win.winfo_viewable():
                return
        except tk.TclError:
            return
        self.settings_check_soon = True

        def check():
            self.settings_check_soon = False
            self._watch_settings(again=False)
        self.root.after(30, check)

    def _watch_settings(self, again=True):
        """While the Settings window is open: notice changes (for Undo) and show the right buttons.
        It runs right after anything is saved, and once every 2 seconds in case something changed
        another way (before, it copied every setting 3 times a second)."""
        if again:
            self.settings_watch_job = None
        if not self.settings_win.winfo_viewable():
            return
        self._note_pictures()
        now = self._page_settings()
        last = self.settings_history[-1][1] if self.settings_history else self.settings_saved_state
        if now != last:
            prev = last
            self.settings_history.append((prev, now))
            del self.settings_history[:-100]
            self.settings_redo = []  # a new change: what was undone can't be redone any more
        self._show_settings_buttons()
        if again:
            self.settings_watch_job = self.root.after(2000, self._watch_settings)

    def _show_settings_buttons(self):
        changed = self.settings_saved_state is not None and self._page_settings() != self.settings_saved_state
        if changed:
            self.btn_done.config(text="Apply")
            if not self.btn_reset.winfo_ismapped():
                self.btn_reset.pack(side="right", padx=(0, 8), after=self.btn_done)
                self.btn_redo.pack(side="right", padx=(0, 8), after=self.btn_reset)
                self.btn_undo.pack(side="right", padx=(0, 8), after=self.btn_redo)
        elif self.settings_redo:
            # everything undone: Done again, but Redo stays so the changes can be put back
            self.btn_done.config(text="Done")
            self.btn_reset.pack_forget()
            if not self.btn_redo.winfo_ismapped():
                self.btn_redo.pack(side="right", padx=(0, 8), after=self.btn_done)
                self.btn_undo.pack(side="right", padx=(0, 8), after=self.btn_redo)
        else:
            self.btn_done.config(text="Done")
            self.btn_undo.pack_forget()
            self.btn_redo.pack_forget()
            self.btn_reset.pack_forget()
        self.btn_undo.config(state="normal" if self.settings_history else "disabled")
        self.btn_redo.config(state="normal" if self.settings_redo else "disabled")

    def _done_or_apply(self):
        self._save_settings()
        if self._page_settings() != self.settings_saved_state:
            self.apply_settings_changes()
        else:
            self.close_settings()

    def apply_settings_changes(self):
        self._read_play_on(quiet=True)
        self._save_settings()
        self.settings_saved_state = self._page_settings()
        self.settings_history = []
        self.settings_redo = []
        self._forget_removed_pictures()
        self._show_settings_buttons()

    def undo_settings_change(self):
        """Back to how the settings were before the last change."""
        if not self.settings_history:
            return
        before, after = self.settings_history.pop()
        self.settings_redo.append((before, after))
        self._put_page_settings(before)

    def redo_settings_change(self):
        """Put back the last change Undo took back."""
        if not self.settings_redo:
            return
        before, after = self.settings_redo.pop()
        self.settings_history.append((before, after))
        self._put_page_settings(after)

    def reset_settings_changes(self):
        """Back to how the settings were when the window opened (or Apply was last pressed)."""
        if self.settings_saved_state is None:
            return
        self.settings_history = []
        self.settings_redo = []
        self._put_page_settings(self.settings_saved_state)

    def _put_page_settings(self, state):
        import copy
        for key in [k for k in self.settings if self._is_page_setting(k)]:
            del self.settings[key]
        self.settings.update(copy.deepcopy(state))
        self._main_held_behind_settings(self._load_page_settings)
        self._save_settings()
        # whatever saving tidied up counts as that state, not as a new change
        tidy = self._page_settings()
        if self.settings_history:
            self.settings_history[-1] = (self.settings_history[-1][0], tidy)
        elif state is self.settings_saved_state or state == self.settings_saved_state:
            self.settings_saved_state = tidy
        self._show_settings_buttons()
        if self.settings_win.winfo_viewable():  # stay in front of the main window
            self.settings_win.lift()
            self.settings_win.focus_force()

    def _load_page_settings(self):
        """Every control on the Settings pages shows what self.settings holds again."""
        s = self.settings
        detail = s.get("mouse_detail")
        through = s.get("video_click_through")
        for var, value in (
                (self.statusbar_var, bool(s.get("status_bar", True))),
                (self.ontop_var, bool(s.get("always_on_top", True))),
                (self.rec_moves_var, bool(s.get("record_mouse_moves", True))),
                (self.detail_var, detail if detail in MOUSE_DETAIL else "Smooth"),
                (self.ready_var, core.int_setting(s, "ready_seconds", 3, 0, 600)),
                (self.overlay_var, bool(s.get("play_overlay", True))),
                (self.video_through_var, through if through in VIDEO_THROUGH else VIDEO_THROUGH[0]),
                (self.video_opacity_var, core.int_setting(s, "video_opacity", 100, 20, 100)),
                (self.watch_var, bool(s.get("watch_enabled", True)) and image_watch is not None),
                (self.watch_bg_var, bool(s.get("watch_ignore_bg", True))),
                (self.watch_click_var, bool(s.get("watch_click", False))),
                (self.watch_wait_var, core.int_setting(s, "watch_wait", 3, 0, 600)),
                (self.watch_match_var, core.int_setting(s, "watch_match", 85, 50, 99)),
                (self.watch_end_var, core.int_setting(s, "watch_end_wait", 3, 0, 3600)),
                (self.sounds_var, bool(s.get("sounds", True))),
                (self.update_check_var, bool(s.get("check_updates", True))),
                (self.logo_same_var, bool(s.get("app_logo_same", False))),
                (self.bg_per_page_var, bool(s.get("settings_background_per_page", False))),
                (self.bg_animate_var, bool(s.get("background_animate", True))),
                (self.bg_fps_var, core.int_setting(s, "background_fps", 15, 5, 30)),
                (self.bg_focused_var, bool(s.get("background_animate_focused", True))),
                (self.bg_pause_others_var, bool(s.get("background_pause_others", True))),
                (self.camera_var, bool(s.get("record_camera", False))),
                (self.away_var, bool(s.get("pause_when_away", True))),
                (self.away_stop_var, core.int_setting(s, "away_stop_seconds", 0, 0, 3600)),
                (self.switch_prog_var, bool(s.get("switch_to_program", True))),
                (self.fit_var, FIT_TO.get(s.get("fit_to"), FIT_TO["window"])),
                (self.discord_var, bool(s.get("discord_enabled", False))),
                (self.discord_url_var, str(s.get("discord_webhook", ""))),
                (self.discord_runs_var, bool(s.get("discord_runs", True))),
                (self.discord_ping_drop_var, bool(s.get("discord_ping_fragments", False))),
                (self.discord_shot_var, bool(s.get("discord_screenshot", True))),
                (self.discord_stop_var, bool(s.get("discord_stops", True))),
                (self.watch_limit_var, core.int_setting(s, "watch_limit_count", 10, 0, 1000)),
                (self.watch_limit_s_var, core.int_setting(s, "watch_limit_seconds", 60, 1, 3600)),
                (self.watch_shift_var, bool(s.get("watch_shift_lock", True))),
                (self.watch_embed_var, bool(s.get("watch_save_with_macro", True))),
                (self.discord_name_var, str(s.get("discord_name", "Macro Recorder"))),
                (self.discord_ping_var, str(s.get("discord_ping", ""))),
                (self.discord_ping_when_var, PING_WHEN.get(s.get("discord_ping_when"), PING_WHEN["problems"])),
                (self.results_var, bool(s.get("results_enabled", True))),
                (self.drops_var, bool(s.get("drops_enabled", True))),
                (self.simplify_var, bool(s.get("simplify_moves", False))),
                (self.results_match_var, core.int_setting(s, "results_match", core.RESULTS_MATCH_DEFAULT, 50, 99))):
            var.set(value)
        cap = str(s.get("discord_capture", "screen"))
        self.discord_capture_var.set(CAPTURE_CHOICES["program"] if cap.startswith("program:")
                                     else CAPTURE_CHOICES.get(cap, "Main screen"))
        self.discord_program_var.set(cap[8:] if cap.startswith("program:") else "")
        self._load_result_pictures()
        self._show_result_pictures()
        # shortcuts
        self.hotkeys = dict(core.DEFAULT_HOTKEYS)
        saved = s.get("hotkeys")
        if isinstance(saved, dict):
            for action in HOTKEY_ACTIONS:
                if core.hotkey_is_valid(saved.get(action)):
                    self.hotkeys[action] = saved[action]
        if len(set(self.hotkeys.values())) != len(HOTKEY_ACTIONS):
            self.hotkeys = dict(core.DEFAULT_HOTKEYS)
        # your screen size
        saved = s.get("play_resolution")
        size = core.parse_resolution(saved) if isinstance(saved, str) else None
        self.play_on_var.set(core.format_resolution(size) if size else self.auto_label)
        # sounds
        volume = sounds.volume_number(s.get("sound_volume", sounds.DEFAULT_VOLUME))
        self.volume_var.set(volume)
        if hasattr(self, "volume_scale"):  # (the Sounds page is made the first time Settings opens)
            self.volume_scale.set(volume)
            self._volume_moved(volume)
            self._show_sounds()
        # pictures to watch for
        if image_watch is not None:
            self.watch_pictures = []
            for entry in s.get("watch_pictures") or []:
                pic = core.saved_picture(entry["file"], screen_h=entry.get("screen_h")) \
                    if isinstance(entry, dict) and entry.get("file") else None
                if pic is not None:
                    self.watch_pictures.append(pic)
            self._show_watch_pictures()
        # background pictures
        for c in [self.bg_main, self.bg_settings] + list(self.bg_pages.values()):
            c.load()
        self._apply_on_top()
        self._apply_app_icon()
        self._draw_logo()
        self._show_icon_logo()
        self._video_opacity()
        self._video_mode()
        self._bg_show_controls()
        self._apply_background()
        self._refresh()

    def _remove_watch_picture(self, index):
        """Removing a picture keeps its file until the change is applied, so Undo can bring it back."""
        if self.recording or self.playing or index >= len(self.watch_pictures):
            return
        self.watch_pictures.pop(index)
        self._show_watch_pictures()
        self._save_settings()
        self._refresh()

    def _pictures_in_use(self):
        """(watch picture files, files in the settings folder: background pictures, own icon and logo)
        in use right now."""
        own = {self.settings.get(k) for k in ("app_icon_file", "app_logo_file")}
        return ({p["file"] for p in self.watch_pictures} | {p["file"] for p in self.result_pictures},
                {e["file"] for e in self.bg_library() if isinstance(e, dict) and e.get("file")}
                | {n for n in own if isinstance(n, str) and n})

    def _note_pictures(self):
        """Remember every picture file that was in a list while Settings was open."""
        watch, bgs = self._pictures_in_use()
        seen = getattr(self, "pictures_seen", None)
        if seen is None:
            seen = self.pictures_seen = (set(), set())
        seen[0].update(watch)
        seen[1].update(bgs)

    def _forget_removed_pictures(self):
        """Delete the picture files that were in a list while Settings was open and aren't anymore
        (after Apply or closing): removed watch pictures, and removed (or added, then undone)
        background pictures. Files that were never in a list this time are never touched."""
        self._note_pictures()
        watch, bgs = self._pictures_in_use()
        seen_watch, seen_bgs = self.pictures_seen
        for folder, names in ((core.watch_dir(), seen_watch - watch),
                              (os.path.dirname(core.settings_path()), seen_bgs - bgs)):
            for name in names:
                if os.path.basename(name) != name:
                    continue  # only plain file names from the app's own lists
                try:
                    os.remove(os.path.join(folder, name))
                except OSError:
                    pass
        self.pictures_seen = None
        self._note_pictures()

    def open_hotkeys(self):  # the old "Hotkeys..." window is now Settings > General
        self.open_settings("General")

    def _capture_hotkey(self, action):
        if self.capture_callback is not None:
            return
        self.key_badges[action].config(text="Press a key…", fg=AMBER)

        def got_key(key_id):  # runs on the Tk thread
            self.capture_callback = None
            if key_id and key_id != "esc":
                for other in HOTKEY_ACTIONS:
                    if other != action and self.hotkeys[other] == key_id:
                        self.hotkeys[other] = self.hotkeys[action]  # swap: two actions never share a key
                self.hotkeys[action] = key_id
                self._save_settings()
            self._refresh()

        self.capture_callback = got_key

    def _reset_hotkeys(self):
        self.capture_callback = None
        self.hotkeys = dict(core.DEFAULT_HOTKEYS)
        self._save_settings()
        self._refresh()
