"""Checks GitHub for a newer Macro Recorder and installs it.

The newest version is the repo's latest GitHub Release (made by .github/workflows/build.yml when
APP_VERSION in version.py goes up). Each Release has these files:
    MacroRecorder-Windows.zip            Windows, the folder build (MacroRecorder.exe + a hidden
                                         _internal folder beside it: starts in about a second)
    MacroRecorder.exe                    Windows, the same app as one file (unpacks itself each time it
                                         starts; kept so copies from before 2.8 can still update)
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


WIN_ZIP = "MacroRecorder-Windows.zip"
WIN_EXE = "MacroRecorder.exe"
INTERNAL = "_internal"  # the folder build's own folder beside the exe (PyInstaller's name for it)


def is_folder_build():
    """True when this is the Windows folder build (the exe with _internal beside it), not the
    one-file exe."""
    if not (IS_WIN and getattr(sys, "frozen", False)):
        return False
    here = os.path.dirname(os.path.abspath(sys.executable))
    own = os.path.normcase(os.path.abspath(getattr(sys, "_MEIPASS", "") or ""))
    return own == os.path.normcase(os.path.join(here, INTERNAL))


def asset_name():
    if IS_WIN:
        return WIN_ZIP
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
    assets = data.get("assets") or []
    asset = next((a for a in assets if a.get("name") == want), None)
    if asset is None and IS_WIN:
        # a Release without the folder zip: the one-file exe works as well
        asset = next((a for a in assets if a.get("name") == WIN_EXE), None)
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
        "name": asset.get("name") or want,
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
    """Run at start: removes the previous version left beside the exe by an update (the exe, and
    for the folder build its _internal folder)."""
    if not (IS_WIN and getattr(sys, "frozen", False)):
        return
    import shutil
    here = os.path.dirname(os.path.abspath(sys.executable))
    old = _old_path(sys.executable)
    old_internal = os.path.join(here, INTERNAL + ".old")
    stage = os.path.join(here, STAGE)
    for _ in range(20):  # the old copy may still be closing for a moment
        if not os.path.exists(old):
            break
        try:
            os.remove(old)
            break
        except OSError:
            time.sleep(0.5)
    for folder in (old_internal, stage):
        if os.path.isdir(folder):
            shutil.rmtree(folder, ignore_errors=True)


def cleanup_leftover_unpacks():
    """Run at start: the built app unpacks itself into a _MEI... folder in Temp each time it starts
    (about 150 MB) and removes it when it closes. A copy that was force-closed or crashed leaves it
    behind, so old ones of this app are removed here. A folder that's still in use (another copy
    is running) is left alone: its Python DLL can't be opened for writing then."""
    import glob
    import shutil
    own = getattr(sys, "_MEIPASS", None)
    if not own or is_folder_build():  # (the folder build doesn't unpack itself)
        return
    temp = os.path.dirname(own)
    try:
        names = os.listdir(temp)
    except OSError:
        return
    for name in names:
        path = os.path.join(temp, name)
        if not name.startswith("_MEI") or os.path.normcase(path) == os.path.normcase(own):
            continue
        # only this app's folders (it bundles retry_default.png), and not younger than a minute
        if not os.path.isfile(os.path.join(path, "retry_default.png")):
            continue
        try:
            if time.time() - os.path.getmtime(path) < 60:
                continue
            dlls = glob.glob(os.path.join(path, "python3*.dll"))
            if not dlls:
                continue
            for dll in dlls:  # a running copy has these loaded: opening one for writing fails
                open(dll, "r+b").close()
            gone = path + ".old"
            os.rename(path, gone)
        except OSError:
            continue
        shutil.rmtree(gone, ignore_errors=True)


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


# ---------------------------------------------------------------- Windows, folder build

STAGE = "_update_new"  # the new version is unpacked here, beside the app, before it's put in place

# Runs after the app has closed (an app can't replace its own _internal folder while it runs: its
# files are in use). Every step is undone if a later one fails, so the app is never left half old,
# half new: the old exe and _internal are renamed to *.old first and only removed by the new copy
# once it has started.
SWAP_SCRIPT = r"""
param([int]$AppPid, [string]$Dir, [string]$ExeName, [string]$Stage, [string]$Log, [int]$Start)
$ErrorActionPreference = 'Stop'
function Note($t) { Add-Content -LiteralPath $Log -Value ((Get-Date -Format 'HH:mm:ss') + ' ' + $t) }
$exe = Join-Path $Dir $ExeName
$int = Join-Path $Dir '_internal'
$exeOld = $exe + '.old'
$intOld = $int + '.old'
try { Wait-Process -Id $AppPid -Timeout 60 -ErrorAction Stop } catch { }
Start-Sleep -Milliseconds 300
$movedExe = $false; $movedInt = $false; $ok = $false
try {
    if (Test-Path -LiteralPath $exeOld) { Remove-Item -LiteralPath $exeOld -Force }
    if (Test-Path -LiteralPath $intOld) { Remove-Item -LiteralPath $intOld -Recurse -Force }
    if (Test-Path -LiteralPath $int) { Rename-Item -LiteralPath $int -NewName '_internal.old'; $movedInt = $true }
    if (Test-Path -LiteralPath $exe) { Rename-Item -LiteralPath $exe -NewName ($ExeName + '.old'); $movedExe = $true }
    Move-Item -LiteralPath (Join-Path $Stage '_internal') -Destination $int
    Move-Item -LiteralPath (Join-Path $Stage 'MacroRecorder.exe') -Destination $exe
    (Get-Item -LiteralPath $int -Force).Attributes = 'Directory, Hidden'
    $ok = $true
    Note 'Update put in place.'
} catch {
    Note ('Update failed, putting the old version back: ' + $_)
    try {
        if ($movedExe) { if (Test-Path -LiteralPath $exe) { Remove-Item -LiteralPath $exe -Force }; Rename-Item -LiteralPath $exeOld -NewName $ExeName }
        if ($movedInt) { if (Test-Path -LiteralPath $int) { Remove-Item -LiteralPath $int -Recurse -Force }; Rename-Item -LiteralPath $intOld -NewName '_internal' }
    } catch { Note ('Putting the old version back failed: ' + $_) }
}
if ($Start -eq 1 -and (Test-Path -LiteralPath $exe)) { Start-Process -FilePath $exe -WorkingDirectory $Dir }
if ($ok) { Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction SilentlyContinue }
"""


