"""Stop by itself and the Discord summary rules (mixin batch 2): the saved options read safely, when to stop, why a
run was the last, the Settings lines, when a summary is due and its card text. No windows, no settings file, no
real clock: every time is made up."""
import sys
import time

src = sys.argv[1]
sys.path.insert(0, src)
import auto_stop as au  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


def at(h, m, day=20):
    return time.mktime((2026, 11, day, h, m, 0, 0, 0, -1))


# ---- HH:MM
check("time: tidied", au.wrap_hhmm("7:5") == "07:05")
check("time: hours wrap at 24, minutes at 60", au.wrap_hhmm("25:70") == "01:10")
check("time: not a time", au.wrap_hhmm("x") is None and au.wrap_hhmm("") is None and au.wrap_hhmm("1:2:3") is None
      and au.wrap_hhmm(None) is None)

# ---- the saved Stop by itself options
a = au.clean_settings(None)
check("settings: nothing saved = off, nothing set", a == {"on": False, "runs": 0, "fragments": 0, "minutes": 0.0,
                                                          "at": "", "finish_run": True, "then": "nothing", "warn": True}, a)
a = au.clean_settings({"on": 1, "runs": "12", "fragments": 3.7, "minutes": "30", "at": " 3:30 ", "then": "sleep",
                       "finish_run": False, "warn": 0})
check("settings: values come through", a == {"on": True, "runs": 12, "fragments": 3, "minutes": 30.0, "at": "03:30",
                                              "finish_run": False, "then": "sleep", "warn": False}, a)
a = au.clean_settings({"runs": "x", "fragments": -5, "minutes": "lots", "at": "soon", "then": "explode"})
check("settings: bad values fall back", (a["runs"], a["fragments"], a["minutes"], a["at"], a["then"])
      == (0, 0, 0.0, "", "nothing"), a)
check("settings: big numbers are capped", au.clean_settings({"runs": 1e12, "minutes": 1e12})["runs"] == au.COUNT_MAX
      and au.clean_settings({"minutes": 1e12})["minutes"] == au.MINUTES_MAX)
# bug fix (batch 2): a broken / endless minutes value in the file became "stop after 100000 min"
check("settings: endless minutes = not used", au.clean_settings({"minutes": float("inf")})["minutes"] == 0.0)
check("settings: not-a-number minutes = not used", au.clean_settings({"minutes": float("nan")})["minutes"] == 0.0)
check("settings: endless runs = not used", au.clean_settings({"runs": float("inf")})["runs"] == 0)
# (before: a list or dict as "then" crashed the check, so Play couldn't start)
check("settings: a list as 'then' = nothing", au.clean_settings({"then": ["sleep"]})["then"] == "nothing")

# ---- the Settings line
base = au.clean_settings({"on": True})
check("text: on but nothing set = Off", au.settings_text(base) == "Off")
check("text: off = Off", au.settings_text(dict(base, on=False, runs=3)) == "Off")
check("text: runs, then close", au.settings_text(dict(base, runs=3, then="close")) == "After 3 runs, then close the game")
check("text: all of them", au.settings_text(dict(base, runs=25, fragments=2, minutes=7.5, at="03:30", then="shutdown"))
      == "After 25 runs or 2 fragments or 7.5 min or at 03:30, then shut down")
check("text: only a time", au.settings_text(dict(base, at="03:30", then="sleep")) == "At 03:30, then sleep")

# ---- the plan for a playback
check("plan: off = none", au.plan(dict(base, on=False, runs=3), at(12, 0)) is None)
check("plan: on with nothing set = none", au.plan(base, at(12, 0)) is None)
p = au.plan(dict(base, runs=3), at(12, 0))
check("plan: runs only has no deadline", p["deadline"] is None and p["cancelled"] is False and p["due"] is None)
check("plan: minutes from now", au.plan(dict(base, minutes=30), at(12, 0))["deadline"] == at(12, 30))
check("plan: a time later today", au.plan(dict(base, at="18:00"), at(12, 0))["deadline"] == at(18, 0))
check("plan: a time already past = tomorrow", au.plan(dict(base, at="09:00"), at(12, 0))["deadline"] == at(9, 0, 21))
check("plan: the time right now = tomorrow", au.plan(dict(base, at="12:00"), at(12, 0))["deadline"] == at(12, 0, 21))
check("plan: the first of minutes and time", au.plan(dict(base, minutes=30, at="12:10"), at(12, 0))["deadline"]
      == at(12, 10))
check("plan: the saved options are not changed", "deadline" not in base)

