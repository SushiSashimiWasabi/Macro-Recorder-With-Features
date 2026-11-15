"""The video window over the game and its keys.

Part of the dark window: ModernMacroRecorder (modern_ui.py) inherits this class.
"""

from ui_common import *  # noqa: F401,F403  (colours, fonts, widgets, tk, core, the other modules)


class VideoMixin:
    VIDEO_KEYS = [("back", "Back 10 seconds", "seek", -10), ("forward", "Forward 10 seconds", "seek", 10),
                  ("vol_up", "Volume up", "volume", 10), ("vol_down", "Volume down", "volume", -10),
                  ("mute", "Mute / sound on", "mute", 0), ("pause", "Pause / play", "pause", 0),
                  ("speed_up", "Faster", "speed", 1), ("speed_down", "Slower", "speed", -1),
                  ("next", "Next video", "next", 0), ("prev", "Previous video", "prev", 0)]
    # the number pad: games rarely use it (with Num Lock on)
    VIDEO_KEY_DEFAULTS = {"back": "vk:100", "forward": "vk:102", "vol_up": "vk:104", "vol_down": "vk:98",
                          "mute": "vk:96", "pause": "vk:101", "speed_up": "vk:107", "speed_down": "vk:109",
                          "next": "vk:105", "prev": "vk:103"}
    VIDEO_KEYS_HELP = (
        "These keys control the video window while it's open, even while you're in the game, so you "
        "don't have to move the mouse (which would disturb a macro). They're never recorded or played "
        "back. The game still gets the key too, so pick keys the game doesn't use; the number pad "
        "(with Num Lock on) is the default.\n\n"
        "Next and Previous video go through the videos you showed before (the last 20), in the same "
        "window.\n\n"
        "Quality: YouTube's embedded player doesn't let other apps change the quality any more, so "
        "pick it with the gear in the video. Faster and Slower change the playback speed instead.")

    def video_keys(self):
        """action -> key id (or None when the action has no key)."""
        saved = self.settings.get("video_keys")
        keys = dict(self.VIDEO_KEY_DEFAULTS)
        if isinstance(saved, dict):
            for action in keys:
                if action in saved:
                    k = saved[action]
                    keys[action] = k if (k is None or core.hotkey_is_valid(k)) else keys[action]
        return keys

    def _video_key_action(self, key):
        if not self.settings.get("video_keys_enabled", True) or not getattr(self, "video_live", False):
            return None
        key_id = core.hotkey_id(key)
        if key_id is None or key_id in self.hotkeys.values():
            return None
        for action, k in self.video_keys().items():
            if k == key_id:
                return action
        return None

    def _on_key_press(self, key):
        if self.capture_callback is None:
            action = self._video_key_action(key)
            if action is not None:
                self._call_ui(lambda: self.video_key(action))
                return  # (not recorded)
        super()._on_key_press(key)

    def _on_key_release(self, key):
        if self.capture_callback is None and self._video_key_action(key) is not None:
            return
        super()._on_key_release(key)

    def video_history(self):
        h = self.settings.get("video_history")
        if not isinstance(h, list):
            h = self.settings["video_history"] = []
        h[:] = [x for x in h if isinstance(x, str) and video_overlay.parse_link(x)]
        return h

    def _remember_video(self, text):
        h = self.video_history()
        if text in h:
            h.remove(text)
        h.append(text)
        del h[:-20]

    def video_key(self, action):
        if not self.video.is_open():
            self.video_live = False
            return
        cmd = next((c for c in self.VIDEO_KEYS if c[0] == action), None)
        if cmd is None:
            return
        _a, _name, what, value = cmd
        if what in ("next", "prev"):
            h = self.video_history()
            current = self.settings.get("video_link", "")
            if len(h) < 2:
                return  # no other video shown before
            i = h.index(current) if current in h else len(h) - 1
            text = h[(i + (1 if what == "next" else -1)) % len(h)]
            link = video_overlay.parse_link(text)
            if not link or not link.get("video"):
                return
            self.settings["video_link"] = text
            self.video_hint_on = False
            self.video_var.set(text)
            self.video_entry.config(fg=TEXT)
            n = h.index(text) + 1
            self.video.command("load", {"video": link["video"], "start": link.get("start") or 0,
                                        "label": f"Video {n} of {len(h)}"})
            core.save_settings(self.settings)
            return
        self.video.command(what, value)

    def open_video_keys(self):
        """A window to pick the video keys (Change, then press a key; Esc cancels, Delete clears)."""
        old = getattr(self, "video_keys_win", None)
        if old is not None and old.winfo_exists():
            old.lift()
            return
        parent = self.settings_win if self.settings_win.winfo_viewable() else self.root
        win = self.video_keys_win = tk.Toplevel(parent, bg=BG)
        win.title("Video keys - Macro Recorder")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.transient(parent)
        if getattr(self, "icon_img", None) is not None:
            win.iconphoto(False, self.icon_img)
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=18, pady=14)
        on_var = tk.BooleanVar(value=bool(self.settings.get("video_keys_enabled", True)))

        def toggled():
            self.settings["video_keys_enabled"] = bool(on_var.get())
            core.save_settings(self.settings)
        r = tk.Frame(body, bg=BG)
        r.pack(fill="x", pady=(0, 8))
        tk.Label(r, text="Use keys for the video window", bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
        self._info_link(r, "Video keys", self.VIDEO_KEYS_HELP).pack(side="left", padx=(5, 0))
        Switch(r, on_var, command=toggled).pack(side="right")
        badges = {}

        def show():
            keys = self.video_keys()
            for action, badge in badges.items():
                k = keys.get(action)
                badge.config(text=core.hotkey_name(k) if k else "none", fg=TEXT if k else DIM)

        def store(action, key_id):
            keys = self.video_keys()
            for other, k in keys.items():  # one key, one action: the other one loses it
                if other != action and k == key_id:
                    keys[other] = None
            keys[action] = key_id
            self.settings["video_keys"] = keys
            core.save_settings(self.settings)
            show()

        def change(action):
            if self.capture_callback is not None:
                return
            badges[action].config(text="Press a key…", fg=AMBER)
            status.set("Press the key. Esc cancels, Delete or Backspace clears it.")

            def got(key_id):
                self.capture_callback = None
                status.set("")
                if not win.winfo_exists():
                    return
                if key_id in ("delete", "backspace"):
                    store(action, None)
                elif key_id and key_id != "esc":
                    if key_id in self.hotkeys.values():
                        status.set("That key is one of the app's shortcuts (Settings > General). Pick another.")
                        show()
                        return
                    store(action, key_id)
                show()
            self.capture_callback = got

        for action, name, _w, _v in self.VIDEO_KEYS:
            r = tk.Frame(body, bg=BG)
            r.pack(fill="x", pady=3)
            tk.Label(r, text=name, bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
            link(r, "Change", lambda a=action: change(a)).pack(side="right")
            badge = tk.Label(r, bg=BADGE, fg=TEXT, font=(FAMILY, 9, "bold"), padx=8, pady=2, width=12)
            badge.pack(side="right", padx=(0, 10))
            badges[action] = badge
        status = tk.StringVar(value="")
        tk.Label(body, textvariable=status, bg=BG, fg=AMBER, font=F_SMALL, anchor="w", wraplength=360,
                 justify="left").pack(fill="x", pady=(6, 0))
        tk.Label(body, text="Quality can't be changed by keys (YouTube doesn't allow it): use the gear in the "
                            "video. Faster / Slower change the speed.", bg=BG, fg=DIM, font=F_SMALL, anchor="w",
                 wraplength=360, justify="left").pack(fill="x", pady=(4, 0))

        def reset():
            self.settings["video_keys"] = dict(self.VIDEO_KEY_DEFAULTS)
            core.save_settings(self.settings)
            show()

        def close():
            self.capture_callback = None
            win.destroy()
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(0, 14))
        link(bottom, "Back to the number pad keys", reset).pack(side="left")
        ttk.Button(bottom, text="Done", style="Accent.TButton", width=8, command=close).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", close)
        show()
        dark_title_bar(win)
        only_close_button(win)
        win.focus_force()

    def _video_hint(self):
        """Grey "Paste a YouTube…" text in the empty link box (gone as soon as you click into it)."""
        e = self.video_entry
        self.video_hint_on = False

        def show(_e=None):
            if not self.video_var.get().strip() and self.root.focus_get() is not e:
                self.video_hint_on = True
                self.video_var.set(VIDEO_HINT)
                e.config(fg=DIM)

        def hide(_e=None):
            if self.video_hint_on:
                self.video_hint_on = False
                self.video_var.set("")
                e.config(fg=TEXT)
        e.bind("<FocusIn>", hide, add="+")
        e.bind("<FocusOut>", show, add="+")
        show()

    def video_link_text(self):
        return "" if getattr(self, "video_hint_on", False) else self.video_var.get().strip()

    def toggle_video(self):
        if self.video.is_open():
            self.close_video()
        else:
            self.show_video()

    def show_video(self):
        text = self.video_link_text()
        link = video_overlay.parse_link(text)
        if link is None:
            messagebox.showinfo("Video", "Paste a YouTube link first, like\n"
                                "https://www.youtube.com/watch?v=…  or  https://www.youtube.com/playlist?list=…",
                                parent=self.root)
            return
        if not link.get("video") and link.get("list") and \
                getattr(self, "playlist_note_var", None) is not None and not self.playlist_note_var.get():
            # the note under Video is hidden, so it's said here (it's still tried)
            messagebox.showinfo("Video", "Playlists aren't supported, only single videos, so this may not "
                                "play. A link to one video of the playlist works.", parent=self.root)
        self.settings["video_link"] = text
        self.video.opacity = self.video_opacity_var.get()
        self.video.click_through = self._video_should_click_through()
        if not self.video.open(link):
            messagebox.showwarning("Video", self.video.error, parent=self.root)
            return
        self.btn_video.config(text="Close")
        self.video_live = True
        self._remember_video(text)
        self._save_settings()
        if self.video_job is None:
            self.video_job = self.root.after(300, self._tick_video)

    def close_video(self):
        self.video.close()
        self._video_closed()

    def _video_closed(self):
        self.video_live = False
        if self.video_job is not None:
            self.root.after_cancel(self.video_job)
            self.video_job = None
        self.btn_video.config(text="Show")
        self._save_video_rect()

    def _save_video_rect(self):
        if self.video.rect and list(self.video.rect) != self.settings.get("video_rect"):
            self.settings["video_rect"] = [int(v) for v in self.video.rect]
            self._save_settings()

    def _tick_video(self):
        """About twice a second while the video window is open: keep it on top, switch clicking
        through it on or off, and notice when it gets closed with its X."""
        self.video_job = None
        if not self.video.poll():
            self._video_closed()
            return
        self._video_mode()
        n = getattr(self, "video_ticks", 0) + 1
        self.video_ticks = n
        if n % 20 == 0:  # remember where it is and how big, every 10 seconds
            self._save_video_rect()
        self.video_job = self.root.after(500, self._tick_video)

    def _video_should_click_through(self):
        if self.video_through_var.get() == "Always":
            return True
        if self.recording:
            return not self.paused
        if self.playing:
            return self.play_paused_at is None  # paused: you can use the video's buttons again
        return False

    def _video_mode(self):
        if hasattr(self, "video") and self.video.is_open():
            want = self._video_should_click_through()
            if want != self.video.click_through:
                self.video.set_click_through(want)

    def _video_opacity(self):
        self.video.set_opacity(self.video_opacity_var.get())
