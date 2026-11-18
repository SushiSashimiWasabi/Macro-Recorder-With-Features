"""2.12 preview 3: shared macros and security. Discord messages from macros don't ping unless allowed;
a macro never types into a command window (also renamed, also with a tricky title); a macro from
someone else that types into another program or reads the copied number asks once (trust is kept on
this PC only, so an edited file can't claim it); macro files from someone else are checked.

No real input is sent to any game, no real Discord, no real message box, a throwaway settings folder."""
import json
import os
import sys
import tempfile
import threading
import time

src = sys.argv[1]
sys.path.insert(0, src)
tmp = tempfile.mkdtemp(prefix="mr_sec_")
import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
import numpy as np  # noqa: E402
import tkinter as tk  # noqa: E402

import color_check  # noqa: E402
import image_watch  # noqa: E402
import macro_steps as workflow  # noqa: E402
import modern_ui  # noqa: E402
import remote_ui  # noqa: E402
import run_history  # noqa: E402
import stats  # noqa: E402
import timed_start_ui  # noqa: E402
import window_tools  # noqa: E402

results = []
known = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


def windows_only(name):
    """(2.12) A check for a feature that only exists on Windows: on other systems it's skipped (printed as
    "SKIP (Windows only)" and counted in the summary), never run."""
    if sys.platform == "win32":
        return False
    print("SKIP (Windows only) " + name)
    return True


def known_bug(name, bug_shows, info=""):
    """A bug found by the hunt, not fixed yet (waiting for Kong's OK)."""
    known.append(name)
    results.append((name, bool(bug_shows)))
    print(("PASS KNOWN BUG " if bug_shows else "FAIL FIXED (make it a normal check) ") + name
          + (f"  [{info}]" if info else ""))


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
        return None
    except Exception as exc:  # noqa: BLE001
        return exc


root = tk.Tk()
root.withdraw()
app = modern_ui.ModernMacroRecorder(root)
app.kb_listener.stop()
app.mouse_listener.stop()
root.withdraw()
asked = []
for name in ("showwarning", "showinfo", "showerror"):
    setattr(app.boxes, name, lambda *a, _n=name, **k: asked.append((_n, a)))
app.boxes.askyesno = lambda *a, **k: True
app.boxes.askyesnocancel = lambda *a, **k: False
modern_ui.messagebox.showwarning = lambda *a, **k: asked.append(("warning", a))
window_tools.foreground = lambda: None
app.settings.update(pause_when_away=False, drops_enabled=False, discord_enabled=False)
app.away_var.set(False)
app.watch_var.set(False)
app.result_pictures = []
app._save_settings()
app._sound = lambda name, *a, **k: None


def pump(seconds=0.1):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)



# ------------------------------------------------------------ the new actions: trying to break them
import step_more  # noqa: E402

app.result_matchers = []
app.ready_var.set(0)
app.loop_var.set(False)
app.repeat_var.set(1)
sent_new = []
real_replay = app._replay_event
app._replay_event = lambda e, hk, hb: sent_new.append(e)
real_windows, real_front = window_tools.windows_of, window_tools.force_to_front
window_tools.windows_of = lambda exe: []
window_tools.force_to_front = lambda hwnd: True


def play_steps(steps):
    sent_new.clear()
    app.stop_reason = None
    app.set_steps(steps)
    app.play()
    t0 = time.time()
    while app.playing and time.time() - t0 < 20:
        pump(0.03)
    pump(0.1)


def new(kind, **kw):
    a = workflow.new_action(kind)
    a.update(kw)
    return a



# ------------------------------------------------------------ (fixed) pings from macros
ping_text = step_more.no_pings("@everyone free robux @here <@123456> <@&42> <@!7> mail me@here.com")
check("pings: @everyone, @here, <@user> and <@&role> no longer ping", "@everyone" not in ping_text
      and "@here " not in ping_text and "<@1" not in ping_text and "<@&" not in ping_text and "<@!" not in ping_text
      and "me@here.com" in ping_text, ping_text)
check("pings: @EVERYONE in capitals too", "@EVERYONE" not in step_more.no_pings("@EVERYONE"))
posted = []
real_notifier_cls = __import__("discord_notify").Notifier


