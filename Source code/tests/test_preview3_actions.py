"""2.12 preview 3: the new Edit actions (Do maths, Read the copied number, Type into a window, Discord
message, sound, Set speed, game to the front, Label / Go to, screenshot, Wait a random time, Else) and the
new options of the old ones (key combos, click offset / where found / random, glide, AND / OR, counter /
program / time conditions, Repeat until, Retry if it fails, Stop with a reason, Note on the timer).

The owner's own use is played end to end: read the copied number -> Total = Total + Copied -> type {Total} into
Notepad (paste) -> Go to the start. Everything uses stand-ins: nothing is typed or clicked for real, the
clipboard and the windows are pretend, no real Discord, a throwaway settings folder."""
import json
import os
import sys
import tempfile
import threading
import time

src = sys.argv[1]
sys.path.insert(0, src)
tmp = tempfile.mkdtemp(prefix="mr_p3a_")
import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
import tkinter as tk  # noqa: E402

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
app.boxes.askyesno = lambda *a, **k: True
app.boxes.askyesnocancel = lambda *a, **k: False
modern_ui.messagebox.showwarning = lambda *a, **k: asked.append(("warning", a))
window_tools.foreground = lambda: None
app.settings.update(pause_when_away=False, drops_enabled=False, discord_enabled=False)
app.away_var.set(False)
app.watch_var.set(False)
app.result_pictures = []
app.switch_prog_var.set(False)
app.ready_var.set(0)
app.recover_count_var.set(0)
app.loop_var.set(False)
app.repeat_var.set(1)
app._save_settings()
played_sounds = []
app._sound = lambda name, *a, **k: played_sounds.append(name)
sent = []
app._replay_event = lambda e, hk, hb: sent.append(e)
app._click_at = lambda x, y: sent.append({"type": "click_at", "x": x, "y": y})
discord = []
app._macro_discord_real = app._macro_discord


def pump(seconds=0.1):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def wait_play(limit=20):
    t0 = time.time()
    while app.playing and time.time() - t0 < limit:
        pump(0.03)
    pump(0.1)


def step(kind, **kw):
    a = workflow.new_action(kind)
    a.update(kw)
    return a


def play(steps):
    sent.clear()
    app.stop_reason = None
    app.set_steps(steps)
    app.play()
    wait_play()


def log_text():
    path = core.diag.log_path()
    return open(path, encoding="utf-8").read() if path else ""


# ------------------------------------------------------------ the copied number, maths and typing: the owner's loop
clip = {"text": "12", "writes": []}
step_more.read_clipboard_text = lambda: clip["text"]
step_more.write_clipboard_text = lambda t: (clip["writes"].append(t), True)[1]
fronted = []
window_tools.windows_of = lambda exe: [4242] if exe and exe.lower() == "notepad.exe" else []
window_tools.force_to_front = lambda hwnd: (fronted.append(hwnd), True)[1]
window_tools.title_of = lambda hwnd: "Untitled - Notepad"
loop = [step("label", name="Start"),
        step("read_clipboard", counter="Copied"),
        step("maths", counter="Total", a={"counter": "Total"}, op="+", b={"counter": "Copied"}),
        step("type", text="{Total}", how="paste", enter=True, window={"exe": "notepad.exe", "title": "Notepad"}),
        step("goto", label="Start", limit=3)]
play(loop)
typed = [w for w in clip["writes"] if w != "12"]
check("The owner's loop: copied 12, Total goes 12, 24, 36, 48 and each is pasted into Notepad",
      typed == ["12", "24", "36", "48"] or [w for w in clip["writes"][::2]] == ["12", "24", "36", "48"],
      clip["writes"])
check("The owner's loop: Notepad was brought to the front each time (and the window before it came back)",
      fronted.count(4242) == 4, fronted)
check("The owner's loop: pasted with Ctrl+V, then Enter", any(e.get("key", {}).get("char") == "v" for e in sent)
      and any(e.get("key", {}).get("special") == "enter" for e in sent))
check("The owner's loop: what you had copied is put back after pasting", clip["writes"][1::2] == ["12"] * 4,
      clip["writes"])
check("The owner's loop: Go to stops at its limit (3 jumps a run) and says why",
      app.stop_reason and "jumped 3 times" in app.stop_reason, app.stop_reason)
