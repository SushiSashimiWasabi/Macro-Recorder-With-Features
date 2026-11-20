"""Discord message rules (mixin batch 3): who is pinged, whether and how a run is sent, and the cards for a
session's end and a disconnect. No windows, no network, no screenshots."""
import sys

src = sys.argv[1]
sys.path.insert(0, src)
import discord_rules as dr  # noqa: E402
import stats  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


# ---- who is pinged
s = {"discord_ping": " <@1> "}
check("ping: problems only by default", dr.ping_for(s, True) == "<@1>" and dr.ping_for(s, False) == "")
check("ping: always", dr.ping_for(dict(s, discord_ping_when="always"), False) == "<@1>")
check("ping: never", dr.ping_for(dict(s, discord_ping_when="never"), True) == "")
check("ping: a fragment drop when asked", dr.ping_for(dict(s, discord_ping_when="never", discord_ping_fragments=True),
                                                      False, dropped=True) == "<@1>")
check("ping: a drop without asking", dr.ping_for(dict(s, discord_ping_when="never"), False, dropped=True) == "")
check("ping: nobody set", dr.ping_for({}, True) == "")

# ---- is a run sent
on = {"discord_enabled": True}
check("run: on = sent", dr.run_wanted(on, False))
check("run: Discord off = never", not dr.run_wanted({"discord_runs": True}, True))
check("run: runs off = not sent", not dr.run_wanted(dict(on, discord_runs=False), False))
check("run: runs off but a fragment ping", dr.run_wanted(dict(on, discord_runs=False, discord_ping_fragments=True), True))
check("run: runs off, a drop, no fragment ping", not dr.run_wanted(dict(on, discord_runs=False), True))

# ---- how a run is sent
live = dict(on, discord_live=True)
check("send: one card that updates", dr.run_send(live, stats.WIN, False, "") == ("live", False))
check("send: a ping gets its own message", dr.run_send(live, stats.WIN, False, "<@1>") == ("own", True))
check("send: blank ping text counts as none", dr.run_send(live, stats.WIN, False, "  ")[0] == "live")
check("send: unknown = own message with a screenshot", dr.run_send(dict(live, discord_screenshot=False), stats.UNKNOWN,
                                                                   False, "") == ("own", True))
check("send: a fragment = own message with a screenshot", dr.run_send(dict(live, discord_screenshot=False), stats.WIN,
                                                                      True, "") == ("own", True))
check("send: no live card, screenshot on by default", dr.run_send(on, stats.LOSS, False, "") == ("own", True))
check("send: screenshots off", dr.run_send(dict(on, discord_screenshot=False), stats.LOSS, False, "") == ("own", False))

# ---- cards
values = {"macro": "Farm", "completed": 3, "failed": 1, "unknown": 0, "winrate": "75.0%", "total": "1:00:00"}
c = dr.session_card(values, "Stopped.", False, True)
check("end card: title and colour", c["title"] == "Farm · Session ended" and c["color"] == dr.END_COLOR)
check("end card: results and runtime", c["description"] == "Stopped.\nCompleted 3 · Failed 1 · Unknown 0 · Win rate 75.0%"
      "\nTotal runtime 1:00:00", c["description"])
c = dr.session_card(values, "Game closed.", True, False)
check("end card: a problem, no results", c["title"] == "Farm · Problem" and c["color"] == dr.PROBLEM_COLOR
      and c["description"] == "Game closed.\nTotal runtime 1:00:00")
c = dr.recovery_card("lost", values, "Disconnected box.", 2)
check("recovery: lost", c["title"] == "Farm · Disconnected" and c["color"] == dr.WARN_COLOR
      and c["description"] == "Disconnected box.\nReconnects this session: 2")
check("recovery: back is green", dr.recovery_card("back", values, "", 0)["color"] == dr.BACK_COLOR
      and dr.recovery_card("back", values, "", 0)["title"] == "Farm · Back in the game")
check("recovery: stuck", dr.recovery_card("stuck", values, "", 0)["title"] == "Farm · A run seems stuck")

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
