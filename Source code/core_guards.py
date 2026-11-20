"""Guards: stop by itself, game closed, stuck run, game not in front; random timing.

Part of the core MacroRecorder class (split out of macro_recorder.py in 2.13): its methods are
unchanged; a name that lives in macro_recorder itself is written core.name."""
import auto_stop
import diag
import os
import run_history
import threading
import time
import window_tools
import macro_recorder as core


class CoreGuardsMixin:
    STUCK_ACTIONS = ("restart", "macro", "ping")

    def _game_exe_now(self):
        """The game being played: the macro's program, else the program in front as playing starts
        (not this app), else the last game a macro was recorded or played in. Remembered for next time."""
        exe = (self.macro_program or {}).get("exe")
        if not exe:
            fg = window_tools.foreground()
            if fg and window_tools.pid_of(fg) != os.getpid():
                exe = window_tools.exe_of(fg)
        if exe:
            self.settings["last_game_exe"] = exe
            return exe
        return self.settings.get("last_game_exe")

    def _game_windows(self):
        """The windows that count as "the game" while playing: the macro's program if it's open,
        else whatever is in front when playing starts (unless that's this app). None = don't check."""
        own = os.getpid()
        exe = (self.macro_program or {}).get("exe")
        fg = window_tools.foreground()
        if exe:
            wins = set(window_tools.windows_of(exe))
            if wins:
                return wins
        if fg and window_tools.pid_of(fg) != own:
            return {fg}
        return None

    def _vary_settings(self):
        """Settings > Playback > "Small random timing": {"on", "ms" (each action up to this much
        earlier or later), "px" (clicks land up to this far from their spot)}. Off unless turned on.
        It keeps a long loop from drifting the exact same way every run; it hides nothing."""
        saved = self.settings.get("vary")
        saved = saved if isinstance(saved, dict) else {}
        return {"on": bool(saved.get("on", False)), "ms": core.int_setting(saved, "ms", 20, 0, 500),
                "px": core.int_setting(saved, "px", 3, 0, 50)}

    def _vary_now(self):
        """What to vary for the open macro: its own choice ("vary" in its file: mode "off", "own"
        with ms / px, or the usual setting), or None for exact playback."""
        own = getattr(self, "macro_vary", None)
        own = own if isinstance(own, dict) else {}
        usual = self._vary_settings()
        if own.get("mode") == "off":
            return None
        if own.get("mode") == "own":
            out = {"ms": core.int_setting(own, "ms", usual["ms"], 0, 500), "px": core.int_setting(own, "px", usual["px"], 0, 50)}
        elif usual["on"]:
            out = {"ms": usual["ms"], "px": usual["px"]}
        else:
            return None
        return out if out["ms"] or out["px"] else None

    def _auto_stop_settings(self):
        """Settings > Playback > "Stop by itself": {"on", "runs", "fragments", "minutes", "at"
        ("HH:MM"), "finish_run", "then" (nothing | close | sleep | shutdown), "warn"}; 0 / "" = not used."""
        return auto_stop.clean_settings(self.settings.get("auto_stop"))

    def _prepare_auto_stop(self):
        """What "Stop by itself" means for the playback that starts now (None = it's off)."""
        return auto_stop.plan(self._auto_stop_settings(), time.time())

    def cancel_auto_stop(self):
        """Keep going: "Stop by itself" is off for the playback that's running. True if it was on."""
        auto = getattr(self, "auto_stop", None)
        if not self.playing or not auto or auto["cancelled"]:
            return False
        auto["cancelled"] = True
        diag.info("Stop by itself was cancelled for this playback")
        return True

    def _auto_stop_timer(self, auto, done):
        """Waits for the time to stop at (telling Discord 5 minutes before)."""
        warn_at = auto["deadline"] - core.AUTO_STOP_WARN_SECONDS
        if auto["warn"] and warn_at > time.time():
            if done.wait(warn_at - time.time()):
                return
            if not auto["cancelled"]:
                self._auto_stop_warning(max(1, round((auto["deadline"] - time.time()) / 60)))
        if done.wait(max(0.0, auto["deadline"] - time.time())) or auto["cancelled"]:
            return
        auto["due"] = "the time you set was reached"
        if not auto["finish_run"]:
            self.auto_stopped = auto["due"]
            self.stop_play.set()

    def _auto_stop_warning(self, minutes):
        """The macro stops by itself in a few minutes (the dark window tells Discord)."""
        diag.info(f"Stop by itself: stopping in about {minutes} min")

    def _auto_stop_due(self, state):
        """After a run: True when "Stop by itself" says this was the last one."""
        auto = getattr(self, "auto_stop", None)
        if not auto or auto["cancelled"]:
            return False
        reason = auto_stop.stop_reason(auto, state["count"], sum(self.session.fragments))
        if not reason:
            return False
        self.auto_stopped = reason
        return True

    def _auto_stop_then(self):
        """After stopping by itself: close the game, or put the PC to sleep, or shut it down."""
        auto = getattr(self, "auto_stop", None) or {}
        then = auto.get("then", "nothing")
        if then == "nothing":
            return
        try:
            self._power_action(then)
        except Exception as exc:
            diag.error(f"Stop by itself: couldn't do \"{then}\"", exc)

    def _power_action(self, then):
        import subprocess

        diag.info(f"Stop by itself: {then}")
        if then == "close":
            exe = (self.macro_program or {}).get("exe") or getattr(self, "play_game_exe", None)
            for hwnd in window_tools.windows_of(exe) if exe else []:
                window_tools.close_window(hwnd)
        elif then == "sleep" and window_tools.IS_WIN:
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        elif then == "shutdown" and window_tools.IS_WIN:
            subprocess.Popen(["shutdown", "/s", "/t", "60", "/c",
                              "Macro Recorder: the macro is done. Shutting down in 1 minute."])
        elif then == "cancel_shutdown" and window_tools.IS_WIN:
            subprocess.Popen(["shutdown", "/a"])

    def _closed_settings(self):
        """Settings > Playback > "If the game closes": {"action": "wait" | "stop" | "reopen", "open":
        what to open (a link or a file), "macro": the rejoin macro, "tries", "settle": seconds to
        let the game load before the macro}."""
        saved = self.settings.get("game_closed")
        saved = saved if isinstance(saved, dict) else {}
        action = saved.get("action") if saved.get("action") in ("wait", "stop", "reopen") else "wait"
        on = bool(saved.get("on", True))
        return {"action": action if on else "wait", "chosen": action, "on": on, "open": str(saved.get("open") or "").strip(),
                "macro": str(saved.get("macro") or ""), "follow": bool(saved.get("follow", True)),
                "tries": core.int_setting(saved, "tries", 3, 1, 20),
                "settle": core.int_setting(saved, "settle", 20, 0, 600),
                "open_wait": core.int_setting(saved, "open_wait", 120, 10, 1800)}

    def _closed_watcher(self, bg):
        """A function playback calls often: when every window of the game has been gone for a few
        seconds (it crashed or was closed), it does what "If the game closes" says. It returns
        False (all fine), True (stop playback) or "gameback" (the game is open again: start the
        run over). None when there's nothing to check."""
        opts = self._closed_settings()
        exe = (self.macro_program or {}).get("exe") or getattr(self, "play_game_exe", None)
        if bg is not None or opts["action"] == "wait" or not exe or not window_tools.IS_WIN:
            return None
        steps = getattr(self, "closed_steps", None)
        state = {"last": 0.0, "since": None}

        def check(held_keys, held_buttons):
            now = time.perf_counter()
            if now - state["last"] < 1.0:
                return False
            state["last"] = now
            if window_tools.windows_of(exe):
                state["since"] = None
                return False
            if state["since"] is None:
                state["since"] = now
                return False
            if now - state["since"] < core.GAME_GONE_SECONDS:
                return False
            state["since"] = None
            self._release_held(None, held_keys, held_buttons)
            return self._game_closed(opts, exe, steps)
        return check

    def _stuck_settings(self):
        """Settings > Playback > "If a run gets stuck": {"on", "minutes" (0 = suggested), "action":
        "restart" / "macro" (play it, then start over) / "ping" (only tell Discord), "macro", "tries"}."""
        saved = self.settings.get("stuck_guard")
        saved = saved if isinstance(saved, dict) else {}
        action = saved.get("action") if saved.get("action") in self.STUCK_ACTIONS else "restart"
        return {"on": saved.get("on") is True, "minutes": core.int_setting(saved, "minutes", 0, 0, 600),
                "action": action, "macro": str(saved.get("macro") or ""), "tries": core.int_setting(saved, "tries", 3, 1, 20)}

    def stuck_minutes_suggested(self, name=None):
        """About 3 times as long as the macro's usual run (from Run stats), at least 3 minutes."""
        try:
            usual = run_history.summary(run_history.runs(name or self._macro_name()))["usual"]
        except Exception:
            usual = 0
        return max(3, int(round(3 * usual / 60))) if usual else 10

    def _stuck_watcher(self):
        """A function playback calls often: when neither MISSION COMPLETED nor MISSION FAILED was seen
        for the set minutes (the clock stands still while paused, while the game isn't in front and
        during disconnect / game-close recovery), it does what "If a run gets stuck" says. It returns
        False (all fine), True (stop playback) or "gameback" (start the run over)."""
        opts = self._stuck_settings()
        if not opts["on"] or not self.settings.get("results_enabled", True):
            return None
        minutes = opts["minutes"] or self.stuck_minutes_suggested()
        st = {"since": self._play_clock(), "tries": 0, "last": 0.0, "result": getattr(self, "last_result_clock", 0.0)}
        diag.info(f"Stuck run guard: on, {minutes} min without a result")

        def check(held_keys, held_buttons):
            wall = time.perf_counter()
            if wall - st["last"] < 1.0:
                return False
            st["last"] = wall
            result = getattr(self, "last_result_clock", 0.0)
            if result > st["result"]:  # a result showed: all fine again
                st["result"] = result
                st["tries"] = 0
            st["since"] = max(st["since"], result, getattr(self, "recovery_end_clock", 0.0))
            wait = minutes * 60 * (1.5 ** st["tries"])  # (each new try waits longer)
            if self._play_clock() - st["since"] < wait:
                return False
            return self._stuck(opts, st, wait, held_keys, held_buttons)
        return check

    def _stuck(self, opts, st, waited, held_keys, held_buttons):
        st["tries"] += 1
        self._release_held(None, held_keys, held_buttons)
        mins = f"{waited / 60:.0f} min"
        if st["tries"] > opts["tries"]:
            self.stop_reason = (f"Stopped: no MISSION COMPLETED or MISSION FAILED for {mins}, also after "
                                f"{opts['tries']} {'try' if opts['tries'] == 1 else 'tries'} (Settings > Playback > "
                                "If a run gets stuck).")
            diag.error(self.stop_reason)
            self._recovery_event("failed", self.stop_reason)
            return True
        text = (f"No MISSION COMPLETED or MISSION FAILED for {mins}: the run seems stuck (try {st['tries']} of "
                f"{opts['tries']}).")
        diag.info("Stuck run guard: " + text)
        self._recovery_event("stuck", text)
        if opts["action"] == "ping":
            st["since"] = self._play_clock()
            return False
        steps = getattr(self, "stuck_steps", None)
        if opts["action"] == "macro" and steps:
            name = os.path.splitext(os.path.basename(opts["macro"]))[0]
            self._set_note(f"The run seems stuck: playing \"{name}\"...")
            diag.info(f"Stuck run guard: playing \"{name}\"")
            ctx = getattr(self, "play_ctx", None) or {}
            sub = dict(ctx, seen=threading.Event(), watch=None, away=None)
            result = self._run_passes(steps, sub, 1, counts=False)
            if sub.get("held"):
                self._release_held(None, *sub["held"])
            if result == "stop" or self.stop_play.is_set():
                return True
        diag.info("Stuck run guard: the run starts over")
        st["since"] = self._play_clock()
        return "gameback"

    def _open_target(self, target):
        """Open a link, shortcut or program as if it was double-clicked."""
        if hasattr(os, "startfile"):
            os.startfile(target)  # noqa: S606 (the user's own choice in Settings)
        else:
            import subprocess

            subprocess.Popen(["open", target])

    def _game_open_target(self, opts):
        """(what to open, a note). A saved game file that is gone after an update is swapped for the newest one in
        its place when "use the newest" is on (the default); the note says what happened ("" = all fine)."""
        path = opts["open"]
        if not os.path.isabs(path) or os.path.exists(path):  # (a link or a program name is not a file that can be gone)
            return path, ""
        found = window_tools.moved_game_file(path) if opts.get("follow", True) else None
        gone = f"The game file you saved ({os.path.basename(os.path.dirname(path))}) isn't there any more"
        if found:
            return found, f"{gone}. Using the newest one ({os.path.basename(os.path.dirname(found))})"
        return path, f"{gone}, and no newer one was found"

    def _game_closed(self, opts, exe, steps, startup=False):
        try:
            return self._game_closed_now(opts, exe, steps, startup)
        finally:
            self.recovery_end_clock = self._play_clock()  # (the stuck run guard starts again from here)

    def _game_closed_now(self, opts, exe, steps, startup=False):
        """Every window of the game is gone. Stop, or open the game again and play the rejoin macro
        (each failed try waits longer). Returns True (stop) or "gameback"."""
        if opts["action"] == "stop":
            self.stop_reason = "Stopped: the game closed (Settings > Playback > If the game closes)."
            diag.info(self.stop_reason)
            return True
        self._away_pause(False)
        if startup:
            diag.info("Start-up: opening the game first")
        else:
            self._recovery_event("lost", "The game closed. Opening it again.")
        ctx = getattr(self, "play_ctx", None) or {}
        sub = dict(ctx, seen=threading.Event(), watch=None, away=None)
        tries = opts["tries"]

        def wait_for_window(seconds, note):
            end = time.perf_counter() + seconds
            while time.perf_counter() < end:
                wins = window_tools.windows_of(exe)
                if wins:
                    return wins
                self._set_note(f"{note} ({int(end - time.perf_counter()) + 1} s)...")
                if self.stop_play.wait(1.0):
                    return []
            return window_tools.windows_of(exe)

        for n in range(tries):
            if n:
                pause = min(300, 15 * 2 ** (n - 1))
                for left in range(pause, 0, -1):
                    self._set_note(f"The game isn't back yet. Try {n + 1} of {tries} in {left} s...")
                    if self.stop_play.wait(1.0):
                        return True
            if not self._recovery_countdown("close"):
                return True
            wins = window_tools.windows_of(exe)
            if not wins and opts["open"]:
                self._set_note(f"Opening the game again (try {n + 1} of {tries})...")
                try:
                    target, note = self._game_open_target(opts)
                    if note:
                        diag.info(note)
                    self._open_target(target)
                except Exception as exc:
                    diag.error("Couldn't open the game again", exc)
                wins = wait_for_window(opts["open_wait"], "Waiting for the game's window")
            if self.stop_play.is_set():
                return True
            if wins:
                for left in range(opts["settle"], 0, -1):
                    self._set_note(f"The game is open. Letting it load ({left} s)...")
                    if self.stop_play.wait(1.0):
                        return True
                wins = window_tools.windows_of(exe) or wins
                window_tools.force_to_front(wins[0])
                time.sleep(0.5)
            if steps and (wins or not opts["open"]):
                self._set_note("Playing the rejoin macro...")
                result = self._run_passes(steps, sub, 1, counts=False)
                self._release_held(None, *sub["held"]) if sub.get("held") else None
                if result == "stop" or self.stop_play.is_set():
                    return True
                if not wins:  # (no link to open: the rejoin macro opens the game itself)
                    wins = wait_for_window(opts["open_wait"], "Waiting for the game's window")
            if self.stop_play.is_set():
                return True
            if window_tools.windows_of(exe):
                if startup:
                    diag.info(f"Start-up: the game is open after {n + 1} {'try' if n == 0 else 'tries'}")
                    return "gameback"
                self.session.reconnects += 1
                run_history.note("reconnects")
                self._recovery_event("back", f"The game is open again after {n + 1} "
                                     f"{'try' if n == 0 else 'tries'}. The macro starts over.")
                return "gameback"
        self.session.failed_reconnects += 1
        self.stop_reason = (f"Stopped: the game closed and couldn't be opened again after {tries} "
                            f"{'try' if tries == 1 else 'tries'}.")
        diag.error(self.stop_reason)
        self._recovery_event("failed", self.stop_reason)
        return True

    def _away_watcher(self, bg, closed=None):
        """When "Pause if the game isn't in front" is on: a function the playback loop calls often.
        If another window (a pop-up, Discord, this app) has been in front for a moment, it lets go of
        every held key and button and pauses until the game is in front again. It returns True
        when playback should stop (waited longer than the limit). None when there's nothing to check."""
        if bg is not None or not self.settings.get("pause_when_away", True) or not window_tools.IS_WIN:
            return None
        games = self._game_windows()
        if not games:
            return None
        limit = core.int_setting(self.settings, "away_stop_seconds", 0, 0, 3600)
        state = {"since": None, "last_check": 0.0}

        exe_of = {}  # window -> its program (asked once per window, not 20 times a second)

        def game_in_front():
            fg = window_tools.foreground()
            if fg is None or fg in games:
                return True  # (no window at all for a moment happens while windows change hands)
            exe = (self.macro_program or {}).get("exe") or (closed and getattr(self, "play_game_exe", None))
            if fg not in exe_of:
                if len(exe_of) > 200:
                    exe_of.clear()
                exe_of[fg] = window_tools.exe_of(fg)
            if exe and exe_of[fg] == exe:  # the game opened another window of its own
                games.add(fg)
                return True
            return False

        def check(held_keys, held_buttons, strict=False):
            now = time.perf_counter()
            if self._user_paused() or (not strict and now - state["last_check"] < 0.05):
                return False
            state["last_check"] = now
            if game_in_front():
                state["since"] = None
                return False
            if strict:  # (a key is about to go down: no moment of grace, see before_key)
                state["since"] = now - core.AWAY_GRACE
            if state["since"] is None:
                state["since"] = now
                return False
            if now - state["since"] < core.AWAY_GRACE:
                return False
            # pause: let go of everything, and wait for the game to come back
            self._release_held(None, held_keys, held_buttons)
            self.away_games = games  # (Preview 4: for "Bring it to front" on the timer)
            name = self._away_name(games)
            self._away_pause(True)
            diag.info(f"Paused: {name or 'the game'} isn't in front")
            began = time.perf_counter()
            try:
                while not self.stop_play.is_set():
                    waited = time.perf_counter() - began
                    if limit and waited >= limit:
                        self.stop_reason = (f"Stopped: the game wasn't in front for {limit} s "
                                            "(Settings > Playback > Pause when the macro's window isn't in front).")
                        diag.info(self.stop_reason)
                        return True
                    note = (f"Paused: {name} isn't in front. Click {name} to go on" if name else
                            "Paused: the game isn't in front. Click back into the game to go on")
                    if limit:
                        note += f" (stops in {int(limit - waited) + 1} s)"
                    self._set_note(note + ".")
                    if closed is not None:  # the game may be gone altogether (crashed, closed)
                        gone = closed(held_keys, held_buttons)
                        if gone:
                            return gone
                    if game_in_front():
                        # give the game a moment to take the mouse and keyboard back
                        if self.stop_play.wait(0.3):
                            break
                        if game_in_front():
                            break
                    self.stop_play.wait(0.1)
            finally:
                self._away_pause(False)
                self.away_games = None
                state["since"] = None
            self._set_note("Playing...")
            diag.info("Going on: the game is in front again")
            return False

        # (security, 20 Nov 2026) asked right before each key goes down: a macro can't open another window
        # (the Run box) and type into it during the usual moment of grace
        check.before_key = lambda held_keys, held_buttons: check(held_keys, held_buttons, strict=True)
        return check

    def _away_name(self, games=None):
        """(Preview 4) The name of the macro's window for the pause message ("Roblox"), or ""."""
        exe = (self.macro_program or {}).get("exe") or getattr(self, "play_game_exe", None)
        if not exe and games:
            try:
                exe = window_tools.exe_of(next(iter(games)))
            except Exception:
                exe = None
        return window_tools.friendly_name(exe)

    def _user_paused(self):
        """True while the user paused playback (the dark window's Pause key)."""
        return False

    def _away_pause(self, on):
        """Playback's clock stands still while the game isn't in front."""
        if on and self.away_started is None:
            self.away_started = time.perf_counter()
        elif not on and self.away_started is not None:
            self.away_total += time.perf_counter() - self.away_started
            self.away_started = None
