# PyInstaller recipe for the Windows MacroRecorder.exe (one file). Used by build.bat and GitHub.
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
    datas=[(os.path.join(here, "retry_default.png"), "."), (os.path.join(here, "default_logo.png"), ".")],
    hiddenimports=["pynput.keyboard._win32", "pynput.mouse._win32"],
    excludes=EXCLUDE_MODULES,
)
a.binaries = [b for b in a.binaries if not os.path.basename(b[0]).lower().startswith(EXCLUDE_FILES)]
a.datas = [d for d in a.datas if not os.path.basename(d[0]).lower().startswith(EXCLUDE_FILES)]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name="MacroRecorder_Preview" if preview_dir else "MacroRecorder",
          console=False, upx=False, icon=os.path.join(here, "app_icon.ico"))
