"""Counters: Picture watch counting and the counter steps.

Part of the core MacroRecorder class (split out of macro_recorder.py in 2.13): its methods are
unchanged; a name that lives in macro_recorder itself is written core.name."""
import counters
import diag
import macro_steps as workflow
import os
import step_more
import threading
import time
import macro_recorder as core


class CoreCountersMixin:
    COUNTER_MAX = counters.COUNTER_MAX

    COUNT_EVERY = 0.5

    _counter_lock = threading.Lock()  # (2.12: Picture watch counting and counter steps can meet)

    def _counters_key(self):
        return os.path.splitext(os.path.basename(self.current_file or ""))[0].lower() or "_"

    def _start_counters(self, steps):
        """Every counter starts at 0 on Play, except the ones a step says to keep (their last value is
        kept in this PC's settings, never in the macro file)."""
        self.counters = {}
        self.kept_counter_names = workflow.kept_counters(steps) | {
            workflow.clean_counter_name(p.get("counter")) for p in self._count_pictures() if p.get("keep") is True}
        saved = self.settings.get("counter_values")
        saved = saved.get(self._counters_key()) if isinstance(saved, dict) else None
        for name in self.kept_counter_names:
            value = saved.get(name) if isinstance(saved, dict) else None
            self.counters[name] = step_more.clean_number(value, 0) if value is not None else 0

    def _count_pictures(self):
        """Picture watch's pictures and colours that "Add to a counter" (when picture watch is on)."""
        try:
            on = bool(self.watch_var.get())
        except Exception:
            on = True
        if not on or core.image_watch is None:
            return []
        return [p for p in self._active_watch_pictures() if p.get("action") == "count"]

    def _count_worker(self, pictures, done):
        """Counts once each time a picture (or colour) shows: then it must be gone (and its cooldown,
        5 s unless set, must be over) before it can count again. Never while paused or away."""
        import color_check

        names = {id(p): core.watch_name(p) for p in pictures}
        state = {id(p): {"since": None, "armed": True, "last": -1e9} for p in pictures}
        matchers = {}
        for p in pictures:
            if not p.get("color_on"):
                try:
                    m = core.image_watch.Matcher(p["img"], picked_screen_h=p.get("screen_h"),
                                            ignore_background=self.picture_ignores_bg(p), screen_h=self.screen_h)
                    m.need = self.picture_need(p)
                    matchers[id(p)] = m
                except Exception as exc:
                    diag.error(f"Picture watch: couldn't use {names[id(p)]} for counting", exc)
        diag.info(f"Picture watch: counting with {len(pictures)} picture(s) / colour(s)")
        while not done.is_set() and not self.stop_play.is_set():
            started = time.perf_counter()
            if self._play_paused_now():
                done.wait(0.3)
                continue
            screen = None
            for p in pictures:
                st = state[id(p)]
                try:
                    if p.get("color_on"):
                        seen = color_check.seen(p)
                    elif id(p) in matchers:
                        if screen is None:
                            screen = self._hide_own_window(core.image_watch.grab_screen(), core.image_watch.screen_origin())
                        m = matchers[id(p)]
                        seen = m.find(screen, good_enough=m.need)[0] >= m.need
                    else:
                        continue
                except Exception as exc:
                    diag.error("Picture watch: a counting look failed", exc)
                    continue
                now = time.perf_counter()
                if not seen:
                    st["since"], st["armed"] = None, True
                    continue
                st["since"] = st["since"] or now
                cooldown = float(p.get("cooldown") or 5)
                if st["armed"] and now - st["since"] >= float(p.get("hold") or 0) and now - st["last"] >= cooldown:
                    st["armed"], st["last"] = False, now
                    self._count_now(p, names[id(p)])
            self._note_look("Picture watch", time.perf_counter() - started)
            done.wait(max(self.COUNT_EVERY, time.perf_counter() - started))

    def _play_paused_now(self):
        """Paused by the user or because the game isn't in front (the dark window knows)."""
        return getattr(self, "play_paused_at", None) is not None or getattr(self, "away_started", None) is not None

    def _count_now(self, p, label):
        name = workflow.clean_counter_name(p.get("counter"))
        amount = workflow.clean_whole(p.get("amount"), 1)
        now = counters.add(self.__dict__.setdefault("counters", {}), self._counter_lock, name, amount)
        diag.info(f"Picture watch: {label} showed: counter \"{name}\" {'+' if amount >= 0 else ''}{amount} "
                  f"(now {now})")

    def _counter_step(self, a, ctx):
        kind = a.get("kind")
        name = workflow.clean_counter_name(a.get("counter"))
        values = self.__dict__.setdefault("counters", {})
        if kind == "counter_add":
            counters.add(values, self._counter_lock, name, workflow.clean_whole(a.get("amount"), 1))
            return "ok"
        if kind == "counter_set":
            counters.set_value(values, self._counter_lock, name, workflow.clean_whole(a.get("value"), 0))
            return "ok"
        with self._counter_lock:
            now = values.get(name, 0)
        self.last_if_true = now >= workflow.clean_whole(a.get("at_least"), 1)
        if self.last_if_true:  # "if_counter"
            return self._run_steps(a.get("actions", []), ctx)
        return "ok"

    def _save_kept_counters(self):
        names = getattr(self, "kept_counter_names", None)
        if not names:
            return
        store = self.settings.get("counter_values")
        if not isinstance(store, dict):
            store = self.settings["counter_values"] = {}
        store[self._counters_key()] = {n: self.counters.get(n, 0) for n in sorted(names)}
        core.save_settings(self.settings)
