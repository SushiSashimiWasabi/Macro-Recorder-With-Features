"""Security (20 Nov 2026): attacks from someone else's files, checked one by one.

1. A shared profile carries only how macros play and look (no alarm / what it opens, Discord links, screenshot
   area, trust list, hotkeys...), on export and on import. 2. Opening a shared file never switches your profile.
3. "Discord message" with a screenshot needs your OK in a macro from someone else. 4. A macro can't name a file
on another computer (\\\\server\\share). 5. A shared file only puts macro files on this PC; an AutoHotkey file can't
freeze the app with an endless loop. 7. A key goes down only while the game is in front (no moment of grace),
and the Windows key / Ctrl+Esc needs your OK. 8. Recording leaves out keys typed into other windows.

No real input is sent, no real Discord, no real message box, a throwaway settings folder."""
import json
import os
import sys
import tempfile
import threading
import time
import zipfile

src = sys.argv[1]
sys.path.insert(0, src)
tmp = tempfile.mkdtemp(prefix="mr_off_")
import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
import tkinter as tk  # noqa: E402

from pynput import keyboard  # noqa: E402

import extras_ui  # noqa: E402
import importers  # noqa: E402
import macro_steps as workflow  # noqa: E402
import modern_ui  # noqa: E402
import step_more  # noqa: E402
import window_tools  # noqa: E402

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
asked = []
for name in ("showwarning", "showinfo", "showerror"):
    setattr(app.boxes, name, lambda *a, _n=name, **k: asked.append((_n, a)))
answer = {"yes": True}
app.boxes.askyesno = lambda *a, **k: (asked.append(("askyesno", a)), answer["yes"])[1]
app.boxes.askyesnocancel = lambda *a, **k: False
window_tools.foreground = lambda: None
app.settings.update(pause_when_away=False, drops_enabled=False, discord_enabled=False)
app.result_pictures = []
app._save_settings()
app._sound = lambda name, *a, **k: None


class FakeKeys:
    def __init__(self):
        self.sent = []

    def press(self, key):
        self.sent.append(("down", key))

    def release(self, key):
        self.sent.append(("up", key))


app.kb_ctrl = FakeKeys()

# ------------------------------------------------------------ 1. what a shared profile may carry
bad = {"schedule": {"timer_on": True, "when": "game", "open": "\\\\evil.example\\s\\x.exe"},
       "startup": {"when": "play"}, "trusted_steps": {"x": ["types into notepad.exe"]},
       "discord_macro_webhook": "https://discord.com/api/webhooks/1/abc", "discord_macro_to": "webhook",
       "discord_macro_pings": True, "discord_capture": "all", "stuck_guard": {"on": True, "macro": "\\\\evil\\a.macro"},
       "hotkeys": {"play": "a"}, "pause_when_away": False, "game_closed": {"open": "calc.exe"}}
part = extras_ui.shareable(dict(bad, speed=2.0, watch_match=90))
check("shared profile: speed and picture watch options still go along", part.get("speed") == 2.0
      and part.get("watch_match") == 90, part)
check("shared profile: the alarm, start-up, trust list, Discord links / where messages go, screenshot area, stuck "
      "macro, hotkeys, 'pause when away' and 'If the game closes' never go along", not set(bad) & set(part), part)
check("shared profile: a setting nobody listed yet doesn't go along", "some_new_setting" not in
      extras_ui.shareable({"some_new_setting": 1}))
import profiles_ui  # noqa: E402

check("trust list: belongs to this PC, never to a profile", not profiles_ui.in_profile("trusted_steps"))

# ------------------------------------------------------------ 1 + 2 + 5. opening a crafted shared file
macro = {"events": [{"type": "key", "key": {"char": "a"}, "pressed": True, "t": 0.0},
                    {"type": "key", "key": {"char": "a"}, "pressed": False, "t": 0.05}],
         "screen": {"width": 1920, "height": 1080}, "profile": "Farm"}
