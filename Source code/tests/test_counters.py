"""Counters (stage 2a): the one place that adds to / sets a counter under the lock and keeps it within +-1e9.
No windows, no settings, no screen: plain functions on a dict and a lock."""
import sys
import threading

src = sys.argv[1]
sys.path.insert(0, src)
import counters  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


vals, lock = {}, threading.Lock()
check("add: a counter that isn't there starts at 0", counters.add(vals, lock, "Wins", 2) == 2 and vals == {"Wins": 2}, vals)
check("add: adds to what is there", counters.add(vals, lock, "Wins", 3) == 5 and vals["Wins"] == 5)
check("add: a negative amount takes away", counters.add(vals, lock, "Wins", -7) == -2 and vals["Wins"] == -2)
vals["Big"] = counters.COUNTER_MAX - 1
check("add: stops at +1,000,000,000", counters.add(vals, lock, "Big", 50) == 10 ** 9 and vals["Big"] == 10 ** 9)
vals["Low"] = -counters.COUNTER_MAX + 1
check("add: stops at -1,000,000,000", counters.add(vals, lock, "Low", -50) == -10 ** 9)
check("set: stores the value as it is, also 2 decimals", counters.set_value(vals, lock, "Half", 3.5) == 3.5 and vals["Half"] == 3.5)
check("set: replaces what was there", counters.set_value(vals, lock, "Wins", 0) == 0 and vals["Wins"] == 0)
check("the other counters are left alone", vals["Half"] == 3.5 and vals["Big"] == 10 ** 9)

# two threads (Picture watch counting + a counter step) must not lose counts
shared, shared_lock = {}, threading.Lock()


def worker():
    for _ in range(20000):
        counters.add(shared, shared_lock, "Drops", 1)


threads = [threading.Thread(target=worker) for _ in range(4)]
for t in threads:
    t.start()
for t in threads:
    t.join()
check("threads: 4 x 20000 adds lose none", shared["Drops"] == 80000, shared)

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
