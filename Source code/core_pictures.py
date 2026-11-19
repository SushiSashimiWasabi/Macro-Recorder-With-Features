"""The pictures to watch for: the list, the picker, which are on, matchers.

Part of the core MacroRecorder class (split out of macro_recorder.py in 2.13): its methods are
unchanged; a name that lives in macro_recorder itself is written core.name."""
from tkinter import ttk
import os
import time
import tkinter as tk
import macro_recorder as core


class CorePicturesMixin:
    def _build_watch_ui(self, frame):
        """'Watch for a picture': while playing, start the macro over when a picture shows on screen."""
        box = ttk.LabelFrame(frame, text="Watch for a picture", padding=8)
        box.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        s = self.settings
        # defaults: a tested AOT:R setup, so a friend only has to open their own macro
        self.watch_var = tk.BooleanVar(value=bool(s.get("watch_enabled", True)))
        self.watch_check = ttk.Checkbutton(
            box, variable=self.watch_var, command=self._save_settings,
            text="While playing, watch for these pictures (Change… says what each one does when it shows)")
        self.watch_check.grid(row=0, column=0, columnspan=4, sticky="w")

        buttons = ttk.Frame(box)
        buttons.grid(row=1, column=0, columnspan=4, sticky="w", pady=4)
        self.btn_pick = ttk.Button(buttons, text="Add from screen...", command=self.pick_watch_picture)
        self.btn_pick_file = ttk.Button(buttons, text="Add picture file...", command=self.load_watch_picture)
        self.btn_test = ttk.Button(buttons, text="Test now", command=self.test_watch_picture)
        self.btn_pick.grid(row=0, column=0, padx=(0, 4))
        self.btn_pick_file.grid(row=0, column=1, padx=4)
        self.btn_builtin = ttk.Button(buttons, text="Add built-in RETRY", command=self.add_builtin_picture)
        self.btn_test.grid(row=0, column=4, padx=4)
        self.btn_builtin.grid(row=0, column=2, padx=4)
        self.btn_builtin_dc = ttk.Button(buttons, text="Add built-in Disconnected",
                                         command=self.add_builtin_disconnect)
        self.btn_builtin_dc.grid(row=0, column=3, padx=4)
        self.watch_list = ttk.Frame(box)  # one row per picture: thumbnail + Remove
        self.watch_list.grid(row=2, column=0, columnspan=4, sticky="w")

        row = ttk.Frame(box)
        row.grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.watch_click_var = tk.BooleanVar(value=bool(s.get("watch_click", False)))
        ttk.Label(row, text="When it shows:").grid(row=0, column=0)
        ttk.Checkbutton(row, variable=self.watch_click_var, command=self._save_settings,
                        text="click on it (like a Retry button),").grid(row=0, column=1, padx=4)
        ttk.Label(row, text="wait").grid(row=0, column=2)
        self.watch_wait_var = tk.IntVar(value=core.int_setting(s, "watch_wait", 3, 0, 600))
        ttk.Spinbox(row, from_=0, to=600, width=5, textvariable=self.watch_wait_var,
                    command=self._save_settings).grid(row=0, column=3, padx=2)
        ttk.Label(row, text="s, then start the macro over.").grid(row=0, column=4)

        row1 = ttk.Frame(box)
        row1.grid(row=5, column=0, columnspan=4, sticky="w", pady=(4, 0))
        ttk.Label(row1, text="Match:").grid(row=0, column=0)
        self.watch_match_var = tk.IntVar(value=core.int_setting(s, "watch_match", 85, 50, 99))
        ttk.Spinbox(row1, from_=50, to=99, width=4, textvariable=self.watch_match_var,
                    command=self._save_settings).grid(row=0, column=1, padx=2)
        ttk.Label(row1, text="%").grid(row=0, column=2)

        row2 = ttk.Frame(box)
        row2.grid(row=4, column=0, columnspan=4, sticky="w", pady=(4, 0))
        ttk.Label(row2, text="If the macro ends before the picture shows, wait up to").grid(row=0, column=0)
        self.watch_end_var = tk.IntVar(value=core.int_setting(s, "watch_end_wait", 3, 0, 3600))
        ttk.Spinbox(row2, from_=0, to=3600, width=5, textvariable=self.watch_end_var,
                    command=self._save_settings).grid(row=0, column=1, padx=2)
        ttk.Label(row2, text="s for it").grid(row=0, column=2)

        self.watch_bg_var = tk.BooleanVar(value=bool(s.get("watch_ignore_bg", True)))
        ttk.Checkbutton(row1, variable=self.watch_bg_var, command=self._save_settings,
                        text="Ignore the background around text").grid(row=0, column=3, padx=(12, 0))

        # safety: a picture that keeps showing (a stuck screen) mustn't restart the macro forever
        row3 = ttk.Frame(box)
        row3.grid(row=6, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Label(row3, text="Safety limit: stop if it starts over more than").grid(row=0, column=0)
        self.watch_limit_var = tk.IntVar(value=core.int_setting(s, "watch_limit_count", 10, 0, 1000))
        ttk.Spinbox(row3, from_=0, to=1000, width=5, textvariable=self.watch_limit_var,
                    command=self._save_settings).grid(row=0, column=1, padx=2)
        ttk.Label(row3, text="times in").grid(row=0, column=2)
        self.watch_limit_s_var = tk.IntVar(value=core.int_setting(s, "watch_limit_seconds", 60, 1, 3600))
        ttk.Spinbox(row3, from_=1, to=3600, width=5, textvariable=self.watch_limit_s_var,
                    command=self._save_settings).grid(row=0, column=3, padx=2)
        ttk.Label(row3, text="s  (0 = no limit)").grid(row=0, column=4)
        self.watch_shift_var = tk.BooleanVar(value=bool(s.get("watch_shift_lock", True)))
        ttk.Checkbutton(box, variable=self.watch_shift_var, command=self._save_settings,
                        text="Before clicking it, press Shift if the mouse pointer is hidden (Roblox Shift Lock)"
                        ).grid(row=7, column=0, columnspan=4, sticky="w", pady=(4, 0))
        self.watch_embed_var = tk.BooleanVar(value=bool(s.get("watch_save_with_macro", True)))
        ttk.Checkbutton(box, variable=self.watch_embed_var, command=self._save_settings,
                        text="Save these pictures inside the macros you save (friends get them with the macro)"
                        ).grid(row=8, column=0, columnspan=4, sticky="w", pady=(4, 0))

        self.watch_widgets = [self.watch_check, self.btn_pick, self.btn_pick_file, self.btn_test,
                              self.btn_builtin, self.btn_builtin_dc]
        self.watch_remove_buttons = []
        if core.image_watch is None:
            self.watch_var.set(False)
            ttk.Label(self.watch_list, foreground="gray",
                      text="Not available: this copy was built without picture support.").grid(sticky="w")
            return
        saved = s.get("watch_pictures")
        if not isinstance(saved, list):
            # first start: the built-in pictures are added by the Picture watch setup (picture_window.py)
            saved = []
        for entry in saved:
            pic = core.watch_picture_from(entry)
            if pic is not None:  # (picture file gone: forget it)
                self.watch_pictures.append(pic)
        self._show_watch_pictures()

    def _show_watch_pictures(self):
        for child in self.watch_list.winfo_children():
            child.destroy()
        self.watch_thumbs = []
        self.watch_remove_buttons = []
        if not self.watch_pictures:
            ttk.Label(self.watch_list, text="No picture yet", foreground="gray").grid(sticky="w")
        for i, pic in enumerate(self.watch_pictures):
            thumb, w, h = core.picture_thumb(pic, 300, 50)
            self.watch_thumbs.append(thumb)
            # the picture and its size in two labels: a label with a picture can't show the
            # background picture behind its text
            cell = ttk.Frame(self.watch_list)
            cell.grid(row=i, column=0, sticky="w", pady=1)
            ttk.Label(cell, image=thumb).pack(side="left")
            ttk.Label(cell, text=f"  {w} x {h}").pack(side="left")
            b = ttk.Button(self.watch_list, text="Remove", command=lambda i=i: self._remove_watch_picture(i))
            b.grid(row=i, column=1, padx=(8, 0))
            self.watch_remove_buttons.append(b)
        self.settings["watch_pictures"] = [core.watch_entry(p) for p in self.watch_pictures]
        core.save_settings(self.settings)

    def add_builtin_picture(self):
        """Add the RETRY picture that comes with the app (AOT:R's Retry button, taken on a 1080p screen)."""
        if self.recording or self.playing:
            return
        try:
            self._add_watch_picture(core.image_watch.load_image(core.resource_path(core.BUILTIN_PICTURE)),
                                    screen_h=core.BUILTIN_PICTURE_SCREEN_H, fields={"builtin": "retry", "name": "RETRY"})
        except Exception as exc:
            core.messagebox.showerror("Macro Recorder", f"Couldn't add the built-in picture:\n{exc}")

    def add_builtin_disconnect(self):
        """Add the word "Disconnected" (Roblox's Disconnected box) with the action that plays a rejoin
        macro; the rejoin macro itself is chosen with Change…."""
        if self.recording or self.playing:
            return
        try:
            self._add_watch_picture(core.image_watch.load_image(core.resource_path(core.BUILTIN_DISCONNECT)),
                                    screen_h=core.BUILTIN_DISCONNECT_SCREEN_H,
                                    fields={"name": "Disconnected", "action": "recover", "builtin": "disconnect"})
        except Exception as exc:
            core.messagebox.showerror("Macro Recorder", f"Couldn't add the built-in picture:\n{exc}")

    def _add_watch_picture(self, img, screen_h=None, fields=None):
        name = f"picture_{int(time.time() * 1000)}.png"
        core.image_watch.save_image(os.path.join(core.watch_dir(), name), img)
        self.watch_pictures.append(dict({"img": img, "file": name, "screen_h": screen_h}, **(fields or {})))
        self.watch_var.set(True)
        self._save_settings()
        self._show_watch_pictures()
        self._refresh()

    def _remove_watch_picture(self, index):
        if self.recording or self.playing or index >= len(self.watch_pictures):
            return
        pic = self.watch_pictures.pop(index)
        try:
            os.remove(os.path.join(core.watch_dir(), pic["file"]))
        except OSError:
            pass
        self._show_watch_pictures()
        self._refresh()

    def _refresh_windows(self):
        names = [core.SCREEN_TARGET]
        self.target_windows = []
        if core.background is not None:
            own = self.root.winfo_toplevel().title()
            for hwnd, title in core.background.list_windows():
                if title in (own, "Program Manager"):
                    continue
                self.target_windows.append((hwnd, title))
                names.append(f"[background] {title}")
        self.target_box.config(values=names)
        if self.target_var.get() not in names:
            self.target_var.set(core.SCREEN_TARGET)

    def _selected_hwnd(self):
        label = self.target_var.get()
        for hwnd, title in self.target_windows:
            if label == f"[background] {title}":
                return hwnd
        return None

    def pick_watch_picture(self):
        """Freeze the screen and let the user drag a box around the picture to watch for."""
        if self.recording or self.playing:
            return
        self.root.withdraw()
        self.root.after(300, self._show_picker)

    def _show_picker(self, on_pick=None, on_cancel=None, hidden=(), on_area=None, tip=None):
        """Freeze the screen and let the user drag a box. on_pick(img, screen_h) gets the picture
        (default: add it to the pictures to watch for). hidden: other windows to show again after."""
        def show_again():
            self.root.deiconify()
            stack = getattr(self, "window_stack", None)
            if stack is not None:
                stack.bring_back(list(hidden))  # (the window it was picked from in front again)
                return
            for w in hidden:
                try:
                    w.deiconify()
                except tk.TclError:
                    pass
        try:
            shot = core.image_watch.grab_screen()
            with core.image_watch.mss.mss() as sct:
                mon = core.image_watch.primary_monitor(sct)
        except Exception as exc:
            show_again()
            core.messagebox.showerror("Macro Recorder", f"Couldn't take a screenshot:\n{exc}")
            return
        h, w = shot.shape[:2]
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry(f"{w}x{h}+{mon['left']}+{mon['top']}")
        canvas = tk.Canvas(win, width=w, height=h, highlightthickness=0, cursor="crosshair")
        canvas.pack()
        photo = tk.PhotoImage(data=core.image_watch.png_data(shot))
        canvas.create_image(0, 0, image=photo, anchor="nw")
        canvas.photo = photo
        tip = tip or ("Drag a box around the picture to watch for (for a banner, just around its text and line). "
                      "Esc cancels.")
        canvas.create_rectangle(0, 0, w, 36, fill="black", outline="")
        canvas.create_text(w // 2, 18, text=tip, fill="white", font=("Segoe UI", 12, "bold"))
        state = {"start": None, "rect": None}

        def close():
            win.destroy()
            show_again()

        def cancel():
            close()
            if on_cancel:
                on_cancel()

        def down(e):
            state["start"] = (e.x, e.y)
            if state["rect"]:
                canvas.delete(state["rect"])
            state["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=2)

        def drag(e):
            if state["start"]:
                x0, y0 = state["start"]
                canvas.coords(state["rect"], x0, y0, e.x, e.y)

        def up(e):
            if not state["start"]:
                return
            x0, y0 = state["start"]
            left, right = sorted((max(0, x0), min(w, e.x)))
            top, bottom = sorted((max(0, y0), min(h, e.y)))
            state["start"] = None
            if right - left < 10 or bottom - top < 10:
                return  # too small, probably a stray click: let them try again
            close()
            if on_area is not None:  # (2.12: only where the box is, on the screen)
                on_area(mon["left"] + left, mon["top"] + top, mon["left"] + right, mon["top"] + bottom)
                return
            try:
                (on_pick or (lambda img, sh: self._add_watch_picture(img, screen_h=sh)))(
                    shot[top:bottom, left:right].copy(), h)
            except Exception as exc:
                core.messagebox.showerror("Macro Recorder", f"Couldn't use that picture:\n{exc}")

        canvas.bind("<ButtonPress-1>", down)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", up)
        win.bind("<Escape>", lambda e: cancel())
        win.focus_force()

    def load_watch_picture(self):
        if self.recording or self.playing:
            return
        path = core.filedialog.askopenfilename(
            filetypes=[("Pictures", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")])
        if not path:
            return
        try:
            self._add_watch_picture(core.image_watch.load_image(path), screen_h=None)
        except Exception as exc:
            core.messagebox.showerror("Macro Recorder", f"Couldn't use that picture:\n{exc}")

    def _hide_own_window(self, screen, origin):
        """Black out this app's window on a screenshot: it shows the pictures themselves in its list,
        and they must not count as seen. (A plain black area never matches.)"""
        left, top, right, bottom = self.win_rect
        ox, oy = origin
        pad = 40  # the title bar and border too
        x0, y0 = max(0, left - ox - pad), max(0, top - oy - pad)
        x1, y1 = max(0, right - ox + pad), max(0, bottom - oy + pad)
        screen[y0:y1, x0:x1] = 0
        return screen

    def _picture_active(self, pic, path=None):
        """Whether a picture is used now: it's on, its group is on, and it's for every macro or for
        this one (path: the macro; None = the open one)."""
        if not core.picture_on(pic):
            return False
        gid = core.picture_group(pic)
        for g in self.settings.get("picture_groups") or []:
            if isinstance(g, dict) and g.get("id") == gid:
                if g.get("on") is False:
                    return False
                break
        macros = pic.get("macros")
        if macros:
            path = path if path is not None else self.current_file
            if not path:
                return False
            key = self._macro_key(path)
            return any(isinstance(m, str) and self._macro_key(m) == key for m in macros)
        return True

    def _active_watch_pictures(self, path=None):
        return [p for p in self.watch_pictures if self._picture_active(p, path)]

    def _active_result_pictures(self, path=None):
        return [p for p in self.result_pictures if self._picture_active(p, path)]

    def picture_need(self, pic):
        """How well a watched picture must match (0.5-0.99): its own Match %, or General's."""
        own = pic.get("match")
        if isinstance(own, (int, float)) and not isinstance(own, bool):
            return max(50, min(99, int(own))) / 100.0
        return self.settings.get("watch_match", 80) / 100.0

    def picture_ignores_bg(self, pic):
        own = pic.get("ignore_bg")
        return own if isinstance(own, bool) else bool(self.watch_bg_var.get())

    def _make_matchers(self):
        matchers = []
        for pic in self._active_watch_pictures():
            if pic.get("action") == "count" or pic.get("color_on"):
                continue  # (2.12: counted on their own, alongside; a colour's file is only a swatch)
            m = core.image_watch.Matcher(pic["img"], picked_screen_h=pic["screen_h"],
                                    ignore_background=self.picture_ignores_bg(pic), screen_h=self.screen_h)
            m.need = self.picture_need(pic)
            # where it was found last time (this session): the next playback looks there first
            m.last_rect = pic.get("seen_rect")
            m.picture_entry = pic
            matchers.append(m)
        return matchers

    def test_watch_picture(self):
        """Look at the screen once and say how well each picture matches right now."""
        if not self.watch_pictures:
            core.messagebox.showinfo("Macro Recorder", "Add a picture first.")
            return
        self._save_settings()
        need = self.settings.get("watch_match", 80)
        try:
            screen = self._hide_own_window(core.image_watch.grab_screen(), core.image_watch.screen_origin())
            scores =[round(m.find(screen)[0] * 100) for m in self._make_matchers()]
        except Exception as exc:
            core.messagebox.showerror("Macro Recorder", f"Couldn't check the screen:\n{exc}")
            return
        lines = [f"Picture {i}: {pct}%  ({'counts as seen' if pct >= need else 'not seen'})"
                 for i, pct in enumerate(scores, start=1)]
        core.messagebox.showinfo(
            "Macro Recorder",
            "How well each picture matches the screen right now (it counts as seen from "
            f"{need}%):\n\n" + "\n".join(lines) +
            "\n\nTry this while a picture is showing, and again while it isn't. Set Match between the two.")