def unpack_folder_update(zip_file, app_dir):
    """Unpacks the downloaded MacroRecorder-Windows.zip into _update_new beside the app and checks it
    (an exe and a complete _internal folder). Returns that folder. Nothing of the app is touched."""
    import shutil
    import zipfile
    stage = os.path.join(app_dir, STAGE)
    if os.path.isdir(stage):
        shutil.rmtree(stage, ignore_errors=True)
    try:
        with zipfile.ZipFile(zip_file) as z:
            bad = z.testzip()
            if bad is not None:
                raise UpdateError(f"The download is damaged ({bad}). Try again later.")
            for name in z.namelist():  # nothing may land outside the folder
                target = os.path.normpath(os.path.join(stage, name))
                if not target.startswith(os.path.normpath(stage) + os.sep):
                    raise UpdateError("The download has unexpected files in it.")
            z.extractall(stage)
    except zipfile.BadZipFile:
        shutil.rmtree(stage, ignore_errors=True)
        raise UpdateError("The download isn't a complete zip file. Try again later.")
    except OSError as e:
        shutil.rmtree(stage, ignore_errors=True)
        raise UpdateError(f"Couldn't unpack the new version ({e}). Is the disk full?")
    exe = os.path.join(stage, WIN_EXE)
    internal = os.path.join(stage, INTERNAL)
    try:
        with open(exe, "rb") as f:
            is_exe = f.read(2) == b"MZ"
    except OSError:
        is_exe = False
    import glob
    if not is_exe or not glob.glob(os.path.join(internal, "python3*.dll")):
        shutil.rmtree(stage, ignore_errors=True)
        raise UpdateError("The download doesn't have a complete Macro Recorder in it.")
    return stage


def install_windows_folder(zip_file, exe=None, pid=None, start=True, wait=False):
    """Puts the folder build from zip_file in place of this app: unpacks and checks it beside the
    app, then a small script waits for this app to close, swaps the exe and _internal (undoing
    everything if a step fails) and starts the new version. Works from the one-file exe too: that
    one becomes the folder build (its exe is replaced and _internal is added beside it).
    Returns the script's process; the caller then closes this app (unless wait)."""
    exe = os.path.abspath(exe or sys.executable)
    app_dir = os.path.dirname(exe)
    stage = unpack_folder_update(zip_file, app_dir)
    try:
        os.remove(zip_file)
    except OSError:
        pass
    work = tempfile.mkdtemp(prefix="MacroRecorder_update_")
    script = os.path.join(work, "swap.ps1")
    with open(script, "w", encoding="utf-8-sig") as f:
        f.write(SWAP_SCRIPT)
    log = os.path.join(work, "update_log.txt")  # (in Temp: what the swap did, for a report)
    args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-WindowStyle", "Hidden", "-File", script, "-AppPid", str(pid or os.getpid()), "-Dir", app_dir,
            "-ExeName", os.path.basename(exe), "-Stage", stage, "-Log", log, "-Start", "1" if start else "0"]
    # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP (not DETACHED_PROCESS: PowerShell does nothing under it)
    flags = 0x08000000 | 0x00000200
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI") and k != "_MEIPASS2"}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    proc = subprocess.Popen(args, cwd=work, env=env, close_fds=True, creationflags=flags)
    proc.log = log
    if wait:
        proc.wait(120)
    return proc


def install(new_file):
    if IS_WIN:
        with open(new_file, "rb") as f:
            is_zip = f.read(2) == b"PK"
        return install_windows_folder(new_file) if is_zip else install_windows(new_file)
    if IS_MAC:
        return install_mac(new_file)
    raise UpdateError("Updating isn't supported here.")


def download_path(name=None):
    name = name or asset_name() or "update"
    if IS_WIN:
        # same folder as the exe when possible, so putting it in place is a quick rename
        folder = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else tempfile.gettempdir()
        test = os.path.join(folder, name + ".download")
        try:
            open(test, "ab").close()
            return test
        except OSError:
            return os.path.join(tempfile.gettempdir(), name + ".download")
    return os.path.join(tempfile.mkdtemp(prefix="MacroRecorder_dl_"), name)
