"""Phone remote rules (mixin batch 2): what a typed /speed, /repeat and /schedule mean, which name a part of a
name picks, and the /pair code check. No windows, no Discord, no settings file."""
import sys

src = sys.argv[1]
sys.path.insert(0, src)
import remote_rules as rr  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


# ---- /speed
check("speed: a number", rr.parse_speed("1.5") == (1.5, None))
check("speed: rounded to 2 places", rr.parse_speed("1.234")[0] == 1.23)
check("speed: the limits are in", rr.parse_speed(0.1)[0] == 0.1 and rr.parse_speed("10")[0] == 10.0)
check("speed: just over the limits is out", rr.parse_speed(10.01)[0] is None and rr.parse_speed(0.09)[0] is None)
check("speed: not a number says how", rr.parse_speed("fast") == (None, "Give a speed like 1, 1.5 or 0.5."))
check("speed: nothing given says how", rr.parse_speed(None)[1] == "Give a speed like 1, 1.5 or 0.5.")
check("speed: endless / not-a-number are out", rr.parse_speed("inf")[0] is None and rr.parse_speed("nan")[0] is None)
check("speed: out of range names the limits", rr.parse_speed(50)[1] == "The speed must be between 0.1 and 10.")

# ---- /repeat
check("repeat: loop words = 0 (loop)", all(rr.parse_repeat(w) == (0, None) for w in ("loop", " LOOP ", "forever",
                                                                                       "always", "0")))
check("repeat: a number of times", rr.parse_repeat("25") == (25, None) and rr.parse_repeat(" 7 ") == (7, None))
check("repeat: a decimal is cut", rr.parse_repeat("2.9") == (2, None))
check("repeat: the limits", rr.parse_repeat("1")[0] == 1 and rr.parse_repeat("9999")[0] == 9999)
check("repeat: over the limit", rr.parse_repeat("10000") == (None, "The number of times must be between 1 and 9999."))
check("repeat: 0.5 is cut to 0, below 1", rr.parse_repeat("0.5")[1] == "The number of times must be between 1 and 9999.")
check("repeat: below 1",rr.parse_repeat("-3")[1] == "The number of times must be between 1 and 9999.")
check("repeat: words say how", rr.parse_repeat("lots") == (None, "Give a number of times (1 to 9999), or loop."))
check("repeat: nothing given says how", rr.parse_repeat(None)[1] == "Give a number of times (1 to 9999), or loop.")
# bug fix (batch 2): "inf" made int() raise OverflowError, so the command broke and Discord got no answer
check("repeat: inf says how (no crash)", rr.parse_repeat("inf") == (None, "Give a number of times (1 to 9999), or loop."))
check("repeat: 1e400 says how (no crash)", rr.parse_repeat("1e400")[0] is None)

# ---- a name from a part of it
names = ["Farm", "farm 2", "Rejoin from disconnect", "Rejoin"]
check("name: the whole name, any case, comes first", rr.pick_name(names, "REJOIN") == "Rejoin")
check("name: else the first that holds it", rr.pick_name(names, "arm") == "Farm")
check("name: a whole name beats an earlier part match", rr.pick_name(["farm 2", "Farm"], "farm") == "Farm")
check("name: none holds it", rr.pick_name(names, "zzz") is None)
check("name: empty picks nothing", rr.pick_name(names, "") is None)
check("name: no names", rr.pick_name([], "farm") is None)
check("name: a dict's keys are the names", rr.pick_name({"Farm": "/a", "B": "/b"}, "b") == "B")

# ---- /schedule
check("schedule: a cancel word", rr.schedule_options(" Off ") == {"cancel": True})
check("schedule: a time alone is the alarm", rr.schedule_options("21:30") == {"alarm": "21:30"})
check("schedule: nothing = show what's planned", rr.schedule_options(None) == {} and rr.schedule_options("") == {})
check("schedule: options pass through", rr.schedule_options({"timer": 5}) == {"timer": 5})
ch, err = rr.schedule_changes({"alarm": "7:5", "every_day": True}, 100.0)
check("schedule: alarm set and tidied", err is None and ch == {"alarm_on": True, "alarm": "07:05", "alarm_last": "",
                                                               "daily": True}, ch)
check("schedule: alarm off words", rr.schedule_changes({"alarm": "OFF"}, 0)[0] == {"alarm_on": False})
check("schedule: a bad alarm says how", rr.schedule_changes({"alarm": "25:00"}, 0) == (None, rr.ALARM_HELP))
check("schedule: an alarm that isn't text says how", rr.schedule_changes({"alarm": 5}, 0) == (None, rr.ALARM_HELP))
check("schedule: a blank alarm is ignored", rr.schedule_changes({"alarm": "  "}, 0) == ({}, None))
ch, _ = rr.schedule_changes({"timer": 5000, "repeat": True}, 123.0)
check("schedule: timer capped at a day, starts now", ch == {"timer_on": True, "timer_min": 1440, "timer_from": 123.0,
                                                            "timer_repeat": True}, ch)
check("schedule: timer 0 or less is off", rr.schedule_changes({"timer": 0}, 0)[0] == {"timer_on": False}
      and rr.schedule_changes({"timer": -5}, 0)[0] == {"timer_on": False})
check("schedule: a bad timer says how", rr.schedule_changes({"timer": "x"}, 0)[1] == "Give the timer in minutes (0 = off).")
check("schedule: an endless timer says how", rr.schedule_changes({"timer": 1e400}, 0)[1] is not None)
check("schedule: cancel turns both off", rr.schedule_changes({"cancel": True}, 0)[0] == {"alarm_on": False,
                                                                                         "timer_on": False})
check("schedule: open the game first", rr.schedule_changes({"open_game": True}, 0)[0] == {"when": "game"}
      and rr.schedule_changes({"open_game": False}, 0)[0] == {"when": "play"})
check("schedule: only real yes / no switches count", rr.schedule_changes({"every_day": "y", "repeat": 1}, 0)[0] == {})

# ---- /pair
check("pair: the right code", rr.check_code("123456", "123456", 2) == (True, 0, True))
check("pair: spaces and other signs don't count", rr.check_code("123 456!", "123456", 0)[0])
check("pair: nothing typed is wrong", rr.check_code(None, "123456", 0) == (False, 1, False))
check("pair: a wrong try counts", rr.check_code("111111", "123456", 3) == (False, 4, False))
check("pair: the 5th wrong try makes a new code", rr.check_code("111111", "123456", 4) == (False, 0, True))
check("pair: a part of the code is wrong", not rr.check_code("123", "123456", 0)[0])

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
