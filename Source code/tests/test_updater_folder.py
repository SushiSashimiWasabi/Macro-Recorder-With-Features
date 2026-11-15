"""Updates for the Windows folder build (MacroRecorder.exe + a hidden _internal folder): which file is
downloaded, unpacking and checking it, and (on Windows) the swap after the app has closed, including
putting the old version back when a step fails and moving a one-file copy over to the folder build.
Only throwaway folders are used; nothing is downloaded and no real app is started."""
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile

src = sys.argv[1]
sys.path.insert(0, src)
import updater  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


def read(path):
    with open(path, "rb") as f:
        return f.read()


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def make_zip(path, exe=b"MZ new exe", dll=True, extra=None):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        if exe is not None:
            z.writestr("MacroRecorder.exe", exe)
        if dll:
            z.writestr("_internal/python313.dll", b"new dll")
        z.writestr("_internal/base_library.zip", b"new lib")
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return path


def make_app(folder, internal=True):
    write(os.path.join(folder, "MacroRecorder.exe"), b"MZ old exe")
    if internal:
        write(os.path.join(folder, "_internal", "python313.dll"), b"old dll")
    write(os.path.join(folder, "my macro.macro"), b"keep me")  # something of the user's beside it
    return folder


# ------------------------------------------------------------ which file is downloaded

class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def release(*names):
    assets = [{"name": n, "browser_download_url": "https://x/" + n, "size": 10,
               "digest": "sha256:" + "ab" * 32} for n in names]
    return json.dumps({"tag_name": "v99.0", "body": "notes", "assets": assets}).encode()


real_get, real_win = updater._get, updater.IS_WIN
updater.IS_WIN = True
updater._get = lambda url, timeout=15: FakeResponse(release("MacroRecorder.exe", "MacroRecorder-Windows.zip"))
info = updater.check()
check("check: the folder zip is chosen when the Release has it", info and info["name"] == "MacroRecorder-Windows.zip",
      info and info["name"])
updater._get = lambda url, timeout=15: FakeResponse(release("MacroRecorder.exe"))
info = updater.check()
check("check: a Release with only the one-file exe still works", info and info["name"] == "MacroRecorder.exe",
      info and info["name"])
check("download path is named after the file", updater.download_path("MacroRecorder-Windows.zip").endswith(
    "MacroRecorder-Windows.zip.download"))
updater._get = real_get

# ------------------------------------------------------------ unpacking and checking

tmp = tempfile.mkdtemp(prefix="mr_update_test_")
app = make_app(os.path.join(tmp, "app1"))
stage = updater.unpack_folder_update(make_zip(os.path.join(tmp, "good.zip")), app)
check("unpack: a good zip lands beside the app", os.path.isfile(os.path.join(stage, "MacroRecorder.exe")) and
      os.path.isfile(os.path.join(stage, "_internal", "python313.dll")), stage)
check("unpack: the app itself is untouched", read(os.path.join(app, "MacroRecorder.exe")) == b"MZ old exe")
for label, kwargs in (("no exe", {"exe": None}), ("not a program", {"exe": b"hello"}), ("no Python DLL", {"dll": False}),
                      ("a file outside the folder", {"extra": {"../evil.txt": b"x"}})):
    try:
        updater.unpack_folder_update(make_zip(os.path.join(tmp, "bad.zip"), **kwargs), app)
        refused = False
    except updater.UpdateError:
        refused = True
    check(f"unpack: refused when the zip has {label}", refused and not os.path.exists(os.path.join(app, updater.STAGE))
          and not os.path.exists(os.path.join(tmp, "evil.txt")))
write(os.path.join(tmp, "broken.zip"), b"PK\x03\x04 not really a zip")
try:
    updater.unpack_folder_update(os.path.join(tmp, "broken.zip"), app)
    refused = False
except updater.UpdateError:
    refused = True
check("unpack: a broken download is refused", refused)

# ------------------------------------------------------------ is this the folder build?

real_frozen, real_exe, real_mei = getattr(sys, "frozen", None), sys.executable, getattr(sys, "_MEIPASS", None)
sys.frozen = True
sys.executable = os.path.join(app, "MacroRecorder.exe")
sys._MEIPASS = os.path.join(app, "_internal")
check("is_folder_build: exe with _internal beside it", updater.is_folder_build())
sys._MEIPASS = os.path.join(tempfile.gettempdir(), "_MEI12345")
check("is_folder_build: the one-file exe (unpacked into Temp) isn't", not updater.is_folder_build())

# leftovers of an update are removed when the new version starts
write(os.path.join(app, "MacroRecorder.exe.old"), b"old")
write(os.path.join(app, "_internal.old", "python313.dll"), b"old")
write(os.path.join(app, updater.STAGE, "x"), b"x")
updater.cleanup_old()
check("cleanup: exe.old, _internal.old and an unfinished unpack are removed",
      not any(os.path.exists(os.path.join(app, n)) for n in ("MacroRecorder.exe.old", "_internal.old", updater.STAGE)))
