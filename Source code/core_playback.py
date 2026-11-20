"""Starting a play: fitting the steps, reading other macros, the play worker.

Part of the core MacroRecorder class (split out of macro_recorder.py in 2.13): its methods are
unchanged; a name that lives in macro_recorder itself is written core.name."""
import diag
import importers
import macro_steps as workflow
import os
import run_history
import stats
import step_more
import threading
import time
import tkinter as tk
import window_tools
import macro_recorder as core


class CorePlaybackMixin:
    def play(self):
        test = getattr(self, "test_play", None)  # (2.11) {"mode": "test" / "ghost", "steps", "screen", "program"}
        if self.recording or self.playing or self.record_countdown_left > 0 \
                or not (self.events or self.actions or test) or self.capture_callback is not None:
            return
        try:
            repeats = max(1, int(self.repeat_var.get()))
        except (tk.TclError, ValueError):
            repeats = 1
        loop = self.loop_var.get()
        if test:
            repeats, loop = 1, False
        speed = self._check_speed()
        if speed is None:
            return
        play_on = self._read_play_on()
        if play_on is None or not self._read_made_for():
            return
        # move mouse positions from the size the macro was made for to the size it's played on
        if test:
            events, self.fit_note = self._fit_steps(test["steps"], test.get("screen"), test.get("program"), play_on)
        else:
            events = self._events_for_play(play_on)  # (the macro's steps, fitted to this screen)
        try:
            # "Play another macro" steps: those macros are read now, so a missing file shows at once
            own = (self._macro_key(self.current_file),) if self.current_file else ()
            events = self._resolve_macros(events, play_on, own)
        except Exception as exc:
            core.messagebox.showerror("Macro Recorder", f"Couldn't use a \"Play another macro\" step:\n{exc}")
            return
        try:
            # (2.11: a watch-only test never looks for pictures)
            self.wait_matchers = {} if test and test["mode"] == "ghost" else self._make_wait_matchers(events)
        except Exception as exc:
            core.messagebox.showerror("Macro Recorder", f"Couldn't use a \"Wait for a picture\" step:\n{exc}")
            return
        ready = self._ready_seconds()
        bg = None
        if self.target_var.get() != core.SCREEN_TARGET and not (test and test["mode"] == "ghost"):
            hwnd = self._selected_hwnd()
            if not hwnd or not core.background.is_usable(hwnd):
                core.messagebox.showerror("Macro Recorder", "That window is gone. Pick it again in \"Play into\".")
                self._refresh_windows()
                return
            if core.background.is_minimized(hwnd):
                core.messagebox.showerror("Macro Recorder", "That window is minimized. Restore it first "
                                     "(it can stay behind other windows).")
                return
            bg = core.background.BackgroundPlayer(hwnd)
        self._save_settings()
        watch = None
        if core.image_watch is not None and self.watch_var.get() and self._active_watch_pictures() and not test:
            # (with no picture on for this macro, it plays without watching: the status line says so)
            try:
                watch = {
                    "matchers": self._make_matchers(),
                    "need": self.settings.get("watch_match", 80) / 100.0,
                    "wait": self.settings.get("watch_wait", 3),
                    "end_wait": self.settings.get("watch_end_wait", 60),
                    "click": bool(self.watch_click_var.get()),
                    "macros": {},  # file -> the steps of a macro a picture plays or switches to
                    "confirm": {},  # id(picture) -> what to look for after a rejoin macro
                }
                self._prepare_watch_actions(watch, play_on)
            except Exception as exc:
                core.messagebox.showerror("Macro Recorder", f"Couldn't use the picture:\n{exc}")
                return
        # "If the game closes": its rejoin macro is read now, so a missing file shows at once
        self.closed_steps = None
        closed = self._closed_settings()
        rejoin = (getattr(self, "start_rejoin_opts", None) or {}).get("macro") or closed["macro"]
        if getattr(self, "start_rejoin_first", False) and rejoin and self._find_macro_file(rejoin):
            try:  # (2.12: open the game first: the alarm's rejoin macro, or "If the game closes"'s)
                self.closed_steps = self._load_for_play(rejoin, play_on)
            except Exception as exc:
                diag.error("Couldn't read the rejoin macro for start-up", exc)
        if test:
            pass  # (a test never gets the game back: it stops instead)
        elif closed["action"] == "reopen" and closed["macro"] and not self._find_macro_file(closed["macro"]):
            diag.info("The rejoin macro of \"If the game closes\" isn't there any more: only the game is opened")
        elif closed["action"] == "reopen" and closed["macro"]:
            try:
                self.closed_steps = self._load_for_play(closed["macro"], play_on)
                self.wait_matchers.update(self._make_wait_matchers(self.closed_steps))
            except Exception as exc:
                core.messagebox.showerror("Macro Recorder", "Couldn't use the rejoin macro of \"If the game "
                                     "closes\" (Settings > Playback):\n" + str(exc))
                return
        self.result_matchers = [] if test else self._build_result_matchers()
        self.stuck_steps = None
        stuck = self._stuck_settings()
        if not test and stuck["on"] and stuck["action"] == "macro" and stuck["macro"]:
            if not self._find_macro_file(stuck["macro"]):
                diag.info("The macro of \"If a run gets stuck\" isn't there any more: the run only starts over")
            else:
                try:
                    self.stuck_steps = self._load_for_play(stuck["macro"], play_on)
                except Exception as exc:
                    diag.error("Couldn't read the macro of \"If a run gets stuck\"", exc)
        alltime = self.settings.get("stats_all") if isinstance(self.settings.get("stats_all"), dict) else {}
        if not test or getattr(self, "session", None) is None:  # (a test keeps the last real session on show)
            self.session = stats.Session(self._macro_name(),
                                         fragments_before=core.int_setting(alltime, "fragments", 0, 0, 10 ** 9),
                                         streak_before=core.int_setting(alltime, "streak_now", 0, 0, 10 ** 9),
                                         best_streak_before=core.int_setting(alltime, "best_streak", 0, 0, 10 ** 9))
        if watch is not None:
            watch["limit_count"] = core.int_setting(self.settings, "watch_limit_count", 10, 0, 1000)
            watch["limit_seconds"] = core.int_setting(self.settings, "watch_limit_seconds", 60, 1, 3600)
            watch["shift_lock"] = bool(self.settings.get("watch_shift_lock", True))
        self.auto_stop = None if test else self._prepare_auto_stop()
        self.auto_stopped = None
        self.play_vary = self._vary_now()
        self._start_counters(events)
        if watch is not None and not watch["matchers"]:
            watch = None  # (only pictures that count were on: no restarting picture to watch for)
        self.count_list = [] if test else self._count_pictures()  # (on this thread: it reads a Tk switch)
        self.stop_play.clear()
        self.stop_reason = None
        self.away_started = None
        self.away_total = 0.0
        self.playing = True
        self.countdown_left = ready
        self.play_note = ""
        self.ghost = bool(test and test["mode"] == "ghost")
        if test:
            self.play_note = ("Watch only: nothing is pressed" if self.ghost else "Test play: not counted")
        elif core.image_watch is not None and self.watch_var.get():
            n = len(watch["matchers"]) if watch else 0
            self.play_note = (f"Watching {n} picture{'s' if n != 1 else ''}" if n
                              else "Picture watch: no picture is on for this macro")
        self.play_bg = bg
        self._refresh()
        diag.info(f"Playing: {workflow.count_events(events)} recorded actions in {len(events)} step(s), speed {speed:g}, "
                  + ("loop" if loop else f"{repeats} time(s)") + (", picture watch" if watch else "")
                  + (", background window" if bg else ""))
        threading.Thread(target=self._play_worker,
                         args=(events, repeats, loop, speed, bg, ready, watch),
                         daemon=True).start()

    def _build_result_matchers(self):
        """The result pictures, ready to look for (each at its own size and two others)."""
        matchers = []
        if core.image_watch is not None and self.settings.get("results_enabled", True):
            for pic in self._active_result_pictures():
                # a result title can show at quite another size than when the picture was taken (other
                # screen or window size), so it's also looked for a quarter smaller and a third bigger
                base_h = pic["screen_h"] or self.screen_h
                # the size it was found at before (remembered per picture and screen) goes first; the
                # other sizes are only looked for if it isn't found at that size for a while
                known = pic.get("found_factor") if pic.get("found_screen") == [self.screen_w, self.screen_h] \
                    else None
                factors = [known] + [f for f in (1.0, 1.33, 0.75) if f != known] if known else [1.0, 1.33, 0.75]
                for f in factors:
                    try:
                        m = core.image_watch.Matcher(pic["img"], picked_screen_h=base_h * f, ignore_background=True,
                                                screen_h=self.screen_h, work_height=core.RESULT_WORK_HEIGHT)
                        m.kind = pic["kind"]
                        m.picture_id = id(pic)
                        m.picture = pic
                        m.factor = f
                        m.fallback = bool(known) and f != known
                        step = pic.get("found_step")
                        if f == known and isinstance(step, int) and 0 <= step < len(m.templates):
                            m.last_best = step  # the exact size it matched at last time is tried first
                        matchers.append(m)
                    except Exception as exc:
                        if f == 1.0:
                            diag.error("A result picture couldn't be used", exc)
        return matchers

    def macro_steps(self):
        """The macro as steps (one recorded step when it was never edited into more)."""
        return self.actions if self.actions else workflow.from_events(self.events)

    def set_steps(self, actions):
        """Replace the macro with these steps (from the Edit window)."""
        actions = workflow.ensure_ids(actions)
        if workflow.is_simple(actions):
            self.actions = None
            self.events = actions[0]["events"]
        else:
            self.actions = actions
            self.events = workflow.all_events(actions)

    def _events_for_play(self, play_on):
        """The macro's steps with mouse positions fitted to this screen, or to the game window
        when Settings > Playback > Fit to says so (and the macro knows its window)."""
        steps, self.fit_note = self._fit_steps(self.macro_steps(), self.macro_screen, self.macro_program, play_on)
        return steps

    def _fit_steps(self, steps, made_for, program, play_on):
        """(a macro's steps fitted to this screen or the game window, a note about how)."""
        note = ""
        fit = None
        if self.settings.get("fit_to", "window") == "window":
            src = (program or {}).get("client")
            dst = self._game_client_rect(program)
            if src and dst and len(src) == 4 and src[3] > 0:
                if tuple(src) == tuple(dst):
                    fit = lambda evs: [dict(ev) for ev in evs]  # noqa: E731
                else:
                    note = "fitted to the game window"
                    fit = lambda evs: core.scale_events_rect(evs, src, dst)  # noqa: E731
            else:
                note = ("the game window wasn't found, so it's fitted to the screen" if src
                        else "this macro doesn't know its window, so it's fitted to the screen")
        if fit is None:
            fit = lambda evs: core.scale_events(evs, made_for, play_on)  # noqa: E731
        # (older recordings may hold a mouse button down the whole run: see drop_stray_clicks)
        return workflow.map_points(steps, lambda evs: fit(core.drop_stray_clicks(evs))), note

    @staticmethod
    def _macro_key(path):
        return os.path.normcase(os.path.abspath(path))

    def _find_macro_file(self, path):
        """Where a macro named in a step or a picture's action is now: its saved place, or (when the
        macros were moved or shared together) the folder of the open macro."""
        if not isinstance(path, str) or not path:
            return None
        if os.name == "nt" and path.replace("/", "\\").startswith("\\"):
            # (security) a file on another computer (\\server\share, \\?\UNC\..., \??\UNC\...): just looking at it
            # could send that computer your Windows login. A Windows path that starts with a slash is never a
            # plain drive path, so only the file name is used, beside the open macro.
            path = os.path.basename(path.replace("\\", "/"))
        if not os.path.isabs(path):
            # (2.9.1) saved relative to the macro's own folder (see shared_macro_path); never above it
            if ".." in path.replace("\\", "/").split("/") or not self.current_file:
                path = os.path.basename(path)
            else:
                inside = os.path.join(os.path.dirname(self.current_file), path)
                if os.path.isfile(inside):
                    return inside
        elif os.path.isfile(path):
            return path
        if self.current_file:
            beside = os.path.join(os.path.dirname(self.current_file), os.path.basename(path))
            if os.path.isfile(beside):
                return beside
        return None

    def _read_macro_file(self, path):
        """Another macro's steps, read without opening it in the window:
        {"steps", "screen" (w, h) or None, "program", "name"}. Raises ValueError with the reason."""
        found = self._find_macro_file(path)
        name = os.path.splitext(os.path.basename(path or ""))[0] or "?"
        if not found:
            raise ValueError(f"the macro \"{name}\" isn't there any more ({path})")
        kept = getattr(self, "file_data", None)
        try:
            program = None
            try:
                events, screen = self._read_own_file(found)
                data = self.file_data
                program = data.get("program")
                raw = data.get("actions")
                if isinstance(raw, list) and raw and all(isinstance(a, dict) for a in raw):
                    steps = workflow.ensure_ids(core.expand_steps(raw))
                else:
                    steps = workflow.from_events(events)
            except (ValueError, RecursionError, KeyError, TypeError, OSError):
                try:
                    imported = importers.import_file(found)
                except Exception as exc:
                    raise ValueError(f"the macro \"{name}\" couldn't be read: {exc}") from None
                if not imported.events:
                    raise ValueError(f"the macro \"{name}\" has no actions") from None
                imported.events.sort(key=lambda ev: ev["t"])
                steps = workflow.from_events(imported.events)
                screen = {"width": imported.screen[0], "height": imported.screen[1]} if imported.screen else {}
                program = imported.program
        finally:
            self.file_data = kept
        try:
            made_for = (int(screen.get("width")), int(screen.get("height")))
            if made_for[0] <= 0 or made_for[1] <= 0:
                made_for = None
        except (TypeError, ValueError, AttributeError):
            made_for = None
        return {"steps": steps, "screen": made_for, "program": program if isinstance(program, dict) else None,
                "name": name}

    def _load_for_play(self, path, play_on, chain=()):
        """Another macro's steps, fitted and ready to play (the macros it plays itself included)."""
        key = self._macro_key(self._find_macro_file(path) or path or "")
        name = os.path.splitext(os.path.basename(path or ""))[0]
        if key in chain:
            raise ValueError(f"the macro \"{name}\" would end up playing itself (macros that play each other "
                             "in a circle)")
        if len(chain) >= core.MAX_MACRO_DEPTH:
            raise ValueError("too many macros inside each other")
        info = self._read_macro_file(path)
        steps, _note = self._fit_steps(info["steps"], info["screen"], info["program"], play_on)
        return self._resolve_macros(steps, play_on, chain + (key,))

    def _resolve_macros(self, steps, play_on, chain=()):
        """The steps with every "Play another macro" step turned into that macro's own steps
        (a "macro" group that playback runs a number of times)."""
        out = []
        for a in steps:
            if a.get("kind") == "play_macro":
                if a.get("off"):
                    continue
                if not a.get("file"):
                    raise ValueError("a \"Play another macro\" step has no macro chosen yet: choose one in Edit")
                if not self._find_macro_file(a["file"]):
                    # (2.10: nothing stops Play; Check my macro tells about it)
                    diag.info(f"Skipped a \"Play another macro\" step: \"{os.path.basename(a['file'])}\" "
                              "isn't there any more")
                    continue
                if a.get("on_fail") and not self._find_macro_file(a["on_fail"]):
                    diag.info(f"A \"Play another macro\" step's macro for when it fails isn't there any more "
                              f"(\"{os.path.basename(a['on_fail'])}\"): left out")
                    a = dict(a, on_fail=None)
                out.append({"kind": "macro", "id": a.get("id"), "times": max(1, int(a.get("times", 1) or 1)),
                            "counts": bool(a.get("counts", True)),
                            "name": os.path.splitext(os.path.basename(a["file"]))[0],
                            "profile": a.get("profile"), "speed": a.get("speed") or 0,
                            "on_fail": (self._load_for_play(a["on_fail"], play_on, chain)
                                        if a.get("on_fail") else None),
                            "on_fail_name": os.path.splitext(os.path.basename(a.get("on_fail") or ""))[0],
                            "actions": self._load_for_play(a["file"], play_on, chain)})
            elif isinstance(a.get("actions"), list):
                b = self._resolve_more_macros(dict(a), play_on, chain)
                b["actions"] = self._resolve_macros(a["actions"], play_on, chain)
                out.append(b)
            else:
                out.append(self._resolve_more_macros(a, play_on, chain))
        return out

    def _resolve_more_macros(self, a, play_on, chain):
        """(2.12) "Run another macro afterwards" / "if it doesn't show: play a macro" / "if every try
        fails: play a macro": that macro's steps, read now (a missing one is left out and logged)."""
        for key in step_more.MACRO_KEYS:
            path = a.get(key)
            if not path or a.get("off"):
                continue
            a = dict(a)
            if not self._find_macro_file(path):
                diag.info(f"A step's macro \"{os.path.basename(path)}\" isn't there any more: left out")
                a[key] = ""
                continue
            a[key.replace("_macro", "_steps")] = self._load_for_play(path, play_on, chain)
        return a

    @staticmethod
    def _has_counted_macro(steps):
        return any(a.get("kind") == "macro" and a.get("counts", True) and not a.get("off")
                   for a, _l, _i, _p in workflow.walk(steps))

    def _prepare_watch_actions(self, watch, play_on):
        """Read the macros that pictures play or switch to, and the pictures that confirm a rejoin."""
        for n, pic in enumerate(self._active_watch_pictures(), start=1):
            action = pic.get("action", "restart")
            if action in core.WATCH_NEED_MACRO:
                if pic.get("macro") and not self._find_macro_file(pic["macro"]):
                    diag.info(f"{core.watch_name(pic, n)}: its macro \"{os.path.basename(pic['macro'])}\" isn't "
                              "there any more, so it only does the rest of its action")
                elif pic.get("macro"):
                    if pic["macro"] not in watch["macros"]:
                        steps = self._load_for_play(pic["macro"], play_on)
                        watch["macros"][pic["macro"]] = steps
                        self.wait_matchers.update(self._make_wait_matchers(steps))
                elif action != "recover":
                    raise ValueError(f"{core.watch_name(pic, n)} has no macro chosen yet (Picture watch)")
            if action == "recover" and pic.get("confirm_file"):
                path = os.path.join(core.watch_dir(), pic["confirm_file"])
                if os.path.isfile(path):
                    watch["confirm"][id(pic)] = core.image_watch.Matcher(
                        core.image_watch.load_image(path), picked_screen_h=pic.get("confirm_screen_h"),
                        ignore_background=True, screen_h=self.screen_h)

    def _game_client_rect(self, program=None):
        """Where the inside of the game's window is now: the macro's program if it's open, else the
        window in front (if it isn't this app)."""
        exe = (program or self.macro_program or {}).get("exe")
        wins = window_tools.windows_of(exe) if exe else []
        if not wins:
            fg = window_tools.foreground()
            if fg and window_tools.pid_of(fg) != os.getpid():
                wins = [fg]
        return window_tools.client_rect(wins[0]) if wins else None

    def _make_wait_matchers(self, program):
        """The pictures of "Wait for a picture" steps and of If / Retry conditions, ready to look for
        (by the id of the dict that holds the picture)."""
        found = {}
        holders = []
        for a, _lst, _i, _p in workflow.walk(program):
            if a.get("off"):
                continue
            kind = a.get("kind")
            if kind == "wait_picture":
                holders.append(a)
            elif kind in ("if", "retry") or (kind == "repeat" and a.get("mode") == "until"):
                c = a.get("condition") or {}
                holders += [h for h in [c] + list(c.get("more") or [])
                            if h.get("type", "picture") == "picture"]  # (2.12: AND / OR parts too)
            elif kind == "recorded":
                holders.extend(ev for ev in a.get("events", []) if ev.get("type") == "wait_picture")
        for n, h in enumerate(holders, start=1):
            if h.get("color_on"):
                continue  # (2.12: a colour check, not a picture)
            if not h.get("png"):
                # (2.10: nothing stops Play; the step is skipped and Check my macro tells about it)
                diag.info(f"A picture step or condition ({n}) has no picture: it's skipped")
                continue
            if core.image_watch is None:
                raise ValueError("this copy was built without picture support")
            import base64

            import numpy as np

            try:
                data = np.frombuffer(base64.b64decode(h["png"]), np.uint8)
                img = core.image_watch.cv2.imdecode(data, core.image_watch.cv2.IMREAD_COLOR)
            except Exception:  # (not a picture, or far too big: see OPENCV_IO_MAX_IMAGE_PIXELS)
                img = None
            if img is None:
                raise ValueError(f"picture {n} is broken")
            found[id(h)] = core.image_watch.Matcher(img, picked_screen_h=h.get("screen_h"), ignore_background=True,
                                               screen_h=self.screen_h)
        return found

    def stop_playback(self):
        self.stop_play.set()

    def _set_countdown(self, seconds):
        def update():
            self.countdown_left = seconds
            self._refresh()
        self._call_ui(update)

    def _picture_seen(self):
        """The watched-for picture showed up (the dark window plays a sound here)."""

    def _set_note(self, text):
        def update():
            if self.play_note == text:
                return  # (shown already: no redraw, e.g. 10 times a second while paused)
            self.play_note = text
            self._refresh()
        self._call_ui(update)

    def _playback_done(self):
        if not getattr(self, "test_play", None):
            self._save_kept_counters()
        self.playing = False
        self.countdown_left = 0
        self.play_note = ""
        self._refresh()
        diag.info("Playback ended" + (f": {self.stop_reason}" if self.stop_reason else "")
                  + (f" (stopped by itself: {self.auto_stopped})" if getattr(self, "auto_stopped", None) else ""))
        run_history.save()
        if getattr(self, "auto_stopped", None) and type(self) is core.MacroRecorder:
            self._auto_stop_then()
        if self.stop_reason and type(self) is core.MacroRecorder:  # (the dark window shows it its own way)
            core.messagebox.showwarning("Macro Recorder", self.stop_reason)

    def _play_worker(self, events, repeats, loop, speed, bg=None, ready=0, watch=None):
        held_keys, held_buttons = set(), set()
        self.held_lists = (held_keys, held_buttons)
        window_tools.set_thread_priority(1)  # playback goes before the screen checks
        window_tools.keep_awake(True)  # no sleep or screen-off during long waits (let go of below)
        self._look_summary()  # (the health line's picture-check times start from this run)
        seen = threading.Event()  # a watched-for picture showed up
        watch_done = threading.Event()
        # count: finished runs; restarts: when a picture did its action (for the runaway limit);
        # starts_over: when a "Start over" step ran (the same kind of limit)
        state = {"count": 0, "restarts": [], "starts_over": []}
        self.play_state = state
        try:
            # "get ready" countdown; Stop cancels it
            for left in range(ready, 0, -1):
                self._set_countdown(left)
                if self.stop_play.wait(1.0):
                    return
            self._set_countdown(0)
            self.play_game_exe = self._game_exe_now()
            test = getattr(self, "test_play", None)
            closed = None if test else self._closed_watcher(bg)
            away = None if getattr(self, "ghost", False) else (self._away_watcher(bg, closed) or closed)
            # (2.12) the stuck run guard is asked as often as the "game in front" check
            away = core.combine_checks(away, None if test else self._stuck_watcher())
            self.late_result = None  # (2.12) the last Unknown run, while its result may still show
            self.timer_text = None  # (2.12) what Do maths / a Note shows on the timer
            self.last_found = None  # (2.12) where a picture / colour was last found (Click: where it was found)
            if self.result_matchers:
                self.result_state = {}
                threading.Thread(target=self._result_worker, args=(self.result_matchers, watch_done),
                                 daemon=True).start()
            if watch is not None:
                threading.Thread(target=self._watch_worker, args=(watch, seen, watch_done),
                                 daemon=True).start()
            ctx = {"speed": speed, "bg": bg, "held": (held_keys, held_buttons), "seen": seen, "away": away,
                   "watch": watch, "state": state, "vary": self.play_vary}
            threading.Thread(target=self._health_worker, args=(watch_done,), daemon=True,
                             name="health").start()
            counting = [] if test else getattr(self, "count_list", [])  # (read in play(): no Tk here)
            if counting:  # (2.12) Picture watch's "Add to a counter": watched alongside, all the time
                threading.Thread(target=self._count_worker, args=(counting, watch_done), daemon=True,
                                 name="count").start()
            if self.auto_stop and self.auto_stop.get("deadline"):
                threading.Thread(target=self._auto_stop_timer, args=(self.auto_stop, watch_done),
                                 daemon=True).start()
            self.play_ctx = ctx
            self.playing_name = None  # set when a picture switched to another macro
            if getattr(self, "start_rejoin_first", False):  # (2.12: start-up: open the game first)
                self.start_rejoin_first = False
                extra = getattr(self, "start_rejoin_opts", None) or {}
                target = extra.get("open") or self._closed_settings()["open"]
                exe = (self.play_game_exe or (self.macro_program or {}).get("exe") or self.settings.get("last_game_exe")
                       or (os.path.basename(target) if target.lower().endswith(".exe") else "RobloxPlayerBeta.exe"))
                if window_tools.IS_WIN and not window_tools.windows_of(exe):
                    opts = dict(self._closed_settings(), action="reopen")
                    if extra.get("open"):
                        opts["open"] = extra["open"]
                    self.start_rejoin_opts = None
                    if self._game_closed(opts, exe, self.closed_steps, startup=True) is True:
                        return
            while True:
                times = None if loop else max(1, repeats - state["count"])
                result = self._run_passes(events, ctx, times, top=True)
                if isinstance(result, tuple) and result[0] == "switch":
                    events, self.playing_name = result[1], result[2]
                    diag.info(f"Picture watch switched to the macro \"{result[2]}\"")
                    continue
                break
        except Exception as exc:
            self.stop_reason = diag.error("Playback stopped because of an error", exc)
        finally:
            watch_done.set()
            window_tools.keep_awake(False)
            # never leave a key or mouse button stuck down
            self._release_held(bg, held_keys, held_buttons)
            self.runs_done = state["count"]
            self._call_ui(self._playback_done)

    def _run_passes(self, steps, ctx, times, top=False, counts=True):
        """Play these steps `times` times (None = until stopped), doing what picture watch asks for
        in between. Used for the macro itself (top) and for every "Play another macro" step.
        Returns "ok", "stop", "restart" (a Start over step, passed up to the macro itself) or
        ("switch", steps, name) when a picture switched to another macro."""
        watch, seen, state = ctx["watch"], ctx["seen"], ctx["state"]
        held_keys, held_buttons = ctx["held"]
        bg = ctx["bg"]
        # a macro that plays other macros doesn't count as a run itself: its parts do
        counts = counts and not self._has_counted_macro(steps) and not getattr(self, "test_play", None)
        done = 0
        while not self.stop_play.is_set() and (times is None or done < times):
            if top and (times is None or times > 1 or watch):
                total = "" if times is None else f" of {state['count'] + times - done}"
                watching = ", watching for the picture" if watch else ""
                name = f" \"{self.playing_name}\"" if getattr(self, "playing_name", None) else ""
                self._set_note(f"Playing{name} run {state['count'] + 1}{total}{watching}...")
            if counts:
                self.run_began = (time.perf_counter(), self._play_clock())
            if top:
                self.goto_jumps, self.goto_fast = {}, [0, self._play_clock()]  # (2.12: Go to's limits)
                if "base_speed" in ctx:  # (2.12: Set speed lasts until the run's end)
                    ctx["speed"] = ctx.pop("base_speed")
            result = self._run_steps(steps, ctx)
            if isinstance(result, str) and result.startswith("goto:"):
                self.stop_reason = f"Stopped: there's no Label \"{result[5:]}\" for Go to."
                diag.info(self.stop_reason)
                return "stop"
            if result == "stop" or isinstance(result, tuple):
                return result
            if result == "gameback":  # the game had closed and is open again: this run starts over
                self._release_held(bg, held_keys, held_buttons)
                seen.clear()
                continue
            if result == "restart":
                if not top:
                    return result
                now = time.perf_counter()
                state["starts_over"][:] = [t for t in state["starts_over"] if now - t < 60] + [now]
                if len(state["starts_over"]) > 10:
                    self.stop_reason = ("Stopped: a \"Start over\" step ran more than 10 times in 60 s. "
                                        "Something is probably stuck.")
                    diag.error(self.stop_reason)
                    return "stop"
                self._release_held(bg, held_keys, held_buttons)
                continue  # from step 1 again (the same run)
            picture = False
            if watch is not None:
                self._release_held(bg, held_keys, held_buttons)
                last_run = top and times is not None and done + 1 >= times
                if result == "ok" and self._picture_now(ctx) != "picture" and watch["end_wait"] > 0 \
                        and not last_run:
                    # the macro ended first: give the picture some time to show up
                    deadline = time.perf_counter() + watch["end_wait"]
                    while True:
                        left = deadline - time.perf_counter()
                        if left <= 0 or self._picture_now(ctx) == "picture":
                            break
                        self._set_note(f"Macro finished, waiting for the picture ({int(left) + 1} s)...")
                        if self.stop_play.wait(min(0.25, left)):
                            return "stop"
                if self.stop_play.is_set():
                    return "stop"
                picture = seen.is_set()
            pic = (watch.get("seen_pic") or {}) if picture else {}
            action = pic.get("action", "restart")
            if not picture or core.watch_counts(pic):
                done += 1
                if counts:
                    state["count"] += 1
                    if self._finish_run(state["count"], "picture" if picture else "end") is False:
                        # (2.12) only the results screen of the Unknown run before: not a run of its own
                        state["count"] -= 1
                        done -= 1
                    if self._auto_stop_due(state):
                        return "stop"
                    if ctx.get("on_fail") and self.session.runs and self.session.runs[-1][0] == stats.LOSS:
                        # this part of the chain was lost: its "if it fails" macro plays before going on
                        if picture:
                            self._picture_click(pic, watch)
                            seen.clear()
                        self._set_note(f"That run failed: playing \"{ctx['on_fail'][1]}\"...")
                        sub = dict(ctx, seen=threading.Event(), watch=None, on_fail=None)
                        if self._run_passes(ctx["on_fail"][0], sub, 1, counts=False) == "stop":
                            return "stop"
                        self._release_held(bg, held_keys, held_buttons)
                        continue
            if not picture:
                continue
            if top and times is not None and done >= times and action == "restart":
                break  # that was the last run: nothing to start over
            seen.clear()
            if self._picture_limit(ctx):
                return "stop"
            if pic.get("builtin") == "retry":  # (2.12: RETRY counts as a result for the stuck run guard)
                self.last_result_clock = self._play_clock()
            self._call_ui(self._picture_seen)
            self._picture_click(pic, watch)
            if action == "stop":
                self.stop_reason = f"Stopped: {core.watch_name(pic)} showed on screen (Picture watch says to stop then)."
                diag.info(self.stop_reason)
                return "stop"
            if action in ("play", "recover"):
                if self._play_picture_macro(pic, ctx, recover=action == "recover") == "stop":
                    return "stop"
            elif action == "switch":
                new_steps = watch["macros"].get(pic.get("macro"))
                if new_steps:
                    return ("switch", new_steps, os.path.splitext(os.path.basename(pic["macro"]))[0])
            for left in range(int(watch["wait"]), 0, -1):
                self._set_note(f"Picture seen! Starting the macro over in {left}...")
                if self.stop_play.wait(1.0):
                    return "stop"
            seen.clear()  # ignore it if it flickered during the wait
        return "stop" if self.stop_play.is_set() else "ok"