check("The owner's loop: the timer shows the sum like 'Total: 36+12=48'", app.timer_text == "Total: 36+12=48",
      app.timer_text)
lt = log_text()
check("The owner's loop: the copied text is never written to the log", "Read the copied number into \"Copied\"" in lt
      and "copied number into \"Copied\": 12" not in lt)

# ------------------------------------------------------------ Do maths
app.counters = {"Items": 4}
app.timer_text = None
ctx = {"speed": 1.0}
app._more_maths(step("maths", counter="Total", a={"number": 1}, op="+", b={"counter": "Items"}), ctx)
check("maths: 1 + Items (4) = 5, shown as 'Total: 1+4=5'", app.counters["Total"] == 5
      and app.timer_text == "Total: 1+4=5", (app.counters, app.timer_text))
app._more_maths(step("maths", counter="Total", a={"number": 7}, op="/", b={"number": 2}), ctx)
check("maths: whole numbers: 7 ÷ 2 = 3 (rounds down)", app.counters["Total"] == 3)
app._more_maths(step("maths", counter="Total", a={"number": 7}, op="/", b={"number": 2}, decimals=2), ctx)
check("maths: 2 decimals: 7 ÷ 2 = 3.5", app.counters["Total"] == 3.5)
app._more_maths(step("maths", counter="Total", a={"number": 1}, op="/", b={"number": 3}, decimals=2), ctx)
check("maths: 2 decimals: 1 ÷ 3 = 0.33", app.counters["Total"] == 0.33)
app._more_maths(step("maths", counter="Total", a={"number": 5}, op="/", b={"number": 0}), ctx)
check("maths: ÷ 0 keeps the value and the log says so", app.counters["Total"] == 0.33
      and "can't divide by 0" in log_text())
app._more_maths(step("maths", counter="Big", a={"number": 999999999}, op="*", b={"number": 999999999}), ctx)
check("maths: huge results stop at 1,000,000,000", app.counters["Big"] == 10 ** 9)
app._more_maths(step("maths", counter="Neg", a={"number": -5}, op="-", b={"counter": "Nobody"}), ctx)
check("maths: a counter that isn't set counts as 0 (and is logged)", app.counters["Neg"] == -5
      and "Counter \"Nobody\" isn't set yet" in log_text())
check("maths: 'Total: 1+4=5' style for decimals too", step_more.fmt(3.5) == "3.5" and step_more.fmt(3.0) == "3"
      and step_more.fmt(0.33) == "0.33")

# ------------------------------------------------------------ the copied number
cases = {"12": 12, " 1,234 ": 1234, "1,234.5": 1234.5, "1.234,5": 1234.5, "-12": -12, "3,5": 3.5,
         "1.000.000": 1000000, "abc": None, "12 apples": None, "": None, "1e9": None, "99999999999": None,
         "١٢": 12, "+7": 7, "0.005": 0.01}
got = {k: step_more.parse_copied(k) for k in cases}
check("copied number: only numbers count (commas, dots, signs)", got == cases,
      {k: (v, cases[k]) for k, v in got.items() if v != cases[k]})
app.counters = {"Copied": 5}
clip["text"] = "not a number"
app._more_read_clipboard(step("read_clipboard", counter="Copied"), ctx)
check("copied number: text that isn't a number leaves the counter as it was", app.counters["Copied"] == 5
      and "isn't a number, so \"Copied\" stays" in log_text())

# ------------------------------------------------------------ Else, AND / OR, counter / program / time
app.counters = {"Wins": 2}
seq = [step("if_counter", counter="Wins", at_least=5, actions=[step("key", key={"vk": 65})]),
       step("else", actions=[step("key", key={"vk": 66})])]
play(seq)
check("Else: runs when the If wasn't true", [e["key"]["vk"] for e in sent if e.get("pressed")] == [66],
      [e.get("key") for e in sent])
app.counters = {}
seq = [step("counter_set", counter="Wins", value=9),
       step("if_counter", counter="Wins", at_least=5, actions=[step("key", key={"vk": 65})]),
       step("else", actions=[step("key", key={"vk": 66})])]
