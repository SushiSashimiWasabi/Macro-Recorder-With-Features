"""Safety fixes after the Preview audit: the keys box is no longer blacked out of what Picture watch looks at,
settings.json is written through a temp file (and a failed write is logged), an unknown run says why, and two
Discord screenshots never run at the same time. Stand-ins only: no windows opened, nothing sent anywhere."""
import json
import os
import sys
import tempfile
import threading
import time
import types

src = sys.argv[1]
sys.path.insert(0, src)
import numpy as np  # noqa: E402

import macro_recorder as core  # noqa: E402  (first: the core class imports its mixins)
import core_results  # noqa: E402
import discord_notify  # noqa: E402
import discord_ui  # noqa: E402
import keys_overlay  # noqa: E402
import own_windows  # noqa: E402
import stats  # noqa: E402
import window_tools  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


# ---- 1: the keys box must not hide the game's pixels (a banner under it was read as "unknown")
fake = types.SimpleNamespace(rect=None)
keys_overlay.KeysOverlay._ignore(fake, (24, 24, 200, 80))
check("keys box: it still knows where it is", fake.rect == (24, 24, 200, 80), fake.rect)
check("keys box: it is not one of the places blacked out of screenshots", "keys" not in own_windows.rects_by_name(),
      own_windows.rects_by_name())
img = np.full((120, 300, 3), 255, np.uint8)
own_windows.blank(img)
check("keys box: the picture under it stays as it is", int(img[40, 40].sum()) == 765)
own_windows.set_rect("timer", (0, 0, 10, 10))
img = np.full((120, 300, 3), 255, np.uint8)
own_windows.blank(img)
check("the timer is still blacked out (only the keys box changed)", int(img[5, 5].sum()) == 0)
own_windows.set_rect("timer", None)

# ---- 2: settings.json is written through a temp file
tmp = tempfile.mkdtemp(prefix="mr_post213_")
path = os.path.join(tmp, "settings.json")
core.settings_path = lambda: path
core.save_settings({"a": 1}, now=True)
check("settings: a normal write", json.load(open(path, encoding="utf-8")) == {"a": 1})
real_replace, real_error = os.replace, core.diag.error
logged = []
os.replace = lambda s, d: (_ for _ in ()).throw(OSError("disk full"))
core.diag.error = lambda msg, *a, **k: logged.append(str(msg))
try:
    core.save_settings({"a": 2}, now=True)
finally:
    os.replace, core.diag.error = real_replace, real_error
check("settings: a write that fails half way leaves the old file whole", json.load(open(path, encoding="utf-8")) == {"a": 1},
      open(path, encoding="utf-8").read()[:60])
check("settings: and says so in the log", any("settings" in m.lower() for m in logged), logged)
check("settings: no temp file is left behind", not os.path.exists(path + ".tmp"))
core.save_settings({"a": 3}, now=True)
check("settings: the next write works again", json.load(open(path, encoding="utf-8")) == {"a": 3})

# ---- 3: an unknown run says why
own_windows.set_rect("keys", (24, 24, 300, 90))
who = types.SimpleNamespace(RESULT_TITLES=core_results.CoreResultsMixin.RESULT_TITLES)
text = core_results.CoreResultsMixin._unknown_reason(who, {stats.WIN: 0.62, stats.LOSS: 0.31}, 0.80)
check("unknown run: names the best score and what was needed",
      "MISSION COMPLETED" in text and "62%" in text and "80%" in text and "31%" in text, text)
check("unknown run: names the own windows that were blacked out and where", "keys" in text and "24" in text, text)
own_windows.set_rect("keys", None)
text = core_results.CoreResultsMixin._unknown_reason(who, {}, 0.80)
check("unknown run: with nothing looked at it still says something sensible", "no" in text.lower(), text)

# ---- 5: two Discord screenshots never run at the same time
obj = discord_ui.DiscordMixin()
obj.settings, obj.macro_program = {}, None
gate, now_in, peak = threading.Lock(), [0], [0]


def slow_grab(target, exe):
    with gate:
        now_in[0] += 1
        peak[0] = max(peak[0], now_in[0])
    time.sleep(0.15)
    with gate:
        now_in[0] -= 1
    return ("pic", "main screen", False)


real = (discord_notify.grab_how, discord_notify.grab_area, window_tools.hide_own_windows_from_capture)
discord_notify.grab_how, discord_notify.grab_area = slow_grab, lambda t, e: None
window_tools.hide_own_windows_from_capture = lambda *a, **k: 0
try:
    threads = [threading.Thread(target=obj._screenshot_with_note) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
finally:
    discord_notify.grab_how, discord_notify.grab_area, window_tools.hide_own_windows_from_capture = real
check("screenshots: never two at the same moment", peak[0] == 1, peak[0])

# ---- a broken number in settings.json ("Infinity", NaN, text) gives the default, never a crash (Play reads the
# all-time results with it; int(Infinity) used to raise OverflowError there and Play didn't start)
for bad in (float("inf"), float("-inf"), float("nan"), "lots", None, [1]):
    try:
        got = core.int_setting({"streak_now": bad}, "streak_now", 0, 0, 10 ** 9)
    except Exception as exc:  # noqa: BLE001
        got = exc
    check(f"int_setting: {bad!r} gives the default", got == 0, got)
check("int_setting: a good number still comes through", core.int_setting({"n": "12"}, "n", 0, 0, 99) == 12)
play_src = open(os.path.join(src, "core_playback.py"), encoding="utf-8").read()
check("Play reads the all-time results through int_setting (no bare int())",
      'int(alltime.get(' not in play_src and play_src.count('core.int_setting(alltime, ') == 3)

# (batch 2) the rules module keeps its own list of "then" choices: it must match the one the window shows
import auto_stop  # noqa: E402

check("Stop by itself: the rules know every 'then' choice", set(auto_stop.THEN) == set(core.AUTO_STOP_THEN)
      and set(auto_stop.THEN_TEXT) == set(core.AUTO_STOP_THEN))
# (batch 3) the group rules keep their own copy of the group ids
import picture_groups  # noqa: E402

check("Picture watch: the rules use the core's group ids", (picture_groups.GENERAL, picture_groups.AOTR, picture_groups.MINE)
      == (core.GROUP_GENERAL, core.GROUP_AOTR, core.GROUP_MINE))

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