pack = os.path.join(tmp, "gift.macropack")
manifest = {"app": "macro_recorder_pack", "version": 1, "main": "Farm.macro",
            "macros": ["Farm.macro", "Setup.exe", "Read me.lnk", "Run me.ahk"], "pictures": [],
            "profile": {"name": "Farm", "settings": dict(bad, speed=3.0)}}
with zipfile.ZipFile(pack, "w") as z:
    z.writestr("manifest.json", json.dumps(manifest))
    z.writestr("macros/Farm.macro", json.dumps(macro))
    z.writestr("macros/Setup.exe", b"MZ not a real program")
    z.writestr("macros/Read me.lnk", b"not a real shortcut")
    z.writestr("macros/Run me.ahk", b"Run, calc.exe")  # a script Windows would run when double-clicked
app.settings.pop("schedule", None)
app.settings["trusted_steps"] = {}
active_before = app.profile_active()
out = os.path.join(tmp, "packs")
os.makedirs(out)
answer["yes"] = True
main = app.import_pack(pack, folder=out)
dest = os.path.dirname(main) if main else ""
check("shared file: its macro opened", main and os.path.isfile(main), (main, asked[-3:]))
check("shared file: a program, shortcut or script inside is NOT put on this PC",
      dest and sorted(os.listdir(dest)) == ["Farm.macro"], os.listdir(dest) if dest else None)
check("shared file: opening it does NOT switch your profile", app.profile_active() == active_before,
      (app.profile_active(), active_before))
check("shared file: your alarm / trust list are untouched", "schedule" not in app.settings
      and app.settings.get("trusted_steps") == {}, (app.settings.get("schedule"), app.settings.get("trusted_steps")))
taken = app.profiles().get("Farm") or {}
check("shared file: the profile you added has its speed, but no alarm, trust list or Discord link",
      taken.get("speed") == 3.0 and "trusted_steps" not in taken
      and taken.get("schedule") != bad["schedule"] and taken.get("discord_macro_webhook") != bad["discord_macro_webhook"],
      {k: taken.get(k) for k in ("speed", "schedule", "discord_macro_webhook", "trusted_steps")})
# an older profile that still holds the trust list can't put it in place when you switch to it
app.profiles()["Old"] = dict(profiles_ui.profile_part(app.settings), trusted_steps={"evil": ["types into cmd.exe"]})
app.settings["trusted_steps"] = {"mine": ["reads the number you copy"]}
app.switch_profile("Old")
check("switching to an older profile never replaces your trust list",
      app.settings.get("trusted_steps") == {"mine": ["reads the number you copy"]}, app.settings.get("trusted_steps"))

# ------------------------------------------------------------ 4. files on another computer
looked = []
real_isfile = os.path.isfile
os.path.isfile = lambda p: (looked.append(str(p)), real_isfile(p))[1]
try:
    found = app._find_macro_file("\\\\evil.example\\share\\rejoin.macro")
    found2 = app._find_macro_file("//evil.example/share/rejoin.macro")
    other_forms = [app._find_macro_file(p) for p in ("\\\\?\\UNC\\evil.example\\share\\x.macro",
                                                     "\\??\\UNC\\evil.example\\share\\x.macro",
                                                     "\\evil.example\\share\\x.macro")]
finally:
    os.path.isfile = real_isfile
check("a macro naming a file on another computer: that computer is never asked",
      found is None and found2 is None and not any(p.replace("/", "\\").startswith("\\\\") for p in looked),
      looked)
check("... also written as \\\\?\\UNC\\, \\??\\UNC\\ or with one slash: nothing starting with a slash is looked at",
      other_forms == [None, None, None] and not any(p.replace("/", "\\").startswith("\\") for p in looked), looked)

# ------------------------------------------------------------ 3b. keys written as bigger key codes
check("the Windows key is also seen when its code is written as 65627 (cut down to 91 when sent)",
      step_more.is_win_key({"vk": 65536 + 91}) and step_more.is_win_key({"vk": 92}) and not step_more.is_win_key({"vk": 65}))
check("Ctrl and Esc too (65698 = 162, 65563 = 27); True is not a key code",
      step_more.is_ctrl_key({"vk": 65536 + 162}) and step_more.is_esc_key({"vk": 65536 + 27})
      and not step_more.is_win_key({"vk": True}))