play(seq)
check("Else: skipped when the If was true", [e["key"]["vk"] for e in sent if e.get("pressed")] == [65])
play([step("else", actions=[step("key", key={"vk": 67})])])
check("Else: on its own (no If before it) never runs", not sent)
app.counters = {"A": 3, "B": 3}
t = time.strftime("%H:%M")
cond = {"type": "counter", "counter": "A", "op": "==", "other": "B", "join": "and",
        "more": [{"type": "time", "from": "00:00", "to": "23:59"}]}
check("If: counter = another counter AND the time of day", app._condition_all(cond) is True)
cond["more"][0] = {"type": "time", "from": "23:59", "to": "00:00"}
check("If: AND is false when one part is false", app._condition_all(cond) is False
      or t == "23:59")
cond["join"] = "or"
check("If: OR is true when one part is true", app._condition_all(cond) is True)
check("time of day: across midnight", step_more.in_time("23:30", "22:00", "02:00")
      and step_more.in_time("01:00", "22:00", "02:00") and not step_more.in_time("12:00", "22:00", "02:00"))
check("If: a program is open / isn't open", app._condition_one({"type": "window", "program": {"exe": "notepad.exe"}})
      and app._condition_one({"type": "window", "program": {"exe": "nothere.exe"}, "shows": False}))
for op, want in ((">=", True), ("<=", True), (">", False), ("<", False), ("!=", False), ("==", True)):
    if app._condition_one({"type": "counter", "counter": "A", "op": op, "value": 3}) != want:
        check(f"If: counter {op} 3", False)
        break
else:
    check("If: counters with = ≥ ≤ ≠ > <", True)
app.counters = {"N": 0}
seq = [step("repeat", mode="until", condition={"type": "counter", "counter": "N", "op": ">=", "value": 4},
            actions=[step("counter_add", counter="N")])]
play(seq)
check("Repeat until a counter reaches 4", app.counters.get("N") == 4, app.counters)
seq = [step("repeat", mode="forever", actions=[step("note", text="x")])]
play(seq)
check("Repeat until stopped: a loop where no time passes is stopped (endless loop)",
      app.stop_reason and "endless loop" in app.stop_reason, app.stop_reason)

# ------------------------------------------------------------ Retry, Stop, Note, Wait random, Set speed
app.counters = {}
seq = [step("retry", tries=2, check=0, condition={"type": "counter", "counter": "X", "op": ">=", "value": 9},
            if_fails="stop", actions=[step("counter_add", counter="X")])]
play(seq)
check("Retry: if every try fails, Stop (with the reason)", app.stop_reason and "2 tries" in app.stop_reason
      and app.counters.get("X") == 2, (app.stop_reason, app.counters))
play([step("stop", reason="out of potions", ping=False)])
check("Stop with a reason: in the reason / log", app.stop_reason == "Stopped by the macro: out of potions")
discord.clear()
app._macro_discord = lambda text, png=None, to="default", channel=None, ping=False: (discord.append((text, ping)), True)[1]
play([step("stop", reason="out of potions", ping=True)])
check("Stop with ping: Discord is told, with a ping", discord and discord[-1][1] is True and "potions" in discord[-1][0])
app.timer_text = None
play([step("note", text="Farming the left side", show=True), step("wait", seconds=0.05)])
check("Note: shown on the timer while it plays", app.timer_text == "Farming the left side")
waits = []
real_pause = app._pause
app._pause = lambda s, ctx: (waits.append(s), "ok")[1]
for _ in range(30):
    app._more_wait_random(step("wait_random", seconds=1, max=3), {"speed": 1.0, "held": (set(), set())})
app._pause = real_pause
check("Wait a random time: always between the two numbers, and not always the same",
      all(1 <= w <= 3 for w in waits) and len({round(w, 2) for w in waits}) > 5)
ctx = {"speed": 2.0}
app._more_set_speed(step("set_speed", speed=0.5), ctx)
check("Set speed: changes this run's speed and remembers the speed to go back to",
      ctx["speed"] == 0.5 and ctx["base_speed"] == 2.0)

# ------------------------------------------------------------ keys, clicks, moves, scrolls
play([step("key", key={"char": "e"}, mods=["ctrl"], times=2, between=0.05)])
order = [(e["key"].get("special") or e["key"].get("char"), e["pressed"]) for e in sent]
check("Key combo: Ctrl down, E, E up, Ctrl up (twice)", order == [("ctrl", True), ("e", True), ("e", False),
                                                                  ("ctrl", False)] * 2, order)
