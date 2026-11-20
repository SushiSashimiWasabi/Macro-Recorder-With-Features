"""Macro folders and tags (Preview 4): the saved macros can be put in folders and get tags, shown in the
Edit window's MACROS list (with a filter box), and the main window's ◀ ▶ row can go through one folder only.

Only this app's settings change: settings["macro_meta"] = {file key: {"folder", "tags"}} and
settings["macro_folders"] (folders, also empty ones). The .macro files never move and keep no folder."""
import os
import tkinter as tk

import folder_rules
import macro_recorder as core
from ui_common import ACCENT, PANEL, TEXT

from folder_rules import clean_name, clean_tags


class MacroFoldersMixin:
    @staticmethod
    def _meta_key(path):
        return os.path.normcase(os.path.abspath(path)) if path else ""

    def _meta_store(self):
        store = self.settings.get("macro_meta")
        if not isinstance(store, dict):
            store = self.settings["macro_meta"] = {}
        return store

    def prune_meta(self):
        """Folder and tags of macros that are gone (not in the list and no file) are forgotten."""
        store = self._meta_store()
        keep = {self._meta_key(p) for p in self.macro_list()}
        gone = [k for k in store if k not in keep and not os.path.exists(k)]
        for k in gone:
            del store[k]
        if gone:
            core.save_settings(self.settings)

    def macro_meta(self, path):
        """{"folder": "" or a name, "tags": [..]} of a saved macro."""
        return folder_rules.clean_meta(self._meta_store().get(self._meta_key(path)))

    def _put_meta(self, path, meta):
        store = self._meta_store()
        key = self._meta_key(path)
        meta = {k: v for k, v in meta.items() if v}
        if meta:
            store[key] = meta
        else:
            store.pop(key, None)

    def macro_folders(self):
        """Every folder: the ones made (also empty) and the ones macros are in, A to Z."""
        return folder_rules.folders(self.settings.get("macro_folders"), self._folders_in_use())

    def _folders_in_use(self):
        return {self.macro_meta(p)["folder"] for p in self.macro_list()}

    def make_folder(self, name):
        made, shown = folder_rules.add_folder(self.settings.get("macro_folders"), name, self._folders_in_use())
        if shown is not None:
            self.settings["macro_folders"] = made
        return shown

    def set_macro_folder(self, paths, folder):
        """Put macros in a folder ("" = no folder). False when the folder can't be made (nothing changes)."""
        folder = self.make_folder(folder) if folder else ""
        if folder is None:
            return False
        for path in paths:
            meta = self.macro_meta(path)
            meta["folder"] = folder or ""
            self._put_meta(path, meta)
        core.save_settings(self.settings)
        self._show_macro_list()

    def set_macro_tags(self, path, tags):
        meta = self.macro_meta(path)
        meta["tags"] = clean_tags(tags)
        self._put_meta(path, meta)
        core.save_settings(self.settings)

    def rename_folder(self, old, new):
        new = clean_name(new)
        if not new or not old:
            return False
        for path in self.macro_list():
            meta = self.macro_meta(path)
            if meta["folder"] == old:
                meta["folder"] = new
                self._put_meta(path, meta)
        self.settings["macro_folders"] = folder_rules.renamed(self.settings.get("macro_folders"), old, new)
        if self.settings.get("macro_row_folder") == old:
            self.settings["macro_row_folder"] = new
        core.save_settings(self.settings)
        self._show_macro_list()
        return True

    def remove_folder(self, name):
        """The folder goes; its macros stay (with no folder)."""
        for path in self.macro_list():
            meta = self.macro_meta(path)
            if meta["folder"] == name:
                meta["folder"] = ""
                self._put_meta(path, meta)
        self.settings["macro_folders"] = folder_rules.removed(self.settings.get("macro_folders"), name)
        if self.settings.get("macro_row_folder") == name:
            self.settings["macro_row_folder"] = ""
        core.save_settings(self.settings)
        self._show_macro_list()

    def meta_renamed(self, old_path, new_path):
        """A macro renamed in Edit keeps its folder and tags."""
        store = self._meta_store()
        old = store.pop(self._meta_key(old_path), None)
        if old:
            store[self._meta_key(new_path)] = old

    def macro_matches(self, path, query):
        """The Edit filter: every word is in the name, the folder or a tag ("#farm" = only tags)."""
        return folder_rules.matches(os.path.splitext(os.path.basename(path or ""))[0], self.macro_meta(path), query)

    # ------------------------------------------------------------ the main window's ◀ ▶ row

    def row_folder(self):
        f = clean_name(self.settings.get("macro_row_folder"))
        return f if f in self.macro_folders() else ""

    def row_macros(self):
        """The saved macros ◀ ▶ goes through: all of them, or only one folder's."""
        lib = self.macro_list()
        f = self.row_folder()
        return [p for p in lib if self.macro_meta(p)["folder"] == f] if f else list(lib)

    def _row_folder_menu(self):
        m = tk.Menu(self.root, tearoff=False, bg=PANEL, fg=TEXT, activebackground=ACCENT,
                    activeforeground="white")
        now = self.row_folder()
        m.add_command(label=("● " if not now else "   ") + "All saved macros", command=lambda: self._set_row_folder(""))
        folders = self.macro_folders()
        if folders:
            m.add_separator()
        for f in folders:
            n = sum(1 for p in self.macro_list() if self.macro_meta(p)["folder"] == f)
            m.add_command(label=("● " if f == now else "   ") + f"{f}  ({n})", command=lambda f=f: self._set_row_folder(f))
        if not folders:
            m.add_command(label="   (Make folders in Edit: right-click a macro)", state="disabled")
        w = self.row_folder_link
        m.tk_popup(w.winfo_rootx(), w.winfo_rooty() + w.winfo_height())

    def _set_row_folder(self, folder):
        self.settings["macro_row_folder"] = folder
        core.save_settings(self.settings)
        self._show_macro_list()