check("a recording with the big-number Windows key needs your OK",
      step_more.SENSITIVE_WINKEY in step_more.sensitive_parts(workflow.from_events(
          [{"type": "key", "key": {"vk": 65536 + 91}, "pressed": True, "t": 0.0}])))

# ------------------------------------------------------------ 5. an AutoHotkey file that loops forever
for label, text in (("a huge empty loop", "Loop 99999999999\n{\n}\n"),
                    ("loops inside loops", "Loop 100000\n{\nLoop 100000\n{\n}\n}\n"),
                    ("an endless count", "Loop % 99999999999999 * 99999999999999 * 99999999999999 * 99999999999999 "
                                         "* 99999999999999 * 99999999999999 * 99999999999999 * 99999999999999 "
                                         "* 99999999999999 * 99999999999999 * 99999999999999 * 99999999999999 "
                                         "* 99999999999999 * 99999999999999 * 99999999999999 * 99999999999999 "
                                         "* 99999999999999 * 99999999999999 * 99999999999999 * 99999999999999 "
                                         "* 99999999999999 * 99999999999999 * 99999999999999\n{\n}\n")):
    t0 = time.time()
    err = None
    try:
        importers.import_ahk(text)
    except importers.ImportError_ as exc:
        err = exc
    except Exception as exc:  # noqa: BLE001
        err = exc
    took = time.time() - t0
    check(f"AutoHotkey file with {label}: refused in a few seconds, no freeze",
          isinstance(err, importers.ImportError_) and took < 10, (type(err).__name__, round(took, 2)))
check("AutoHotkey: a normal loop still works", len(importers.import_ahk("Loop 3\n{\nSend a\n}\n").events) == 6)


# ------------------------------------------------------------ 3 + 7. what needs your OK
def key(k, down, t=0.0):
    return {"type": "key", "key": k, "pressed": down, "t": t}


win_r = [key({"special": "cmd"}, True), key({"char": "r"}, True), key({"char": "r"}, False),
         key({"special": "cmd"}, False)]
ctrl_esc = [key({"special": "ctrl_l"}, True), key({"special": "esc"}, True), key({"special": "esc"}, False),
            key({"special": "ctrl_l"}, False)]
check("needs your OK: a recording that presses the Windows key",
      step_more.SENSITIVE_WINKEY in step_more.sensitive_parts(workflow.from_events(win_r)))
check("needs your OK: a recording that presses Ctrl+Esc",
      step_more.SENSITIVE_WINKEY in step_more.sensitive_parts(workflow.from_events(ctrl_esc)))
check("needs your OK: the Windows key as a VK number (other recorders' files)",
      step_more.SENSITIVE_WINKEY in step_more.sensitive_parts(workflow.from_events([key({"vk": 91}, True)])))
check("no OK needed: Esc alone, Ctrl+C",
      not step_more.sensitive_parts(workflow.from_events([key({"special": "esc"}, True), key({"special": "ctrl"}, True),
                                                          key({"char": "c"}, True)])))
k = workflow.new_action("key")
k.update(key={"char": "r"}, mods=["cmd"])
check("needs your OK: a Key action with the Windows key held", step_more.SENSITIVE_WINKEY in step_more.sensitive_parts([k]))
d = workflow.new_action("discord")
d.update(text="hi", screenshot=True)
s = workflow.new_action("screenshot")
s.update(to="both")
check("needs your OK: a Discord message with a screenshot, a screenshot sent to Discord",
      step_more.sensitive_parts([d]) == {step_more.SENSITIVE_SHOT} == step_more.sensitive_parts([s]))
d2 = workflow.new_action("discord")
d2.update(text="hi", screenshot=False)
check("no OK needed: a Discord message without a screenshot", not step_more.sensitive_parts([d2]))

# a macro that is only a recording (from someone else) asks at Play
app.actions = None
app.events = list(win_r)
app.current_file = os.path.join(tmp, "someone.macro")
app.settings["trusted_steps"] = {}
asked.clear()
answer["yes"] = False
app.check_sensitive()
check("a plain recording that presses the Windows key asks first", any(a[0] == "askyesno" for a in asked), asked)
check("... and with No it isn't allowed", app.allow_sensitive is False)
app.kb_ctrl.sent.clear()
held = set()
for ev in win_r:
    app._replay_event(dict(ev), held, set())