app.last_found = (100, 200, 40, 20)
sent.clear()
app._more_click(step("click", target="found", dx=5, dy=-5), {"speed": 1.0, "bg": None, "held": (set(), set()),
                                                             "seen": threading.Event(), "away": None})
clicks = [e for e in sent if e["type"] == "click"]
check("Click where it was found: its middle + the offset", clicks and clicks[0]["x"] == 125 and clicks[0]["y"] == 205,
      clicks[:1])
spots = set()
for _ in range(40):
    p = app._click_point(step("click", target="area", random=True, x0=10, y0=10, x1=20, y1=14))
    spots.add(p)
check("Click a random spot in the area: always inside, and different spots", all(10 <= x < 20 and 10 <= y < 14
                                                                                  for x, y in spots) and len(spots) > 5)
app.last_found = None
play([step("click", target="found")])
check("Click where it was found, with nothing found: no click (and the log says so)",
      not [e for e in sent if e["type"] == "click"] and "nothing was found yet" in log_text())
j = {app._click_point(step("click", x=50, y=50, jitter=3)) for _ in range(40)}
check("Click: small random offset stays within ± pixels", all(47 <= x <= 53 and 47 <= y <= 53 for x, y in j))
app.mouse_ctrl = type("M", (), {"position": (0, 0)})()
play([step("move", x=100, y=50, glide=0.2)])
moves = [e for e in sent if e["type"] == "move"]
check("Move slowly: many small moves ending on the spot", len(moves) > 10 and (moves[-1]["x"], moves[-1]["y"]) == (100, 50))
play([step("move", relative=True, dx=300, dy=0)])
check("Move: camera turn sends a relative move", sent and sent[0]["type"] == "move_rel" and sent[0]["dx"] == 300)
play([step("scroll", amount=-3, between=0.02)])
check("Scroll: one notch at a time", [e["dy"] for e in sent] == [-1, -1, -1])

# ------------------------------------------------------------ Go to, endless loops, missing labels
play([step("label", name="A"), step("goto", label="A", limit=100000)])
check("Go to: 50 jumps in a row with no time passing stop the macro", app.stop_reason
      and "no time passing" in app.stop_reason, app.stop_reason)
play([step("goto", label="Nowhere")])
check("Go to a Label that isn't there: stops and says so", app.stop_reason and "no Label \"Nowhere\"" in app.stop_reason)
inner = [step("label", name="Top"), step("counter_add", counter="G"),
         step("if_counter", counter="G", at_least=3, actions=[step("stop")]),
         step("if_counter", counter="G", at_least=0, actions=[step("goto", label="Top", limit=10)])]
app.counters = {}
play(inner)
check("Go to from inside a group jumps to a Label outside it", app.counters.get("G") == 3, app.counters)

# ------------------------------------------------------------ Discord from a macro
app._macro_discord = app._macro_discord_real
posted = []
import discord_notify  # noqa: E402

class FakeNotifier:
    def __init__(self, get_url, **kw):
        self.get_url = get_url

    def send(self, text, png=None, **kw):
        posted.append((self.get_url(), text))
        return True


real_notifier = discord_notify.Notifier
discord_notify.Notifier = FakeNotifier
app.macro_notifier = None
app.settings.update(discord_macro_to="webhook", discord_macro_webhook="https://example.com/not-a-webhook")
check("Discord: a wrong extra webhook isn't used", app._macro_discord("hi") is False and not posted)
hook = "https://discord.com/api/webhooks/123456789012345678/" + "x" * 60
app.settings["discord_macro_webhook"] = hook
app.counters = {"Total": 48}
app._more_discord(step("discord", text="Total sum: {Total} ({Unknown})"), {"speed": 1})
check("Discord: {Total} is filled in, unknown names stay", posted and posted[-1][1] == "Total sum: 48 ({Unknown})",
      posted)
check("Discord: the webhook link is never written to the log", hook not in log_text())
check("Discord: the webhook never goes into a support report", hook not in core.diag.report("x", app.settings))
app.settings.update(discord_macro_to="channel", discord_macro_channel="123", remote_enabled=False)
check("Discord: the bot channel needs the bot on and a channel ID", app._macro_discord("x") is False)
discord_notify.Notifier = real_notifier
app.settings.update(discord_macro_to="cards", discord_macro_webhook="", discord_enabled=False)
app._macro_discord = lambda text, png=None, to="default", channel=None, ping=False: (discord.append((text, ping)), True)[1]

