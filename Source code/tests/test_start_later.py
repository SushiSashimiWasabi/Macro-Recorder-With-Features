"""Start playing later rules (mixin batch 1): the saved schedule read safely, what's due now, one start when the
alarm and the timer go off together, what a start changes, and what opening the app does to a timer. No windows,
no settings file, no real clock: every time is made up."""
import sys
import time

src = sys.argv[1]
sys.path.insert(0, src)
import start_later as sl  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


def at(h, m, day=20):
    return time.mktime((2026, 11, day, h, m, 0, 0, 0, -1))


# ---- reading the saved schedule
sc = sl.clean_schedule(None)
check("schedule: nothing saved = the defaults", sc == sl.SCHEDULE_DEFAULTS, sc)
sc = sl.clean_schedule({"alarm_on": "yes", "daily": 1, "timer_on": True, "alarm": "7:5", "timer_min": "45",
                        "when": "game", "open": "Roblox", "macro": "Rejoin", "timer_from": "12.5", "alarm_last": None})
check("schedule: only a real True turns a switch on", not sc["alarm_on"] and not sc["daily"] and sc["timer_on"], sc)
check("schedule: the alarm time is tidied", sc["alarm"] == "07:05")
check("schedule: numbers and words come through", sc["timer_min"] == 45 and sc["when"] == "game" and sc["open"] == "Roblox"
      and sc["macro"] == "Rejoin" and sc["timer_from"] == 12.5 and sc["alarm_last"] == "")
sc = sl.clean_schedule({"alarm": "25:99", "timer_min": 9999, "when": "explode", "timer_from": "soon"})
check("schedule: bad values fall back", sc["alarm"] == "07:00" and sc["timer_min"] == 24 * 60 and sc["when"] == "play"
      and sc["timer_from"] == 0.0, sc)
check("schedule: a repeating timer is at least the minimum",
      sl.clean_schedule({"timer_repeat": True, "timer_min": 1})["timer_min"] == sl.TIMER_REPEAT_MIN)
check("schedule: the defaults are never changed by reading", sl.SCHEDULE_DEFAULTS["alarm"] == "07:00"
      and sl.SCHEDULE_DEFAULTS["timer_on"] is False)

# ---- what's due
alarm = dict(sl.SCHEDULE_DEFAULTS, alarm_on=True, alarm="21:30")
check("alarm: due exactly at the time", sl.due(alarm, at(21, 30)) == (True, False, False))
check("alarm: due up to 10 minutes late", sl.due(alarm, at(21, 39))[0] and not sl.due(alarm, at(21, 40))[0])
check("alarm: not before the time", not sl.due(alarm, at(21, 29))[0])
check("alarm: not twice the same day", not sl.due(dict(alarm, alarm_last="2026-11-20"), at(21, 31))[0])
check("alarm: again the next day", sl.due(dict(alarm, alarm_last="2026-11-20"), at(21, 31, day=21))[0])
check("alarm: off = never", not sl.due(dict(alarm, alarm_on=False), at(21, 30))[0])
timer = dict(sl.SCHEDULE_DEFAULTS, timer_on=True, timer_min=30, timer_from=at(20, 0))
check("timer: due when the minutes are up", sl.due(timer, at(20, 30)) == (False, True, False))
check("timer: not a second early", not sl.due(timer, at(20, 30) - 1)[1])
check("timer: no start time = not due", not sl.due(dict(timer, timer_from=0.0), at(23, 0))[1])
check("timer: the clock went back = not due, and says so", sl.due(timer, at(20, 0) - 120) == (False, False, True))
check("timer: up to a minute ahead is not 'the clock went back'", sl.due(timer, at(20, 0) - 59)[2] is False)

# ---- one start for both, and what it changes
both = dict(alarm, timer_on=True, timer_min=30, timer_from=at(21, 0) + 20)
a, t, ch = sl.one_start(both, True, False, at(21, 30))
check("together: a timer due within a minute joins the alarm", a and t, (a, t))
a, t, ch = sl.one_start(dict(both, timer_from=at(21, 0) + 70), True, False, at(21, 30))
check("together: a timer more than a minute away doesn't", a and not t)
a, t, ch = sl.one_start(dict(timer, alarm_on=True, alarm="20:30"), False, True, at(20, 30) + 30)
check("together: an alarm within a minute joins the timer", a and t)
a, t, ch = sl.one_start(dict(timer, alarm_on=True, alarm="20:32"), False, True, at(20, 30))
check("together: an alarm 2 minutes away doesn't", t and not a)
_a, _t, ch = sl.one_start(alarm, True, False, at(21, 30))
check("changes: a once-alarm turns off and remembers today", ch == {"alarm_last": "2026-11-20", "alarm_on": False}, ch)
_a, _t, ch = sl.one_start(dict(alarm, daily=True), True, False, at(21, 30))
check("changes: a daily alarm stays on", ch == {"alarm_last": "2026-11-20"}, ch)
_a, _t, ch = sl.one_start(timer, False, True, at(20, 30))
check("changes: a once-timer turns off", ch == {"timer_on": False}, ch)
_a, _t, ch = sl.one_start(dict(timer, timer_repeat=True), False, True, at(20, 30))
check("changes: a repeating timer starts again from now", ch == {"timer_from": at(20, 30)}, ch)

# ---- when the app opens
check("open: a running timer is left alone", sl.on_open(dict(timer, timer_from=at(20, 0)), at(20, 10)) == ({}, False))
check("open: a timer with no start time starts now", sl.on_open(dict(timer, timer_from=0.0), at(20, 10))
      == ({"timer_from": at(20, 10)}, False))
check("open: a once-timer that ran out while closed turns off", sl.on_open(timer, at(22, 0)) == ({"timer_on": False}, True))
check("open: a repeating timer that ran out starts again", sl.on_open(dict(timer, timer_repeat=True), at(22, 0))
      == ({"timer_from": at(22, 0)}, True))
check("open: ran out less than a minute ago = still left alone", sl.on_open(timer, at(20, 31) - 1) == ({}, False))
check("open: timer off = nothing", sl.on_open(dict(timer, timer_on=False), at(23, 0)) == ({}, False))

# ---- typing a time (moved here unchanged)
now = at(20, 0)
check("parse: 21:30 today", sl.parse_when("21:30", now) == at(21, 30))
check("parse: a time already past = tomorrow", sl.parse_when("19:00", now) == at(19, 0) + 86400)
check("parse: in 15 / +15 / 15 min", sl.parse_when("in 15", now) == sl.parse_when("+15", now) == sl.parse_when("15 min", now)
      == now + 900)
check("parse: nonsense, 0 and more than a day refused", sl.parse_when("soon", now) is None and sl.parse_when("0", now) is None
      and sl.parse_when("1441", now) is None and sl.parse_when("25:00", now) is None)
check("clean_hhmm: 7:5 -> 07:05, bad ones refused", sl.clean_hhmm("7:5") == "07:05" and sl.clean_hhmm("24:00") is None
      and sl.clean_hhmm(None) is None)

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