check("... then the Windows key is not pressed (R still is; letting go of a key that isn't down does nothing)",
      [s for s in app.kb_ctrl.sent if s[0] == "down" and s[1] in (keyboard.Key.cmd, keyboard.Key.cmd_l)] == []
      and any(s[0] == "down" for s in app.kb_ctrl.sent), app.kb_ctrl.sent)
app.kb_ctrl.sent.clear()
held = set()
for ev in ctrl_esc:
    app._replay_event(dict(ev), held, set())
check("... and Ctrl+Esc doesn't reach Esc", not any(s == ("down", keyboard.Key.esc) for s in app.kb_ctrl.sent),
      app.kb_ctrl.sent)
app.kb_ctrl.sent.clear()
held = set()
for ev in [key({"vk": 162}, True), key({"vk": 27}, True), key({"vk": 27}, False), key({"vk": 162}, False)]:
    app._replay_event(dict(ev), held, set())  # Ctrl+Esc written as plain key codes
check("... also when the keys are written as key codes", not any(s[0] == "down" and getattr(s[1], "vk", None) == 27 or s == ("down", keyboard.Key.esc) for s in app.kb_ctrl.sent),
      app.kb_ctrl.sent)
app.allow_sensitive = True
app.kb_ctrl.sent.clear()
app._replay_event(key({"special": "esc"}, True), set(), set())
check("Esc alone still works", app.kb_ctrl.sent == [("down", keyboard.Key.esc)], app.kb_ctrl.sent)

# ------------------------------------------------------------ 7. a key goes down only while the game is in front
front = {"hwnd": 1}
real = (window_tools.foreground, window_tools.windows_of, window_tools.exe_of, window_tools.IS_WIN)
window_tools.foreground = lambda: front["hwnd"]
window_tools.windows_of = lambda exe: [1] if exe == "Game.exe" else []
window_tools.exe_of = lambda h: "Game.exe" if h == 1 else "explorer.exe"
window_tools.IS_WIN = True
app.settings["pause_when_away"] = True
app.settings["away_stop_seconds"] = 0
app.macro_program = {"exe": "Game.exe"}
app.stop_play.clear()
try:
    watch = app._away_watcher(None)
    check("the 'game in front' check can be asked right before a key", callable(getattr(watch, "before_key", None)))
    front["hwnd"] = 2  # the Run box (explorer) just came to the front
    check("the usual check still gives windows a moment", watch(set(), set()) is False)
    threading.Timer(0.4, lambda: front.__setitem__("hwnd", 1)).start()
    t0 = time.time()
    said = watch.before_key(set(), set()) if hasattr(watch, "before_key") else "missing"
    waited = time.time() - t0
    check("right before a key: the Run box in front = playback pauses at once, until the game is back",
          said is False and waited >= 0.35, (said, round(waited, 2)))
    both = core.combine_checks(watch, lambda hk, hb: False)
    check("the check survives being combined with the stuck run guard", getattr(both, "before_key", None) is not None)

    # in playback: nothing is typed while another window is in front
    calls = []

    def away(hk, hb):
        return False

    away.before_key = lambda hk, hb: (calls.append(1), True)[1]
    app.kb_ctrl.sent.clear()
    ctx = {"speed": 1.0, "bg": None, "seen": threading.Event(), "away": away, "held": (set(), set())}
    result = app._play_events([key({"char": "x"}, True), key({"char": "x"}, False, 0.01)], ctx)
    check("playback: a key isn't sent while another window is in front (it stops / waits instead)",
          result == "stop" and not app.kb_ctrl.sent and calls, (result, app.kb_ctrl.sent))
    step = workflow.new_action("key")
    step.update(key={"char": "x"})
    app.kb_ctrl.sent.clear()
    result = app._run_step(step, ctx) if hasattr(app, "_run_step") else "missing"
    check("playback: a Key action also waits for the game", result == "stop" and not app.kb_ctrl.sent,
          (result, app.kb_ctrl.sent))
