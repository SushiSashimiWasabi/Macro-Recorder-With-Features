"""Sharing in one file, the Settings search, the first-start guide, the dashboard, the chain chart,
"if a run fails" in chains, the live Discord card and "ping me when".
No real input is sent, throwaway settings folder."""
import json
import os
import sys
import tempfile
import time
import zipfile

src = sys.argv[1]
sys.path.insert(0, src)
tmp = tempfile.mkdtemp(prefix="mr_test_")

import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
import numpy as np  # noqa: E402
import tkinter as tk  # noqa: E402

import discord_notify  # noqa: E402
import extras_ui  # noqa: E402
import image_watch  # noqa: E402
import macro_steps as workflow  # noqa: E402
import modern_ui  # noqa: E402
import profiles_ui  # noqa: E402
import stats  # noqa: E402
import window_tools  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


def key(vk, t, pressed=True):
    return {"type": "key", "key": {"vk": vk}, "pressed": pressed, "t": t}


def tap(vk):
    return [key(vk, 0.0), key(vk, 0.05, False)]


def save_macro(folder, name, events=None, actions=None, **more):
    path = os.path.join(folder, name + ".macro")
    data = dict({"app": "macro_recorder", "version": 1, "events": events or []}, **more)
    if actions:
        data["actions"] = actions
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def play_macro_step(path, times=1, **more):
    a = workflow.new_action("play_macro")
    a.update(file=path, times=times, **more)
    return a


# ---- the live card: one message that's changed in place (a fake Discord)
calls = []


def fake_post(url, text, png=None, timeout=15, embed=None, username=None, edit_id=None, want_id=False):
    calls.append({"edit": edit_id, "want": want_id, "title": (embed or {}).get("title")})
    if edit_id == "gone":
        raise LookupError("gone")
    return "id1" if want_id else None


real_post, discord_notify.post = discord_notify.post, fake_post
hook = "https://discord.com/api/webhooks/123456789012345678/abcSECRETabcSECRETabcSECRETabcSECRETabcSECRET"
n = discord_notify.Notifier(lambda: hook)
n.last_sent = -10
for i in range(3):
    n.send("", embed={"title": f"run {i}"}, live="runs:1")
    n.last_sent = -10
n.send("plain", embed={"title": "own"})
time.sleep(0.2)
t0 = time.time()
while len(calls) < 4 and time.time() - t0 < 12:
    time.sleep(0.05)
check("live card: first a new message, then the same one changed, others still new",
      [(c["edit"], c["want"]) for c in calls] == [(None, True), ("id1", False), ("id1", False), (None, False)], calls)
n.live["runs:1"] = (hook, "gone")
calls.clear()
n.send("", embed={"title": "again"}, live="runs:1")
t0 = time.time()
while len(calls) < 2 and time.time() - t0 < 6:
    time.sleep(0.05)
check("live card: a deleted card is posted again", [(c["edit"], c["want"]) for c in calls] == [("gone", False),
                                                                                              (None, True)], calls)
discord_notify.post = real_post

# ---- the app
root = tk.Tk()
root.withdraw()
app = modern_ui.ModernMacroRecorder(root)
app.kb_listener.stop()
app.mouse_listener.stop()
root.withdraw()
sent = []
app._replay_event = lambda e, hk, hb: sent.append(e)
app._click_at = lambda x, y: None
app.root.after = (lambda real: (lambda ms, fn=None, *a: real(ms, fn, *a) if fn else real(ms)))(app.root.after)
modern_ui.messagebox.showwarning = lambda *a, **k: None
window_tools.foreground = lambda: None
app.settings.update(pause_when_away=False, watch_enabled=False)
app.away_var.set(False)
app.watch_var.set(False)
app.result_pictures = []
app._save_settings()
boxes = []
app.boxes.showinfo = lambda *a, **k: boxes.append(("info", a))
app.boxes.showerror = lambda *a, **k: boxes.append(("error", a))
app.boxes.askyesno = lambda *a, **k: (boxes.append(("ask", a)), True)[1]


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def run_play(limit=15):
    sent.clear()
    app.ready_var.set(0)
    app.play()
    t0 = time.time()
    while app.playing and time.time() - t0 < limit:
        pump(0.03)
    pump(0.1)


