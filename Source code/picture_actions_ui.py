"""Picture watch: what each watched picture does when it shows. The options are made by
_picture_action_form, used in the Picture watch window (picture_window.py) and in the small
"When this picture shows" window (edit_picture_action)."""
import os
import time
import tkinter as tk
from tkinter import filedialog, ttk

import macro_recorder as core
from macro_editor import key_from_id
from ui_common import *  # noqa: F401,F403
import macro_steps as workflow

image_watch = core.image_watch

CLICK_CHOICES = {None: "As in General (\"Click on it\")", True: "Yes", False: "No"}
NO_MACRO = "(choose a macro)"
NO_PICTURE = "(no other picture)"


def macro_label(path):
    return os.path.splitext(os.path.basename(path or ""))[0]


def action_summary(pic):
    """One line for the list: what this picture does."""
    action = pic.get("action", "restart")
    macro = macro_label(pic.get("macro")) or "?"
    text = {
        "restart": "Start the macro over",
        "play": f"Play \"{macro}\", then start over",
        "switch": f"Switch to \"{macro}\"",
        "recover": (f"Disconnect: play \"{macro}\" to get back in" if pic.get("macro")
                    else "Disconnect: get back into the game"),
        "skip": "Skip to the next step",
        "key": f"Press {workflow.key_text(pic.get('key') or {})}, go on",
        "wait": f"Wait {float(pic.get('seconds') or 0):g} s, go on",
        "stop": "Stop the macro",
        "nothing": "Nothing by itself",
    }.get(action, action)
    extra = []
    if pic.get("also"):
        extra.append("only with another picture")
    if pic.get("cooldown"):
        extra.append(f"cooldown {float(pic['cooldown']):g} s")
    return text + (f"  ({', '.join(extra)})" if extra else "")


