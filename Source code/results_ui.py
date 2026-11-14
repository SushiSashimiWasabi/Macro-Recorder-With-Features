"""Settings > Results: the pictures that mean a run was won or lost, and the results shown.

Part of the dark window: ModernMacroRecorder (modern_ui.py) inherits this class.
"""

from ui_common import *  # noqa: F401,F403  (colours, fonts, widgets, tk, core, the other modules)


class ResultsMixin:
    RESULTS_HELP = (
        "While a macro plays, the app looks for these pictures on your main screen. A \"mission "
        "completed\" picture counts the run as won, a \"mission failed\" one as lost, and a run where "
        "neither showed as unknown. The results (wins, losses, streak, win rate, run times) show in the "
        "timer at the top, here, and in the Discord messages.\n\n"
        "The built-in picture is AOT:R's gold MISSION COMPLETED title. Add your own with Add from "
        "screen (while it shows) or a picture file. Test now shows how well each one matches the "
        "screen right now.")

    DROPS_HELP = (
        "When a run ends, the app counts the divine fragments in the results screen's OBTAINED row: "
        "every item whose frame goes from pink-purple on the left to light blue on the right (all 4 kinds "
        "of fragment have that frame). The count goes in the Discord card ({fragments} this run, "
        "{fragments_session} this session, {fragments_total} in total) and in the results here.\n\n"
        "It looks at the screen when the run ends, so it works best with Picture watch ending each run "
        "on the results screen (the RETRY button).")

    def _load_result_pictures(self):
        self.result_pictures = []
        if image_watch is None:
            return
        saved = self.settings.get("result_pictures")
        if not isinstance(saved, list):
            return
        for entry in saved:
            kind = entry.get("kind") if entry.get("kind") in (stats.WIN, stats.LOSS) else stats.WIN
            pic = core.saved_picture(entry["file"], screen_h=entry.get("screen_h"), kind=kind) \
                if isinstance(entry, dict) and entry.get("file") else None
            if pic is None:
                continue
            if isinstance(entry.get("found_factor"), (int, float)) and isinstance(entry.get("found_screen"), list):
                pic["found_factor"], pic["found_screen"] = entry["found_factor"], entry["found_screen"]
                if isinstance(entry.get("found_step"), int):
                    pic["found_step"] = entry["found_step"]
            self.result_pictures.append(pic)

    def _save_result_pictures(self):
        self.settings["result_pictures"] = [
            dict({"file": p["file"], "screen_h": p["screen_h"], "kind": p["kind"]},
                 **{k: p[k] for k in ("found_factor", "found_screen", "found_step") if k in p})
            for p in self.result_pictures]
        self._save_settings()

    def _add_result_picture(self, img, kind, screen_h=None):
        name = f"result_{int(time.time() * 1000)}.png"
        image_watch.save_image(os.path.join(core.watch_dir(), name), img)
        self.result_pictures.append({"img": img, "file": name, "screen_h": screen_h, "kind": kind})
        self._save_result_pictures()
        self._show_result_pictures()

    BUILTINS = {stats.WIN: (core.BUILTIN_WIN_PICTURE, core.BUILTIN_WIN_PICTURE_SCREEN_H),
                stats.LOSS: (core.BUILTIN_LOSS_PICTURE, core.BUILTIN_LOSS_PICTURE_SCREEN_H)}

    def add_builtin_result(self, kind=stats.WIN):
        try:
            name, screen_h = self.BUILTINS[kind]
            self._add_result_picture(image_watch.load_image(core.resource_path(name)), kind, screen_h)
        except Exception as exc:
            messagebox.showerror("Macro Recorder", f"Couldn't add the built-in picture:\n{exc}",
                                 parent=self.settings_win)

    def _result_from_screen(self, kind):
        if self.recording or self.playing:
            return
        self.settings_win.withdraw()
        self.root.withdraw()

        def picked(img, screen_h):
            self._add_result_picture(img, kind, screen_h)
        self.root.after(300, lambda: self._show_picker(on_pick=picked, hidden=(self.settings_win,)))

    def _result_from_file(self, kind):
        path = filedialog.askopenfilename(parent=self.settings_win,
                                          filetypes=[("Pictures", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")])
        if path:
            try:
                self._add_result_picture(image_watch.load_image(path), kind, None)
            except Exception as exc:
                messagebox.showerror("Macro Recorder", f"Couldn't use that picture:\n{exc}", parent=self.settings_win)

    def _remove_result_picture(self, pic):
        if self.recording or self.playing:
            return
        if pic in self.result_pictures:
            self.result_pictures.remove(pic)  # (the file goes once the change is applied)
        self._save_result_pictures()
        self._show_result_pictures()

    def test_result_pictures(self):
        if not self.result_pictures:
            messagebox.showinfo("Macro Recorder", "Add a picture first.", parent=self.settings_win)
            return
        self._save_settings()
        need = self.settings.get("results_match", core.RESULTS_MATCH_DEFAULT)
        lines = []
        try:
            screen = self._hide_own_window(image_watch.grab_screen(), image_watch.screen_origin())
            for kind, word in ((stats.WIN, "Completed"), (stats.LOSS, "Failed")):
                for i, p in enumerate([p for p in self.result_pictures if p["kind"] == kind], start=1):
                    m = image_watch.Matcher(p["img"], picked_screen_h=p["screen_h"], screen_h=self.screen_h,
                                            work_height=core.RESULT_WORK_HEIGHT)
                    pct = round(m.find(screen)[0] * 100)
                    lines.append(f"{word} picture {i}: {pct}%  ({'seen' if pct >= need else 'not seen'})")
        except Exception as exc:
            messagebox.showerror("Macro Recorder", f"Couldn't check the screen:\n{exc}", parent=self.settings_win)
            return
        messagebox.showinfo("Macro Recorder", f"How well each picture matches the screen right now (seen from "
                            f"{need}%):\n\n" + "\n".join(lines), parent=self.settings_win)

    def _load_result_pictures_first(self):
        """At start: the result pictures (read when first used). On the very first start, the
        built-in MISSION COMPLETED and MISSION FAILED pictures are added, ready to use; a copy that
        already had result pictures gets the MISSION FAILED one once, if it has no "failed" picture."""
        first = "result_pictures" not in self.settings
        if image_watch is not None and (first or not self.settings.get("builtin_failed_added")):
            self._load_result_pictures()
            kinds = [stats.WIN, stats.LOSS] if first else []
            if not first and not any(p["kind"] == stats.LOSS for p in self.result_pictures):
                kinds = [stats.LOSS]
            for kind in kinds:
                try:
                    name, screen_h = self.BUILTINS[kind]
                    self._add_result_picture(image_watch.load_image(core.resource_path(name)), kind, screen_h)
                except Exception as exc:
                    diag.error("Couldn't add a built-in result picture", exc)
            self.settings["builtin_failed_added"] = True
            core.save_settings(self.settings)
        self._load_result_pictures()

    def _build_results_tab(self, f):
        self._section(f, "MISSION RESULTS", first=True)
        self._switch_row(f, "Count wins and losses while playing", self.results_var, info=self.RESULTS_HELP)
        self.result_lists = {}
        self.result_buttons = []
        for kind, title in ((stats.WIN, "MISSION COMPLETED  (counts as a win)"),
                            (stats.LOSS, "MISSION FAILED  (counts as a loss)")):
            tk.Label(f, text=title, bg=BG, fg=MUTED, font=F_SECTION, anchor="w").pack(fill="x", pady=(10, 2))
            lst = tk.Frame(f, bg=BG)
            lst.pack(fill="x")
            self.result_lists[kind] = lst
            row = tk.Frame(f, bg=BG)
            row.pack(fill="x", pady=(4, 0))
            b1 = ttk.Button(row, text="Add from screen…", command=lambda k=kind: self._result_from_screen(k))
            b2 = ttk.Button(row, text="Picture file…", command=lambda k=kind: self._result_from_file(k))
            b1.pack(side="left")
            b2.pack(side="left", padx=6)
            self.result_buttons += [b1, b2]
            b3 = ttk.Button(row, text="Add built-in " + ("MISSION COMPLETED" if kind == stats.WIN else "MISSION FAILED"),
                            command=lambda k=kind: self.add_builtin_result(k))
            b3.pack(side="left")
            self.result_buttons.append(b3)
        row = self._row(f, "Match", "%  (80-90 suits most pictures)")
        ttk.Spinbox(row, from_=50, to=99, width=4, textvariable=self.results_match_var,
                    command=self._save_settings).pack(side="right")
        b = ttk.Button(row, text="Test now", command=self.test_result_pictures)
        b.pack(side="right", padx=(0, 10))
        self.result_buttons.append(b)
        self._switch_row(f, "Count divine fragments", self.drops_var, "by their pink-to-blue frame",
                         info=self.DROPS_HELP)
        self._section(f, "RESULTS")
        tk.Label(f, textvariable=self.session_var, bg=BG, fg=TEXT, font=F_SMALL, anchor="w", justify="left").pack(
            fill="x")
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", pady=(6, 0))
        tk.Label(row, textvariable=self.alltime_var, bg=BG, fg=MUTED, font=F_SMALL, anchor="w",
                 justify="left").pack(side="left")
        link(row, "Reset", self._reset_all_time).pack(side="right")
        for var in (self.session_var, self.alltime_var):
            var.trace_add("write", lambda *a: self.root.after_idle(self._settings_text_changed))
        if image_watch is None:
            for b in self.result_buttons:
                b.config(state="disabled")
        self._show_result_pictures()
        self._show_session()

    def _show_result_pictures(self):
        if not hasattr(self, "result_lists"):
            return
        self.result_thumbs = []
        for kind, lst in self.result_lists.items():
            for child in lst.winfo_children():
                child.destroy()
            pics = [p for p in self.result_pictures if p["kind"] == kind]
            if not pics:
                tk.Label(lst, text="No picture yet", bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x")
            for p in pics:
                r = tk.Frame(lst, bg=BG)
                r.pack(fill="x", pady=1)
                thumb, w, h = core.picture_thumb(p, 260, 34)
                self.result_thumbs.append(thumb)
                tk.Label(r, image=thumb, bg=BG).pack(side="left")
                tk.Label(r, text=f"  {w} x {h}", bg=BG, fg=MUTED, font=F_SMALL).pack(side="left")
                link(r, "Remove", lambda p=p: self._remove_result_picture(p)).pack(side="right")
        if getattr(self, "settings_backdrop", None) is not None and self.settings_win.winfo_viewable():
            self.root.after_idle(self.settings_backdrop.repaint)

    def _show_session(self):
        if not hasattr(self, "session_var"):
            return
        sess = self.session
        if sess.runs:
            v = sess.values()
            self.session_var.set(
                f"Last session ({v['macro']}): {v['run']} runs, completed {v['completed']}, failed {v['failed']}, "
                f"unknown {v['unknown']}\nWin rate {v['winrate']} · win streak {v['streak']} · average run "
                f"{v['average']} · total {v['total']} · divine fragments {v['fragments_session']}")
        a = self.settings.get("stats_all") if isinstance(self.settings.get("stats_all"), dict) else {}
        runs = a.get("runs", 0)
        self.alltime_var.set(f"All time: {runs} runs · {a.get('wins', 0)} won · {a.get('losses', 0)} failed · "
                             f"{a.get('unknown', 0)} unknown · {stats.duration_text(a.get('seconds', 0))} played"
                             f"\nDivine fragments: {a.get('fragments', 0)}"
                             if runs else "All time: nothing counted yet")

    def _remember_found_sizes(self):
        saved = self.settings.get("result_pictures")
        if not isinstance(saved, list):
            return
        by_file = {p["file"]: p for p in self.result_pictures}
        changed = False
        for entry in saved:
            p = by_file.get(entry.get("file"))
            if p and "found_factor" in p and (entry.get("found_factor"), entry.get("found_step")) != \
                    (p["found_factor"], p.get("found_step")):
                entry["found_factor"], entry["found_screen"] = p["found_factor"], p["found_screen"]
                if "found_step" in p:
                    entry["found_step"] = p["found_step"]
                changed = True
        if changed:
            core.save_settings(self.settings)

    def _add_to_all_time(self):
        sess = self.session
        if not sess.runs:
            return
        a = self.settings.get("stats_all")
        if not isinstance(a, dict):
            a = self.settings["stats_all"] = {}
        a["runs"] = a.get("runs", 0) + len(sess.runs)
        a["wins"] = a.get("wins", 0) + sess.count(stats.WIN)
        a["losses"] = a.get("losses", 0) + sess.count(stats.LOSS)
        a["unknown"] = a.get("unknown", 0) + sess.count(stats.UNKNOWN)
        a["fragments"] = a.get("fragments", 0) + sum(sess.fragments)
        a["seconds"] = a.get("seconds", 0) + int(time.time() - sess.started)
        core.save_settings(self.settings)

    def _reset_all_time(self):
        if messagebox.askyesno("Macro Recorder", "Reset the all-time results to zero?", parent=self.settings_win):
            self.settings["stats_all"] = {}
            core.save_settings(self.settings)
            self._show_session()
