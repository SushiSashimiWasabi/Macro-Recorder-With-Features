"""Settings, the speed / ready boxes, the screen-size boxes and the UI queue.

Part of the core MacroRecorder class (split out of macro_recorder.py in 2.13): its methods are
unchanged; a name that lives in macro_recorder itself is written core.name."""
from tkinter import ttk
import queue
import tkinter as tk
import macro_recorder as core


class CoreSettingsMixin:
    def _save_settings(self):
        self.settings["hotkeys"] = dict(self.hotkeys)
        self.settings["loop"] = bool(self.loop_var.get())
        speed = core.parse_speed(self.speed_var.get())
        if speed is not None:
            self.settings["speed"] = speed
        try:
            self.settings["ready_seconds"] = max(0, min(600, int(self.ready_var.get())))
        except (tk.TclError, ValueError):
            pass
        if hasattr(self, "watch_var"):
            self.settings["watch_enabled"] = bool(self.watch_var.get())
            self.settings["watch_ignore_bg"] = bool(self.watch_bg_var.get())
            self.settings["watch_click"] = bool(self.watch_click_var.get())
            self.settings["watch_shift_lock"] = bool(self.watch_shift_var.get())
            self.settings["watch_save_with_macro"] = bool(self.watch_embed_var.get())
            for name, var, low, high in (("watch_wait", self.watch_wait_var, 0, 600),
                                         ("watch_match", self.watch_match_var, 50, 99),
                                         ("watch_end_wait", self.watch_end_var, 0, 3600),
                                         ("watch_limit_count", self.watch_limit_var, 0, 1000),
                                         ("watch_limit_seconds", self.watch_limit_s_var, 1, 3600)):
                try:
                    self.settings[name] = max(low, min(high, int(var.get())))
                except (tk.TclError, ValueError):
                    pass
        core.save_settings(self.settings)

    def _check_speed(self, quiet=False):
        """Read the speed box. Returns the speed, or None (with a message unless quiet) if it's not valid."""
        speed = core.parse_speed(self.speed_var.get())
        if speed is None:
            if not quiet:
                core.messagebox.showerror(
                    "Macro Recorder",
                    f"Speed must be a number from {core.MIN_SPEED:g} to {core.MAX_SPEED:g}, like 1.5 or 2.5x.",
                )
            return None
        self.speed_var.set(core.format_speed(speed))
        self._save_settings()
        return speed

    def _ready_seconds(self):
        try:
            return max(0, min(600, int(self.ready_var.get())))
        except (tk.TclError, ValueError):
            return 0

    def _read_play_on(self, quiet=False):
        """The screen size to play on: (w, h), or None if the box doesn't hold a size."""
        text = self.play_on_var.get().strip()
        if not text or text.lower().startswith(core.AUTO_PREFIX.lower()):
            self.play_on_var.set(self.auto_label)
            self.settings.pop("play_resolution", None)
            core.save_settings(self.settings)
            return (self.screen_w, self.screen_h)
        size = core.parse_resolution(text)
        if size is None:
            if not quiet:
                core.messagebox.showerror("Macro Recorder", "\"Your screen\" must be a size like 1920x1080, or Auto.")
            return None
        self.play_on_var.set(core.format_resolution(size))
        self.settings["play_resolution"] = core.format_resolution(size)
        core.save_settings(self.settings)
        return size

    def _read_made_for(self, quiet=False):
        """Reads the "Macro made for" box into self.macro_screen. False if it doesn't hold a size."""
        text = self.made_for_var.get().strip()
        if not text or text.lower().startswith("same"):
            self.macro_screen = None
            self.made_for_var.set(core.SAME_AS_PLAY)
            return True
        size = core.parse_resolution(text)
        if size is None:
            if not quiet:
                core.messagebox.showerror("Macro Recorder",
                                     "\"Macro recorded at\" must be a size like 1920x1080, or \"Same as your screen\".")
            return False
        self.macro_screen = size
        self.made_for_var.set(core.format_resolution(size))
        return True

    def _show_made_for(self):
        self.made_for_var.set(core.format_resolution(self.macro_screen) if self.macro_screen else core.SAME_AS_PLAY)

    def _build_resolution_ui(self, frame):
        """Screen size the macro was made for, and the one to play it on (positions are scaled)."""
        box = ttk.LabelFrame(frame, text="Screen size", padding=8)
        box.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        own = core.format_resolution((self.screen_w, self.screen_h))
        ttk.Label(box, text="Macro recorded at:").grid(row=0, column=0, sticky="w")
        self.made_for_var = tk.StringVar(value=core.SAME_AS_PLAY)
        self.made_for_box = ttk.Combobox(box, width=17, textvariable=self.made_for_var,
                                         values=[core.SAME_AS_PLAY] + core.RESOLUTIONS)
        self.made_for_box.grid(row=0, column=1, padx=(4, 12), sticky="w")
        self.made_for_box.bind("<<ComboboxSelected>>", lambda e: self._read_made_for(quiet=True))
        self.made_for_box.bind("<FocusOut>", lambda e: self._read_made_for(quiet=True))
        self.made_for_box.bind("<Return>", lambda e: self._read_made_for(quiet=True))

        ttk.Label(box, text="Your screen:").grid(row=0, column=2, sticky="w")
        self.auto_label = f"{core.AUTO_PREFIX} ({own})"
        saved = self.settings.get("play_resolution")
        start = self.auto_label
        if isinstance(saved, str) and core.parse_resolution(saved):
            start = core.format_resolution(core.parse_resolution(saved))
        self.play_on_var = tk.StringVar(value=start)
        self.play_on_box = ttk.Combobox(box, width=17, textvariable=self.play_on_var,
                                        values=[self.auto_label] + core.RESOLUTIONS)
        self.play_on_box.grid(row=0, column=3, padx=4, sticky="w")
        for ev in ("<<ComboboxSelected>>", "<FocusOut>", "<Return>"):
            self.play_on_box.bind(ev, lambda e: self._read_play_on(quiet=True))
        ttk.Label(box, text="Some macros were recorded in fullscreen, so those only work in fullscreen.\n"
                            "The app itself works properly in windowed mode too.\n"
                            "The left box is filled in from the macro file and is usually right, so leave it.\n"
                            "\"Your screen\" is found by itself (Auto).",
                  foreground="#b00000", justify="left").grid(row=1, column=0, columnspan=4, sticky="w",
                                                             pady=(6, 0))

    def _process_ui_queue(self):
        try:
            while True:
                action = self.ui_queue.get_nowait()
                action()
        except queue.Empty:
            pass
        r = self.root
        self.win_rect = (r.winfo_rootx(), r.winfo_rooty(),
                         r.winfo_rootx() + r.winfo_width(), r.winfo_rooty() + r.winfo_height())
        # (half as often while nothing is being recorded or played)
        busy = self.recording or self.playing or self.record_countdown_left > 0
        self.ui_queue_job = self.root.after(50 if busy else 100, self._process_ui_queue)

    def _call_ui(self, fn):
        """Run fn on the Tk thread (listeners run on their own threads)."""
        self.ui_queue.put(fn)
