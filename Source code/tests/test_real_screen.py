"""Checks on a real AOT:R results screen (tests/data/results_screen_part.png, taken on a 2560x1440
screen): the built-in MISSION COMPLETED picture is found (at the size it really shows, about 6 %
bigger than the picture), during playback and at the end of a run, and the divine fragment in the
OBTAINED row is counted. No real input, no windows."""
import os
import sys
import threading
import time

src = sys.argv[1]
sys.path.insert(0, src)
import cv2  # noqa: E402
import numpy as np  # noqa: E402

import drops  # noqa: E402
import image_watch as iw  # noqa: E402
import macro_recorder as core  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


part = cv2.imread(os.path.join(src, "tests", "data", "results_screen_part.png"))
shot = np.full((1440, 2560, 3), 20, np.uint8)
shot[240:240 + part.shape[0], 560:560 + part.shape[1]] = part  # where it was on the screen
blank = np.full((1440, 2560, 3), 20, np.uint8)
cur = {"img": shot}
iw.grab_screen = lambda sct=None, region=None: cur["img"].copy()
iw.grab_part = lambda x0, y0, x1, y1: (cur["img"][y0:y1, x0:x1].copy(), (x0, y0))
picture = os.path.join(src, core.BUILTIN_WIN_PICTURE)


def make_app(remembered=None):
    a = core.MacroRecorder.__new__(core.MacroRecorder)
    a.settings = {"results_match": 85, "results_enabled": True}
    a.screen_w, a.screen_h = 2560, 1440
    a.win_rect = (0, 0, 0, 0)
    fields = dict(file="x", screen_h=core.BUILTIN_WIN_PICTURE_SCREEN_H, kind="win")
    fields.update(remembered or {})
    a.result_pictures = [core.SavedPicture(picture, **fields)]
    a.result_matchers = a._build_result_matchers()
    a.result_state = {}
    return a


a = make_app()
t = time.perf_counter()
check("end of run: MISSION COMPLETED found", a._run_result(0) == "win")
first = time.perf_counter() - t
check("end of run: first look under 1.5 s", first < 1.5, f"{first:.2f} s")
step = a.result_pictures[0].get("found_step")
check("its size is remembered", isinstance(step, int), step)
a.result_state = {}
t = time.perf_counter()
check("end of run again: found", a._run_result(0) == "win")
check("end of run again: quick", time.perf_counter() - t < (0.8 if sys.platform == "darwin" else 0.2),  # (slow Macs)
      f"{time.perf_counter() - t:.3f} s")

# while playing: blank screen, then the results screen shows
b = make_app()
cur["img"] = blank
done = threading.Event()
th = threading.Thread(target=b._result_worker, args=(b.result_matchers, done))
th.start()
time.sleep(1.5)
cur["img"] = shot
deadline = time.time() + 15
while time.time() < deadline and not b.result_state.get("win", {}).get("appeared"):
    time.sleep(0.2)
done.set()
th.join()
check("while playing: the results screen is noticed once",
      len(b.result_state.get("win", {}).get("appeared", [])) == 1, b.result_state)

# next session with the remembered size: found straight away
c = make_app({"found_factor": 1.0, "found_screen": [2560, 1440], "found_step": step})
cur["img"] = shot
t = time.perf_counter()
# (Preview 4) GitHub's Intel Macs are several times slower: "at once" is 0.3 s here, 1.2 s there (missed by a
# little in 2.12's Mac run; a whole-size search takes far longer, so this still tells the two apart)
limit = 1.2 if sys.platform == "darwin" else 0.3
check("next session: found at once", c._run_result(0) == "win" and time.perf_counter() - t < limit,
      f"{time.perf_counter() - t:.2f} s")
cur["img"] = blank
c.result_state = {}
check("blank screen: unknown", c._run_result(0) == "unknown")

# MISSION FAILED: with both built-in pictures, a failed screen is a loss and a completed one a win
part_f = cv2.imread(os.path.join(src, "tests", "data", "failed_screen_part.png"))
failed = np.full((1440, 2560, 3), 20, np.uint8)
failed[240:240 + part_f.shape[0], 560:560 + part_f.shape[1]] = part_f


def make_both():
    a2 = make_app()
    a2.result_pictures.append(core.SavedPicture(os.path.join(src, core.BUILTIN_LOSS_PICTURE), file="y",
                                                screen_h=core.BUILTIN_LOSS_PICTURE_SCREEN_H, kind="loss"))
    a2.settings["results_match"] = core.RESULTS_MATCH_DEFAULT
    a2.result_matchers = a2._build_result_matchers()
    return a2


d = make_both()
cur["img"] = failed
check("MISSION FAILED screen: loss", d._run_result(0) == "loss")
d.result_state = {}
cur["img"] = shot
check("then a MISSION COMPLETED screen: win", d._run_result(0) == "win")
d.result_state = {}
cur["img"] = failed
check("and a failed one again: loss", d._run_result(0) == "loss")
e = make_both()
cur["img"] = shot
check("completed first (fresh): win", e._run_result(0) == "win")

# divine fragments
check("fragments on the whole screen: 1", drops.count_frames(shot)[0] == 1)
cur["img"] = shot
c.result_matchers[0].last_rect = (910, 284, 746, 74)
check("fragments in the OBTAINED row: 1", c._count_drops() == 1)
check("fragments on a blank screen: 0", drops.count_frames(blank)[0] == 0)
# a full OBTAINED row is wider than the title: a fragment in the last slot (past the title's end) counts too
fx, fy, fw, fh = drops.count_frames(shot)[1][0]
wide = shot.copy()
nx = int(910 + 1.2 * 746)
wide[fy:fy + fh, nx:nx + fw] = shot[fy:fy + fh, fx:fx + fw]
cur["img"] = wide
check("fragments: one in the row's last slot counts too", c._count_drops() == 2)
cur["img"] = shot
for dy in (1, 3, 5):
    check(f"fragments, screen moved {dy} px: 1", drops.count_frames(shot[dy:], full_height=1440)[0] == 1)

print()
print(f"{sum(ok for _, ok in results)} of {len(results)} passed")