def pressed_vks():
    return [e["key"]["vk"] for e in sent if e.get("type") == "key" and e.get("pressed")]


# ---- "if a run of it fails, play" in a chain
home = os.path.join(tmp, "mine")
os.makedirs(home)
a_path = save_macro(home, "A", tap(65))
fix_path = save_macro(home, "Fix", tap(70))
status = {"next": [stats.LOSS, stats.WIN]}
real_finish = app._finish_run


def fake_finish(count, how):
    app.session.add(status["next"].pop(0) if status["next"] else stats.WIN, 1.0, 0)
    app._run_finished(count, how)


app._finish_run = fake_finish
app._run_finished = lambda c, how: None
app.current_file = None
app.set_steps([play_macro_step(a_path, 2, on_fail=fix_path)])
app.loop_var.set(False)
app.repeat_var.set(1)
run_play()
check("chain: after a failed run its 'if it fails' macro plays, then the chain goes on",
      pressed_vks() == [65, 70, 65], pressed_vks())
app._finish_run = real_finish
del app._run_finished

# ---- share: export, then import as a friend would (another settings folder would be the same app here)
pic = np.zeros((20, 40, 3), np.uint8)
pic[5:15, 5:35] = (40, 200, 240)
os.makedirs(core.watch_dir(), exist_ok=True)
image_watch.save_image(os.path.join(core.watch_dir(), "retry.png"), pic)
image_watch.save_image(os.path.join(core.watch_dir(), "dc.png"), pic[:, ::-1].copy())
app.watch_pictures = [core.watch_picture_from({"file": "retry.png", "screen_h": 1080, "name": "Retry", "click": True}),
                      core.watch_picture_from({"file": "dc.png", "screen_h": 1080, "name": "Disconnected",
                                               "action": "recover", "macro": fix_path, "also": "retry.png"})]
app._show_watch_pictures()
app.settings.update(discord_enabled=True, discord_webhook=hook, discord_ping="<@1>",
                    game_closed={"action": "reopen", "open": "C:/secret.exe"}, remote_token="TOKEN")
app.save_profile("Farm")
main_path = save_macro(home, "Chain", actions=[play_macro_step(a_path, 3, on_fail=fix_path)], profile="Farm")
app.load(main_path, quiet=True)
pack = os.path.join(tmp, "Chain.macropack")
check("share: export writes the file", app.export_pack(pack) == pack and os.path.isfile(pack), boxes[-1:])
with zipfile.ZipFile(pack) as z:
    names = sorted(z.namelist())
    manifest = json.loads(z.read("manifest.json"))
    everything = b"".join(z.read(n) for n in names).decode("utf-8", "replace")
check("share: the chain's macros and the pictures are inside",
      {"macros/Chain.macro", "macros/A.macro", "macros/Fix.macro", "pictures/retry.png", "pictures/dc.png"}
      <= set(names), names)
check("share: nothing private is inside", "abcSECRET" not in everything and "TOKEN" not in everything
      and "secret.exe" not in everything and "<@1>" not in everything)
check("share: the profile and each picture's action are inside",
      manifest.get("profile", {}).get("name") == "Farm" and manifest["pictures"][1]["action"] == "recover"
      and manifest["pictures"][1]["macro"] == "Fix.macro", manifest.get("pictures"))

# the friend: no pictures, no profile yet
app.watch_pictures = []
app._show_watch_pictures()
app.delete_profile("Farm")
friend = os.path.join(tmp, "friend")
os.makedirs(friend)
boxes.clear()
opened = app.import_pack(pack, folder=friend)
check("share: import opens the main macro from the new folder",
      opened and os.path.dirname(opened) == os.path.join(friend, "Chain") and app.current_file == opened,
      (opened, boxes[-1:]))
