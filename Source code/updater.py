"""Checks GitHub for a newer Macro Recorder and installs it.

The newest version is the repo's latest GitHub Release (made by .github/workflows/build.yml when
APP_VERSION in version.py goes up). Each Release has these files:
    MacroRecorder.exe                    Windows
    MacroRecorder-Mac-AppleSilicon.zip   Mac with an M1 or newer chip
    MacroRecorder-Mac-Intel.zip          older Intel Mac

Installing only works in the built app (the .exe / .app), not when running from the source code.
Nothing personal is sent: the only requests are GitHub's public "latest release" page and the
file download.
"""
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from version import APP_VERSION

REPO = "SushiSashimiWasabi/Macro-Recorder-With-Features"
# only for testing: point the check at another "latest release" address
LATEST_URL = os.environ.get("MACRO_RECORDER_UPDATE_URL") or f"https://api.github.com/repos/{REPO}/releases/latest"
USER_AGENT = "MacroRecorder-updater"
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


class UpdateError(Exception):
    pass


def version_tuple(text):
    """'v2.10.1' -> (2, 10, 1). Anything that isn't a number counts as 0."""
    text = str(text or "").strip().lstrip("vV")
    out = []
    for part in text.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    while len(out) > 1 and out[-1] == 0:
        out.pop()
    return tuple(out)


def is_newer(remote, local=APP_VERSION):
    return version_tuple(remote) > version_tuple(local)


def can_install():
    """True for the built app (PyInstaller sets sys.frozen); from source there's nothing to replace."""
    return bool(getattr(sys, "frozen", False)) and (IS_WIN or IS_MAC)


def asset_name():
    if IS_WIN:
        return "MacroRecorder.exe"
    if IS_MAC:
        return "MacroRecorder-Mac-AppleSilicon.zip" if platform.machine() == "arm64" else "MacroRecorder-Mac-Intel.zip"
    return None


