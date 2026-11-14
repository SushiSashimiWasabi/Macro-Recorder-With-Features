"""Settings: Undo / Redo / Reset / Apply (and Done while nothing changed). Opens the Settings window
off to the side; sends no input to other programs."""
import os
import sys
import tempfile
import time

src = sys.argv[1]
sys.path.insert(0, src)
tmp = tempfile.mkdtemp(prefix="mr_setundo_")
import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
import tkinter as tk  # noqa: E402

import modern_ui  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


root = tk.Tk()
root.withdraw()
app = modern_ui.ModernMacroRecorder(root)
app.kb_listener.stop()
app.mouse_listener.stop()
root.withdraw()


def pump(n=8):
    for _ in range(n):
        root.update()
        time.sleep(0.03)


pump()  # (on a first start the built-in RETRY picture is added just after the window opens)
app.open_settings("Playback")
app.settings_win.geometry("+60+60")
pump()


def shown():
    return [b.cget("text") for b in (app.btn_undo, app.btn_redo, app.btn_reset) if b.winfo_ismapped()]


check("nothing changed: only Done", app.btn_done.cget("text") == "Done" and shown() == [])
app.ready_var.set(7)
app._save_settings()
pump(20)
check("a change: Undo, Redo, Reset and Apply", app.btn_done.cget("text") == "Apply"
      and sorted(shown()) == ["Redo", "Reset", "Undo"], shown())
check("Redo off before anything was undone", str(app.btn_redo.cget("state")) == "disabled")
app.ready_var.set(9)
app._save_settings()
pump(20)
app.undo_settings_change()
pump()
check("Undo: back to 7", app.settings.get("ready_seconds") == 7, app.settings.get("ready_seconds"))
check("Redo on after Undo", str(app.btn_redo.cget("state")) == "normal")
app.redo_settings_change()
pump()
check("Redo: 9 again", app.settings.get("ready_seconds") == 9, app.settings.get("ready_seconds"))
app.undo_settings_change()
app.undo_settings_change()
pump()
check("Undo twice: back to the start", app.settings.get("ready_seconds") == 3 and app.btn_done.cget("text") == "Done",
      app.settings.get("ready_seconds"))
check("everything undone: Redo still there", "Redo" in shown())
app.redo_settings_change()
pump()
check("Redo after everything was undone", app.settings.get("ready_seconds") == 7)
app.ready_var.set(5)
app._save_settings()
pump(20)
check("a new change clears Redo", str(app.btn_redo.cget("state")) == "disabled")
app.reset_settings_changes()
pump()
check("Reset: back to the start", app.settings.get("ready_seconds") == 3 and shown() == [])
app.ready_var.set(4)
app._save_settings()
pump(20)
app.apply_settings_changes()
pump()
check("Apply: kept, buttons gone", app.settings.get("ready_seconds") == 4 and shown() == []
      and app.btn_done.cget("text") == "Done")
app.close_settings()
print()
print(f"{sum(ok for _, ok in results)} of {len(results)} passed")
root.destroy()
