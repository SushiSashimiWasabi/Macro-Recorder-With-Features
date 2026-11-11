#!/bin/bash
# Builds MacroRecorder.app on a Mac and puts it in "Mac build version".
# Run it in Terminal from this folder:   bash build_mac.sh
# Needs Python 3 from python.org (it includes Tk, which the window uses).
set -e
cd "$(dirname "$0")"
WORK="${TMPDIR:-/tmp}/MacroRecorder_build"
OUT="Mac build version"
python3 -m pip install -q --upgrade pyinstaller -r "Source code/requirements.txt"
python3 -m PyInstaller --noconfirm --clean \
  --distpath "$WORK/dist" --workpath "$WORK/work" \
  "Source code/MacroRecorder_mac.spec"
mkdir -p "$OUT"
rm -rf "$OUT/MacroRecorder.app"
ditto "$WORK/dist/MacroRecorder.app" "$OUT/MacroRecorder.app"
echo
echo "Built \"$OUT/MacroRecorder.app\""