step = app.macro_steps()[0]
# (2.9.1: saved by file name beside the macro, no whole paths; found again from the open macro)
check("share: its steps point at the imported macros",
      app._find_macro_file(step.get("file")) == os.path.join(friend, "Chain", "A.macro")
      and app._find_macro_file(step.get("on_fail")) == os.path.join(friend, "Chain", "Fix.macro")
      and not os.path.isabs(step.get("file")), step)
check("share: the pictures came with their actions",
      [(p.get("name"), p.get("action", "restart")) for p in app.watch_pictures] == [("Retry", "restart"),
                                                                                  ("Disconnected", "recover")]
      and app.watch_pictures[1]["macro"] == os.path.join(friend, "Chain", "Fix.macro")
      and app.watch_pictures[1]["also"] == app.watch_pictures[0]["file"],
      [{k: v for k, v in p.items() if k != "img"} for p in app.watch_pictures])
check("share: the profile was offered and added, without anything private",
      "Farm" in app.profiles() and "discord_webhook" not in manifest["profile"]["settings"]
      and "game_closed" not in manifest["profile"]["settings"], list(manifest["profile"]["settings"])[:5])
app.result_pictures = []
app._finish_run = fake_finish
app._run_finished = lambda c, how: None
app.watch_var.set(False)
app.settings["watch_enabled"] = False
run_play()
check("share: the imported chain plays", pressed_vks() == [65, 65, 65], pressed_vks())
app._finish_run = real_finish
del app._run_finished
again = app.import_pack(pack, folder=friend)
check("share: importing again uses a new folder and adds no picture twice",
      again and "Chain (2)" in again and len(app.watch_pictures) == 2, (again, len(app.watch_pictures)))
# a file that isn't one, and one that tries to write outside its folder
bad = os.path.join(tmp, "bad.macropack")
with open(bad, "w") as f:
    f.write("not a zip")
boxes.clear()
check("share: a broken file is refused with a message", app.import_pack(bad, folder=friend) is None
      and boxes and boxes[0][0] == "error", boxes)
evil = os.path.join(tmp, "evil.macropack")
with zipfile.ZipFile(evil, "w") as z:
    z.writestr("manifest.json", json.dumps({"app": "macro_recorder_pack", "version": 1,
                                            "main": "../../escaped.macro", "macros": ["../../escaped.macro"],
                                            "pictures": [], "profile": {"name": "P", "settings": {
                                                "discord_webhook": "https://evil", "remote_token": "x",
                                                "game_closed": {"action": "reopen", "open": "calc.exe"},
                                                "speed": 2.0}}}))
    z.writestr("macros/../../escaped.macro", json.dumps({"app": "macro_recorder", "version": 1,
                                                         "events": tap(65)}))
out = app.import_pack(evil, folder=friend)
check("share: a file name with ../ stays inside the chosen folder",
      out and os.path.dirname(out) == os.path.join(friend, "evil") and not os.path.exists(
          os.path.join(tmp, "escaped.macro")), out)
p_part = app.profiles().get("P") or {}
check("share: a profile from a file can't bring a Discord link, a token or a program to open",
      p_part.get("speed") == 2.0 and "evil" not in str(p_part.get("discord_webhook"))
      and "remote_token" not in p_part and "calc.exe" not in json.dumps(p_part.get("game_closed") or {}),
      {k: p_part.get(k) for k in ("speed", "discord_webhook", "game_closed")})