# ------------------------------------------------------------ sounds, screenshots, the game
played_sounds.clear()
app._call_ui = lambda fn: fn()
app._more_sound(step("sound", sound="win"), {})
check("Play a sound: plays it", played_sounds == ["win"])
shots = []
app._screenshot = lambda: b"\x89PNGfake"
app._more_screenshot(step("screenshot", to="both"), {})
folder = core.diag.reports_dir()
saved = [f for f in os.listdir(folder) if f.startswith("screenshot")] if folder and os.path.isdir(folder) else []
check("Take a screenshot: saved in the reports folder and sent to Discord", saved and discord
      and discord[-1][0].startswith("Screenshot"), (saved, discord[-1:]))
app.play_game_exe = "notepad.exe"
fronted.clear()
check("Bring the game to the front", app._more_game(step("game"), {}) == "ok" and fronted == [4242])
app.play_game_exe = "nothere.exe"
app.stop_play.clear()
r = app._more_game(step("game", mode="wait", wait=0.3, otherwise="stop"), {})
check("Wait for the game: not open in time -> Stop (as chosen)", r == "stop" and "isn't open" in app.stop_reason)
app.stop_reason = None

# ------------------------------------------------------------ files: shared, checked, older versions
hostile = {"kind": "maths", "counter": "\u202eEvil" + "x" * 99, "a": {"number": float("inf")}, "b": "x",
           "op": "^", "decimals": 7, "show_timer": "yes", "then_macro": "..\\..\\evil.macro"}
step_more.clean_step(hostile)
check("files: a hostile Do maths is cleaned", hostile["counter"] == ("Evil" + "x" * 99)[:30]
      and hostile["a"] == {"number": 0} and hostile["b"] == {"number": 0} and hostile["op"] == "+"
      and hostile["decimals"] == 0 and hostile["show_timer"] is False and hostile["then_macro"] == "", hostile)
d = {"kind": "discord", "text": "x" * 5000, "to": "moon", "channel": "abc", "webhook": "https://secret"}
step_more.clean_step(d)
check("files: a Discord step never keeps a webhook link, text is limited", "webhook" not in d
      and len(d["text"]) == step_more.TEXT_LETTERS and d["to"] == "default" and d["channel"] == "")
g = {"kind": "goto", "label": None, "limit": -5}
step_more.clean_step(g)
check("files: Go to's limit is at least 1", g["limit"] == 1 and g["label"] == "Start")
t = {"kind": "type", "text": "hi", "window": {"exe": "C:\\Users\\Someone\\notepad.exe", "title": "x" * 500}}
step_more.clean_step(t)
check("files: Type's window keeps the program's file name only (no path)", t["window"]["exe"] == "notepad.exe"
      and len(t["window"]["title"]) == 60)
c = {"kind": "if", "condition": {"type": "time", "from": "25:99", "to": None, "more": [{"type": "counter",
                                                                                        "op": "drop"}] * 20}}
step_more.clean_step(c)
check("files: conditions: bad times / ops fixed, at most 8 more", c["condition"]["from"] == "02:00"
      and len(c["condition"]["more"]) == 8 and c["condition"]["more"][0]["op"] == ">=")
other = os.path.join(tmp, "After.macro")
with open(other, "w", encoding="utf-8") as f:
    json.dump({"app": "macro_recorder", "version": 1, "events": []}, f)
path = os.path.join(tmp, "Mine.macro")
app.set_steps([step("type", text="x", then_macro=other), step("discord", text="hi")])
with open(os.path.join(tmp, "sub_ignored.txt"), "w") as f:
    pass
with open(path, "w", encoding="utf-8") as f:
    core.dump_macro({"app": "macro_recorder", "version": core.FILE_VERSION, "events": app.events,
                     "actions": app.actions}, f)
text = open(path, encoding="utf-8").read()
check("files: the macro a step plays is saved by name, not with this PC's path", "After.macro" in text
      and tmp not in text and "webhook" not in text)