class _FakeNotifier:
    def __init__(self, get_url, **kw):
        pass

    def send(self, text, png=None, **kw):
        posted.append(text)
        return True


__import__("discord_notify").Notifier = _FakeNotifier
app.macro_notifier = None
app.settings.update(discord_macro_to="webhook", discord_macro_pings=False,
                    discord_macro_webhook="https://discord.com/api/webhooks/123456789012345678/" + "y" * 60)
app._macro_discord("@everyone look")
check("pings: off (as at first): a macro's message doesn't ping", posted and "@everyone" not in posted[-1], posted)
app.settings["discord_macro_pings"] = True
app._macro_discord("@everyone look")
check("pings: 'Allow pings in macro messages' on: it pings", posted[-1] == "@everyone look")
app.settings["discord_macro_pings"] = False
api_calls = []
import discord_remote  # noqa: E402
real_api = discord_remote.api
discord_remote.api = lambda method, url, payload=None, **kw: api_calls.append(payload)
app._post_to_channel("123456789012345678", "token", "hi", None, False)
discord_remote.api = real_api
check("pings: the bot's channel message also tells Discord to ping nobody", api_calls
      and api_calls[-1]["allowed_mentions"] == {"parse": []}, api_calls)
__import__("discord_notify").Notifier = real_notifier_cls
app.macro_notifier = None
app.settings.update(discord_macro_to="cards", discord_macro_webhook="")

# ------------------------------------------------------------ (fixed) never typing into a command window
import shutil  # noqa: E402

for exe in ("cmd.exe", "CMD.EXE", "powershell.exe", "pwsh.exe", "WindowsTerminal.exe", "regedit.exe", "mmc.exe",
            "explorer.exe"):
    if not window_tools.never_type_into(exe=exe):
        check(f"command windows: {exe} is refused", False)
        break
else:
    check("command windows: cmd, PowerShell, Terminal, regedit, mmc, the Run box (explorer) are refused", True)
t = step_more.clean_step({"kind": "type", "text": "del /q *\n", "window": {"exe": "C:\\x\\CMD.exe", "title": ""}})
check("command windows: a shared step naming cmd.exe loses its target", t.get("window") is None, t)
if sys.platform == "win32":  # (cmd.exe, PowerShell and console windows only exist on Windows)
    renamed = os.path.join(tmp, "notepad2.exe")
    shutil.copyfile(os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "cmd.exe"), renamed)
    real_path_of, real_class_of = window_tools.exe_path_of, window_tools.class_of
    window_tools.exe_path_of = lambda hwnd: renamed
    window_tools.class_of = lambda hwnd: "Notepad"
    check("bypass: cmd.exe renamed to notepad2.exe is still refused (by the name it was built with)",
          window_tools.never_type_into(12345))
    window_tools.exe_path_of = lambda hwnd: os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "notepad.exe")
    window_tools.class_of = lambda hwnd: "ConsoleWindowClass"
    check("bypass: any console window is refused, whatever its program is called", window_tools.never_type_into(12345))
    window_tools.class_of = lambda hwnd: "Notepad"
    window_tools.exe_path_of = lambda hwnd: os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32",
                                                         "WindowsPowerShell", "v1.0", "powershell.exe")
    real_title_of = window_tools.title_of
    window_tools.title_of = lambda hwnd: "Untitled - Notepad"
    check("bypass: a PowerShell window titled 'Untitled - Notepad' is refused (title doesn't count)",
          window_tools.never_type_into(12345))
    window_tools.windows_of = lambda exe: [12345]
    window_tools.force_to_front = lambda hwnd: True
    sent_new.clear()
    app.allow_sensitive = True
    app._more_type(new("type", text="evil", window={"exe": "notepad.exe", "title": ""}),
                   {"speed": 1, "bg": None, "held": (set(), set()), "seen": threading.Event(), "away": None})
    check("bypass: a step that says notepad.exe but finds a PowerShell window types nothing", not sent_new)
    window_tools.exe_path_of = lambda hwnd: os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "notepad.exe")
    check("a real notepad.exe is fine", not window_tools.never_type_into(12345))
    window_tools.exe_path_of, window_tools.class_of, window_tools.title_of = real_path_of, real_class_of, real_title_of