# ---- share: background pictures go in the file too (if you say yes), and come back on import
import cv2  # noqa: E402
settings_dir = os.path.dirname(core.settings_path())
bgimg = np.zeros((60, 90, 3), np.uint8)
bgimg[:, :45] = (200, 120, 40)
cv2.imwrite(os.path.join(settings_dir, "background_1.png"), bgimg)
app.settings["background_library"] = [{"file": "background_1.png", "name": "sky.png"}]
app.settings["background_picture"] = "background_1.png"
app.save_profile("Farm")
app.load(main_path, quiet=True)
pack2 = os.path.join(tmp, "WithBg.macropack")
boxes.clear()
check("share+bg: export with the background", app.export_pack(pack2) == pack2, boxes[-2:])
with zipfile.ZipFile(pack2) as z:
    names2 = z.namelist()
    manifest2 = json.loads(z.read("manifest.json"))
check("share+bg: the picture is inside, with which window shows it",
      "backgrounds/background_1.png" in names2 and manifest2["backgrounds"]["settings"].get("background_picture")
      == "background_1.png" and not any(n.startswith("macros/backgrounds") for n in names2), names2)
check("share+bg: the profile itself still carries no background (the backgrounds part does)",
      not any(profiles_ui.is_background_key(k) for k in manifest2["profile"]["settings"]))
# the friend: no background pictures yet, no Farm profile
app.settings["background_library"] = []
app.settings["background_picture"] = ""
os.remove(os.path.join(settings_dir, "background_1.png"))
app.delete_profile("Farm")
boxes.clear()
out2 = app.import_pack(pack2, folder=friend)
lib = app.bg_library()
check("share+bg: import adds the background picture", out2 and len(lib) == 1 and lib[0]["name"] == "sky.png"
      and os.path.isfile(os.path.join(settings_dir, lib[0]["file"])), (lib, boxes[-1:]))
check("share+bg: the imported profile shows it", app.profiles().get("Farm", {}).get("background_picture") == lib[0]["file"],
      app.profiles().get("Farm", {}).get("background_picture"))
again2 = app.import_pack(pack2, folder=friend)
check("share+bg: importing again doesn't add it twice", again2 and len(app.bg_library()) == 1, app.bg_library())

# ---- with one card that updates: won/failed runs update it, unknown runs and fragment drops get their
# own message with a screenshot
cards = []
real_send = app._send_card
app._send_card = lambda content, card, png, live=None: cards.append((card["title"], bool(png), live))
app._screenshot = lambda: b"\x89PNGfake"
app.settings.update(discord_enabled=True, discord_runs=True, discord_live=True, discord_screenshot=False,
                    discord_ping_when="never")
app.session = stats.Session("Farm")
for status, frags in ((stats.WIN, 0), (stats.LOSS, 0), (stats.UNKNOWN, 0), (stats.WIN, 1), (stats.WIN, 0)):
    app.session.add(status, 10, frags)
    discord_ui_finished = type(app).__mro__[0]._run_finished
    discord_ui_finished(app, len(app.session.runs), "end")
live = [c for c in cards if c[2]]
own = [c for c in cards if not c[2]]
check("live card: won and failed runs update the one card", len(live) == 3, cards)
check("live card: the unknown run and the fragment run are messages of their own, with a screenshot",
      len(own) == 2 and all(c[1] for c in own), cards)
app._send_card = real_send
app.settings["discord_live"] = False
del app._screenshot

# ---- "ping me when"
app.settings.update(discord_enabled=True, discord_webhook=hook)
pinged = []
app.notifier.send = lambda text, **k: pinged.append(text)
check("ping me: needs what to wait for", "ping you once when a divine fragment drops"
      in app.remote_pingme(("fragment", None, "42"), "Kong"), app.remote_pingme(("x", None, "42"), "Kong"))
app.remote_pings[:] = [{"uid": "42", "when": "fragment"}]
app.remote_pingme((None, 2, "42"), "Kong")
app.remote_pingme(("stop", None, "42"), "Kong")
app.session = stats.Session("Farm run")
app.session.add(stats.WIN, 10, 0)
extras_ui.ExtrasMixin._run_finished(app, 1, "end") if False else app._run_finished(1, "end")
check("ping me: nothing yet after a run without a fragment", pinged == [] or all("<@42>" not in p for p in pinged),
      pinged)
