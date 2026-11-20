"""Screenshots for Discord: which way a screenshot was taken (the game's window, or the main screen because the window
wasn't found), and the words the phone remote adds when it had to use the whole screen.
No windows opened, nothing really captured: the window lookup and the screen grab are stand-ins."""
import sys
import types

src = sys.argv[1]
sys.path.insert(0, src)
import numpy as np  # noqa: E402

import discord_notify  # noqa: E402
import image_watch  # noqa: E402
import window_tools  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


MAIN = np.zeros((1440, 2560, 3), dtype=np.uint8)  # (what a main-screen grab returns)
GAME = np.zeros((100, 200, 4), dtype=np.uint8)    # (what grabbing the game's window returns: BGRA)


class FakeMss:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def grab(self, box):
        return GAME

    monitors = [{"left": 0, "top": 0, "width": 4480, "height": 1440}]


image_watch.mss = types.SimpleNamespace(mss=FakeMss)
image_watch.grab_screen = lambda: MAIN
window_tools.IS_WIN = True

# ---- the game's window is found
window_tools.windows_of = lambda exe: [7]
window_tools.client_rect = lambda h: (0, 23, 200, 100)
img, how, fell = discord_notify.grab_how(discord_notify.CAPTURE_GAME, "RobloxPlayerBeta.exe")
check("game window found: its picture, no fallback", img.shape == (100, 200, 3) and not fell and "game window" in how, (img.shape, how, fell))

# ---- no window of that program
window_tools.windows_of = lambda exe: []
img, how, fell = discord_notify.grab_how(discord_notify.CAPTURE_GAME, "RobloxPlayerBeta.exe")
check("no window: the main screen, and it says why", img.shape == MAIN.shape and fell and "not found" in how, (img.shape, how, fell))

# ---- a window with no usable inside (minimized, or only a moment ago re-created)
window_tools.windows_of = lambda exe: [7]
window_tools.client_rect = lambda h: None
img, how, fell = discord_notify.grab_how(discord_notify.CAPTURE_GAME, "RobloxPlayerBeta.exe")
check("window without a usable inside: the main screen, and it says why",
      img.shape == MAIN.shape and fell and "no usable" in how, (img.shape, how, fell))

# ---- a program chosen by name
window_tools.windows_of = lambda exe: []
img, how, fell = discord_notify.grab_how("program:Notepad.exe", None)
check("a chosen program that isn't open: fallback, with its name", fell and "Notepad.exe" in how, how)

# ---- screens chosen on purpose are not a fallback
img, how, fell = discord_notify.grab_how(discord_notify.CAPTURE_SCREEN, None)
check("main screen chosen: no fallback", img.shape == MAIN.shape and not fell and "main screen" in how, (how, fell))
img, how, fell = discord_notify.grab_how(discord_notify.CAPTURE_ALL, None)
check("all screens chosen: no fallback", img.shape == (100, 200, 3) and not fell and "all screens" in how, (img.shape, how, fell))

# ---- the old function still gives just the picture
window_tools.windows_of = lambda exe: [7]
window_tools.client_rect = lambda h: (0, 23, 200, 100)
check("grab() still returns only the picture", discord_notify.grab(discord_notify.CAPTURE_GAME, "x.exe").shape == (100, 200, 3))

# ---- the words in the Discord reply
plain = discord_notify.shot_caption("08:22:48", False)
check("caption: a normal screenshot keeps its old words", plain == "Screenshot at 08:22:48", plain)
warn = discord_notify.shot_caption("08:22:48", True)
check("caption: a fallback says it is the whole screen", warn.startswith("Screenshot at 08:22:48") and "whole screen" in warn
      and "not found" in warn, warn)

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