# ------------------------------------------------------------ Check my macro
app.set_steps([step("goto", label="Missing"), step("else"), step("type", text="x", then_macro="gone.macro")])
found = {p["id"].split(":")[0] for p in app.check_macro()}
check("Check my macro: Go to without its Label, an Else not after an If, a missing macro",
      {"goto", "else", "then"} <= found, found)

# ------------------------------------------------------------ the Edit window shows every new action
app.set_steps([step("wait")])
app.open_editor()
ed = app.macro_editor
pump(0.2)
broken = []
for kind, _n, _w in workflow.ADDABLE:
    if kind in ("record_here", "insert_macro"):
        continue
    a = workflow.new_action(kind)
    if kind == "click":
        a.update(target="area", x0=1, y0=1, x1=5, y1=5)
    if kind == "if":
        a["condition"].update(type="counter", more=[{"type": "time", "from": "01:00", "to": "02:00"}])
    if kind == "repeat":
        a["mode"] = "until"
    if kind == "retry":
        a["if_fails"] = "macro"
    ed.steps.append(a)
    try:
        ed._fill_steps(select=a["id"])
        ed._show_detail(a)
        pump(0.02)
    except Exception as exc:  # noqa: BLE001
        broken.append((kind, repr(exc)))
check("Edit: every action's panel opens (new and updated ones)", not broken, broken)
check("Edit: the Add action list has the new actions in sections", all(k in workflow.NAMES for k in step_more.KINDS))
ed.win.destroy()

# ------------------------------------------------------------ Settings > Discord: messages from macros
holder = tk.Toplevel(root)
holder.withdraw()
frame = tk.Frame(holder)
app._build_macro_messages(frame)
v = app.macro_messages_vars
v["webhook"].set("not a link")
check("Settings > Discord: a wrong webhook is refused (and said so)", app.settings.get("discord_macro_webhook") == ""
      and "isn't a Discord webhook" in v["status"].cget("text"))
v["channel"].set("12345678901234567")
check("Settings > Discord: a channel ID is kept", app.settings.get("discord_macro_channel") == "12345678901234567")
found = app.search_settings("webhook") if hasattr(app, "tab_frames") else None
holder.destroy()

# ------------------------------------------------------------ (the owner's round 3 report) Else, time boxes, dark option buttons
from ui_common import TimeBox, parse_time_text  # noqa: E402

app.set_steps([step("wait", seconds=0.01)])
app.open_editor()
ed = app.macro_editor
pump(0.2)
ed.steps[:] = [step("if", condition={"type": "time", "from": "00:00", "to": "23:59", "shows": True})]
workflow.ensure_ids(ed.steps)
the_if = ed.steps[0]
ed._fill_steps(select=the_if["id"])
ed.add("key")  # (goes inside the If and stays chosen, like in the owner's test)
inner = the_if["actions"][0]
ed._fill_steps(select=inner["id"])
ed.add("else")
check("Else: added while a key INSIDE the If is chosen, it still goes right after the If (not inside)",
      [a["kind"] for a in ed.steps] == ["if", "else"] and [a["kind"] for a in the_if["actions"]] == ["key"],
      ([a["kind"] for a in ed.steps], [a["kind"] for a in the_if["actions"]]))
els = ed.steps[1]
ed._fill_steps(select=els["id"])
ed.add("key")
check("Else: actions added while it's chosen go inside it", [a["kind"] for a in els["actions"]] == ["key"])
check("Else: right after its If, no warning", ed._else_has_if(els))
els2 = step("else")
ed.steps.append(els2)
workflow.ensure_ids(ed.steps)
check("Else: not after an If, it says so (orange line)", not ed._else_has_if(els2))
ed._show_detail(els2)
texts = []


def all_text(w):
    for c in w.winfo_children():
        try:
            texts.append(str(c.cget("text")))
        except tk.TclError:
            pass
        all_text(c)


