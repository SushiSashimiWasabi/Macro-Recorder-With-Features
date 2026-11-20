"""Milestone rules (mixin pilot): totals, wins in a row, which milestones are reached, the check when one is
added. No windows, no settings file: plain functions on made-up numbers."""
import sys

src = sys.argv[1]
sys.path.insert(0, src)
import milestones  # noqa: E402
import stats  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


# ---- totals
saved = {"runs": 10, "wins": 7, "fragments": 3, "best_streak": 4, "seconds": 7200}
t = milestones.totals(saved, None, 0)
check("totals: from the saved all-time results", t == {"runs": 10, "wins": 7, "fragments": 3, "streak": 4, "hours": 2.0}, t)
check("totals: nothing saved = all 0", milestones.totals(None, None, 0) == {"runs": 0, "wins": 0, "fragments": 0,
                                                                              "streak": 0, "hours": 0.0})
sess = stats.Session()
sess.started = 1000.0
sess.add(stats.WIN, 30, fragments=2)
sess.add(stats.LOSS, 30)
t = milestones.totals(saved, sess, 1000.0 + 1800)
check("totals: the playing session is added", t["runs"] == 12 and t["wins"] == 8 and t["fragments"] == 5
      and t["hours"] == 2.5, t)
sess.added = True
check("totals: a session already added to the saved results isn't counted twice",
      milestones.totals(saved, sess, 5000)["runs"] == 10)
sess.added = False
check("totals: a clock that went back adds no negative time", milestones.totals(saved, sess, 0)["hours"] == 2.0)
check("totals: a session with no runs yet adds nothing", milestones.totals(saved, stats.Session(), 10 ** 10)["hours"] == 2.0)
# the fix: a broken number in the saved results no longer stops the check (it counts as 0)
bad = {"runs": "lots", "wins": float("inf"), "fragments": None, "best_streak": [1], "seconds": float("nan")}
try:
    t = milestones.totals(bad, None, 0)
    ok = t == {"runs": 0, "wins": 0, "fragments": 0, "streak": 0, "hours": 0.0}
except Exception as exc:  # noqa: BLE001
    t, ok = exc, False
check("totals: broken numbers in the settings count as 0 (no crash)", ok, t)
check("totals: endless seconds count as 0 (no endless hours)",
      milestones.totals({"seconds": float("inf")}, None, 0)["hours"] == 0.0)
check("totals: a whole number too big for the clock counts as 0 (no crash)",
      milestones.totals({"seconds": 10 ** 400}, None, 0)["hours"] == 0.0)
check("totals: numbers saved as text still count", milestones.totals({"runs": "12"}, None, 0)["runs"] == 12)

# ---- wins in a row
W, L, U = stats.WIN, stats.LOSS, stats.UNKNOWN
check("streak: wins add up, from what it was before", milestones.streak([(W, 1), (W, 1)], 3, 5) == (5, 5))
check("streak: a loss ends it", milestones.streak([(W, 1), (L, 1), (W, 1)], 2, 2) == (1, 3))
check("streak: an unknown run doesn't end it", milestones.streak([(W, 1), (U, 1), (W, 1)], 0, 0) == (2, 2))
check("streak: the best one before is kept", milestones.streak([(L, 1)], 4, 9) == (0, 9))
check("streak: no runs = as it was", milestones.streak([], 6, 6) == (6, 6))

# ---- which are reached
today = "2026-11-20"
ms = [{"kind": "runs", "at": 10}, {"kind": "wins", "at": 8}, {"kind": "hours", "at": 3},
      {"kind": "runs", "at": 5, "reached": "2026-01-01"}]
got = milestones.mark_reached(ms, {"runs": 10, "wins": 7, "hours": 2.5}, today)
check("reached: exactly at the number counts", ms[0].get("reached") == today and got == [ms[0]], got)
check("reached: one below doesn't", "reached" not in ms[1] and "reached" not in ms[2])
check("reached: one reached before keeps its date and isn't told again", ms[3]["reached"] == "2026-01-01")
check("reached: a second look tells nothing new", milestones.mark_reached(ms, {"runs": 10, "wins": 7}, today) == [])
odd = ["x", {"kind": "nope", "at": 1}, {"kind": "runs", "at": "abc"}, {"kind": "runs", "at": 1e400}]
check("reached: odd entries are skipped, no crash", milestones.mark_reached(odd, {"runs": 99}, today) == [])

# ---- adding one
have = [{"kind": "wins", "at": 1000}]
check("new: ok, commas allowed", milestones.check_new("wins", " 2,500 ", have) == (2500, ""))
check("new: unknown kind", milestones.check_new("nope", "5", have) == (None, "Choose what it counts."))
check("new: not a number", milestones.check_new("wins", "lots", have)[0] is None)
check("new: 0 and too big are refused", milestones.check_new("wins", "0", have)[0] is None
      and milestones.check_new("wins", str(milestones.MAX_AT + 1), have)[0] is None)
check("new: the biggest allowed is fine", milestones.check_new("runs", str(milestones.MAX_AT), have)[0] == milestones.MAX_AT)
check("new: the same one twice is refused", milestones.check_new("wins", "1000", have)[1]
      == "That milestone is already in the list.")
full = [{"kind": "runs", "at": i} for i in range(1, milestones.MAX_MILESTONES + 1)]
check("new: no more than the limit", milestones.check_new("wins", "5", full)[0] is None)
check("new: one below the limit is fine", milestones.check_new("wins", "5", full[:-1])[0] == 5)

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
