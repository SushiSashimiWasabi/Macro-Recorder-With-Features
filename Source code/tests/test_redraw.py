"""The main window isn't redrawn when nothing on it changed (optimization round 3: O1 status line,
O2 the big buttons). No real input is sent, no window is shown, throwaway settings folder."""
import os
import sys
import tempfile

src = sys.argv[1]
sys.path.insert(0, src)
tmp = tempfile.mkdtemp(prefix="mr_test_")

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

# ---- O1: the same status text again doesn't redraw the window
refreshes = []
real_refresh = app._refresh
app._refresh = lambda: (refreshes.append(1), real_refresh())
for _ in range(10):
    app._set_note("Paused: the game isn't in front.")
app._process_ui_queue()
check("same note 10 times: one redraw", len(refreshes) == 1, len(refreshes))
check("note is shown", app.play_note == "Paused: the game isn't in front.")
app._set_note("Waiting for RETRY (3 s)...")
app._set_note("Waiting for RETRY (2 s)...")
app._process_ui_queue()
check("changed notes: each redraws", len(refreshes) == 3, len(refreshes))
check("last note wins", app.play_note == "Waiting for RETRY (2 s)...")
# A, B, A queued before the window gets to them: ends on A (compared on the window's thread)
app._set_note("A")
app._set_note("B")
app._set_note("A")
app._process_ui_queue()
check("A, B, A ends on A", app.play_note == "A", app.play_note)
app._refresh = real_refresh

# ---- O2: a big button only redraws when its look changes
card = app.card_play
draws = []
real_draw = card._draw
card._draw = lambda: (draws.append(1), real_draw())
card.shown = None
card.update_card("Play", "F11", enabled=True, active=False)
card.update_card("Play", "F11", enabled=True, active=False)
check("same card twice: one redraw", len(draws) == 1, len(draws))
card.update_card("Play", "F11", enabled=False, active=False)
check("disabled: redraws", len(draws) == 2 and card.label.cget("fg") == modern_ui.DIM, len(draws))
card.update_card("Play", "F10", enabled=False, active=False)
check("new key: redraws and shows it", len(draws) == 3 and card.badge.cget("text") == "F10")
card._hover(True)
check("hover still redraws", len(draws) == 4)
card._hover(False)
card._draw = real_draw
# a whole refresh with nothing changed redraws no card
app._refresh()
counts = []
for c in (app.card_record, app.card_pause, app.card_play, app.card_stop):
    c._draw = (lambda real: (lambda: (counts.append(1), real())))(c._draw)
app._refresh()
check("refresh with nothing changed: no card redraw", not counts, len(counts))

root.destroy()
failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)} of {len(results)} passed")  # (the form run_tests.py reads)
sys.exit(1 if failed else 0)
