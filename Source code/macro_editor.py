"""The Edit window: your saved macros on the left, the steps of the chosen one in the middle, and
the chosen step's details on the right.

  - Add action: waits, key presses, typing, clicks, mouse moves, scrolling, Wait for a picture,
    If / Repeat / Retry groups, Start over, Stop, notes
  - Duplicate, Remove and More (move up / down, copy / paste, move into / out of a group, group into
    an If / Repeat / Retry, ungroup, turn a step off) for the chosen step or macro, with shortcuts
  - the macro's name (its file name) can be changed
  - Undo, Redo, Reset and Apply light up once something was changed; Apply writes the macro's file
    (and updates the open macro)

The recorded keys and mouse stay one step; "Edit the recorded events…" opens the list of every
recorded event (remove some, add or change waits, Wait for a picture inside it)."""

import copy
import json
import os

from ui_common import *  # noqa: F401,F403

OWN_EXTS = (".macro", ".json")


def key_from_id(key_id):
    """A hotkey-style id ('vk:65', 'f9', 'char:a') -> key data as recorded ({"vk": 65}...)."""
    if key_id.startswith("vk:"):
        return {"vk": int(key_id[3:])}
    if key_id.startswith("char:"):
        return {"char": key_id[5:]}
    return {"special": key_id}


def read_macro(path):
    """(steps, the file's other data) for a macro file; other recorders' files are converted."""
    if os.path.splitext(path)[1].lower() in OWN_EXTS:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("format") != "luvmacro":
            steps = data.get("actions")
            if isinstance(steps, list) and steps and all(isinstance(a, dict) for a in steps):
                return workflow.ensure_ids(core.expand_steps(steps)), data
            events = data.get("events")
            if not isinstance(events, list):
                raise ValueError("this isn't a macro file")
            return workflow.from_events(core.expand_moves(events)), data
    imported = importers.import_file(path)
    events = sorted(imported.events, key=lambda ev: ev["t"])
    data = {"imported_from": imported.source}
    if imported.screen:
        data["screen"] = {"width": imported.screen[0], "height": imported.screen[1]}
    if imported.program:
        data["program"] = imported.program
    return workflow.from_events(events), data