finally:
    window_tools.foreground, window_tools.windows_of, window_tools.exe_of, window_tools.IS_WIN = real
    app.settings["pause_when_away"] = False
    app.macro_program = None

# ------------------------------------------------------------ 8. recording leaves out keys typed elsewhere
front = {"hwnd": 1}
real = (window_tools.foreground, window_tools.exe_of, window_tools.pid_of, window_tools.program_info)
window_tools.foreground = lambda: front["hwnd"]
window_tools.exe_of = lambda h: {1: "Game.exe", 2: "Discord.exe", 3: "explorer.exe"}.get(h)
window_tools.pid_of = lambda h: 1000 + h
window_tools.program_info = lambda h: None
kc = keyboard.KeyCode.from_char


def start_recording(chosen=None):
    app.record_window = chosen
    app.events, app.window_samples, app.record_exe_of = [], {}, {}
    app.paused, app.paused_total, app.start_time = False, 0.0, time.perf_counter()
    app.record_exe, app.keys_down_recorded, app.keys_left_out = app._record_exe_now(), set(), 0
    app.capture_callback = None
    app.recording = True


def keys_recorded():
    return [(e["key"].get("char"), e["pressed"]) for e in app.events if e["type"] == "key"]


try:
    app.record_window = {"hwnd": 1, "title": "Game", "exe": "Game.exe"}
    check("recording: the window chosen in 'Record in which window?' decides", app._record_exe_now() == "Game.exe")
    app.record_window = {"desktop": True, "title": "the desktop"}
    check("recording on the desktop: every key counts", app._record_exe_now() is None)
    # recording starts with the desktop / taskbar in front, then you click into the game: the game decides
    front["hwnd"] = 3
    start_recording()
    app._on_key_press(kc("q"))
    app._on_key_release(kc("q"))
    front["hwnd"] = 1
    app._on_click(5, 5, __import__("pynput").mouse.Button.left, True)
    app._on_key_press(kc("e"))
    app._on_key_release(kc("e"))
    front["hwnd"] = 2
    app._on_key_press(kc("p"))
    app.recording = False
    check("recording: the desktop in front at the start doesn't decide; the first click into the game does",
          app.record_exe == "Game.exe" and keys_recorded() == [("q", True), ("q", False), ("e", True), ("e", False)],
          (app.record_exe, keys_recorded()))
    front["hwnd"] = 1
    start_recording()
    app._on_key_press(kc("w"))           # in the game (the first key decides)
    front["hwnd"] = 2                    # Discord comes to the front while W is still held
    app._on_key_press(kc("p"))           # a password letter typed in Discord
    app._on_key_release(kc("p"))
    app._on_key_release(kc("w"))         # W let go of: kept (its press was)
    front["hwnd"] = 1
    app._on_key_press(kc("s"))
    app._on_key_release(kc("s"))
    app.recording = False
    got = keys_recorded()
    check("recording: keys typed into Discord are left out, the game's keys kept (also a let-go in another window)",
          got == [("w", True), ("w", False), ("s", True), ("s", False)] and app.keys_left_out == 1,
          (got, app.keys_left_out))
    # Windows can't say which window is in front: the key is kept, and nothing breaks the keyboard hook
    def broken():
        raise OSError("no answer")

    window_tools.foreground = broken
    app.events, app.recording = [], True
    err = None
    try:
        app._on_key_press(kc("d"))
    except Exception as exc:  # noqa: BLE001
        err = exc
    check("recording: if Windows can't say which window is in front, the key is kept and nothing breaks",
          err is None and [e["key"].get("char") for e in app.events if e["type"] == "key"] == ["d"], (err, app.events))
finally:
    app.recording = False
    window_tools.foreground, window_tools.exe_of, window_tools.pid_of, window_tools.program_info = real

passed = sum(ok for _n, ok in results)
print(f"\n{passed} of {len(results)} passed")
try:
    root.destroy()
except tk.TclError:
    pass
sys.exit(0 if passed == len(results) else 1)
