"""Profile rules: plain functions, no window, no settings file (switching, the window and saving are in
profiles_ui.py). Which settings belong in a profile, profile names, and which background pictures and Picture
watch pictures the profiles use. `profiles` is the {name: settings part} dict kept under "profiles"."""
import copy

# never part of a profile
SKIP_KEYS = {"profiles", "profile_active", "macro_library", "stats_all", "milestones", "tour_done", "tours_seen", "macro_meta", "macro_folders", "macro_row_folder", "last_seen_version", "last_game_exe",
             "builtin_failed_added", "check_updates", "app_icon_file", "app_logo_file", "app_logo_same",
             "video_history", "video_link", "first_start_done", "warn_big_pictures",
             "video_playlist_note", "check_ignore", "counter_values",
             "trusted_steps"}  # (the macros you OK'd belong to this PC, never to a profile)
SKIP_PREFIXES = ("remote_", "video_rect")
SKIP_ENDINGS = ("_geometry",)
NO_PROFILE = "(none)"
# background options that belong to this PC, not to a profile: the saved pictures and how GIFs play
BG_SHARED_KEYS = {"background_library", "background_animate", "background_animate_focused",
                  "background_fps", "background_pause_others"}
NAME_MAX = 40


def is_background_key(key):
    """Which background each window shows, and its darkness, fit and part (in a profile since 2.9)."""
    return key.startswith(("background_", "settings_background")) and key not in BG_SHARED_KEYS


def in_profile(key):
    if key.startswith(("background", "settings_background")):
        return is_background_key(key)
    return not (key in SKIP_KEYS or key.startswith(SKIP_PREFIXES) or key.endswith(SKIP_ENDINGS))


def profile_part(settings):
    return {k: copy.deepcopy(v) for k, v in settings.items() if in_profile(k)}


def clean_name(name):
    """A profile name: spaces tidied, at most NAME_MAX letters ("" = not a name)."""
    name = " ".join(str(name).split())[:NAME_MAX]
    return "" if name == NO_PROFILE else name


def free_name(base, taken):
    """`base`, or "base 2", "base 3"... the first that isn't taken."""
    name, n = base, 2
    while name in taken:
        name = f"{base} {n}"
        n += 1
    return name


def using_background(profiles, active, picture):
    """Names of the profiles other than `active` that show the background picture `picture`."""
    return [p for p, part in profiles.items() if p != active and isinstance(part, dict) and any(
        is_background_key(k) and k.endswith("_picture") and v == picture for k, v in part.items())]


def forget_background(profiles, picture):
    """A removed background picture: no profile shows it any more (changes `profiles`)."""
    for part in profiles.values():
        if isinstance(part, dict):
            for k in list(part):
                if is_background_key(k) and k.endswith("_picture") and part[k] == picture:
                    part[k] = ""


def watched_pictures(profiles):
    """The picture files the profiles' Picture watch and results lists use (they must stay on disk)."""
    out = set()
    for part in profiles.values():
        for key in ("watch_pictures", "result_pictures"):
            for e in part.get(key) or []:
                if isinstance(e, dict):
                    out |= {e.get(k) for k in ("file", "confirm_file") if e.get(k)}
    return out