all_text(ed.detail)
check("Else: the warning is shown in its panel", any("never runs" in t for t in texts))
ed.steps.remove(els2)
played = []
real_play_test = app.play_test
app.play_test = lambda steps, how, screen, program, found=True: played.append([a["kind"] for a in steps])
ed._fill_steps(select=els["id"])
ed.test_play("only")
check("Else: 'Play only this action' plays its If first", played and played[-1] == ["if", "else"], played)
ed.test_play("from")
check("Else: 'Play from here' plays its If first", played[-1][:2] == ["if", "else"], played[-1])
app.play_test = real_play_test
# the time of day boxes in the If's panel
ed._show_detail(the_if)
tb = ed.time_boxes["from"]
tb.mm.set("")
tb.hh.set("0")
tb.hh.set("05")
check("If time: a half-typed time isn't saved", the_if["condition"]["from"] == "00:00")
tb.mm.set("3")
tb.mm.set("30")
check("If time: hours + minutes typed: saved as 05:30", the_if["condition"]["from"] == "05:30", the_if["condition"])
ed.win.destroy()

# the HH : MM box itself
holder = tk.Toplevel(root)
holder.withdraw()
tb = TimeBox(holder, value="7:5")
check("time box: '7:5' shows as 07 : 05", (tb.hh.get(), tb.mm.get()) == ("07", "05") and tb.value() == "07:05")
check("time box: only digits, at most 2 (letters and ':' can't be typed)",
      not tb.hh_box.tk.call(tb.hh_box.cget("validatecommand").split()[0], "1a")
      and not tb.hh_box.tk.call(tb.hh_box.cget("validatecommand").split()[0], "123")
      and tb.hh_box.tk.call(tb.hh_box.cget("validatecommand").split()[0], "12"))
jumped = []
tb.focus_get = lambda: tb.hh_box
tb.mm_box.focus_set = lambda: jumped.append("mm")
tb.hh_box.focus_set = lambda: jumped.append("hh")
tb.hh.set("")
tb.hh.set("2")
check("time box: one hour digit stays in the hours", not jumped)
tb.hh.set("21")
check("time box: two hour digits jump to the minutes", jumped == ["mm"], jumped)
tb.hh.set("99")
check("time box: hours over 23 become 23", tb.hh.get() == "23")
tb.mm.set("75")
check("time box: minutes over 59 become 59", tb.mm.get() == "59")
tb.mm.set("")
jumped.clear()
check("time box: Backspace in empty minutes jumps back to the hours", tb._back(None) == "break" and jumped == ["hh"])
check("time box: half typed is None (not a time), both empty is ''", tb.value() is None
      and (tb.hh.set("") or tb.value()) == "")
for text, want in (("21:30", ("21", "30")), ("2130", ("21", "30")), ("9.05", ("09", "05")), ("25:99", ("23", "59")),
                   ("abc", None), ("1:2:3", None), ("", None)):
    if parse_time_text(text) != want:
        check(f"time box: paste '{text}'", False, parse_time_text(text))
        break
else:
    check("time box: pasting 21:30, 2130, 9.05 fills both boxes (and nonsense does nothing)", True)
tb.var.set("06:45")
check("time box: setting the time from outside fills both boxes", (tb.hh.get(), tb.mm.get()) == ("06", "45"))
holder.destroy()
# playback never stops on a half time
check("If time: half-typed / broken times count as 'not now', never an error",
      all(step_more.in_time("12:00", a, b) is False for a, b in (("05", "06:00"), ("05:", "06:00"), ("21.00", "x"),
                                                                ("25:00", "26:00"), (None, "06:00"))))
# Stop by itself uses the same box
win = app.open_auto_stop()
box_var = win.variables["at"]
box_var.set("03:30")
check("Stop by itself: 'At this time' is an HH : MM box", isinstance(box_var, tk.StringVar)
      and any(isinstance(w, TimeBox) for w in win.body.winfo_children()[0].master.winfo_children()
              for w in [w] + list(w.winfo_children())))
win.save()
check("Stop by itself: the time is saved as 03:30", app.settings.get("auto_stop", {}).get("at") == "03:30",
      app.settings.get("auto_stop"))
# the dark look for round option buttons
from tkinter import ttk as _ttk  # noqa: E402

st = _ttk.Style()
check("option buttons: dark, also under the mouse (no white hover)",
      st.lookup("TRadiobutton", "background", ["active"]) == st.lookup("TCheckbutton", "background", ["active"])
      and st.lookup("TRadiobutton", "background") == st.lookup("TCheckbutton", "background"),
      (st.lookup("TRadiobutton", "background", ["active"]), st.lookup("TCheckbutton", "background", ["active"])))

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
root.destroy()
sys.exit(0 if passed == len(results) else 1)
