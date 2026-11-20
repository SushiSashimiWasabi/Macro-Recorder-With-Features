"""Profile rules (mixin batch 2): which settings belong in a profile, profile names, and which background and
Picture watch pictures the profiles use. No windows, no settings file."""
import sys

src = sys.argv[1]
sys.path.insert(0, src)
import profile_rules as pr  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


# ---- what belongs in a profile
check("in: a play option", pr.in_profile("speed") and pr.in_profile("loop"))
check("out: this PC's things", not any(pr.in_profile(k) for k in ("macro_library", "stats_all", "trusted_steps",
                                                                     "profiles", "profile_active", "check_ignore")))
check("out: the phone remote and window places", not pr.in_profile("remote_token") and not pr.in_profile("main_geometry")
      and not pr.in_profile("video_rect_x"))
check("in: which background a window shows", pr.in_profile("background_main_picture")
      and pr.in_profile("settings_background_general_picture"))
check("out: the shared background list and GIF options", not pr.in_profile("background_library")
      and not pr.in_profile("background_fps"))
check("background key: only the per-window ones", pr.is_background_key("background_dim")
      and not pr.is_background_key("background_library") and not pr.is_background_key("speed"))
part = pr.profile_part({"speed": 2, "watch_pictures": [{"file": "a"}], "macro_library": ["x"]})
check("part: only profile keys", part == {"speed": 2, "watch_pictures": [{"file": "a"}]})
src_list = {"watch_pictures": [{"file": "a"}]}
pr.profile_part(src_list)["watch_pictures"].append("changed")
check("part: a copy, not the same lists", src_list["watch_pictures"] == [{"file": "a"}])

# ---- names
check("name: spaces tidied", pr.clean_name("  My   farm ") == "My farm")
check("name: cut to the limit", len(pr.clean_name("x" * 60)) == pr.NAME_MAX)
check("name: empty", pr.clean_name("   ") == "")
check("name: '(none)' is not a name", pr.clean_name(" (none) ") == "")
check("name: not text", pr.clean_name(5) == "5")
check("free: base when free", pr.free_name("My settings", {"x"}) == "My settings")
check("free: the next number", pr.free_name("My settings", {"My settings", "My settings 2"}) == "My settings 3")
check("free: a gap is used", pr.free_name("My settings", {"My settings", "My settings 3"}) == "My settings 2")

# ---- background pictures in profiles
profs = {"A": {"background_main_picture": "cat.png", "speed": 1, "background_main_part": "cat.png"},
         "B": {"settings_background_general_picture": "cat.png"},
         "C": {"background_main_picture": "dog.png"},
         "D": "broken",
         "E": {"background_library": "cat.png"}}
check("using: other profiles that show it", pr.using_background(profs, "A", "cat.png") == ["B"])
check("using: none in use = all of them", pr.using_background(profs, None, "cat.png") == ["A", "B"])
check("using: a picture nobody shows", pr.using_background(profs, None, "fish.png") == [])
pr.forget_background(profs, "cat.png")
check("forget: no profile shows it", profs["A"]["background_main_picture"] == ""
      and profs["B"]["settings_background_general_picture"] == "")
check("forget: others and the shared list stay", profs["C"]["background_main_picture"] == "dog.png"
      and profs["E"]["background_library"] == "cat.png" and profs["A"]["speed"] == 1 and profs["D"] == "broken")
check("forget: only the picture options", profs["A"]["background_main_part"] == "cat.png")

# ---- Picture watch pictures the profiles need
profs = {"A": {"watch_pictures": [{"file": "a.png", "confirm_file": "c.png"}, "junk", {"file": ""}]},
         "B": {"result_pictures": [{"file": "r.png"}], "watch_pictures": None},
         "C": {}}
check("watched: every file once", pr.watched_pictures(profs) == {"a.png", "c.png", "r.png"}, pr.watched_pictures(profs))
check("watched: no profiles", pr.watched_pictures({}) == set())

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
