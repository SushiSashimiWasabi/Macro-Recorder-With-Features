"""Settings > Results: the pictures that mean a run was won or lost, and the results shown.

Part of the dark window: ModernMacroRecorder (modern_ui.py) inherits this class.
"""

from ui_common import *  # noqa: F401,F403  (colours, fonts, widgets, tk, core, the other modules)


class ResultsMixin:
    RESULTS_HELP = (
        "While a macro plays, the app looks for the result pictures on your main screen. A \"mission "
        "completed\" picture counts the run as won, a \"mission failed\" one as lost, and a run where "
        "neither showed as unknown. The results (wins, losses, streak, win rate, run times) show in the "
        "timer at the top, here, and in the Discord messages.\n\n"
        "The pictures are in Picture watch: AOT:R's gold MISSION COMPLETED and MISSION FAILED titles come "
        "with the app, and you can add your own (choose \"This picture is: MISSION COMPLETED\" for it).")

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
            if not isinstance(entry, dict) or not entry.get("file"):
                continue
            kind = entry.get("kind") if entry.get("kind") in (stats.WIN, stats.LOSS) else stats.WIN
            fields = core.group_fields(entry)
            if isinstance(entry.get("name"), str) and entry["name"]:
                fields["name"] = entry["name"]
            pic = core.saved_picture(entry["file"], screen_h=entry.get("screen_h"), kind=kind, **fields)
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
                 **{k: p[k] for k in ("found_factor", "found_screen", "found_step") if k in p},
                 **({"name": p["name"]} if p.get("name") else {}), **core.group_fields(p))
            for p in self.result_pictures]
        self._save_settings()

    def _add_result_picture(self, img, kind, screen_h=None, fields=None):
        name = f"result_{int(time.time() * 1000)}.png"
        image_watch.save_image(os.path.join(core.watch_dir(), name), img)
        self.result_pictures.append(dict({"img": img, "file": name, "screen_h": screen_h, "kind": kind},
                                         **(fields or {})))
        self._save_result_pictures()
        self._show_result_pictures()

    BUILTINS = {stats.WIN: (core.BUILTIN_WIN_PICTURE, core.BUILTIN_WIN_PICTURE_SCREEN_H),
                stats.LOSS: (core.BUILTIN_LOSS_PICTURE, core.BUILTIN_LOSS_PICTURE_SCREEN_H)}

    def add_builtin_result(self, kind=stats.WIN):
        try:
            name, screen_h = self.BUILTINS[kind]
            key = "completed" if kind == stats.WIN else "failed"
            self._add_result_picture(image_watch.load_image(core.resource_path(name)), kind, screen_h,
                                     fields=dict(core.BUILTINS[key][3], builtin=key))
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
        """At start: the result pictures (read when first used), then the Picture watch groups (on the
        very first start, or the first start of 2.9, that adds the built-in pictures)."""
        self._load_result_pictures()
        self._setup_picture_groups()

    def _build_results_tab(self, f):
        self._section(f, "RUN RESULTS (AOT:R)", first=True)
        row = self._row(f, "Run stats", "win rate, run times, fragments an hour, a chart of each day")
        ttk.Button(row, text="Open…", command=self.open_stats).pack(side="right")
        self._switch_row(f, "Count wins and losses while playing", self.results_var, info=self.RESULTS_HELP)
        # the MISSION COMPLETED / FAILED pictures and their Match are in the Picture watch window (2.9)
        row = self._row(f, "Win / loss pictures", "MISSION COMPLETED / FAILED: in Picture watch > AOT:R")
        b = ttk.Button(row, text="Open Picture watch…", command=lambda: self.open_picture_watch("aotr"))
        b.pack(side="right")
        self.result_buttons = [b]
        self._switch_row(f, "Count divine fragments (AOT:R)", self.drops_var, "by their pink-to-blue frame",
                         info=self.DROPS_HELP)
        self._build_milestones_rows(f)  # (Preview 4)
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
        self._show_session()

    def _show_result_pictures(self):
        """(The result pictures are shown in the Picture watch window now.)"""
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
        sess.added = True  # (Preview 4: milestones then count it from the all-time results only)
        core.save_settings(self.settings)

    def _reset_all_time(self):
        if messagebox.askyesno("Macro Recorder", "Reset the all-time results to zero?", parent=self.settings_win):
            self.settings["stats_all"] = {}
            core.save_settings(self.settings)
            self._show_session()