class PictureActionsMixin:
    def _saved_macro_paths(self):
        paths = [p for p in self.settings.get("macro_library") or [] if isinstance(p, str)]
        return [p for p in paths if os.path.isfile(p)]

    def edit_picture_action(self, index):
        """The window for one watched picture: its name, what it does when it shows, and when."""
        if self.recording or self.playing or index >= len(self.watch_pictures):
            return
        pic = self.watch_pictures[index]
        parent = self.settings_win if self.settings_win is not None else self.root
        win = tk.Toplevel(parent, bg=BG)
        win.title("When this picture shows")
        win.transient(parent)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=18, pady=14)
        try:
            thumb, w, h = core.picture_thumb(pic, 420, 70)
            lab = tk.Label(body, image=thumb, bg=FIELD)
            lab.photo = thumb
            lab.pack(fill="x", pady=(0, 10))
        except Exception:
            pass
        form = self._picture_action_form(body, pic, self.watch_pictures, win)

        def save():
            new, problem = form.read()
            if problem:
                self.boxes.showinfo("Picture watch", problem, parent=win)
                return
            for k, v in new.items():
                if v is None or v == "":
                    pic.pop(k, None)
                else:
                    pic[k] = v
            self.capture_callback = None
            win.destroy()
            self._show_watch_pictures()
            self._save_settings()
            self._refresh()

        def close():
            self.capture_callback = None
            win.destroy()

        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(0, 14))
        ttk.Button(bottom, text="Save", style="Accent.TButton", width=8, command=save).pack(side="right")
        ttk.Button(bottom, text="Cancel", width=8, command=close).pack(side="right", padx=6)
        win.protocol("WM_DELETE_WINDOW", close)
        dark_title_bar(win)
        win.focus_force()
        self.picture_action_win = win
        win.save, win.vars = save, form.vars
        return win

    def _picture_action_form(self, body, pic, all_pictures, win, on_change=None, show_name=True,
                             wrap=470):
        """The options of one watched picture (name, what it does when it shows, and when), made in
        body. Returns a form: form.read() gives (the picture's new fields, a problem to show or None),
        form.vars its boxes. on_change() runs after anything in it was changed (None: nothing)."""
        rows = {}
        notify = (lambda *_a: on_change()) if on_change else (lambda *_a: None)

        def row(key, text, tip=None):
            f = tk.Frame(body, bg=BG)
            tk.Label(f, text=text, bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
            if tip:
                tk.Label(f, text=tip, bg=BG, fg=DIM, font=F_SMALL).pack(side="left", padx=(8, 0))
            rows[key] = f
            return f

        def entry(parent_row, var, width=10):
            e = tk.Entry(parent_row, textvariable=var, width=width, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat",
                         insertbackground=TEXT, highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT)
            e.pack(side="right", ipady=3)
            return e

        name_var = tk.StringVar(value=pic.get("name") or "")
        entry(row("name", "Name", "like Retry or Disconnected"), name_var, 24)

        action_var = tk.StringVar(value=core.WATCH_ACTION_NAMES.get(pic.get("action", "restart")))
        r = row("action", "When it shows")
        action_box = ttk.Combobox(r, textvariable=action_var, state="readonly", width=36,
                                  values=[n for _k, n, _w in core.WATCH_ACTIONS])
        action_box.pack(side="right")
        words = tk.Label(body, text="", bg=BG, fg=MUTED, font=F_SMALL, anchor="w", justify="left", wraplength=wrap)
        rows["words"] = words

        # the macro to play / switch to / rejoin with
        macros = {macro_label(p): p for p in self._saved_macro_paths()}
        if self.current_file and os.path.isfile(self.current_file):
            macros.setdefault(macro_label(self.current_file), self.current_file)
        state = {"macro": pic.get("macro") or "", "key": pic.get("key"),
                 "confirm_file": pic.get("confirm_file"), "confirm_screen_h": pic.get("confirm_screen_h")}
        if state["macro"]:
            macros.setdefault(macro_label(state["macro"]), state["macro"])
        macro_var = tk.StringVar(value=macro_label(state["macro"]) or NO_MACRO)
        r = row("macro", "Macro")
        ttk.Button(r, text="A macro file…", command=lambda: choose_file()).pack(side="right")
        macro_box = ttk.Combobox(r, textvariable=macro_var, state="readonly", width=24, values=list(macros))
        macro_box.pack(side="right", padx=(0, 6))

        def choose_file():
            path = filedialog.askopenfilename(parent=win, filetypes=core.OPEN_FILE_TYPES)
            if path:
                macros[macro_label(path)] = path
                macro_box.config(values=list(macros))
                macro_var.set(macro_label(path))

        # the key to press
        r = row("key", "Key")
        badge = tk.Label(r, text=workflow.key_text(state["key"] or {}) if state["key"] else "none yet", bg=BADGE,
                         fg=TEXT, font=(FAMILY, 10, "bold"), padx=10, pady=2)

        def capture():
            badge.config(text="Press a key…", fg=AMBER)

            def got(key_id):
                self.capture_callback = None
                if not win.winfo_exists():
                    return
                if key_id and key_id != "esc":
                    state["key"] = key_from_id(key_id)
                badge.config(text=workflow.key_text(state["key"] or {}) if state["key"] else "none yet", fg=TEXT)
                notify()
            self.capture_callback = got
        link(r, "Change", capture).pack(side="right")
        badge.pack(side="right", padx=(0, 10))

        seconds_var = tk.StringVar(value=f"{float(pic.get('seconds') or 5):g}")
        entry(row("seconds", "Wait (seconds)"), seconds_var)

        # disconnect recovery
        tries_var = tk.StringVar(value=str(int(pic.get("tries") or 3)))
        entry(row("tries", "How many tries", "each one waits longer: 15 s, 30 s, 60 s…"), tries_var, 6)
        r = row("confirm", "\"I'm back\" picture")
        confirm_text = tk.Label(r, text="", bg=BG, fg=MUTED, font=F_SMALL)

        def show_confirm():
            confirm_text.config(text="chosen" if state["confirm_file"] else "none (optional)")

        def got_confirm(img, screen_h):
            file = f"picture_{int(time.time() * 1000)}.png"
            image_watch.save_image(os.path.join(core.watch_dir(), file), img)
            state["confirm_file"], state["confirm_screen_h"] = file, screen_h
            show_confirm()
            notify()

        def confirm_from_screen():
            # (only the windows that are showing: the others mustn't pop up after picking)
            hidden = [w for w in (win.winfo_toplevel(), self.settings_win) if w is not None and w.winfo_viewable()]
            for w in hidden:
                w.withdraw()
            self.root.withdraw()
            self.root.after(300, lambda: self._show_picker(on_pick=got_confirm, hidden=tuple(hidden)))

        def confirm_from_file():
            path = filedialog.askopenfilename(parent=win, filetypes=[("Pictures", "*.png *.jpg *.jpeg *.bmp"),
                                                                     ("All files", "*.*")])
            if path:
                try:
                    got_confirm(image_watch.load_image(path), None)
                except Exception as exc:
                    self.boxes.showerror("Picture watch", f"Couldn't use that picture:\n{exc}", parent=win)

        def no_confirm():
            state["confirm_file"] = state["confirm_screen_h"] = None
            show_confirm()
            notify()
        link(r, "None", no_confirm).pack(side="right")
        ttk.Button(r, text="File…", command=confirm_from_file).pack(side="right", padx=6)
        ttk.Button(r, text="From screen…", command=confirm_from_screen).pack(side="right")
        confirm_text.pack(side="right", padx=(0, 8))
        show_confirm()
        confirm_s_var = tk.StringVar(value=f"{float(pic.get('confirm_seconds') or 60):g}")
        entry(row("confirm_seconds", "Wait for it up to (seconds)"), confirm_s_var, 6)

        # for every action
        click_var = tk.StringVar(value=CLICK_CHOICES[pic.get("click") if pic.get("click") in (True, False)
                                                     else None])
        r = row("click", "Click on it first")
        ttk.Combobox(r, textvariable=click_var, state="readonly", width=30,
                     values=list(CLICK_CHOICES.values())).pack(side="right")
        counts_var = tk.BooleanVar(value=core.watch_counts(pic))
        r = row("counts", "It means a run is finished", "counted in the results")
        Switch(r, counts_var).pack(side="right")
        cooldown_var = tk.StringVar(value=f"{float(pic.get('cooldown') or 0):g}")
        entry(row("cooldown", "Cooldown (seconds)", "not again within this time; 0 = none"), cooldown_var, 6)
        others = {NO_PICTURE: ""}
        for n, other in enumerate(all_pictures, start=1):
            if other is not pic and other.get("file") != pic.get("file"):
                others[f"{n}: {other.get('name') or 'picture ' + str(n)}"] = other["file"]
        also_now = next((label for label, file in others.items() if file and file == pic.get("also")), NO_PICTURE)
        also_var = tk.StringVar(value=also_now)
        r = row("also", "Only when this also shows")
        ttk.Combobox(r, textvariable=also_var, state="readonly", width=24, values=list(others)).pack(side="right")

        order = (["name"] if show_name else []) + [
            "action", "words", "macro", "key", "seconds", "tries", "confirm", "confirm_seconds",
            "click", "counts", "cooldown", "also"]
        only_for = {"macro": core.WATCH_NEED_MACRO, "key": ("key",), "seconds": ("wait",),
                    "tries": ("recover",), "confirm": ("recover",), "confirm_seconds": ("recover",),
                    "counts": ("restart", "play", "switch", "stop")}
        helps = {k: w for k, _n, w in core.WATCH_ACTIONS}
        helps["recover"] = ("For a \"Disconnected\" box: your rejoin macro plays (record the steps that get you back "
                            "into a mission), then it checks that this picture is gone and, if you chose one, that "
                            "the \"I'm back\" picture shows. If not, it tries again after a longer wait, and after "
                            "the last try it stops and tells Discord. Then the main macro starts over.")

        def action_key():
            return next(k for k, n, _w in core.WATCH_ACTIONS if n == action_var.get())

        def layout(_e=None, set_counts=False):
            action_box.selection_clear()
            action = action_key()
            if set_counts:
                counts_var.set(action == "restart")
            words.config(text=helps.get(action, "")[:1].upper() + helps.get(action, "")[1:].rstrip(".") + ".")
            for key in rows:
                rows[key].pack_forget()
            for key in order:
                if key not in only_for or action in only_for[key]:
                    rows[key].pack(fill="x", pady=4)
        action_box.bind("<<ComboboxSelected>>", lambda e: (layout(set_counts=True), notify()))
        layout()

        def number(var, default, low, high):
            try:
                return max(low, min(high, float(var.get().strip().replace(",", "."))))
            except ValueError:
                return default

        def read():
            action = action_key()
            macro = macros.get(macro_var.get(), "")
            problem = None
            if action in ("play", "switch") and not macro:
                problem = "Choose the macro it should play first."
            elif action == "key" and not state["key"]:
                problem = "Choose the key it should press first (Change)."
            click = next(k for k, v in CLICK_CHOICES.items() if v == click_var.get())
            counts = bool(counts_var.get()) if action in only_for["counts"] else None
            new = {
                "action": action if action != "restart" else None,
                "macro": macro if action in core.WATCH_NEED_MACRO else None,
                "key": state["key"] if action == "key" else None,
                "seconds": number(seconds_var, 5, 0, 36000) if action == "wait" else None,
                "click": click,
                "counts": None if counts is None or counts == (action == "restart") else counts,
                "cooldown": number(cooldown_var, 0, 0, 86400) or None,
                "also": others.get(also_var.get()) or None,
                "tries": int(number(tries_var, 3, 1, 20)) if action == "recover" else None,
                "confirm_file": state["confirm_file"] if action == "recover" else None,
                "confirm_screen_h": state["confirm_screen_h"] if action == "recover" else None,
                "confirm_seconds": number(confirm_s_var, 60, 1, 3600) if action == "recover" else None,
            }
            if show_name:
                new["name"] = name_var.get().strip()
            return new, problem

        for var in (name_var, macro_var, seconds_var, tries_var, confirm_s_var, click_var, counts_var,
                    cooldown_var, also_var):
            var.trace_add("write", notify)

        class Form:
            pass
        form = Form()
        form.read = read
        form.vars = {"action": action_var, "macro": macro_var, "name": name_var, "cooldown": cooldown_var,
                     "seconds": seconds_var, "counts": counts_var, "layout": layout, "macros": macros,
                     "state": state, "click": click_var, "also": also_var, "tries": tries_var}
        return form

    def _pictures_in_use(self):
        watch, own = super()._pictures_in_use()
        return watch | {p["confirm_file"] for p in self.watch_pictures if p.get("confirm_file")}, own

    # ------------------------------------------------------------ if the game closes

    CLOSED_CHOICES = {"wait": "Wait for it to come back", "stop": "Stop the macro and say why",
                      "reopen": "Open it again and rejoin"}
    CLOSED_HELP = (
        "If the game closes completely while a macro plays (it crashed, or was closed), the macro can't go on.\n\n"
        "Wait: the macro pauses until the game is in front again (as before).\n\n"
        "Stop: the macro stops and says why (Discord too, if that's set up).\n\n"
        "Open it again and rejoin: the app opens what you put in \"Open this\" (the game's link, or a "
        "shortcut or program file, just as if you double-clicked it), waits for the game's window, lets it "
        "load, then plays your rejoin macro (record the steps that get you from there back into a "
        "mission). Then the main macro starts over. If the game isn't back, it tries again after a "
        "longer wait each time (15 s, 30 s, 60 s…), and after the last try it stops and tells Discord.\n\n"
        "A \"Disconnected\" box inside the game is something else: add its picture in Picture watch "
        "and choose \"Disconnected: play my rejoin macro\" for it.")

    def closed_summary(self):
        opts = self._closed_settings()
        if not opts["on"]:
            return "Off"
        text = self.CLOSED_CHOICES[opts["action"]]
        if opts["action"] == "reopen" and opts["macro"]:
            text += f" (\"{macro_label(opts['macro'])}\")"
        return text

    def closed_switched(self):
        """The switch on the "If the game closes" row: off = wait for the game, as if nothing was set
        (what was chosen stays, for when it's turned on again)."""
        saved = self.settings.get("game_closed")
        saved = dict(saved) if isinstance(saved, dict) else {"action": "wait"}
        saved["on"] = bool(self.closed_on_var.get())
        self.settings["game_closed"] = saved
        self._save_settings()
        self._show_closed_choice()

    def open_game_closed(self):
        """Settings > Playback > "If the game closes": what to do, what to open, the rejoin macro."""
        opts = self._closed_settings()
        opts["action"] = opts["chosen"]
        parent = self.settings_win if self.settings_win is not None else self.root
        win = tk.Toplevel(parent, bg=BG)
        win.title("If the game closes")
        win.transient(parent)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=18, pady=14)

        def row(text, tip=None):
            f = tk.Frame(body, bg=BG)
            f.pack(fill="x", pady=4)
            tk.Label(f, text=text, bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
            if tip:
                tk.Label(f, text=tip, bg=BG, fg=DIM, font=F_SMALL).pack(side="left", padx=(8, 0))
            return f

        def entry(parent_row, var, width):
            e = tk.Entry(parent_row, textvariable=var, width=width, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat",
                         insertbackground=TEXT, highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT)
            e.pack(side="right", ipady=3)
            return e

        action_var = tk.StringVar(value=self.CLOSED_CHOICES[opts["action"]])
        r = row("If the game closes while playing")
        link(r, "ⓘ", lambda: self.boxes.showinfo("If the game closes", self.CLOSED_HELP, parent=win), bg=BG).pack(
            side="left", padx=(6, 0))
        box = ttk.Combobox(r, textvariable=action_var, state="readonly", width=28,
                           values=list(self.CLOSED_CHOICES.values()))
        box.pack(side="right", padx=(16, 0))
        open_var = tk.StringVar(value=opts["open"])
        r = row("Open this", "the game's link, or a file")
        ttk.Button(r, text="File…", command=lambda: pick_open()).pack(side="right")
        entry(r, open_var, 34).pack_configure(padx=(0, 6))

        def pick_open():
            path = filedialog.askopenfilename(parent=win)
            if path:
                open_var.set(path)

        macros = {macro_label(p): p for p in self._saved_macro_paths()}
        if opts["macro"]:
            macros.setdefault(macro_label(opts["macro"]), opts["macro"])
        macros = dict({"(none)": ""}, **macros)
        macro_var = tk.StringVar(value=macro_label(opts["macro"]) or "(none)")
        r = row("Rejoin macro", "played once the game is open")
        ttk.Button(r, text="A macro file…", command=lambda: pick_macro()).pack(side="right")
        macro_box = ttk.Combobox(r, textvariable=macro_var, state="readonly", width=22, values=list(macros))
        macro_box.pack(side="right", padx=(0, 6))

        def pick_macro():
            path = filedialog.askopenfilename(parent=win, filetypes=core.OPEN_FILE_TYPES)
            if path:
                macros[macro_label(path)] = path
                macro_box.config(values=list(macros))
                macro_var.set(macro_label(path))

        settle_var = tk.StringVar(value=str(opts["settle"]))
        entry(row("Let the game load for (seconds)", "before the rejoin macro"), settle_var, 6)
        tries_var = tk.StringVar(value=str(opts["tries"]))
        entry(row("How many tries", "each one waits longer"), tries_var, 6)

        def save():
            action = next(k for k, v in self.CLOSED_CHOICES.items() if v == action_var.get())
            macro = macros.get(macro_var.get(), "")
            if action == "reopen" and not open_var.get().strip() and not macro:
                self.boxes.showinfo("If the game closes", "Fill in what to open, or choose a rejoin macro "
                                    "that opens the game itself.", parent=win)
                return

            def whole(var, default):
                try:
                    return int(float(var.get().strip()))
                except ValueError:
                    return default
            new = {"action": action, "on": opts["on"], "open": open_var.get().strip(), "macro": macro,
                   "tries": max(1, min(20, whole(tries_var, 3))), "settle": max(0, min(600, whole(settle_var, 20)))}
            if action == "wait" and not new["open"] and not macro and new["on"]:
                self.settings.pop("game_closed", None)
            else:
                self.settings["game_closed"] = new
            win.destroy()
            self._save_settings()
            self._show_closed_choice()

        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(0, 14))
        ttk.Button(bottom, text="Save", style="Accent.TButton", width=8, command=save).pack(side="right")
        ttk.Button(bottom, text="Cancel", width=8, command=win.destroy).pack(side="right", padx=6)
        dark_title_bar(win)
        win.focus_force()
        win.save, win.vars = save, {"action": action_var, "open": open_var, "macro": macro_var, "macros": macros}
        return win

    def _show_closed_choice(self):
        if getattr(self, "closed_var", None) is not None:
            self.closed_var.set(self.closed_summary())
        if getattr(self, "closed_on_var", None) is not None:
            self.closed_on_var.set(self._closed_settings()["on"])

    # ------------------------------------------------------------ what recovery tells Discord

    def _recovery_event(self, kind, text):
        super()._recovery_event(kind, text)
        try:
            self._discord_recovery(kind, text)
        except Exception as exc:
            core.diag.error("Couldn't tell Discord about the reconnect", exc)
