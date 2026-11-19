"""Looking at the screen while playing: Picture watch, waits, colour checks.

Part of the core MacroRecorder class (split out of macro_recorder.py in 2.13): its methods are
unchanged; a name that lives in macro_recorder itself is written core.name."""
import diag
import os
import run_history
import threading
import time
import window_tools
import macro_recorder as core


class CoreWatchingMixin:
    _look_lock = threading.Lock()

    def _watch_worker(self, watch, seen, done):
        """Takes screenshots and sets `seen` when one of the pictures shows up (watch["seen_pic"] says
        which, watch["seen_at"] where its middle is).

        A picture only fires again after it has gone away, so a results screen that stays up for a
        while doesn't restart the macro over and over. If it's already showing when playback
        starts, it waits for it to go away first. Each picture can also have a cooldown (seconds
        before it may fire again) and "only when picture B also shows"."""
        matchers, need = watch["matchers"], watch["need"]
        window_tools.set_thread_priority(-1)  # never in the way of playback's timing
        states = [{"armed": None, "fired": 0.0} for _ in matchers]
        checks = 0
        try:
            with core.image_watch.mss.mss() as sct:
                origin = core.image_watch.screen_origin(sct)
                while not done.is_set():
                    started = time.perf_counter()
                    # Every check (about once a second) first looks only around the spot where each
                    # picture was found before: a small part of the screen, so it's very light. A
                    # picture's whole area is searched on every 5th check (every size on every 30th).
                    # A picture never found yet: every check for the first 10, then every 3rd check,
                    # taking turns with the other such pictures (so a Disconnected box that never
                    # shows doesn't make every check a heavy one all night).
                    looks = [self._watch_look_area(m, i, checks) for i, m in enumerate(matchers)]
                    all_sizes = checks % 30 == 0
                    checks += 1
                    visible = [False] * len(matchers)
                    middles = [None] * len(matchers)
                    scores = [0.0] * len(matchers)
                    try:
                        # only take the parts of the screen that are looked at
                        areas = [a for a in looks if a is not None] + \
                                [m.near_last_area() for m in matchers if m.last_rect is not None]
                        region = None
                        if areas:
                            region = (min(a[0] for a in areas), min(a[1] for a in areas),
                                      max(a[2] for a in areas), max(a[3] for a in areas))
                            if region[0] <= 0 and region[1] <= 0 and region[2] >= self.screen_w and \
                                    region[3] >= self.screen_h:
                                region = None  # (the whole screen)
                        screen = self._hide_own_window(core.image_watch.grab_screen(sct, region), origin)
                        for i, m in enumerate(matchers):
                            m_need = getattr(m, "need", need)  # (its own Match %, or General's)
                            score, rect = m.find_near_last(screen, good_enough=m_need)
                            if score < m_need and looks[i] is not None:
                                score, rect = m.find(screen, good_enough=m_need, quick=not all_sizes, area=looks[i])
                            scores[i] = score
                            if score >= m_need and self._watch_match_ok(m.picture_entry, score, rect, m_need):
                                visible[i] = True
                                m.picture_entry["seen_rect"] = m.last_rect
                                ox, oy = origin
                                x, y, w, h = rect
                                middles[i] = (ox + x + w // 2, oy + y + h // 2)
                    except Exception:
                        pass
                    for i, m in enumerate(matchers):
                        st, pic = states[i], m.picture_entry
                        if st["armed"] is None:
                            # a picture already on screen when playing starts waits until it has gone
                            # (a results screen left up), except a disconnect box: that one is dealt
                            # with at once, or a macro started while disconnected would never rejoin
                            st["armed"] = not visible[i] or pic.get("action") == "recover"
                        if visible[i] and st["armed"]:
                            also = pic.get("also")
                            if also and not any(visible[j] for j, other in enumerate(matchers)
                                                if other.picture_entry.get("file") == also):
                                continue  # its other picture isn't showing (yet)
                            if started - st["fired"] < float(pic.get("cooldown") or 0):
                                continue
                            if seen.is_set():
                                continue  # another picture is being dealt with: this one waits its turn
                            st["armed"] = False
                            st["fired"] = started
                            watch["seen_at"] = middles[i]
                            watch["seen_pic"] = pic
                            # (so a report says which picture ended a run, and how sure it was)
                            diag.info(f"Picture watch: \"{core.watch_name(pic, i + 1)}\" showed "
                                      f"({scores[i] * 100:.0f}%, needs {getattr(m, 'need', need) * 100:.0f}%): "
                                      f"{pic.get('action', 'restart')}")
                            seen.set()
                        elif not visible[i] and looks[i] is not None:
                            st["armed"] = True  # gone (its whole area was checked): it may count again
                    # check about once a second; when a check is slow, rest at least as long as it
                    # took, so watching never uses more than about half of one CPU core
                    took = time.perf_counter() - started
                    self._note_look("Picture watch", took)
                    done.wait(max(0.3, 1.0 - took, took))
        except Exception:
            pass  # screenshots don't work here: playback just goes on without watching

    def _health_worker(self, done):
        """While playing: every HEALTH_EVERY seconds, one line in the log with how heavy the app is
        (memory, CPU, threads, Windows handles), so a report shows whether something slowly grows
        during a long run."""
        began_cpu, began = time.process_time(), time.perf_counter()
        last_cpu, last = began_cpu, began
        while not done.wait(core.HEALTH_EVERY):
            now_cpu, now = time.process_time(), time.perf_counter()
            cpu = 100.0 * (now_cpu - last_cpu) / max(1e-6, now - last)  # (100 % = one whole core)
            last_cpu, last = now_cpu, now
            h = window_tools.process_health()
            parts = [f"playing {int((now - began) // 60)} min", f"CPU {cpu:.0f}% of one core"]
            if "memory_mb" in h:
                parts.append(f"memory {h['memory_mb']} MB")
            parts.append(f"threads {threading.active_count()}")
            if "gdi" in h:
                parts.append(f"GDI {h['gdi']}, USER {h['user']}")
            diag.info("Health: " + ", ".join(parts))
            looks = self._look_summary()
            if looks:
                diag.info(f"Picture checks (last {core.HEALTH_EVERY // 60} min): " + looks)

    def _watch_look_area(self, m, i, checks):
        """Where Picture watch searches for picture i on this check (besides around where it was
        last found): (x0, y0, x1, y1) on the screen, or None for not this time."""
        if m.last_rect is not None:
            due = checks % 5 == 0
        else:
            due = checks < 10 or (checks + i) % 3 == 0
        if not due:
            return None
        if m.picture_entry.get("action") == "recover":
            # Roblox's Disconnected box is always in the middle of the screen, and a match anywhere
            # else doesn't count (see _watch_match_ok), so only the middle is searched
            t = m.templates[m.last_best][0]
            pw, ph = t.shape[1] / m.work, t.shape[0] / m.work  # its size on the screen
            mx, my = self.screen_w * 0.15 + pw * 0.6 + 20, self.screen_h * 0.2 + ph * 0.6 + 20
            cx, cy = self.screen_w / 2, self.screen_h / 2
            return int(cx - mx), int(cy - my), int(cx + mx) + 1, int(cy + my) + 1
        return 0, 0, self.screen_w, self.screen_h

    def _watch_match_ok(self, pic, score, rect, need):
        """Extra care for a disconnect picture: a big box matched only on its bright parts also
        scores about 0.8 on ordinary game screens (bright sky, white text). Roblox's Disconnected
        box is always in the middle of the screen, so it must be found there, and match well."""
        if pic.get("action") != "recover" or not rect:
            return True
        if score < max(need, core.RECOVER_MATCH):
            return False
        x, y, w, h = rect
        cx, cy = x + w / 2, y + h / 2  # (on the main screen, which is what's grabbed)
        return abs(cx - self.screen_w / 2) <= self.screen_w * 0.15 and abs(cy - self.screen_h / 2) <= self.screen_h * 0.2

    def _picture_limit(self, ctx):
        """The runaway guard: True (and playback stops) when pictures did their actions more often
        than Picture watch > Safety limit allows. A stuck screen mustn't go on forever."""
        watch, restarts = ctx["watch"], ctx["state"]["restarts"]
        now = time.perf_counter()
        limit = watch.get("limit_count", 0)
        within = watch.get("limit_seconds", 60)
        restarts[:] = [t for t in restarts if now - t <= within] + [now]
        if limit and len(restarts) > limit:
            self.stop_reason = (f"Stopped: the picture started the macro over {len(restarts)} times "
                                f"in {within} s. Something is probably stuck (see Picture watch "
                                "> Safety limit).")
            diag.error(self.stop_reason)
            return True
        return False

    def _picture_click(self, pic, watch):
        """Click the picture that showed, when it (or "click on it" for all pictures) says so."""
        click = pic.get("click")
        if (watch["click"] if click is None else click) and watch.get("seen_at"):
            if watch.get("shift_lock"):
                self._set_note("Picture seen! Freeing the mouse from Shift Lock...")
                self._free_shift_lock()
            self._set_note("Picture seen! Clicking it...")
            self._click_at(*watch["seen_at"])

    def _picture_now(self, ctx):
        """Called by playback when a watched picture has shown. Pictures whose action lets the macro
        go on (press a key, wait, skip the step, nothing) are dealt with right here: returns None
        (go on) or "skip" (the step that's playing ends). For every other action it returns
        "picture": the run is over and _run_passes does the rest."""
        seen, watch = ctx["seen"], ctx.get("watch")
        if not seen.is_set():
            return None
        pic = (watch.get("seen_pic") or {}) if watch else {}
        action = pic.get("action", "restart")
        if action not in core.WATCH_INLINE:
            return "picture"
        seen.clear()
        if action == "nothing":
            return None
        if self._picture_limit(ctx):
            self.stop_play.set()
            return None
        self._call_ui(self._picture_seen)
        began = time.perf_counter()
        try:
            self._picture_click(pic, watch)
            if action == "key" and isinstance(pic.get("key"), dict):
                held_keys, held_buttons = ctx["held"]
                for pressed in (True, False):
                    ev = {"type": "key", "key": pic["key"], "pressed": pressed}
                    if ctx["bg"] is not None:
                        self._replay_event_bg(ctx["bg"], ev, held_keys)
                    else:
                        self._replay_event(ev, held_keys, held_buttons)
                    time.sleep(0.05)
            elif action == "wait":
                end = time.perf_counter() + max(0.0, float(pic.get("seconds") or 0))
                while not self.stop_play.is_set():
                    left = end - time.perf_counter()
                    if left <= 0:
                        break
                    self._set_note(f"Picture seen! Waiting {int(left) + 1} s...")
                    self.stop_play.wait(min(0.25, left))
            self._set_note("Playing...")
        finally:
            # the macro's clock didn't run meanwhile, so nothing is rushed afterwards
            self._clock_back(time.perf_counter() - began)
        return "skip" if action == "skip" else None

    def _play_picture_macro(self, pic, ctx, recover=False):
        try:
            return self._play_picture_macro_now(pic, ctx, recover)
        finally:
            if recover:
                self.recovery_end_clock = self._play_clock()  # (the stuck run guard starts again from here)

    def _play_picture_macro_now(self, pic, ctx, recover=False):
        """A picture's own macro: played once, then the main macro starts over. With recover (a
        disconnect screen): the rejoin macro is played until the screen is gone and, if one was
        chosen, the "I'm back" picture shows; each failed try waits longer. Returns "ok" or "stop"."""
        watch = ctx["watch"]
        steps = watch["macros"].get(pic.get("macro"))
        name = os.path.splitext(os.path.basename(pic.get("macro") or ""))[0]
        sub = dict(ctx, seen=threading.Event(), watch=None)  # (picture watch rests while it plays)

        def play_it():
            if not steps:
                return "ok"
            result = self._run_passes(steps, sub, 1, counts=False)
            self._release_held(ctx["bg"], *ctx["held"])
            return "stop" if result == "stop" or self.stop_play.is_set() else "ok"

        if not recover:
            self._set_note(f"Picture seen! Playing \"{name}\"...")
            return play_it()
        tries = max(1, int(pic.get("tries") or 3))
        self._recovery_event("lost", f"{core.watch_name(pic)} showed: trying to get back into the game.")
        own = next((m for m in watch["matchers"] if getattr(m, "picture_entry", None) is pic), None)
        confirm = watch["confirm"].get(id(pic))
        for n in range(tries):
            if n:  # wait longer before each new try: 15 s, 30 s, 60 s... (5 minutes at most)
                pause = min(300, 15 * 2 ** (n - 1))
                for left in range(pause, 0, -1):
                    self._set_note(f"Still not back in the game. Try {n + 1} of {tries} in {left} s...")
                    if self.stop_play.wait(1.0):
                        return "stop"
            if not self._recovery_countdown("disconnect"):
                return "stop"
            self._set_note(f"Getting back into the game (try {n + 1} of {tries})"
                           + (f": playing \"{name}\"..." if steps else "..."))
            if play_it() == "stop":
                return "stop"
            self._set_note("Checking whether the game is back...")
            back = True
            if own is not None:  # the disconnect screen must be gone
                back = not self._shows(own, watch["need"], wait=0)
            if back and confirm is not None:
                back = self._shows(confirm, watch["need"],
                                   wait=max(1.0, float(pic.get("confirm_seconds") or 60)))
            if self.stop_play.is_set():
                return "stop"
            if back:
                self.session.reconnects += 1
                run_history.note("reconnects")
                self._recovery_event("back", f"Back in the game after {n + 1} "
                                     f"{'try' if n == 0 else 'tries'}. The macro goes on.")
                return "ok"
        self.session.failed_reconnects += 1
        self.stop_reason = (f"Stopped: couldn't get back into the game after {tries} "
                            f"{'try' if tries == 1 else 'tries'} ({core.watch_name(pic)} in Picture watch).")
        diag.error(self.stop_reason)
        self._recovery_event("failed", self.stop_reason)
        return "stop"

    def _shows(self, matcher, need, wait=0.0):
        """Whether a picture is on screen now; looks again for up to `wait` seconds until it is."""
        return self._look_until(matcher, need, True, wait, 0.5, "recovery")

    def _look_until(self, matcher, need, want, wait, every, kind):
        """Looks for a picture until it shows (want True) or is gone (want False), for up to `wait`
        seconds: True when that happened, else False.

        Light, like Wait for a picture: around the spot where it was last found first, its whole area
        only every other look (and always on the first and the last look, since only a whole look can
        say it's gone), every size only on the first look. A disconnect picture is only looked for in
        the middle of the screen (it only counts there). It rests at least as long as a look took."""
        need = getattr(matcher, "need", need)  # (its own Match %, if it has one)
        pic = getattr(matcher, "picture_entry", None) or {}
        area = None
        if pic.get("action") == "recover":
            area = self._watch_look_area(matcher, 0, 0)
        deadline = time.perf_counter() + wait
        looks = 0
        with core.image_watch.mss.mss() as sct:
            origin = core.image_watch.screen_origin(sct)
            while True:
                started = time.perf_counter()
                last = started >= deadline
                whole = matcher.last_rect is None or looks % 2 == 0 or last
                first = looks == 0
                looks += 1
                visible = None  # (not known: only around the last spot was looked at)
                try:
                    region = area if whole else matcher.near_last_area()
                    screen = self._hide_own_window(core.image_watch.grab_screen(sct, region), origin)
                    score, rect = matcher.find_near_last(screen, good_enough=need)
                    if score < need and whole:
                        score, rect = matcher.find(screen, good_enough=need,
                                                   quick=not first and matcher.last_rect is not None, area=area)
                    if score >= need and self._watch_match_ok(pic, score, rect, need):
                        visible = True
                    elif whole:
                        visible = False
                except Exception as exc:
                    diag.error("Couldn't check a picture", exc)
                    visible = None  # (not known: a failed screenshot never means the picture is gone)
                took = time.perf_counter() - started
                self._note_look(kind, took)
                if visible is not None and visible == want:
                    return True
                if last or self.stop_play.is_set():
                    return False
                self.stop_play.wait(max(every, took))

    def _note_look(self, kind, seconds):
        """Counts how long a picture look took, for the health line in the log."""
        with self._look_lock:
            stats = self.__dict__.setdefault("look_stats", {})
            s = stats.setdefault(kind, [0, 0.0, 0.0])
            s[0] += 1
            s[1] += seconds
            s[2] = max(s[2], seconds)

    def _look_summary(self):
        """"Picture watch 1800 looks, 6 ms on average, slowest 120 ms; ..." since the last call."""
        with self._look_lock:
            stats = self.__dict__.pop("look_stats", {})
        parts = []
        for kind in ("Picture watch", "results", "wait for a picture", "if/retry", "recovery"):
            s = stats.get(kind)
            if s and s[0]:
                parts.append(f"{kind} {s[0]} looks, {s[1] / s[0] * 1000:.0f} ms on average, "
                             f"slowest {s[2] * 1000:.0f} ms")
        return "; ".join(parts)

    def _recovery_countdown(self, kind):
        """A few seconds' warning (Settings > Playback > Countdown before rejoining) before the app takes
        over the mouse to get back into the game. kind: "disconnect" or "close". Each second is told to
        _recovery_tick (the dark window plays a sound). It follows playback's clock, so a pause holds
        it. False when playback was stopped meanwhile (also when stopped while paused)."""
        seconds = core.int_setting(self.settings, "recovery_countdown", 5, 0, 60)
        what = "Rejoining" if kind == "disconnect" else "Opening the game again"
        try:
            for left in range(seconds, 0, -1):
                self.recover_left = (kind, left)  # (the dark window's top-of-screen timer shows it)
                self._set_note(f"{what} in {left} s...")
                self._recovery_tick(kind, left)
                end = self._play_clock() + 1.0
                while self._play_clock() < end:  # (stands still while paused)
                    if self.stop_play.wait(0.05):
                        return False
        finally:
            self.recover_left = None
        return not self.stop_play.is_set()

    def _color_until(self, h, want, wait, away=None, held=None):
        """Looks at the colour until it shows (want True) or is gone (want False) and has stayed so for
        its "hold" seconds, for up to `wait` seconds (plus the hold): True when that happened."""
        import color_check

        if not color_check.ready(h):
            return not want
        hold = float(h.get("hold", 0) or 0)
        every = color_check.every(h)
        deadline = time.perf_counter() + max(0.0, wait) + hold
        since = None
        while True:
            started = time.perf_counter()
            try:
                now = color_check.seen(h) == want
            except Exception as exc:
                diag.error("Couldn't check a colour", exc)
                now = False
            self._note_look("if/retry", time.perf_counter() - started)
            if now:
                since = since or started
                if started - since >= hold:
                    return True
            else:
                since = None
            if started >= deadline or self.stop_play.is_set():
                return False
            if away is not None:
                gone = away(*held)
                if gone:
                    return ("away", gone)  # (the game went away for too long, or closed and is back)
            self.stop_play.wait(max(every, time.perf_counter() - started))

    def _wait_for_color(self, ev, held_keys, held_buttons, away):
        """A "Wait for…" step that waits for a colour (up to its time limit), then maybe clicks the spot."""
        import color_check

        timeout = float(ev.get("timeout", 30))
        self._set_note("Waiting for " + color_check.describe(ev) + (f" ({timeout:g} s)..." if timeout > 0 else "..."))
        found = self._color_until(ev, True, timeout if timeout > 0 else 10 ** 9, away, (held_keys, held_buttons))
        if isinstance(found, tuple):
            return "gameback" if found[1] == "gameback" else "stop"
        if self.stop_play.is_set():
            return "stop"
        if not found:
            if ev.get("otherwise") == "stop":
                self.stop_reason = f"Stopped: {color_check.describe(ev)} didn't show within {timeout:g} s."
                diag.info(self.stop_reason)
                return "stop"
            return "go on"
        if ev.get("click") and ev.get("where") != "screen" and "x" in ev:
            self._click_at(int(ev["x"]), int(ev["y"]))
        return "go on"

    def _wait_for_picture(self, ev, bg, held_keys, held_buttons, away):
        """A step that waits until a picture shows on screen (up to its time limit), then maybe clicks
        it. Returns "stop" when the macro should stop, else "go on"."""
        if getattr(self, "ghost", False):  # watch only: no look, the way chosen for the test
            found = self.test_play.get("found", True)
            self._set_note(f"Watch only: {ev.get('name') or 'the picture'} counts as {'found' if found else 'not found'}")
            if self.stop_play.wait(0.8):
                return "stop"
            if not found and ev.get("otherwise") == "stop":
                self.stop_reason = None
                return "stop"
            return "go on"
        if ev.get("color_on"):  # (2.12: wait until a colour shows)
            return self._wait_for_color(ev, held_keys, held_buttons, away)
        matcher = self.wait_matchers.get(id(ev))
        if matcher is None:
            return "go on"
        need = max(0.5, min(0.99, ev.get("match", 85) / 100.0))
        timeout = float(ev.get("timeout", 30))
        began = time.perf_counter()
        found = None
        looks = 0
        with core.image_watch.mss.mss() as sct:
            origin = core.image_watch.screen_origin(sct)
            while not self.stop_play.is_set():
                if away is not None:
                    gone = away(held_keys, held_buttons)
                    if gone:
                        return gone if gone == "gameback" else "stop"
                waited = time.perf_counter() - began
                left = timeout - waited
                if timeout > 0 and left <= 0:
                    break
                label = ev.get("name") or "the picture"
                self._set_note(f"Waiting for {label}" + (f" ({int(left) + 1} s)..." if timeout > 0 else "..."))
                started = time.perf_counter()
                try:
                    # first only around where it was found before (light); the whole screen every
                    # other look, or every look while it was never found
                    whole = matcher.last_rect is None or looks % 2 == 0
                    looks += 1
                    region = None if whole else matcher.near_last_area()
                    screen = self._hide_own_window(core.image_watch.grab_screen(sct, region), origin)
                    score, rect = matcher.find_near_last(screen, good_enough=need)
                    if score < need and whole:
                        score, rect = matcher.find(screen, good_enough=need, quick=True)
                except Exception as exc:
                    diag.error("Wait for a picture: screenshot failed", exc)
                    score, rect = 0.0, None
                self._note_look("wait for a picture", time.perf_counter() - started)
                if score >= need and rect is not None:
                    x, y, w, h = rect
                    found = (origin[0] + x + w // 2, origin[1] + y + h // 2)
                    self.last_found = (origin[0] + x, origin[1] + y, w, h)  # (2.12)
                    break
                # look 4 times a second; when a look is slow, rest at least as long as it took (so
                # waiting never takes more than about half of one CPU core away from the game)
                self.stop_play.wait(max(0.25, time.perf_counter() - started))
        if self.stop_play.is_set():
            return "stop"
        if found is None:
            if ev.get("otherwise") == "stop":
                self.stop_reason = f"Stopped: {ev.get('name') or 'the picture'} didn't show within {timeout:g} s."
                diag.info(self.stop_reason)
                return "stop"
            return "go on"
        if ev.get("click"):
            self._click_at(*found)
        return "go on"

    def _recovery_tick(self, kind, seconds_left):
        """Each second of the countdown before rejoining (the dark window plays a sound)."""

    def _recovery_event(self, kind, text):
        """A disconnect screen showed ("lost"), the game is back ("back") or it couldn't be got back
        ("failed"). The dark window tells Discord here."""
        diag.info(f"Recovery ({kind}): {text}")