check("cleanup: the user's own files stay", read(os.path.join(app, "my macro.macro")) == b"keep me")
sys.executable = real_exe
if real_frozen is None:
    del sys.frozen
else:
    sys.frozen = real_frozen
if real_mei is None:
    del sys._MEIPASS
else:
    sys._MEIPASS = real_mei
updater.IS_WIN = real_win

# ------------------------------------------------------------ the swap itself (Windows only)


def stand_in(seconds):
    """A process that plays the part of the closing app."""
    return subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({seconds})"])


def hidden(path):
    import ctypes
    attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
    return attrs != -1 and bool(attrs & 0x2)


if sys.platform == "win32":
    # the folder build updating itself
    app = make_app(os.path.join(tmp, "app2"))
    fake = stand_in(1.5)
    t0 = time.time()
    proc = updater.install_windows_folder(make_zip(os.path.join(tmp, "u2.zip")),
                                          exe=os.path.join(app, "MacroRecorder.exe"), pid=fake.pid,
                                          start=False, wait=True)
    log = read(proc.log).decode("utf-8", "replace") if os.path.exists(proc.log) else ""
    check("swap: waited for the app to close first", time.time() - t0 >= 1.3, f"{time.time() - t0:.1f} s")
    check("swap: the new exe and _internal are in place", read(os.path.join(app, "MacroRecorder.exe")) == b"MZ new exe"
          and read(os.path.join(app, "_internal", "python313.dll")) == b"new dll", log)
    check("swap: the old ones are kept as .old until the new version starts",
          read(os.path.join(app, "MacroRecorder.exe.old")) == b"MZ old exe" and
          read(os.path.join(app, "_internal.old", "python313.dll")) == b"old dll")
    check("swap: _internal is hidden", hidden(os.path.join(app, "_internal")))
    check("swap: the unpacked copy is cleaned up", not os.path.exists(os.path.join(app, updater.STAGE)))
    check("swap: the user's files beside the app stay", read(os.path.join(app, "my macro.macro")) == b"keep me")

    # a step fails (the new exe vanished): everything is put back as it was
    app = make_app(os.path.join(tmp, "app3"))
    fake = stand_in(2.0)
    proc = updater.install_windows_folder(make_zip(os.path.join(tmp, "u3.zip")),
                                          exe=os.path.join(app, "MacroRecorder.exe"), pid=fake.pid, start=False)
    os.remove(os.path.join(app, updater.STAGE, "MacroRecorder.exe"))  # (while the script waits for the app)
    proc.wait(120)
    log = read(proc.log).decode("utf-8", "replace") if os.path.exists(proc.log) else ""
    check("failed swap: the old exe and _internal are back", read(os.path.join(app, "MacroRecorder.exe")) == b"MZ old exe"
          and read(os.path.join(app, "_internal", "python313.dll")) == b"old dll", log)
    check("failed swap: no .old leftovers in the way", not os.path.exists(os.path.join(app, "MacroRecorder.exe.old"))
          and not os.path.exists(os.path.join(app, "_internal.old")))
    check("failed swap: the log says what happened", "failed" in log.lower(), log)

    # a one-file copy (from before 2.8) moves over to the folder build
    app = make_app(os.path.join(tmp, "app4"), internal=False)
    fake = stand_in(0.5)
    proc = updater.install_windows_folder(make_zip(os.path.join(tmp, "u4.zip")),
                                          exe=os.path.join(app, "MacroRecorder.exe"), pid=fake.pid,
                                          start=False, wait=True)
    check("one-file copy: becomes the folder build", read(os.path.join(app, "MacroRecorder.exe")) == b"MZ new exe"
          and os.path.isfile(os.path.join(app, "_internal", "python313.dll")) and hidden(os.path.join(app, "_internal")))

    # the preview exe keeps its own name
    app = os.path.join(tmp, "app5")
    write(os.path.join(app, "MacroRecorder_Preview.exe"), b"MZ old exe")
    fake = stand_in(0.5)
    updater.install_windows_folder(make_zip(os.path.join(tmp, "u5.zip")),
                                   exe=os.path.join(app, "MacroRecorder_Preview.exe"), pid=fake.pid,
                                   start=False, wait=True)
    check("preview: the new exe keeps the preview's name",
          read(os.path.join(app, "MacroRecorder_Preview.exe")) == b"MZ new exe" and
          not os.path.exists(os.path.join(app, "MacroRecorder.exe")))
else:
    print("(the swap itself is only checked on Windows)")

import shutil  # noqa: E402

shutil.rmtree(tmp, ignore_errors=True)
failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)} of {len(results)} passed")
sys.exit(1 if failed else 0)
