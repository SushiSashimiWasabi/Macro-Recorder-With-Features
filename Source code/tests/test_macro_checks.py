"""Check my macro rules (mixin batch 1): the step checks (missing macros, also inside played macros, steps with no
picture, Go to without its Label, Else not after an If, Type text into a closed program) and the "Don't warn me
again" list. No windows, no files: the macros a step plays are a dict of made-up ones."""
import sys

src = sys.argv[1]
sys.path.insert(0, src)
import macro_checks as mc  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


MACROS = {}  # path -> steps of the made-up macros on "disk"
reads = []


def find(path):
    return path if path in MACROS or path == "broken.macro" else None


def read(found):
    reads.append(found)
    if found == "broken.macro":
        raise ValueError("broken")
    return MACROS[found]


def ids(steps, open_programs=None, depth=6):
    probe = None if open_programs is None else (lambda exe: exe in open_programs)
    return [p[0] for p in mc.step_problems(steps, find, read, probe, depth)]


def play(path, on_fail=None, **kw):
    a = {"kind": "play_macro", "file": path, "id": kw.pop("id", "p")}
    if on_fail:
        a["on_fail"] = on_fail
    a.update(kw)
    return a


# ---- macros a "Play another macro" step plays
MACROS["a.macro"] = []
check("chain: a macro that is there = nothing", ids([play("a.macro")]) == [])
check("chain: a gone macro is a sure problem", mc.step_problems([play("Gone.macro")], find, read)[0]
      == ("chain:gone", mc.SURE, 'The macro "Gone" that a "Play another macro" step plays isn\'t there any more. '
                                  "That part is skipped."))
check("chain: the fail macro is checked too", ids([play("a.macro", on_fail="Lost.macro")]) == ["chain:lost"])
check("chain: a turned-off step is skipped", ids([play("Gone.macro", off=True)]) == [])
MACROS["b.macro"] = [play("Inner gone.macro")]
check("chain: a gone macro inside a played macro is found", ids([play("b.macro")]) == ["chain:inner gone"])
MACROS["loop1.macro"] = [play("loop2.macro")]
MACROS["loop2.macro"] = [play("loop1.macro"), play("Deep gone.macro")]
reads.clear()
check("chain: macros playing each other are read once each (no endless loop)",
      ids([play("loop1.macro")]) == ["chain:deep gone"] and sorted(reads) == ["loop1.macro", "loop2.macro"], reads)
check("chain: a broken macro file is skipped (told when it plays)", ids([play("broken.macro")]) == [])
chain = {f"d{i}.macro": [play(f"d{i + 1}.macro")] for i in range(10)}
chain["d10.macro"] = [play("Bottom gone.macro")]
MACROS.update(chain)
check("chain: deeper than the limit isn't looked into", ids([play("d0.macro")], depth=3) == []
      and ids([play("d0.macro")], depth=20) == ["chain:bottom gone"])

# ---- steps with no picture
check("picture: a Wait for a picture with no picture", ids([{"kind": "wait_picture", "id": "w1"}]) == ["steppic:w1"])
check("picture: a colour check counts as a picture", ids([{"kind": "wait_picture", "id": "w1", "color_on": True}]) == [])
check("picture: If / Retry look at their condition", ids([{"kind": "if", "id": "i1", "condition": {}, "steps": []},
                                                           {"kind": "retry", "id": "r1", "condition": {"png": "x"},
                                                            "steps": []}]) == ["steppic:i1"])
check("picture: the words say which step", "An \"If\" step has no picture" in mc.step_problems(
    [{"kind": "if", "id": "i1", "condition": {}, "steps": []}], find, read)[0][2])

# ---- Go to, Else, other macros, Type text
check("goto: no Label to jump to", ids([{"kind": "goto", "id": "g1", "label": "top"}]) == ["goto:g1"])
check("goto: a Label that is there", ids([{"kind": "label", "name": "top"}, {"kind": "goto", "id": "g1", "label": "top"}])
      == [])
check("goto: a turned-off Label doesn't count", ids([{"kind": "label", "name": "top", "off": True},
                                                     {"kind": "goto", "id": "g1", "label": "top"}]) == ["goto:g1"])
check("else: right after an If is fine", ids([{"kind": "if", "id": "i", "condition": {"png": "x"}, "steps": []},
                                              {"kind": "else", "id": "e", "steps": []}]) == [])
check("else: on its own is a problem", ids([{"kind": "else", "id": "e", "steps": []}]) == ["else:e"])
key = next(iter(mc.step_more.MACRO_KEYS))
check("other macros a step plays: a gone one is told", ids([{"kind": "wait", "id": "x", key: "Then gone.macro"}])
      == ["then:then gone"], key)
typing = [{"kind": "type", "id": "t", "window": {"exe": "Notepad.exe"}}]
check("type: a closed program is a maybe", mc.step_problems(typing, find, read, lambda exe: False)[0][:2]
      == ("window:notepad.exe", mc.MAYBE))
check("type: an open program is fine", ids(typing, open_programs={"Notepad.exe"}) == [])
check("type: not looked at when there's no way to look (not Windows)", ids(typing) == [])

# ---- don't warn me again
store = {}
mc.set_ignored(store, "main", "screen", True)
mc.set_ignored(store, "main", "game", True)
check("ignore: kept per macro, sorted", store == {"main": ["game", "screen"]} and mc.ignored(store, "main") == {"game", "screen"})
check("ignore: other macros aren't touched", mc.ignored(store, "other") == set())
mc.set_ignored(store, "main", "game", False)
check("ignore: warn me again takes it off", mc.ignored(store, "main") == {"screen"})
mc.set_ignored(store, "main", "screen", False)
check("ignore: an empty list is removed", store == {})
check("ignore: odd saved values give nothing", mc.ignored({"m": "screen"}, "m") == set()
      and mc.ignored({"m": [1, "ok"]}, "m") == {"ok"} and mc.ignored(None, "m") == set())
store = {"old": ["a"]}
mc.rename_ignored(store, "old", "new")
check("ignore: a renamed macro keeps its list", store == {"new": ["a"]})
mc.rename_ignored(store, "missing", "x")
check("ignore: renaming one with nothing is fine", store == {"new": ["a"]})

# ---- screen size (moved here unchanged)
check("screen: much smaller is far off", mc.screen_far_off((3840, 2160), (1280, 720)))
check("screen: same size and 16:10 are fine", not mc.screen_far_off((1920, 1080), (1920, 1080))
      and not mc.screen_far_off((1920, 1080), (1920, 1200)))
check("screen: another shape (4:3 against 16:9) is far off", mc.screen_far_off((1440, 1080), (1920, 1080)))
check("screen: odd sizes don't crash", not mc.screen_far_off((0, 0), (1920, 1080)) and not mc.screen_far_off(None, (1, 1)))

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
