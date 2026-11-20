"""Recording: the countdown, camera movement, mouse and key capture, hotkeys.

Part of the core MacroRecorder class (split out of macro_recorder.py in 2.13): its methods are
unchanged; a name that lives in macro_recorder itself is written core.name."""
from pynput import keyboard
import diag
import os
import raw_mouse
import time
import window_tools
import macro_recorder as core


class CoreRecordingMixin:
    def toggle_record(self):
        if self.playing:
            return
        if self.record_countdown_left > 0:  # Record pressed again during the countdown: don't record
            self._cancel_record_countdown()
            return
        if self.recording:
            self.recording = False
            self.paused = False
            self._stop_camera()
            if self.record_into is not None:
                # recorded for the Edit window: the open macro comes back as it was
                recorded, done = core.drop_stray_clicks(self.events), self.record_into
                (self.events, self.actions, self.current_file, self.macro_screen, self.macro_program) = \
                    self.record_saved
                self.record_into = self.record_saved = None
                self._show_made_for()
                diag.info(f"Recording for the Edit window stopped: {len(recorded)} actions")
                self._refresh()
                self.root.after(0, lambda: done(recorded))
                return
            self.macro_program = self._recorded_program()
            n = len(self.events)
            self.events = core.drop_stray_clicks(self.events)
            if len(self.events) != n:
                diag.info(f"Left out {n - len(self.events)} mouse press(es) that were never let go of")
            if getattr(self, "keys_left_out", 0):
                diag.info(f"Left out {self.keys_left_out} key press(es) typed into other windows")
            diag.info(f"Recording stopped: {len(self.events)} actions"
                      + (f", program {self.macro_program['exe']}" if self.macro_program else ""))
        else:
            if self.record_into is None and self.events and not core.messagebox.askyesno(
                "Macro Recorder", "Start a new recording? The current one will be replaced."
            ):
                return
            if not self._before_record():  # (2.11: the dark window asks which window to record in)
                return
            seconds = self._record_ready_seconds()
            if seconds > 0:
                self._start_record_countdown(seconds)
                return
            self._begin_recording()
            return
        self._refresh()

    def _record_ready_seconds(self):
        """The countdown before recording starts (Settings > Recording; 0 = at once; 5 s since 2.11)."""
        return core.int_setting(self.settings, "record_ready_seconds", 5, 0, 600)

    def _before_record(self):
        """Just before the countdown before recording (the dark window may ask things here)."""
        return True

    def _start_record_countdown(self, seconds):
        self.record_countdown_left = seconds
        diag.info(f"Recording starts in {seconds} s")
        self._record_countdown_tick(seconds)
        self._refresh()
        self.record_countdown_job = self.root.after(1000, self._record_countdown_next)

    def _record_countdown_next(self):
        self.record_countdown_job = None
        if self.record_countdown_left <= 0:
            return
        self.record_countdown_left -= 1
        if self.record_countdown_left <= 0:
            self._begin_recording()
            return
        self._record_countdown_tick(self.record_countdown_left)
        self._refresh()
        self.record_countdown_job = self.root.after(1000, self._record_countdown_next)

    def _cancel_record_countdown(self):
        if self.record_countdown_job is not None:
            self.root.after_cancel(self.record_countdown_job)
            self.record_countdown_job = None
        self.record_countdown_left = 0
        diag.info("Recording cancelled during the countdown")
        done, self.record_into = self.record_into, None
        if done is not None:  # (the Edit window gets nothing, and comes back)
            self.root.after(0, lambda: done([]))
        self._refresh()

    def _record_countdown_tick(self, seconds_left):
        """Each second of the countdown before recording (the dark window plays a sound)."""

    def _recording_began(self):
        """Recording has really started (after the countdown)."""

    def _begin_recording(self):
        self.record_countdown_left = 0
        if self.record_into is not None:
            self.record_saved = (self.events, self.actions, self.current_file, self.macro_screen,
                                 self.macro_program)
        self.events = []
        self.actions = None
        self.current_file = None
        self.macro_screen = (self.screen_w, self.screen_h)  # recorded on this screen
        self.macro_program = None
        self.window_samples = {}
        self._show_made_for()
        self.paused = False
        self.paused_total = 0.0
        self.record_exe = self._record_exe_now()
        self.record_exe_of = {}  # (window -> program, fresh for each recording: Windows reuses window numbers)
        self.keys_down_recorded = set()
        self.keys_left_out = 0
        self.start_time = time.perf_counter()
        self.recording = True
        self._add_held_buttons()
        self._start_camera()
        diag.info("Recording started" + (" with camera movement" if self.raw_mouse else ""))
        self._recording_began()
        self._refresh()

    def _add_held_buttons(self):
        """A mouse button already held down when recording starts is recorded as pressed at the start
        (otherwise its later release would come without a press)."""
        try:
            held = window_tools.held_mouse_buttons()
            if not held:
                return
            x, y = self.mouse_ctrl.position
            for name in held:
                self.events.append({"type": "click", "x": int(x), "y": int(y), "button": name, "pressed": True,
                                    "t": 0.0})
        except Exception as exc:
            diag.error("Couldn't read held mouse buttons", exc)

    def _camera_wanted(self):
        return bool(self.settings.get("record_camera", False))

    def _start_camera(self):
        self._stop_camera()
        if not self._camera_wanted() or not raw_mouse.IS_WIN:
            return
        self.camera_dx = self.camera_dy = 0
        self.camera_last = time.perf_counter()
        rm = raw_mouse.RawMouse(self._on_raw_move)
        if rm.start():
            self.raw_mouse = rm
        else:
            diag.error("Camera recording couldn't start (Raw Input)")

    def _stop_camera(self):
        rm, self.raw_mouse = self.raw_mouse, None
        if rm is not None:
            self._flush_camera()
            rm.stop()

    def _camera_turning(self):
        """While the game hides the pointer (Shift Lock, holding the right button), mouse movement
        turns the camera: it's recorded as camera movement instead of positions."""
        if self.raw_mouse is None:
            return False
        # asked at most every 10 ms (the mouse can report up to 1000 times a second)
        now = time.perf_counter()
        cached = getattr(self, "hidden_cache", (0.0, False))
        if now - cached[0] >= 0.01:
            cached = self.hidden_cache = (now, window_tools.cursor_hidden() is True)
        return cached[1]

    def _on_raw_move(self, dx, dy):
        """The mouse itself moved (Raw Input thread). Small movements are added up into one step
        every few milliseconds, so playback sends them at the same pace the mouse did."""
        if not self._capturing() or not self._camera_turning():
            self._flush_camera()
            return
        self.camera_dx += dx
        self.camera_dy += dy
        if time.perf_counter() - self.camera_last >= core.CAMERA_STEP:
            self._flush_camera()

    def _flush_camera(self):
        dx, dy = self.camera_dx, self.camera_dy
        self.camera_dx = self.camera_dy = 0
        self.camera_last = time.perf_counter()
        if (dx or dy) and self.recording:
            ev = {"type": "move_rel", "dx": int(dx), "dy": int(dy)}
            try:
                # (2.11) where the pointer was: Windows speeds up added-together moves differently on
                # playback, so the pointer is put back on this spot after each turn
                x, y = self.mouse_ctrl.position
                ev["x"], ev["y"] = int(x), int(y)
            except Exception:
                pass
            self._add(ev)

    def _note_window(self):
        """While recording: remember which program's window is in front (on each click and key)."""
        try:
            hwnd = window_tools.foreground()
            if not hwnd or window_tools.pid_of(hwnd) == os.getpid():
                return
            entry = self.window_samples.get(hwnd)
            if entry is None:
                info = window_tools.program_info(hwnd)
                if info is None:
                    return
                entry = self.window_samples[hwnd] = [0, info]
            entry[0] += 1
        except Exception:
            pass

    # windows that never decide what a recording is for (the desktop, the taskbar, the Start menu)
    RECORD_NOT_TARGET = {"explorer.exe", "searchhost.exe", "startmenuexperiencehost.exe", "shellexperiencehost.exe"}

    def _record_exe_now(self):
        """(security, 20 Nov 2026) The program this recording is for, when known at the start: the window chosen in
        "Record in which window?". Else None, and the first real window you click or type into decides
        (_record_lock); until then every key counts."""
        w = getattr(self, "record_window", None) or {}
        return None if w.get("desktop") else w.get("exe") or None

    def _front_exe(self):
        """(hwnd, program) of the window in front while recording; program None when unknown or this app."""
        fg = None
        try:
            fg = window_tools.foreground()
            cache = self.__dict__.setdefault("record_exe_of", {})
            if fg not in cache:
                if len(cache) > 200:
                    cache.clear()
                own = fg and window_tools.pid_of(fg) == os.getpid()
                cache[fg] = window_tools.exe_of(fg) if fg and not own else None
            return fg, cache[fg]
        except Exception:
            return fg, None

    def _record_lock(self, here):
        """The first real window you click or type into while recording is the one the recording is for."""
        if not getattr(self, "record_exe", None) and here and str(here).lower() not in self.RECORD_NOT_TARGET \
                and not (getattr(self, "record_window", None) or {}).get("desktop"):
            self.record_exe = here
            diag.info(f"Recording keys typed into {here} only")

    def _key_for_recording(self, key, pressed):
        """Keys typed into another window while recording (a password in Discord, a browser) are left out;
        a key let go of is kept when its press was."""
        down = self.__dict__.setdefault("keys_down_recorded", set())
        ident = repr(core.key_to_data(key))
        if not pressed and ident in down:
            down.discard(ident)
            return True
        _fg, here = self._front_exe()
        if pressed:
            self._record_lock(here)
        exe = getattr(self, "record_exe", None)
        if exe and here and str(here).lower() != str(exe).lower():
            if pressed:
                self.keys_left_out = getattr(self, "keys_left_out", 0) + 1
            return False
        if pressed:
            down.add(ident)
        return True

    def _recorded_program(self):
        if not self.window_samples:
            return None
        return max(self.window_samples.values(), key=lambda e: e[0])[1]

    def toggle_pause(self):
        if not self.recording:
            return
        now = time.perf_counter()
        if self.paused:
            self.paused_total += now - self.pause_started
            self.paused = False
        else:
            self.pause_started = now
            self.paused = True
        self._refresh()

    def _capturing(self):
        return self.recording and not self.paused

    def _on_own_window(self, x, y):
        left, top, right, bottom = self.win_rect
        return left <= x < right and top <= y < bottom

    def _elapsed(self):
        return time.perf_counter() - self.start_time - self.paused_total

    def _add(self, event):
        event["t"] = round(self._elapsed(), 4)
        self.events.append(event)

    def _on_move(self, x, y):
        if not self._capturing() or self._camera_turning():
            return
        now = time.perf_counter()
        if now - self.last_move < core.MOVE_INTERVAL:
            return
        self.last_move = now
        self._add({"type": "move", "x": x, "y": y})

    def _on_click(self, x, y, button, pressed):
        if self._capturing() and not self._on_own_window(x, y):
            self._flush_camera()  # camera movement before the click stays before it
            self._add({"type": "click", "x": x, "y": y, "button": button.name, "pressed": pressed})
            if pressed:
                self._note_window()
                self._record_lock(self._front_exe()[1])

    def _on_scroll(self, x, y, dx, dy):
        if self._capturing() and not self._on_own_window(x, y):
            self._add({"type": "scroll", "x": x, "y": y, "dx": dx, "dy": dy})

    def _hotkey_action(self, key):
        key_id = core.hotkey_id(key)
        for action, hk in self.hotkeys.items():
            if hk == key_id:
                return action
        return None

    def _emergency_key(self, key, pressed):
        """Keeps track of Ctrl and Alt; True when End is pressed while both are down."""
        mods = self.__dict__.setdefault("mods_down", set())
        which = {keyboard.Key.ctrl: "ctrl", keyboard.Key.ctrl_l: "ctrl", keyboard.Key.ctrl_r: "ctrl",
                 keyboard.Key.alt: "alt", keyboard.Key.alt_l: "alt", keyboard.Key.alt_r: "alt",
                 keyboard.Key.alt_gr: "alt"}.get(key)
        if which:
            mods.add(which) if pressed else mods.discard(which)
            return False
        return pressed and key == keyboard.Key.end and mods >= {"ctrl", "alt"}

    def emergency_stop(self):
        """Stop everything now: playback (also while it counts down or waits), recording and its
        countdown. Ctrl+Alt+End does this whatever the hotkeys are set to."""
        diag.info("Emergency stop")
        self.stop_play.set()
        self.capture_callback = None
        if self.record_countdown_left > 0:
            self._cancel_record_countdown()
        if self.recording:
            self.toggle_record()
        if self.playing:
            self.stop_playback()

    def _on_key_press(self, key):
        if self._emergency_key(key, True):
            self.stop_play.set()  # (at once, from this thread: works even if the window is busy)
            self._call_ui(self.emergency_stop)
            return
        callback = self.capture_callback
        if callback is not None:  # the hotkeys window is waiting for a key
            key_id = core.hotkey_id(key)
            self._call_ui(lambda: callback(key_id))
            return
        action = self._hotkey_action(key)
        if action is not None:
            handler = {
                "record": self.toggle_record,
                "pause": self.toggle_pause,
                "play": self.play,
                "stop": self.stop_playback,
            }[action]
            self._call_ui(handler)
            return
        if self._capturing() and self._key_for_recording(key, True):
            self._add({"type": "key", "key": core.key_to_data(key), "pressed": True})
            self._note_window()

    def _on_key_release(self, key):
        self._emergency_key(key, False)
        if self._hotkey_action(key) is not None:
            return
        if self._capturing() and self._key_for_recording(key, False):
            self._add({"type": "key", "key": core.key_to_data(key), "pressed": False})
