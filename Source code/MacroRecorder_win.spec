# PyInstaller recipe for the Windows MacroRecorder.exe. Used by build.bat and GitHub.
# Normally the folder build: dist\MacroRecorder\ holds MacroRecorder.exe and a folder _internal beside
# it (starts in about a second, nothing to unpack). Set MR_ONEFILE=1 for the one-file exe instead
# (dist\MacroRecorder.exe: unpacks itself into Temp each time it starts; Releases keep it for copies
# from before 2.8, which can only update to one file).
# Set MR_PREVIEW=<folder with preview_main.py> to build the preview exe instead.
import os

here = os.path.abspath(SPECPATH)
preview_dir = os.environ.get("MR_PREVIEW")
entry = os.path.join(preview_dir, "preview_main.py") if preview_dir else os.path.join(here, "macro_recorder.py")

# Not needed by the app, so left out (smaller exe, faster start). The big one is OpenCV's video
# reader (about 30 MB): the app only reads pictures and GIFs, which OpenCV does without it.
EXCLUDE_MODULES = ["unittest", "pydoc", "doctest", "lib2to3", "xmlrpc", "pdb", "tkinter.test", "test",
                   "numpy.f2py", "numpy.testing", "setuptools", "pip"]
EXCLUDE_FILES = ("opencv_videoio_ffmpeg",)

a = Analysis(
    [entry],
    pathex=[here],
    datas=[(os.path.join(here, "retry_default.png"), "."), (os.path.join(here, "default_logo.png"), "."),
           (os.path.join(here, "completed_default.png"), "."),
           (os.path.join(here, "failed_default.png"), "."),
           (os.path.join(here, "disconnected_default.png"), ".")],
    hiddenimports=["image_watch", "lazy", "pynput.keyboard._win32", "pynput.mouse._win32"],
    excludes=EXCLUDE_MODULES,
)
a.binaries = [b for b in a.binaries if not os.path.basename(b[0]).lower().startswith(EXCLUDE_FILES)]
a.datas = [d for d in a.datas if not os.path.basename(d[0]).lower().startswith(EXCLUDE_FILES)]
pyz = PYZ(a.pure)
# a picture shown at once while the app starts; the app closes it when its window is ready
# (modern_ui.main). Set MR_NO_SPLASH=1 to build without it.
name = "MacroRecorder_Preview" if preview_dir else "MacroRecorder"
icon = os.path.join(here, "app_icon.ico")
splash = None
if not os.environ.get("MR_NO_SPLASH"):
    splash = Splash(os.path.join(here, "splash.png"), binaries=a.binaries, datas=a.datas, text_pos=None,
                    always_on_top=False)
if os.environ.get("MR_ONEFILE"):
    parts = [splash, splash.binaries] if splash else []
    exe = EXE(pyz, a.scripts, *parts, a.binaries, a.datas, [], name=name,
              console=False, upx=False, icon=icon)
else:
    exe = EXE(pyz, a.scripts, *([splash] if splash else []), [], exclude_binaries=True, name=name,
              console=False, upx=False, icon=icon, contents_directory="_internal")
    coll = COLLECT(exe, a.binaries, a.datas, *([splash.binaries] if splash else []), name=name, upx=False)
