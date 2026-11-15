"""Tests for which window stays in front (2.9): a window opened from another stays in front of it;
of two windows opened from the same one, the one used last is in front. No real input, a throwaway
settings folder."""
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
    """Like clicking it: Windows brings it to the front and gives it the keyboard (Xvfb has no window
    manager to bring it forward, so that's done here)."""
    w.lift()
    w.focus_force()
    pump(0.3)


def above(a, b):
    o = order()
    return str(a) in o and str(b) in o and o.index(str(a)) > o.index(str(b))


stack = app.window_stack
use(root)
app.open_settings("Picture watch")
pump(0.5)
sett = app.settings_win
use(sett)
pw = app.open_picture_watch()
pump(0.5)
use(pw.win)
check("Picture watch opened from Settings remembers it", stack.opener_of(str(pw.win)) == str(sett),
      (stack.opener_of(str(pw.win)), str(sett)))
check("Settings opened from the main window remembers it", stack.opener_of(str(sett)) == str(root),
      stack.opener_of(str(sett)))
use(root)
check("using the main window: Settings stays in front of it", above(sett, root), order())
check("...and Picture watch in front of Settings", above(pw.win, sett), order())
use(sett)
check("using Settings: Picture watch stays in front of it", above(pw.win, sett), order())
# a second window opened from Settings: the one used last is in front
use(sett)
other = tk.Toplevel(root)
other.title("Other")
pump(0.3)
use(other)
check("a second window from Settings remembers it", stack.opener_of(str(other)) == str(sett),
      stack.opener_of(str(other)))
check("the one in use is in front of its sibling", above(other, pw.win), order())
use(pw.win)
check("using the first one brings it in front of its sibling", above(pw.win, other), order())
use(root)
check("using the main window keeps both in front of Settings", above(pw.win, sett) and above(other, sett), order())
check("...and the one used last stays in front of its sibling", above(pw.win, other), order())
# after picking from the screen, the window it was picked from is in front again
pw.win.withdraw()
sett.withdraw()
pump(0.2)
stack.bring_back([pw.win, sett])
pump(0.4)
check("after picking: Picture watch is in front of Settings again", above(pw.win, sett), order())
other.destroy()
pw.close()
failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)} of {len(results)} passed")
core.flush_settings()
root.destroy()
sys.exit(1 if failed else 0)
