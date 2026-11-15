"""Picture watch (2.9): its own window, made like the Edit window.

  - GROUPS on the left: General (the options for every picture), AOT:R (the pictures that come with
    the app), My pictures, and groups you make (New group, Duplicate, Remove)
  - PICTURES of the chosen group in the middle: Add from screen, Picture file, Add built-in, Remove,
    Move to group
  - the chosen picture's OPTIONS on the right: on/off, what it does when it shows, which macros it's
    used for, Test now
  - a green dot before a name means on, red off, grey: on, but its group is off
  - the name box at the top renames the chosen group or picture; Undo, Redo, Reset and Apply work on
    everything in the window, and nothing is used until Apply

Settings > Picture watch keeps the on/off switch, a summary and a button that opens this window.
Settings > Results keeps the run stats; its MISSION COMPLETED / FAILED pictures live in AOT:R here.
"""

import copy
import json
import os
import shutil
import time

from ui_common import *  # noqa: F401,F403
from picture_actions_ui import action_summary, macro_label

GENERAL_ID, AOTR_ID, MINE_ID = core.GROUP_GENERAL, core.GROUP_AOTR, core.GROUP_MINE

# what each built-in picture is for (the ⓘ beside it)
BUILTIN_INFO = {
    "retry": ("AOT:R's RETRY button, on the results screen after a mission. When it shows, the run is over: "
              "the macro starts over (with \"Click on it\" on in General, it's clicked first, which starts "
              "the next mission)."),
    "disconnect": ("The word \"Disconnected\" from Roblox's Disconnected box. It only counts in the middle of "
                   "the screen and when it matches very well, so game screens don't set it off. When it "
                   "shows, your rejoin macro plays (choose it below), the app checks you're back in, and "
                   "the macro starts over. Without a rejoin macro it only starts the macro over."),
    "completed": ("AOT:R's gold MISSION COMPLETED title. When it shows, the run counts as won (run stats, "
                  "the timer, Discord)."),
    "failed": "AOT:R's gold MISSION FAILED title. When it shows, the run counts as lost.",
}
BUILTIN_TITLES = {"retry": "RETRY", "disconnect": "Disconnected", "completed": "MISSION COMPLETED",
                  "failed": "MISSION FAILED"}
KIND_CHOICES = {None: "A picture to act on (Retry, Disconnected…)",
                stats.WIN: "MISSION COMPLETED: the run counts as won",
                stats.LOSS: "MISSION FAILED: the run counts as lost"}
# the options in General: setting, default, lowest, highest (None for on/off), the app's box for it
GENERAL = [
    ("watch_click", False, None, None, "watch_click_var"),
    ("watch_wait", 3, 0, 600, "watch_wait_var"),
    ("watch_match", 85, 50, 99, "watch_match_var"),
    ("watch_ignore_bg", True, None, None, "watch_bg_var"),
    ("watch_end_wait", 3, 0, 3600, "watch_end_var"),
    ("watch_limit_count", 10, 0, 1000, "watch_limit_var"),
    ("watch_limit_seconds", 60, 1, 3600, "watch_limit_s_var"),
    ("watch_shift_lock", True, None, None, "watch_shift_var"),
    ("watch_save_with_macro", True, None, None, "watch_embed_var"),
    ("results_match", core.RESULTS_MATCH_DEFAULT, 50, 99, "results_match_var"),
]
WATCH_HELP = (
    "While a macro plays, the app looks at the screen for the pictures that are on, and does what each "
    "one says when it shows: start the macro over (a RETRY button), play your rejoin macro (Roblox's "
    "Disconnected box), count a won or lost run (MISSION COMPLETED / FAILED), and more.\n\n"
    "Open Picture watch to add pictures, sort them into groups, turn them on or off, choose what each "
    "one does, and which macros it's used for.")


def default_groups():
    return [{"id": AOTR_ID, "name": "AOT:R", "builtin": True}, {"id": MINE_ID, "name": "My pictures"}]


def fixed_group(gid):
    """General, AOT:R and My pictures can't be removed."""
    return gid in (GENERAL_ID, AOTR_ID, MINE_ID)


