"""Tests for which window is in front (2.9): the window you switch to comes to the front and stays
there; after picking a picture from the screen, the window it was picked from is in front again.
No real input, a throwaway settings folder."""
import os
import sys
import tempfile
import time

sys.path.insert(0, sys.argv[1])
tmp = tempfile.mkdtemp(prefix="mr_win_")
import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
import tkinter as tk  # noqa: E402

import modern_ui  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


root = tk.Tk()
app = modern_ui.ModernMacroRecorder(root)
app.kb_listener.stop()
app.mouse_listener.stop()
root.deiconify()


def pump(seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def order():
    """The app's windows from the back to the front."""
    return [str(w) for w in root.tk.splitlist(root.tk.call("wm", "stackorder", str(root)))]


def use(w):
    """Like clicking it or Alt+Tab: Windows brings it to the front and gives it the keyboard (Xvfb
    has no window manager to bring it forward, so that's done here)."""
    w.lift()
    w.focus_force()
    pump(0.3)


def above(a, b):
    o = order()
    return str(a) in o and str(b) in o and o.index(str(a)) > o.index(str(b))


use(root)
app.open_settings("Picture watch")
pump(0.5)
sett = app.settings_win
check("Settings opens in front of the main window", above(sett, root), order())
use(sett)
pw = app.open_picture_watch()
pump(0.5)
check("Picture watch opens in front of Settings", above(pw.win, sett), order())
use(root)
check("switching to the main window: it comes in front and stays there",
      above(root, sett) and above(root, pw.win), order())
pump(0.5)
check("...nothing is pushed back in front of it a moment later", above(root, sett) and above(root, pw.win), order())
use(sett)
check("switching to Settings: it comes in front of Picture watch", above(sett, pw.win) and above(sett, root), order())
use(pw.win)
check("switching to Picture watch: it comes in front again", above(pw.win, sett), order())
# after picking from the screen, the window it was picked from is in front again (not Settings)
pw.win.withdraw()
sett.withdraw()
pump(0.2)
app.window_stack.bring_back([pw.win, sett])
pump(0.4)
check("after picking: Picture watch is in front of Settings again", above(pw.win, sett), order())
pw.close()
failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)} of {len(results)} passed")
core.flush_settings()
root.destroy()
sys.exit(1 if failed else 0)
