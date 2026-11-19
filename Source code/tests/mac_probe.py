"""(2.13) Which new part makes playing freeze the window on a Mac? Each variant plays a 1-second macro in a
fresh copy of the app with one part switched off, and says whether the window kept up (on GitHub: as notes).
Not a test file (run_tests doesn't pick it up). Usage: python mac_probe.py [variant]"""
import os
import subprocess
import sys
import tempfile
import time

here = os.path.dirname(os.path.abspath(__file__))
src = os.path.dirname(here)
VARIANTS = ["all_new_parts", "no_scroll_area", "no_milestones", "no_window_size", "no_search_close",
            "no_backdrop_root", "no_front_button", "none_of_them"]


def one(variant):
    sys.path.insert(0, src)
    tmp = tempfile.mkdtemp()
    import macro_recorder as core
    core.settings_path = lambda: os.path.join(tmp, "settings.json")
    import tkinter as tk
    import ui_common
    off = set(VARIANTS[1:-1]) if variant == "none_of_them" else {variant}
    if "no_scroll_area" in off:
        class Plain(tk.Frame):
            def __init__(self, parent, bg, natural=True, on_scroll=None):
                super().__init__(parent, bg=bg)
                self.inner = self
                self.vbar = self.hbar = tk.Frame(self)

            def wheel(self, e):
                return None

            def see(self, w):
                pass
        ui_common.ScrollArea = Plain
    import modern_ui
    if "no_scroll_area" in off:
        modern_ui.ScrollArea = ui_common.ScrollArea
        import settings_pages
        settings_pages.ScrollArea = ui_common.ScrollArea
    if "no_window_size" in off:
        modern_ui.ModernMacroRecorder._keep_window_size = lambda self, *a, **k: None
    if "no_milestones" in off:
        modern_ui.ModernMacroRecorder.check_milestones = lambda self: []
    if "no_search_close" in off:
        import extras_ui
        extras_ui.ExtrasMixin._search_settings_moved = lambda self, e: None
    if "no_front_button" in off:
        ui_common.PlayOverlay.front_button = lambda self, *a, **k: None
    if "no_backdrop_root" in off:
        import backdrop
        backdrop.Backdrop._root_changed = lambda self, e: None
    import macro_steps as workflow

    root = tk.Tk()
    root.withdraw()
    app = modern_ui.ModernMacroRecorder(root)
    app.kb_listener.stop()
    app.mouse_listener.stop()
    root.withdraw()
    app._replay_event = lambda *a: None
    app.settings.update(pause_when_away=False, watch_enabled=False, results_enabled=False, drops_enabled=False)
    a = workflow.new_action("wait")
    a["seconds"] = 1
    app.set_steps([a])
    app.ready_var.set(0)
    app.loop_var.set(False)
    app.repeat_var.set(1)
    t0 = time.time()
    app.play()
    longest = 0.0
    while app.playing and time.time() - t0 < 15:
        s = time.perf_counter()
        root.update()
        longest = max(longest, time.perf_counter() - s)
        time.sleep(0.01)
    print(f"RESULT {variant}: played in {time.time() - t0:.1f} s, longest window update {longest:.2f} s")


def main():
    if len(sys.argv) > 1:
        one(sys.argv[1])
        return
    for v in VARIANTS:
        try:
            out = subprocess.run([sys.executable, os.path.abspath(__file__), v], capture_output=True, text=True,
                                 timeout=40).stdout
            line = next((l for l in out.splitlines() if l.startswith("RESULT")), f"RESULT {v}: no result")
        except subprocess.TimeoutExpired:
            line = f"RESULT {v}: FROZE (no answer within 40 s)"
        print(line, flush=True)
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::notice title=probe {v}::{line}", flush=True)


if __name__ == "__main__":
    main()
