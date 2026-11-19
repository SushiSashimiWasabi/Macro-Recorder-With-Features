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
import time

import macro_versions

from ui_common import *  # noqa: F401,F403
from edit_more import EditMoreMixin
import step_more

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


class MacroEditor(EditMoreMixin):
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
        entry_hint(self.name_entry, self.name_var, "Type a name for this macro")  # (gone once you type)
        self.btn_apply = ttk.Button(top, text="Apply", width=8, command=self.apply)
        self.btn_reset = ttk.Button(top, text="Reset", width=8, command=self.reset)
        self.btn_redo = ttk.Button(top, text="Redo", width=8, command=self.redo)
        self.btn_undo = ttk.Button(top, text="Undo", width=8, command=self.undo)
        for b in (self.btn_apply, self.btn_reset, self.btn_redo, self.btn_undo):
            b.pack(side="right", padx=(8, 0))
        # (Preview 4) the window the macro plays in: change it without recording again
        game = tk.Frame(win, bg=BG)
        game.pack(fill="x", padx=14, pady=(0, 8))
        tk.Label(game, text="Game window:", bg=BG, fg=MUTED, font=F_SMALL).pack(side="left")
        self.game_label = tk.Label(game, text="", bg=BG, fg=TEXT, font=F_SMALL)
        self.game_label.pack(side="left", padx=(6, 0))
        if IS_WIN:
            link(game, "Change…", self.change_game_window, bg=BG).pack(side="left", padx=(10, 0))
        self.game_forget = link(game, "Forget", self.forget_game_window, bg=BG)
        self.game_forget.pack(side="left", padx=(10, 0))
        self.program = self.base_program = None
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True)
        # left: saved macros
        left = tk.Frame(body, bg=BG, width=240)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(left, text="MACROS", bg=BG, fg=MUTED, font=F_SECTION, anchor="w").pack(fill="x", padx=14,
                                                                                      pady=(12, 6))
        # (Preview 4) a filter: name, folder or #tag
        self.macro_filter_var = tk.StringVar()
        mfilter = tk.Entry(left, textvariable=self.macro_filter_var, bg=FIELD, fg=TEXT, font=F_SMALL, relief="flat",
                           insertbackground=TEXT, highlightthickness=1, highlightbackground=BORDER,
                           highlightcolor=ACCENT)
        mfilter.pack(fill="x", padx=(14, 6), pady=(0, 6), ipady=3)
        entry_hint(mfilter, self.macro_filter_var, "Filter: name, folder or #tag", size=9)
        self.macro_filter_var.trace_add("write", lambda *a: self._fill_macros())
        self.macros = ttk.Treeview(left, show="tree", selectmode="extended")
        self.macros.pack(fill="both", expand=True, padx=(14, 6))
        self.macros.tag_configure("folder", foreground=AMBER)
        self.macros.bind("<Button-3>", self._macros_right_click)
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
        self.tree = ttk.Treeview(mid, show="tree", selectmode="extended")
        self.tree.pack(fill="both", expand=True, padx=12, pady=(8, 0))
        self.tree.tag_configure("off", foreground=DIM)
        self.tree.tag_configure("group", foreground=AMBER)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._step_clicked())
        self.tree.bind("<FocusIn>", lambda e: self._set_focus("steps"))
        # bottom left: Duplicate / Remove / More (only while a macro or step is chosen)
        self.bottom = tk.Frame(mid, bg=BG)
        self.bottom.pack(fill="x", padx=12, pady=10)
        # (Preview 4: a bit narrower, so ⇤ Out and In ⇥ fit next to them)
        self.btn_dup = ttk.Button(self.bottom, text="Duplicate", width=9, command=self.duplicate)
        self.btn_remove = ttk.Button(self.bottom, text="Remove", width=7, command=self.remove)
        self.btn_more = ttk.Button(self.bottom, text="More", width=5, command=self._more_menu)
        # (Preview 4) small buttons to move the chosen action out of / into a group
        self.btn_out = ttk.Button(self.bottom, text="⇤ Out", width=6, command=self.out_of_group)
        self.btn_in = ttk.Button(self.bottom, text="In ⇥", width=6, command=self.into_group_above)
        hover_text(self.btn_out, lambda: "Move out of its group (Alt+Left)")
        hover_text(self.btn_in, lambda: "Move into the group above it (Alt+Right)")
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
        # (2.11) Ctrl+click / Shift+click / drag to choose many; drag chosen ones to move them
        TreeDrag(self.tree, self._drop_steps, is_group=lambda iid: "group" in self.tree.item(iid, "tags"))
        TreeDrag(self.macros, self._drop_macros, is_group=lambda iid: iid.startswith("f:"))
        win.bind("<Control-x>", lambda e: (self.cut(), "break")[1] if not self._typing(e) else None)
        self.tree.bind("<Button-3>", self._right_click)
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
        self._forget_autosave()
        self.win.destroy()

    # ------------------------------------------------------------ crash-safe autosave

    @staticmethod
    def autosave_path():
        return os.path.join(os.path.dirname(core.settings_path()), "edit_autosave.json")

    def _autosave_soon(self):
        """A moment after each change, the unapplied steps are written to a file, so a crash or a
        power cut doesn't lose them (the next time Edit opens, it offers them back)."""
        if not hasattr(self, "win") or not hasattr(self, "steps"):
            return
        if getattr(self, "autosave_job", None) is not None:
            try:
                self.win.after_cancel(self.autosave_job)
            except tk.TclError:
                pass
        try:
            self.autosave_job = self.win.after(1500, self.autosave_now)
        except tk.TclError:
            self.autosave_job = None

    def autosave_now(self):
        self.autosave_job = None
        if self.current is None or not self._changed():
            self._forget_autosave(cancel=False)
            return
        try:
            data = {"path": self.entries[self.current][1], "name": self.name_var.get().strip(),
                    "saved": time.time(), "steps": self.steps}
            tmp = self.autosave_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self.autosave_path())
        except (OSError, TypeError, ValueError) as exc:
            core.diag.error("Edit: couldn't autosave", exc)

    def _forget_autosave(self, cancel=True):
        if cancel and getattr(self, "autosave_job", None) is not None:
            try:
                self.win.after_cancel(self.autosave_job)
            except tk.TclError:
                pass
            self.autosave_job = None
        try:
            os.remove(self.autosave_path())
        except OSError:
            pass

    def offer_autosave(self):
        """Changes left over from a crash: offer to bring them back. True when they were."""
        try:
            with open(self.autosave_path(), encoding="utf-8") as f:
                data = json.load(f)
            steps = data["steps"]
            if not isinstance(steps, list) or not steps:
                raise ValueError
        except (OSError, ValueError, KeyError, TypeError):
            return False
        path = data.get("path")
        index = next((i for i, (_label, p) in enumerate(self.entries) if p == path), None)
        when = time.strftime("%d %b %H:%M", time.localtime(data.get("saved") or 0))
        name = data.get("name") or "a macro"
        if index is None or not self.app.boxes.askyesno(
                "Edit", f"Changes to \"{name}\" from {when} were never applied (the app closed "
                "unexpectedly).\n\nBring them back? They'll show as unapplied changes: Apply keeps them, "
                "Reset throws them away.", parent=self.win):
            self._forget_autosave()
            return False
        self._open_entry(index, ask=False)
        self.change(lambda: setattr(self, "steps", workflow.ensure_ids(steps)))
        if data.get("name"):
            self.name_var.set(data["name"])
        self._show_buttons()
        return True

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
        # (Preview 4) folders first (open, amber), then the macros with no folder; tags after the name
        query = self.macro_filter_var.get().strip() if hasattr(self, "macro_filter_var") else ""
        meta = {i: (app.macro_meta(p) if p else {"folder": "", "tags": []}) for i, (_l, p) in enumerate(self.entries)}
        for folder in (app.macro_folders() if hasattr(app, "macro_folders") else []):
            inside = [i for i, m in meta.items() if m["folder"] == folder]
            self.macros.insert("", "end", iid="f:" + folder, text=f"{folder}  ({len(inside)})", open=True,
                               tags=("folder",))
        for i, (label, path) in enumerate(self.entries):
            if query and not (path and app.macro_matches(path, query)) and \
                    not (path is None and query.lower() in label.lower()):
                continue
            mark = "  ●" if (path == app.current_file and path) or (path is None) else ""
            tags = meta[i]["tags"]
            text = label + mark + (f"   · {', '.join(tags)}" if tags else "")
            parent = "f:" + meta[i]["folder"] if meta[i]["folder"] else ""
            if parent and not self.macros.exists(parent):
                parent = ""
            self.macros.insert(parent, "end", iid=str(i), text=text)
        if query:  # (a filter hides folders with nothing that matches)
            for f in self.macros.get_children(""):
                if f.startswith("f:") and not self.macros.get_children(f):
                    self.macros.delete(f)
        if self.current is not None and self.current < len(self.entries) and self.macros.exists(str(self.current)):
            self.macros.selection_set(str(self.current))

    def _macro_clicked(self):
        sel = self.macros.selection()
        if not sel:
            return
        if len(sel) > 1:  # (2.11: several chosen: Duplicate / Remove work on all of them)
            self._set_focus("macros")
            return
        if not sel[0].isdigit():  # (Preview 4: a folder's row)
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
                    self._select_macro_row(self.current)
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
        self.base_steps = workflow.snapshot(self.steps)
        self.file_data = data
        prog = app.macro_program if (path is None or path == app.current_file) else data.get("program")
        self.program = copy.deepcopy(prog) if isinstance(prog, dict) else None
        self.base_program = copy.deepcopy(self.program)
        self._show_game()
        self.base_name = label if path else (app.name_var.get().strip() or "")
        self.name_var.set(self.base_name)
        self.undo_stack, self.redo_stack = [], []
        self._select_macro_row(i)
        self._fill_steps()
        self._show_detail(None)
        self._show_buttons()

    # ------------------------------------------------------------ the steps in the middle

    def _fill_steps(self, select=None):
        tree = self.tree
        keep = list(self.tree.selection()) if select is None else ([select] if isinstance(select, str) else
                                                                    list(select or []))
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
        keep = [k for k in keep if tree.exists(k)]
        if keep:
            tree.selection_set(keep)
            tree.see(keep[0])

    def _selected_id(self):
        sel = self.tree.selection() if hasattr(self, "tree") else ()
        return sel[0] if sel else None

    def _selected(self):
        sid = self._selected_id()
        return workflow.find(self.steps, sid) if sid else None

    def _chosen(self):
        """(2.11) Every chosen step as (step, its list, index, group), in list order. A step inside a
        chosen group isn't listed again (it goes along with its group)."""
        ids = set(self.tree.selection()) if hasattr(self, "tree") else set()
        out, covered = [], set()
        for a, lst, i, parent in workflow.walk(self.steps):
            if parent is not None and parent.get("id") in covered:
                covered.add(a.get("id"))
                continue
            if a.get("id") in ids:
                out.append((a, lst, i, parent))
                covered.add(a.get("id"))
        return out

    def _step_clicked(self):
        self.focus = "steps"
        self._show_buttons()
        self.typing_snapshot = False
        if len(self.tree.selection()) > 1:
            self._show_many(len(self._chosen()))
            return
        found = self._selected()
        self._show_detail(found[0] if found else None)

    def _show_many(self, n):
        for child in self.detail.winfo_children():
            child.destroy()
        box = tk.Frame(self.detail, bg=BG)
        box.pack(fill="both", expand=True, padx=22, pady=16)
        tk.Label(box, text=f"{n} actions chosen", bg=BG, fg=TEXT, font=(FAMILY, 14, "bold"), anchor="w").pack(fill="x")
        tk.Label(box, text="Duplicate, Remove, Copy (Ctrl+C), Cut (Ctrl+X), Paste (Ctrl+V), Move up / down "
                           "(Alt+arrows), Turn off / on (Ctrl+E) and Group into work on all of them at once; one "
                           "Undo puts them back. Drag them to move them.\n\nCtrl+click adds or takes away one, "
                           "Shift+click chooses everything in between.", bg=BG, fg=MUTED, font=F_BASE, anchor="w",
                 justify="left", wraplength=440).pack(fill="x", pady=(4, 0))

    def _set_focus(self, which):
        self.focus = which
        self._show_buttons()

    # ------------------------------------------------------------ changes, Undo / Redo / Reset / Apply

    def _changed(self):
        return self.steps != self.base_steps or self.name_var.get().strip() != self.base_name \
            or getattr(self, "program", None) != getattr(self, "base_program", None)

    # ------------------------------------------------------------ (Preview 4) the macro's game window

    def _show_game(self):
        if not hasattr(self, "game_label"):
            return
        p = self.program or {}
        exe = p.get("exe")
        if exe:
            text = f"{window_tools.friendly_name(exe)}  ({exe})"
            client = p.get("client")
            if isinstance(client, (list, tuple)) and len(client) == 4:
                text += f",  {client[2]}×{client[3]}"
            self.game_label.config(text=text, fg=TEXT)
            self.game_forget.config(text="Forget")
        else:
            self.game_label.config(text="none (it plays on the whole screen)", fg=DIM)
            self.game_forget.config(text="")

    def forget_game_window(self):
        if not self.program:
            return
        self.program = None
        self._show_game()
        self._show_buttons()

    def change_game_window(self):
        """Pick another open window for this macro (like "Record in which window?"). The size the macro
        was recorded at stays, so its clicks are still fitted from there to the new window."""
        if self.current is None:
            return
        own = os.getpid()
        wins = [(h, t, e) for h, t, e in window_tools.app_windows() if window_tools.pid_of(h) != own and e]
        win = tk.Toplevel(self.win, bg=BG)
        win.withdraw()
        win.title("Game window")
        win.transient(self.win)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=20, pady=(16, 8))
        tk.Label(body, text="Which window does this macro play in?", bg=BG, fg=TEXT, font=F_BOLD,
                 anchor="w").pack(fill="x")
        old = self.program or {}
        client = old.get("client")
        if isinstance(client, (list, tuple)) and len(client) == 4:
            warn = (f"It was recorded in a window of {client[2]}×{client[3]}. With \"Fit clicks to: The game window\" "
                    "(Settings > Playback) its clicks are fitted to the new window. With \"The whole screen\" they "
                    "stay where they were recorded, so a window of another size or place can be missed.")
        else:
            warn = ("It didn't remember a window's size, so its clicks stay where they were recorded. The new "
                    "window's size is remembered from now on.")
        tk.Label(body, text=warn, bg=BG, fg=AMBER, font=F_SMALL, anchor="w", justify="left",
                 wraplength=470).pack(fill="x", pady=(4, 8))
        if not wins:
            tk.Label(body, text="No other window is open. Open the game first.", bg=BG, fg=MUTED, font=F_BASE,
                     anchor="w").pack(fill="x")
        lst = ttk.Treeview(body, show="tree", selectmode="browse", height=max(1, min(10, len(wins))))
        lst.column("#0", width=470)
        if wins:
            lst.pack(fill="x")
        pick = None
        for k, (_h, title, exe) in enumerate(wins):
            lst.insert("", "end", iid=str(k), text=f"{short(title, 52)}   ({os.path.splitext(exe)[0]})")
            if pick is None and old.get("exe") and exe.lower() == str(old["exe"]).lower():
                pick = str(k)
        if wins:
            lst.selection_set(pick or "0")
            lst.see(pick or "0")

        def ok(_e=None):
            sel = lst.selection()
            if not sel or not wins:
                return
            hwnd, _title, exe = wins[int(sel[0])]
            new = {k: v for k, v in old.items() if k != "title"}
            new["exe"] = exe
            if not (isinstance(client, (list, tuple)) and len(client) == 4):
                rect = window_tools.client_rect(hwnd)
                if rect:
                    new["client"] = list(rect)
            win.destroy()
            self.program = new
            core.diag.info(f"Edit: the macro's game window is now {exe}")
            self._show_game()
            self._show_buttons()
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=20, pady=(4, 16))
        ttk.Button(bottom, text="Cancel", width=8, command=win.destroy).pack(side="right")
        ttk.Button(bottom, text="OK", width=8, style="Accent.TButton", command=ok,
                   state="normal" if wins else "disabled").pack(side="right", padx=(0, 8))
        lst.bind("<Double-1>", ok)
        win.bind("<Return>", ok)
        win.bind("<Escape>", lambda e: win.destroy())
        dark_title_bar(win)
        win.update_idletasks()
        x = self.win.winfo_rootx() + max(0, (self.win.winfo_width() - win.winfo_reqwidth()) // 2)
        y = self.win.winfo_rooty() + max(0, (self.win.winfo_height() - win.winfo_reqheight()) // 3)
        win.geometry(f"+{x}+{y}")
        win.deiconify()
        win.lift()
        self.game_box = win  # (for tests)
        return win

    def change(self, fn, select=None, keep_detail=False):
        """Make a change (fn changes self.steps) so it can be undone."""
        self.undo_stack.append((workflow.snapshot(self.steps), self.name_var.get()))
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
            self.undo_stack.append((workflow.snapshot(self.steps), self.name_var.get()))
            self.redo_stack = []

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append((workflow.snapshot(self.steps), self.name_var.get()))
        self.steps, name = self.undo_stack.pop()
        self.name_var.set(name)
        self._after_jump()

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append((workflow.snapshot(self.steps), self.name_var.get()))
        self.steps, name = self.redo_stack.pop()
        self.name_var.set(name)
        self._after_jump()

    def reset(self):
        if not self._changed():
            return
        self.undo_stack.append((workflow.snapshot(self.steps), self.name_var.get()))
        self.redo_stack = []
        self.steps = workflow.snapshot(self.base_steps)
        self.name_var.set(self.base_name)
        self.program = copy.deepcopy(self.base_program)
        self._show_game()
        self._after_jump()

    def _after_jump(self):
        self.typing_snapshot = False
        self._fill_steps()
        found = self._selected()
        self._show_detail(found[0] if found else None)
        self._show_buttons()

    def _show_buttons(self):
        self._autosave_soon()
        if not hasattr(self, "btn_apply"):
            return
        changed = self._changed() if hasattr(self, "base_steps") else False
        self.btn_undo.config(state="normal" if self.undo_stack else "disabled")
        self.btn_redo.config(state="normal" if self.redo_stack else "disabled")
        self.btn_reset.config(state="normal" if changed else "disabled")
        self.btn_apply.config(state="normal" if changed else "disabled",
                              style="Accent.TButton" if changed else "TButton")
        chosen = (self.focus == "macros" and (self.current is not None or self.macros.selection())) or \
                 (self.focus == "steps" and self._selected_id() is not None)
        for b in (self.btn_dup, self.btn_remove, self.btn_more):
            if chosen and not b.winfo_ismapped():
                b.pack(side="left", padx=(0, 6))
            elif not chosen:
                b.pack_forget()
        if hasattr(self, "btn_out"):  # (Preview 4) only for actions, greyed out when it can't be done
            steps = chosen and self.focus == "steps"
            in_group, above_group, _g = self._group_moves() if steps else (False, False, False)
            for b, ok in ((self.btn_out, in_group), (self.btn_in, above_group)):
                if steps and not b.winfo_ismapped():
                    b.pack(side="left", padx=(0, 6))
                elif not steps:
                    b.pack_forget()
                b.config(state="normal" if ok else "disabled")

    def apply(self):
        """Write the changes: to the macro's file (renamed if the name changed), and to the open
        macro if it's this one. Returns True when done."""
        if self.current is None:
            return False
        app = self.app
        label, path = self.entries[self.current]
        steps = workflow.ensure_ids(copy.deepcopy(self.steps))
        # (2.12) what you add here yourself (typing into a program, reading the copied number) is OK'd;
        # what the macro already did when it came to you still asks once at Play
        added = step_more.sensitive_parts(steps) - step_more.sensitive_parts(self.base_steps or [])
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
            if self.program:  # (Preview 4: the game window can be changed or forgotten here)
                data["program"] = copy.deepcopy(self.program)
            else:
                data.pop("program", None)
            if not workflow.is_simple(steps):
                data["actions"] = steps
            if own:
                macro_versions.keep(path)  # (2.10: the version it had stays in Restore an older version…)
            try:
                with open(new_path, "w", encoding="utf-8") as f:
                    core.dump_macro(data, f)
                if os.path.normcase(new_path) != os.path.normcase(path) and own:
                    os.remove(path)  # renamed: the old name goes (it was this same macro)
                    macro_versions.renamed(path, new_path)  # (its older versions and warnings go along)
                    if hasattr(app, "meta_renamed"):
                        app.meta_renamed(path, new_path)  # (Preview 4: and its folder and tags)
                    if hasattr(app, "rename_check_ignored"):
                        app.rename_check_ignored(macro_versions._key(path), macro_versions._key(new_path))
            except OSError as exc:
                app.boxes.showerror("Edit", f"Couldn't save the macro:\n{exc}", parent=self.win)
                return False
            lib = app.macro_list()
            i = app._list_index(path)
            if i is not None and own:
                lib[i] = os.path.abspath(new_path)
            elif app._list_index(new_path) is None:
                lib.append(os.path.abspath(new_path))
            if own and os.path.normcase(new_path) != os.path.normcase(path) and \
                    hasattr(app, "_pictures_macro_renamed"):
                app._pictures_macro_renamed(path, new_path)  # (pictures used only for it follow it)
            if added and hasattr(app, "trust_steps"):
                app.trust_steps(app._macro_key(new_path), added)
            old_key = app._macro_key(path)
            if hasattr(app, "_trusted") and old_key in app._trusted() and app._macro_key(new_path) != old_key:
                app.trust_steps(app._macro_key(new_path), app._trusted()[old_key])
            core.save_settings(app.settings)
            if is_open:
                app.current_file = new_path
            self.entries[self.current] = (name, new_path)
            self.file_data = data
        if path is None and added and hasattr(app, "trust_steps"):
            app.trust_steps("", added)
        if is_open:
            app.set_steps(copy.deepcopy(steps))
            if self.program != self.base_program:
                app.macro_program = copy.deepcopy(self.program)
                if isinstance(getattr(app, "file_data", None), dict):
                    app.file_data["program"] = copy.deepcopy(self.program)
            app.name_var.set(name)
            app.unsaved = path is None
            app.sub_note = "Macro edited" + (" (Save… to keep it in a file)" if path is None else " and saved")
            app._refresh()
        self.base_steps = workflow.snapshot(steps)
        self.steps = workflow.snapshot(steps)
        self.base_program = copy.deepcopy(self.program)
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
                    ("WAITING", ("wait", "wait_random", "wait_picture", "game")),
                    ("GROUPS", ("if", "else", "repeat", "retry")),
                    ("COUNTERS AND MATHS", ("counter_add", "counter_set", "if_counter", "maths", "read_clipboard")),
                    None,  # (the second column)
                    ("JUMPS", ("label", "goto")),
                    ("CHAIN (PLAY OTHER MACROS)", ("play_macro",)),
                    ("TELL ME", ("discord", "screenshot", "sound")),
                    ("MACRO", ("set_speed", "restart", "stop", "note")),
                    ("RECORD OR COPY IN", ("record_here", "insert_macro"))]
        pop = self.add_popup = tk.Toplevel(self.win, bg=BORDER)
        pop.overrideredirect(True)
        pop.attributes("-topmost", True)
        outer = tk.Frame(pop, bg=CARD)
        outer.pack(fill="both", expand=True, padx=1, pady=1)
        inner = tk.Frame(outer, bg=CARD)
        inner.pack(side="left", fill="both", expand=True, anchor="n")

        def close(_e=None):
            if pop.winfo_exists():
                pop.destroy()

        def choose(kind):
            close()
            self.add(kind)
        name_font = (FAMILY, 10, "bold")
        name_width = max(len(n) for n in names.values()) + 2
        for section in sections:
            if section is None:  # (2.12: the list got long: a second column)
                tk.Frame(inner, bg=CARD, height=6).pack(fill="x")
                tk.Frame(outer, bg=BORDER, width=1).pack(side="left", fill="y", pady=8)
                inner = tk.Frame(outer, bg=CARD)
                inner.pack(side="left", fill="both", expand=True, anchor="n")
                continue
            title, kinds = section
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
            found = self._selected()
            if kind == "else" and found:
                # (2.12) an Else goes right after its If: the chosen If, or the If the chosen action is in
                # (a key just added inside the If is still chosen: the Else must not land inside the If)
                if found[0].get("kind") in ("if", "if_counter"):
                    lst, i = found[1], found[2] + 1
                elif found[3] is not None and found[3].get("kind") in ("if", "if_counter"):
                    outer = workflow.find(self.steps, found[3].get("id"))
                    if outer:
                        lst, i = outer[1], outer[2] + 1
            lst.insert(i, a)
        self.change(do, select=a["id"])

    def _where_choices(self):
        """At the start / inside the chosen group (2.11) / after the chosen action / at the end."""
        choices = [("At the start", "start")]
        found = self._selected()
        if found and found[0].get("kind") in workflow.GROUPS:
            choices.append(("Inside the chosen group", "inside"))
        if found:
            choices.append(("After the chosen action", "after"))
        return choices + [("At the end", "end"), ("Cancel", None)]

    def _ask_where(self, title, text):
        """Where new actions go (None = cancelled)."""
        choices = self._where_choices()
        return self.app.boxes.askchoice(title, text, choices, default=choices[0][1], parent=self.win)

    def _put(self, new_steps, where, chosen_id):
        """Put steps where _ask_where said (in the step tree as it is now)."""
        found = workflow.find(self.steps, chosen_id) if chosen_id else None
        if where == "start":
            self.steps[0:0] = new_steps
        elif where == "inside" and found and found[0].get("kind") in workflow.GROUPS:
            found[0].setdefault("actions", []).extend(new_steps)
        elif where == "after" and found:
            found[1][found[2] + 1:found[2] + 1] = new_steps
        else:
            self.steps.extend(new_steps)

    def _insert_steps(self, new_steps, where, after_id=None):
        """Put steps in this macro (as one change, so Undo takes them out again)."""
        new_steps = [self._fresh_ids(copy.deepcopy(a)) for a in new_steps]
        if not new_steps:
            return

        self.change(lambda: self._put(new_steps, where, after_id), select=new_steps[0]["id"])

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
        choices = self._where_choices()
        where = app.boxes.askchoice(
            "Record keys and mouse", "Where should the new recording go in this macro?\n\nAfter you choose, "
            f"recording starts at once. Press the Record key ({core.hotkey_name(app.hotkeys['record'])}) "
            "again to stop it; this window then comes back.", choices, default=choices[0][1], parent=self.win)
        if where is None:
            return
        chosen_id = self._selected_id() if where in ("after", "inside") else None

        def done(events):
            self.win.deiconify()
            self.win.lift()
            if not events:
                return
            step = workflow.new_action("recorded")
            step["events"] = self.to_macro_size(events)

            self.change(lambda: self._put([step], where, chosen_id), select=step["id"])
        app.record_into = done
        self.win.withdraw()
        app.toggle_record()

    def duplicate(self):
        if self.focus == "macros":
            return self._duplicate_macro()
        chosen = self._chosen()
        if not chosen:
            return
        twins = []

        def do():
            for a, lst, _i, _p in reversed(chosen):
                twin = workflow.ensure_ids([self._fresh_ids(copy.deepcopy(a))])[0]
                lst.insert(lst.index(a) + 1, twin)
                twins.insert(0, twin["id"])
        self.change(do, select=twins)

    @staticmethod
    def _fresh_ids(a):
        a["id"] = workflow.new_id()
        for sub in a.get("actions", []) if a.get("kind") in workflow.GROUPS else []:
            MacroEditor._fresh_ids(sub)
        return a

    REMOVE_ASK_OVER = 5

    def remove(self, ask=True):
        if self.focus == "macros":
            return self._remove_macro()
        chosen = self._chosen()
        if not chosen:
            return
        if ask and len(chosen) > self.REMOVE_ASK_OVER and not self.app.boxes.askyesno(
                "Edit", f"Remove these {len(chosen)} actions?\n\nUndo puts them back.", parent=self.win):
            return
        a, lst, i, _p = chosen[-1]
        gone = {c[0]["id"] for c in chosen}
        after = [b["id"] for b in lst[i + 1:] if b["id"] not in gone]
        before = [b["id"] for b in lst[:chosen[0][2]] if b["id"] not in gone] if chosen[0][1] is lst else []
        nxt = after[0] if after else (before[-1] if before else None)

        def do():
            for b, blst, _i, _p in reversed(chosen):
                blst.remove(b)
        self.change(do, select=nxt)

    def move(self, d):
        """Move the chosen actions one place up (d = -1) or down (1), each within its own list."""
        chosen = self._chosen()
        if not chosen:
            return
        ids = [c[0]["id"] for c in chosen]

        def do():
            lists = []
            for _a, lst, _i, _p in chosen:
                if not any(lst is x for x in lists):
                    lists.append(lst)
            for lst in lists:
                picked = [b for b in lst if b["id"] in ids]
                order = range(len(lst)) if d < 0 else range(len(lst) - 1, -1, -1)
                for k in order:
                    j = k + d
                    if lst[k] in picked and 0 <= j < len(lst) and lst[j] not in picked:
                        lst[k], lst[j] = lst[j], lst[k]
        self.change(do, select=ids)

    def copy(self):
        chosen = self._chosen()
        if chosen:
            self.clipboard = [copy.deepcopy(c[0]) for c in chosen]

    def cut(self):
        """(2.11) Copy the chosen actions, then take them out (Undo puts them back)."""
        if self.focus != "steps" or not self._chosen():
            return
        self.copy()
        self.remove(ask=False)

    def paste(self):
        if self.clipboard is None or self.current is None:
            return
        items = self.clipboard if isinstance(self.clipboard, list) else [self.clipboard]
        new = [self._fresh_ids(copy.deepcopy(b)) for b in items]

        def do():
            lst, i = self._place()
            lst[i:i] = new
        self.change(do, select=[b["id"] for b in new])

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
        chosen = self._chosen()
        if not chosen:
            return
        lst = chosen[0][1]
        if any(c[1] is not lst for c in chosen):
            self.app.boxes.showinfo("Edit", "To group them, choose actions that are in the same list (not some "
                                    "inside a group and some outside it).", parent=self.win)
            return
        g = workflow.new_action(kind)
        items = [c[0] for c in chosen]

        def do():
            i = lst.index(items[0])
            for b in items:
                lst.remove(b)
            g["actions"] = items
            lst.insert(i, g)
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
        """Turn the chosen actions off (or, when they're all off already, on again)."""
        chosen = self._chosen()
        if not chosen:
            return
        items = [c[0] for c in chosen]
        turn_on = all(b.get("off") for b in items)

        def do():
            for b in items:
                if turn_on:
                    b.pop("off", None)
                else:
                    b["off"] = True
        self.change(do, select=[b["id"] for b in items])

    # ------------------------------------------------------------ (2.11) tests and Show my clicks

    def _right_click(self, e):
        iid = self.tree.identify_row(e.y)
        if not iid:
            return
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self._step_clicked()
        m = self._menu()
        self._test_items(m)
        m.add_separator()
        for label, fn in (("Duplicate", self.duplicate), ("Copy", self.copy), ("Cut", self.cut),
                          ("Remove", self.remove)):
            m.add_command(label=label, command=fn)
        # (Preview 4) in and out of groups, right here (greyed out when it can't be done now)
        m.add_separator()
        in_group, above_group, is_group = self._group_moves()
        for label, accel, fn, ok in (
                ("Move out of the group", "Alt+Left", self.out_of_group, in_group),
                ("Move into the group above", "Alt+Right", self.into_group_above, above_group),
                ("Put in a new If", "", lambda: self.group_into("if"), True),
                ("Put in a new Repeat", "", lambda: self.group_into("repeat"), True),
                ("Put in a new Retry", "", lambda: self.group_into("retry"), True),
                ("Ungroup", "", self.ungroup, is_group)):
            m.add_command(label=label, accelerator=accel, command=fn, state="normal" if ok else "disabled")
        m.tk_popup(e.x_root, e.y_root)

    def _group_moves(self):
        """(Preview 4) What the chosen action can do: (move out of its group, move into the group above it,
        ungroup it)."""
        found = self._selected()
        a = found[0] if found else {}
        in_group = bool(found and found[3] is not None)
        above_group = bool(found and found[2] > 0 and found[1][found[2] - 1].get("kind") in workflow.GROUPS)
        return in_group, above_group, a.get("kind") in workflow.GROUPS

    def _test_items(self, m):
        ok = "normal" if self._selected_id() and not self.app.playing and not self.app.recording else "disabled"
        m.add_command(label="Play from here (test)", command=lambda: self.test_play("from"), state=ok)
        m.add_command(label="Play only this action (test)", command=lambda: self.test_play("only"), state=ok)
        m.add_command(label="Show without playing (nothing is pressed)", command=lambda: self.test_play("ghost"),
                      state=ok)
        if not hasattr(self, "ghost_not_found"):
            self.ghost_not_found = tk.BooleanVar(value=False)
        on = self.ghost_not_found.get()
        m.add_command(label="  Test as if pictures are missing: " + ("on" if on else "off"),
                      image=self._dot(GREEN if on else RED), compound="left",
                      command=lambda: self.ghost_not_found.set(not self.ghost_not_found.get()))
        m.add_command(label="  What does that mean?", command=self._ghost_help)
        m.add_command(label="Show my clicks…", command=self.show_clicks,
                      state="normal" if self.steps else "disabled")

    def _dot(self, color):
        """A small round dot picture (green = on, red = off, like Picture watch)."""
        cache = self.__dict__.setdefault("dots", {})
        if color not in cache:
            img = tk.PhotoImage(master=self.win, width=12, height=12)
            for y in range(12):
                for x in range(12):
                    if (x - 5.5) ** 2 + (y - 5.5) ** 2 <= 22:
                        img.put(color, (x, y))
            cache[color] = img
        return cache[color]

    GHOST_HELP = ("\"Show without playing\" doesn't look at the screen, so steps that need a picture (Wait for a "
                  "picture, If, Retry) need an answer:\n\n"
                  "OFF (red dot, the usual): every picture counts as FOUND. If-steps run what's inside them, "
                  "Wait for a picture goes on.\n\n"
                  "ON (green dot): no picture counts as found. If-steps are skipped, Retry tries again, and Wait "
                  "for a picture does what you chose for when it doesn't show (go on or stop).\n\n"
                  "So you can check both ways your macro can go. A real test (Play from here) always looks "
                  "at the screen.")

    def _ghost_help(self):
        self.app.boxes.showinfo("Test as if pictures are missing", self.GHOST_HELP, parent=self.win)

    def to_macro_size(self, events):
        """(2.11) A recording made now, moved to the size this macro was made for (its game window, or
        its screen), so the whole macro matches when it's fitted to the screen it plays on."""
        app = self.app
        screen, program = self._macro_fit()
        here = (app.screen_w, app.screen_h)
        client = (program or {}).get("client")
        try:
            if app.settings.get("fit_to", "window") == "window" and client and len(client) == 4 and client[3] > 0:
                now = app._game_client_rect(program)
                if now:
                    if tuple(now) != tuple(client):
                        core.diag.info(f"Recording for Edit fitted from the game window {tuple(now)} to the "
                                       f"macro's {tuple(client)}")
                        return core.scale_events_rect(events, now, client)
                    return events
            if screen and tuple(screen) != here:
                core.diag.info(f"Recording for Edit fitted from {here[0]}x{here[1]} to the macro's "
                               f"{screen[0]}x{screen[1]}")
                return core.scale_events(events, here, screen)
        except Exception as exc:
            core.diag.error("Couldn't fit the recording to the macro's size", exc)
        return events

    def _macro_fit(self):
        """The screen size and game the edited macro was recorded for (to fit its spots to this screen)."""
        path = self.entries[self.current][1] if self.current is not None else None
        program = getattr(self, "program", None)  # (Preview 4: as shown in Edit, also before Apply)
        if path is None or path == self.app.current_file:
            return self.app.macro_screen, program if hasattr(self, "game_label") else self.app.macro_program
        d = self.file_data or {}
        try:
            screen = (int(d["screen"]["width"]), int(d["screen"]["height"]))
        except (KeyError, TypeError, ValueError):
            screen = None
        if hasattr(self, "game_label"):
            return screen, program
        return screen, d.get("program") if isinstance(d.get("program"), dict) else None

    def test_play(self, how):
        """how: "from" (this action to the end), "only" (just the chosen ones), "ghost" (from here, but
        nothing is pressed). Plays what Edit shows now, also changes not applied yet. Never counted."""
        chosen = self._chosen()
        if not chosen:
            return False
        if how == "only":
            steps = [copy.deepcopy(c[0]) for c in chosen]
            for b in steps:
                b.pop("off", None)  # ("only this action": also when it's turned off)
        else:
            steps = workflow.steps_from(self.steps, chosen[0][0]["id"])
        # (2.12) an Else on its own never runs: its If plays first, so the test shows what really happens
        a, lst, i, _parent = chosen[0]
        if a.get("kind") == "else" and step_more.else_has_if(lst, i) and \
                not any(c[0] is lst[i - 1] for c in chosen):
            steps.insert(0, copy.deepcopy(lst[i - 1]))
        screen, program = self._macro_fit()
        found = not (hasattr(self, "ghost_not_found") and self.ghost_not_found.get())
        return self.app.play_test(steps, "ghost" if how == "ghost" else "test", screen, program, found=found)

    def show_clicks(self):
        import clicks_view

        return clicks_view.open_clicks(self)

    def _drop_steps(self, ids, target, where):
        """(2.11) Chosen actions dragged onto another one: they go before or after it (in its list)."""
        moving = [c[0] for c in self._chosen()]  # (ids: the list's choice; inside chosen groups go along)
        moving_ids = {b["id"] for b in moving}
        found = workflow.find(self.steps, target)
        if not moving or not found or target in moving_ids:
            return
        # (a group can't go inside itself)
        parent = found[3]
        while parent is not None:
            if parent.get("id") in moving_ids:
                return
            up = workflow.find(self.steps, parent.get("id"))
            parent = up[3] if up else None

        if where == "into" and found[0].get("kind") not in workflow.GROUPS:
            where = "after"

        def do():
            for b in moving:
                for _a, lst, _i, _p in workflow.walk(self.steps):
                    k = next((n for n, x in enumerate(lst) if x is b), None)
                    if k is not None:
                        del lst[k]
                        break
            t, tlst, ti, _p = workflow.find(self.steps, target)
            if where == "into":  # (2.11: dropped on the middle of a group's row: inside it, at its end)
                t.setdefault("actions", []).extend(moving)
                return
            at = ti + (1 if where == "after" else 0)
            tlst[at:at] = moving
        self.change(do, select=[b["id"] for b in moving])

    def _drop_macros(self, ids, target, where):
        """(2.11) Chosen macros dragged in the list: the saved macros list gets that order.
        (Preview 4) Dropped on a folder: they go into it; next to a macro: into that macro's folder."""
        paths = [self.entries[int(i)][1] for i in ids if i.isdigit() and self.entries[int(i)][1]]
        if target.startswith("f:"):
            if paths:
                self.app.set_macro_folder(paths, target[2:])
                self._fill_macros()
            return
        tpath = self.entries[int(target)][1]
        if not paths or not tpath or tpath in paths:
            return
        folder = self.app.macro_meta(tpath)["folder"]
        if any(self.app.macro_meta(p)["folder"] != folder for p in paths):
            self.app.set_macro_folder(paths, folder)
        lib = self.app.macro_list()
        keys = {os.path.normcase(os.path.abspath(p)) for p in paths}
        moving = [p for p in lib if os.path.normcase(os.path.abspath(p)) in keys]
        rest = [p for p in lib if os.path.normcase(os.path.abspath(p)) not in keys]
        tkey = os.path.normcase(os.path.abspath(tpath))
        at = next((k for k, p in enumerate(rest) if os.path.normcase(os.path.abspath(p)) == tkey), None)
        if at is None or not moving:
            return
        at += 1 if where == "after" else 0
        lib[:] = rest[:at] + moving + rest[at:]
        core.save_settings(self.app.settings)
        current = self.entries[self.current][1] if self.current is not None else None
        self._fill_macros()
        if current:
            self.current = next((k for k, (_l, p) in enumerate(self.entries) if p == current), self.current)
        self.macros.selection_set([str(k) for k, (_l, p) in enumerate(self.entries)
                                   if p in paths and self.macros.exists(str(k))])

    # ------------------------------------------------------------ (Preview 4) folders and tags

    def _select_macro_row(self, i):
        if i is not None and self.macros.exists(str(i)):
            self.macros.selection_set(str(i))

    def _macros_right_click(self, e):
        iid = self.macros.identify_row(e.y)
        if not iid:
            return
        m = self._menu()
        if iid.startswith("f:"):
            name = iid[2:]
            m.add_command(label="Rename folder…", command=lambda: self._rename_folder(name))
            m.add_command(label="Remove folder (its macros stay)", command=lambda: self._remove_folder(name))
        else:
            if iid not in self.macros.selection():
                self.macros.selection_set(iid)
            self._folder_items(m)
        m.tk_popup(e.x_root, e.y_root)

    def _folder_items(self, m):
        """Move to folder ▸ and Tags… for the chosen macros (right-click, and More)."""
        paths = [p for _l, p in self._chosen_macros() if p]
        sub = self._menu()
        for f in self.app.macro_folders():
            sub.add_command(label=f, command=lambda f=f: self._to_folder(paths, f))
        if self.app.macro_folders():
            sub.add_separator()
        sub.add_command(label="New folder…", command=lambda: self._to_folder(paths, None))
        sub.add_command(label="No folder", command=lambda: self._to_folder(paths, ""))
        m.add_cascade(label="Move to folder", menu=sub, state="normal" if paths else "disabled")
        m.add_command(label="Tags…", command=lambda: self._edit_tags(paths[0]),
                      state="normal" if len(paths) == 1 else "disabled")

    def _ask_text(self, title, question, text=""):
        ok, answer = self.app.boxes._box(title, question, "question", [("OK", True), ("Cancel", False)], True,
                                         False, self.win, entry=text)
        return answer if ok else None

    def _to_folder(self, paths, folder):
        if folder is None:
            folder = self._ask_text("New folder", "A name for the new folder:")
            if not folder or not folder.strip():
                return
        self.app.set_macro_folder(paths, folder)
        self._fill_macros()

    def _edit_tags(self, path):
        now = ", ".join(self.app.macro_meta(path)["tags"])
        text = self._ask_text("Tags", "Tags for this macro, with commas between them\n(like: aot:r, farm, rejoin):",
                              now)
        if text is not None:
            self.app.set_macro_tags(path, text)
            self._fill_macros()

    def _rename_folder(self, name):
        new = self._ask_text("Rename folder", "A new name for the folder:", name)
        if new and new.strip() and self.app.rename_folder(name, new):
            self._fill_macros()

    def _remove_folder(self, name):
        if self.app.boxes.askyesno("Remove folder", f"Remove the folder \"{name}\"?\n\nIts macros stay in the list "
                                   "(with no folder). No file is deleted.", parent=self.win):
            self.app.remove_folder(name)
            self._fill_macros()

    def _more_menu(self):
        m = self._menu()
        if self.focus == "macros":
            m.add_command(label="Open it in the main window", command=self._open_in_app)
            m.add_command(label="Show the file in its folder", command=self._show_file)
            path = self.entries[self.current][1] if self.current is not None else None
            m.add_command(label="Restore an older version…", command=self._restore_version,
                          state="normal" if path and macro_versions.versions(path) else "disabled")
            m.add_separator()
            self._folder_items(m)  # (Preview 4)
        else:
            found = self._selected()
            a = found[0] if found else {}
            in_group = bool(found and found[3] is not None)
            above_group = bool(found and found[2] > 0 and found[1][found[2] - 1].get("kind") in workflow.GROUPS)
            is_group = a.get("kind") in workflow.GROUPS
            for item in (
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
                if item is None:  # (a line between parts; 2.9.2: this used to stop the menu opening)
                    m.add_separator()
                    continue
                label, accel, fn, ok = item
                m.add_command(label=label, accelerator=accel, command=fn, state="normal" if ok else "disabled")
            m.add_separator()
            self._test_items(m)
        b = self.btn_more
        m.tk_popup(b.winfo_rootx(), b.winfo_rooty() - 10 - 22 * m.index("end"))

    # ------------------------------------------------------------ the macros: duplicate, remove

    def _chosen_macros(self):
        """(2.11) The chosen macros: [(label, path)] (the open one when none is chosen)."""
        sel = [int(i) for i in self.macros.selection() if i.isdigit() and int(i) < len(self.entries)]
        if not sel and self.current is not None:
            sel = [self.current]
        return [self.entries[i] for i in sel]

    def _duplicate_macro(self):
        chosen = self._chosen_macros()
        if not chosen:
            return
        if len(chosen) > 1:
            for label, path in chosen:
                if path:
                    self._duplicate_one(label, path, open_it=False)
            self._fill_macros()
            return
        label, path = chosen[0]
        if path is None:
            self.app.boxes.showinfo("Edit", "Save this macro first (Save… in the main window).", parent=self.win)
            return
        self._duplicate_one(label, path)

    def _duplicate_one(self, label, path, open_it=True):
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
        if not open_it:
            return
        self._fill_macros()
        i = next(k for k, (_l, p) in enumerate(self.entries) if p and os.path.normcase(p) == os.path.normcase(
            os.path.abspath(new)))
        self._open_entry(i)

    def _remove_macro(self):
        chosen = [(label, path) for label, path in self._chosen_macros() if path]
        if not chosen:
            return
        what = chosen[0][0] if len(chosen) == 1 else f"these {len(chosen)} macros"
        if not self.app.boxes.askyesno("Edit", f"Take {what} off the saved macros list?\n\nThe "
                                       f"file{'s themselves are' if len(chosen) > 1 else ' itself is'} kept.",
                                       parent=self.win):
            return
        lib = self.app.macro_list()
        for _label, path in chosen:
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

    def _restore_version(self):
        """(2.10) Pick one of the versions the macro had before it was saved over, and put it back."""
        if self.current is None or not self.entries[self.current][1]:
            return
        label, path = self.entries[self.current]
        kept = macro_versions.versions(path)
        if not kept:
            self.app.boxes.showinfo("Edit", f"{label} has no older versions yet. One is kept each time it's "
                                    "saved.", parent=self.win)
            return
        win = tk.Toplevel(self.win, bg=BG)
        win.title("Restore an older version")
        win.transient(self.win)
        win.resizable(False, False)
        dark_title_bar(win)
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=18, pady=14)
        tk.Label(body, text=f"Older versions of {short(label, 40)}", bg=BG, fg=TEXT, font=F_BOLD,
                 anchor="w").pack(fill="x")
        tk.Label(body, text=f"The last {macro_versions.KEEP} saves are kept, newest first.", bg=BG, fg=DIM,
                 font=F_SMALL, anchor="w").pack(fill="x", pady=(0, 6))
        lst = ttk.Treeview(body, show="tree", selectmode="browse", height=min(10, len(kept)))
        lst.column("#0", width=300)  # (room for the whole date)
        lst.pack(fill="x")
        for i, (_p, when) in enumerate(kept):
            lst.insert("", "end", iid=str(i), text="Before the save of " + macro_versions.when_text(when))
        lst.selection_set("0")

        def restore():
            sel = lst.selection()
            if not sel:
                return
            version, when = kept[int(sel[0])]
            if not self.app.boxes.askyesno(
                    "Edit", f"Put back {label} as it was before the save of {macro_versions.when_text(when)}?\n\n"
                    "The macro as it is now is kept as an older version too, so you can go back to it."
                    + ("\n\nThe changes not applied in Edit are thrown away." if self._changed() else ""),
                    parent=win):
                return
            try:
                macro_versions.restore(version, path)
            except OSError as exc:
                self.app.boxes.showerror("Edit", f"Couldn't restore it:\n{exc}", parent=win)
                return
            win.destroy()
            if path == self.app.current_file:
                self.app.load(path, quiet=True)
                self.app.sub_note = "An older version was put back"
                self.app._refresh()
            self._fill_macros()
            self._open_entry(self.current, ask=False)

        row = tk.Frame(body, bg=BG)
        row.pack(fill="x", pady=(10, 0))
        ttk.Button(row, text="Close", command=win.destroy).pack(side="right")
        ttk.Button(row, text="Restore", command=restore).pack(side="right", padx=(0, 6))

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
                self.change(lambda: a.__setitem__(key, value), select=self._owner(a)["id"], keep_detail=True)
                self._refresh_row(a)
        box.bind("<<ComboboxSelected>>", picked)

    def _owner(self, a):
        """The step a value belongs to: the step itself, or (for an If / Retry condition, which has no
        id of its own) the chosen step. (2.12 fix: changing a condition's drop-down failed with an error.)"""
        if "id" in a:
            return a
        found = self._selected()
        return found[0] if found else a

    def _refresh_row(self, a):
        """The step's line in the list and the summary after a value changed (no new Undo point)."""
        a = self._owner(a)
        if "id" not in a:
            return
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
        ttk.Button(row, text="Trim…", command=lambda: self.trim_window(a)).pack(side="left", padx=6)

    def trim_window(self, a):
        """Cut dead time out of a recorded part: the wait at its start, mouse wandering at its end and
        long pauses in the middle, each one ticked (or not) before anything changes."""
        import trim

        evs = a.get("events", [])
        win = tk.Toplevel(self.win, bg=BG)
        win.title("Trim")
        win.transient(self.win)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=18, pady=14)
        tk.Label(body, text="Cut out time where nothing happens", bg=BG, fg=TEXT, font=F_BOLD, anchor="w").pack(
            fill="x")
        tk.Label(body, text="Tick what should go. A pause only counts when no key or button is held down. "
                            "Careful with pauses that wait for the game (a loading screen): leave those.",
                 bg=BG, fg=MUTED, font=F_SMALL, anchor="w", justify="left", wraplength=470).pack(fill="x", pady=(2, 8))
        top = tk.Frame(body, bg=BG)
        top.pack(fill="x")
        tk.Label(top, text="Suggest pauses longer than (seconds)", bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
        gap_var = tk.StringVar(value=f"{trim.MIN_GAP:g}")
        tk.Entry(top, textvariable=gap_var, width=6, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat",
                 insertbackground=TEXT, highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side="right", ipady=3)
        lst = tk.Frame(body, bg=BG)
        lst.pack(fill="x", pady=(8, 0))
        total = tk.Label(body, text="", bg=BG, fg=MUTED, font=F_BASE, anchor="w")
        total.pack(fill="x", pady=(8, 0))
        state = {"found": [], "vars": []}

        def chosen():
            return [c for c, v in zip(state["found"], state["vars"]) if v.get()]

        def show_total():
            secs = trim.saved_seconds(chosen())
            length = evs[-1].get("t", 0) if evs else 0
            total.config(text=f"{secs:.1f} s shorter: {length:.1f} s becomes {length - secs:.1f} s."
                         if secs else "Nothing ticked.")

        def fill(*_a):
            try:
                min_gap = max(0.2, float(gap_var.get().strip().replace(",", ".")))
            except ValueError:
                return
            for child in lst.winfo_children():
                child.destroy()
            state["found"] = trim.suggestions(evs, min_gap=min_gap)
            state["vars"] = []
            if not state["found"]:
                tk.Label(lst, text="Nothing to cut: no dead time found.", bg=BG, fg=DIM, font=F_BASE,
                         anchor="w").pack(fill="x")
            for c in state["found"][:40]:
                var = tk.BooleanVar(value=c["kind"] != "gap")  # start and end ticked; pauses are yours to tick
                state["vars"].append(var)
                tk.Checkbutton(lst, text=c["text"], variable=var, command=show_total, bg=BG, fg=TEXT,
                               selectcolor=FIELD, activebackground=BG, activeforeground=TEXT, font=F_BASE,
                               anchor="w").pack(fill="x")
            if len(state["found"]) > 40:
                tk.Label(lst, text=f"…and {len(state['found']) - 40} more (raise the seconds to see fewer).",
                         bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x")
            show_total()
        gap_var.trace_add("write", fill)
        fill()

        def every(on):
            for v in state["vars"]:
                v.set(on)
            show_total()

        def cut():
            picked = chosen()
            if picked:
                new_events = trim.apply(evs, picked)
                self.change(lambda: a.__setitem__("events", new_events), select=a["id"])
            win.destroy()
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(0, 14))
        link(bottom, "Tick all", lambda: every(True), bg=BG).pack(side="left")
        link(bottom, "Untick all", lambda: every(False), bg=BG).pack(side="left", padx=10)
        ttk.Button(bottom, text="Cut", style="Accent.TButton", width=8, command=cut).pack(side="right")
        ttk.Button(bottom, text="Cancel", width=8, command=win.destroy).pack(side="right", padx=6)
        dark_title_bar(win)
        win.cut, win.state, win.every, win.gap_var = cut, state, every, gap_var
        return win

    def _detail_wait(self, box, a):
        self._field(box, "Wait (seconds)", a, "seconds", float, 0, 36000)
        self._more_wait_rows(box, a)

    def _detail_note(self, box, a):
        self._field(box, "Note", a, "text", str, width=34)
        self._more_note_rows(box, a)

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
        self._more_key_rows(box, a)

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
        self._more_type_rows(box, a)

    def _point_rows(self, box, a):
        self._field(box, "X (from the left of the screen)", a, "x", int)
        self._field(box, "Y (from the top)", a, "y", int)
        row = tk.Frame(box, bg=BG)
        row.pack(fill="x", pady=(4, 0))

        def pick():
            def picked(x, y):
                x, y = self._spot_to_macro(x, y)  # (2.12: kept in the macro's size, like colour spots)

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
        self._more_click_rows(box, a)

    def _detail_move(self, box, a):
        if not a.get("relative"):
            self._point_rows(box, a)
        self._more_move_rows(box, a)

    def _detail_scroll(self, box, a):
        self._field(box, "Notches (+ up, - down)", a, "amount", int, -100, 100)
        self._more_scroll_rows(box, a)

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
        color = self._color_switch(box, a, a)
        if color:
            self._color_rows(box, a, a)
        else:
            self._picture_thumb(box, a, lambda fn: self.change(fn, select=a["id"]))
            self._field(box, "Name", a, "name", str, width=24)
        self._field(box, "Wait up to (seconds, 0 = no limit)", a, "timeout", float, 0, 36000)
        if not color:
            self._how_close(box, a)
        click = tk.BooleanVar(value=bool(a.get("click")))
        row = self._row(box, "Click on the spot when it shows" if color else "Click on it when it shows")
        Switch(row, click, command=lambda: self.change(lambda: a.__setitem__("click", bool(click.get())),
                                                       select=a["id"])).pack(side="right")
        self._rebuild_choice(box, "If it doesn't happen in time", a, "otherwise", self.OTHERWISE)
        self._more_wait_picture_rows(box, a)

    def _condition(self, box, a):
        c = a.setdefault("condition", {"shows": True, "png": None, "screen_h": None, "match": 85})
        tk.Label(box, text="CONDITION", bg=BG, fg=MUTED, font=F_SECTION, anchor="w").pack(fill="x")
        if self._condition_kind_row(box, a, c) != "picture":  # (2.12: a counter, a program or the time)
            self._condition_other_rows(box, a, c)
            self._condition_more_rows(box, a, c)
            return
        color = self._color_switch(box, a, c)
        self._choice(box, "When this colour" if color else "When this picture", c, "shows",
                     {True: "shows on screen", False: "doesn't show"})
        if color:
            self._color_rows(box, a, c)
        else:
            self._picture_thumb(box, c, lambda fn: self.change(fn, select=a["id"]))
            self._field(box, "Name", c, "name", str, width=24)
            self._how_close(box, c)
        self._condition_more_rows(box, a, c)

    # ------------------------------------------------------------ (2.12) colour checks

    def _color_switch(self, box, a, h):
        """The "Check a colour instead of a picture" switch (off at first). True when it's on."""
        on = tk.BooleanVar(value=h.get("color_on") is True)
        row = self._row(box, "Check a colour instead of a picture", "no picture needed")

        def flip():
            def do():
                h["color_on"] = bool(on.get())
                if h["color_on"]:
                    for k, v in (("tolerance", 10), ("area", 1), ("hold", 0.0), ("where", "spot")):
                        h.setdefault(k, v)
            self.change(do, select=a["id"])
        Switch(row, on, command=flip).pack(side="right")
        return on.get()

    COLOR_HELP = ("A colour check looks at one spot of the game (or the whole screen) and asks: is this colour "
                  "there? It's quicker than a picture and works for things like a health bar turning red or a "
                  "button lighting up.\n\n"
                  "Pick spot and colour: click the spot on a frozen screenshot; its colour is taken too. "
                  "Pick colour only: take a colour from anywhere.\n"
                  "How close: 100 = exactly this colour; 80-90 is usual (light changes a little).\n"
                  "Area: one pixel, or a small square around the spot (more steady).\n"
                  "Must stay for: it only counts when the colour has stayed that long (no flickers).\n"
                  "Where to look: only the spot you picked (best), or the whole screen (any patch of the colour "
                  "counts; slower, and other things with that colour can count too).\n\n"
                  "The spot follows \"Fit clicks to: The game window\", like clicks do.\n\n"
                  "More than one screen? The picker shows your main screen only: put the game there to pick. "
                  "\"The whole screen\" also means the main screen only.")

    def _color_rows(self, box, a, h):
        import color_check

        app = self.app
        row = self._row(box, "Spot", f"{h['x']}, {h['y']}" if "x" in h else "not picked yet")
        link(row, "ⓘ", lambda: app.boxes.showinfo("Colour check", self.COLOR_HELP, parent=self.win),
             bg=BG).pack(side="left", padx=(6, 0))

        def picked(x, y, rgb):
            x, y = self._spot_to_macro(x, y)  # (2.12: picked on this screen, kept in the macro's size)
            self.change(lambda: h.update(x=x, y=y, rgb=list(rgb)), select=a["id"])

        def picked_color(_x, _y, rgb):
            self.change(lambda: h.update(rgb=list(rgb)), select=a["id"])
        ttk.Button(row, text="Pick spot and colour…",
                   command=lambda: app._pick_point(self.win, picked, with_color=True)).pack(side="right")
        row = self._row(box, "Colour", color_check.hex_of(h["rgb"]) if h.get("rgb") else "not picked yet")
        ttk.Button(row, text="Pick colour only…",
                   command=lambda: app._pick_point(self.win, picked_color, with_color=True)).pack(side="right")
        if h.get("rgb"):
            tk.Label(row, text="      ", bg=color_check.hex_of(h["rgb"]), relief="flat").pack(side="right", padx=8)
        self._how_close(box, h)
        self._choice(box, "Area", h, "area", {1: "1 pixel", 5: "A small square (5 × 5)"})
        self._field(box, "Must stay for (seconds)", h, "hold", float, 0, 60)
        self._choice(box, "Where to look", h, "where", {"spot": "Only the spot I picked",
                                                      "area": "An area I draw",
                                                      "screen": "The whole screen"})
        if h.get("where") == "area":
            row = self._row(box, "Area", f"{h['x0']}, {h['y0']} to {h['x1']}, {h['y1']}" if "x0" in h
                            else "not drawn yet")

            def drew(x0, y0, x1, y1):
                x0, y0 = self._spot_to_macro(x0, y0)
                x1, y1 = self._spot_to_macro(x1, y1)
                self.change(lambda: h.update(x0=x0, y0=y0, x1=x1, y1=y1), select=self._owner(h)["id"])
            ttk.Button(row, text="Draw the area…", command=lambda: self._draw_area(drew)).pack(side="right")
        self._look_now_row(box, h)
        if h.get("where") == "screen":
            tk.Label(box, text="The whole screen: any patch of this colour counts, so other things with the same "
                               "colour can count too (false matches), and it's looked at less often and costs more "
                               "of the PC. Use \"Only the area I picked\" when you can.", bg=BG, fg=AMBER,
                     font=F_SMALL, anchor="w", justify="left", wraplength=460).pack(fill="x", pady=(6, 0))

    def _spot_to_macro(self, x, y):
        """A spot picked on this screen, in the size the macro was made for (like its recordings)."""
        ev = self.to_macro_size([{"type": "move", "x": int(x), "y": int(y), "t": 0.0}])[0]
        return int(ev["x"]), int(ev["y"])

    def _draw_area(self, on_area):
        """Freeze the screen and drag a box (like taking a picture of an area)."""
        app = self.app
        self.win.withdraw()
        app.root.withdraw()
        app.root.after(300, lambda: app._show_picker(
            on_area=on_area, hidden=(self.win,),
            tip="Drag a box around where the colour can show. Esc cancels."))

    def _look_now_row(self, box, h):
        """(2.12) Look now: is the colour there, how close the best match is, and where."""
        import color_check

        row = self._row(box, "Look now", "is it on the screen right now?")
        result = tk.Label(row, text="", bg=BG, fg=MUTED, font=F_SMALL)

        def look():
            try:
                seen, best, where = color_check.look(h)
            except Exception as exc:
                result.config(text=f"couldn't look: {exc}", fg=RED)
                return
            if not color_check.ready(h):
                result.config(text="pick a colour (and a spot or an area) first", fg=AMBER)
                return
            spot = f" at {where[0]}, {where[1]}" if where else ""
            result.config(text=(f"Seen ✓ (best {best}%{spot})" if seen else f"Not seen ✗ (best {best}%{spot})"),
                          fg=GREEN if seen else RED)
        ttk.Button(row, text="Look now", command=look).pack(side="right")
        result.pack(side="right", padx=(0, 8))

    def _detail_if(self, box, a):
        self._condition(box, a)
        tk.Label(box, text="The actions inside this group only run when the condition is true. Add actions "
                           "into it with Add action while it's chosen, or Alt+Right on the action below it.",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w", justify="left", wraplength=460).pack(fill="x", pady=(8, 0))

    # ------------------------------------------------------------ (2.11) counters

    def _counter_name(self, box, a):
        """The counter's name: pick one the macro already uses, or type a new one."""
        row = self._row(box, "Counter", "pick one or type a new name")
        var = tk.StringVar(value=a.get("counter", "Counter"))
        names = workflow.counters(self.steps)
        combo = ttk.Combobox(row, textvariable=var, values=names, width=22)
        combo.pack(side="right")

        def changed(*_a):
            name = workflow.clean_counter_name(var.get())
            if not var.get().strip() or a.get("counter") == name:
                return
            self._snapshot_for_typing()
            a["counter"] = name
            self._refresh_row(a)
        var.trace_add("write", changed)
        combo.bind("<<ComboboxSelected>>", lambda e: combo.selection_clear())

    def _counter_keep(self, box, a):
        keep = tk.BooleanVar(value=a.get("keep") is True)
        row = self._row(box, "Keep between plays", "else it starts at 0 each time you press Play")

        def flip():
            self.change(lambda: a.__setitem__("keep", bool(keep.get())), select=a["id"], keep_detail=True)
        Switch(row, keep, command=flip).pack(side="right")

    def _detail_counter_add(self, box, a):
        self._counter_name(box, a)
        self._field(box, "Add", a, "amount", int, -workflow.COUNTER_LIMIT, workflow.COUNTER_LIMIT,
                    tip="1 counts one up; -1 counts one down")
        self._counter_keep(box, a)
        self._counter_help(box)

    def _detail_counter_set(self, box, a):
        self._counter_name(box, a)
        self._field(box, "Set it to", a, "value", int, -workflow.COUNTER_LIMIT, workflow.COUNTER_LIMIT)
        self._counter_keep(box, a)
        self._counter_help(box)

    def _detail_if_counter(self, box, a):
        self._counter_name(box, a)
        self._more_if_counter_rows(box, a)
        self._field(box, "The number", a, "at_least", int, -workflow.COUNTER_LIMIT, workflow.COUNTER_LIMIT,
                    tip="when no counter is chosen above")
        tk.Label(box, text="The actions inside only run when the counter has reached this number. Put a "
                           "\"Set a counter\" to 0 inside if it should count again from the start.", bg=BG,
                 fg=DIM, font=F_SMALL, anchor="w", justify="left", wraplength=460).pack(fill="x", pady=(8, 0))
        self._counter_help(box)

    @staticmethod
    def _counter_help(box):
        tk.Label(box, text="Counters are whole numbers. While the macro plays they show in the timer at the top "
                           "of the screen.", bg=BG, fg=DIM, font=F_SMALL, anchor="w", justify="left",
                 wraplength=460).pack(fill="x", pady=(8, 0))

    def _detail_repeat(self, box, a):
        self._more_repeat_rows(box, a)
        if a.get("mode", "times") == "times":
            self._field(box, "Repeat how many times", a, "times", int, 0, 100000)

    def _detail_retry(self, box, a):
        self._condition(box, a)
        self._field(box, "At most how many tries", a, "tries", int, 1, 1000)
        self._more_retry_rows(box, a)
        tk.Label(box, text="The actions inside run, then the condition is checked (for the seconds above); if "
                           "it isn't true yet, they run again.", bg=BG, fg=DIM, font=F_SMALL, anchor="w",
                 justify="left", wraplength=460).pack(fill="x", pady=(8, 0))

    def _detail_play_macro(self, box, a):
        here = self.entries[self.current][1] if self.current is not None else None
        macros = {label: path for label, path in self.entries if path and path != here}
        if a.get("file"):
            macros.setdefault(os.path.splitext(os.path.basename(a["file"]))[0], a["file"])
        row = self._row(box, "Macro")
        now = next((label for label, path in macros.items() if path == a.get("file")), "(choose a macro)")
        var = tk.StringVar(value=now)

        def set_file(path):
            if path and path != a.get("file"):
                self.change(lambda: a.__setitem__("file", path), select=a["id"])

        def from_file():
            path = filedialog.askopenfilename(parent=self.win, filetypes=core.OPEN_FILE_TYPES)
            if path:
                set_file(path)
        ttk.Button(row, text="A macro file…", command=from_file).pack(side="right")
        combo = ttk.Combobox(row, textvariable=var, state="readonly", values=list(macros), width=24)
        combo.pack(side="right", padx=(0, 6))
        combo.bind("<<ComboboxSelected>>", lambda e: (combo.selection_clear(), set_file(macros.get(var.get()))))
        self._field(box, "Play it how many times", a, "times", int, 1, 100000)
        chart = tk.Frame(box, bg=BG)
        chart.pack(fill="x", pady=(2, 4))
        ttk.Button(chart, text="Show the chain as a chart…",
                   command=lambda: self.app.open_chain_chart(self)).pack(side="left")
        profiles = {None: "(the settings in use)"}
        profiles.update({n: n for n in sorted(self.app.settings.get("profiles") or {}, key=str.lower)})
        if a.get("profile") not in profiles:
            a.pop("profile", None)
        a.setdefault("profile", None)
        self._choice(box, "Profile for this part", a, "profile", profiles)
        fails = {"": "(just go on)"}
        fails.update({path: label for label, path in macros.items()})
        if a.get("on_fail") and a["on_fail"] not in fails:
            fails[a["on_fail"]] = os.path.splitext(os.path.basename(a["on_fail"]))[0]
        a.setdefault("on_fail", "")
        self._choice(box, "If a run of it fails, play", a, "on_fail", fails)
        self._more_play_macro_rows(box, a)
        counts = tk.BooleanVar(value=bool(a.get("counts", True)))
        row = self._row(box, "Each time counts as a run", "in the results and on Discord")
        Switch(row, counts, command=lambda: self.change(lambda: a.__setitem__("counts", bool(counts.get())),
                                                        select=a["id"])).pack(side="right")
        tk.Label(box, text="The saved macro plays here, as it is when you press Play (it isn't copied in, so "
                           "changing that macro later changes this too). Put a few of these under each other to "
                           "make a chain: macro A 5 times, then macro B, and with Repeat on it all starts again. "
                           "Picture watch works in every part: when its picture shows, that part's run is over "
                           "and the chain goes on.", bg=BG, fg=DIM, font=F_SMALL, anchor="w", justify="left",
                 wraplength=460).pack(fill="x", pady=(8, 0))

    def _detail_restart(self, box, a):
        tk.Label(box, text="Starts the macro again from step 1 (it stops by itself if this happens more than 10 "
                           "times in 60 seconds). Usually inside an If, as a failsafe.", bg=BG, fg=MUTED, font=F_BASE,
                 anchor="w", justify="left", wraplength=460).pack(fill="x")

    def _detail_stop(self, box, a):
        tk.Label(box, text="Ends the macro here. Usually inside an If.", bg=BG, fg=MUTED, font=F_BASE, anchor="w",
                 justify="left", wraplength=460).pack(fill="x")
        self._more_stop_rows(box, a)


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
        self.edit_win.after(200, self.macro_editor.offer_autosave)

    def _pick_point(self, parent, on_pick, hidden=(), with_color=False):
        """Freeze the screen and let the user click a spot: on_pick(x, y) in screen pixels.
        `hidden`: more windows to hide meanwhile (and show again after). with_color (2.12): a swatch
        follows the mouse with the colour under it, and on_pick(x, y, (r, g, b)) gets it too."""
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
            canvas.create_text(w // 2, 18, text=("Click the spot: its colour is taken too (the square shows it). "
                                                 "Esc cancels." if with_color else "Click the spot. Esc cancels."),
                               fill="white", font=(FAMILY, 12, "bold"))

            def color_at(x, y):
                b_, g_, r_ = (int(v) for v in shot[max(0, min(h - 1, y)), max(0, min(w - 1, x))][:3])
                return r_, g_, b_
            if with_color:
                swatch = canvas.create_rectangle(0, 0, 0, 0, outline="white", width=2)
                swatch_text = canvas.create_text(0, 0, text="", fill="white", anchor="w", font=(FAMILY, 10, "bold"))

                def moved(e):
                    rgb = color_at(e.x, e.y)
                    hx = "#%02x%02x%02x" % rgb
                    canvas.coords(swatch, e.x + 18, e.y + 18, e.x + 58, e.y + 58)
                    canvas.itemconfig(swatch, fill=hx)
                    canvas.coords(swatch_text, e.x + 64, e.y + 38)
                    canvas.itemconfig(swatch_text, text=hx)
                canvas.bind("<Motion>", moved)

            def close():
                win.destroy()
                show_again()

            def clicked(e):
                close()
                if with_color:
                    on_pick(int(mon["left"] + e.x), int(mon["top"] + e.y), color_at(e.x, e.y))
                else:
                    on_pick(int(mon["left"] + e.x), int(mon["top"] + e.y))
            canvas.bind("<Button-1>", clicked)
            win.bind("<Escape>", lambda e: close())
            win.focus_force()
        self.root.after(300, show)

