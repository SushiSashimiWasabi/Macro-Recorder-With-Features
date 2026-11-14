# PyInstaller recipe for the Mac app (MacroRecorder.app). Used by build_mac.sh, on a Mac only.
# The Windows .exe is built by build.bat instead.
import os

here = os.path.abspath(SPECPATH)

a = Analysis(
    [os.path.join(here, "macro_recorder.py")],
    pathex=[here],
    datas=[(os.path.join(here, "retry_default.png"), "."), (os.path.join(here, "default_logo.png"), "."),
           (os.path.join(here, "completed_default.png"), "."),
           (os.path.join(here, "failed_default.png"), ".")],
    hiddenimports=["image_watch", "lazy", "pynput.keyboard._darwin", "pynput.mouse._darwin", "WebKit", "AppKit", "Foundation", "certifi"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="MacroRecorder", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="MacroRecorder")


def doc_type(name, ext, rank):
    return {"CFBundleTypeName": name, "CFBundleTypeRole": "Viewer",
            "CFBundleTypeExtensions": [ext], "LSHandlerRank": rank}


app = BUNDLE(
    coll,
    name="MacroRecorder.app",
    bundle_identifier="local.macrorecorder",
    info_plist={
        "CFBundleDisplayName": "Macro Recorder",
        "NSHighResolutionCapable": True,
        # so .macro files open in this app when double-clicked (and others via "Open With")
        "CFBundleDocumentTypes": [
            doc_type("Macro Recorder macro", "macro", "Owner"),
            doc_type("luvmacro macro", "luvmacro", "Alternate"),
            doc_type("TinyTask macro", "rec", "Alternate"),
            doc_type("Jitbit macro", "mcr", "Alternate"),
            doc_type("AutoHotkey script", "ahk", "Alternate"),
        ],
    },
)
