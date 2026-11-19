"""What the app remembers about a saved macro, in one place (2.13 review, candidate B).

A saved macro has data kept for it in several places: its folder and tags (macro_folders), its older
versions (macro_versions), its turned-off warnings (check_ui), the pictures that use or play it
(picture_window) and the steps you OK'd (step_more). Callers say only what happened to the macro:

    app.macro_renamed(old_path, new_path)   everything follows the new name
    app.macro_gone(path)                    what is kept for that exact path is forgotten

(Older versions and turned-off warnings are kept by macro NAME, not by path, so another macro of the same
name may share them: they are not forgotten when one file is gone.)"""
import os

import macro_versions


class MacroRecordsMixin:
    def macro_renamed(self, old_path, new_path):
        """A saved macro got a new file name: everything kept for it goes along."""
        if os.path.normcase(os.path.abspath(old_path)) == os.path.normcase(os.path.abspath(new_path)):
            return
        macro_versions.renamed(old_path, new_path)
        self.meta_renamed(old_path, new_path)
        self.rename_check_ignored(macro_versions._key(old_path), macro_versions._key(new_path))
        self._pictures_macro_renamed(old_path, new_path)
        old_key, new_key = self._macro_key(old_path), self._macro_key(new_path)
        trusted = self._trusted()
        if old_key in trusted and new_key != old_key:
            self.trust_steps(new_key, trusted[old_key])

    def macro_gone(self, path):
        """A saved macro's file is gone: what is kept for that exact path (folder, tags, OK'd steps) goes too."""
        self._meta_store().pop(self._meta_key(path), None)
        self._trusted().pop(self._macro_key(path), None)