def dot_image(color, thumb=None, height=16, thumb_w=0):
    """A small round dot (green = on, red = off, grey = its group is off), with the picture's
    thumbnail beside it (in a column thumb_w wide, so the names line up), as one Tk picture for a
    list row."""
    h = max(height, thumb.height() if thumb is not None else 0)
    w = 16 + (max(thumb_w, thumb.width() if thumb is not None else 0) + 6 if thumb is not None or thumb_w else 0)
    img = tk.PhotoImage(width=w, height=h)
    cx, cy, r = 7, h // 2, 4.6
    for dy in range(-4, 5):
        half = int((r * r - dy * dy) ** 0.5)
        img.put(color, to=(cx - half, cy + dy, cx + half + 1, cy + dy + 1))
    if thumb is not None:
        img.tk.call(img, "copy", thumb, "-to", 16, (h - thumb.height()) // 2)
    return img


class PictureWatchMixin:
    # ------------------------------------------------------------ Settings > Picture watch (short)

    def _build_watch_ui(self, frame):
        """Settings > Picture watch: the on/off switch, what's on, and the button that opens the
        Picture watch window. (The options themselves are in that window.)"""
        s = self.settings
        self.pictures_fresh = not isinstance(s.get("watch_pictures"), list)  # the very first start
        self.watch_var = tk.BooleanVar(value=bool(s.get("watch_enabled", True)))
        self.watch_click_var = tk.BooleanVar(value=bool(s.get("watch_click", False)))
        self.watch_wait_var = tk.IntVar(value=core.int_setting(s, "watch_wait", 3, 0, 600))
        self.watch_match_var = tk.IntVar(value=core.int_setting(s, "watch_match", 85, 50, 99))
        self.watch_end_var = tk.IntVar(value=core.int_setting(s, "watch_end_wait", 3, 0, 3600))
        self.watch_bg_var = tk.BooleanVar(value=bool(s.get("watch_ignore_bg", True)))
        self.watch_limit_var = tk.IntVar(value=core.int_setting(s, "watch_limit_count", 10, 0, 1000))
        self.watch_limit_s_var = tk.IntVar(value=core.int_setting(s, "watch_limit_seconds", 60, 1, 3600))
        self.watch_shift_var = tk.BooleanVar(value=bool(s.get("watch_shift_lock", True)))
        self.watch_embed_var = tk.BooleanVar(value=bool(s.get("watch_save_with_macro", True)))
        self.picture_summary_var = tk.StringVar(value="")
        self.picture_win = None

        self._section(frame, "PICTURE WATCH", first=True)
        self.watch_switch = self._switch_row(frame, "While playing, watch for pictures", self.watch_var,
                                             "Retry, Disconnected, mission results…", info=WATCH_HELP)
        tk.Label(frame, textvariable=self.picture_summary_var, bg=BG, fg=MUTED, font=F_SMALL, anchor="w",
                 justify="left", wraplength=520).pack(fill="x", pady=(4, 0))
        row = tk.Frame(frame, bg=BG)
        row.pack(fill="x", pady=(10, 0))
        self.btn_open_pictures = ttk.Button(row, text="Open Picture watch…", style="Accent.TButton",
                                            command=self.open_picture_watch)
        self.btn_open_pictures.pack(side="left")
        tk.Label(row, text="groups, pictures, what each one does, and for which macros", bg=BG, fg=DIM,
                 font=F_SMALL).pack(side="left", padx=(10, 0))
        self.watch_widgets = [self.btn_open_pictures]
        self.watch_remove_buttons = []
        if image_watch is None:
            self.watch_var.set(False)
            self.btn_open_pictures.config(state="disabled")
            self.picture_summary_var.set("Not available: this copy was built without picture support.")
            return
        for entry in s.get("watch_pictures") or []:
            pic = core.watch_picture_from(entry)
            if pic is not None:  # (picture file gone: forget it)
                self.watch_pictures.append(pic)

    def _show_watch_pictures(self):
        """The watched pictures changed: remember them, and say what's on."""
        self.settings["watch_pictures"] = [core.watch_entry(p) for p in self.watch_pictures]
        core.save_settings(self.settings)
        self._show_picture_summary()

    def _picture_groups(self):
        groups = self.settings.get("picture_groups")
        return [g for g in groups if isinstance(g, dict) and g.get("id")] if isinstance(groups, list) else []

    def picture_summary(self):
        """"AOT:R: 4 of 4 on · My pictures: 1 of 1 on"."""
        pics = self.watch_pictures + self.result_pictures
        bits = []
        for g in self._picture_groups():
            mine = [p for p in pics if core.picture_group(p) == g["id"]]
            if g.get("on") is False:
                bits.append(f"{g.get('name')}: off")
            elif mine:
                bits.append(f"{g.get('name')}: {sum(1 for p in mine if p.get('on') is not False)} of {len(mine)} on")
        return " · ".join(bits) or "No pictures yet"

    def _show_picture_summary(self):
        if getattr(self, "picture_summary_var", None) is not None:
            self.picture_summary_var.set(self.picture_summary())

    # ------------------------------------------------------------ groups: the first start of 2.9

    def _setup_picture_groups(self):
        """Once: sort the pictures into groups. The built-in pictures go into AOT:R (found by comparing
        them with the app's own), your own into My pictures; built-in pictures that are missing are
        added (on for a new copy of the app, off when you already had pictures). The settings are
        backed up first."""
        s = self.settings
        if image_watch is None:
            return
        if self._picture_groups():
            ids = {g["id"] for g in self._picture_groups()}
            groups = self._picture_groups() + [g for g in default_groups() if g["id"] not in ids]
            if len(groups) != len(self._picture_groups()):
                s["picture_groups"] = groups
                core.save_settings(s)
            self._show_picture_summary()
            return
        fresh = getattr(self, "pictures_fresh", False)
        if not fresh:
            self._backup_settings_before_groups()
        try:
            self._find_builtin_pictures()
        except Exception as exc:
            diag.error("Couldn't compare the pictures with the built-in ones", exc)
        for pic in self.watch_pictures + self.result_pictures:
            pic["group"] = core.picture_group(pic)
        have = {p.get("builtin") for p in self.watch_pictures + self.result_pictures}
        for key in core.BUILTINS:
            if key in have:
                continue
            try:
                entry = self._builtin_entry(key, on=fresh)
            except OSError as exc:
                diag.error("Couldn't add a built-in picture", exc)
                continue
            if entry.get("kind"):
                pic = core.saved_picture(entry.pop("file"), **entry)
                if pic is not None:
                    self.result_pictures.append(pic)
            else:
                pic = core.watch_picture_from(entry)
                if pic is not None:
                    self.watch_pictures.append(pic)
        s["picture_groups"] = default_groups()
        s["watch_pictures"] = [core.watch_entry(p) for p in self.watch_pictures]
        self._save_result_pictures()
        core.save_settings(s, now=True)
        self._show_picture_summary()

    def _backup_settings_before_groups(self):
        """A copy of the settings as they were before 2.9 sorted the pictures (Backups folder, beside
        the settings)."""
        folder = os.path.join(os.path.dirname(core.settings_path()), "Backups")
        try:
            os.makedirs(folder, exist_ok=True)
            dest = os.path.join(folder, "settings before 2.9 picture groups.json")
            if os.path.exists(dest):
                return
            if os.path.isfile(core.settings_path()):
                shutil.copyfile(core.settings_path(), dest)
            else:
                with open(dest, "w", encoding="utf-8") as f:
                    json.dump(self.settings, f, indent=1)
        except OSError as exc:
            diag.error("Couldn't back up the settings", exc)

    def _find_builtin_pictures(self):
        """Mark the pictures that are copies of the built-in ones (they were added with "Add built-in")."""
        import numpy as np
        own = {}
        for key, (file, _h, kind, _f) in core.BUILTINS.items():
            try:
                own[key] = (image_watch.load_image(core.resource_path(file)), kind)
            except Exception:
                continue
        for pics, result in ((self.watch_pictures, False), (self.result_pictures, True)):
            for pic in pics:
                if pic.get("builtin"):
                    continue
                for key, (img, kind) in own.items():
                    if bool(kind) != result or (result and pic.get("kind") != kind):
                        continue
                    try:
                        mine = pic["img"]
                    except Exception:
                        break
                    if mine.shape == img.shape and np.array_equal(mine, img):
                        pic["builtin"] = key
                        if not pic.get("name"):
                            pic["name"] = BUILTIN_TITLES[key]
                        break

    def _builtin_entry(self, key, on=True, group=None):
        """A new copy of a built-in picture (its file copied into the pictures folder), as a settings
        entry with its built-in settings ("kind" set for a result picture)."""
        file, screen_h, kind, fields = core.BUILTINS[key]
        os.makedirs(core.watch_dir(), exist_ok=True)
        name = f"{'result' if kind else 'picture'}_{int(time.time() * 1000)}_{key}.png"
        n = 1
        while os.path.exists(os.path.join(core.watch_dir(), name)):
            n += 1
            name = f"{'result' if kind else 'picture'}_{int(time.time() * 1000)}_{key}_{n}.png"
        shutil.copyfile(core.resource_path(file), os.path.join(core.watch_dir(), name))
        entry = dict(copy.deepcopy(fields), file=name, screen_h=screen_h, builtin=key, group=group or AOTR_ID)
        if not on:
            entry["on"] = False
        if kind:
            entry["kind"] = kind
        return entry

    # ------------------------------------------------------------ links to macros

    def _pictures_macro_renamed(self, old, new):
        """A macro was renamed (Edit window): pictures used only for it, and pictures that play it,
        follow it."""
        key = self._macro_key(old)
        changed = False
        for pic in self.watch_pictures + self.result_pictures:
            macros = pic.get("macros")
            if macros:
                fixed = [os.path.abspath(new) if self._macro_key(m) == key else m for m in macros]
                if fixed != macros:
                    pic["macros"] = fixed
                    changed = True
            if pic.get("macro") and self._macro_key(pic["macro"]) == key:
                pic["macro"] = os.path.abspath(new)
                changed = True
        if changed:
            self.settings["watch_pictures"] = [core.watch_entry(p) for p in self.watch_pictures]
            self._save_result_pictures()
        win = self.picture_win
        if win is not None and win.alive():
            win.macro_renamed(key, os.path.abspath(new))

    # ------------------------------------------------------------ the window

    def open_picture_watch(self, group=None):
        if image_watch is None:
            return None
        win = self.picture_win
        if win is not None and win.alive():
            win.win.deiconify()
            win.win.lift()
            win.win.focus_force()
            if group:
                win.select_group(group)
            return win
        self.picture_win = PictureWatchWindow(self, group)
        return self.picture_win

    def _picture_window_reload(self):
        """The settings changed as a whole (a profile): the window shows them again, unless it has
        changes that weren't applied."""
        win = self.picture_win
        if win is not None and win.alive() and not win.changed():
            win.load_from_app()


class PictureWatchWindow:
    def __init__(self, app, group=None):
        self.app = app
        self.undo_stack = []
        self.redo_stack = []
        self.typing_point = False
        self.new_files = set()  # picture files made while the window is open (gone again if not applied)
        self.thumbs = {}
        self.images = []
        self.sel_group = group or AOTR_ID
        self.sel_pic = None
        self.next_uid = 1
        self.form = None
        self.filling_name = False
        self._build()
        self.load_from_app()
        self.select_group(self.sel_group)

    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    # ------------------------------------------------------------ the working copy

    def load_from_app(self):
        """Everything the window works on, copied from the app's settings (nothing is used until Apply)."""
        app = self.app
        s = app.settings
        self.groups = copy.deepcopy(app._picture_groups()) or default_groups()
        self.pics = []
        for p in app.watch_pictures:
            e = core.watch_entry(p)
            e["kind"] = None
            self.pics.append(self._with_uid(e))
        for p in app.result_pictures:
            e = {"file": p["file"], "screen_h": p.get("screen_h"), "kind": p.get("kind")}
            e.update({k: p[k] for k in ("found_factor", "found_screen", "found_step", "name") if k in p})
            e.update(core.group_fields(p))
            self.pics.append(self._with_uid(e))
        for e in self.pics:
            e["group"] = core.picture_group(e)
        self.general = {}
        for key, default, low, high, _var in GENERAL:
            self.general[key] = bool(s.get(key, default)) if low is None else core.int_setting(s, key, default, low, high)
        self.base = self._state()
        self.undo_stack, self.redo_stack = [], []
        self.typing_point = False
        if hasattr(self, "groups_tree"):
            self._fill_groups()
            self._fill_pictures()
            self._show_options()
            self._show_buttons()

    def _with_uid(self, entry):
        entry["_uid"] = self.next_uid
        self.next_uid += 1
        return entry

    def _state(self):
        return copy.deepcopy((self.groups, self.pics, self.general))

    def changed(self):
        return self._state() != self.base

    def _pic(self, uid):
        return next((e for e in self.pics if e["_uid"] == uid), None)

    def _group(self, gid):
        return next((g for g in self.groups if g["id"] == gid), None)

    def _group_on(self, gid):
        g = self._group(gid)
        return g is None or g.get("on") is not False

    def change(self, fn, rebuild=True):
        """Make a change (fn changes the working copy) so it can be undone."""
        self.undo_stack.append((self._state(), self.sel_group, self.sel_pic))
        del self.undo_stack[:-200]
        self.redo_stack = []
        self.typing_point = False
        fn()
        if rebuild:
            self._fill_groups()
            self._fill_pictures()
            self._show_options()
        self._show_buttons()

    def _typing(self):
        """The first change in a box after choosing something makes one Undo point (not every key)."""
        if not self.typing_point:
            self.typing_point = True
            self.undo_stack.append((self._state(), self.sel_group, self.sel_pic))
            self.redo_stack = []

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append((self._state(), self.sel_group, self.sel_pic))
        self._put(self.undo_stack.pop())

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append((self._state(), self.sel_group, self.sel_pic))
        self._put(self.redo_stack.pop())

    def reset(self):
        if not self.changed():
            return
        self.undo_stack.append((self._state(), self.sel_group, self.sel_pic))
        self.redo_stack = []
        self._put((self.base, self.sel_group, self.sel_pic))

    def _put(self, saved):
        state, group, pic = saved
        self.groups, self.pics, self.general = copy.deepcopy(state)
        self.typing_point = False
        self.sel_group = group if group == GENERAL_ID or self._group(group) else AOTR_ID
        self.sel_pic = pic if self._pic(pic) is not None else None
        self._fill_groups()
        self._fill_pictures()
        self._show_options()
        self._show_buttons()

    # ------------------------------------------------------------ window

    def _build(self):
        app = self.app
        win = self.win = tk.Toplevel(app.root, bg=BG)
        win.title("Picture watch - Macro Recorder")
        win.attributes("-topmost", True)
        win.minsize(980, 560)
        geo = app.settings.get("picture_watch_geometry")
        win.geometry(geo if isinstance(geo, str) and geo[:1].isdigit() else "1280x740")
        if getattr(app, "icon_img", None) is not None:
            win.iconphoto(False, app.icon_img)
        win.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(win)
        style.configure("Pictures.Treeview", rowheight=34)

        # top: the chosen group's or picture's name, Undo / Redo / Reset / Apply
        top = tk.Frame(win, bg=BG)
        top.pack(fill="x", padx=14, pady=(12, 8))
        self.name_var = tk.StringVar()
        self.name_entry = tk.Entry(top, textvariable=self.name_var, bg=FIELD, fg=TEXT, font=(FAMILY, 12, "bold"),
                                   relief="flat", insertbackground=TEXT, highlightthickness=1,
                                   highlightbackground=BORDER, highlightcolor=ACCENT,
                                   disabledbackground=BG, disabledforeground=MUTED)
        self.name_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.name_var.trace_add("write", lambda *a: self._name_typed())
        self.btn_apply = ttk.Button(top, text="Apply", width=8, command=self.apply)
        self.btn_reset = ttk.Button(top, text="Reset", width=8, command=self.reset)
        self.btn_redo = ttk.Button(top, text="Redo", width=8, command=self.redo)
        self.btn_undo = ttk.Button(top, text="Undo", width=8, command=self.undo)
        for b in (self.btn_apply, self.btn_reset, self.btn_redo, self.btn_undo):
            b.pack(side="right", padx=(8, 0))
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True)
        # left: the groups
        left = tk.Frame(body, bg=BG, width=240)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(left, text="GROUPS", bg=BG, fg=MUTED, font=F_SECTION, anchor="w").pack(fill="x", padx=14,
                                                                                      pady=(12, 6))
        gbuttons = tk.Frame(left, bg=BG)
        gbuttons.pack(side="bottom", fill="x", padx=(14, 6), pady=10)
        grow1 = tk.Frame(gbuttons, bg=BG)
        grow1.pack(fill="x")
        grow2 = tk.Frame(gbuttons, bg=BG)
        grow2.pack(fill="x", pady=(6, 0))
        self.btn_new_group = ttk.Button(grow1, text="New group", command=self.new_group)
        self.btn_new_group.pack(side="left")
        self.btn_dup_group = ttk.Button(grow2, text="Duplicate", command=self.duplicate_group)
        self.btn_remove_group = ttk.Button(grow2, text="Remove", command=self.remove_group)
        for b in (self.btn_dup_group, self.btn_remove_group):
            b.pack(side="left", padx=(0, 6))
        self.groups_tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.groups_tree.pack(fill="both", expand=True, padx=(14, 6))
        self.groups_tree.tag_configure("off", foreground=DIM)
        self.groups_tree.bind("<<TreeviewSelect>>", lambda e: self._group_clicked())
        # clicking the chosen group again (while one of its pictures is chosen) shows the group's options
        self.groups_tree.bind("<ButtonRelease-1>", lambda e: self.groups_tree.identify_row(e.y) == self.sel_group
                              and self.sel_pic is not None and self.select_group(self.sel_group), add="+")
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        # middle: the pictures of the chosen group
        mid = tk.Frame(body, bg=BG, width=430)
        mid.pack(side="left", fill="y")
        mid.pack_propagate(False)
        self.pictures_title = tk.Label(mid, text="PICTURES", bg=BG, fg=MUTED, font=F_SECTION, anchor="w")
        self.pictures_title.pack(fill="x", padx=12, pady=(12, 6))
        pbuttons = tk.Frame(mid, bg=BG)
        pbuttons.pack(side="bottom", fill="x", padx=12, pady=10)
        row1 = tk.Frame(pbuttons, bg=BG)
        row1.pack(fill="x")
        row2 = tk.Frame(pbuttons, bg=BG)
        row2.pack(fill="x", pady=(6, 0))
        self.btn_from_screen = ttk.Button(row1, text="Add from screen…", command=self.add_from_screen)
        self.btn_from_file = ttk.Button(row1, text="Picture file…", command=self.add_from_file)
        self.btn_builtin = ttk.Button(row1, text="Add built-in ▾", command=self._builtin_menu)
        for b in (self.btn_from_screen, self.btn_from_file, self.btn_builtin):
            b.pack(side="left", padx=(0, 6))
        self.btn_move_pic = ttk.Button(row2, text="Move to group ▾", command=self._move_menu)
        self.btn_remove_pic = ttk.Button(row2, text="Remove", command=self.remove_picture)
        for b in (self.btn_move_pic, self.btn_remove_pic):
            b.pack(side="left", padx=(0, 6))
        self.pics_tree = ttk.Treeview(mid, show="tree", selectmode="browse", style="Pictures.Treeview")
        self.pics_tree.pack(fill="both", expand=True, padx=12)
        self.pics_tree.tag_configure("off", foreground=DIM)
        self.pics_tree.tag_configure("missing", foreground=RED)
        self.pics_tree.bind("<<TreeviewSelect>>", lambda e: self._picture_clicked())
        self.pics_tree.bind("<Delete>", lambda e: self.remove_picture())
        self._tree_tips(self.pics_tree)
        self.empty_note = tk.Label(mid, text="", bg=FIELD, fg=DIM, font=F_SMALL, justify="center", wraplength=320)
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        # right: the chosen picture's (or group's) options, scrolling when they're taller than the window
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(right, bg=BG, highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(right, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.detail = tk.Frame(self.canvas, bg=BG)
        self.detail_item = self.canvas.create_window(0, 0, window=self.detail, anchor="nw")
        self.detail.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.detail_item, width=e.width))
        win.bind("<MouseWheel>", self._wheel, add="+")
        for seq, fn in (("<Control-z>", self.undo), ("<Control-y>", self.redo), ("<Control-Z>", self.redo)):
            win.bind(seq, lambda e, fn=fn: (fn(), "break")[1] if not self._typing_in(e) else None)
        dark_title_bar(win)

    @staticmethod
    def _typing_in(event):
        return isinstance(event.widget, (tk.Entry, tk.Text, ttk.Entry, ttk.Spinbox, ttk.Combobox))

    def _wheel(self, event):
        try:
            inside = str(event.widget).startswith(str(self.canvas)) or str(event.widget).startswith(str(self.detail))
        except tk.TclError:
            return
        if inside and self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _tree_tips(self, tree):
        """Hover a picture that's grey (its group is off) or links a missing macro: a box says why."""
        tip = {"win": None, "row": None}

        def hide(_e=None):
            if tip["win"] is not None:
                try:
                    tip["win"].destroy()
                except tk.TclError:
                    pass
            tip["win"], tip["row"] = None, None

        def motion(event):
            row = tree.identify_row(event.y)
            if row == tip["row"]:
                return
            hide()
            e = self._pic(int(row)) if row.isdigit() else None
            text = self._picture_tip(e) if e else ""
            if not text:
                return
            tip["row"] = row
            w = tip["win"] = tk.Toplevel(tree)
            w.overrideredirect(True)
            w.attributes("-topmost", True)
            tk.Label(w, text=text, bg=CARD, fg=TEXT, font=F_SMALL, justify="left", wraplength=360, padx=8, pady=5,
                     highlightthickness=1, highlightbackground=BORDER).pack()
            w.geometry(f"+{event.x_root + 14}+{event.y_root + 12}")
        tree.bind("<Motion>", motion, add="+")
        tree.bind("<Leave>", hide, add="+")
        tree.bind("<Destroy>", hide, add="+")

    def _picture_tip(self, e):
        lines = []
        g = self._group(e["group"])
        if e.get("on") is not False and g is not None and g.get("on") is False:
            lines.append(f"On, but not used: the group \"{g.get('name')}\" is off.")
        gone = [m for m in e.get("macros") or [] if not os.path.isfile(m)]
        if gone:
            lines.append("Missing macro" + ("s" if len(gone) > 1 else "") + ": "
                         + ", ".join(macro_label(m) for m in gone))
        return "\n".join(lines)

    # ------------------------------------------------------------ the lists

    def _dot_color(self, on, group_on=True):
        return (GREEN if group_on else DIM) if on else RED

    def _thumb(self, file, max_w=90, max_h=26):
        key = (file, max_w, max_h)
        if key not in self.thumbs:
            try:
                pic = core.SavedPicture(os.path.join(core.watch_dir(), file), file=file)
                self.thumbs[key] = core.picture_thumb(pic, max_w, max_h)
            except Exception:
                self.thumbs[key] = (None, 0, 0)
        return self.thumbs[key]

    def _group_label(self, g):
        n = sum(1 for e in self.pics if e["group"] == g["id"])
        text = g.get("name") or "Group"
        if g.get("builtin"):
            text += " (built-in)"
        text += f"  ({n})"
        if g.get("on") is False:
            text += "  (off)"
        return text

    def _fill_groups(self):
        tree = self.groups_tree
        tree.delete(*tree.get_children())
        self.group_images = []
        img = dot_image(BORDER)
        self.group_images.append(img)
        tree.insert("", "end", iid=GENERAL_ID, text="  General  (every picture)", image=img)
        for g in self.groups:
            on = g.get("on") is not False
            img = dot_image(self._dot_color(on))
            self.group_images.append(img)
            tree.insert("", "end", iid=g["id"], text="  " + self._group_label(g), image=img,
                        tags=() if on else ("off",))
        if tree.exists(self.sel_group):
            self.filling_tree = True
            tree.selection_set(self.sel_group)
            tree.see(self.sel_group)
            self.filling_tree = False

    def _pic_label(self, e, number):
        if e.get("kind"):
            name = e.get("name") or ("Completed picture" if e["kind"] == stats.WIN else "Failed picture")
            what = "counts a win" if e["kind"] == stats.WIN else "counts a loss"
        else:
            name = e.get("name") or f"Picture {number}"
            what = action_summary(e).split("  (")[0]
        bits = [name + ("  ⓘ" if e.get("builtin") else "")]
        if e.get("on") is False:
            bits.append("(off)")
        macros = e.get("macros") or []
        if macros:
            bits.append(f"· {len(macros)} macro{'s' if len(macros) != 1 else ''}")
        return "  " + "  ".join(bits) + "\n  " + short(what, 40)

    def _fill_pictures(self):
        tree = self.pics_tree
        tree.delete(*tree.get_children())
        self.pic_images = []
        gid = self.sel_group
        self.empty_note.place_forget()
        if gid == GENERAL_ID:
            self.pictures_title.config(text="PICTURES")
            self.empty_note.config(text="General holds the options for every picture.\nChoose a group to see "
                                        "its pictures.")
            self.empty_note.place(in_=tree, relx=0.5, rely=0.3, anchor="center")
            return
        g = self._group(gid)
        self.pictures_title.config(text="PICTURES IN " + short((g or {}).get("name", "").upper(), 30))
        group_on = self._group_on(gid)
        number = 0
        for e in self.pics:
            if e["group"] != gid:
                continue
            number += 1
            on = e.get("on") is not False
            thumb, _w, _h = self._thumb(e["file"])
            img = dot_image(self._dot_color(on, group_on), thumb, height=28, thumb_w=90)
            self.pic_images.append(img)
            tags = ()
            if not on or not group_on:
                tags = ("off",)
            if any(not os.path.isfile(m) for m in e.get("macros") or []):
                tags = ("missing",)
            tree.insert("", "end", iid=str(e["_uid"]), text=self._pic_label(e, number), image=img, tags=tags)
        if not number:
            self.empty_note.config(text="No pictures in this group yet.\nAdd one from the screen, a picture "
                                        "file, or a built-in one.")
            self.empty_note.place(in_=tree, relx=0.5, rely=0.3, anchor="center")
        if self.sel_pic is not None and tree.exists(str(self.sel_pic)):
            self.filling_tree = True
            tree.selection_set(str(self.sel_pic))
            tree.see(str(self.sel_pic))
            self.filling_tree = False
        elif self.sel_pic is not None:
            self.sel_pic = None

    def _refresh_rows(self):
        """The names and dots again, without building the options again (after typing in them)."""
        if self.sel_group != GENERAL_ID:
            g = self._group(self.sel_group)
            if g is not None and self.groups_tree.exists(g["id"]):
                self.groups_tree.item(g["id"], text="  " + self._group_label(g))
        e = self._pic(self.sel_pic)
        if e is not None and self.pics_tree.exists(str(e["_uid"])):
            number = [x["_uid"] for x in self.pics if x["group"] == e["group"]].index(e["_uid"]) + 1
            self.pics_tree.item(str(e["_uid"]), text=self._pic_label(e, number))

    def select_group(self, gid):
        self.sel_group = gid if gid == GENERAL_ID or self._group(gid) else AOTR_ID
        self.sel_pic = None
        self.typing_point = False
        self._fill_groups()
        self._fill_pictures()
        self._show_options()
        self._show_buttons()

    def _group_clicked(self):
        if getattr(self, "filling_tree", False):
            return
        # (selecting in code sends this event later too: only a different group counts. Clicking the
        # group again while a picture is chosen doesn't change the selection, so it sends nothing)
        sel = self.groups_tree.selection()
        if sel and sel[0] != self.sel_group:
            self.select_group(sel[0])

    def _picture_clicked(self):
        if getattr(self, "filling_tree", False):
            return
        sel = self.pics_tree.selection()
        if not sel or not sel[0].isdigit() or int(sel[0]) == self.sel_pic:
            return
        self.sel_pic = int(sel[0])
        self.typing_point = False
        self._show_options()
        self._show_buttons()

    # ------------------------------------------------------------ the name box

    def _show_name(self):
        self.filling_name = True
        e = self._pic(self.sel_pic)
        if e is not None:
            self.name_var.set(e.get("name") or "")
            self.name_entry.config(state="normal")
        elif self.sel_group == GENERAL_ID:
            self.name_var.set("General: the options for every picture")
            self.name_entry.config(state="disabled")
        else:
            g = self._group(self.sel_group) or {}
            self.name_var.set(g.get("name", ""))
            self.name_entry.config(state="disabled" if g.get("builtin") else "normal")
        self.filling_name = False

    def _name_typed(self):
        if self.filling_name or str(self.name_entry.cget("state")) == "disabled":
            return
        text = " ".join(self.name_var.get().split())[:60]
        e = self._pic(self.sel_pic)
        target = e if e is not None else self._group(self.sel_group)
        if target is None or (e is None and target.get("builtin")):
            return
        if (target.get("name") or "") == text:
            return
        self._typing()
        if e is not None and not text:
            target.pop("name", None)
        else:
            target["name"] = text or "Group"
        self._refresh_rows()
        self._show_buttons()

    # ------------------------------------------------------------ options (right)

    def _clear_detail(self):
        self.app.capture_callback = None
        for child in self.detail.winfo_children():
            child.destroy()
        self.form = None
        self.canvas.yview_moveto(0)

    def _heading(self, text, top=14):
        tk.Label(self.detail, text=text, bg=BG, fg=MUTED, font=F_SECTION, anchor="w").pack(fill="x", padx=18,
                                                                                          pady=(top, 6))

    def _row(self, text, tip=None, parent=None):
        row = tk.Frame(parent or self.detail, bg=BG)
        row.pack(fill="x", padx=18, pady=4)
        tk.Label(row, text=text, bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
        if tip:
            tk.Label(row, text=tip, bg=BG, fg=DIM, font=F_SMALL).pack(side="left", padx=(8, 0))
        return row

    def _para(self, text, color=MUTED, parent=None):
        tk.Label(parent or self.detail, text=text, bg=BG, fg=color, font=F_SMALL, anchor="w", justify="left",
                 wraplength=440).pack(fill="x", padx=18, pady=(2, 4))

    def _show_options(self):
        self._clear_detail()
        self._show_name()
        e = self._pic(self.sel_pic)
        if e is not None:
            self._picture_options(e)
        elif self.sel_group == GENERAL_ID:
            self._general_options()
        else:
            self._group_options(self._group(self.sel_group))

    def _switch(self, row, value, on_set):
        var = tk.BooleanVar(value=value)
        Switch(row, var, command=lambda: on_set(bool(var.get()))).pack(side="right")
        return var

    def _group_options(self, g):
        if g is None:
            return
        self._heading("GROUP", top=16)
        row = self._row("On", "its pictures are used while playing")

        def set_on(on):
            self.change(lambda: g.pop("on", None) if on else g.update(on=False))
        self._switch(row, g.get("on") is not False, set_on)
        mine = [e for e in self.pics if e["group"] == g["id"]]
        on = sum(1 for e in mine if e.get("on") is not False)
        self._para(f"{len(mine)} picture{'s' if len(mine) != 1 else ''}, {on} on.")
        if g["id"] == AOTR_ID:
            self._para("The pictures that come with the app, for Attack on Titan Revolution: RETRY, Disconnected, "
                       "MISSION COMPLETED and MISSION FAILED. They're on to start with; you can turn each one "
                       "off, change what it does, or reset it to its built-in settings, but they stay in this "
                       "group. To use one in another group too, choose that group and Add built-in.", DIM)
        elif g["id"] == MINE_ID:
            self._para("Pictures you add go here unless you make your own groups. Turning a group off turns "
                       "every picture in it off at once (each picture keeps its own on/off).", DIM)
        else:
            self._para("Rename the group in the box at the top. Turning it off turns every picture in it off at "
                       "once (each picture keeps its own on/off).", DIM)

    def _general_options(self):
        gen = self.general
        self._heading("WHEN A PICTURE SHOWS", top=16)

        def on_off(key, text, tip=None):
            row = self._row(text, tip)

            def set_it(v):
                self.change(lambda: gen.__setitem__(key, v), rebuild=False)
            self._switch(row, gen[key], set_it)

        def number(key, text, tip=None, width=5):
            _k, _d, low, high, _v = next(x for x in GENERAL if x[0] == key)
            row = self._row(text, tip)
            var = tk.StringVar(value=str(gen[key]))

            def typed(*_a):
                try:
                    value = max(low, min(high, int(float(var.get().strip() or "x"))))
                except ValueError:
                    return
                if gen[key] != value:
                    self._typing()
                    gen[key] = value
                    self._show_buttons()
            box = ttk.Spinbox(row, from_=low, to=high, width=width, textvariable=var)
            box.pack(side="right")
            var.trace_add("write", typed)
            box.bind("<FocusOut>", lambda e: var.set(str(gen[key])))
            return row

        on_off("watch_click", "Click on it", "like a Retry button (a picture can choose for itself)")
        number("watch_wait", "Then wait", "seconds, before it starts the macro over")
        number("watch_match", "Match", "% for pictures to act on (85 suits most)")
        on_off("watch_ignore_bg", "Ignore the background around text")
        on_off("watch_shift_lock", "Press Shift first if the mouse pointer is hidden", "Roblox Shift Lock")
        self._heading("WHILE PLAYING")
        number("watch_end_wait", "If the macro ends before a picture shows, wait up to", "s")
        number("watch_limit_count", "Safety limit: stop if it starts over more than", "times")
        number("watch_limit_seconds", "... within", "seconds (0 times = no limit)")
        on_off("watch_save_with_macro", "Save the pictures inside the macros you save", "the ones used for it")
        self._heading("MISSION RESULTS")
        number("results_match", "Match for MISSION COMPLETED / FAILED pictures", "% (80-90 suits most)")
        self._para("Whether runs are counted at all, run stats and divine fragments are in Settings > Results.",
                   DIM)

    def _picture_options(self, e):
        app = self.app
        group_on = self._group_on(e["group"])
        # the picture itself
        top = tk.Frame(self.detail, bg=BG)
        top.pack(fill="x", padx=18, pady=(16, 4))
        thumb, w, h = self._thumb(e["file"], 420, 90)
        if thumb is not None:
            tk.Label(top, image=thumb, bg=FIELD, padx=6, pady=6).pack(anchor="w")
        line = tk.Frame(top, bg=BG)
        line.pack(fill="x", pady=(4, 0))
        tk.Label(line, text=f"{w} x {h}" + (f"  ·  taken on a {e['screen_h']}p screen" if e.get("screen_h") else ""),
                 bg=BG, fg=DIM, font=F_SMALL).pack(side="left")
        key = e.get("builtin")
        if key:
            tk.Label(line, text="  ·  built-in", bg=BG, fg=MUTED, font=F_SMALL).pack(side="left")
            link(line, "ⓘ", lambda: app.boxes.showinfo(BUILTIN_TITLES[key], BUILTIN_INFO[key], parent=self.win),
                 fg=MUTED, font=(FAMILY, 11)).pack(side="left", padx=(6, 0))
            link(line, "Reset to built-in", lambda: self.reset_builtin(e)).pack(side="right")

        row = self._row("On", "used while playing" if group_on else "but its group is off")

        def set_on(on):
            self.change(lambda: e.pop("on", None) if on else e.update(on=False))
        self._switch(row, e.get("on") is not False, set_on)

        if not key:
            row = self._row("This picture is")
            kind_var = tk.StringVar(value=KIND_CHOICES[e.get("kind")])
            box = ttk.Combobox(row, textvariable=kind_var, state="readonly", width=40, values=list(KIND_CHOICES.values()))
            box.pack(side="right")

            def kind_chosen(_e=None):
                box.selection_clear()
                kind = next(k for k, v in KIND_CHOICES.items() if v == kind_var.get())
                if kind != e.get("kind"):
                    self.change(lambda: e.update(kind=kind))
            box.bind("<<ComboboxSelected>>", kind_chosen)

        if e.get("kind"):
            self._heading("MISSION RESULT")
            self._para(("When it shows, the run counts as won." if e["kind"] == stats.WIN
                        else "When it shows, the run counts as lost.")
                       + f" Match: {self.general['results_match']}% (General, for every result picture).")
        else:
            self._heading("WHEN IT SHOWS")
            holder = tk.Frame(self.detail, bg=BG)
            holder.pack(fill="x", padx=18)
            others = [x for x in self.pics if not x.get("kind")]
            self.form = app._picture_action_form(holder, e, others, self.win, on_change=lambda: self._form_changed(e),
                                                 show_name=False, wrap=440)
        self._use_for(e)
        self._heading("TEST")
        row = tk.Frame(self.detail, bg=BG)
        row.pack(fill="x", padx=18, pady=(0, 18))
        self.test_var = tk.StringVar(value="How well it matches the screen right now")
        ttk.Button(row, text="Test now", command=lambda: self.test_picture(e)).pack(side="left")
        tk.Label(row, textvariable=self.test_var, bg=BG, fg=MUTED, font=F_SMALL).pack(side="left", padx=(10, 0))

    def _form_changed(self, e):
        if self.form is None:
            return
        new, _problem = self.form.read()
        old = {k: e.get(k) for k in new}
        cleaned = {k: (None if v in (None, "") else v) for k, v in new.items()}
        if cleaned == {k: (None if v in (None, "") else v) for k, v in old.items()}:
            return
        self._typing()
        for k, v in new.items():
            if v is None or v == "":
                e.pop(k, None)
            else:
                e[k] = v
        self._refresh_rows()
        self._show_buttons()

    def _macro_choices(self, e):
        app = self.app
        paths = list(app._saved_macro_paths())
        if app.current_file and os.path.isfile(app.current_file):
            paths.append(app.current_file)
        paths += list(e.get("macros") or [])
        seen, out = set(), []
        for p in paths:
            k = app._macro_key(p)
            if k not in seen:
                seen.add(k)
                out.append(p)
        return out

    def _use_for(self, e):
        app = self.app
        self._heading("USE FOR")
        mode = tk.StringVar(value="some" if e.get("macros") else "all")
        box = tk.Frame(self.detail, bg=BG)
        box.pack(fill="x", padx=18)
        choices = self._macro_choices(e)
        ticks = {}

        def chosen_paths():
            return [p for p in choices if ticks[p].get()]

        def set_mode():
            if mode.get() == "all":
                self.change(lambda: e.pop("macros", None))
            else:
                picked = chosen_paths() or ([app.current_file] if app.current_file else choices[:1])
                if picked:
                    self.change(lambda: e.update(macros=[os.path.abspath(p) for p in picked]))
                else:
                    mode.set("all")
                    app.boxes.showinfo("Picture watch", "Save a macro first: then this picture can be used "
                                       "only for it.", parent=self.win)

        def ticked():
            picked = chosen_paths()
            if not picked:
                self.change(lambda: e.pop("macros", None))
            else:
                self.change(lambda: e.update(macros=[os.path.abspath(p) for p in picked]))

        for value, text in (("all", "All macros"), ("some", "Only these macros")):
            tk.Radiobutton(box, text=text, value=value, variable=mode, command=set_mode, bg=BG, fg=TEXT,
                           selectcolor=FIELD, activebackground=BG, activeforeground=TEXT, font=F_BASE,
                           highlightthickness=0, bd=0).pack(anchor="w", pady=1)
        if not e.get("macros"):
            return
        lst = tk.Frame(box, bg=BG)
        lst.pack(fill="x", padx=(22, 0), pady=(2, 4))
        mine = {app._macro_key(m) for m in e.get("macros") or []}
        for p in choices:
            gone = not os.path.isfile(p)
            ticks[p] = tk.BooleanVar(value=app._macro_key(p) in mine)
            tk.Checkbutton(lst, text=macro_label(p) + ("  (missing)" if gone else ""), variable=ticks[p],
                           command=ticked, bg=BG, fg=RED if gone else TEXT, selectcolor=FIELD,
                           activebackground=BG, activeforeground=TEXT, font=F_BASE, highlightthickness=0,
                           bd=0, anchor="w").pack(fill="x")
        if any(not os.path.isfile(m) for m in e.get("macros") or []):
            self._para("A macro in red isn't there any more (moved or deleted): untick it, or put it back.", RED,
                       parent=box)

    # ------------------------------------------------------------ groups: New, Duplicate, Remove

    def _unique_group_name(self, base):
        names = {g.get("name") for g in self.groups}
        if base not in names:
            return base
        n = 2
        while f"{base} {n}" in names:
            n += 1
        return f"{base} {n}"

    def new_group(self):
        g = {"id": f"g{int(time.time() * 1000)}", "name": self._unique_group_name("New group")}

        def do():
            self.groups.append(g)
            self.sel_group, self.sel_pic = g["id"], None
        self.change(do)
        self.name_entry.focus_set()
        self.name_entry.select_range(0, "end")

    def duplicate_group(self):
        g = self._group(self.sel_group)
        if g is None:
            return
        copy_g = {"id": f"g{int(time.time() * 1000)}", "name": self._unique_group_name(g.get("name", "Group") + " copy")}
        if g.get("on") is False:
            copy_g["on"] = False

        def do():
            self.groups.insert(self.groups.index(g) + 1, copy_g)
            for e in [x for x in self.pics if x["group"] == g["id"]]:
                self.pics.append(self._with_uid(dict(copy.deepcopy(e), group=copy_g["id"])))
            self.sel_group, self.sel_pic = copy_g["id"], None
        self.change(do)

    def remove_group(self):
        g = self._group(self.sel_group)
        if g is None or fixed_group(g["id"]):
            return
        mine = [e for e in self.pics if e["group"] == g["id"]]
        if mine and not self.app.boxes.askyesno(
                "Picture watch", f"Remove the group \"{g.get('name')}\" and its {len(mine)} picture"
                f"{'s' if len(mine) != 1 else ''}?\n\n(Undo brings it back until you close the window.)",
                parent=self.win):
            return

        def do():
            self.groups.remove(g)
            self.pics[:] = [e for e in self.pics if e["group"] != g["id"]]
            self.sel_group, self.sel_pic = MINE_ID, None
        self.change(do)

    # ------------------------------------------------------------ pictures: add, remove, move

    def _target_group(self):
        return self.sel_group if self.sel_group != GENERAL_ID and self._group(self.sel_group) else MINE_ID

    def _add_entry(self, entry):
        self.new_files.add(entry["file"])
        entry.setdefault("kind", None)
        entry.setdefault("group", self._target_group())

        def do():
            self.pics.append(self._with_uid(entry))
            self.sel_group, self.sel_pic = entry["group"], entry["_uid"]
        self.change(do)

    def _picked(self, img, screen_h):
        name = f"picture_{int(time.time() * 1000)}.png"
        image_watch.save_image(os.path.join(core.watch_dir(), name), img)
        self._add_entry({"file": name, "screen_h": screen_h})

    def add_from_screen(self):
        app = self.app
        if app.recording or app.playing:
            return
        hidden = [w for w in (self.win, app.settings_win) if w is not None and w.winfo_viewable()]
        for w in hidden:
            w.withdraw()
        app.root.withdraw()
        app.root.after(300, lambda: app._show_picker(on_pick=self._picked, hidden=tuple(hidden)))

    def add_from_file(self):
        path = filedialog.askopenfilename(parent=self.win, filetypes=[("Pictures", "*.png *.jpg *.jpeg *.bmp"),
                                                                     ("All files", "*.*")])
        if not path:
            return
        try:
            self._picked(image_watch.load_image(path), None)
        except Exception as exc:
            self.app.boxes.showerror("Picture watch", f"Couldn't use that picture:\n{exc}", parent=self.win)

    def add_builtin(self, key):
        try:
            entry = self.app._builtin_entry(key, group=self._target_group())
        except OSError as exc:
            self.app.boxes.showerror("Picture watch", f"Couldn't add the built-in picture:\n{exc}", parent=self.win)
            return
        entry.setdefault("kind", None)
        self._add_entry(entry)

    def _menu(self):
        return tk.Menu(self.win, tearoff=False, bg=CARD, fg=TEXT, activebackground=ACCENT, activeforeground="white",
                       disabledforeground=DIM, font=F_BASE, bd=0, relief="flat")

    def _popup(self, menu, button):
        try:
            menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())
        finally:
            menu.grab_release()

    def _builtin_menu(self):
        menu = self._menu()
        where = (self._group(self._target_group()) or {}).get("name", "")
        for key in core.BUILTINS:
            menu.add_command(label=f"{BUILTIN_TITLES[key]}  (into {where})", command=lambda k=key: self.add_builtin(k))
        self._popup(menu, self.btn_builtin)

    def _move_menu(self):
        e = self._pic(self.sel_pic)
        if e is None:
            return
        menu = self._menu()
        stuck = e.get("builtin") and e["group"] == AOTR_ID
        for g in self.groups:
            if g["id"] == e["group"]:
                continue
            menu.add_command(label=g.get("name", "Group"), state="disabled" if stuck else "normal",
                             command=lambda gid=g["id"]: self.move_picture(gid))
        if stuck:
            menu.add_separator()
            menu.add_command(label="Built-in pictures stay in AOT:R: use Add built-in in another group", state="disabled")
        self._popup(menu, self.btn_move_pic)

    def move_picture(self, gid):
        e = self._pic(self.sel_pic)
        if e is None or (e.get("builtin") and e["group"] == AOTR_ID) or self._group(gid) is None:
            return

        def do():
            e["group"] = gid
            self.sel_group = gid
        self.change(do)

    def remove_picture(self):
        e = self._pic(self.sel_pic)
        if e is None:
            return
        if e.get("builtin") and e["group"] == AOTR_ID:
            self.app.boxes.showinfo("Picture watch", "The built-in pictures can't be removed from AOT:R. Turn it "
                                    "off instead (the switch on the right).", parent=self.win)
            return

        def do():
            self.pics.remove(e)
            self.sel_pic = None
        self.change(do)

    def reset_builtin(self, e):
        key = e.get("builtin")
        if not key or not self.app.boxes.askyesno(
                "Picture watch", f"Put {BUILTIN_TITLES[key]} back to its built-in settings? Its name and what it "
                "does when it shows go back to how they came with the app (it stays on or off, in this group, "
                "for the same macros).\n\nUndo takes it back.", parent=self.win):
            return
        _file, screen_h, kind, fields = core.BUILTINS[key]

        def do():
            keep = {k: e[k] for k in ("_uid", "file", "group", "on", "macros", "found_factor", "found_screen",
                                      "found_step") if k in e}
            e.clear()
            e.update(copy.deepcopy(fields), screen_h=screen_h, builtin=key, kind=kind, **keep)
        self.change(do)

    # ------------------------------------------------------------ Test now

    def test_picture(self, e):
        app = self.app
        try:
            pic = core.SavedPicture(os.path.join(core.watch_dir(), e["file"]), file=e["file"])
            img = pic["img"]
            screen = image_watch.grab_screen()
            origin = image_watch.screen_origin()
            screen = app._hide_own_window(screen, origin)
            # this window shows the picture itself: blacked out too
            x0 = max(0, self.win.winfo_rootx() - origin[0] - 40)
            y0 = max(0, self.win.winfo_rooty() - origin[1] - 40)
            screen[y0:y0 + self.win.winfo_height() + 80, x0:x0 + self.win.winfo_width() + 80] = 0
            if e.get("kind"):
                need = self.general["results_match"]
                base_h = e.get("screen_h") or app.screen_h
                score = max(image_watch.Matcher(img, picked_screen_h=base_h * f, ignore_background=True,
                                                screen_h=app.screen_h, work_height=core.RESULT_WORK_HEIGHT
                                                ).find(screen)[0] for f in (1.0, 1.33, 0.75))
            else:
                need = self.general["watch_match"]
                score = image_watch.Matcher(img, picked_screen_h=e.get("screen_h"),
                                            ignore_background=bool(self.general["watch_ignore_bg"]),
                                            screen_h=app.screen_h).find(screen)[0]
        except Exception as exc:
            self.test_var.set(f"Couldn't check the screen: {exc}")
            return
        pct = round(score * 100)
        self.test_var.set(f"{pct}% right now: {'seen' if pct >= need else 'not seen'} (seen from {need}%)")

    # ------------------------------------------------------------ buttons, Apply, close

    def _show_buttons(self):
        changed = self.changed()
        self.btn_undo.config(state="normal" if self.undo_stack else "disabled")
        self.btn_redo.config(state="normal" if self.redo_stack else "disabled")
        self.btn_reset.config(state="normal" if changed else "disabled")
        self.btn_apply.config(state="normal" if changed else "disabled",
                              style="Accent.TButton" if changed else "TButton")
        g = self._group(self.sel_group)
        self.btn_dup_group.config(state="normal" if g is not None else "disabled")
        self.btn_remove_group.config(state="normal" if g is not None and not fixed_group(g["id"]) else "disabled")
        e = self._pic(self.sel_pic)
        self.btn_remove_pic.config(state="normal" if e is not None and not (e.get("builtin") and e["group"] == AOTR_ID)
                                   else "disabled")
        self.btn_move_pic.config(state="normal" if e is not None else "disabled")

    def _problem(self):
        """(a picture that can't be used as it is, what's wrong) or (None, None)."""
        for e in self.pics:
            if e.get("kind") or e.get("on") is False or not self._group_on(e["group"]):
                continue
            action = e.get("action", "restart")
            if action in ("play", "switch") and not e.get("macro"):
                return e, "Choose the macro it should play first."
            if action == "key" and not e.get("key"):
                return e, "Choose the key it should press first (Change)."
        return None, None

    def apply(self):
        app = self.app
        if not self.changed():
            return True
        if app.recording or app.playing:
            app.boxes.showinfo("Picture watch", "Stop the macro first, then Apply.", parent=self.win)
            return False
        bad, problem = self._problem()
        if bad is not None:
            self.sel_group, self.sel_pic = bad["group"], bad["_uid"]
            self._fill_groups()
            self._fill_pictures()
            self._show_options()
            name = bad.get("name") or "A picture"
            app.boxes.showinfo("Picture watch", f"{name}: {problem}", parent=self.win)
            return False
        before = {e["file"] for e in self.base[1]}
        s = app.settings
        s["picture_groups"] = copy.deepcopy(self.groups)
        seen = {p["file"]: p.get("seen_rect") for p in app.watch_pictures if p.get("seen_rect")}
        watch, results = [], []
        for e in self.pics:
            clean = {k: v for k, v in e.items() if k not in ("_uid", "kind")}
            if e.get("kind"):
                clean["kind"] = e["kind"]
                results.append(clean)
            else:
                for k in ("found_factor", "found_screen", "found_step"):
                    clean.pop(k, None)
                watch.append(clean)
        s["watch_pictures"] = watch
        app.watch_pictures = []
        for entry in watch:
            pic = core.watch_picture_from(entry)
            if pic is not None:
                if pic["file"] in seen:
                    pic["seen_rect"] = seen[pic["file"]]
                app.watch_pictures.append(pic)
        s["result_pictures"] = results
        app._load_result_pictures()
        for key, _d, _l, _h, var in GENERAL:
            s[key] = self.general[key]
            if getattr(app, var, None) is not None:
                getattr(app, var).set(self.general[key])
        app._save_settings()
        core.save_settings(s, now=True)
        # picture files that were removed (or added, then removed) go now, unless something else uses them
        in_use, _own = app._pictures_in_use()
        in_use |= {e.get("confirm_file") for e in self.pics if e.get("confirm_file")}
        for name in (before | self.new_files) - in_use:
            self._delete_file(name)
        self.new_files = set()
        self.base = self._state()
        self.undo_stack, self.redo_stack = [], []
        self.typing_point = False
        app._show_picture_summary()
        app._refresh()
        self._fill_groups()
        self._fill_pictures()
        self._show_buttons()
        return True

    @staticmethod
    def _delete_file(name):
        if not name or os.path.basename(name) != name:
            return
        try:
            os.remove(os.path.join(core.watch_dir(), name))
        except OSError:
            pass

    def macro_renamed(self, key, new):
        """A macro was renamed in the Edit window: links in the window (and in its starting point) follow."""
        for pics in (self.pics, self.base[1]):
            for e in pics:
                if e.get("macros"):
                    e["macros"] = [new if self.app._macro_key(m) == key else m for m in e["macros"]]
                if e.get("macro") and self.app._macro_key(e["macro"]) == key:
                    e["macro"] = new
        self._fill_pictures()
        if self._pic(self.sel_pic) is not None:
            self._show_options()

    def close(self):
        app = self.app
        if self.changed():
            answer = app.boxes.askchoice(
                "Picture watch", "Keep the changes you made in Picture watch?",
                [("Apply", "apply"), ("Discard", "discard"), ("Cancel", None)], default="apply", parent=self.win)
            if answer is None:
                return
            if answer == "apply" and not self.apply():
                return
        # pictures added and then thrown away
        in_use, _own = app._pictures_in_use()
        for name in self.new_files - in_use:
            self._delete_file(name)
        self.new_files = set()
        try:
            app.settings["picture_watch_geometry"] = self.win.geometry()
            core.save_settings(app.settings)
        except tk.TclError:
            pass
        app.capture_callback = None
        self.win.destroy()
        app.picture_win = None
