"""The Edit window: the list of a macro's actions, waits and "Wait for a picture" steps.

Part of the dark window: ModernMacroRecorder (modern_ui.py) inherits this class.
"""

from ui_common import *  # noqa: F401,F403  (colours, fonts, widgets, tk, core, the other modules)


class EditWindowMixin:
    def open_editor(self):
        if self.recording or self.playing:
            return
        if not self.events:
            messagebox.showinfo("Macro Recorder", "There's nothing to edit yet. Record or open a macro first.")
            return
        if self.edit_win is not None and self.edit_win.winfo_exists():
            self.edit_win.lift()
            return
        events = [dict(ev) for ev in self.events]
        win = tk.Toplevel(self.root, bg=BG)
        self.edit_win = win
        win.title(f"Edit - {self.name_var.get().strip() or 'new macro'}")
        win.attributes("-topmost", True)
        win.geometry("600x580")
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

        def fill():
            tree.delete(*tree.get_children())
            for i, ev in enumerate(events):
                action, detail = describe(ev)
                tags = ("move",) if ev.get("type") in ("move", "move_rel") else (
                    ("step",) if ev.get("type") == "wait_picture" else ())
                tree.insert("", "end", iid=str(i), values=(f"{ev['t']:.2f} s", action, detail), tags=tags)
            length = events[-1]["t"] if events else 0
            summary.set(f"{len(events)} actions, {length:.1f} s. Select rows (Ctrl/Shift for more) to remove them.")

        def remove_selected():
            picked = {int(i) for i in tree.selection()}
            if not picked:
                return
            events[:] = [ev for i, ev in enumerate(events) if i not in picked]
            fill()

        def remove_moves():
            n = sum(1 for ev in events if ev.get("type") == "move")
            if not n:
                messagebox.showinfo("Macro Recorder", "There are no mouse moves to remove.", parent=win)
                return
            if messagebox.askyesno("Macro Recorder", f"Remove all {n} mouse moves? Clicks keep their position, "
                                   "and camera turns are kept.", parent=win):
                events[:] = [ev for ev in events if ev.get("type") != "move"]
                fill()

        def trim_start():
            if not events or events[0]["t"] <= 0:
                return
            gap = events[0]["t"]
            for ev in events:
                ev["t"] = round(ev["t"] - gap, 4)
            fill()

        def selected_index():
            picked = sorted(int(i) for i in tree.selection())
            return picked[0] if picked else None

        def show_row(i):
            fill()
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
            for ev in events[i:]:
                ev["t"] = round(max(0.0, ev["t"] + shift), 4)
            show_row(i)

        def add_picture_step():
            i = selected_index()
            if i is None:
                i = len(events)
            self._picture_step_dialog(win, lambda step: insert_step(i, step))

        def insert_step(i, step):
            step["t"] = events[i]["t"] if i < len(events) else (events[-1]["t"] if events else 0.0)
            events.insert(i, step)
            show_row(i)

        def edit_step(_e=None):
            i = selected_index()
            if i is None or events[i].get("type") != "wait_picture":
                return
            def replace(step):
                step["t"] = events[i]["t"]
                events[i] = step
                show_row(i)
            self._picture_step_dialog(win, replace, events[i])

        def apply():
            if not events:
                messagebox.showinfo("Macro Recorder", "That would leave the macro empty. Use Clear in "
                                    "Settings > Recording for that.", parent=win)
                return
            self.events = events
            self.unsaved = True
            self.sub_note = "Macro edited (Save… to keep the changes in the file)"
            win.destroy()
            self._refresh()

        tools = tk.Frame(win, bg=BG)
        tools.pack(fill="x", padx=14, pady=(8, 0))
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
        tk.Label(win, text="New steps go before the selected row. Double-click a \"Wait for a picture\" "
                           "step to change it.", bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(
            fill="x", padx=14, pady=(6, 0))
        tree.bind("<Delete>", lambda e: remove_selected())
        tree.bind("<Double-1>", edit_step)

        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=14, pady=12)
        ttk.Button(bottom, text="Apply", style="Accent.TButton", command=apply).pack(side="right")
        ttk.Button(bottom, text="Cancel", command=win.destroy).pack(side="right", padx=6)
        fill()

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
