"""(2.12) The Edit window's panels for the new actions and the new options of the old ones.
MacroEditor (macro_editor.py) inherits this class; the logic is in step_more.py."""
import os

import macro_steps as workflow
import step_more
from ui_common import *  # noqa: F401,F403


def _hint(box, text, color=None):
    tk.Label(box, text=text, bg=BG, fg=color or DIM, font=F_SMALL, anchor="w", justify="left",
             wraplength=460).pack(fill="x", pady=(6, 0))


class EditMoreMixin:
    # -------------------------------------------------------------- small pieces
    def _switch(self, box, label, a, key, tip=None, rebuild=False):
        on = tk.BooleanVar(value=a.get(key) is True)
        row = self._row(box, label, tip)
        owner = self._owner(a)

        def flip():
            self.change(lambda: a.__setitem__(key, bool(on.get())), select=owner["id"], keep_detail=not rebuild)
            self._refresh_row(a)
        Switch(row, on, command=flip).pack(side="right")
        return row

    def _rebuild_choice(self, box, label, a, key, options):
        """A drop-down whose choice shows other rows (the panel is built again)."""
        row = self._row(box, label)
        var = tk.StringVar(value=options.get(a.get(key), next(iter(options.values()))))
        combo = ttk.Combobox(row, textvariable=var, state="readonly", values=list(options.values()), width=28)
        combo.pack(side="right")
        owner = self._owner(a)

        def picked(_e=None):
            combo.selection_clear()
            value = next(k for k, v in options.items() if v == var.get())
            if a.get(key) != value:
                self.change(lambda: a.__setitem__(key, value), select=owner["id"])
        combo.bind("<<ComboboxSelected>>", picked)
        return combo

    def _counter_combo(self, box, label, holder, key, allow_empty=False, tip=None):
        """A counter's name: one the macro uses, or a new one typed in."""
        row = self._row(box, label, tip)
        var = tk.StringVar(value=holder.get(key) or "")
        names = workflow.counters(self.steps)
        combo = ttk.Combobox(row, textvariable=var, values=(["(a number)"] if allow_empty else []) + names, width=22)
        combo.pack(side="right")

        def changed(*_a):
            text = var.get().strip()
            if allow_empty and text in ("", "(a number)"):
                name = ""
            elif not text:
                return
            else:
                name = workflow.clean_counter_name(text)
            if holder.get(key) == name:
                return
            self._snapshot_for_typing()
            holder[key] = name
            self._refresh_row(holder)
        var.trace_add("write", changed)
        combo.bind("<<ComboboxSelected>>", lambda e: combo.selection_clear())
        return combo

    def _operand(self, box, label, a, key):
        """A number or a counter (Do maths): type a number, or pick / type a counter's name."""
        row = self._row(box, label, "a number or a counter")
        o = a.get(key) or {"number": 0}
        var = tk.StringVar(value=o["counter"] if "counter" in o else step_more.fmt(o.get("number", 0)))
        combo = ttk.Combobox(row, textvariable=var, values=workflow.counters(self.steps), width=22)
        combo.pack(side="right")

        def changed(*_a):
            text = var.get().strip()
            if not text:
                return
            try:
                new = {"number": step_more.clean_number(float(text.replace(",", ".")))}
            except ValueError:
                new = {"counter": workflow.clean_counter_name(text)}
            if a.get(key) == new:
                return
            self._snapshot_for_typing()
            a[key] = new
            self._refresh_row(a)
        var.trace_add("write", changed)
        combo.bind("<<ComboboxSelected>>", lambda e: combo.selection_clear())

    def _macro_choice(self, box, label, a, key):
        """Another saved macro to play (or none)."""
        here = self.entries[self.current][1] if self.current is not None else None
        macros = {"(none)": ""}
        macros.update({lbl: path for lbl, path in self.entries if path and path != here})
        if a.get(key) and a[key] not in macros.values():
            macros[os.path.splitext(os.path.basename(a[key]))[0]] = a[key]
        row = self._row(box, label)
        now = next((lbl for lbl, path in macros.items() if path == (a.get(key) or "")), "(none)")
        var = tk.StringVar(value=now)
        owner = self._owner(a)

        def set_file(path):
            if (path or "") != (a.get(key) or ""):
                self.change(lambda: a.__setitem__(key, path or ""), select=owner["id"], keep_detail=True)
                self._refresh_row(a)

        def from_file():
            path = filedialog.askopenfilename(parent=self.win, filetypes=core.OPEN_FILE_TYPES)
            if path:
                set_file(path)
                var.set(os.path.splitext(os.path.basename(path))[0])
        ttk.Button(row, text="A macro file…", command=from_file).pack(side="right")
        combo = ttk.Combobox(row, textvariable=var, state="readonly", values=list(macros), width=20)
        combo.pack(side="right", padx=(0, 6))
        combo.bind("<<ComboboxSelected>>", lambda e: (combo.selection_clear(), set_file(macros.get(var.get()))))

    def _then_row(self, box, a):
        self._macro_choice(box, "Then play another macro", a, "then_macro")

    def _program_choice(self, box, label, holder, key, none_text):
        """A program's window, from the windows open now (like "Record in which window?")."""
        import window_tools

        row = self._row(box, label)
        found = {}
        for _hwnd, title, exe in window_tools.app_windows():
            if exe and exe.lower() not in ("macrorecorder.exe", "macrorecorder_preview.exe", "python.exe",
                                           "pythonw.exe") and not window_tools.never_type_into(_hwnd, exe):
                found.setdefault(f"{exe} — {short(title, 30)}", {"exe": exe, "title": title[:60]})
        now = holder.get(key)
        choices = {none_text: None}
        if now:
            choices[f"{now['exe']} — {short(now.get('title') or '', 30)}"] = now
        choices.update(found)
        var = tk.StringVar(value=next((k for k, v in choices.items() if v == now), none_text))
        combo = ttk.Combobox(row, textvariable=var, state="readonly", values=list(choices), width=34)
        combo.pack(side="right")
        owner = self._owner(holder)

        def picked(_e=None):
            combo.selection_clear()
            value = choices.get(var.get())
            if value != holder.get(key):
                self.change(lambda: holder.__setitem__(key, value), select=owner["id"], keep_detail=True)
                self._refresh_row(holder)
        combo.bind("<<ComboboxSelected>>", picked)

    # -------------------------------------------------------------- new actions
    def _detail_else(self, box, a):
        if not self._else_has_if(a):
            _hint(box, "This Else isn't right after an If, so it never runs. Drag it right under an If "
                       "(not inside it).", AMBER)
        _hint(box, "Put this right after an If (or If a counter reaches). Its actions run only when that If's "
                   "condition was NOT true. Add actions into it while it's chosen.", MUTED)

    def _else_has_if(self, a):
        """(2.12) Is this Else right after an If (the action just before it, turned on)? The same rule as
        playback and Check my macro use."""
        found = workflow.find(self.steps, a.get("id"))
        if not found:
            return False
        _a, lst, i, _parent = found
        return step_more.else_has_if(lst, i)

    def _detail_wait_random(self, box, a):
        self._field(box, "From (seconds)", a, "seconds", float, 0, 36000)
        self._field(box, "To (seconds)", a, "max", float, 0, 36000)
        _hint(box, "Each time, a different wait between the two numbers.")

    def _detail_maths(self, box, a):
        self._counter_combo(box, "Put the result in", a, "counter", tip="a counter")
        self._operand(box, "First", a, "a")
        self._choice(box, "Do", a, "op", {"+": "+  add", "-": "−  take away", "*": "×  times", "/": "÷  divide"})
        self._operand(box, "Second", a, "b")
        self._choice(box, "Numbers", a, "decimals", {0: "Whole numbers (÷ rounds down)", 2: "2 decimals"})
        self._switch(box, "Show it on the timer at the top", a, "show_timer", "like Total: 1+4=5")
        self._switch(box, "Write it in the log", a, "show_log")
        self._switch(box, "Send it to Discord", a, "show_discord")
        self._switch(box, "Keep the result between plays", a, "keep")
        self._then_row(box, a)
        _hint(box, "Example: Total = 1 + Items. With Items at 4 the timer shows \"Total: 1+4=5\". A counter that "
                   "isn't set yet counts as 0. Dividing by 0 leaves the result as it was (the log says so). "
                   "Numbers stay between −1,000,000,000 and 1,000,000,000. Use {Total} in Type text or a "
                   "Discord message to write the number.")

    def _detail_read_clipboard(self, box, a):
        self._counter_combo(box, "Into the counter", a, "counter")
        self._switch(box, "Keep it between plays", a, "keep")
        self._then_row(box, a)
        _hint(box, "Takes the number you copied (Ctrl+C), like 1234, 1,234.5 or -12. When what's copied isn't a "
                   "number, the counter stays as it was and the log says so. The copied text itself is never "
                   "written to the log, saved or sent anywhere.")

    def _detail_discord(self, box, a):
        tk.Label(box, text="Message", bg=BG, fg=TEXT, font=F_BASE, anchor="w").pack(fill="x")
        text = tk.Text(box, height=4, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat", font=F_BASE,
                       highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT, wrap="word")
        text.pack(fill="x", pady=(4, 6))
        text.insert("1.0", a.get("text", ""))

        def typed(_e=None):
            value = text.get("1.0", "end-1c")[:step_more.TEXT_LETTERS]
            if value != a.get("text"):
                self._snapshot_for_typing()
                a["text"] = value
                self._refresh_row(a)
        text.bind("<KeyRelease>", typed)
        self._switch(box, "With a screenshot", a, "screenshot")
        self._rebuild_choice(box, "Send it to", a, "to", step_more.DESTINATIONS)
        if a.get("to") == "channel":
            self._field(box, "Channel ID", a, "channel", str, width=22, tip="empty = the one in Settings")
        _hint(box, "{Name} is replaced by that counter's number, like \"Total sum: {Total}\". Where the messages "
                   "go is set in Settings > Discord (webhook links stay there, never in the macro).")

    def _detail_sound(self, box, a):
        import sounds

        self._choice(box, "Sound", a, "sound", {ev: name for ev, name, _t, _o in sounds.EVENTS})
        row = tk.Frame(box, bg=BG)
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text="Play it now", command=lambda: self.app._sound(a.get("sound"), even_if_off=True)).pack(
            side="left")
        _hint(box, "It plays even when that sound is turned off in Settings > Sounds (your own sound file is "
                   "used when you chose one there).")

    def _detail_set_speed(self, box, a):
        self._field(box, "Speed (×)", a, "speed", float, 0.01, 100)
        _hint(box, "From here until this run ends; the next run starts at the speed you play at again.")

    def _detail_game(self, box, a):
        self._rebuild_choice(box, "What to do", a, "mode", {"front": "Bring the game to the front",
                                                            "wait": "Wait until the game is open, then that"})
        if a.get("mode") == "wait":
            self._field(box, "Wait up to (seconds)", a, "wait", float, 0, 3600)
            self._choice(box, "If it isn't open by then", a, "otherwise", {"go on": "Go on with the macro",
                                                                           "stop": "Stop the macro"})
        _hint(box, "The game is the program the macro was recorded in (or the one in front when you pressed Play).")

    def _detail_label(self, box, a):
        self._field(box, "Name", a, "name", str, width=22)
        _hint(box, "A spot Go to can jump to. It does nothing by itself.")

    def _detail_goto(self, box, a):
        labels = [b.get("name") for b, _l, _i, _p in workflow.walk(self.steps) if b.get("kind") == "label"]
        row = self._row(box, "Label")
        var = tk.StringVar(value=a.get("label", ""))
        combo = ttk.Combobox(row, textvariable=var, values=labels, width=22)
        combo.pack(side="right")

        def changed(*_a):
            name = workflow.clean_counter_name(var.get())
            if var.get().strip() and name != a.get("label"):
                self._snapshot_for_typing()
                a["label"] = name
                self._refresh_row(a)
        var.trace_add("write", changed)
        self._field(box, "At most how many jumps a run", a, "limit", int, 1, 1000000)
        if a.get("label") not in labels:
            _hint(box, f"There's no Label \"{a.get('label')}\" yet: add one (Add action > Label).", AMBER)
        _hint(box, "Jumps to the Label, in this list or a group around it. To keep a mistake from looping "
                   "forever, the macro stops (and Discord is told) after the jumps above in one run, or after "
                   f"{step_more.GOTO_FAST} jumps in a row where no time passes.")

    def _detail_screenshot(self, box, a):
        self._choice(box, "Send it to", a, "to", step_more.SHOT_TO)
        _hint(box, "The reports folder: Settings > About > Reports and logs. Discord: where Settings > Discord "
                   "sends the macro's messages. It shows what Settings > Discord > Screenshot of says.")

    # -------------------------------------------------------------- more options on the old actions
    def _more_key_rows(self, box, a):
        row = self._row(box, "Together with", "for combos like Ctrl+E")
        mods = list(a.get("mods") or [])
        for m in step_more.MODS:
            var = tk.BooleanVar(value=m in mods)

            def flip(m=m, var=var):
                new = [x for x in step_more.MODS if (x in a.get("mods", []) and x != m) or (x == m and var.get())]
                self.change(lambda: a.__setitem__("mods", new), select=a["id"], keep_detail=True)
                self._refresh_row(a)
            tk.Checkbutton(row, text={"cmd": "Win"}.get(m, m.title()), variable=var, command=flip, bg=BG, fg=TEXT,
                           selectcolor=FIELD, activebackground=BG, activeforeground=TEXT, font=F_SMALL).pack(
                side="right")
        self._field(box, "Time between presses (seconds)", a, "between", float, 0, 3600, tip="when more than once")

    def _more_type_rows(self, box, a):
        self._switch(box, "Press Enter at the end", a, "enter")
        self._rebuild_choice(box, "How", a, "how", {"letters": "Letter by letter", "paste": "Paste it (quick)"})
        self._program_choice(box, "Type it in", a, "window", "(the window in front)")
        self._then_row(box, a)
        _hint(box, "{Name} is replaced by that counter's number, like {Total}. In another program's window: it's "
                   "brought to the front, the text goes in, then the game comes back to the front. Paste uses the "
                   "clipboard for a moment and puts back what you had copied.")

    def _macro_to_screen(self, x, y):
        """A spot in the macro's size, on this screen (the opposite of _spot_to_macro)."""
        ax0, ay0 = self._spot_to_macro(0, 0)
        ax1, ay1 = self._spot_to_macro(1000, 1000)
        sx, sy = (ax1 - ax0) / 1000.0 or 1.0, (ay1 - ay0) / 1000.0 or 1.0
        return int(round((x - ax0) / sx)), int(round((y - ay0) / sy))

    def _show_spot(self, x, y, text="It clicks here"):
        """A ring on the screen for 3 seconds, where a click lands (it takes no clicks, nothing is pressed)."""
        ring = tk.Toplevel(self.win, bg="#ff00ff")
        ring.overrideredirect(True)
        ring.attributes("-topmost", True)
        try:
            ring.attributes("-transparentcolor", "#ff00ff")
        except tk.TclError:
            pass
        size = 44
        c = tk.Canvas(ring, width=size + 160, height=size, bg="#ff00ff", highlightthickness=0)
        c.pack()
        c.create_oval(4, 4, size - 4, size - 4, outline=RED, width=3)
        c.create_line(size // 2, 10, size // 2, size - 10, fill=RED, width=2)
        c.create_line(10, size // 2, size - 10, size // 2, fill=RED, width=2)
        c.create_text(size + 6, size // 2, text=text, fill=RED, anchor="w", font=F_BOLD)
        ring.geometry(f"+{x - size // 2}+{y - size // 2}")
        ring.after(3000, ring.destroy)
        return ring

    def _more_click_rows(self, box, a):
        self._rebuild_choice(box, "Where", a, "target", {"spot": "On the spot above",
                                                         "area": "In an area I draw",
                                                         "found": "Where a picture / colour was found"})
        target = a.get("target", "spot")
        if target == "area":
            row = self._row(box, "Area", f"{a['x0']}, {a['y0']} to {a['x1']}, {a['y1']}" if "x0" in a
                            else "not drawn yet")

            def drew(x0, y0, x1, y1):
                x0, y0 = self._spot_to_macro(x0, y0)
                x1, y1 = self._spot_to_macro(x1, y1)
                self.change(lambda: a.update(x0=min(x0, x1), y0=min(y0, y1), x1=max(x0, x1), y1=max(y0, y1)),
                            select=a["id"])
            ttk.Button(row, text="Draw the area…", command=lambda: self._draw_area_for(drew)).pack(side="right")
        if target in ("area", "found"):
            self._switch(box, "A random spot inside it", a, "random", "else its middle")
        self._field(box, "Offset right (pixels, − = left)", a, "dx", int, -5000, 5000)
        self._field(box, "Offset down (pixels, − = up)", a, "dy", int, -5000, 5000)
        self._field(box, "Small random offset (± pixels)", a, "jitter", int, 0, 200, tip="0 = exact")
        row = tk.Frame(box, bg=BG)
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text="Show where it clicks", command=lambda: self._preview_click(a)).pack(side="left")
        self.click_preview_note = tk.Label(row, text="", bg=BG, fg=MUTED, font=F_SMALL)
        self.click_preview_note.pack(side="left", padx=8)

    def _preview_click(self, a):
        """The ring where the click would land now, offset included (nothing is clicked)."""
        target = a.get("target", "spot")
        if target == "found":
            found = getattr(self.app, "last_found", None)
            if not found:
                self.click_preview_note.config(text="Nothing was found yet: play the macro (or a test) once.",
                                               fg=AMBER)
                return
            x, y, w, h = found
            x, y = x + w // 2, y + h // 2
        elif target == "area" and "x0" in a:
            x, y = self._macro_to_screen((a["x0"] + a["x1"]) // 2, (a["y0"] + a["y1"]) // 2)
        else:
            x, y = self._macro_to_screen(int(a.get("x", 0)), int(a.get("y", 0)))
        x, y = x + int(a.get("dx", 0)), y + int(a.get("dy", 0))
        self.click_preview_note.config(text=f"at {x}, {y} on this screen" + (
            f" (± {a['jitter']} px)" if a.get("jitter") else ""), fg=MUTED)
        self._show_spot(x, y)

    def _draw_area_for(self, on_area):
        self._draw_area(on_area)

    def _more_move_rows(self, box, a):
        self._switch(box, "Turn the camera instead (move by)", a, "relative", "for games", rebuild=True)
        if a.get("relative"):
            self._field(box, "Move right by (pixels, − = left)", a, "dx", int, -20000, 20000)
            self._field(box, "Move down by (pixels, − = up)", a, "dy", int, -20000, 20000)
        else:
            self._field(box, "Move slowly over (seconds)", a, "glide", float, 0, 60, tip="0 = at once")

    def _more_scroll_rows(self, box, a):
        self._field(box, "Time between notches (seconds)", a, "between", float, 0, 60, tip="0 = all at once")

    def _more_wait_rows(self, box, a):
        self._switch(box, "A random wait", a, "random", "between the seconds above and…", rebuild=True)
        if a.get("random"):
            a.setdefault("max", float(a.get("seconds", 1)) * 2)
            self._field(box, "…up to (seconds)", a, "max", float, 0, 36000)

    def _more_wait_picture_rows(self, box, a):
        self._choice(box, "Wait until it", a, "until", {"shows": "shows", "gone": "is gone"})
        if not a.get("color_on"):
            self._rebuild_choice(box, "Look", a, "where", {"screen": "On the whole screen",
                                                           "area": "Only in an area I draw"})
            if a.get("where") == "area":
                row = self._row(box, "Area", f"{a['x0']}, {a['y0']} to {a['x1']}, {a['y1']}" if "x0" in a
                                else "not drawn yet")

                def drew(x0, y0, x1, y1):
                    x0, y0 = self._spot_to_macro(x0, y0)
                    x1, y1 = self._spot_to_macro(x1, y1)
                    self.change(lambda: a.update(x0=min(x0, x1), y0=min(y0, y1), x1=max(x0, x1), y1=max(y0, y1)),
                                select=a["id"])
                ttk.Button(row, text="Draw the area…", command=lambda: self._draw_area_for(drew)).pack(side="right")
        if a.get("otherwise") == "macro":
            self._macro_choice(box, "The macro to play", a, "otherwise_macro")

    OTHERWISE = {"go on": "Go on with the macro", "stop": "Stop the macro", "macro": "Play a macro, then go on",
                 "restart": "Start over", "discord": "Tell Discord, then go on"}

    def _how_close(self, box, holder):
        """(2.12) "How close (%)" for pictures (Match %) and colours (100 − how different it may be)."""
        if holder.get("color_on"):
            row = self._row(box, "How close (%)", "100 = exactly this colour; 80-90 usual")
            var = tk.StringVar(value=str(100 - int(holder.get("tolerance", 10))))
            tk.Entry(row, textvariable=var, width=10, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat",
                     insertbackground=TEXT, highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=ACCENT).pack(side="right", ipady=3)

            def changed(*_a):
                try:
                    v = max(0, min(100, int(float(var.get().strip()))))
                except ValueError:
                    return
                if 100 - v != holder.get("tolerance"):
                    self._snapshot_for_typing()
                    holder["tolerance"] = 100 - v
            var.trace_add("write", changed)
        else:
            self._field(box, "How close (%)", holder, "match", int, 50, 99, tip="85 usual; higher = stricter")

    # -------------------------------------------------------------- conditions
    def _condition_kind_row(self, box, a, c):
        self._rebuild_choice(box, "Check", c, "type", step_more.CONDITION_TYPES)
        return c.get("type", "picture")

    def _condition_other_rows(self, box, a, c):
        """The rows of a counter / program / time condition."""
        t = c.get("type", "picture")
        if t == "counter":
            self._counter_combo(box, "Counter", c, "counter")
            self._choice(box, "Is", c, "op", {k: v for k, v in step_more.COMPARE.items()})
            self._counter_combo(box, "Than the counter", c, "other", allow_empty=True,
                                tip="or leave it for a number")
            if not c.get("other"):
                self._field(box, "Than the number", c, "value", float, -step_more.NUMBER_LIMIT, step_more.NUMBER_LIMIT)
        elif t == "window":
            self._choice(box, "When it", c, "shows", {True: "is open", False: "isn't open"})
            self._program_choice(box, "Program", c, "program", "(choose a program)")
        elif t == "time":
            note = tk.Label(box, text="", bg=BG, fg=AMBER, font=F_SMALL, anchor="w")
            boxes = {}
            for key, label in (("from", "From"), ("to", "To")):
                row = self._row(box, label, "hours : minutes")

                def changed(value, key=key):
                    # (2.12) only a whole time is kept; a half-typed one is shown in orange, not saved
                    half = [k for k, b in boxes.items() if b.value() is None or b.value() == ""]
                    note.config(text="Fill in both the hours and the minutes." if half else "")
                    if value and value != c.get(key):
                        self._snapshot_for_typing()
                        c[key] = value
                        self._refresh_row(c)
                boxes[key] = TimeBox(row, value=c.get(key, ""), on_change=changed)
                boxes[key].pack(side="right")
            note.pack(fill="x")
            self.time_boxes = boxes
            _hint(box, "By this PC's clock. Over midnight works too (22:00 to 02:00).")

    def _condition_more_rows(self, box, a, c):
        """Wait before deciding, and more conditions joined with AND / OR."""
        if c.get("type", "picture") == "picture":
            self._field(box, "Look for up to (seconds)", c, "wait", float, 0, 3600, tip="0 = one look")
        more = c.get("more") or []
        if more:
            self._choice(box, "Join them with", c, "join", {"and": "AND (all must be true)",
                                                            "or": "OR (one is enough)"})
        for n, m in enumerate(more):
            tk.Frame(box, bg=BORDER, height=1).pack(fill="x", pady=(8, 4))
            head = self._row(box, f"{'AND' if c.get('join', 'and') == 'and' else 'OR'} condition {n + 2}")
            link(head, "Remove", lambda n=n: self.change(lambda: c["more"].pop(n), select=a["id"]), bg=BG).pack(
                side="right")
            self._rebuild_choice(box, "Check", m, "type", step_more.CONDITION_TYPES)
            if m.get("type", "picture") == "picture":
                self._choice(box, "When this picture / colour", m, "shows", {True: "shows on screen", False: "doesn't show"})
                color = self._color_switch(box, a, m)
                if color:
                    self._color_rows(box, a, m)
                else:
                    self._picture_thumb(box, m, lambda fn: self.change(fn, select=a["id"]))
                    self._how_close(box, m)
            else:
                self._condition_other_rows(box, a, m)
        if len(more) < 8:
            row = tk.Frame(box, bg=BG)
            row.pack(fill="x", pady=(6, 0))

            def add():
                def do():
                    c.setdefault("more", []).append({"type": "counter", "counter": "Counter", "op": ">=", "value": 1,
                                                     "shows": True, "match": 85})
                    c.setdefault("join", "and")
                self.change(do, select=a["id"])
            ttk.Button(row, text="+ Another condition (AND / OR)", command=add).pack(side="left")

    # -------------------------------------------------------------- groups
    def _more_repeat_rows(self, box, a):
        self._rebuild_choice(box, "Repeat", a, "mode", {"times": "A number of times", "until": "Until something is true",
                                                        "minutes": "For some minutes", "forever": "Until stopped"})
        mode = a.get("mode", "times")
        if mode == "minutes":
            self._field(box, "For how many minutes", a, "minutes", float, 0.1, 100000)
        if mode == "until":
            c = a.setdefault("condition", {"shows": True, "png": None, "screen_h": None, "match": 85,
                                           "type": "counter", "counter": "Counter", "op": ">=", "value": 10})
            self._condition_block(box, a, c)
            _hint(box, "The actions inside run, then the condition is checked; it stops once it's true.")
        if mode == "forever":
            _hint(box, "Until you stop the macro (or a Stop / Go to inside ends it).")

    def _more_retry_rows(self, box, a):
        self._field(box, "Check for up to (seconds)", a, "check", float, 0, 3600, tip="after each try; was 2")
        self._field(box, "Wait between tries (seconds)", a, "between", float, 0, 3600)
        self._rebuild_choice(box, "If every try fails", a, "if_fails", {"go on": "Go on with the macro",
                                                                        "stop": "Stop the macro",
                                                                        "macro": "Play a macro, then go on"})
        if a.get("if_fails") == "macro":
            self._macro_choice(box, "The macro to play", a, "fail_macro")

    def _condition_block(self, box, a, c):
        """A whole condition (used by Repeat until): what to check and its rows."""
        t = self._condition_kind_row(box, a, c)
        if t == "picture":
            color = self._color_switch(box, a, c)
            self._choice(box, "When this colour" if color else "When this picture", c, "shows",
                         {True: "shows on screen", False: "doesn't show"})
            if color:
                self._color_rows(box, a, c)
            else:
                self._picture_thumb(box, c, lambda fn: self.change(fn, select=a["id"]))
                self._how_close(box, c)
        else:
            self._condition_other_rows(box, a, c)
        self._condition_more_rows(box, a, c)

    def _more_stop_rows(self, box, a):
        self._field(box, "Reason", a, "reason", str, width=30, tip="in the log and on Discord")
        self._switch(box, "Ping me on Discord", a, "ping", "with the Ping from Settings > Discord")

    def _more_note_rows(self, box, a):
        self._switch(box, "Show it on the timer at the top", a, "show", "while it plays")

    def _more_play_macro_rows(self, box, a):
        self._field(box, "Its own speed (×, 0 = the same)", a, "speed", float, 0, 100)

    def _more_if_counter_rows(self, box, a):
        self._choice(box, "Is", a, "op", step_more.COMPARE)
        self._counter_combo(box, "Than the counter", a, "other", allow_empty=True, tip="or the number above")
