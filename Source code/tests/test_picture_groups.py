"""Picture watch group rules (mixin batch 3): the default groups, the Settings line, locked built-in pictures, on /
off after a move, and sorting an old profile's pictures into groups. No windows, no picture files."""
import sys

src = sys.argv[1]
sys.path.insert(0, src)
import picture_groups as pg  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


# ---- the groups
check("default: AOT:R then My pictures", [g["id"] for g in pg.default_groups()] == [pg.AOTR, pg.MINE])
check("default: a new list each time", pg.default_groups() is not pg.default_groups()
      and (pg.default_groups()[0].update(name="x") or pg.default_groups()[0]["name"] == "AOT:R"))
check("fixed: the three", all(pg.fixed_group(g) for g in (pg.GENERAL, pg.AOTR, pg.MINE)) and not pg.fixed_group("g123"))
check("clean: only dicts with an id", pg.clean_groups([{"id": "a"}, {"name": "x"}, "junk", {"id": ""}]) == [{"id": "a"}])
check("clean: not a list", pg.clean_groups({"id": "a"}) == [])
g = pg.with_defaults([{"id": "x", "name": "X"}])
check("defaults: missing ones added after", [x["id"] for x in g] == ["x", pg.AOTR, pg.MINE])
check("defaults: none missing = same", pg.with_defaults(pg.default_groups()) == pg.default_groups())

# ---- the Settings line
groups = [{"id": pg.AOTR, "name": "AOT:R"}, {"id": pg.MINE, "name": "My pictures"}, {"id": "g1", "name": "Off", "on": False},
          {"id": "g2", "name": "Empty"}]
pics = [(pg.AOTR, True), (pg.AOTR, False), (pg.MINE, True), ("g1", True)]
check("summary: on counts, off groups, empty groups left out",
      pg.summary_text(groups, pics) == "AOT:R: 1 of 2 on · My pictures: 1 of 1 on · Off: off", pg.summary_text(groups, pics))
check("summary: nothing", pg.summary_text([], []) == "No pictures yet" and pg.summary_text(groups[3:], []) == "No pictures yet")

# ---- moving
check("locked: a built-in in AOT:R", pg.locked({"builtin": "retry", "group": pg.AOTR}))
check("locked: a built-in elsewhere / own picture in AOT:R", not pg.locked({"builtin": "retry", "group": pg.MINE})
      and not pg.locked({"group": pg.AOTR}))
check("move: a built-in is on in AOT:R", pg.on_after_move({"builtin": "retry"}, False, pg.AOTR) is True)
check("move: a built-in is off anywhere else", pg.on_after_move({"builtin": "retry"}, True, "g1") is False)
check("move: own pictures keep on / off", pg.on_after_move({}, True, "g1") is True and pg.on_after_move({}, False, pg.AOTR) is False)

# ---- an old profile's pictures
asked = []


def builtin_of(file, result, kind):
    asked.append((file, result, kind))
    return "retry" if file == "copy_of_retry.png" else None


part = {"watch_pictures": [{"file": "copy_of_retry.png"}, {"file": "mine.png"}, {"file": "done.png", "group": "g1"},
                           {"file": "", "x": 1}, "junk", {"file": "b.png", "builtin": "failed"}],
        "result_pictures": [{"file": "won.png", "kind": "win"}]}
check("sort: something changed", pg.sort_part(part, builtin_of, {"retry": "RETRY button"}))
w = part["watch_pictures"]
check("sort: groups added", part["picture_groups"] == pg.default_groups())
check("sort: a copy of a built-in goes to AOT:R with its name", w[0] == {"file": "copy_of_retry.png", "builtin": "retry",
                                                                         "name": "RETRY button", "group": pg.AOTR}, w[0])
check("sort: own picture to My pictures", w[1]["group"] == pg.MINE and "builtin" not in w[1])
check("sort: a picture with a group / no file / junk is left", w[2]["group"] == "g1" and "group" not in w[3] and w[4] == "junk")
check("sort: a known built-in isn't compared again", w[5]["group"] == pg.AOTR and ("b.png", False, None) not in asked)
check("sort: results are compared as results", ("won.png", True, "win") in asked
      and part["result_pictures"][0]["group"] == pg.MINE)
check("sort: a second time changes nothing", not pg.sort_part(part, builtin_of, {}))
check("sort: groups kept when there", not pg.sort_part({"picture_groups": [], "watch_pictures": []}, builtin_of, {}))
check("sort: not a dict", pg.sort_part("junk", builtin_of, {}) is False)
check("sort: no pictures = no groups added", not pg.sort_part({}, builtin_of, {}))

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