def _ssl_context():
    """The Mac app's Python has no certificate list of its own, so use certifi's there."""
    import ssl
    if IS_MAC:
        try:
            import certifi
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
    return ssl.create_default_context()


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    ctx = _ssl_context() if url.startswith("https:") else None
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def check(timeout=15):
    """Returns None when this is the newest version, else a dict:
    {version, notes, url, size, sha256, page}. Raises UpdateError when GitHub can't be reached."""
    try:
        with _get(LATEST_URL, timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateError("No published version on GitHub yet.")
        if e.code in (403, 429):  # GitHub allows 60 checks an hour per internet connection
            raise UpdateError("GitHub got too many checks from your internet connection. Try again in an hour.")
        raise UpdateError(f"GitHub didn't answer (error {e.code}). Try again later.")
    except Exception as e:
        raise UpdateError(f"Couldn't reach GitHub ({e}).")
    tag = data.get("tag_name") or ""
    if not is_newer(tag):
        return None
    want = asset_name()
    asset = next((a for a in data.get("assets") or [] if a.get("name") == want), None)
    if asset is None:
        raise UpdateError(f"Version {tag.lstrip('vV')} is out, but it has no {want} yet.")
    digest = str(asset.get("digest") or "")
    return {
        "version": tag.lstrip("vV"),
        "notes": (data.get("body") or "").strip(),
        "url": asset.get("browser_download_url"),
        "size": int(asset.get("size") or 0),
        "sha256": digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else "",
        "page": data.get("html_url") or f"https://github.com/{REPO}/releases/latest",
    }


def download(info, dest, progress=None):
    """Saves the new file to dest, checking its size and SHA-256 (when GitHub gives one)."""
    sha = hashlib.sha256()
    done = 0
    try:
        with _get(info["url"], timeout=60) as r, open(dest, "wb") as out:
            total = info.get("size") or int(r.headers.get("Content-Length") or 0)
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except Exception as e:
        raise UpdateError(f"The download stopped ({e}).")
    if info.get("size") and done != info["size"]:
        raise UpdateError("The download is incomplete. Try again later.")
    if info.get("sha256") and sha.hexdigest() != info["sha256"]:
        raise UpdateError("The downloaded file doesn't match the release. Try again later.")
    return dest


# ---------------------------------------------------------------- Windows

def _old_path(exe):
    return exe + ".old"


def cleanup_old():
    """Run at start: removes the previous version left beside the exe by an update."""
    if not (IS_WIN and getattr(sys, "frozen", False)):
        return
    old = _old_path(sys.executable)
    for _ in range(20):  # the old copy may still be closing for a moment
        if not os.path.exists(old):
            return
        try:
            os.remove(old)
            return
        except OSError:
            time.sleep(0.5)


def install_windows(new_file, exe=None):
    """Puts new_file in place of the running exe and starts it. Windows lets a running exe be
    renamed (not overwritten), so: exe -> exe.old, new -> exe, start exe. The new copy deletes
    exe.old when it starts. Returns the started process; the caller then closes this app."""
    exe = exe or sys.executable
    with open(new_file, "rb") as f:
        if f.read(2) != b"MZ":
            raise UpdateError("The downloaded file isn't a Windows program.")
    old = _old_path(exe)
    try:
        if os.path.exists(old):
            os.remove(old)
    except OSError:
        raise UpdateError(f"Couldn't remove the leftover {os.path.basename(old)}. Close every "
                          "Macro Recorder window and try again.")
    try:
        os.replace(exe, old)
    except OSError as e:
        raise UpdateError(f"Couldn't move the current version aside ({e}).")
    try:
        os.replace(new_file, exe)
    except OSError:
        try:  # moving across drives (Temp on C:, app on D:) needs a copy
            import shutil
            shutil.copyfile(new_file, exe)
            os.remove(new_file)
        except Exception as e:
            os.replace(old, exe)  # put the old version back
            raise UpdateError(f"Couldn't put the new version in place ({e}).")
    # the PyInstaller bootloader of the new copy must not inherit this one's temp folder
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI") and k != "_MEIPASS2"}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return subprocess.Popen([exe], cwd=os.path.dirname(exe), env=env, close_fds=True,
                            creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | NEW_PROCESS_GROUP


# ---------------------------------------------------------------- Mac

def mac_app_path():
    """/…/MacroRecorder.app for the running app, or None."""
    p = os.path.abspath(sys.executable)
    while p and p != "/":
        if p.endswith(".app"):
            return p
        p = os.path.dirname(p)
    return None


def install_mac(zip_file):
    """Unzips the new MacroRecorder.app, then a small script waits for this app to quit, swaps
    the bundles and opens the new one. The caller then closes this app."""
    app = mac_app_path()
    if not app:
        raise UpdateError("Couldn't find MacroRecorder.app.")
    work = tempfile.mkdtemp(prefix="MacroRecorder_update_")
    if subprocess.call(["ditto", "-x", "-k", zip_file, work]) != 0:
        raise UpdateError("Couldn't unzip the new version.")
    new_app = os.path.join(work, "MacroRecorder.app")
    if not os.path.isdir(new_app):
        raise UpdateError("The download has no MacroRecorder.app in it.")
    subprocess.call(["xattr", "-dr", "com.apple.quarantine", new_app])
    script = os.path.join(work, "swap.sh")
    with open(script, "w") as f:
        f.write(
            '#!/bin/bash\n'
            'while kill -0 "$1" 2>/dev/null; do sleep 0.3; done\n'
            'rm -rf "$2.old" && mv "$2" "$2.old" && ditto "$3" "$2" && rm -rf "$2.old"\n'
            'if [ ! -d "$2" ]; then mv "$2.old" "$2"; fi\n'
            'open "$2"\n'
            'rm -rf "$4"\n')
    os.chmod(script, 0o755)
    return subprocess.Popen(["/bin/bash", script, str(os.getpid()), app, new_app, work],
                            start_new_session=True, close_fds=True)


def install(new_file):
    if IS_WIN:
        return install_windows(new_file)
    if IS_MAC:
        return install_mac(new_file)
    raise UpdateError("Updating isn't supported here.")


def download_path():
    name = asset_name() or "update"
    if IS_WIN:
        # same folder as the exe when possible, so putting it in place is a quick rename
        folder = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else tempfile.gettempdir()
        test = os.path.join(folder, "MacroRecorder.exe.download")
        try:
            open(test, "ab").close()
            return test
        except OSError:
            return os.path.join(tempfile.gettempdir(), "MacroRecorder.exe.download")
    return os.path.join(tempfile.mkdtemp(prefix="MacroRecorder_dl_"), name)
