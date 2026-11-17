"""The Settings window and its pages: General (shortcuts, icon and logo), Recording, Playback
(screen size), Background, Sounds.

Part of the dark window: ModernMacroRecorder (modern_ui.py) inherits this class.
"""

from ui_common import *  # noqa: F401,F403  (colours, fonts, widgets, tk, core, the other modules)


class SettingsPagesMixin:
    def _build_settings_window(self):
        win = tk.Toplevel(self.root, bg=BG)
        win.withdraw()
        self.settings_win = win
        win.title("Settings - Macro Recorder")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", self.close_settings_x)
        self.title_bar = None  # (an own title bar was tried and rolled back: Windows' own is used)
        # page names as plain text with a blue line under the open one (the notebook's own tabs
        # and frame are hidden, see "Flat.TNotebook" in apply_theme)
        bar = self.tab_bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=14, pady=(10, 0))
        self.tab_labels = {}
        # everything under the page names: the background picture fills all of it (full width,
        # down to the bottom with the buttons); only the page names stay plain
        self.settings_body = tk.Frame(win, bg=BG)
        self.settings_body.pack(fill="both", expand=True, pady=(6, 0))
        self.tabs = ttk.Notebook(self.settings_body, style="Flat.TNotebook")
        self.tabs.pack(fill="both", expand=True, padx=8, pady=(4, 0))
        self.tab_frames = {}
        for name in SETTINGS_PAGES:
            f = ttk.Frame(self.tabs, padding=(18, 14))
            self.tabs.add(f, text=name)
            self.tab_frames[name] = f
            cell = tk.Frame(bar, bg=BG)
            cell.pack(side="left", padx=(0, 4))
            # as wide as the name in bold, so the names don't shift when the open one turns bold
            lab = tk.Label(cell, text=name, bg=BG, fg=MUTED, font=(FAMILY, 10, "bold"), padx=8, pady=4,
                           cursor="hand2")
            line = tk.Frame(cell, bg=BG, height=2)
            line.pack(side="bottom", fill="x", padx=8)
            lab.pack(side="top", fill="x")
            cell.update_idletasks()
            cell.config(width=lab.winfo_reqwidth(), height=lab.winfo_reqheight() + 2)
            cell.pack_propagate(False)
            lab.config(font=(FAMILY, 10))
            lab.bind("<Button-1>", lambda e, n=name: self.tabs.select(self.tab_frames[n]))
            lab.bind("<Enter>", lambda e, n=name: self._tab_hover(n, True))
            lab.bind("<Leave>", lambda e, n=name: self._tab_hover(n, False))
            self.tab_labels[name] = (lab, line)
        # pages whose controls playback and the main window use are made now; the others the first
        # time Settings opens, so the app starts sooner
        self._build_general_tab(self.tab_frames["General"])
        self._build_playback_tab(self.tab_frames["Playback"])
        watch = self.tab_frames["Picture watch"]
        self._build_watch_ui(watch)
        self.bg_tab_built = False
        self.later_pages = [("Recording", self._build_recording_tab), ("Results", self._build_results_tab),
                            ("Background", self._build_background_tab), ("Sounds", self._build_sounds_tab),
                            ("Discord", self._build_discord_tab), ("About", self._build_about_tab)]
        self._dialogs_over_settings()
        self._load_result_pictures_first()
        self._recolor_notes(win)
        bottom = tk.Frame(self.settings_body, bg=BG)
        bottom.pack(fill="x", padx=18, pady=12)
        # "Done" while nothing changed; after a change: Undo (the last change), Reset (every change
        # since the window opened or Apply was last pressed) and Apply
        self.btn_done = ttk.Button(bottom, text="Done", style="Accent.TButton", width=8,
                                   command=self._done_or_apply)
        self.btn_done.pack(side="right")
        self.btn_reset = ttk.Button(bottom, text="Reset", width=8, command=self.reset_settings_changes)
        self.btn_undo = ttk.Button(bottom, text="Undo", width=8, command=self.undo_settings_change)
        self.btn_redo = ttk.Button(bottom, text="Redo", width=8, command=self.redo_settings_change)
        self._build_settings_search(bottom)
        self.settings_redo = []  # changes taken back with Undo, newest last (Redo puts them back)
        self.settings_history = []  # earlier states of the page settings, oldest first
        self.settings_saved_state = None  # the state at the last Apply (or when the window opened)
        self.settings_watch_job = None
        win.bind("<KeyRelease>", lambda e: win.after_idle(self._save_settings), add="+")
        self._title_labels(win)
        # the background picture shows here too (darker behind the pages, as there's more text)
        self.settings_backdrop = backdrop.Backdrop(
            win, see_through=(BG,), base_color=BG, glass=self.settings_body, glass_color=BG, glass_mix=0.55,
            area=lambda: self.settings_body,  # everything but the page names
            lift_colors={DIM: MUTED, MUTED: "#c2c2cc"},
            skip=(self.tab_bar,) + ((self.title_bar,) if self.title_bar else ()))
        self.tabs.bind("<<NotebookTabChanged>>", lambda e: win.after(10, self._settings_tab_changed), add="+")

    def _finish_settings_window(self):
        """The first time Settings opens: make the Background page, then size every page."""
        if self.bg_tab_built:
            return
        self.bg_tab_built = True
        for name, build in self.later_pages:
            f = self.tab_frames[name]
            build(f)
            self._recolor_notes(f)
            self._title_labels(f)
        # every page the same size (the biggest page, with a little room for lists that grow), so the
        # window doesn't change size between pages
        # (measured with every "Advanced" part open, so nothing is cut off when one is opened)
        for part in getattr(self, "advanced_parts", []):
            part.toggle(True)
        self.settings_win.update_idletasks()
        self.tabs.configure(width=max(f.winfo_reqwidth() for f in self.tab_frames.values()),
                            height=max(f.winfo_reqheight() for f in self.tab_frames.values()) + 40)
        for part in getattr(self, "advanced_parts", []):
            part.toggle(False)

    def _settings_page(self):
        """The settings page that's open (the area the background picture fills)."""
        try:
            return self.tabs.nametowidget(str(self.tabs.select()))
        except (AttributeError, KeyError, tk.TclError):
            return self.settings_win

    def _settings_tab_changed(self):
        self._show_tab_bar()
        # nothing on the new page should start out selected (the Countdown box used to)
        self.settings_win.focus_set()
        if self.bg_per_page_var.get():  # each page may have its own background
            self._settings_bg_controls().apply()
        self.settings_backdrop.repaint()

    def _open_page_name(self):
        try:
            return self.tabs.tab(self.tabs.select(), "text")
        except (AttributeError, tk.TclError):
            return SETTINGS_PAGES[0]

    def _show_tab_bar(self):
        open_page = self._open_page_name()
        for name, (lab, line) in self.tab_labels.items():
            on = name == open_page
            lab.config(fg=TEXT if on else MUTED, font=(FAMILY, 10, "bold") if on else (FAMILY, 10))
            line.config(bg=ACCENT if on else BG)

    def _tab_hover(self, name, inside):
        if name != self._open_page_name():
            self.tab_labels[name][0].config(fg=TEXT if inside else MUTED)

    def _title_labels(self, widget):
        """Boxes with a title get it as a separate label, so the background picture can go behind it."""
        for child in widget.winfo_children():
            if isinstance(child, ttk.Labelframe) and not str(child.cget("labelwidget")):
                child.config(labelwidget=tk.Label(child, text=str(child.cget("text")).upper(), bg=BG, fg=MUTED,
                                                  font=F_SECTION))
            self._title_labels(child)

    def _recolor_notes(self, widget):
        """The old option boxes used dark-red and grey notes made for a white window."""
        for child in widget.winfo_children():
            if isinstance(child, ttk.Label):
                fg = str(child.cget("foreground"))
                if fg == "#b00000":
                    child.config(foreground=RED)
                elif fg == "gray":
                    child.config(foreground=MUTED)
            self._recolor_notes(child)

    def _section(self, parent, text, first=False):
        if not first:
            ttk.Separator(parent).pack(fill="x", pady=(12, 10))
        tk.Label(parent, text=text, bg=BG, fg=MUTED, font=F_SECTION, anchor="w").pack(fill="x", pady=(0, 6))

    def _row(self, parent, text, tip=None, info=None):
        """A settings row: its name, a few grey words, and an ⓘ that explains more when clicked."""
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=text, bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
        if info:
            self._info_link(row, text, info).pack(side="left", padx=(5, 0))
        if tip:
            tk.Label(row, text=tip, bg=BG, fg=DIM, font=F_SMALL).pack(side="left", padx=(8, 0))
        return row

    def _info_link(self, parent, title, text):
        return link(parent, "ⓘ", lambda: messagebox.showinfo(title, text, parent=self.settings_win),
                    fg=MUTED, font=(FAMILY, 10))

    def _switch_row(self, parent, text, var, tip=None, command=None, info=None):
        row = self._row(parent, text, tip, info)
        sw = Switch(row, var, command=command or self._save_settings)
        sw.pack(side="right")
        return sw

    def _advanced(self, parent):
        """A "▸ Advanced" link that shows or hides the rarely used options under it."""
        head = tk.Frame(parent, bg=BG)
        head.pack(fill="x", pady=(12, 0))
        body = tk.Frame(parent, bg=BG)
        lab = link(head, "▸  Advanced", lambda: toggle(), fg=MUTED, font=F_SECTION)
        lab.pack(side="left")

        def toggle(show=None):
            show = not body.winfo_ismapped() if show is None else show
            if show:
                body.pack(fill="x", after=head)
            else:
                body.pack_forget()
            lab.config(text=("▾" if show else "▸") + "  Advanced")
            if getattr(self, "settings_backdrop", None) is not None and self.settings_win.winfo_viewable():
                self.settings_win.after_idle(self.settings_backdrop.repaint)
        body.toggle = toggle
        if not hasattr(self, "advanced_parts"):
            self.advanced_parts = []
        self.advanced_parts.append(body)
        return body

    def _build_general_tab(self, f):
        self._section(f, "PROFILE", first=True)
        self._choice_row(f, "Profile", self.profile_summary, self.open_profiles, info=self.PROFILE_HELP,
                         tip="a named set of all your settings")
        row = self._row(f, "Share", "the open macro with its pictures, chain and profile, in one file",
                        info=self.SHARE_HELP)
        ttk.Button(row, text="Import…", command=self.import_pack).pack(side="right")
        ttk.Button(row, text="Export…", command=self.export_pack).pack(side="right", padx=(0, 6))
        row = self._row(f, "First-start questions", "windowed or fullscreen, AOT:R, Discord")
        ttk.Button(row, text="Ask again…", command=self.open_first_start).pack(side="right")
        self._section(f, "SHORTCUTS")
        self._row(f, "Emergency stop", "Ctrl + Alt + End: stops playing and recording, always, whatever the "
                  "keys below are")
        self.key_badges = {}
        self.change_links = {}
        for action in HOTKEY_ACTIONS:
            row = self._row(f, core.HOTKEY_LABELS[action])
            ch = link(row, "Change", lambda a=action: self._capture_hotkey(a))
            ch.pack(side="right")
            badge = tk.Label(row, bg=BADGE, fg=TEXT, font=(FAMILY, 9, "bold"), padx=8, pady=2, width=10)
            badge.pack(side="right", padx=(0, 10))
            self.key_badges[action] = badge
            self.change_links[action] = ch
        r = tk.Frame(f, bg=BG)
        r.pack(fill="x")
        link(r, "Reset to F9 - F12", self._reset_hotkeys).pack(side="right")
        tk.Label(f, text="Pick keys you don't use in the game: a shortcut is never recorded or sent.",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x", pady=(4, 0))

        self._section(f, "INTERFACE")
        self._switch_row(f, "Status bar", self.statusbar_var, "shortcuts and options at the bottom",
                         command=lambda: (self._save_settings(), self._refresh()))
        self._switch_row(f, "Keep window on top", self.ontop_var,
                         command=lambda: (self._save_settings(), self._apply_on_top()))
        self._build_icon_logo_rows(f)
        if IS_WIN:
            self._section(f, "FILES")
            row = self._row(f, "Open .macro files with a double-click")
            b = ttk.Button(row, text="Link .macro files", command=self.link_file_type)
            b.pack(side="right")
            if self.preview:
                b.config(state="disabled")  # the preview must not take over your real app's files
                tk.Label(f, text="Turned off in the preview, so your .macro files keep opening your real app.",
                         bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x")

    # ------------------------------------------------------------ sounds

    SOUND_DEFAULT, SOUND_OFF, SOUND_CHOOSE = "Default sound", "No sound", "Choose a file…"

    # ------------------------------------------------------------ app icon and logo

    def _own_picture(self, key):
        """The stored file of your own icon ("app_icon_file") or logo ("app_logo_file"), or ""."""
        name = self.settings.get(key) or ""
        if not isinstance(name, str) or os.path.basename(name) != name:
            return ""
        path = os.path.join(os.path.dirname(core.settings_path()), name)
        return path if name and os.path.isfile(path) else ""

    def _logo_file(self):
        return self._own_picture("app_icon_file" if self.logo_same_var.get() else "app_logo_file")

    @staticmethod
    def _default_picture():
        """The built-in picture for the icon and the logo (default_logo.png, bundled with the app)."""
        path = core.resource_path("default_logo.png")
        return path if os.path.isfile(path) else ""

    def _apply_app_icon(self):
        """The icon in the title bars and the taskbar: your own picture, or the built-in one."""
        path = self._own_picture("app_icon_file") or self._default_picture()
        imgs = []
        if path:
            for size in (64, 32, 16):
                p = icon_picture.photo(tk, path, size, master=self.root)
                if p is not None:
                    imgs.append(p)
        if not imgs:
            imgs = [app_icon()]
        self.icon_imgs = imgs
        self.icon_img = imgs[0]
        try:
            self.root.iconphoto(True, *imgs)
            for win in (self.settings_win, getattr(self, "edit_win", None)):
                if win is not None and win.winfo_exists():
                    win.iconphoto(False, *imgs)
        except tk.TclError:
            pass

    def _draw_logo(self):
        """The logo in front of "Macro Recorder": your own picture, or the built-in blue square."""
        c = getattr(self, "logo_canvas", None)
        if c is None:
            return
        c.delete("logo")
        path = self._logo_file() or self._default_picture()
        img = icon_picture.photo(tk, path, 30, master=self.root) if path else None
        if img is not None:
            self.logo_img = img
            c.create_image(15, 15, image=img, tags="logo")
        else:
            self.logo_img = None
            rounded_rect(c, 1, 1, 29, 29, 8, fill=ACCENT, outline="", tags="logo")
            c.create_oval(9, 9, 21, 21, fill="white", outline="", tags="logo")
        c.tag_raise("logo")

    def _icon_logo_changed(self):
        self._save_settings()
        self._apply_app_icon()
        self._draw_logo()
        self._show_icon_logo()

    def _choose_own_picture(self, key):
        path = filedialog.askopenfilename(parent=self.settings_win, title="Choose a picture",
                                          filetypes=icon_picture.PICTURE_TYPES)
        if not path:
            return
        kind = "icon" if key == "app_icon_file" else "logo"
        name = f"{kind}_{int(time.time() * 1000)}.png"  # a new file each time, so Undo can go back
        if not icon_picture.store(path, os.path.join(os.path.dirname(core.settings_path()), name)):
            messagebox.showerror("Macro Recorder", "That file couldn't be opened as a picture.\n"
                                 "Try a .png, .jpg, .gif, .bmp, .webp or .ico file.", parent=self.settings_win)
            return
        self.settings[key] = name
        self._icon_logo_changed()

    def _default_own_picture(self, key):
        self.settings[key] = ""
        self._icon_logo_changed()

    def _build_icon_logo_rows(self, f):
        self._section(f, "ICON AND LOGO")
        self.icon_rows = {}
        for key, label, tip in (("app_icon_file", "App icon", "title bar and taskbar"),
                                ("app_logo_file", "Logo", "in front of \"Macro Recorder\"")):
            row = self._row(f, label, tip)
            default = link(row, "Default", lambda k=key: self._default_own_picture(k))
            default.pack(side="right")
            choose = ttk.Button(row, text="Choose…", width=9, command=lambda k=key: self._choose_own_picture(k))
            choose.pack(side="right", padx=(0, 10))
            thumb = tk.Canvas(row, width=24, height=24, bg=BG, highlightthickness=0)
            thumb.pack(side="right", padx=(0, 10))
            self.icon_rows[key] = (thumb, choose, default)
        self._switch_row(f, "Logo the same as the app icon", self.logo_same_var, command=self._icon_logo_changed)
        tk.Label(f, text="Any picture works (.png, .jpg, .gif, .bmp, .webp, .ico). The exe file itself keeps "
                         "its icon in File Explorer.", bg=BG, fg=DIM, font=F_SMALL, anchor="w",
                 wraplength=520, justify="left").pack(fill="x", pady=(2, 0))
        self._show_icon_logo()

    def _show_icon_logo(self):
        rows = getattr(self, "icon_rows", None)
        if not rows:
            return
        same = self.logo_same_var.get()
        self.icon_thumbs = []
        for key, (thumb, choose, default) in rows.items():
            thumb.delete("pic")
            follows = key == "app_logo_file" and same
            path = self._logo_file() if key == "app_logo_file" else self._own_picture(key)
            path = path or self._default_picture()
            img = icon_picture.photo(tk, path, 24, master=self.root) if path else None
            if img is None:
                img = app_icon(24)
            self.icon_thumbs.append(img)
            thumb.create_image(12, 12, image=img, tags="pic")
            thumb.tag_raise("pic")
            choose.config(state="disabled" if follows else "normal")
            own = bool(self._own_picture(key)) and not follows
            default.config(text="Default" if own else "", cursor="hand2" if own else "arrow")

    def _build_sounds_tab(self, f):
        self._section(f, "SOUNDS", first=True)
        self._switch_row(f, "Sounds", self.sounds_var, "off = the app is completely quiet")
        row = self._row(f, "Volume", "slide or scroll")
        self.volume_label = tk.Label(row, bg=BG, fg=TEXT, font=F_SMALL, width=5, anchor="e")
        self.volume_label.pack(side="right")
        tk.Label(row, text="High", bg=BG, fg=MUTED, font=F_SMALL).pack(side="right")
        vol = ttk.Scale(row, from_=0, to=100, length=170, command=lambda v: self._volume_moved(v))
        vol.set(self.volume_var.get())
        vol.pack(side="right", padx=6)
        tk.Label(row, text="Low", bg=BG, fg=MUTED, font=F_SMALL).pack(side="right")
        self.volume_scale = vol
        # letting go of the bar plays a sound, so you hear how loud it is now
        vol.bind("<ButtonRelease-1>", lambda e: self._volume_chosen())

        def wheel(event):
            step = 5 if (event.delta > 0 or event.num == 4) else -5  # wheel up = louder
            vol.set(max(0, min(100, self.volume_var.get() + step)))
            if getattr(self, "volume_job", None) is not None:
                self.root.after_cancel(self.volume_job)
            self.volume_job = self.root.after(250, self._volume_chosen)
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            vol.bind(ev, wheel)
        self._volume_moved(self.volume_var.get())
        self._section(f, "YOUR SOUNDS")
        self.sound_vars, self.sound_boxes = {}, {}
        for event, label, tip, _on in sounds.EVENTS:
            row = self._row(f, label, tip or None)
            box_var = tk.StringVar()
            box = ttk.Combobox(row, width=24, state="readonly", textvariable=box_var)
            box.pack(side="right")
            box.bind("<<ComboboxSelected>>", lambda e, ev=event: self._sound_picked(ev))
            link(row, "▶ Try", lambda ev=event: self._sound(ev, test=True), fg=TEXT,
                 font=F_SMALL).pack(side="right", padx=(0, 10))
            self.sound_vars[event], self.sound_boxes[event] = box_var, box
        r = tk.Frame(f, bg=BG)
        r.pack(fill="x", pady=(4, 0))
        link(r, "Set all back to how they were", self._reset_sounds).pack(side="right")
        tk.Label(f, text="Pick \"Choose a file…\" to use a sound of your own (.wav or .mp3). "
                         "Your sounds stay on this computer.",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x", pady=(6, 0))
        self._show_sounds()

    def _volume_moved(self, value):
        self.volume_var.set(sounds.volume_number(value))
        v = self.volume_var.get()
        self.volume_label.config(text=f"{v}%" if v else "off")

    def _volume_chosen(self):
        self.volume_job = None
        self._save_settings()
        self._sound("play_start", test=True, even_if_off=True)

    def sound_choice(self, event):
        """What an event sounds like: {"mode": "default" / "off" / "custom", "file": stored file name,
        "name": the name of the file you picked}."""
        choices = self.settings.get("sound_choices")
        if not isinstance(choices, dict):
            choices = self.settings["sound_choices"] = {}
        c = choices.get(event)
        if not isinstance(c, dict) or c.get("mode") not in ("default", "off", "custom"):
            c = choices[event] = {"mode": "default" if self._sound_on_at_first(event) else "off"}
        return c

    @staticmethod
    def _sound_on_at_first(event):
        return next((on for ev, _l, _t, on in sounds.EVENTS if ev == event), True)

    def _sound_folder(self):
        return os.path.join(os.path.dirname(core.settings_path()), "sounds")

    def _sound_file(self, event):
        """Your own sound file for an event ("" = there isn't one)."""
        name = self.sound_choice(event).get("file") or ""
        path = os.path.join(self._sound_folder(), os.path.basename(name)) if name else ""
        return path if path and os.path.isfile(path) else ""

    def _show_sounds(self):
        for event, box in self.sound_boxes.items():
            c = self.sound_choice(event)
            own = short(c.get("name") or "", 30) if self._sound_file(event) else ""
            values = [self.SOUND_DEFAULT, self.SOUND_OFF] + ([own] if own else []) + [self.SOUND_CHOOSE]
            box.config(values=values)
            mode = c["mode"] if (c["mode"] != "custom" or own) else "default"
            self.sound_vars[event].set({"default": self.SOUND_DEFAULT, "off": self.SOUND_OFF}.get(mode, own))

    def _sound_picked(self, event):
        picked = self.sound_vars[event].get()
        self.sound_boxes[event].selection_clear()
        c = self.sound_choice(event)
        if picked == self.SOUND_CHOOSE:
            self._show_sounds()  # (the box shows what it was while the file window is open)
            self._choose_sound(event)
            return
        if picked == self.SOUND_DEFAULT:
            c["mode"] = "default"
        elif picked == self.SOUND_OFF:
            c["mode"] = "off"
        else:
            c["mode"] = "custom"
        self._save_settings()
        self._show_sounds()
        if picked != self.SOUND_OFF:
            self._sound(event, test=True)

    def _choose_sound(self, event):
        path = filedialog.askopenfilename(parent=self.settings_win, title="Choose a sound",
                                          filetypes=sounds.SOUND_TYPES)
        if not path:
            return
        if not self.player.can_play(path):
            messagebox.showerror("Macro Recorder", "That file couldn't be played as a sound.\n"
                                 "Try a .wav or .mp3 file.", parent=self.settings_win)
            return
        c = self.sound_choice(event)
        folder = self._sound_folder()
        stored = event + os.path.splitext(path)[1].lower()
        try:
            self.player.stop()  # lets go of the old file, so it can be replaced
            os.makedirs(folder, exist_ok=True)
            old = self._sound_file(event)
            if old and os.path.basename(old) != stored:
                os.remove(old)
            shutil.copyfile(path, os.path.join(folder, stored))
        except OSError as exc:
            messagebox.showerror("Macro Recorder", f"Couldn't copy the sound:\n{exc}", parent=self.settings_win)
            return
        c.update(mode="custom", file=stored, name=os.path.basename(path))
        self._save_settings()
        self._show_sounds()
        self._sound(event, test=True)

    def _reset_sounds(self):
        """Every event back to its built-in beep (or silence, for the ones that start silent).
        Your own files stay in the lists, so you can pick them again."""
        for event in sounds.EVENT_IDS:
            self.sound_choice(event)["mode"] = "default" if self._sound_on_at_first(event) else "off"
        self._save_settings()
        self._show_sounds()

    def _sound(self, name, test=False, even_if_off=False):
        """Play an event's sound. test: also when Sounds is switched off (the Try buttons);
        even_if_off: an event set to "No sound" plays its beep (to hear the volume)."""
        if not (test or self.sounds_var.get()):
            return
        mode = self.sound_choice(name)["mode"]
        if mode == "off" and not even_if_off:
            return
        self.last_sound = time.perf_counter()
        volume = self.volume_var.get()
        path = self._sound_file(name) if mode == "custom" else ""
        if path:
            self.player.play_file(path, volume, fallback=name)
        else:
            self.player.beep(name, volume)

    def _click_sound(self, event):
        """A click on a button, switch or link in this app (if "Button click" has a sound)."""
        if not self.sounds_var.get() or self.sound_choice("click")["mode"] == "off":
            return
        w = event.widget
        try:
            clickable = w.winfo_class() in ("TButton", "TCheckbutton") or str(w.cget("cursor")) == "hand2"
        except (AttributeError, tk.TclError):
            return
        asked = time.perf_counter()
        if clickable and asked - self.last_sound > 0.05:
            # the click's own sound (say, "Recording starts") goes first
            self.root.after(30, lambda: self._sound("click") if self.last_sound < asked else None)

    # ------------------------------------------------------------ background picture

    def _build_background_tab(self, f):
        self._section(f, "MAIN WINDOW", first=True)
        self.bg_main.build(f)
        self._section(f, "SETTINGS WINDOW")
        self._switch_row(f, "A different background for each page", self.bg_per_page_var,
                         command=self._bg_pages_changed)
        page_holder = tk.Frame(f, bg=BG)
        page_holder.pack(fill="x")
        self.bg_page_row = tk.Frame(page_holder, bg=BG)
        tk.Label(self.bg_page_row, text="Page", bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
        tk.Label(self.bg_page_row, text="the options below are for this page", bg=BG, fg=DIM,
                 font=F_SMALL).pack(side="left", padx=(8, 0))
        box = ttk.Combobox(self.bg_page_row, width=14, state="readonly", textvariable=self.bg_page_var,
                           values=list(SETTINGS_PAGES))
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>", lambda e: self._bg_show_controls())
        holder = tk.Frame(f, bg=BG)
        holder.pack(fill="x")
        self.bg_frames = {}
        for c in [self.bg_settings] + list(self.bg_pages.values()):
            frame = tk.Frame(holder, bg=BG)
            c.build(frame)
            self.bg_frames[c] = frame
        self._section(f, "ANIMATED PICTURES (.GIF)")
        self._switch_row(f, "Play animated pictures", self.bg_animate_var,
                         "they stand still while recording or playing",
                         command=lambda: (self._save_settings(), self._apply_animation()))
        row = self._row(f, "Frame rate", "pictures a second (lower = lighter for the computer)")
        ttk.Spinbox(row, from_=5, to=30, width=4, textvariable=self.bg_fps_var,
                    command=lambda: (self._save_settings(), self._apply_animation())).pack(side="right")
        self._switch_row(f, "Only animate the window you're looking at", self.bg_focused_var,
                         command=lambda: (self._save_settings(), self._apply_animation()))
        self._switch_row(f, "Pause while another window is in front", self.bg_pause_others_var,
                         "like the game", command=lambda: (self._save_settings(), self._apply_animation()))
        tk.Label(f, text="Darker = easier to read. Your pictures stay on this computer.",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x", pady=(10, 0))
        if not backdrop.AVAILABLE:
            tk.Label(f, text="Needs the picture tools (numpy + opencv), which aren't installed.",
                     bg=BG, fg=RED, font=F_SMALL, anchor="w").pack(fill="x")
        self._bg_show_controls()

    def bg_library(self):
        """The saved background pictures: [{"file": stored file name, "name": original name}], up to 5."""
        lib = self.settings.get("background_library")
        if not isinstance(lib, list):
            lib = self.settings["background_library"] = []
        return lib

    def _bg_library_upgrade(self):
        """Pictures chosen before there was a list of saved pictures go into the list."""
        if isinstance(self.settings.get("background_library"), list):
            return
        lib = self.bg_library()
        folder = os.path.dirname(core.settings_path())
        for key in [k for k in self.settings if k.endswith("_picture") and
                    k.startswith(("background", "settings_background"))]:
            name = self.settings.get(key)
            if name and os.path.isfile(os.path.join(folder, name)) and len(lib) < MAX_BACKGROUNDS \
                    and all(e["file"] != name for e in lib):
                original = self.settings.get(key[:-len("_picture")] + "_original") or name
                lib.append({"file": name, "name": original})

    def _settings_bg_controls(self):
        """The options the settings window shows right now: the shared ones, or the open page's."""
        if not self.bg_per_page_var.get():
            return self.bg_settings
        try:
            page = self.tabs.tab(self.tabs.select(), "text")
        except (AttributeError, tk.TclError):
            page = SETTINGS_PAGES[0]
        return self.bg_pages.get(page, self.bg_settings)

    def _bg_show_controls(self):
        """Show the options of every page together, or of the page picked in the Page box."""
        if not getattr(self, "bg_tab_built", False):
            return  # the Background page isn't made yet
        per_page = self.bg_per_page_var.get()
        if per_page:
            self.bg_page_row.pack(fill="x", pady=4)
        else:
            self.bg_page_row.pack_forget()
        shown = self.bg_pages.get(self.bg_page_var.get(), self.bg_settings) if per_page else self.bg_settings
        for c, frame in self.bg_frames.items():
            if c is shown:
                frame.pack(fill="x")
            else:
                frame.pack_forget()
        shown.show_state()
        if getattr(self, "settings_backdrop", None) is not None:
            self.settings_win.after_idle(self.settings_backdrop.refresh)

    def _bg_pages_changed(self):
        self._save_settings()
        self._bg_show_controls()
        self._apply_background()

    def _apply_animation(self):
        """Animated pictures play, unless that's switched off or a macro is recording or playing
        (then nothing else is going on in the app, so the macro's timing stays exact)."""
        try:
            fps = max(5, min(30, int(self.bg_fps_var.get())))
        except (tk.TclError, ValueError):
            fps = 15
        for b, which in ((getattr(self, "backdrop", None), "main"),
                         (getattr(self, "settings_backdrop", None), "settings")):
            if b is not None:
                b.set_fps(fps)
                b.may_animate = lambda which=which: self._may_animate(which)
                b.set_animate(self.bg_animate_var.get())
                b.set_paused(self.recording or self.playing)

    def _active_window(self):
        """The app's window that's in front (self.root, self.settings_win or another one of ours),
        or None when another app's window is in front (like the game)."""
        if IS_WIN:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                fg = user32.GetForegroundWindow()
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
                if pid.value != os.getpid():
                    return None
                if self.settings_win is not None and fg == user32.GetParent(self.settings_win.winfo_id()):
                    return self.settings_win
                return self.root
            except Exception:
                return self.root
        try:
            focus = self.root.focus_get()
            return focus.winfo_toplevel() if focus is not None else None
        except (KeyError, tk.TclError):
            return self.root  # (a dropdown list of this app has the keyboard)

    def _may_animate(self, which):
        """Whether the main or settings window's animated picture should move right now."""
        active = self._active_window()
        if active is None:  # another app is in front, like the game
            if self.bg_pause_others_var.get():
                return False
            return which == "main" or not self.bg_focused_var.get()
        if not self.bg_focused_var.get():
            return True
        settings_active = active is self.settings_win
        return settings_active if which == "settings" else not settings_active

    def _apply_background(self):
        self._apply_animation()
        self.bg_main.apply()
        self._settings_bg_controls().apply()
        for c in [self.bg_settings] + list(self.bg_pages.values()):
            c.show_state()

    CAMERA_HELP = (
        "Games like Roblox hide the mouse pointer while you turn the camera (Shift Lock, or holding the "
        "right mouse button) and keep putting it back in the middle. The pointer's position then says "
        "nothing about how far you turned.\n\n"
        "With this on, the app also reads how far the mouse itself moved, the way the game does, while "
        "the pointer is hidden. Those turns are played back at the same pace, so the camera ends up "
        "facing the same way. While the pointer shows, positions are recorded as usual.\n\n"
        "The camera sensitivity in the game must be the same when you play the macro. "
        "Only on Windows.")

    SIMPLIFY_HELP = (
        "When a macro is saved, mouse positions that lie on a straight, evenly paced line between "
        "their neighbours are left out of the file, and put back when it's opened. The pointer goes "
        "through the same places at the same times (within 1 pixel); clicks, keys, scrolling and "
        "camera turns are never changed. Macros with a lot of mouse movement get much smaller.\n\n"
        "Friends need version 2.5 or newer to open such a file the same way (older versions make the "
        "pointer jump between the saved positions).")

    def _build_recording_tab(self, f):
        self._section(f, "BEFORE RECORDING", first=True)
        row = self._row(f, "Countdown", "seconds to switch to the game (0 = start at once)")
        ttk.Spinbox(row, from_=0, to=600, width=5, textvariable=self.rec_ready_var,
                    command=self._save_settings).pack(side="right")
        self._switch_row(f, "Ask which window to record in", self.rec_ask_window_var,
                         "when you press Record in this app (Windows)")
        self._section(f, "MOUSE")
        self._switch_row(f, "Record mouse movement", self.rec_moves_var,
                         "off = only clicks, scrolls and keys")
        self._switch_row(f, "Record game camera movement", self.camera_var, "Shift Lock, right-click turning",
                         info=self.CAMERA_HELP)
        adv = self._advanced(f)
        row = self._row(adv, "Mouse detail")
        box = ttk.Combobox(row, width=9, state="readonly", textvariable=self.detail_var, values=list(MOUSE_DETAIL))
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>", lambda e: self._save_settings())
        tk.Label(adv, text="Smooth keeps every small movement (bigger files). Light keeps fewer points.",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x")
        self._switch_row(adv, "Save smaller mouse paths", self.simplify_var, "the same movement, smaller files",
                         info=self.SIMPLIFY_HELP)
        self._section(f, "GOOD TO KNOW")
        tk.Label(f, justify="left", bg=BG, fg=MUTED, font=F_BASE, anchor="w", text=(
            "Your shortcut keys are never recorded.\n"
            "Clicks on this app's window are not recorded.\n"
            "Pause stops recording for a moment without making a gap in the macro.\n"
            "A mouse button you're already holding when recording starts is recorded too.\n"
            "The game you record in is remembered with the macro.")).pack(fill="x")
        self._section(f, "THIS RECORDING")
        row = self._row(f, "Start over with an empty macro")
        self.btn_clear = ttk.Button(row, text="Clear", style="Danger.TButton", command=self.clear)
        self.btn_clear.pack(side="right")

    def _build_playback_tab(self, f):
        self._section(f, "BEFORE PLAYING", first=True)
        row = self._row(f, "Countdown", "seconds to switch to the game (0 = start at once)")
        ttk.Spinbox(row, from_=0, to=600, width=5, textvariable=self.ready_var,
                    command=self._save_settings).pack(side="right")
        self._switch_row(f, "Timer at the top of the screen", self.overlay_var,
                         "countdown, then how long it's been playing or recording")
        self._switch_row(f, "Offer to switch to the macro's game", self.switch_prog_var,
                         "when you press Play here", info=self.SWITCH_HELP)
        self._section(f, "WHILE PLAYING")
        self._switch_row(f, "Pause if the game isn't in front", self.away_var, "a pop-up, Discord, this app",
                         info=self.AWAY_HELP)
        row = self._row(f, "Stop after waiting", "seconds (0 = keep waiting)")
        ttk.Spinbox(row, from_=0, to=3600, width=5, textvariable=self.away_stop_var,
                    command=self._save_settings).pack(side="right")
        row = self._row(f, "If the game closes", info=self.CLOSED_HELP)
        self.closed_on_var = tk.BooleanVar(value=self._closed_settings()["on"])
        Switch(row, self.closed_on_var, command=self.closed_switched).pack(side="right", padx=(10, 0))
        ttk.Button(row, text="Change…", command=self.open_game_closed).pack(side="right")
        self.closed_var = tk.StringVar(value=self.closed_summary())
        self.closed_var.trace_add("write", lambda *a: self.root.after_idle(self._settings_text_changed))
        tk.Label(row, textvariable=self.closed_var, bg=BG, fg=MUTED, font=F_SMALL).pack(side="right", padx=(0, 10))
        row = self._row(f, "Countdown before rejoining", "seconds, with a sound each second (0 = none)")
        ttk.Spinbox(row, from_=0, to=60, width=5, textvariable=self.recover_count_var,
                    command=self._save_settings).pack(side="right")
        self._choice_row(f, "Stop by itself", self.auto_stop_summary, self.open_auto_stop,
                         info=self.AUTO_STOP_HELP)
        self._build_resolution_ui(f)
        adv = self._advanced(f)
        self._choice_row(adv, "Small random timing", self.vary_summary, self.open_vary, info=self.VARY_HELP)
        row = self._row(adv, "Play into")
        self.target_box = ttk.Combobox(row, width=30, state="readonly", textvariable=self.target_var,
                                       postcommand=self._refresh_windows)
        self.target_box.pack(side="right")
        if background is None:
            self.target_box.config(state="disabled")
        self._refresh_windows()
        tk.Label(adv, text="Background playback is experimental and can't turn a game's camera.",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x")
        self._section(adv, "VIDEO WINDOW")
        f = adv
        row = self._row(f, "Clicks go through it", "so the macro and the game don't notice it")
        box = ttk.Combobox(row, width=24, state="readonly", textvariable=self.video_through_var,
                           values=VIDEO_THROUGH)
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>", lambda e: (self._save_settings(), self._video_mode()))
        row = self._row(f, "Keys for the video", "skip, volume, speed, next video", info=self.VIDEO_KEYS_HELP)
        ttk.Button(row, text="Change keys…", command=self.open_video_keys).pack(side="right")
        row = self._row(f, "See-through", "lower shows more of the game")
        scale = ttk.Scale(row, from_=20, to=100, length=160, variable=self.video_opacity_var,
                          command=lambda v: self._video_opacity())
        scale.pack(side="right")
        scale.bind("<ButtonRelease-1>", lambda e: self._save_settings())
        row = self._row(f, "Saved browser data", info=self.VIDEO_DATA_HELP)
        ttk.Button(row, text="Clear…", command=self.clear_video_data).pack(side="right")
        self.video_data_var = tk.StringVar(value="")
        tk.Label(row, textvariable=self.video_data_var, bg=BG, fg=MUTED, font=F_SMALL).pack(side="right",
                                                                                          padx=(0, 10))
        self.video_data_var.trace_add("write", lambda *a: self.root.after_idle(self._settings_text_changed))
        self._show_video_data_size()

    SWITCH_HELP = (
        "A macro remembers the game it was recorded in (like Roblox). When you press Play in this "
        "window and that game is open, the app asks whether to switch to it first, so the macro "
        "doesn't click into the wrong window. If the game isn't open, it asks whether to play anyway.")
    AWAY_HELP = (
        "If another window comes in front of the game while a macro plays (a pop-up, a message, "
        "Discord, this app), the macro lets go of every key and button and pauses. Click back into "
        "the game and it carries on from the same spot, so it never clicks into another program.\n\n"
        "\"Stop after waiting\" ends the macro if the game stays away that long (0 = wait as long as "
        "it takes). Not used with \"Play into\" a background window.")
    FIT_HELP = (
        "The whole screen: clicks are moved to fit your screen size (for macros recorded in fullscreen).\n\n"
        "The game window: clicks are moved to fit the game's window where it is now, even if it's smaller, "
        "bigger or somewhere else than when the macro was recorded. Needs a macro that knows its "
        "window: recorded in this version or newer, or a .luvmacro file. Others are fitted to the screen.")
    SCREEN_SIZE_HELP = (
        "Macros recorded before 2.6 don't know their game window: played in a window, their clicks may "
        "miss, so record them again or play them in fullscreen (a yellow note says so when one is open). "
        "Camera turns (Shift Lock) are never fitted to the window: they turn the same in any size. "
        "The app itself works properly in windowed mode too.\n\n"
        "Macro recorded at: the screen size the macro was made on. It's filled in from the macro "
        "file and is usually right, so leave it.\n\n"
        "Your screen: the size you play on. Auto finds it by itself.\n\n"
        "When the two differ, clicks are moved to the same spot on your screen.")

    def _build_resolution_ui(self, f):
        """Screen size (Playback page): what the macro was made for and what you play on."""
        self._section(f, "SCREEN SIZE")
        own = core.format_resolution((self.screen_w, self.screen_h))
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text="Macro recorded at", bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
        self.made_for_var = tk.StringVar(value=core.SAME_AS_PLAY)
        self.made_for_box = ttk.Combobox(row, width=19, textvariable=self.made_for_var,
                                         values=[core.SAME_AS_PLAY] + core.RESOLUTIONS)
        self.made_for_box.pack(side="left", padx=(8, 0))
        for ev in ("<<ComboboxSelected>>", "<FocusOut>", "<Return>"):
            self.made_for_box.bind(ev, lambda e: self._read_made_for(quiet=True))
        self.auto_label = f"{core.AUTO_PREFIX} ({own})"
        saved = self.settings.get("play_resolution")
        size = core.parse_resolution(saved) if isinstance(saved, str) else None
        self.play_on_var = tk.StringVar(value=core.format_resolution(size) if size else self.auto_label)
        self.play_on_box = ttk.Combobox(row, width=15, textvariable=self.play_on_var,
                                        values=[self.auto_label] + core.RESOLUTIONS)
        self.play_on_box.pack(side="right")
        for ev in ("<<ComboboxSelected>>", "<FocusOut>", "<Return>"):
            self.play_on_box.bind(ev, lambda e: self._read_play_on(quiet=True))
        tk.Label(row, text="Your screen", bg=BG, fg=TEXT, font=F_BASE).pack(side="right", padx=(0, 8))
        row = self._row(f, "Fit clicks to", info=self.FIT_HELP + "\n\n" + self.SCREEN_SIZE_HELP)
        box = ttk.Combobox(row, width=19, state="readonly", textvariable=self.fit_var, values=list(FIT_TO.values()))
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>", lambda e: (box.selection_clear(), self._save_settings()))
        note = tk.Frame(f, bg=BG)
        note.pack(fill="x", pady=(2, 0))
        # only for an open macro that doesn't know its game window (recorded before 2.6)
        tk.Label(note, textvariable=self.old_macro_var, bg=BG, fg=AMBER, font=F_SMALL, anchor="w",
                 justify="left", wraplength=520).pack(side="left")
        # (one ⓘ for the whole part, after "Fit clicks to": 2.9)