pinged.clear()
app.session.add(stats.WIN, 10, 1)
app._run_finished(2, "end")
check("ping me: pinged for the fragment and for the 2 runs, once each",
      len([p for p in pinged if "<@42>" in p]) == 2 and any("fragment" in p for p in pinged)
      and any("runs you asked" in p for p in pinged), pinged)
pinged.clear()
app._pings_on_stop("Stopped by you after 2 runs.")
app._pings_on_stop("again")
check("ping me: pinged once when it stops", len(pinged) == 1 and "<@42>" in pinged[0], pinged)
app.settings["discord_enabled"] = False
check("ping me: says so when Discord is off", "Turn that on" in app.remote_pingme(("stop", None, "42"), "Kong"))

# ---- Settings search, the first-start guide, the dashboard and the chart (opened, used, closed)
app.open_settings()
pump(0.4)
found = app.search_settings("random timing")
check("search: finds a setting on its page", found and found[0][0] == "Playback", [(p, t) for p, _w, t in found])
found = app.search_settings("webhook") + app.search_settings("discord link")
check("search: finds by the grey words too, and nothing for nonsense",
      bool(app.search_settings("countdown")) and app.search_settings("zzzqqq") == [],
      [(p, t) for p, _w, t in app.search_settings("countdown")])
app.search_var.set("stop by itself")
pump(0.2)
check("search: the list of results shows", app.search_list is not None and app.search_list.winfo_exists())
app._search_go(0)
pump(0.2)
check("search: choosing a result opens its page", app._open_page_name() == "Playback", app._open_page_name())
app.close_settings()

app.settings.pop("first_start_done", None)
for k in ("speed", "hotkeys", "macro_library"):
    app.settings.pop(k, None)
check("first start: due on a fresh install", app.first_start_due())
win = app.open_first_start()
pump(0.2)
win.answers["fit"].set("screen")
win.answers["watch"].set("no")
win.done()
pump(0.2)
check("first start: the answers became settings", app.settings["fit_to"] == "screen"
      and app.settings["watch_enabled"] is False and app.settings["first_start_done"] and not app.first_start_due(),
      {k: app.settings.get(k) for k in ("fit_to", "watch_enabled", "first_start_done")})
app.settings["speed"] = 1.0
app.settings.pop("first_start_done")
check("first start: not shown after an update (settings already there)", not app.first_start_due())

app.load(opened, quiet=True)
lines = dict(app.dashboard_lines())
check("dashboard: says what's open and how it's set up",
      lines["Macro"] and "A ×3" in lines["Chain"] and lines["Profile"] and "Stop by itself" in lines, lines)
win = app.open_dashboard()
pump(0.3)
check("dashboard: the window shows", win.winfo_exists())
win.destroy()

app.open_editor()
pump(0.5)
ed = app.macro_editor
ed._open_entry(ed.current if ed.current is not None else 0, ask=False)
extra = workflow.new_action("wait")
ed.change(lambda: ed.steps.append(extra))
chart = app.open_chain_chart(ed)
pump(0.2)
check("chart: one box per step, the fail branch named", [b["title"] for b in chart.state["boxes"]] == ["A", "Wait"]
      and chart.state["boxes"][0]["fail"] == "Fix", chart.state["boxes"])


class Ev:
    def __init__(self, x, y):
        self.x, self.y = x, y


chart.press(Ev(100, 30))
chart.release(Ev(100, 30 + 72))
pump(0.1)
check("chart: dragging a box moves the step (and can be undone)",
      [a["kind"] for a in ed.steps] == ["wait", "play_macro"] and len(ed.undo_stack) == 2,
      [a["kind"] for a in ed.steps])
chart.destroy()
ed.steps = workflow.snapshot(ed.base_steps)
ed.autosave_now()
ed.win.destroy()

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)} of {len(results)} passed")
root.destroy()
sys.exit(1 if failed else 0)
