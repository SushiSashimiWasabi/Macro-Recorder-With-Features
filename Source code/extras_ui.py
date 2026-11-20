"""The Run dashboard, sharing a macro with everything it needs in one file, the search box in
Settings, the first-start guide, the chain chart, the live Discord card and "ping me when"."""
import hashlib
import json
import os
import time
import tkinter as tk
import zipfile
from tkinter import filedialog, ttk

import importers
import macro_recorder as core
import macro_steps as workflow
import profiles_ui
import run_history
from picture_actions_ui import action_summary, macro_label
from ui_common import *  # noqa: F401,F403

PACK_EXT = ".macropack"
PACK_TYPES = [("Macro with everything it needs", "*" + PACK_EXT)]
MAX_PACK_FILES = 80
MAX_PACK_FILE_BYTES = 25 * 1024 * 1024
# never shared, and never taken from a shared file: they belong to one person or one PC
PRIVATE_KEYS = {"discord_webhook", "discord_ping", "discord_name", "discord_enabled", "discord_summary",
                "game_closed", "watch_pictures", "result_pictures", "auto_stop", "picture_groups"}
# (security, 20 Nov 2026) a shared profile carries ONLY these: how macros play and look. Anything else (the
# alarm and what it opens, Discord links and where messages go, the screenshot area, the trust list, hotkeys,
# "Pause when the game isn't in front"...) stays as you have it, also settings added later.
SHARE_KEYS = {"accent", "always_on_top", "away_stop_seconds", "drops_enabled", "fit_to", "keys_corner",
              "keys_on_screen", "loop", "mouse_detail", "play_overlay", "ready_seconds", "record_ask_window",
              "record_camera", "record_mouse_moves", "record_ready_seconds", "recovery_countdown", "repeat_count",
              "results_enabled", "results_match", "simplify_moves", "sound_volume", "sounds", "speed", "status_bar",
              "switch_to_program", "vary", "video_click_through", "video_opacity", "watch_click", "watch_enabled",
              "watch_end_wait", "watch_ignore_bg", "watch_limit_count", "watch_limit_seconds", "watch_match",
              "watch_save_with_macro", "watch_shift_lock", "watch_wait"}
# what a shared file may put on this PC as a macro (never a program or a shortcut)
# (no .ahk: a script file Windows would run if it were double-clicked in the folder it lands in)
PACK_MACRO_EXTS = (core.FILE_EXT, ".json") + tuple(e for e in importers.IMPORT_EXTS if e != ".ahk")
PING_WHEN_TEXT = {"fragment": "a divine fragment drops", "stop": "the macro stops", "loss": "a run fails",
                  "lost": "it disconnects or the game closes"}


def shareable(part):
    # (backgrounds point at picture files on this PC, so they stay out of a shared profile)
    return {k: v for k, v in part.items() if k in SHARE_KEYS and profiles_ui.in_profile(k) and k not in PRIVATE_KEYS
            and not profiles_ui.is_background_key(k)}


def safe_name(name):
    """Just the file name, whatever path a shared file claims."""
    name = os.path.basename(str(name).replace("\\", "/"))
    return "".join(c for c in name if c not in '<>:"/\\|?*' and ord(c) >= 32).strip(". ") or "file"


# (Preview 4) Settings names that changed: new name -> old name, so Settings search still finds the old one
OLD_NAMES = {
    "Status line at the bottom": "Status bar",
    "Open .macro files with this app": "Open .macro files with a double-click Link .macro files",
    "Offer to switch to the macro's window": "Offer to switch to the macro's game",
    "Pause when the macro's window isn't in front": "Pause if the game isn't in front",
    "Stop if still paused after…": "Stop after waiting",
    "If the game closes or disconnects": "If the game closes",
    "Countdown before reopening the game": "Countdown before rejoining",
    "If a run gets stuck (no result seen)": "If a run gets stuck",
    "Let clicks pass through the video": "Clicks go through it",
    "Video transparency": "See-through",
    "Remember YouTube sign-in": "Saved browser data",
    "Record camera turning (Shift Lock)": "Record game camera movement",
    "RUN RESULTS (AOT:R)": "MISSION RESULTS",
    "Win / loss pictures": "Result pictures",
    "Update one message instead of sending new ones": "One card that updates",
    "Screenshot shows": "Screenshot of",
}


