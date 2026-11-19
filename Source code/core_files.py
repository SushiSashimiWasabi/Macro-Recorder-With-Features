"""Files: save, open, link .macro files, clear, close.

Part of the core MacroRecorder class (split out of macro_recorder.py in 2.13): its methods are
unchanged; a name that lives in macro_recorder itself is written core.name."""
import diag
import importers
import json
import os
import sys
import macro_recorder as core


class CoreFilesMixin:
    def save(self):
        if not self.events:
            core.messagebox.showinfo("Macro Recorder", "Nothing to save yet. Record something first.")
            return
        path = core.filedialog.asksaveasfilename(
            defaultextension=core.FILE_EXT, filetypes=core.FILE_TYPES, initialfile="my_macro" + core.FILE_EXT
        )
        if not path:
            return
        self._read_made_for(quiet=True)
        data = {
            "app": "macro_recorder",
            "version": core.FILE_VERSION,
            "events": self.events,  # positions as made, on the "screen" size below
        }
        if self.macro_screen:
            data["screen"] = {"width": self.macro_screen[0], "height": self.macro_screen[1]}
        with open(path, "w", encoding="utf-8") as f:
            core.dump_macro(data, f)
        self.current_file = path
        self._refresh()

    def load(self, path=None, quiet=False):
        """Open a macro file. quiet: no message boxes (an error goes to self.load_error instead).
        Returns True when the macro was opened."""
        self.load_error = None

        def fail(text):
            self.load_error = text
            if not quiet:
                core.messagebox.showerror("Macro Recorder", text)
            return False

        if self.recording or self.playing:
            return False
        if path is None:
            path = core.filedialog.askopenfilename(filetypes=core.OPEN_FILE_TYPES)
        if not path:
            return False
        imported = None
        self.file_data = {}
        steps = None
        try:
            events, screen = self._read_own_file(path)
            raw = self.file_data.get("actions")
            if isinstance(raw, list) and raw and all(isinstance(a, dict) for a in raw):
                # a macro with steps made in Edit (its recorded parts may be stored in a smaller form)
                try:
                    steps = core.expand_steps(raw)
                except (ValueError, RecursionError) as exc:
                    return fail(f"Couldn't open that file: {exc}.")
        except Exception as own_error:
            # not one of ours: try the formats of other macro recorders
            try:
                imported = importers.import_file(path)
            except importers.ImportError_ as exc:
                return fail(f"Couldn't open that file:\n{exc}")
            except Exception as exc:
                if os.path.splitext(path)[1].lower() in (core.FILE_EXT, ".json"):
                    exc = own_error
                return fail(f"Couldn't open that file:\n{exc}")
            if not imported.events:
                return fail("No actions could be read from that file.")
            events = imported.events
            events.sort(key=lambda ev: ev["t"])
            screen = {"width": imported.screen[0], "height": imported.screen[1]} if imported.screen else {}

        # positions stay as they are in the file; they're scaled from this size when playing
        try:
            made_for = (int(screen.get("width")), int(screen.get("height")))
            if made_for[0] <= 0 or made_for[1] <= 0:
                made_for = None
        except (TypeError, ValueError):
            made_for = None
        self.macro_screen = made_for
        self._show_made_for()
        program = imported.program if imported is not None else self.file_data.get("program")
        self.macro_program = program if isinstance(program, dict) else None
        # the macro's own choice for "Small random timing" and its linked profile (kept in its file)
        own = self.file_data if imported is None else {}
        self.macro_vary = own.get("vary") if isinstance(own.get("vary"), dict) else None
        self.macro_profile = own.get("profile") if isinstance(own.get("profile"), str) else None
        self.events = events
        self.actions = None
        if steps:
            self.set_steps(steps)
        self.current_file = path
        diag.info(f"Opened a macro: {len(events)} actions" + (f" ({imported.source})" if imported else ""))
        self._refresh()
        play_on = self._read_play_on(quiet=True)
        size_note = ""
        if made_for and play_on and made_for != play_on:
            size_note = (f"This macro was made for a {core.format_resolution(made_for)} screen. Mouse clicks will "
                         f"be moved to fit {core.format_resolution(play_on)} (see \"Screen size\"). "
                         "Play the game in fullscreen.")
        elif not made_for and any("x" in ev for ev in events):
            size_note = ("This file doesn't say which screen size it was made for. If it was made on a "
                         "different size than yours, pick that size in \"Macro recorded at\".")
        if quiet:
            return True
        if imported is None and size_note:
            core.messagebox.showinfo("Macro Recorder", size_note)
        if imported is not None:
            lines = [f"Opened a {imported.source} macro: {len(events)} actions, {events[-1]['t']:.1f} s."]
            if size_note:
                lines.append(size_note)
            if imported.skipped:
                lines.append(f"{imported.skipped} step(s) couldn't be converted and were left out.")
            lines.extend(dict.fromkeys(imported.notes))
            if any(ev["type"] == "move_rel" for ev in events):
                lines.append("It turns the camera with mouse movements, so play it on the whole screen, "
                             "not into a background window.")
            lines.append("Click Save... to keep it as a .macro file.")
            core.messagebox.showinfo("Macro Recorder", "\n\n".join(lines))
        return True

    def _read_own_file(self, path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("format") == "luvmacro":
            raise ValueError("a luvmacro file")
        events = data["events"]
        if not isinstance(events, list):
            raise ValueError("this isn't a macro file")
        self.file_data = data  # the rest of the file (its program, pictures to watch for)
        return core.expand_moves(events), data.get("screen", {})

    def link_file_type(self):
        """Make .macro files open with this app when double-clicked (current Windows user only)."""
        import winreg

        if getattr(sys, "frozen", False):
            command = f'"{sys.executable}" "%1"'
        else:
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if not os.path.exists(pythonw):
                pythonw = sys.executable
            command = f'"{pythonw}" "{os.path.abspath(__file__)}" "%1"'
        prog_id = "MacroRecorder.Macro"
        try:
            base = r"Software\Classes"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + "\\" + core.FILE_EXT) as k:
                winreg.SetValue(k, "", winreg.REG_SZ, prog_id)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + "\\" + prog_id) as k:
                winreg.SetValue(k, "", winreg.REG_SZ, "Macro Recorder macro")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + "\\" + prog_id + r"\shell\open\command") as k:
                winreg.SetValue(k, "", winreg.REG_SZ, command)
            import ctypes

            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # refresh file icons
        except Exception as exc:
            core.messagebox.showerror("Macro Recorder", f"Couldn't link .macro files:\n{exc}")
            return
        core.messagebox.showinfo(
            "Macro Recorder",
            "Done. Double-clicking a .macro file now opens it here.\n"
            "If you move this program, click this button again.",
        )

    def clear(self):
        if self.events and core.messagebox.askyesno("Macro Recorder", "Clear the current recording?"):
            self.events = []
            self.actions = None
            self.current_file = None
            self.macro_screen = None
            self.macro_program = None
            self._show_made_for()
            self._refresh()

    def _on_close(self):
        self._save_settings()
        core.flush_settings()
        self._stop_camera()
        self.stop_play.set()
        self.kb_listener.stop()
        self.mouse_listener.stop()
        self.root.destroy()
