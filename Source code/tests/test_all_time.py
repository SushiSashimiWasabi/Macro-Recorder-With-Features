"""All-time results (mixin batch 1): a session's runs added to the saved all-time results, and the guard that makes
a broken saved number count as 0 instead of stopping the adding. No windows, no settings file."""
import sys

src = sys.argv[1]
sys.path.insert(0, src)
import stats  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


def session(*runs, started=1000.0):
    s = stats.Session("m")
    s.started = started
    for status, frags in runs:
        s.add(status, 30, frags)
    return s


W, L, U = stats.WIN, stats.LOSS, stats.UNKNOWN
a = {}
stats.add_to_all_time(a, session((W, 2), (L, 0), (U, 1), (W, 0)), 1000.0 + 125.7)
check("adds: runs, wins, losses, unknown, fragments, whole seconds", a == {"runs": 4, "wins": 2, "losses": 1, "unknown": 1,
                                                                         "fragments": 3, "seconds": 125}, a)
stats.add_to_all_time(a, session((W, 1)), 1000.0 + 10)
check("adds: on top of what was saved", a["runs"] == 5 and a["wins"] == 3 and a["fragments"] == 4 and a["seconds"] == 135, a)
a = {"best_streak": 7, "streak_now": 2, "runs": 1}
stats.add_to_all_time(a, session((L, 0)), 1000.0)
check("adds: other saved values are left alone", a["best_streak"] == 7 and a["streak_now"] == 2 and a["runs"] == 2, a)
a = {"runs": "12"}
stats.add_to_all_time(a, session((W, 0)), 1000.0)
check("adds: a number saved as text still counts", a["runs"] == 13, a)
for bad in ("lots", None, [1], float("inf"), float("nan")):
    a = {"runs": bad, "wins": bad, "losses": bad, "unknown": bad, "fragments": bad, "seconds": bad}
    try:
        stats.add_to_all_time(a, session((W, 1)), 1000.0 + 5)
        ok = a == {"runs": 1, "wins": 1, "losses": 0, "unknown": 0, "fragments": 1, "seconds": 5}
    except Exception as exc:  # noqa: BLE001
        a, ok = exc, False
    check(f"fix: a broken saved value ({bad!r}) counts as 0, no crash", ok, a)

check("saved_number: good numbers come through", stats.saved_number("2.5") == 2.5 and stats.saved_number(7) == 7.0)
check("saved_number: broken, endless and too big give 0", all(stats.saved_number(v) == 0.0 for v in
                                                              ("x", None, float("inf"), float("-inf"), float("nan"), 10 ** 400)))

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