# ---- why a run was the last
p = au.plan(dict(base, runs=3, fragments=2), at(12, 0))
check("due: not yet", au.stop_reason(p, 2, 1) is None)
check("due: runs reached", au.stop_reason(p, 3, 0) == "3 runs were played")
check("due: fragments reached", au.stop_reason(p, 1, 2) == "2 divine fragments dropped")
check("due: one fragment", au.stop_reason(dict(p, fragments=1), 0, 1) == "1 divine fragment dropped")
check("due: runs win over fragments", au.stop_reason(p, 5, 5) == "3 runs were played")
check("due: the time was reached", au.stop_reason(dict(p, due="the time you set was reached"), 0, 0)
      == "the time you set was reached")
check("due: runs win over the time", au.stop_reason(dict(p, due="the time"), 3, 0) == "3 runs were played")
check("due: cancelled (/keepgoing) never stops", au.stop_reason(dict(p, cancelled=True, due="x"), 9, 9) is None)
check("due: no plan never stops", au.stop_reason(None, 9, 9) is None)

# ---- the Discord summary options
s = au.clean_summary(None)
check("summary: nothing saved", s == {"daily": False, "at": "22:00", "weekly": False, "weekday": "Sunday",
                                      "last_daily": None, "last_weekly": None}, s)
s = au.clean_summary({"daily": 1, "at": "7:5", "weekly": True, "weekday": "Friday", "last_daily": "2026-11-19"})
check("summary: values come through", s["daily"] and s["at"] == "07:05" and s["weekday"] == "Friday"
      and s["last_daily"] == "2026-11-19")
check("summary: bad values fall back", au.clean_summary({"at": "soon", "weekday": "Funday"})["at"] == "22:00"
      and au.clean_summary({"weekday": "Funday"})["weekday"] == "Sunday")
check("summary text: off", au.summary_text(au.clean_summary({})) == "Off")
check("summary text: both", au.summary_text(au.clean_summary({"daily": True, "weekly": True, "weekday": "Friday"}))
      == "Every day and every Friday at 22:00")
check("summary text: weekly only", au.summary_text(au.clean_summary({"weekly": True})) == "Every Sunday at 22:00")

# ---- the first one after turning it on
old = au.clean_summary({})
new = {"daily": True, "weekly": True, "at": "22:00"}
check("first: turned on before the time = today", au.first_sent(old, new, "2026-11-20", "21:59") == (None, None))
check("first: turned on after the time = tomorrow", au.first_sent(old, new, "2026-11-20", "22:00")
      == ("2026-11-20", "2026-11-20"))
old = au.clean_summary({"daily": True, "last_daily": "2026-11-18"})
check("first: already on keeps its day", au.first_sent(old, new, "2026-11-20", "23:00")[0] == "2026-11-18")

# ---- due now
s = au.clean_summary({"daily": True, "weekly": True, "weekday": "Friday", "last_daily": "2026-11-19"})
check("due: before the time = nothing", au.due(s, "2026-11-20", "21:59", 4) == [])
check("due: at the time on a Friday = both", au.due(s, "2026-11-20", "22:00", 4) == ["daily", "weekly"])
check("due: not Friday = daily only", au.due(s, "2026-11-20", "23:00", 3) == ["daily"])
check("due: sent today already = nothing", au.due(dict(s, last_daily="2026-11-20", last_weekly="2026-11-20"),
                                                  "2026-11-20", "23:00", 4) == [])
check("due: both off = nothing", au.due(au.clean_summary({}), "2026-11-20", "23:59", 4) == [])

# ---- the card
summ = {"runs": 10, "wins": 7, "losses": 2, "unknown": 1, "winrate": 77.77, "average": 65.0, "best": 50.0,
        "worst": None, "fragments": 3, "fragments_per_hour": 1.234, "seconds": 650.0, "slow": 1}
lines = au.card_lines(summ, 10, 2)
check("card: the numbers", lines[0] == "**Runs** 10  ·  **Won** 7  ·  **Failed** 2  ·  **Unknown** 1"
      and lines[1].startswith("**Win rate** 77.8%") and "**Longest** -" in lines[2]
      and lines[3] == "**Divine fragments** 3  (1.23 an hour)", lines)
check("card: slow runs and reconnects", "**Unusually slow runs** 1" in lines and lines[-1] == "**Reconnects** 2")
check("card: no kept runs = only the count", au.card_lines(None, 4, 0) == ["**Runs** 4"])
check("card: no win rate", "**Win rate** -" in au.card_lines(dict(summ, winrate=None), 10, 0)[1])
week = [("2026-11-14", {"runs": 3}), ("2026-11-15", {"runs": 9}), ("2026-11-16", {"runs": 9})]
lines = au.card_lines(None, 21, 0, week, {"runs": ("2026-11-01", 40), "fragments": ("2026-11-02", 7)})
check("card: weekly best day (the first of a tie)", "**Best day this week** 2026-11-15 with 9 runs" in lines, lines)
check("card: weekly records", lines[-1] == "**Record day** 2026-11-01: 40 runs  ·  most fragments 2026-11-02: 7")
check("card: weekly without records", len(au.card_lines(None, 21, 0, week, {})) == 2)

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