class MacroEditor:
    def __init__(self, app):
        self.app = app
        self.entries = []      # [(label, path or None)]
        self.current = None    # index in self.entries
        self.steps = []
        self.base_steps = []   # as the macro was opened (or last applied): Reset goes back to it
        self.base_name = ""
        self.file_data = {}
        self.undo_stack = []   # [(steps, name)] before each change
        self.redo_stack = []
        self.focus = "steps"   # which list the bottom buttons work on: "macros" or "steps"
        self.clipboard = None
        self.typing_snapshot = False
        self._build()
        self._fill_macros()
        start = next((i for i, (_l, p) in enumerate(self.entries) if p == app.current_file), 0)
        if self.entries:
            self._open_entry(start, ask=False)
        self._show_buttons()

    # ------------------------------------------------------------ window

    def _build(self):
        app = self.app
        win = self.win = tk.Toplevel(app.root, bg=BG)
        win.title("Edit - Macro Recorder")
        win.attributes("-topmost", True)
        win.minsize(940, 540)
        geo = app.settings.get("editor_geometry")
        win.geometry(geo if isinstance(geo, str) and geo[:1].isdigit() else "1220x720")
        if getattr(app, "icon_img", None) is not None:
            win.iconphoto(False, app.icon_img)
        win.protocol("WM_DELETE_WINDOW", self.close)

        # top: the macro's name, Undo / Redo / Reset / Apply
        top = tk.Frame(win, bg=BG)
        top.pack(fill="x", padx=14, pady=(12, 8))
        self.name_var = tk.StringVar()
        self.name_entry = tk.Entry(top, textvariable=self.name_var, bg=FIELD, fg=TEXT, font=(FAMILY, 12, "bold"),
                                   relief="flat", insertbackground=TEXT, highlightthickness=1,
                                   highlightbackground=BORDER, highlightcolor=ACCENT)
        self.name_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.name_var.trace_add("write", lambda *a: self._show_buttons())
        self.btn_apply = ttk.Button(top, text="Apply", width=8, command=self.apply)
        self.btn_reset = ttk.Button(top, text="Reset", width=8, command=self.reset)
        self.btn_redo = ttk.Button(top, text="Redo", width=8, command=self.redo)
        self.btn_undo = ttk.Button(top, text="Undo", width=8, command=self.undo)
        for b in (self.btn_apply, self.btn_reset, self.btn_redo, self.btn_undo):
            b.pack(side="right", padx=(8, 0))
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True)
        # left: saved macros
        left = tk.Frame(body, bg=BG, width=240)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(left, text="MACROS", bg=BG, fg=MUTED, font=F_SECTION, anchor="w").pack(fill="x", padx=14,
                                                                                      pady=(12, 6))
        self.macros = ttk.Treeview(left, show="tree", selectmode="browse")
        self.macros.pack(fill="both", expand=True, padx=(14, 6))
        self.macros.bind("<<TreeviewSelect>>", lambda e: self._macro_clicked())
        self.macros.bind("<FocusIn>", lambda e: self._set_focus("macros"))
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        # middle: the steps
        mid = tk.Frame(body, bg=BG, width=420)
        mid.pack(side="left", fill="y")
        mid.pack_propagate(False)
        head = tk.Frame(mid, bg=BG)
        head.pack(fill="x", padx=12, pady=(10, 6))
        tk.Label(head, text="Actions", bg=BG, fg=TEXT, font=F_BOLD).pack(side="left")
        self.btn_add = ttk.Button(head, text="Add action", style="Accent.TButton", command=self._add_menu)
        self.btn_add.pack(side="right")
        self.search_var = tk.StringVar()
        search = tk.Entry(mid, textvariable=self.search_var, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat",
                          insertbackground=TEXT, highlightthickness=1, highlightbackground=BORDER,
                          highlightcolor=ACCENT)
        search.pack(fill="x", padx=12, ipady=4)
        self._hint(search, self.search_var, "Search actions")
        self.search_var.trace_add("write", lambda *a: self._fill_steps())
        self.tree = ttk.Treeview(mid, show="tree", selectmode="browse")
        self.tree.pack(fill="both", expand=True, padx=12, pady=(8, 0))
        self.tree.tag_configure("off", foreground=DIM)
        self.tree.tag_configure("group", foreground=AMBER)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._step_clicked())
        self.tree.bind("<FocusIn>", lambda e: self._set_focus("steps"))
        # bottom left: Duplicate / Remove / More (only while a macro or step is chosen)
        self.bottom = tk.Frame(mid, bg=BG)
        self.bottom.pack(fill="x", padx=12, pady=10)
        self.btn_dup = ttk.Button(self.bottom, text="Duplicate", command=self.duplicate)
        self.btn_remove = ttk.Button(self.bottom, text="Remove", command=self.remove)
        self.btn_more = ttk.Button(self.bottom, text="More", command=self._more_menu)
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        # right: the chosen step's details
        self.detail = tk.Frame(body, bg=BG)
        self.detail.pack(side="left", fill="both", expand=True)

        # shortcuts
        for seq, fn in (("<Alt-Up>", lambda: self.move(-1)), ("<Alt-Down>", lambda: self.move(1)),
                        ("<Control-d>", self.duplicate), ("<Control-c>", self.copy), ("<Control-v>", self.paste),
                        ("<Alt-Left>", self.out_of_group), ("<Alt-Right>", self.into_group_above),
                        ("<Control-e>", self.toggle_off), ("<Control-z>", self.undo), ("<Control-y>", self.redo),
                        ("<Control-Z>", self.redo)):
            win.bind(seq, lambda e, fn=fn: (fn(), "break")[1] if not self._typing(e) else None)
        self.tree.bind("<Delete>", lambda e: self.remove())
        self.macros.bind("<Delete>", lambda e: self.remove())
        dark_title_bar(win)

    def _typing(self, event):
        return isinstance(event.widget, (tk.Entry, tk.Text, ttk.Entry, ttk.Spinbox, ttk.Combobox))

    @staticmethod
    def _hint(entry, var, text):
        state = {"on": False}

        def show(_e=None):
            if not var.get():
                state["on"] = True
                entry.config(fg=DIM)
                var.set(text)

        def hide(_e=None):
            if state["on"]:
                state["on"] = False
                var.set("")
                entry.config(fg=TEXT)
        entry.bind("<FocusIn>", hide, add="+")
        entry.bind("<FocusOut>", show, add="+")
        entry.hint_state = state
        show()

    def _search_text(self):
        return "" if getattr(self, "search_var", None) is None or self.search_var.get() == "Search actions" \
            else self.search_var.get().strip().lower()

    def close(self):
        if self._changed():
            answer = self.app.boxes.askyesnocancel(
                "Edit", "Keep the changes to this macro?\n\nYes = apply them, No = throw them away.", parent=self.win)
            if answer is None:
                return
            if answer and not self.apply():
                return
        try:
            self.app.settings["editor_geometry"] = self.win.geometry()
            core.save_settings(self.app.settings)
        except tk.TclError:
            pass
        self.app.capture_callback = None
        self.win.destroy()

    # ------------------------------------------------------------ the macros on the left

    def _fill_macros(self):
        app = self.app
        self.entries = []
        if app.current_file is None and (app.events or app.actions):
            self.entries.append((app.name_var.get().strip() or "Open macro (not saved)", None))
        for path in app.macro_list():
            if os.path.isfile(path):
                self.entries.append((os.path.splitext(os.path.basename(path))[0], path))
        if app.current_file and os.path.isfile(app.current_file) and \
                all(p != app.current_file for _l, p in self.entries):
            self.entries.insert(0, (os.path.splitext(os.path.basename(app.current_file))[0], app.current_file))
        self.macros.delete(*self.macros.get_children())
        for i, (label, path) in enumerate(self.entries):
            mark = "  ●" if (path == app.current_file and path) or (path is None) else ""
            self.macros.insert("", "end", iid=str(i), text=label + mark)
        if self.current is not None and self.current < len(self.entries):
            self.macros.selection_set(str(self.current))

    def _macro_clicked(self):
        sel = self.macros.selection()
        if not sel:
            return
        i = int(sel[0])
        try:
            by_user = self.win.focus_get() is self.macros
        except (KeyError, tk.TclError):
            by_user = False
        if by_user:  # (not when the list is set up or a macro is opened by the app)
            self._set_focus("macros")
        if i != self.current:
            self._open_entry(i)

    def _open_entry(self, i, ask=True):
        if ask and self._changed():
            answer = self.app.boxes.askyesnocancel(
                "Edit", "This macro has changes. Apply them before opening another one?\n\n"
                "Yes = apply, No = throw them away.", parent=self.win)
            if answer is None or (answer and not self.apply()):
                if self.current is not None:
                    self.macros.selection_set(str(self.current))
                return
        label, path = self.entries[i]
        app = self.app
        try:
            if path is None or path == app.current_file:
                steps = copy.deepcopy(app.macro_steps())
                data = dict(getattr(app, "file_data", {}) or {}) if path else {}
            else:
                steps, data = read_macro(path)
        except Exception as exc:
            app.boxes.showerror("Edit", f"Couldn't open {label}:\n{exc}", parent=self.win)
            return
        self.current = i
        self.steps = workflow.ensure_ids(steps)
        self.base_steps = copy.deepcopy(self.steps)
        self.file_data = data
        self.base_name = label if path else (app.name_var.get().strip() or "")
        self.name_var.set(self.base_name)
        self.undo_stack, self.redo_stack = [], []
        self.macros.selection_set(str(i))
        self._fill_steps()
        self._show_detail(None)
        self._show_buttons()

    # ------------------------------------------------------------ the steps in the middle

    def _fill_steps(self, select=None):
        tree = self.tree
        keep = select or self._selected_id()
        tree.delete(*tree.get_children())
        query = self._search_text()

        def add(parent, steps):
            for a in steps:
                name, words = workflow.describe(a)
                text = f"{name}   ·   {words}" if words else name
                if a.get("off"):
                    text = "(off)  " + text
                tags = ("off",) if a.get("off") else (("group",) if a.get("kind") in workflow.GROUPS else ())
                if query and query not in text.lower() and a.get("kind") not in workflow.GROUPS:
                    continue
                tree.insert(parent, "end", iid=a["id"], text=text, tags=tags, open=True)
                if a.get("kind") in workflow.GROUPS:
                    add(a["id"], a.get("actions", []))
        add("", self.steps)
        if keep and tree.exists(keep):
            tree.selection_set(keep)
            tree.see(keep)

    def _selected_id(self):
        sel = self.tree.selection() if hasattr(self, "tree") else ()
        return sel[0] if sel else None

    def _selected(self):
        sid = self._selected_id()
        return workflow.find(self.steps, sid) if sid else None

    def _step_clicked(self):
        self.focus = "steps"
        self._show_buttons()
        found = self._selected()
        self.typing_snapshot = False
        self._show_detail(found[0] if found else None)

    def _set_focus(self, which):
        self.focus = which
        self._show_buttons()

    # ------------------------------------------------------------ changes, Undo / Redo / Reset / Apply

    def _changed(self):
        return self.steps != self.base_steps or self.name_var.get().strip() != self.base_name

    def change(self, fn, select=None, keep_detail=False):
        """Make a change (fn changes self.steps) so it can be undone."""
        self.undo_stack.append((copy.deepcopy(self.steps), self.name_var.get()))
        del self.undo_stack[:-200]
        self.redo_stack = []
        fn()
        self._fill_steps(select)
        if not keep_detail:
            found = self._selected()
            self._show_detail(found[0] if found else None)
        self._show_buttons()

    def _snapshot_for_typing(self):
        """The first keystroke in a box after choosing a step makes one Undo point (not every key)."""
        if not self.typing_snapshot:
            self.typing_snapshot = True
            self.undo_stack.append((copy.deepcopy(self.steps), self.name_var.get()))
            self.redo_stack = []

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append((copy.deepcopy(self.steps), self.name_var.get()))
        self.steps, name = self.undo_stack.pop()
        self.name_var.set(name)
        self._after_jump()

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append((copy.deepcopy(self.steps), self.name_var.get()))
        self.steps, name = self.redo_stack.pop()
        self.name_var.set(name)
        self._after_jump()

    def reset(self):
        if not self._changed():
            return
        self.undo_stack.append((copy.deepcopy(self.steps), self.name_var.get()))
        self.redo_stack = []
        self.steps = copy.deepcopy(self.base_steps)
        self.name_var.set(self.base_name)
        self._after_jump()

    def _after_jump(self):
        self.typing_snapshot = False
        self._fill_steps()
        found = self._selected()
        self._show_detail(found[0] if found else None)
        self._show_buttons()

    def _show_buttons(self):
        if not hasattr(self, "btn_apply"):
            return
        changed = self._changed() if hasattr(self, "base_steps") else False
        self.btn_undo.config(state="normal" if self.undo_stack else "disabled")
        self.btn_redo.config(state="normal" if self.redo_stack else "disabled")
        self.btn_reset.config(state="normal" if changed else "disabled")
        self.btn_apply.config(state="normal" if changed else "disabled",
                              style="Accent.TButton" if changed else "TButton")
        chosen = (self.focus == "macros" and self.current is not None) or \
                 (self.focus == "steps" and self._selected_id() is not None)
        for b in (self.btn_dup, self.btn_remove, self.btn_more):
            if chosen and not b.winfo_ismapped():
                b.pack(side="left", padx=(0, 6))
            elif not chosen:
                b.pack_forget()

    def apply(self):
        """Write the changes: to the macro's file (renamed if the name changed), and to the open
        macro if it's this one. Returns True when done."""
        if self.current is None:
            return False
        app = self.app
        label, path = self.entries[self.current]
        steps = workflow.ensure_ids(copy.deepcopy(self.steps))
        if not steps:
            app.boxes.showinfo("Edit", "A macro needs at least one step.", parent=self.win)
            return False
        name = "".join(c for c in self.name_var.get().strip() if c not in '\\\\/:*?"<>|') or "macro"
        is_open = path is None or path == app.current_file
        if path is not None:
            folder = os.path.dirname(path)
            new_path = path
            own = os.path.splitext(path)[1].lower() in OWN_EXTS
            if name != os.path.splitext(os.path.basename(path))[0] or not own:
                new_path = os.path.join(folder, name + core.FILE_EXT)
                if os.path.exists(new_path) and os.path.normcase(new_path) != os.path.normcase(path):
                    app.boxes.showerror("Edit", f"There's already a macro called {name} in that folder.",
                                        parent=self.win)
                    return False
            data = {k: v for k, v in (self.file_data or {}).items() if k not in ("events", "actions", "format",
                                                                               "imported_from", "workflow")}
            data.update({"app": "macro_recorder", "version": core.FILE_VERSION, "name": name})
            data["events"] = workflow.all_events(steps)
            if not workflow.is_simple(steps):
                data["actions"] = steps
            try:
                with open(new_path, "w", encoding="utf-8") as f:
                    core.dump_macro(data, f)
                if os.path.normcase(new_path) != os.path.normcase(path) and own:
                    os.remove(path)  # renamed: the old name goes (it was this same macro)
            except OSError as exc:
                app.boxes.showerror("Edit", f"Couldn't save the macro:\n{exc}", parent=self.win)
                return False
            lib = app.macro_list()
            i = app._list_index(path)
            if i is not None and own:
                lib[i] = os.path.abspath(new_path)
            elif app._list_index(new_path) is None:
                lib.append(os.path.abspath(new_path))
            core.save_settings(app.settings)
            if is_open:
                app.current_file = new_path
            self.entries[self.current] = (name, new_path)
            self.file_data = data
        if is_open:
            app.set_steps(copy.deepcopy(steps))
            app.name_var.set(name)
            app.unsaved = path is None
            app.sub_note = "Macro edited" + (" (Save… to keep it in a file)" if path is None else " and saved")
            app._refresh()
        self.base_steps = copy.deepcopy(steps)
        self.steps = copy.deepcopy(steps)
        self.base_name = name
        self.name_var.set(name)
        self._fill_macros()
        self._fill_steps()
        self._show_buttons()
        return True

    # ------------------------------------------------------------ Add action, Duplicate, Remove, More

    def _menu(self):
        return tk.Menu(self.win, tearoff=False, bg=CARD, fg=TEXT, activebackground=ACCENT, activeforeground="white",
                       disabledforeground=DIM, font=F_BASE, bd=0, relief="flat")

    def _add_menu(self):
        """A drop-down of the actions, in sections: each one's name in bold, its description lined up
        beside it. A click adds it; Esc or a click elsewhere closes it."""
        if self.current is None:
            return
        old = getattr(self, "add_popup", None)
        if old is not None and old.winfo_exists():
            old.destroy()
            return
        words = {k: w for k, _n, w in workflow.ADDABLE}
        names = {k: n for k, n, _w in workflow.ADDABLE}
        sections = [("KEYS AND MOUSE", ("key", "type", "click", "move", "scroll")),
                    ("WAITING", ("wait", "wait_picture")),
                    ("GROUPS", ("if", "repeat", "retry")),
                    ("MACRO", ("restart", "stop", "note")),
                    ("RECORD OR COPY IN", ("record_here", "insert_macro"))]
        pop = self.add_popup = tk.Toplevel(self.win, bg=BORDER)
        pop.overrideredirect(True)
        pop.attributes("-topmost", True)
        inner = tk.Frame(pop, bg=CARD)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        def close(_e=None):
            if pop.winfo_exists():
                pop.destroy()

        def choose(kind):
            close()
            self.add(kind)
        name_font = (FAMILY, 10, "bold")
        name_width = max(len(n) for n in names.values()) + 2
        for title, kinds in sections:
            tk.Label(inner, text=title, bg=CARD, fg=MUTED, font=F_SECTION, anchor="w").pack(
                fill="x", padx=12, pady=(8, 2))
            for kind in kinds:
                row = tk.Frame(inner, bg=CARD, cursor="hand2")
                row.pack(fill="x")
                name = tk.Label(row, text=names[kind], bg=CARD, fg=TEXT, font=name_font, anchor="w",
                                width=name_width, padx=12, pady=4)
                name.pack(side="left")
                desc = tk.Label(row, text=words[kind], bg=CARD, fg=MUTED, font=F_SMALL, anchor="w", padx=8)
                desc.pack(side="left", fill="x", expand=True)
                parts = (row, name, desc)

                def hover(on, parts=parts):
                    for w in parts:
                        w.config(bg=ACCENT if on else CARD)
                    parts[2].config(fg="white" if on else MUTED)
                for w in parts:
                    w.bind("<Enter>", lambda e, h=hover: h(True))
                    w.bind("<Leave>", lambda e, h=hover: h(False))
                    w.bind("<Button-1>", lambda e, k=kind: choose(k))
        tk.Frame(inner, bg=CARD, height=6).pack(fill="x")
        pop.update_idletasks()
        b = self.btn_add
        x = b.winfo_rootx() + b.winfo_width() - pop.winfo_reqwidth()
        pop.geometry(f"+{max(0, x)}+{b.winfo_rooty() + b.winfo_height() + 4}")
        pop.bind("<Escape>", close)
        pop.bind("<FocusOut>", lambda e: pop.after(150, close))
        pop.focus_force()

    def _place(self):
        """Where a new step goes: after the chosen one (inside it, if it's a group), else at the end."""
        found = self._selected()
        if not found:
            return self.steps, len(self.steps)
        a, lst, i, _parent = found
        if a.get("kind") in workflow.GROUPS:
            return a.setdefault("actions", []), len(a["actions"])
        return lst, i + 1

    def add(self, kind):
        if kind == "record_here":
            return self.record_here()
        if kind == "insert_macro":
            return self.insert_macro()
        a = workflow.new_action(kind)
        if kind in ("click", "move"):
            x, y = self.app.mouse_ctrl.position
            a["x"], a["y"] = int(x), int(y)

        def do():
            lst, i = self._place()
            lst.insert(i, a)
        self.change(do, select=a["id"])

    def _ask_where(self, title, text):
        """At the start / after the chosen action / at the end (None = cancelled)."""
        choices = [("At the start", "start")]
        if self._selected_id():
            choices.append(("After the chosen action", "after"))
        choices += [("At the end", "end"), ("Cancel", None)]
        return self.app.boxes.askchoice(title, text, choices, default=choices[0][1], parent=self.win)

    def _insert_steps(self, new_steps, where, after_id=None):
        """Put steps in this macro (as one change, so Undo takes them out again)."""
        new_steps = [self._fresh_ids(copy.deepcopy(a)) for a in new_steps]
        if not new_steps:
            return

        def do():
            if where == "start":
                self.steps[0:0] = new_steps
            elif where == "after" and after_id and workflow.find(self.steps, after_id):
                _a, lst, i, _p = workflow.find(self.steps, after_id)
                lst[i + 1:i + 1] = new_steps
            else:
                self.steps.extend(new_steps)
        self.change(do, select=new_steps[0]["id"])

    def insert_macro(self):
        """Copy another macro's actions into this one (at the start, after the chosen action or at the
        end). They're a copy: change them here as you like; the other macro stays as it is."""
        if self.current is None:
            return
        app = self.app
        here = self.entries[self.current][1]
        others = [(label, path) for label, path in self.entries if path and path != here]
        win = tk.Toplevel(self.win, bg=BG)
        win.title("Insert another macro")
        win.transient(self.win)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=18, pady=14)
        tk.Label(body, text="Which macro's actions should be copied in?", bg=BG, fg=TEXT, font=F_BOLD,
                 anchor="w").pack(fill="x")
        tk.Label(body, text="They're copied: change them here as you like, the other macro isn't changed.",
                 bg=BG, fg=MUTED, font=F_SMALL, anchor="w").pack(fill="x", pady=(2, 8))
        lst = ttk.Treeview(body, show="tree", selectmode="browse", height=min(10, max(3, len(others))))
        lst.pack(fill="x")
        for i, (label, _p) in enumerate(others):
            lst.insert("", "end", iid=str(i), text=label)
        if others:
            lst.selection_set("0")
        picked = {"path": None}

        def from_file():
            path = filedialog.askopenfilename(parent=win, filetypes=core.OPEN_FILE_TYPES)
            if path:
                picked["path"] = path
                go()

        def go():
            path = picked["path"]
            if path is None:
                sel = lst.selection()
                if not sel:
                    return
                path = others[int(sel[0])][1]
            try:
                steps, _data = read_macro(path)
            except Exception as exc:
                app.boxes.showerror("Edit", f"Couldn't open that macro:\n{exc}", parent=win)
                return
            win.destroy()
            where = self._ask_where("Insert another macro", "Where should its actions go in this macro?")
            if where is None:
                return
            found = self._selected()
            self._insert_steps(steps, where, found[0]["id"] if found else None)
        lst.bind("<Double-1>", lambda e: go())
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(0, 14))
        ttk.Button(bottom, text="A macro file…", command=from_file).pack(side="left")
        ttk.Button(bottom, text="Insert", style="Accent.TButton", width=8, command=go).pack(side="right")
        ttk.Button(bottom, text="Cancel", width=8, command=win.destroy).pack(side="right", padx=6)
        dark_title_bar(win)
        win.focus_force()

    def record_here(self):
        """Record keys and mouse now (with the Record key, as usual) and put the recording in this
        macro: at the start, after the chosen action, or at the end."""
        app = self.app
        if app.recording or app.playing or self.current is None:
            return
        choices = [("At the start", "start")]
        if self._selected_id():
            choices.append(("After the chosen action", "after"))
        choices += [("At the end", "end"), ("Cancel", None)]
        where = app.boxes.askchoice(
            "Record keys and mouse", "Where should the new recording go in this macro?\n\nAfter you choose, "
            f"recording starts at once. Press the Record key ({core.hotkey_name(app.hotkeys['record'])}) "
            "again to stop it; this window then comes back.", choices, default=choices[0][1], parent=self.win)
        if where is None:
            return
        found = self._selected() if where == "after" else None

        def done(events):
            self.win.deiconify()
            self.win.lift()
            if not events:
                return
            step = workflow.new_action("recorded")
            step["events"] = events

            def do():
                if where == "start":
                    self.steps.insert(0, step)
                elif where == "after" and found:
                    a = workflow.find(self.steps, found[0]["id"])
                    if a:
                        a[1].insert(a[2] + 1, step)
                    else:
                        self.steps.append(step)
                else:
                    self.steps.append(step)
            self.change(do, select=step["id"])
        app.record_into = done
        self.win.withdraw()
        app.toggle_record()

    def duplicate(self):
        if self.focus == "macros":
            return self._duplicate_macro()
        found = self._selected()
        if not found:
            return
        a, lst, i, _p = found
        twin = workflow.ensure_ids([self._fresh_ids(copy.deepcopy(a))])[0]
        self.change(lambda: lst.insert(i + 1, twin), select=twin["id"])

    @staticmethod
    def _fresh_ids(a):
        a["id"] = workflow.new_id()
        for sub in a.get("actions", []) if a.get("kind") in workflow.GROUPS else []:
            MacroEditor._fresh_ids(sub)
        return a

    def remove(self):
        if self.focus == "macros":
            return self._remove_macro()
        found = self._selected()
        if not found:
            return
        a, lst, i, _p = found
        nxt = lst[i + 1]["id"] if i + 1 < len(lst) else (lst[i - 1]["id"] if i > 0 else None)
        self.change(lambda: lst.pop(i), select=nxt)

    def move(self, d):
        found = self._selected()
        if not found:
            return
        a, lst, i, _p = found
        j = i + d
        if 0 <= j < len(lst):
            def do():
                lst[i], lst[j] = lst[j], lst[i]
            self.change(do, select=a["id"])

    def copy(self):
        found = self._selected()
        if found:
            self.clipboard = copy.deepcopy(found[0])

    def paste(self):
        if self.clipboard is None or self.current is None:
            return
        a = self._fresh_ids(copy.deepcopy(self.clipboard))

        def do():
            lst, i = self._place()
            lst.insert(i, a)
        self.change(do, select=a["id"])

    def out_of_group(self):
        found = self._selected()
        if not found or found[3] is None:
            return
        a, lst, i, parent = found
        outer = workflow.find(self.steps, parent["id"])
        if not outer:
            return
        _g, glist, gi, _gp = outer

        def do():
            lst.pop(i)
            glist.insert(gi + 1, a)
        self.change(do, select=a["id"])

    def into_group_above(self):
        found = self._selected()
        if not found:
            return
        a, lst, i, _p = found
        if i == 0 or lst[i - 1].get("kind") not in workflow.GROUPS:
            return
        group = lst[i - 1]

        def do():
            lst.pop(i)
            group.setdefault("actions", []).append(a)
        self.change(do, select=a["id"])

    def group_into(self, kind):
        found = self._selected()
        if not found:
            return
        a, lst, i, _p = found
        g = workflow.new_action(kind)
        g["actions"] = [a]

        def do():
            lst[i] = g
        self.change(do, select=g["id"])

    def ungroup(self):
        found = self._selected()
        if not found or found[0].get("kind") not in workflow.GROUPS:
            return
        g, lst, i, _p = found
        inner = g.get("actions", [])

        def do():
            lst[i:i + 1] = inner
        self.change(do, select=inner[0]["id"] if inner else None)

    def toggle_off(self):
        found = self._selected()
        if not found:
            return
        a = found[0]

        def do():
            if a.get("off"):
                a.pop("off", None)
            else:
                a["off"] = True
        self.change(do, select=a["id"])

    def _more_menu(self):
        m = self._menu()
        if self.focus == "macros":
            m.add_command(label="Open it in the main window", command=self._open_in_app)
            m.add_command(label="Show the file in its folder", command=self._show_file)
        else:
            found = self._selected()
            a = found[0] if found else {}
            in_group = bool(found and found[3] is not None)
            above_group = bool(found and found[2] > 0 and found[1][found[2] - 1].get("kind") in workflow.GROUPS)
            is_group = a.get("kind") in workflow.GROUPS
            for label, accel, fn, ok in (
                    ("Move up", "Alt+Up", lambda: self.move(-1), True),
                    ("Move down", "Alt+Down", lambda: self.move(1), True),
                    ("Duplicate", "Ctrl+D", self.duplicate, True),
                    ("Remove", "Delete", self.remove, True),
                    None,
                    ("Copy", "Ctrl+C", self.copy, True),
                    ("Paste", "Ctrl+V", self.paste, self.clipboard is not None),
                    None,
                    ("Move out of its group", "Alt+Left", self.out_of_group, in_group),
                    ("Move into the group above", "Alt+Right", self.into_group_above, above_group),
                    None,
                    ("Group into an If", "", lambda: self.group_into("if"), True),
                    ("Group into a Repeat", "", lambda: self.group_into("repeat"), True),
                    ("Group into a Retry", "", lambda: self.group_into("retry"), True),
                    ("Ungroup", "", self.ungroup, is_group),
                    None,
                    ("Turn this action on" if a.get("off") else "Turn this action off", "Ctrl+E", self.toggle_off,
                     True)):
                if label is None:
                    m.add_separator()
                    continue
                label, accel, fn, ok = label, accel, fn, ok
                m.add_command(label=label, accelerator=accel, command=fn, state="normal" if ok else "disabled")
        b = self.btn_more
        m.tk_popup(b.winfo_rootx(), b.winfo_rooty() - 10 - 22 * m.index("end"))

    # ------------------------------------------------------------ the macros: duplicate, remove

    def _duplicate_macro(self):
        if self.current is None:
            return
        label, path = self.entries[self.current]
        if path is None:
            self.app.boxes.showinfo("Edit", "Save this macro first (Save… in the main window).", parent=self.win)
            return
        base = os.path.join(os.path.dirname(path), label + " copy")
        new = base + core.FILE_EXT
        n = 2
        while os.path.exists(new):
            new = f"{base} {n}{core.FILE_EXT}"
            n += 1
        try:
            steps, data = read_macro(path)
            data = {k: v for k, v in data.items() if k not in ("format", "imported_from", "workflow")}
            data.update({"app": "macro_recorder", "version": core.FILE_VERSION,
                         "name": os.path.splitext(os.path.basename(new))[0], "events": workflow.all_events(steps)})
            if not workflow.is_simple(steps):
                data["actions"] = steps
            with open(new, "w", encoding="utf-8") as f:
                core.dump_macro(data, f)
        except Exception as exc:
            self.app.boxes.showerror("Edit", f"Couldn't copy the macro:\n{exc}", parent=self.win)
            return
        self.app._remember_macro(new)
        self._fill_macros()
        i = next(k for k, (_l, p) in enumerate(self.entries) if p and os.path.normcase(p) == os.path.normcase(
            os.path.abspath(new)))
        self._open_entry(i)

    def _remove_macro(self):
        if self.current is None:
            return
        label, path = self.entries[self.current]
        if path is None:
            return
        if not self.app.boxes.askyesno("Edit", f"Take {label} off the saved macros list?\n\nThe file itself is "
                                       "kept.", parent=self.win):
            return
        lib = self.app.macro_list()
        i = self.app._list_index(path)
        if i is not None:
            del lib[i]
            core.save_settings(self.app.settings)
        self.current = None
        self._fill_macros()
        self.steps, self.base_steps = [], []
        self.name_var.set("")
        self.base_name = ""
        self._fill_steps()
        self._show_detail(None)
        if self.entries:
            self._open_entry(0, ask=False)
        self._show_buttons()

    def _open_in_app(self):
        if self.current is None:
            return
        _label, path = self.entries[self.current]
        if path and path != self.app.current_file:
            if self._changed() and not self.apply():
                return
            self.app.load(path, quiet=True)
            self._fill_macros()

    def _show_file(self):
        if self.current is not None and self.entries[self.current][1]:
            self.app._show_in_folder(self.entries[self.current][1])

    # ------------------------------------------------------------ the details on the right

    def _show_detail(self, a):
        for child in self.detail.winfo_children():
            child.destroy()
        box = tk.Frame(self.detail, bg=BG)
        box.pack(fill="both", expand=True, padx=22, pady=16)
        if a is None:
            text = ("Choose an action in the list to see and change it, or Add action to add one."
                    if self.current is not None else "Choose a macro on the left.")
            tk.Label(box, text=text, bg=BG, fg=MUTED, font=F_BASE, anchor="w", justify="left",
                     wraplength=420).pack(fill="x")
            return
        name, words = workflow.describe(a)
        tk.Label(box, text=name, bg=BG, fg=TEXT, font=(FAMILY, 14, "bold"), anchor="w").pack(fill="x")
        self.summary = tk.Label(box, text=words, bg=BG, fg=MUTED, font=F_BASE, anchor="w", justify="left",
                                wraplength=460)
        self.summary.pack(fill="x", pady=(2, 10))
        tk.Frame(box, bg=BORDER, height=1).pack(fill="x", pady=(0, 10))
        build = getattr(self, "_detail_" + a.get("kind", ""), None)
        if build:
            build(box, a)
        tk.Frame(box, bg=BORDER, height=1).pack(fill="x", pady=(14, 8))
        off = tk.BooleanVar(value=bool(a.get("off")))
        row = self._row(box, "Turn this action off", "kept, but skipped when playing")
        Switch(row, off, command=self.toggle_off).pack(side="right")

    def _row(self, parent, text, tip=None):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=text, bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
        if tip:
            tk.Label(row, text=tip, bg=BG, fg=DIM, font=F_SMALL).pack(side="left", padx=(8, 0))
        return row

    def _field(self, parent, label, a, key, kind=float, low=None, high=None, width=10, tip=None):
        """A box for one value of the step; changes are kept as you type (one Undo point)."""
        row = self._row(parent, label, tip)
        var = tk.StringVar(value=f"{a.get(key, '')}" if kind is not float else f"{float(a.get(key, 0)):g}")
        e = tk.Entry(row, textvariable=var, width=width, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat",
                     insertbackground=TEXT, highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT)
        e.pack(side="right", ipady=3)

        def changed(*_a):
            text = var.get().strip().replace(",", ".")
            try:
                value = kind(float(text)) if kind in (int, float) else text
            except ValueError:
                return
            if kind in (int, float):
                if low is not None:
                    value = max(low, value)
                if high is not None:
                    value = min(high, value)
            if a.get(key) == value:
                return
            self._snapshot_for_typing()
            a[key] = value
            self._refresh_row(a)
        var.trace_add("write", changed)
        return e

    def _choice(self, parent, label, a, key, options):
        """A drop-down for one value: options = {stored value: shown text}."""
        row = self._row(parent, label)
        var = tk.StringVar(value=options.get(a.get(key), next(iter(options.values()))))
        box = ttk.Combobox(row, textvariable=var, state="readonly", values=list(options.values()), width=22)
        box.pack(side="right")

        def picked(_e=None):
            box.selection_clear()
            value = next(k for k, v in options.items() if v == var.get())
            if a.get(key) != value:
                self.change(lambda: a.__setitem__(key, value), select=a["id"], keep_detail=True)
                self._refresh_row(a)
        box.bind("<<ComboboxSelected>>", picked)

    def _refresh_row(self, a):
        """The step's line in the list and the summary after a value changed (no new Undo point)."""
        name, words = workflow.describe(a)
        if self.tree.exists(a["id"]):
            text = f"{name}   ·   {words}" if words else name
            self.tree.item(a["id"], text=("(off)  " if a.get("off") else "") + text)
        if getattr(self, "summary", None) is not None and self.summary.winfo_exists():
            self.summary.config(text=words)
        self._show_buttons()

    def _detail_recorded(self, box, a):
        evs = a.get("events", [])
        tk.Label(box, text="Recorded events", bg=BG, fg=MUTED, font=F_SECTION, anchor="w").pack(fill="x")
        secs = evs[-1].get("t", 0) if evs else 0
        tk.Label(box, text=f"{len(evs):,} recorded events, lasting about {secs:.1f} seconds. They play back with "
                           "their original timing.", bg=BG, fg=TEXT, font=F_BASE, anchor="w", justify="left",
                 wraplength=460).pack(fill="x", pady=(2, 8))
        row = tk.Frame(box, bg=BG)
        row.pack(fill="x")

        def edit_events():
            def done(new_events):
                self.change(lambda: a.__setitem__("events", new_events), select=a["id"])
            self.app._events_window(self.win, [dict(ev) for ev in evs], done)
        ttk.Button(row, text="Edit the recorded events…", command=edit_events).pack(side="left")

    def _detail_wait(self, box, a):
        self._field(box, "Wait (seconds)", a, "seconds", float, 0, 36000)

    def _detail_note(self, box, a):
        self._field(box, "Note", a, "text", str, width=34)

    def _detail_key(self, box, a):
        row = self._row(box, "Key")
        badge = tk.Label(row, text=workflow.key_text(a.get("key", {})), bg=BADGE, fg=TEXT,
                         font=(FAMILY, 10, "bold"), padx=10, pady=2)

        def capture():
            badge.config(text="Press a key…", fg=AMBER)

            def got(key_id):
                self.app.capture_callback = None
                if not self.win.winfo_exists():
                    return
                if key_id and key_id != "esc":
                    key = key_from_id(key_id)
                    self.change(lambda: a.__setitem__("key", key), select=a["id"])
                else:
                    badge.config(text=workflow.key_text(a.get("key", {})), fg=TEXT)
            self.app.capture_callback = got
        link(row, "Change", capture).pack(side="right")
        badge.pack(side="right", padx=(0, 10))
        self._choice(box, "What to do", a, "mode", {"press": "Press it", "down": "Hold it down",
                                                    "up": "Let go of it"})
        self._field(box, "How many times", a, "times", int, 1, 1000, tip="when pressing")
        self._field(box, "Hold it down for (seconds)", a, "hold", float, 0, 3600, tip="0 = a quick press")

    def _detail_type(self, box, a):
        tk.Label(box, text="Text to type", bg=BG, fg=TEXT, font=F_BASE, anchor="w").pack(fill="x")
        text = tk.Text(box, height=5, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat", font=F_BASE,
                       highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT, wrap="word")
        text.pack(fill="x", pady=(4, 6))
        text.insert("1.0", a.get("text", ""))

        def typed(_e=None):
            value = text.get("1.0", "end-1c")
            if value != a.get("text"):
                self._snapshot_for_typing()
                a["text"] = value
                self._refresh_row(a)
        text.bind("<KeyRelease>", typed)
        self._field(box, "Time between letters (seconds)", a, "delay", float, 0, 5)

    def _point_rows(self, box, a):
        self._field(box, "X (from the left of the screen)", a, "x", int)
        self._field(box, "Y (from the top)", a, "y", int)
        row = tk.Frame(box, bg=BG)
        row.pack(fill="x", pady=(4, 0))

        def pick():
            def picked(x, y):
                def do():
                    a["x"], a["y"] = x, y
                self.change(do, select=a["id"])
            self.app._pick_point(self.win, picked)
        ttk.Button(row, text="Pick the spot on the screen…", command=pick).pack(side="left")

    def _detail_click(self, box, a):
        self._point_rows(box, a)
        self._choice(box, "Button", a, "button", {"left": "Left", "right": "Right", "middle": "Middle"})
        self._choice(box, "Click", a, "mode", {"click": "Click", "double": "Double-click", "down": "Hold down",
                                               "up": "Let go"})
        self._field(box, "Hold the button for (seconds)", a, "hold", float, 0, 3600, tip="0 = a quick click")

    def _detail_move(self, box, a):
        self._point_rows(box, a)

    def _detail_scroll(self, box, a):
        self._field(box, "Notches (+ up, - down)", a, "amount", int, -100, 100)

    def _picture_thumb(self, box, holder, on_change):
        """The picture of a step or condition, with buttons to take a new one."""
        thumb = tk.Label(box, bg=FIELD, fg=DIM, text="No picture yet", font=F_SMALL, height=3)
        thumb.pack(fill="x", pady=(4, 6))
        if holder.get("png"):
            try:
                photo = tk.PhotoImage(data=holder["png"])
                step = max(1, -(-photo.width() // 420), -(-photo.height() // 80))
                photo = photo.subsample(step) if step > 1 else photo
                thumb.photo = photo
                thumb.config(image=photo, text="", height=0)
            except tk.TclError:
                pass
        row = tk.Frame(box, bg=BG)
        row.pack(fill="x")

        def got(img, screen_h):
            png = image_watch.png_data(img)

            def do():
                holder["png"], holder["screen_h"] = png, screen_h
            on_change(do)

        def from_screen():
            self.win.withdraw()
            self.app.root.withdraw()
            self.app.root.after(300, lambda: self.app._show_picker(on_pick=got, hidden=(self.win,)))

        def from_file():
            path = filedialog.askopenfilename(parent=self.win, filetypes=[("Pictures", "*.png *.jpg *.jpeg *.bmp"),
                                                                          ("All files", "*.*")])
            if path:
                try:
                    got(image_watch.load_image(path), None)
                except Exception as exc:
                    self.app.boxes.showerror("Edit", f"Couldn't use that picture:\n{exc}", parent=self.win)
        ttk.Button(row, text="Take from the screen…", command=from_screen).pack(side="left")
        ttk.Button(row, text="Picture file…", command=from_file).pack(side="left", padx=6)

    def _detail_wait_picture(self, box, a):
        self._picture_thumb(box, a, lambda fn: self.change(fn, select=a["id"]))
        self._field(box, "Name", a, "name", str, width=24)
        self._field(box, "Wait up to (seconds, 0 = no limit)", a, "timeout", float, 0, 36000)
        self._field(box, "Match (%)", a, "match", int, 50, 99)
        click = tk.BooleanVar(value=bool(a.get("click")))
        row = self._row(box, "Click on it when it shows")
        Switch(row, click, command=lambda: self.change(lambda: a.__setitem__("click", bool(click.get())),
                                                       select=a["id"])).pack(side="right")
        self._choice(box, "If it doesn't show in time", a, "otherwise", {"go on": "Go on with the macro",
                                                                        "stop": "Stop the macro"})

    def _condition(self, box, a):
        c = a.setdefault("condition", {"shows": True, "png": None, "screen_h": None, "match": 85})
        tk.Label(box, text="CONDITION", bg=BG, fg=MUTED, font=F_SECTION, anchor="w").pack(fill="x")
        self._choice(box, "When this picture", c, "shows", {True: "shows on screen", False: "doesn't show"})
        self._picture_thumb(box, c, lambda fn: self.change(fn, select=a["id"]))
        self._field(box, "Name", c, "name", str, width=24)
        self._field(box, "Match (%)", c, "match", int, 50, 99)

    def _detail_if(self, box, a):
        self._condition(box, a)
        tk.Label(box, text="The actions inside this group only run when the condition is true. Add actions "
                           "into it with Add action while it's chosen, or Alt+Right on the action below it.",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w", justify="left", wraplength=460).pack(fill="x", pady=(8, 0))

    def _detail_repeat(self, box, a):
        self._field(box, "Repeat how many times", a, "times", int, 0, 100000)

    def _detail_retry(self, box, a):
        self._condition(box, a)
        self._field(box, "At most how many tries", a, "tries", int, 1, 1000)
        tk.Label(box, text="The actions inside run, then the condition is checked (for up to 2 seconds); if "
                           "it isn't true yet, they run again.", bg=BG, fg=DIM, font=F_SMALL, anchor="w",
                 justify="left", wraplength=460).pack(fill="x", pady=(8, 0))

    def _detail_restart(self, box, a):
        tk.Label(box, text="Starts the macro again from step 1 (it stops by itself if this happens more than 10 "
                           "times in 60 seconds). Usually inside an If, as a failsafe.", bg=BG, fg=MUTED, font=F_BASE,
                 anchor="w", justify="left", wraplength=460).pack(fill="x")

    def _detail_stop(self, box, a):
        tk.Label(box, text="Ends the macro here. Usually inside an If.", bg=BG, fg=MUTED, font=F_BASE, anchor="w",
                 justify="left", wraplength=460).pack(fill="x")


class MacroEditorMixin:
    def open_editor(self):
        if self.recording or self.playing:
            return
        ed = getattr(self, "macro_editor", None)
        if ed is not None and ed.win.winfo_exists():
            ed.win.deiconify()
            ed.win.lift()
            return
        self.macro_editor = MacroEditor(self)
        self.edit_win = self.macro_editor.win

    def _pick_point(self, parent, on_pick, hidden=()):
        """Freeze the screen and let the user click a spot: on_pick(x, y) in screen pixels.
        `hidden`: more windows to hide meanwhile (and show again after)."""
        windows = [w for w in hidden if w is not None] + [parent]

        def show_again():
            self.root.deiconify()
            for w in windows:
                try:
                    w.deiconify()
                except tk.TclError:
                    pass
        for w in windows:
            w.withdraw()
        self.root.withdraw()

        def show():
            try:
                shot = image_watch.grab_screen()
                with image_watch.mss.mss() as sct:
                    mon = image_watch.primary_monitor(sct)
            except Exception as exc:
                show_again()
                self.boxes.showerror("Edit", f"Couldn't take a screenshot:\n{exc}", parent=parent)
                return
            h, w = shot.shape[:2]
            win = tk.Toplevel(self.root)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.geometry(f"{w}x{h}+{mon['left']}+{mon['top']}")
            canvas = tk.Canvas(win, width=w, height=h, highlightthickness=0, cursor="crosshair")
            canvas.pack()
            photo = tk.PhotoImage(data=image_watch.png_data(shot))
            canvas.create_image(0, 0, image=photo, anchor="nw")
            canvas.photo = photo
            canvas.create_rectangle(0, 0, w, 36, fill="black", outline="")
            canvas.create_text(w // 2, 18, text="Click the spot. Esc cancels.", fill="white",
                               font=(FAMILY, 12, "bold"))

            def close():
                win.destroy()
                show_again()

            def clicked(e):
                close()
                on_pick(int(mon["left"] + e.x), int(mon["top"] + e.y))
            canvas.bind("<Button-1>", clicked)
            win.bind("<Escape>", lambda e: close())
            win.focus_force()
        self.root.after(300, show)

