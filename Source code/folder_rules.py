"""Macro folders and tags rules: plain functions, no window, no settings file (the menus, saving and the macro list
are in macro_folders.py). `made` is the saved list of folders (settings["macro_folders"], also empty ones); a
macro's `meta` is {"folder": "" or a name, "tags": [...]}."""

MAX_TAGS = 10
MAX_FOLDERS = 50


def clean_name(text, size=30):
    """A folder or tag name: one line, no control characters, not too long ('' when nothing's left)."""
    text = "".join(c for c in str(text or "") if c.isprintable())
    return " ".join(text.split())[:size].strip()


def clean_tags(text):
    """'AOT:R, rejoin #farm' -> ['aot:r', 'rejoin', 'farm'] (no doubles, at most MAX_TAGS)."""
    if isinstance(text, (list, tuple)):
        text = ",".join(str(t) for t in text)
    out = []
    for part in str(text or "").replace("#", ",").split(","):
        tag = clean_name(part, 20).lower()
        if tag and tag not in out:
            out.append(tag)
    return out[:MAX_TAGS]


def clean_meta(m):
    """A saved {"folder", "tags"} entry, checked."""
    m = m if isinstance(m, dict) else {}
    return {"folder": clean_name(m.get("folder")), "tags": clean_tags(m.get("tags"))}


def folders(made, in_use):
    """Every folder: the ones made (also empty) and the ones macros are in (`in_use`), A to Z."""
    names = {clean_name(n) for n in made} if isinstance(made, list) else set()
    names |= set(in_use)
    return sorted((n for n in names if n), key=str.lower)


def add_folder(made, name, in_use):
    """(new made list, the folder's name as it's shown) for making folder `name`; `in_use` = the folders macros are
    in. A name that's there already (any case) isn't added again; (made, None) when there are MAX_FOLDERS already
    or `name` is empty."""
    name = clean_name(name)
    made = [clean_name(n) for n in made] if isinstance(made, list) else []
    if not name:
        return made, None
    if name.lower() not in (n.lower() for n in made + folders(made, in_use)):
        if len(made) >= MAX_FOLDERS:
            return made, None
        made.append(name)
    return made, next((n for n in folders(made, in_use) if n.lower() == name.lower()), name)


def renamed(made, old, new):
    """The made list after folder `old` is renamed to `new` (already cleaned). `new` is in it once, even when a folder
    with that name (any case) was there already."""
    made = made if isinstance(made, list) else []
    return [n for n in made if clean_name(n) != old and clean_name(n).lower() != new.lower()] + [new]


def removed(made, name):
    """The made list without folder `name`."""
    return [n for n in made if clean_name(n) != name] if isinstance(made, list) else []


def matches(name, meta, query):
    """The Edit filter: every word is in the macro's `name`, its folder or a tag ("#farm" = only tags)."""
    name = name.lower()
    for word in str(query or "").lower().split():
        if word.startswith("#"):
            if not any(word[1:] in t for t in meta["tags"]):
                return False
        elif word not in name and word not in meta["folder"].lower() and not any(word in t for t in meta["tags"]):
            return False
    return True
