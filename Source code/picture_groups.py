"""Picture watch group rules: plain functions, no window, no settings file, no picture files (the window, picture
finding and comparing are in picture_window.py). A group is {"id", "name", "builtin"?, "on"?}; a picture's
settings entry holds "group" and "builtin" (the key of an app's own picture, or nothing)."""

GENERAL, AOTR, MINE = "general", "aotr", "mine"  # (the same ids as core.GROUP_*)


def default_groups():
    return [{"id": AOTR, "name": "AOT:R", "builtin": True}, {"id": MINE, "name": "My pictures"}]


def fixed_group(gid):
    """General, AOT:R and My pictures can't be removed."""
    return gid in (GENERAL, AOTR, MINE)


def clean_groups(saved):
    """The saved groups that are usable (a dict with an id)."""
    return [g for g in saved if isinstance(g, dict) and g.get("id")] if isinstance(saved, list) else []


def with_defaults(groups):
    """The groups plus AOT:R and My pictures when one of them is missing."""
    ids = {g["id"] for g in groups}
    return groups + [g for g in default_groups() if g["id"] not in ids]


def summary_text(groups, pictures):
    """"AOT:R: 4 of 4 on · My pictures: 1 of 1 on". `pictures` = [(group id, on)]."""
    bits = []
    for g in groups:
        mine = [on for gid, on in pictures if gid == g["id"]]
        if g.get("on") is False:
            bits.append(f"{g.get('name')}: off")
        elif mine:
            bits.append(f"{g.get('name')}: {sum(1 for on in mine if on)} of {len(mine)} on")
    return " · ".join(bits) or "No pictures yet"


def locked(e):
    """A built-in picture in the built-in AOT:R group: it can be copied, not moved or removed."""
    return bool(e.get("builtin")) and e["group"] == AOTR


def on_after_move(e, was_on, gid):
    """Whether a picture is on after it moves into group `gid`: a built-in one is on in AOT:R and off anywhere else,
    any other keeps what it was."""
    return gid == AOTR if e.get("builtin") else was_on


def sort_part(part, builtin_of, titles):
    """Put the pictures of a profile from before 2.9 (its settings `part`) that have no group yet into one: copies of
    the app's own pictures into AOT:R, others into My pictures. `builtin_of(file, result, kind)` says which of the app's
    own pictures a file is a copy of (None: none); `titles` their names. True if something changed (`part` changes)."""
    if not isinstance(part, dict):
        return False
    changed = False
    if not isinstance(part.get("picture_groups"), list) and (part.get("watch_pictures") or part.get("result_pictures")):
        part["picture_groups"] = default_groups()
        changed = True
    for key, result in (("watch_pictures", False), ("result_pictures", True)):
        for e in part.get(key) or []:
            if not isinstance(e, dict) or e.get("group") or not e.get("file"):
                continue
            if not e.get("builtin"):
                found = builtin_of(e["file"], result, e.get("kind"))
                if found:
                    e["builtin"] = found
                    e.setdefault("name", titles[found])
            e["group"] = AOTR if e.get("builtin") else MINE
            changed = True
    return changed
