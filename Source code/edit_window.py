"""The list of a recorded step's events (from the Edit window: "Edit the recorded events…"):
remove some, remove all mouse moves, cut the wait at the start, add or change waits, and "Wait for a
picture" inside the recording.

Part of the dark window: ModernMacroRecorder (modern_ui.py) inherits this class.
"""

from ui_common import *  # noqa: F401,F403  (colours, fonts, widgets, tk, core, the other modules)


MANUAL_KINDS = (("key", "Key press…"), ("type", "Type text…"), ("click", "Mouse click…"),
                ("move", "Mouse move…"), ("scroll", "Scroll…"))
MANUAL_TITLES = dict(MANUAL_KINDS)


class EditWindowMixin:
    def _manual_event_dialog(self, events_win, editor_win, kind, where_choices, on_done):
        """Ask for one key press / typing / click / move / scroll and where it goes:
        on_done(action, where), the action as the Edit window's steps have it."""
        from macro_editor import key_from_id

        win = tk.Toplevel(events_win, bg=BG)
        win.title(MANUAL_TITLES[kind].rstrip("…"))
        win.transient(events_win)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=18, pady=14)
        a = workflow.new_action(kind)
        fields = {}

        def line(text):
            r = tk.Frame(body, bg=BG)
            r.pack(fill="x", pady=(6, 0))
            tk.Label(r, text=text, bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
            return r

        def entry(text, key, value, width=8):
            var = tk.StringVar(value=f"{value:g}" if isinstance(value, (int, float)) else str(value))
            tk.Entry(line(text), textvariable=var, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat",
                     insertbackground=TEXT, width=width).pack(side="right", ipady=2)
            fields[key] = var
            return var

        def combo(text, key, options, value):
            var = tk.StringVar(value=options[value])
            ttk.Combobox(line(text), width=16, state="readonly", textvariable=var,
                         values=list(options.values())).pack(side="right")
            fields[key] = (var, options)

        def point_rows():
            x = entry("X (from the left of the screen)", "x", 0)
            y = entry("Y (from the top)", "y", 0)

            def pick():
                def picked(px, py):
                    x.set(str(px))
                    y.set(str(py))
                    win.lift()
                self._pick_point(win, picked, hidden=(events_win, editor_win))
            r = tk.Frame(body, bg=BG)
            r.pack(fill="x", pady=(6, 0))
            ttk.Button(r, text="Pick the spot on the screen…", command=pick).pack(side="left")

        if kind == "key":
            r = line("Key")
            badge = tk.Label(r, text=workflow.key_text(a["key"]), bg=BADGE, fg=TEXT, font=(FAMILY, 10, "bold"), padx=10, pady=2)

            def capture():
                badge.config(text="Press a key…", fg=AMBER)

                def got(key_id):
                    self.capture_callback = None
                    if not win.winfo_exists():
                        return
                    if key_id and key_id != "esc":
                        a["key"] = key_from_id(key_id)
                    badge.config(text=workflow.key_text(a["key"]), fg=TEXT)
                self.capture_callback = got
            link(r, "Change", capture).pack(side="right")
            badge.pack(side="right", padx=(0, 10))
            combo("What to do", "mode", {"press": "Press it", "down": "Hold it down", "up": "Let go of it"},
                  "press")
            entry("How many times", "times", 1)
            entry("Hold for (seconds, 0 = quick)", "hold", 0)
        elif kind == "type":
            tk.Label(body, text="Text to type", bg=BG, fg=TEXT, font=F_BASE, anchor="w").pack(fill="x")
            text = tk.Text(body, height=4, width=40, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat",
                           font=F_BASE, wrap="word")
            text.pack(fill="x", pady=(4, 0))
            entry("Time between letters (seconds)", "delay", 0.02)
        elif kind == "click":
            point_rows()
            combo("Button", "button", {"left": "Left", "right": "Right", "middle": "Middle"}, "left")
            combo("Click", "mode", {"click": "Click", "double": "Double-click", "down": "Hold down",
                                    "up": "Let go"}, "click")
            entry("Hold for (seconds, 0 = quick)", "hold", 0)
        elif kind == "move":
            point_rows()
        elif kind == "scroll":
            combo("Direction", "dir", {"down": "Down", "up": "Up"}, "down")
            entry("How many notches", "amount", 3)
        where_names = dict(where_choices)
        where_var = tk.StringVar(value=where_choices[0][0])
        ttk.Combobox(line("Put it"), width=22, state="readonly", textvariable=where_var,
                     values=list(where_names)).pack(side="right")

        def number(key, cast, low, high):
            value = cast(float(fields[key].get().replace(",", ".")))
            return max(low, min(high, value))

        def picked_value(key):
            var, options = fields[key]
            return next(k for k, v in options.items() if v == var.get())

        def ok():
            try:
                if kind == "key":
                    a.update(mode=picked_value("mode"), times=number("times", int, 1, 1000),
                             hold=number("hold", float, 0, 3600))
                elif kind == "type":
                    a.update(text=text.get("1.0", "end-1c"), delay=number("delay", float, 0, 5))
                    if not a["text"]:
                        self.boxes.showinfo("Add action", "Type the text first.", parent=win)
                        return
                elif kind in ("click", "move"):
                    a.update(x=number("x", int, -100000, 100000), y=number("y", int, -100000, 100000))
                    if kind == "click":
                        a.update(button=picked_value("button"), mode=picked_value("mode"),
                                 hold=number("hold", float, 0, 3600))
                elif kind == "scroll":
                    notches = number("amount", int, 1, 1000)
                    a["amount"] = notches if picked_value("dir") == "up" else -notches
            except (ValueError, tk.TclError):
                self.boxes.showinfo("Add action", "Type numbers in the boxes.", parent=win)
                return
            close()
            on_done(a, where_names[where_var.get()])

        def close():
            self.capture_callback = None
            win.destroy()

        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(0, 14))
        ttk.Button(bottom, text="Add", style="Accent.TButton", width=8, command=ok).pack(side="right")
        ttk.Button(bottom, text="Cancel", width=8, command=close).pack(side="right", padx=6)
        win.protocol("WM_DELETE_WINDOW", close)
        dark_title_bar(win)
        win.focus_force()
        return win

    def _events_window(self, parent, events, on_done):
        """Change a recorded step's events; on_done(events) gets them when Apply is pressed."""
        win = tk.Toplevel(parent, bg=BG)
        win.transient(parent)
        win.title("Recorded events - Macro Recorder")
        win.attributes("-topmost", True)
        win.geometry("620x640")
        win.minsize(460, 360)
        dark_title_bar(win)

        top = tk.Frame(win, bg=BG)
        top.pack(fill="x", padx=14, pady=(12, 6))
        summary = tk.StringVar()
        tk.Label(top, textvariable=summary, bg=BG, fg=MUTED, font=F_BASE, anchor="w").pack(side="left")

        table = tk.Frame(win, bg=BG)
        table.pack(fill="both", expand=True, padx=14)
        tree = ttk.Treeview(table, columns=("time", "action", "detail"), show="headings", selectmode="extended")
        for col, text, width in (("time", "Time", 80), ("action", "Action", 160), ("detail", "Details", 220)):
            tree.heading(col, text=text, anchor="w")
            tree.column(col, width=width, anchor="w", stretch=col == "detail")
        bar = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=bar.set)
        tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        tree.tag_configure("move", foreground=MUTED)
        tree.tag_configure("step", foreground=AMBER)

        def fill(start=0):
            """Show the events in the list; start: only the rows from there on changed (the rows
            before it are left as they are, which is much quicker in a long recording)."""
            rows = tree.get_children()
            start = max(0, min(start, len(rows), len(events)))
            if rows[start:]:
                tree.delete(*rows[start:])
            for i in range(start, len(events)):
                ev = events[i]
                action, detail = describe(ev)
                tags = ("move",) if ev.get("type") in ("move", "move_rel") else (
                    ("step",) if ev.get("type") == "wait_picture" else ())
                tree.insert("", "end", iid=str(i), values=(f"{ev['t']:.2f} s", action, detail), tags=tags)
            length = events[-1]["t"] if events else 0
            summary.set(f"{len(events)} actions, {length:.1f} s. Choose rows to change them.")

        # (2.11) Undo / Redo: a copy of the list before each change
        undo_stack, redo_stack = [], []
        note = tk.StringVar()

        def snap():
            undo_stack.append([dict(ev) for ev in events])
            del undo_stack[:-100]
            redo_stack.clear()
            show_undo()

        def jump(src, dst):
            if not src:
                return
            dst.append([dict(ev) for ev in events])
            events[:] = src.pop()
            fill()
            show_undo()

        def show_undo():
            if "undo_btn" in buttons:
                buttons["undo_btn"].config(state="normal" if undo_stack else "disabled")
                buttons["redo_btn"].config(state="normal" if redo_stack else "disabled")

        def chosen():
            return sorted(int(i) for i in tree.selection())

        def with_partners(rows):
            """The chosen rows, plus the let-go of a chosen press (and the press of a chosen let-go),
            so a key or mouse button is never left held down. Returns (rows, names of what was added)."""
            rows = set(rows)
            added = []

            def same(a, b):
                if a.get("type") != b.get("type"):
                    return False
                return a.get("key") == b.get("key") if a.get("type") == "key" else a.get("button") == b.get("button")
            for i in sorted(rows):
                ev = events[i]
                if ev.get("type") not in ("key", "click"):
                    continue
                if ev.get("pressed"):
                    k = next((j for j in range(i + 1, len(events)) if same(events[j], ev)
                              and not events[j].get("pressed")), None)
                else:
                    k = next((j for j in range(i - 1, -1, -1) if same(events[j], ev) and events[j].get("pressed")),
                             None)
                if k is not None and k not in rows:
                    rows.add(k)
                    added.append(describe(events[k])[1] or describe(events[k])[0])
            return sorted(rows), added

        def tell(added):
            note.set((", ".join(added[:3]) + ("…" if len(added) > 3 else "") + ": the matching press or let-go "
                      "was taken along too, so nothing stays held down.") if added else "")

        def take(rows):
            """Copies of these rows, timed from 0, and how long they last."""
            first = events[rows[0]]["t"]
            block = [dict(events[i], t=round(events[i]["t"] - first, 4)) for i in rows]
            return block, block[-1]["t"] + 0.03

        def remove_selected(ask=True):
            rows, added = with_partners(chosen())
            if not rows:
                return
            if ask and len(rows) > 5 and not self.boxes.askyesno(
                    "Remove actions", f"Remove these {len(rows)} actions?\n\nUndo puts them back.", parent=win):
                return
            snap()
            gone = set(rows)
            events[:] = [ev for i, ev in enumerate(events) if i not in gone]
            fill(min(rows))
            tell(added)

        def copy_rows():
            rows, added = with_partners(chosen())
            if rows:
                self.events_clipboard = take(rows)
                tell(added)

        def cut_rows():
            if chosen():
                copy_rows()
                remove_selected(ask=False)

        def paste_rows():
            clip = getattr(self, "events_clipboard", None)
            if not clip:
                return
            snap()
            insert_block([dict(ev) for ev in clip[0]], clip[1], "after" if chosen() else "end", snapped=True)

        def duplicate_rows():
            rows, added = with_partners(chosen())
            if not rows:
                return
            block, length = take(rows)
            snap()
            tree.selection_set([str(i) for i in rows])
            insert_block(block, length, "after", snapped=True)
            tell(added)

        def move_rows(rows, target, where):
            """Move rows before / after another row: they keep their own timing, the gap they leave
            closes, and what comes after their new place moves later by their length."""
            rows, added = with_partners(rows)
            if not rows or target in rows:
                return
            snap()
            gone = set(rows)
            block, length = take(rows)
            last = events[rows[-1]]["t"]
            target_ev = events[target]
            rest = [ev for i, ev in enumerate(events) if i not in gone]
            for ev in rest:  # (the gap closes)
                if ev["t"] > last:
                    ev["t"] = round(max(0.0, ev["t"] - length), 4)
            pos = next(k for k, ev in enumerate(rest) if ev is target_ev)
            if where == "after":
                pos += 1
                start = target_ev["t"] + 0.03
            else:
                start = target_ev["t"]
            for ev in rest[pos:]:
                ev["t"] = round(ev["t"] + length + (0.03 if where == "after" else 0.0), 4)
            for ev in block:
                ev["t"] = round(start + ev["t"], 4)
            events[:] = rest[:pos] + block + rest[pos:]
            fill(0)
            new = [str(pos + k) for k in range(len(block))]
            tree.selection_set(new)
            tree.see(new[0])
            tell(added)

        # (2.11) preview the chosen rows: play them as a test, show them without pressing, Show my clicks
        def chosen_rows_step():
            """A recorded step with copies of the chosen rows (and the matching press / let-go), timed
            from the first one; the time between rows that are far apart is skipped."""
            rows, added = with_partners(chosen())
            if not rows:
                messagebox.showinfo("Macro Recorder", "Choose the rows to preview first.", parent=win)
                return None, []
            out, t, prev = [], 0.0, None
            for i in rows:
                if prev is not None:
                    t += events[i]["t"] - events[prev]["t"] if i == prev + 1 else 0.05
                out.append(dict(events[i], t=round(t, 4)))
                prev = i
            step = workflow.new_action("recorded")
            step["events"] = out
            return step, added

        def fit_of():
            ed = getattr(self, "macro_editor", None)
            if ed is not None and ed.win.winfo_exists():
                return ed._macro_fit()
            return self.macro_screen, self.macro_program

        def preview(mode):
            step, added = chosen_rows_step()
            if step is None:
                return
            tell(added)
            if mode == "clicks":
                ed = getattr(self, "macro_editor", None)
                if ed is None or not ed.win.winfo_exists():
                    return
                import clicks_view

                return clicks_view.open_clicks(ed, steps=[step], owner=win)
            screen, program = fit_of()
            ed = getattr(self, "macro_editor", None)
            found = not (ed is not None and getattr(ed, "ghost_not_found", None) is not None
                         and ed.ghost_not_found.get())
            self.test_restore = [w for w in (parent, win) if w.winfo_exists()]
            for w in self.test_restore:
                w.withdraw()
            if not self.play_test([step], mode, screen, program, found=found):
                for w in self.test_restore:
                    w.deiconify()
                self.test_restore = []
            return True

        def preview_menu(x, y):
            m = tk.Menu(win, tearoff=False, bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground="white",
                        bd=0, font=F_BASE)
            ok = "normal" if chosen() and not self.playing and not self.recording else "disabled"
            m.add_command(label="Play the chosen rows (test)", command=lambda: preview("test"), state=ok)
            m.add_command(label="Show without playing (nothing is pressed)", command=lambda: preview("ghost"),
                          state=ok)
            m.add_command(label="Show my clicks…", command=lambda: preview("clicks"), state=ok)
            m.tk_popup(x, y)

        def right_click(e):
            iid = tree.identify_row(e.y)
            if iid and iid not in tree.selection():
                tree.selection_set(iid)
            preview_menu(e.x_root, e.y_root)

        def move_by(d):
            rows = chosen()
            if not rows:
                return
            if d < 0 and rows[0] > 0:
                move_rows(rows, rows[0] - 1, "before")
            elif d > 0 and rows[-1] + 1 < len(events):
                move_rows(rows, rows[-1] + 1, "after")

        def remove_moves():
            n = sum(1 for ev in events if ev.get("type") == "move")
            if not n:
                messagebox.showinfo("Macro Recorder", "There are no mouse moves to remove.", parent=win)
                return
            if messagebox.askyesno("Macro Recorder", f"Remove all {n} mouse moves? Clicks keep their position, "
                                   "and camera turns are kept.", parent=win):
                snap()
                events[:] = [ev for ev in events if ev.get("type") != "move"]
                fill()

        def trim_start():
            if not events or events[0]["t"] <= 0:
                return
            gap = events[0]["t"]
            snap()
            for ev in events:
                ev["t"] = round(ev["t"] - gap, 4)
            fill()

        def selected_index():
            picked = sorted(int(i) for i in tree.selection())
            return picked[0] if picked else None

        def show_row(i):
            fill(max(0, i - 1))
            if 0 <= i < len(events):
                tree.selection_set(str(i))
                tree.see(str(i))

        def ask_seconds(title, text, start):
            value = self.boxes.asknumber(title, text, start, 0, 3600, parent=win)
            return None if value is None else round(value, 3)

        def add_wait():
            """A pause before the selected action: it and everything after it move later."""
            i = selected_index()
            if i is None:
                messagebox.showinfo("Macro Recorder", "Select the action the wait should come before.", parent=win)
                return
            secs = ask_seconds("Add a wait", "Wait how many seconds before the selected action?", 1.0)
            if not secs:
                return
            snap()
            for ev in events[i:]:
                ev["t"] = round(ev["t"] + secs, 4)
            show_row(i)

        def change_wait():
            """Set the time between the selected action and the one before it."""
            i = selected_index()
            if i is None:
                messagebox.showinfo("Macro Recorder", "Select the action whose wait you want to change.",
                                    parent=win)
                return
            gap = events[i]["t"] - (events[i - 1]["t"] if i > 0 else 0.0)
            secs = ask_seconds("Change the wait", f"Seconds between the action before and the selected one "
                               f"(now {gap:.2f} s):", round(gap, 2))
            if secs is None:
                return
            shift = secs - gap
            snap()
            for ev in events[i:]:
                ev["t"] = round(max(0.0, ev["t"] + shift), 4)
            show_row(i)

        def add_picture_step():
            i = selected_index()
            if i is None:
                i = len(events)
            self._picture_step_dialog(win, lambda step: insert_step(i, step))

        def insert_step(i, step):
            snap()
            step["t"] = events[i]["t"] if i < len(events) else (events[-1]["t"] if events else 0.0)
            events.insert(i, step)
            show_row(i)

        def edit_step(_e=None):
            i = selected_index()
            if i is None or events[i].get("type") != "wait_picture":
                return
            def replace(step):
                snap()
                step["t"] = events[i]["t"]
                events[i] = step
                show_row(i)
            self._picture_step_dialog(win, replace, events[i])

        def where_choices():
            choices = []
            if selected_index() is not None:
                choices += [("After the selected row", "after"), ("Before the selected row", "before")]
            return choices + [("At the end", "end"), ("At the start", "start")]

        def insert_block(block, length, where, snapped=False):
            """Put timed events (their "t" counted from 0, lasting `length` s) in the list; the
            events after them move later by that much."""
            if not block:
                return
            if not snapped:
                snap()
            i = selected_index()
            if where == "start" or not events:
                pos, start, shift = 0, (events[0]["t"] if events else 0.0), length
            elif where == "before" and i is not None:
                pos, start, shift = i, events[i]["t"], length
            elif where == "after" and i is not None:
                last = max(int(r) for r in tree.selection())
                pos, start, shift = last + 1, events[last]["t"] + 0.03, length + 0.03
            else:
                pos, start, shift = len(events), events[-1]["t"] + 0.1, 0.0
            for ev in events[pos:]:
                ev["t"] = round(ev["t"] + shift, 4)
            for k, ev in enumerate(block):
                ev["t"] = round(start + ev["t"], 4)
            events[pos:pos] = block
            fill(pos)
            rows = [str(pos + k) for k in range(len(block))]
            tree.selection_set(rows)
            tree.see(rows[-1])
            tree.see(rows[0])

        def add_action(kind):
            def done(action, where):
                block, t = [], 0.0
                for ev in self._step_events(action):
                    ev = dict(ev)
                    pause = ev.pop("pause", 0.0)
                    ev["t"] = t
                    block.append(ev)
                    t += pause
                insert_block(block, max(0.03, t), where)
            self._manual_event_dialog(win, parent, kind, where_choices(), done)

        def add_menu():
            menu = tk.Menu(win, tearoff=False, bg=PANEL, fg=TEXT, activebackground=ACCENT,
                           activeforeground="white", bd=0, font=F_BASE)
            for kind, label in MANUAL_KINDS:
                menu.add_command(label=label, command=lambda k=kind: add_action(k))
            menu.tk_popup(add_btn.winfo_rootx(), add_btn.winfo_rooty() + add_btn.winfo_height())

        def record_here():
            """Record keys and mouse now and put the recording in this list."""
            if self.recording or self.playing:
                return
            choices = where_choices() + [("Cancel", None)]
            where = self.boxes.askchoice(
                "Record here", "Where should the new recording go?\n\nAfter you choose, recording starts at "
                f"once. Press the Record key ({core.hotkey_name(self.hotkeys['record'])}) again to stop it; this "
                "window then comes back.", choices, default=choices[0][1], parent=win)
            if where is None:
                return

            def done(recorded):
                for w in (parent, win):
                    try:
                        w.deiconify()
                    except tk.TclError:
                        pass
                win.lift()
                if not recorded or not win.winfo_exists():
                    return
                ed = getattr(self, "macro_editor", None)
                if ed is not None and ed.win.winfo_exists():
                    recorded = ed.to_macro_size(recorded)  # (2.11: the macro's own size)
                first = recorded[0]["t"]
                block = [dict(ev, t=round(ev["t"] - first, 4)) for ev in recorded]
                insert_block(block, block[-1]["t"] + 0.05, where)
            self.record_into = done
            win.withdraw()
            parent.withdraw()
            self.toggle_record()

        def apply():
            if not events:
                messagebox.showinfo("Macro Recorder", "That would leave the step empty. Remove the step "
                                    "instead.", parent=win)
                return
            win.destroy()
            on_done(events)

        buttons = {}
        tools0 = tk.Frame(win, bg=BG)
        tools0.pack(fill="x", padx=14, pady=(8, 0))
        add_btn = ttk.Button(tools0, text="Add action ▾", style="Accent.TButton", command=add_menu)
        add_btn.pack(side="left")
        ttk.Button(tools0, text="Record here…", command=record_here).pack(side="left", padx=6)
        preview_btn = ttk.Button(tools0, text="Preview ▾", command=lambda: preview_menu(
            preview_btn.winfo_rootx(), preview_btn.winfo_rooty() + preview_btn.winfo_height()))
        preview_btn.pack(side="left")
        buttons["redo_btn"] = ttk.Button(tools0, text="Redo", width=7, command=lambda: jump(redo_stack, undo_stack))
        buttons["redo_btn"].pack(side="right")
        buttons["undo_btn"] = ttk.Button(tools0, text="Undo", width=7, command=lambda: jump(undo_stack, redo_stack))
        buttons["undo_btn"].pack(side="right", padx=6)
        show_undo()
        tools_many = tk.Frame(win, bg=BG)
        tools_many.pack(fill="x", padx=14, pady=(6, 0))
        for text, fn in (("Duplicate", duplicate_rows), ("Copy", copy_rows), ("Cut", cut_rows),
                         ("Paste", paste_rows), ("▲ Up", lambda: move_by(-1)), ("▼ Down", lambda: move_by(1))):
            ttk.Button(tools_many, text=text, width=len(text) + 3, command=fn).pack(side="left", padx=(0, 6))
        tools = tk.Frame(win, bg=BG)
        tools.pack(fill="x", padx=14, pady=(6, 0))
        ttk.Button(tools, text="Remove selected", command=remove_selected).pack(side="left")
        ttk.Button(tools, text="Remove all mouse moves", command=remove_moves).pack(side="left", padx=6)
        ttk.Button(tools, text="Cut the wait at the start", command=trim_start).pack(side="left")
        tools2 = tk.Frame(win, bg=BG)
        tools2.pack(fill="x", padx=14, pady=(6, 0))
        ttk.Button(tools2, text="Add a wait…", command=add_wait).pack(side="left")
        ttk.Button(tools2, text="Change the wait…", command=change_wait).pack(side="left", padx=6)
        b = ttk.Button(tools2, text="Wait for a picture…", command=add_picture_step)
        b.pack(side="left")
        if image_watch is None:
            b.config(state="disabled")
        tk.Label(win, text="Choose many with Ctrl+click, Shift+click or by dragging over rows; drag chosen rows "
                           "to move them, right-click (or Preview) to try them. Added actions and recordings go where you choose; waits and pictures go "
                           "before the selected row. Double-click a \"Wait for a picture\" step to change it.",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w", justify="left", wraplength=560).pack(
            fill="x", padx=14, pady=(6, 0))
        tk.Label(win, textvariable=note, bg=BG, fg=AMBER, font=F_SMALL, anchor="w", justify="left",
                 wraplength=560).pack(fill="x", padx=14)
        tree.bind("<Delete>", lambda e: remove_selected())
        tree.bind("<Button-3>", right_click)
        TreeDrag(tree, lambda ids, target, where: move_rows([int(i) for i in ids], int(target), where))
        for seq, fn in (("<Control-z>", lambda: jump(undo_stack, redo_stack)),
                        ("<Control-y>", lambda: jump(redo_stack, undo_stack)), ("<Control-c>", copy_rows),
                        ("<Control-x>", cut_rows), ("<Control-v>", paste_rows), ("<Control-d>", duplicate_rows),
                        ("<Alt-Up>", lambda: move_by(-1)), ("<Alt-Down>", lambda: move_by(1))):
            win.bind(seq, lambda e, fn=fn: (fn(), "break")[1])
        tree.bind("<Double-1>", edit_step)

        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=14, pady=12)
        ttk.Button(bottom, text="Apply", style="Accent.TButton", command=apply).pack(side="right")
        ttk.Button(bottom, text="Cancel", command=win.destroy).pack(side="right", padx=6)
        fill()
        win.tree, win.add_action, win.record_here, win.apply = tree, add_action, record_here, apply  # (for tests)
        win.ops = {"remove": remove_selected, "copy": copy_rows, "cut": cut_rows, "paste": paste_rows,
                   "duplicate": duplicate_rows, "move": move_rows, "move_by": move_by,
                   "undo": lambda: jump(undo_stack, redo_stack), "redo": lambda: jump(redo_stack, undo_stack),
                   "preview": preview, "rows_step": chosen_rows_step,
                   "note": note}
        return win

    def _picture_step_dialog(self, parent, on_done, step=None):
        """The options of a "Wait for a picture" step: its picture (taken from the screen or a file),
        how long to wait, whether to click it, and what to do if it doesn't show."""
        import base64

        import numpy as np

        step = dict(step or {})
        state = {"img": None, "screen_h": step.get("screen_h")}
        if step.get("png"):
            try:
                data = np.frombuffer(base64.b64decode(step["png"]), np.uint8)
                state["img"] = image_watch.cv2.imdecode(data, image_watch.cv2.IMREAD_COLOR)
            except Exception:
                state["img"] = None
        win = tk.Toplevel(parent, bg=BG)
        win.title("Wait for a picture")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.transient(parent)
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=18, pady=14)
        tk.Label(body, text="The macro stops here until this picture shows on your main screen.", bg=BG,
                 fg=MUTED, font=F_BASE, anchor="w").pack(fill="x")
        thumb = tk.Label(body, bg=FIELD, fg=DIM, font=F_SMALL, text="No picture yet", width=40, height=4)
        thumb.pack(fill="x", pady=8)

        def show_thumb():
            if state["img"] is None:
                thumb.config(image="", text="No picture yet", width=40, height=4)
                return
            photo = tk.PhotoImage(data=image_watch.png_data(state["img"], 420, 90))
            thumb.photo = photo
            thumb.config(image=photo, text="", width=0, height=0)

        def picked(img, screen_h):
            state["img"], state["screen_h"] = img, screen_h
            show_thumb()
            win.lift()

        def from_screen():
            for w in (win, parent):
                w.withdraw()
            self.root.withdraw()
            self.root.after(300, lambda: self._show_picker(on_pick=picked, hidden=(parent, win)))

        def from_file():
            path = filedialog.askopenfilename(parent=win, filetypes=[("Pictures", "*.png *.jpg *.jpeg *.bmp"),
                                                                     ("All files", "*.*")])
            if path:
                try:
                    picked(image_watch.load_image(path), None)
                except Exception as exc:
                    messagebox.showerror("Macro Recorder", f"Couldn't use that picture:\n{exc}", parent=win)

        row = tk.Frame(body, bg=BG)
        row.pack(fill="x")
        ttk.Button(row, text="Take from the screen…", command=from_screen).pack(side="left")
        ttk.Button(row, text="Picture file…", command=from_file).pack(side="left", padx=6)

        def line(text):
            r = tk.Frame(body, bg=BG)
            r.pack(fill="x", pady=(8, 0))
            tk.Label(r, text=text, bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
            return r
        r = line("Name")
        name_var = tk.StringVar(value=step.get("name", ""))
        tk.Entry(r, textvariable=name_var, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat", insertbackground=TEXT,
                 width=26).pack(side="right", ipady=2)
        r = line("Wait up to (seconds, 0 = no limit)")
        timeout_var = tk.StringVar(value=f"{step.get('timeout', 30):g}")
        ttk.Spinbox(r, from_=0, to=3600, width=6, textvariable=timeout_var).pack(side="right")
        r = line("Match (%)")
        match_var = tk.IntVar(value=int(step.get("match", 85)))
        ttk.Spinbox(r, from_=50, to=99, width=6, textvariable=match_var).pack(side="right")
        click_var = tk.BooleanVar(value=bool(step.get("click", False)))
        r = line("Click on it when it shows")
        Switch(r, click_var).pack(side="right")
        r = line("If it doesn't show in time")
        otherwise = {"go on": "Go on with the macro", "stop": "Stop the macro"}
        other_var = tk.StringVar(value=otherwise.get(step.get("otherwise", "go on"), otherwise["go on"]))
        ttk.Combobox(r, width=22, state="readonly", textvariable=other_var,
                     values=list(otherwise.values())).pack(side="right")

        def ok():
            if state["img"] is None:
                messagebox.showinfo("Macro Recorder", "Take a picture from the screen or choose a file first.",
                                    parent=win)
                return
            try:
                timeout = max(0.0, min(3600.0, float(timeout_var.get().replace(",", "."))))
                match = max(50, min(99, int(match_var.get())))
            except (ValueError, tk.TclError):
                messagebox.showinfo("Macro Recorder", "Type a number of seconds and a match from 50 to 99.",
                                    parent=win)
                return
            win.destroy()
            on_done({"type": "wait_picture", "png": image_watch.png_data(state["img"]),
                     "screen_h": state["screen_h"], "timeout": timeout, "match": match,
                     "click": bool(click_var.get()), "name": name_var.get().strip(),
                     "otherwise": next(k for k, v in otherwise.items() if v == other_var.get())})

        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(0, 14))
        ttk.Button(bottom, text="OK", style="Accent.TButton", width=8, command=ok).pack(side="right")
        ttk.Button(bottom, text="Cancel", width=8, command=win.destroy).pack(side="right", padx=6)
        show_thumb()
        dark_title_bar(win)
        win.focus_force()