else:
    print("SKIP (Windows only) bypass: cmd.exe renamed to notepad2.exe is still refused (by the name it was built with)")
    print("SKIP (Windows only) bypass: any console window is refused, whatever its program is called")
    print("SKIP (Windows only) bypass: a PowerShell window titled 'Untitled - Notepad' is refused (title doesn't count)")
    print("SKIP (Windows only) bypass: a step that says notepad.exe but finds a PowerShell window types nothing")
    print("SKIP (Windows only) a real notepad.exe is fine")
# ------------------------------------------------------------ (fixed) macros from someone else ask once
asked_sens = []
app.boxes.askyesno = lambda *a, **k: (asked_sens.append(a), answer["v"])[1]
answer = {"v": False}
shared = os.path.join(tmp, "From a friend.macro")
steps_shared = [new("read_clipboard", counter="C"), new("type", text="{C}", window={"exe": "notepad.exe", "title": ""})]
with open(shared, "w", encoding="utf-8") as f:
    core.dump_macro({"app": "macro_recorder", "version": core.FILE_VERSION, "events": [], "actions": steps_shared,
                     "trusted_steps": True, "own": True, "trusted": ["types into notepad.exe"]}, f)
app.settings["trusted_steps"] = {}
app.load(shared, quiet=True)
check("someone else's macro: asks once before it types into notepad / reads the copied number",
      app.check_sensitive() is False and asked_sens and "types into notepad.exe" in asked_sens[-1][1]
      and "reads the number you copy" in asked_sens[-1][1], asked_sens[-1:])
check("bypass: a file that says it's trusted / your own still asks (trust is kept on this PC only)",
      len(asked_sens) == 1)
clip_reads = []
real_read = step_more.read_clipboard_text
step_more.read_clipboard_text = lambda: (clip_reads.append(1), "5")[1]
app.counters = {}
app._more_read_clipboard(new("read_clipboard", counter="C"), {"speed": 1})
check("No: the copied number isn't read", not clip_reads and "C" not in app.counters)
answer["v"] = True
asked_sens.clear()
check("Yes: allowed", app.check_sensitive() is True and len(asked_sens) == 1)
asked_sens.clear()
check("Yes is remembered: no question next time", app.check_sensitive() is True and not asked_sens)
with open(shared, "w", encoding="utf-8") as f:
    core.dump_macro({"app": "macro_recorder", "version": core.FILE_VERSION, "events": [],
                     "actions": steps_shared + [new("type", text="x", window={"exe": "calc.exe", "title": ""})]}, f)
app.load(shared, quiet=True)
answer["v"] = False
check("bypass: the same file changed to type into another program asks again", app.check_sensitive() is False
      and asked_sens and "calc.exe" in asked_sens[-1][1] and "notepad" not in asked_sens[-1][1], asked_sens[-1:])
app.boxes.quiet = []
asked_sens.clear()
real_box = app.boxes.askyesno
del app.boxes.askyesno
check("nobody at the PC (Discord / timed start): not allowed, no question waits", app.check_sensitive() is False
      and app.boxes.quiet and "calc.exe" in app.boxes.quiet[-1])
app.boxes.askyesno = real_box
app.boxes.quiet = None
# what you add in Edit yourself is yours
mine = os.path.join(tmp, "Mine2.macro")
with open(mine, "w", encoding="utf-8") as f:
    core.dump_macro({"app": "macro_recorder", "version": core.FILE_VERSION, "events": [],
                     "actions": [new("wait", seconds=0.01)]}, f)
app.load(mine, quiet=True)
app.open_editor()
ed = app.macro_editor
pump(0.2)
ed.steps.append(new("type", text="hi", window={"exe": "notepad.exe", "title": ""}))
ed.apply()
asked_sens.clear()
answer["v"] = False
check("what you add in Edit yourself doesn't ask", app.check_sensitive() is True and not asked_sens)
ed.win.destroy()
step_more.read_clipboard_text = real_read
app.boxes.askyesno = lambda *a, **k: True
window_tools.windows_of, window_tools.force_to_front = real_windows, real_front
app._replay_event = real_replay

passed = sum(1 for _n, ok in results if ok)
print(f"\nKnown bugs still there: {len(known)}")
print(f"\n{passed} of {len(results)} passed")
root.destroy()
sys.exit(0 if passed == len(results) else 1)