class ExtrasMixin:
    # ------------------------------------------------------------ one live Discord card

    def live_summary(self):
        return "On" if self.settings.get("discord_live") else "Off"

    def toggle_live_card(self):
        self.settings["discord_live"] = not self.settings.get("discord_live")
        self._save_settings()
        self._show_automation()

    # ------------------------------------------------------------ "ping me when" (phone remote)

    def remote_pingme(self, arg, who):
        when, runs, uid = arg if isinstance(arg, tuple) else (arg, None, "")
        pings = self.__dict__.setdefault("remote_pings", [])
        if when == "none":
            pings[:] = [p for p in pings if p["uid"] != uid]
            return "Forgot your pings."
        if not (self.settings.get("discord_enabled") and str(self.settings.get("discord_webhook") or "").strip()):
            return ("Pings are sent to the channel of the Discord link in Settings > Discord. Turn that on first "
                    "(on the PC).")
        if runs:
            pings.append({"uid": uid, "when": "runs", "left": max(1, int(runs))})
            return f"OK {who}: I'll ping you after {int(runs)} more run{'s' if int(runs) != 1 else ''}."
        if when not in PING_WHEN_TEXT:
            return "Choose what to wait for."
        pings.append({"uid": uid, "when": when})
        return f"OK {who}: I'll ping you once when {PING_WHEN_TEXT[when]}."

    def _ping_those(self, when, text):
        pings = getattr(self, "remote_pings", None)
        if not pings:
            return
        due = [p for p in pings if p["when"] == when]
        if not due:
            return
        pings[:] = [p for p in pings if p["when"] != when]
        who = " ".join(dict.fromkeys(f"<@{p['uid']}>" for p in due if p["uid"]))
        try:
            self.notifier.send(f"{who} {text}".strip(),
                               username=str(self.settings.get("discord_name") or "Macro Recorder"))
        except Exception as exc:
            core.diag.error("Couldn't send a ping", exc)

    def _run_finished(self, count, how):
        super()._run_finished(count, how)
        pings = getattr(self, "remote_pings", None)
        if not pings:
            return
        name = self.session.macro or "The macro"
        if self.session.fragments and self.session.fragments[-1] > 0:
            self._ping_those("fragment", f"A divine fragment dropped in run {count} of {name}.")
        if self.session.runs and self.session.runs[-1][0] == "loss":
            self._ping_those("loss", f"Run {count} of {name} failed.")
        done = False
        for p in pings:
            if p["when"] == "runs":
                p["left"] -= 1
                if p["left"] <= 0:
                    p["when"], done = "runs_done", True
        if done:
            self._ping_those("runs_done", f"{name}: the runs you asked about are done ({count} this session).")

    def _recovery_event(self, kind, text):
        super()._recovery_event(kind, text)
        if kind in ("lost", "failed", "stuck"):
            self._ping_those("lost", text)

    def _pings_on_stop(self, text):
        self._ping_those("stop", f"{self.session.macro or 'The macro'}: {text}")

    # ------------------------------------------------------------ share: one file with everything

    SHARE_HELP = (
        "Export makes one " + PACK_EXT + " file with the open macro and everything it needs: the macros its "
        "\"Play another macro\" steps and pictures use, the pictures of Picture watch with what each one does, "
        "the profile linked to the macro (if any), and, if you say yes, its background pictures and GIFs "
        "(each up to 25 MB).\n\n"
        "Left out on purpose: your Discord link and pings, the phone remote, \"If the game closes\" and "
        "\"Stop by itself\". Those stay yours.\n\n"
        "Import puts the macros in a folder you choose, asks before adding the pictures, the profile and the "
        "backgrounds, then opens the macro.")

    def _pack_collect(self, path, found):
        """Read a macro and every macro it plays into found: {file name in the pack: text or bytes}."""
        real = self._find_macro_file(path)
        if not real:
            raise ValueError(f"the macro \"{macro_label(path)}\" isn't there any more")
        key = core.MacroRecorder._macro_key(real)
        if key in found["by_path"]:
            return found["by_path"][key]
        name = safe_name(real)
        n = 2
        while name in found["files"]:
            base, ext = os.path.splitext(safe_name(real))
            name = f"{base} ({n}){ext}"
            n += 1
        found["by_path"][key] = name
        found["files"][name] = None  # (taken, so a macro that plays itself in a circle ends here)
        try:
            with open(real, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or data.get("format") == "luvmacro":
                raise ValueError
        except (OSError, ValueError):
            with open(real, "rb") as f:  # another recorder's file: goes in as it is
                found["files"][name] = f.read()
            return name
        for a, _l, _i, _p in workflow.walk(data.get("actions") or []):
            if isinstance(a, dict) and a.get("kind") == "play_macro":
                for field in ("file", "on_fail"):
                    if a.get(field):
                        a[field] = self._pack_collect(a[field], found)
        data.pop("watch_pictures", None)  # (the pack carries the pictures itself, with their actions)
        found["files"][name] = json.dumps(data)
        return name

    def export_pack(self, path=None):
        """Write the open macro and what it needs to one file. Returns the path, or None."""
        parent = self.settings_win if self.settings_win is not None else self.root
        if not self.current_file or getattr(self, "unsaved", False):
            self.boxes.showinfo("Share", "Save the macro first (Save…), then export it.", parent=parent)
            return None
        try:
            found = {"files": {}, "by_path": {}}
            main = self._pack_collect(self.current_file, found)
            pictures = []
            image_watch = core.image_watch
            for pic in self._active_watch_pictures(self.current_file):
                entry = core.watch_entry(pic)
                entry.pop("seen_rect", None)
                for k in core.GROUP_FIELDS:  # (where it's kept here, and which macros: this PC's own)
                    entry.pop(k, None)
                with open(os.path.join(core.watch_dir(), pic["file"]), "rb") as f:
                    found["files"]["pictures/" + safe_name(pic["file"])] = f.read()
                if entry.get("macro"):
                    entry["macro"] = self._pack_collect(entry["macro"], found)
                if entry.get("confirm_file"):
                    with open(os.path.join(core.watch_dir(), entry["confirm_file"]), "rb") as f:
                        found["files"]["pictures/" + safe_name(entry["confirm_file"])] = f.read()
                pictures.append(entry)
            del image_watch
            manifest = {"app": "macro_recorder_pack", "version": 1, "main": main,
                        "macros": [n for n in found["files"] if not n.startswith("pictures/")],
                        "pictures": pictures,
                        "watch": {k: self.settings[k] for k in ("watch_enabled", "watch_click", "watch_wait",
                                                                 "watch_match", "watch_end_wait")
                                  if k in self.settings}}
            linked = getattr(self, "macro_profile", None)
            if linked and linked in self.profiles():
                manifest["profile"] = {"name": linked, "settings": shareable(self.profiles()[linked])}
            skipped_bg = self._pack_backgrounds(manifest, found, parent)
            if skipped_bg is None:
                return None  # (cancelled)
        except (OSError, ValueError) as exc:
            self.boxes.showerror("Share", f"Couldn't put the file together:\n{exc}", parent=parent)
            return None
        if path is None:
            path = filedialog.asksaveasfilename(parent=parent, defaultextension=PACK_EXT, filetypes=PACK_TYPES,
                                                initialfile=macro_label(self.current_file) + PACK_EXT)
        if not path:
            return None
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("manifest.json", json.dumps(manifest, indent=1))
                for name, content in found["files"].items():
                    z.writestr(name if name.startswith(("pictures/", "backgrounds/")) else "macros/" + name, content)
        except OSError as exc:
            self.boxes.showerror("Share", f"Couldn't write the file:\n{exc}", parent=parent)
            return None
        n_m, n_p = len(manifest["macros"]), len(pictures)
        n_b = len((manifest.get("backgrounds") or {}).get("files") or [])
        self.boxes.showinfo("Share", f"Saved: {n_m} macro{'s' if n_m != 1 else ''}, {n_p} picture"
                            f"{'s' if n_p != 1 else ''}" + (", the profile \"" + manifest["profile"]["name"] + "\""
                                                            if "profile" in manifest else "")
                            + (f", {n_b} background picture{'s' if n_b != 1 else ''}" if n_b else "")
                            + "." + (f"\n\nLeft out (bigger than 25 MB): {', '.join(skipped_bg)}" if skipped_bg else "")
                            + "\n\nYour Discord link and the phone remote are not inside.", parent=parent)
        return path

    def _pack_backgrounds(self, manifest, found, parent):
        """Asks whether the background pictures go in the file too (the linked profile's, or the ones
        showing now), and puts them in. Returns the names left out for being too big, or None when
        cancelled."""
        linked = (manifest.get("profile") or {}).get("name")
        source = self.profiles()[linked] if linked else self.settings
        bg = {k: v for k, v in source.items() if profiles_ui.is_background_key(k)}
        folder = os.path.dirname(core.settings_path())
        lib = {e["file"]: e for e in self.bg_library() if isinstance(e, dict) and e.get("file")}
        used = []
        for k, v in bg.items():
            if k.endswith("_picture") and v in lib and v not in used and os.path.isfile(os.path.join(folder, v)):
                used.append(v)
        if not used:
            return []
        size = sum(os.path.getsize(os.path.join(folder, f)) for f in used)
        answer = self.boxes.askyesno(
            "Share", f"Put the background picture{'s' if len(used) != 1 else ''} in the file too? "
            f"({len(used)}, {size / 1048576:.1f} MB: " + ", ".join(lib[f].get("name") or f for f in used)
            + ")\n\nThe one you share it with is asked before they're used.", parent=parent)
        if not answer:
            return []
        skipped, files = [], []
        for f in used:
            if os.path.getsize(os.path.join(folder, f)) > MAX_PACK_FILE_BYTES:
                skipped.append(lib[f].get("name") or f)
                continue
            with open(os.path.join(folder, f), "rb") as fh:
                found["files"]["backgrounds/" + safe_name(f)] = fh.read()
            files.append({"file": safe_name(f), "name": str(lib[f].get("name") or f)[:120]})
        kept = {f["file"] for f in files}
        manifest["backgrounds"] = {
            "files": files,
            "settings": {k: ((safe_name(v) if v and safe_name(v) in kept else "") if k.endswith("_picture") else v)
                         for k, v in bg.items() if not k.endswith("_original")}}
        return skipped

    def _pack_take_backgrounds(self, backgrounds, picture_bytes, took_profile, parent):
        """Offer the pack's background pictures: added to your saved background pictures (one you
        already have isn't added twice), then used by the profile that came with it, or, if you say
        so, right away. Returns how many were added."""
        files = [f for f in backgrounds.get("files") or [] if isinstance(f, dict) and f.get("file") in picture_bytes]
        settings = backgrounds.get("settings") if isinstance(backgrounds.get("settings"), dict) else {}
        if not files:
            return 0
        where = (f"the profile \"{took_profile}\" uses them" if took_profile
                 else "you're asked next whether to show them now")
        if not self.boxes.askyesno("Share", f"This macro comes with {len(files)} background picture"
                                   f"{'s' if len(files) != 1 else ''}.\n\nAdd "
                                   f"{'them' if len(files) != 1 else 'it'} to your background pictures? "
                                   f"({where})", parent=parent):
            return 0
        import backdrop
        folder = os.path.dirname(core.settings_path())
        lib = self.bg_library()
        have = {}
        for e in lib:
            try:
                with open(os.path.join(folder, e["file"]), "rb") as fh:
                    have[hashlib.sha1(fh.read()).hexdigest()] = e["file"]
            except (OSError, KeyError, TypeError):
                pass
        names, added, full = {}, 0, []
        for f in files:
            data = picture_bytes[f["file"]]
            same = have.get(hashlib.sha1(data).hexdigest())
            if same:
                names[f["file"]] = same
                continue
            if len(lib) >= MAX_BACKGROUNDS:
                full.append(f.get("name") or f["file"])
                continue
            used_stems = {os.path.splitext(e["file"])[0] for e in lib}
            stem = next(f"background_{i}" for i in range(1, 100) if f"background_{i}" not in used_stems)
            tmp = os.path.join(folder, f"_shared_{stem}{os.path.splitext(f['file'])[1].lower() or '.png'}")
            try:
                with open(tmp, "wb") as fh:
                    fh.write(data)
                stored = backdrop.store_any(tmp, folder, stem)  # (checked: only a real picture is kept)
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            if not stored:
                continue
            lib.append({"file": stored, "name": str(f.get("name") or stored)[:120]})
            names[f["file"]] = stored
            added += 1
        clean = {}
        for k, v in settings.items():
            if not profiles_ui.is_background_key(k):
                continue  # (only background options come from a shared file this way)
            if k.endswith("_picture"):
                v = names.get(v, "") if isinstance(v, str) else ""
            elif not isinstance(v, (int, float, str, bool)):
                continue
            clean[k] = v
        if took_profile and took_profile in self.profiles():
            self.profiles()[took_profile].update(clean)
        elif clean and self.boxes.askyesno("Share", "Show the shared background now? (Undo: pick your old one "
                                           "again in Settings > Background.)", parent=parent):
            self.settings.update(clean)
            self._load_page_settings()
        core.save_settings(self.settings)
        if full:
            self.boxes.showinfo("Share", f"You already have {MAX_BACKGROUNDS} saved background pictures, so these "
                                "weren't added: " + ", ".join(full) + "\n\nRemove one in Settings > Background "
                                "and import again.", parent=parent)
        return added

    def import_pack(self, path=None, folder=None):
        """Open a shared file: its macros go in a folder, pictures and profile are offered.
        Returns the main macro's path, or None."""
        parent = self.settings_win if self.settings_win is not None else self.root
        if self.playing or self.recording:
            return None
        if path is None:
            path = filedialog.askopenfilename(parent=parent, filetypes=PACK_TYPES)
        if not path:
            return None
        try:
            with zipfile.ZipFile(path) as z:
                infos = {i.filename: i for i in z.infolist() if not i.is_dir()}
                if len(infos) > MAX_PACK_FILES or any(i.file_size > MAX_PACK_FILE_BYTES for i in infos.values()):
                    raise ValueError("it's bigger than a shared macro should be")
                manifest = json.loads(z.read("manifest.json").decode("utf-8"))
                if not isinstance(manifest, dict) or manifest.get("app") != "macro_recorder_pack":
                    raise ValueError("it isn't a shared macro file")
                macros = [m for m in manifest.get("macros") or [] if isinstance(m, str)
                          and safe_name(m).lower().endswith(PACK_MACRO_EXTS)]
                main = manifest.get("main")
                if main not in macros or "macros/" + main not in infos:
                    raise ValueError("its main macro is missing")
                if folder is None:
                    folder = filedialog.askdirectory(parent=parent, title="Where should its macros go?",
                                                     initialdir=os.path.dirname(path))
                if not folder:
                    return None
                dest = os.path.join(folder, safe_name(os.path.splitext(os.path.basename(path))[0]))
                n = 2
                while os.path.exists(dest):
                    dest = os.path.join(folder, safe_name(os.path.splitext(os.path.basename(path))[0]) + f" ({n})")
                    n += 1
                os.makedirs(dest)
                placed = {}
                for m in macros:
                    if "macros/" + m in infos:
                        placed[m] = os.path.join(dest, safe_name(m))
                        with open(placed[m], "wb") as f:
                            f.write(z.read("macros/" + m))
                # the macros name each other by file name: point them at their new places
                for m, target in placed.items():
                    try:
                        with open(target, encoding="utf-8") as f:
                            data = json.load(f)
                    except (OSError, ValueError):
                        continue
                    changed = False
                    for a, _l, _i, _p in workflow.walk(data.get("actions") or [] if isinstance(data, dict) else []):
                        if isinstance(a, dict) and a.get("kind") == "play_macro":
                            for field in ("file", "on_fail"):
                                if a.get(field):
                                    a[field] = placed.get(a[field], os.path.join(dest, safe_name(a[field])))
                                    changed = True
                    if changed:
                        with open(target, "w", encoding="utf-8") as f:
                            core.dump_macro(data, f)
                pictures = [p for p in manifest.get("pictures") or [] if isinstance(p, dict) and p.get("file")]
                backgrounds = manifest.get("backgrounds") if isinstance(manifest.get("backgrounds"), dict) else {}
                bg_bytes = {}
                for f in backgrounds.get("files") or []:
                    name = "backgrounds/" + safe_name(f.get("file") or "") if isinstance(f, dict) else ""
                    if name in infos:
                        bg_bytes[f["file"]] = z.read(name)
                picture_bytes = {}
                for p in pictures:
                    for field in ("file", "confirm_file"):
                        name = "pictures/" + safe_name(p.get(field) or "")
                        if p.get(field) and name in infos:
                            picture_bytes[p[field]] = z.read(name)
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
            self.boxes.showerror("Share", f"Couldn't open that file:\n{exc}", parent=parent)
            return None
        added = self._pack_add_pictures(pictures, picture_bytes, placed, dest, parent)
        profile = manifest.get("profile")
        took_profile = None
        if isinstance(profile, dict) and isinstance(profile.get("settings"), dict) and profile.get("name"):
            name = " ".join(str(profile["name"]).split())[:40]
            if self.boxes.askyesno("Share", f"This macro comes with the settings profile \"{name}\" (speed, "
                                   "countdown, picture watch options and so on).\n\nAdd it to your profiles? "
                                   "Your own settings stay as they are until you switch to it yourself.",
                                   parent=parent):
                took_profile = name
                n = 2
                while took_profile in self.profiles():
                    took_profile = f"{name} ({n})"
                    n += 1
                # what a shared profile never carries (your Discord link, your pictures, "If the game
                # closes"...) stays as you have it now
                self._save_settings()
                part = profiles_ui.profile_part(self.settings)
                part.update(shareable(profile["settings"]))
                self.profiles()[took_profile] = part
                core.save_settings(self.settings)
        took_bg = self._pack_take_backgrounds(backgrounds, bg_bytes, took_profile, parent) if bg_bytes else 0
        self.skip_file_pictures = True
        self.skip_profile_switch = True  # (security: a shared macro never switches your settings by itself)
        try:
            loaded = self.load(placed[main], quiet=True)
        finally:
            self.skip_profile_switch = False
        if not loaded:
            self.skip_file_pictures = False
            self.boxes.showerror("Share", "The macros were put in\n" + dest + "\nbut the main one couldn't be "
                                 "opened: " + str(self.load_error or ""), parent=parent)
            return None
        self.boxes.showinfo("Share", f"Opened \"{macro_label(placed[main])}\".\n\n{len(placed)} macro"
                            f"{'s' if len(placed) != 1 else ''} in {dest}\n{added} picture"
                            f"{'s' if added != 1 else ''} added to Picture watch"
                            + (f"\nProfile added: {took_profile}" if took_profile else "")
                            + (f"\n{took_bg} background picture{'s' if took_bg != 1 else ''} added" if took_bg else ""),
                            parent=parent)
        return placed[main]

    def _pack_add_pictures(self, pictures, picture_bytes, placed, dest, parent):
        """Offer the pack's watched pictures that aren't in the list yet. Returns how many were added."""
        def digest(data):
            return hashlib.sha1(data).hexdigest()
        have = {}
        for pic in self.watch_pictures:
            try:
                with open(os.path.join(core.watch_dir(), pic["file"]), "rb") as f:
                    have[digest(f.read())] = pic["file"]
            except OSError:
                pass
        new = [p for p in pictures if p["file"] in picture_bytes and digest(picture_bytes[p["file"]]) not in have]
        if not new:
            return 0
        lines = "\n".join(f"  • {p.get('name') or 'picture'}: {action_summary(p)}" for p in new[:8])
        if not self.boxes.askyesno("Share", f"This macro comes with {len(new)} picture{'s' if len(new) != 1 else ''} "
                                   f"for Picture watch:\n\n{lines}\n\nAdd {'them' if len(new) != 1 else 'it'}?",
                                   parent=parent):
            return 0
        os.makedirs(core.watch_dir(), exist_ok=True)
        renamed = dict((p["file"], have[digest(picture_bytes[p["file"]])]) for p in pictures
                       if p["file"] in picture_bytes and digest(picture_bytes[p["file"]]) in have)
        stamp = int(time.time() * 1000)
        for i, p in enumerate(new):
            renamed[p["file"]] = f"picture_{stamp + i}.png"
        for i, p in enumerate(new):
            entry = {k: p[k] for k in core.WATCH_FIELDS if k in p}
            entry["file"] = renamed[p["file"]]
            with open(os.path.join(core.watch_dir(), entry["file"]), "wb") as f:
                f.write(picture_bytes[p["file"]])
            if entry.get("action") not in core.WATCH_ACTION_NAMES:
                entry.pop("action", None)
            if entry.get("macro"):
                entry["macro"] = placed.get(entry["macro"], os.path.join(dest, safe_name(entry["macro"])))
            if entry.get("also"):
                entry["also"] = renamed.get(entry["also"])
            if entry.get("confirm_file"):
                if entry["confirm_file"] in picture_bytes:
                    confirm = f"picture_{stamp + 1000 + i}.png"
                    with open(os.path.join(core.watch_dir(), confirm), "wb") as f:
                        f.write(picture_bytes[entry["confirm_file"]])
                    entry["confirm_file"] = confirm
                else:
                    entry.pop("confirm_file")
            pic = core.watch_picture_from(entry)
            if pic is not None:
                self.watch_pictures.append(pic)
        self._show_watch_pictures()
        self._save_settings()
        return len(new)

    # ------------------------------------------------------------ the search box in Settings

    def _build_settings_search(self, parent):
        self.search_var = tk.StringVar()
        box = tk.Entry(parent, textvariable=self.search_var, width=22, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat",
                       insertbackground=TEXT, highlightthickness=1, highlightbackground=BORDER,
                       highlightcolor=ACCENT)
        tk.Label(parent, text="Search", bg=BG, fg=MUTED, font=F_SMALL).pack(side="left")
        box.pack(side="left", padx=(6, 0), ipady=3)
        link(parent, "Take a tour", lambda: self.start_tour("settings"), bg=BG).pack(side="left", padx=(14, 0))
        self.search_box = box
        self.search_list = None
        self.search_var.trace_add("write", lambda *a: self._search_show())
        box.bind("<Return>", lambda e: self._search_go(0))
        box.bind("<Escape>", lambda e: (self.search_var.set(""), self._search_close()))
        box.bind("<Down>", lambda e: self.search_list and self.search_list.winfo_exists()
                 and (self.search_list.lst.focus_set(), self.search_list.lst.selection_set(0)))
        # (Preview 4) the list is its own little window: it closes when Settings is moved, hidden or
        # closed, when the page changes, and when you click anywhere else
        win = self.settings_win
        box.bind("<FocusOut>", lambda e: win.after(150, self._search_close_unless_used), add="+")
        win.bind("<Configure>", self._search_settings_moved, add="+")
        win.bind("<Unmap>", lambda e: e.widget is win and self._search_close(), add="+")
        # (a click on a plain part of Settings doesn't take the keyboard away from the box)
        win.bind("<Button-1>", lambda e: e.widget is not box and self._search_close(), add="+")
        self.tabs.bind("<<NotebookTabChanged>>", lambda e: self._search_close(), add="+")
        self.search_at = None

    def _search_settings_moved(self, event):
        if event.widget is not self.settings_win:
            return
        at = (self.settings_win.winfo_rootx(), self.settings_win.winfo_rooty())
        if at != self.search_at:
            self.search_at = at
            self._search_close()

    def _search_close_unless_used(self):
        """The search box lost the keyboard: close the list, unless it went to the list itself."""
        lst = self.search_list.lst if self.search_list is not None and self.search_list.winfo_exists() else None
        try:
            now = self.settings_win.focus_get()
        except (KeyError, tk.TclError):
            now = None
        if lst is not None and (now is lst or self._pointer_in(self.search_list)):
            return  # (a click on the list: it opens that setting on letting go)
        self._search_close()

    @staticmethod
    def _pointer_in(win):
        try:
            x, y = win.winfo_pointerxy()
            return (win.winfo_rootx() <= x < win.winfo_rootx() + win.winfo_width()
                    and win.winfo_rooty() <= y < win.winfo_rooty() + win.winfo_height())
        except tk.TclError:
            return False

    def search_settings(self, text):
        """Every setting whose name or grey words hold the text: [(page, widget, its text)]."""
        words = [w for w in str(text).lower().split() if w]
        out = []
        if not words:
            return out

        def walk(page, w):
            for child in w.winfo_children():
                try:
                    label = str(child.cget("text"))
                except tk.TclError:
                    label = ""
                if label and len(label) > 1 and isinstance(child, (tk.Label, ttk.Label, ttk.Checkbutton,
                                                                    tk.Checkbutton, ttk.Button, ttk.Labelframe)):
                    # (Preview 4) names changed in Preview 4 are still found by their old name
                    text = (label + " " + OLD_NAMES.get(label, "")).lower()
                    if all(word in text for word in words):
                        out.append((page, child, " ".join(label.split())))
                walk(page, child)
        for page, frame in self.tab_frames.items():
            if all(word in page.lower() for word in words):
                out.append((page, frame, "The whole page"))
            walk(page, frame)
        return out[:14]

    def _search_close(self):
        if self.search_list is not None and self.search_list.winfo_exists():
            self.search_list.destroy()
        self.search_list = None

    def _search_show(self):
        self._search_close()
        self.search_found = self.search_settings(self.search_var.get())
        if not self.search_found:
            return
        box = self.search_box
        win = tk.Toplevel(self.settings_win, bg=BORDER)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        lst = tk.Listbox(win, bg=CARD, fg=TEXT, font=F_BASE, relief="flat", highlightthickness=0,
                         selectbackground=ACCENT_DARK, selectforeground=TEXT, activestyle="none",
                         height=len(self.search_found), width=58)
        lst.pack(padx=1, pady=1)
        for page, _w, label in self.search_found:
            lst.insert("end", f"  {page}  ›  {short(label, 44)}")
        win.update_idletasks()
        win.geometry(f"+{box.winfo_rootx()}+{box.winfo_rooty() - win.winfo_reqheight() - 4}")
        lst.bind("<ButtonRelease-1>", lambda e: self._search_go(lst.nearest(e.y)))
        lst.bind("<Return>", lambda e: self._search_go((lst.curselection() or [0])[0]))
        lst.bind("<Escape>", lambda e: self._search_close())
        lst.bind("<FocusOut>", lambda e: self.settings_win.after(150, self._search_close_unless_typing), add="+")
        win.lst = lst
        self.search_list = win
        self.search_at = (self.settings_win.winfo_rootx(), self.settings_win.winfo_rooty())

    def _search_close_unless_typing(self):
        """The list lost the keyboard: close it, unless you went back to typing in the search box."""
        try:
            now = self.settings_win.focus_get()
        except (KeyError, tk.TclError):
            now = None
        if now is not self.search_box:
            self._search_close()

    def _search_go(self, index):
        found = getattr(self, "search_found", [])
        self._search_close()
        if not (0 <= index < len(found)):
            return
        page, widget, _label = found[index]
        self.tabs.select(self.tab_areas[page])
        # a setting inside a folded "Advanced" part: open that part
        for part in getattr(self, "advanced_parts", []):
            try:
                if str(widget).startswith(str(part)) and not part.winfo_ismapped():
                    part.toggle(True)
            except (tk.TclError, AttributeError):
                pass
        if widget is self.tab_frames[page]:
            return
        self.tab_areas[page].see(widget)  # (Preview 4: the page may need scrolling to show it)
        try:  # show where it is: its text turns blue for a moment
            before = widget.cget("foreground")
            widget.configure(foreground=ACCENT)
            self.settings_win.after(1800, lambda: widget.winfo_exists() and widget.configure(foreground=before))
        except tk.TclError:
            pass

    # ------------------------------------------------------------ the first-start guide

    def first_start_due(self):
        s = self.settings
        if s.get("first_start_done"):
            return False
        if "speed" in s or "hotkeys" in s or s.get("macro_library"):  # not a first start: an update
            s["first_start_done"] = True
            return False
        return True

    def open_first_start(self):
        """Three questions, each with what it changes; everything can be changed later in Settings."""
        win = self.first_start_win = tk.Toplevel(self.root, bg=BG)  # (Preview 4: the tour waits for it)
        win.title("Welcome to Macro Recorder")
        win.transient(self.root)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=22, pady=16)
        tk.Label(body, text="Three quick questions", bg=BG, fg=TEXT, font=(FAMILY, 14, "bold"), anchor="w").pack(
            fill="x")
        tk.Label(body, text="So the app fits how you play. Everything here can be changed later in Settings.",
                 bg=BG, fg=MUTED, font=F_BASE, anchor="w").pack(fill="x", pady=(2, 10))
        answers = {}

        def question(key, title, options, default):
            tk.Label(body, text=title, bg=BG, fg=TEXT, font=F_BOLD, anchor="w").pack(fill="x", pady=(10, 2))
            var = tk.StringVar(value=default)
            answers[key] = var
            for value, label, words in options:
                row = tk.Frame(body, bg=BG)
                row.pack(fill="x")
                tk.Radiobutton(row, text=label, value=value, variable=var, bg=BG, fg=TEXT, selectcolor=FIELD,
                               activebackground=BG, activeforeground=TEXT, font=F_BASE, anchor="w").pack(side="left")
                tk.Label(row, text=words, bg=BG, fg=DIM, font=F_SMALL).pack(side="left", padx=(6, 0))

        question("fit", "How do you play your game?", [
            ("window", "In a window, or sometimes fullscreen", "clicks follow the game's window"),
            ("screen", "Always fullscreen", "clicks are fitted to the whole screen")], "window")
        question("watch", "Do you grind missions in AOT:R (Roblox)?", [
            ("yes", "Yes", "the macro starts over when the RETRY button shows, and wins are counted"),
            ("no", "No, other things", "plays your macro as it is; nothing is watched")], "yes")
        question("discord", "Do you want messages on Discord (a card after each run)?", [
            ("no", "Not now", ""),
            ("yes", "Yes, set it up", "opens Settings > Discord next")], "no")

        def done():
            s = self.settings
            s["fit_to"] = answers["fit"].get()
            aot = answers["watch"].get() == "yes"
            s["watch_enabled"] = aot
            s["results_enabled"] = aot
            s["drops_enabled"] = aot
            s["first_start_done"] = True
            core.save_settings(s)
            self._load_page_settings()
            win.destroy()
            self._refresh()
            if answers["discord"].get() == "yes":
                self.open_settings("Discord")
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=22, pady=(0, 16))
        ttk.Button(bottom, text="Done", style="Accent.TButton", width=8, command=done).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", done)
        dark_title_bar(win)
        win.focus_force()
        win.done, win.answers = done, answers
        return win

    # ------------------------------------------------------------ the Run dashboard

    def dashboard_lines(self):
        """[(label, text)] of everything a run depends on, as it is right now."""
        s = self.settings
        if self.recording:
            state = "Recording"
        elif self.playing:
            state = ("Starting in " + str(self.countdown_left) + " s" if self.countdown_left > 0
                     else "Paused" if self.play_paused_at is not None else "Playing")
        else:
            state = "Ready" if (self.events or self.actions) else "No macro open"
        name = self.name_var.get().strip() or "-"
        steps = self.macro_steps() if (self.events or self.actions) else []
        parts = [a for a, _l, _i, _p in workflow.walk(steps) if a.get("kind") == "play_macro" and not a.get("off")]
        chain = (" → ".join(f"{macro_label(a.get('file')) or '?'}" + (f" ×{a['times']}" if a.get("times", 1) > 1 else "")
                            for a in parts[:6]) + (" …" if len(parts) > 6 else "")) if parts else "Not a chain"
        if self.playing and getattr(self, "chain_step", None):
            chain += f"   (now: {self.chain_step})"
        lines = [("State", state), ("Macro", name), ("Chain", chain)]
        if self.playing:
            lines.append(("Now", (self.play_note or "Playing").strip()))
            v = self.session.values("")
            lines.append(("This session", f"{v['run']} runs in {v['total']} · {self.session.summary()}"))
        elif self.session.runs:
            lines.append(("Last session", f"{len(self.session.runs)} runs · {self.session.summary()}"))
        today = [r for r in run_history.runs() if run_history.day_of(r["t"]) == run_history.day_of()]
        t = run_history.summary(today)
        rate = f"{t['winrate']:.0f}%" if t["winrate"] is not None else "-"
        lines.append(("Today", f"{t['runs']} runs · {t['wins']} won · {t['losses']} failed · win rate {rate} · "
                               f"{t['fragments']} fragment{'s' if t['fragments'] != 1 else ''}"))
        active = self._active_watch_pictures()
        if self.watch_var.get() and active:
            rules = "; ".join((p.get("name") or f"picture {i}") + ": " + action_summary(p).split("  (")[0]
                              for i, p in enumerate(active[:4], start=1))
            lines.append(("Picture watch", f"On, {len(active)} picture"
                                           f"{'s' if len(active) != 1 else ''}. {rules}"))
        else:
            lines.append(("Picture watch", "Off"))
        lines.append(("If the game closes or disconnects", self.closed_summary()))
        stop = self.auto_stop_summary()
        if self.playing and getattr(self, "auto_stop", None) and self.auto_stop["cancelled"]:
            stop += " (cancelled for this playback)"
        lines.append(("Stop by itself", stop))
        lines.append(("Random timing", self.vary_summary()))
        lines.append(("Profile", self.profile_active() or "None"))
        lines.append(("Discord", ("On" + (", one live card" if s.get("discord_live") else "")
                                  + (" · summary " + self.summary_summary().lower()
                                     if self.summary_summary() != "Off" else ""))
                      if s.get("discord_enabled") else "Off"))
        remote = "Off"
        if s.get("remote_enabled"):
            users = len(s.get("remote_users") or [])
            remote = f"On, {users} paired account{'s' if users != 1 else ''}"
            pings = len(getattr(self, "remote_pings", []) or [])
            if pings:
                remote += f", {pings} ping{'s' if pings != 1 else ''} waiting"
        lines.append(("Phone remote", remote))
        return lines

    def open_dashboard(self):
        old = getattr(self, "dashboard_win", None)
        if old is not None and old.winfo_exists():
            old.lift()
            return old
        win = tk.Toplevel(self.root, bg=BG)
        win.title("Run dashboard")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        self.dashboard_win = win
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", padx=18, pady=14)
        grid = tk.Frame(body, bg=BG)
        grid.pack(fill="x")
        labels = {}

        def show():
            if not win.winfo_exists():
                return
            lines = self.dashboard_lines()
            if list(labels) != [k for k, _v in lines]:
                for child in grid.winfo_children():
                    child.destroy()
                labels.clear()
                for r, (key, _v) in enumerate(lines):
                    tk.Label(grid, text=key, bg=BG, fg=MUTED, font=F_BASE, anchor="w").grid(row=r, column=0,
                                                                                            sticky="nw", pady=2)
                    lab = tk.Label(grid, text="", bg=BG, fg=TEXT, font=F_BASE, anchor="w", justify="left",
                                   wraplength=430)
                    lab.grid(row=r, column=1, sticky="w", padx=(18, 0), pady=2)
                    labels[key] = lab
            for key, value in lines:
                if labels[key].cget("text") != value:
                    labels[key].config(text=value, fg=(GREEN if value == "Playing" else AMBER if value == "Paused"
                                                       else TEXT) if key == "State" else TEXT)
            b_play.config(state="normal" if not (self.playing or self.recording)
                          and (self.events or self.actions) else "disabled")
            b_pause.config(state="normal" if self.playing and self.countdown_left == 0 else "disabled",
                           text="Resume" if self.playing and self.play_paused_at is not None else "Pause")
            b_stop.config(state="normal" if self.playing else "disabled")
            win.job = win.after(1000, show)
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(0, 14))
        b_play = ttk.Button(bottom, text="Play", style="Accent.TButton", width=8, command=self.play)
        b_pause = ttk.Button(bottom, text="Pause", width=8, command=self.toggle_pause)
        b_stop = ttk.Button(bottom, text="Stop", width=8, command=self.stop_playback)
        for b in (b_play, b_pause, b_stop):
            b.pack(side="left", padx=(0, 6))
        ttk.Button(bottom, text="Close", width=8, command=win.destroy).pack(side="right")
        ttk.Button(bottom, text="Stats…", width=8, command=self.open_stats).pack(side="right", padx=6)
        ttk.Button(bottom, text="Chain chart…", command=self.open_chain_chart).pack(side="right")
        dark_title_bar(win)
        show()
        win.show = show
        return win

    # ------------------------------------------------------------ the chain as a chart

    def chain_boxes(self, steps=None):
        """The macro's top steps as boxes for the chart: [{"title", "words", "fail", "id"}]."""
        steps = self.macro_steps() if steps is None else steps
        out = []
        for a in steps:
            name, words = workflow.describe(a)
            box = {"id": a.get("id"), "title": name, "words": words, "fail": None, "off": bool(a.get("off"))}
            if a.get("kind") == "play_macro":
                box["title"] = macro_label(a.get("file")) or "(no macro chosen)"
                times = int(a.get("times", 1) or 1)
                box["words"] = (f"{times} times" if times > 1 else "once") + (
                    f" · profile {a['profile']}" if a.get("profile") else "")
                box["fail"] = macro_label(a.get("on_fail")) or None
            out.append(box)
        return out

    def open_chain_chart(self, editor=None):
        """The open macro (or the one in Edit) as a chart: its steps from top to bottom, what happens
        when a run fails, and what the watched pictures do. In Edit, drag a box to move the step."""
        parent = editor.win if editor is not None else self.root
        win = tk.Toplevel(parent, bg=BG)
        win.title("Chain chart")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        hint = ("Drag a box up or down to move that step." if editor is not None
                else "Open it from Edit to move steps by dragging.")
        tk.Label(win, text=hint, bg=BG, fg=MUTED, font=F_SMALL, anchor="w").pack(fill="x", padx=18, pady=(12, 0))
        canvas = tk.Canvas(win, width=760, height=420, bg=FIELD, highlightthickness=0)
        canvas.pack(padx=18, pady=10)
        BW, BH, GAP, X0, Y0 = 250, 46, 26, 40, 24
        state = {"drag": None, "boxes": []}

        def steps_now():
            return editor.steps if editor is not None else (self.macro_steps() if (self.events or self.actions) else [])

        def draw():
            canvas.delete("all")
            boxes = self.chain_boxes(steps_now())
            state["boxes"] = boxes
            height = max(420, Y0 * 2 + len(boxes) * (BH + GAP) + 30)
            canvas.config(height=min(height, 640), scrollregion=(0, 0, 760, height))
            if not boxes:
                canvas.create_text(380, 200, text="No macro is open.", fill=MUTED, font=F_BASE)
            for i, b in enumerate(boxes):
                y = Y0 + i * (BH + GAP)
                colour = DIM if b["off"] else ACCENT
                rounded_rect(canvas, X0, y, X0 + BW, y + BH, 8, fill=CARD, outline=colour, tags=(f"box{i}",))
                canvas.create_text(X0 + 12, y + 14, text=short(b["title"], 30), fill=TEXT, font=F_BOLD, anchor="w",
                                   tags=(f"box{i}",))
                canvas.create_text(X0 + 12, y + 32, text=short(b["words"], 38), fill=MUTED, font=F_SMALL, anchor="w",
                                   tags=(f"box{i}",))
                if i + 1 < len(boxes):
                    canvas.create_line(X0 + BW / 2, y + BH, X0 + BW / 2, y + BH + GAP, fill=MUTED, arrow="last")
                if b["fail"]:
                    fx = X0 + BW + 50
                    canvas.create_line(X0 + BW, y + BH / 2, fx, y + BH / 2, fill=RED, arrow="last")
                    canvas.create_text(X0 + BW + 25, y + BH / 2 - 9, text="fails", fill=RED, font=F_SMALL)
                    rounded_rect(canvas, fx, y + 6, fx + 150, y + BH - 6, 8, fill=CARD, outline=RED)
                    canvas.create_text(fx + 10, y + BH / 2, text=short(b["fail"], 20), fill=TEXT, font=F_BASE,
                                       anchor="w")
            if boxes and self.loop_var.get():
                bottom_y = Y0 + (len(boxes) - 1) * (BH + GAP) + BH
                canvas.create_line(X0 + BW / 2, bottom_y, X0 + BW / 2, bottom_y + 14, X0 - 18, bottom_y + 14, X0 - 18,
                                   Y0 + BH / 2, X0, Y0 + BH / 2, fill=GREEN, arrow="last")
                canvas.create_text(X0 + BW / 2 + 8, bottom_y + 14, text="Repeat is on: back to the top", fill=GREEN,
                                   font=F_SMALL, anchor="w")
            # what the watched pictures do, on the right
            x = 520
            canvas.create_text(x, Y0 - 6, text="PICTURE WATCH" + ("" if self.watch_var.get() else "  (off)"),
                               fill=MUTED, font=F_SECTION, anchor="w")
            for i, p in enumerate(self._active_watch_pictures()[:7] if self.watch_var.get() else []):
                y = Y0 + 12 + i * 52
                rounded_rect(canvas, x, y, x + 220, y + 42, 8, fill=CARD, outline=AMBER)
                canvas.create_text(x + 10, y + 13, text="When " + short(p.get("name") or f"picture {i + 1}", 22)
                                   + " shows", fill=TEXT, font=F_BOLD, anchor="w")
                canvas.create_text(x + 10, y + 30, text=short(action_summary(p).split("  (")[0], 34), fill=MUTED,
                                   font=F_SMALL, anchor="w")

        def index_at(y):
            return max(0, min(len(state["boxes"]) - 1, int((y - Y0 + GAP / 2) // (BH + GAP))))

        def press(e):
            if editor is None or not state["boxes"] or not (X0 <= e.x <= X0 + BW):
                return
            state["drag"] = index_at(canvas.canvasy(e.y))
            canvas.itemconfig(f"box{state['drag']}", fill=ACCENT_DARK)

        def release(e):
            start = state["drag"]
            state["drag"] = None
            if start is None:
                return
            end = index_at(canvas.canvasy(e.y))
            if end != start:
                moved_id = editor.steps[start].get("id")
                editor.change(lambda: editor.steps.insert(end, editor.steps.pop(start)), select=moved_id)
            draw()
        canvas.bind("<ButtonPress-1>", press)
        canvas.bind("<ButtonRelease-1>", release)
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(0, 14))
        ttk.Button(bottom, text="Close", width=8, command=win.destroy).pack(side="right")
        ttk.Button(bottom, text="Refresh", width=8, command=draw).pack(side="right", padx=6)
        dark_title_bar(win)
        draw()
        win.draw, win.canvas, win.state, win.press, win.release = draw, canvas, state, press, release
        return win
