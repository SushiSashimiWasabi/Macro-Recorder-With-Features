"""Running the steps: the step runner, replaying events, playback's clock.

Part of the core MacroRecorder class (split out of macro_recorder.py in 2.13): its methods are
unchanged; a name that lives in macro_recorder itself is written core.name."""
from pynput import keyboard
from pynput import mouse
import diag
import macro_steps as workflow
import random
import time
import window_tools
import macro_recorder as core


class CoreStepsMixin:
    def _run_steps(self, steps, ctx):
        """Play a list of steps. Returns "ok", "picture" (picture watch saw its picture: this run is
        over), "stop" (stop the macro) or "restart" (start the macro again from step 1)."""
        # (2.13 review) last_if_true is what the Else after an If reads. An If inside this list's steps changes
        # it, so it's put back when the list ends: an If's body can't change what its own Else sees.
        entry = getattr(self, "last_if_true", True)
        try:
            return self._run_steps_list(steps, ctx)
        finally:
            self.last_if_true = entry

    def _run_steps_list(self, steps, ctx):
        i = 0
        prev = None
        while i < len(steps):
            a = steps[i]
            i += 1
            if self.stop_play.is_set():
                return "stop"
            if ctx["seen"].is_set() and self._picture_now(ctx) == "picture":
                return "picture"
            if a.get("off"):
                prev = None
                continue
            kind = a.get("kind")
            if kind == "else":  # (2.12) only right after an If whose condition wasn't true
                was = prev
                prev = None
                if was not in ("if", "if_counter") or getattr(self, "last_if_true", True):
                    continue
                result = self._run_steps(a.get("actions", []), ctx)
            else:
                if kind in ("if", "if_counter"):
                    self.last_if_true = True
                result = self._run_step(a, ctx)
                prev = kind
            if result == "skip":  # a picture's "Skip to the next step"
                continue
            if isinstance(result, str) and result.startswith("goto:"):  # (2.12) a Label in this list?
                at = next((n for n, b in enumerate(steps) if b.get("kind") == "label" and not b.get("off")
                           and b.get("name") == result[5:]), None)
                if at is None:
                    return result  # (maybe in the list around this one)
                i, prev = at, None
                continue
            if result != "ok":
                return result
        return "ok"

    def _run_step(self, a, ctx):
        kind = a.get("kind")
        held_keys, held_buttons = ctx["held"]
        bg = ctx["bg"]
        if kind == "recorded":
            return self._play_events(a.get("events", []), ctx)
        more = self._run_more_step(a, ctx)  # (2.12: the new actions and options)
        if more is not None:
            return more
        if kind == "wait":
            seconds = float(a.get("seconds", 0)) / ctx["speed"]
            vary = ctx.get("vary")
            if vary and vary["ms"]:
                seconds = max(0.0, seconds + random.uniform(-vary["ms"], vary["ms"]) / 1000.0)
            return self._pause(seconds, ctx)
        if kind == "note":
            return "ok"
        if kind in workflow.COUNTER_KINDS:
            return self._counter_step(a, ctx)
        if kind == "macro":  # a "Play another macro" step: that macro's steps, a number of times
            self.chain_step = a.get("name")
            part = (self.settings.get("profiles") or {}).get(a.get("profile")) if a.get("profile") else None
            if isinstance(part, dict):
                vary = part.get("vary") if isinstance(part.get("vary"), dict) else {}
                ctx = dict(ctx, speed=core.parse_speed(part.get("speed", 1)) or ctx["speed"],
                           vary=({"ms": core.int_setting(vary, "ms", 20, 0, 500), "px": core.int_setting(vary, "px", 3, 0, 50)}
                                 if vary.get("on") else None))
            if a.get("on_fail"):
                ctx = dict(ctx, on_fail=(a["on_fail"], a.get("on_fail_name")))
            if a.get("speed"):  # (2.12: its own speed)
                ctx = dict(ctx, speed=max(0.01, min(100.0, float(a["speed"]))))
            try:
                return self._run_passes(a.get("actions", []), ctx, max(1, int(a.get("times", 1))),
                                        counts=bool(a.get("counts", True)))
            finally:
                self.chain_step = None
        if kind == "stop":
            self.stop_reason = None
            return "stop"
        if kind == "restart":
            return "restart"
        if kind == "repeat":
            for _ in range(max(0, int(a.get("times", 1)))):
                result = self._run_steps(a.get("actions", []), ctx)
                if result != "ok":
                    return result
            return "ok"
        if kind == "if":
            self.last_if_true = bool(self._condition_one(a.get("condition", {})))
            if self.last_if_true:
                return self._run_steps(a.get("actions", []), ctx)
            return "ok"
        if kind == "retry":
            tries = max(1, int(a.get("tries", 3)))
            for n in range(tries):
                result = self._run_steps(a.get("actions", []), ctx)
                if result != "ok":
                    return result
                if self._condition_true(a.get("condition", {}), wait=2.0):
                    return "ok"
                self._set_note(f"Retry: try {n + 2} of {tries}...") if n + 1 < tries else None
            return "ok"
        if kind == "wait_picture":
            waited = self._wait_for_picture(a, bg, held_keys, held_buttons, ctx["away"])
            return waited if waited in ("stop", "gameback") else "ok"
        # one-off actions: done as recorded events would be
        for ev in self._step_events(a):
            if bg is not None:
                self._replay_event_bg(bg, ev, held_keys)
            else:
                gone = self._key_guard(ev, ctx["away"], held_keys, held_buttons)
                if gone:
                    return gone
                self._replay_event(ev, held_keys, held_buttons)
            if ev.get("pause"):
                result = self._pause(ev["pause"], ctx)
                if result != "ok":
                    return result
        return "ok"

    @staticmethod
    def _step_events(a):
        """The events a key / type / click / move / scroll step plays (with "pause" after some)."""
        kind = a.get("kind")
        out = []
        if kind == "key":
            mode = a.get("mode", "press")
            key = a.get("key", {})
            if mode == "down":
                out.append({"type": "key", "key": key, "pressed": True})
            elif mode == "up":
                out.append({"type": "key", "key": key, "pressed": False})
            else:
                hold = max(0.03, float(a.get("hold", 0) or 0))  # how long the key stays down
                for _ in range(max(1, int(a.get("times", 1)))):
                    out.append({"type": "key", "key": key, "pressed": True, "pause": hold})
                    out.append({"type": "key", "key": key, "pressed": False, "pause": 0.03})
        elif kind == "type":
            delay = max(0.0, float(a.get("delay", 0.02)))
            for ch in str(a.get("text", "")):
                key = {"char": ch} if ch not in "\n\r\t" else {"special": {"\n": "enter", "\r": "enter",
                                                                             "\t": "tab"}[ch]}
                if ch == " ":
                    key = {"special": "space"}
                out.append({"type": "key", "key": key, "pressed": True})
                out.append({"type": "key", "key": key, "pressed": False, "pause": delay})
        elif kind == "click":
            x, y, button, mode = a.get("x", 0), a.get("y", 0), a.get("button", "left"), a.get("mode", "click")
            out.append({"type": "move", "x": x, "y": y, "pause": 0.03})
            presses = {"click": [True, False], "double": [True, False, True, False], "down": [True],
                       "up": [False]}.get(mode, [True, False])
            hold = max(0.04, float(a.get("hold", 0) or 0)) if mode == "click" else 0.04  # how long it's held
            for pressed in presses:
                out.append({"type": "click", "x": x, "y": y, "button": button, "pressed": pressed,
                            "pause": hold if pressed else 0.04})
        elif kind == "move":
            out.append({"type": "move", "x": a.get("x", 0), "y": a.get("y", 0)})
        elif kind == "scroll":
            out.append({"type": "scroll", "dx": 0, "dy": int(a.get("amount", 0))})
        return out

    def _pause(self, seconds, ctx):
        """Wait (playback's clock, so Pause works), noticing Stop, picture watch and the game leaving."""
        end = self._play_clock() + max(0.0, seconds)
        while True:
            if self.stop_play.is_set():
                return "stop"
            if ctx["seen"].is_set():
                now = self._picture_now(ctx)
                if now:
                    return now
            if ctx["away"] is not None:
                gone = ctx["away"](*ctx["held"])
                if gone:
                    return gone if gone == "gameback" else "stop"
            left = end - self._play_clock()
            if left <= 0:
                return "ok"
            time.sleep(min(left, 0.02))

    def _play_events(self, events, ctx):
        """Recorded events, each at its own time from the start of this step."""
        speed, bg, seen, away = ctx["speed"], ctx["bg"], ctx["seen"], ctx["away"]
        held_keys, held_buttons = ctx["held"]
        start = self._play_clock()
        vary = ctx.get("vary")
        earliest = start
        offsets = {}  # mouse button -> how far its click was moved (the release lands on the same spot)
        for ev in events:
            target = start + ev["t"] / speed
            if vary:
                # a little earlier or later, never out of order
                if vary["ms"]:
                    target = max(earliest, target + random.uniform(-vary["ms"], vary["ms"]) / 1000.0)
                    earliest = target
                if vary["px"] and ev["type"] == "click" and "x" in ev:
                    if ev["pressed"] or ev["button"] not in offsets:
                        offsets[ev["button"]] = (random.randint(-vary["px"], vary["px"]),
                                                 random.randint(-vary["px"], vary["px"]))
                    dx, dy = offsets[ev["button"]] if ev["pressed"] else offsets.pop(ev["button"])
                    ev = dict(ev, x=ev["x"] + dx, y=ev["y"] + dy)
            # wait in small steps so Stop (F12) and the picture are noticed quickly
            while True:
                if self.stop_play.is_set():
                    return "stop"
                if seen.is_set():
                    now = self._picture_now(ctx)
                    if now:
                        return now
                if away is not None:
                    gone = away(held_keys, held_buttons)
                    if gone:  # waited too long for the game to come back, or it closed
                        return gone if gone == "gameback" else "stop"
                remaining = target - self._play_clock()
                if remaining <= 0:
                    break
                if remaining > core.SPIN_SECONDS:
                    time.sleep(min(remaining - core.SPIN_SECONDS * 0.75, 0.02))
                else:
                    time.sleep(0)  # the last moment: check the clock closely (steadier quick taps)
            if ev["type"] == "wait_picture":
                before = self._play_clock()
                waited = self._wait_for_picture(ev, bg, held_keys, held_buttons, away)
                if waited in ("stop", "gameback"):
                    return waited
                start += self._play_clock() - before  # the rest keeps its timing after the wait
                earliest = start
                continue
            if bg is not None:
                self._replay_event_bg(bg, ev, held_keys)
            else:
                gone = self._key_guard(ev, away, held_keys, held_buttons)
                if gone:
                    return gone
                self._replay_event(ev, held_keys, held_buttons)
        return "ok"

    def _condition_true(self, condition, wait=0.0):
        """Whether an If / Retry condition holds now ("shows": the picture is on screen, or isn't).
        wait: look again for up to that many seconds before saying it doesn't."""
        if getattr(self, "ghost", False):  # watch only: no look, the way chosen for the test
            found = self.test_play.get("found", True)
            label = condition.get("name") or "the picture"
            self._set_note(f"Watch only: {label} counts as {'found' if found else 'not found'}")
            self.stop_play.wait(0.6)
            return found if condition.get("shows", True) else not found
        if condition.get("color_on"):  # (2.12: a colour instead of a picture)
            return self._color_until(condition, bool(condition.get("shows", True)), wait)
        matcher = self.wait_matchers.get(id(condition))
        if matcher is None:
            return not condition.get("shows", True)
        need = max(0.5, min(0.99, condition.get("match", 85) / 100.0))
        return self._look_until(matcher, need, bool(condition.get("shows", True)), wait, 0.25, "if/retry")

    def _run_finished(self, count, how):
        """One run of the macro is over (how: "end" = it played to the end, "picture" = picture watch).
        The dark window sends a Discord message here, if that's set up."""

    @staticmethod
    def _opens_start(ev, held_keys):
        """The Windows key, or Esc while Ctrl is held (both open the Start menu)."""
        import step_more

        if step_more.is_win_key(ev.get("key")):
            return True
        ctrls = {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}

        def ctrl_down(k):  # (a file can write Ctrl as a plain key code: look at the code too; on Windows only,
            # a Mac's own key codes mean other keys)
            vk = step_more.vk_of(k) or step_more.vk_of(getattr(k, "value", None))
            return k in ctrls or (core.IS_WIN and vk in step_more.CTRL_VKS)

        return step_more.is_esc_key(ev.get("key")) and any(ctrl_down(k) for k in held_keys)

    def _key_guard(self, ev, away, held_keys, held_buttons):
        """(security, 20 Nov 2026) Right before a key goes down: the game must be in front NOW (the usual
        check allows a moment for windows changing hands, long enough for a macro to type into a box it just
        opened). Not in front: playback pauses until it is. Returns what the usual check would ("stop",
        "gameback") or None to go on."""
        guard = getattr(away, "before_key", None)
        if guard is None or ev.get("type") != "key" or not ev.get("pressed"):
            return None
        gone = guard(held_keys, held_buttons)
        if gone:
            return gone if gone == "gameback" else "stop"
        return None

    def _replay_event(self, ev, held_keys, held_buttons):
        if getattr(self, "ghost", False):
            return self._ghost_event(ev)  # (2.11: watch only, nothing is pressed)
        kind = ev["type"]
        if kind == "wait_picture":
            return
        if kind == "move":
            core.move_to(self.mouse_ctrl, ev["x"], ev["y"])
        elif kind == "move_rel":
            core.move_relative(self.mouse_ctrl, ev["dx"], ev["dy"], held_buttons)
            if "x" in ev and "y" in ev:
                # the game turned by the move above; the pointer goes on the exact recorded spot (the
                # game doesn't see this as movement, so the camera isn't turned twice)
                self.mouse_ctrl.position = (ev["x"], ev["y"])
        elif kind == "click":
            button = core.button_from_name(ev["button"])
            if "x" in ev and self.mouse_ctrl.position != (ev["x"], ev["y"]):
                core.move_to(self.mouse_ctrl, ev["x"], ev["y"])
            if ev["pressed"]:
                self.mouse_ctrl.press(button)
                held_buttons.add(button)
            else:
                self.mouse_ctrl.release(button)
                held_buttons.discard(button)
        elif kind == "scroll":
            if "x" in ev and self.mouse_ctrl.position != (ev["x"], ev["y"]):
                core.move_to(self.mouse_ctrl, ev["x"], ev["y"])
            self.mouse_ctrl.scroll(ev["dx"], ev["dy"])
        elif kind == "key":
            key = core.data_to_key(ev["key"])
            if key is None:
                return  # a key this computer doesn't have
            if ev["pressed"] and not getattr(self, "allow_sensitive", True) and self._opens_start(ev, held_keys):
                return  # (security: a macro from someone else you said No to doesn't open the Start menu)
            if ev["pressed"]:
                self.kb_ctrl.press(key)
                held_keys.add(key)
            else:
                self.kb_ctrl.release(key)
                held_keys.discard(key)

    def _replay_event_bg(self, bg, ev, held_vks):
        kind = ev["type"]
        if kind in ("move_rel", "wait_picture"):
            return  # camera-style moves can't be sent to a background window
        x, y = (ev["x"], ev["y"]) if "x" in ev else self.mouse_ctrl.position
        if kind == "move":
            bg.mouse_move(x, y)
        elif kind == "click":
            bg.mouse_button(x, y, ev["button"], ev["pressed"])
        elif kind == "scroll":
            bg.scroll(x, y, ev["dx"], ev["dy"])
        elif kind == "key":
            vk = core.key_to_vk(ev["key"])
            if vk is None:
                return
            bg.key(vk, ev["pressed"])
            (held_vks.add if ev["pressed"] else held_vks.discard)(vk)

    def _clock_back(self, seconds):
        """Take time out of playback's clock (something else was done meanwhile)."""
        if self.away_started is None:  # (while paused the clock isn't running anyway)
            self.away_total += seconds

    def _play_clock(self):
        """The clock playback follows: it stands still while the game isn't in front (and, in the dark
        window, while playback is paused)."""
        now = self.away_started if self.away_started is not None else time.perf_counter()
        return now - self.away_total

    def _release_held(self, bg, held_keys, held_buttons):
        """Let go of every key and mouse button the macro is holding down."""
        if getattr(self, "ghost", False):  # (watch only held nothing down)
            held_keys.clear()
            held_buttons.clear()
            return
        if bg is not None:
            try:
                bg.release_all(held_keys)
            except Exception:
                pass
            held_keys.clear()
        for k in list(held_keys):
            try:
                self.kb_ctrl.release(k)
            except Exception:
                pass
        for b in list(held_buttons):
            try:
                self.mouse_ctrl.release(b)
            except Exception:
                pass
        held_keys.clear()
        held_buttons.clear()

    def _click_at(self, x, y):
        """Left-click a spot like a person would: move there, nudge so the game sees the mouse, click."""
        if getattr(self, "ghost", False):
            return self._ghost_event({"type": "click", "x": x, "y": y, "button": "left", "pressed": True})
        core.move_to(self.mouse_ctrl, x, y)
        time.sleep(0.05)
        core.move_relative(self.mouse_ctrl, 1, 0)
        time.sleep(0.05)
        core.move_relative(self.mouse_ctrl, -1, 0)
        time.sleep(0.1)
        self.mouse_ctrl.press(mouse.Button.left)
        time.sleep(0.06)
        self.mouse_ctrl.release(mouse.Button.left)

    def _free_shift_lock(self):
        """If the game hides the pointer (Roblox's Shift Lock is on), press Shift once to get the
        pointer back, so a click can land on a button. Returns True if the pointer is visible now."""
        if getattr(self, "ghost", False) or window_tools.cursor_hidden() is not True:
            return True
        try:
            self.kb_ctrl.press(keyboard.Key.shift_l)
            time.sleep(0.05)
            self.kb_ctrl.release(keyboard.Key.shift_l)
        except Exception:
            return False
        time.sleep(0.3)
        ok = window_tools.cursor_hidden() is not True
        diag.info("Pressed Shift to free the mouse from Shift Lock: " + ("worked" if ok else "pointer still hidden"))
        return ok

    def _ghost_event(self, ev):
        """Watch only (2.11): what would have been pressed (the dark window shows it). Sends nothing."""
