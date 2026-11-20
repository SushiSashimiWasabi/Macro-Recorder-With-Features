"""Late results (stage 2b): the rules that decide which run a late MISSION COMPLETED / FAILED belongs to.
No windows, no screen, no files: plain functions on numbers and a real stats.Session."""
import sys

src = sys.argv[1]
sys.path.insert(0, src)
import late_results  # noqa: E402
import stats  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


LIMIT = 30.0

# ---- how long after an Unknown run its result may still show
check("window: no runs known yet gives the whole limit", late_results.window([], LIMIT) == LIMIT)
check("window: usual runs of 100 s give the limit (half is more than 30)", late_results.window([100, 100, 100], LIMIT) == LIMIT)
check("window: short runs of 20 s give half the usual run", late_results.window([20, 20, 20], LIMIT) == 10.0)
check("window: never under 1 second", late_results.window([0.5, 0.5], LIMIT) == 1.0)
check("window: the middle run counts, not the average", late_results.window([10, 10, 100], LIMIT) == 5.0)
check("window: only the last 10 runs count", late_results.window([5] * 5 + [100] * 10, LIMIT) == LIMIT)

# ---- does a result that shows now belong to that unknown run?
late = {"ended": 100.0, "index": 0, "window": 20.0}
check("due: a win 5 s later belongs to it", late_results.due(late, stats.WIN, 105.0, LIMIT))
check("due: a loss belongs to it too", late_results.due(late, stats.LOSS, 105.0, LIMIT))
check("due: too late (over its window) does not", not late_results.due(late, stats.WIN, 121.0, LIMIT))
check("due: exactly at the end of the window still does", late_results.due(late, stats.WIN, 120.0, LIMIT))
check("due: an unknown result never does", not late_results.due(late, stats.UNKNOWN, 105.0, LIMIT))
check("due: nothing waiting means no", not late_results.due(None, stats.WIN, 105.0, LIMIT))
check("due: already given once means no", not late_results.due(dict(late, given=True), stats.WIN, 105.0, LIMIT))
check("due: without its own window the limit is used", late_results.due({"ended": 0.0, "index": 0}, stats.WIN, 29.0, LIMIT)
      and not late_results.due({"ended": 0.0, "index": 0}, stats.WIN, 31.0, LIMIT))

# ---- giving it to the run
s = stats.Session()
s.add(stats.WIN, 70)
s.add(stats.UNKNOWN, 60)
late_results.apply(s, {"index": 1}, stats.WIN)
check("apply: the unknown run becomes a win, its time stays", s.runs[1] == (stats.WIN, 60) and s.streak == 2, (s.runs, s.streak))
s2 = stats.Session()
s2.add(stats.WIN, 70)
s2.add(stats.UNKNOWN, 60)
late_results.apply(s2, {"index": 1}, stats.LOSS)
check("apply: a loss makes it a loss and ends the streak", s2.runs[1] == (stats.LOSS, 60) and s2.streak == 0, (s2.runs, s2.streak))
s3 = stats.Session()
s3.add(stats.WIN, 70)
late_results.apply(s3, {"index": 0}, stats.LOSS)
check("apply: a run that already has a result is left alone", s3.runs == [(stats.WIN, 70)] and s3.streak == 1, (s3.runs, s3.streak))
late_results.apply(s3, {"index": 9}, stats.WIN)
check("apply: an index that isn't there changes nothing", s3.runs == [(stats.WIN, 70)] and s3.streak == 1)

# ---- the short run that follows is only the results screen
check("leftover: a short run after it is only the results screen", late_results.is_leftover({"window": 20.0}, 5.0, LIMIT))
check("leftover: a run as long as the window is a real run", not late_results.is_leftover({"window": 20.0}, 20.0, LIMIT))
check("leftover: nothing waiting means no", not late_results.is_leftover(None, 1.0, LIMIT))
check("leftover: without its own window the limit is used", late_results.is_leftover({"index": 0}, 29.0, LIMIT)
      and not late_results.is_leftover({"index": 0}, 30.0, LIMIT))
check("leftover: an empty note counts as nothing waiting (as before)", not late_results.is_leftover({}, 1.0, LIMIT))

s4 = stats.Session()
s4.add(stats.UNKNOWN, 60, 1)
check("fragments: the short run's fragments go to the run before", late_results.add_fragments(s4, {"index": 0}, 2)
      and s4.fragments == [3], s4.fragments)
check("fragments: none to hand over changes nothing", not late_results.add_fragments(s4, {"index": 0}, 0) and s4.fragments == [3])
check("fragments: an index that isn't there changes nothing", not late_results.add_fragments(s4, {"index": 5}, 2) and s4.fragments == [3])

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
