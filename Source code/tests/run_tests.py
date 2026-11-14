"""Runs every test_*.py here, each in its own Python, and says whether all of them passed.

    py "Source code/tests/run_tests.py"

GitHub runs this before it builds and publishes a new version (see .github/workflows/build.yml), so
a version that breaks recording, playback, results or the Discord card never reaches anyone. The
tests send no real mouse or keyboard input and use throwaway settings folders."""
import glob
import os
import re
import subprocess
import sys
import time

here = os.path.dirname(os.path.abspath(__file__))
src = os.path.dirname(here)
failed = []
total_pass = total = 0
for path in sorted(glob.glob(os.path.join(here, "test_*.py"))):
    name = os.path.basename(path)
    started = time.time()
    proc = subprocess.run([sys.executable, "-X", "utf8", path, src], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600)
    out = proc.stdout + proc.stderr
    m = re.search(r"(\d+) of (\d+) passed", out)
    passed, count = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    total_pass += passed
    total += count
    ok = proc.returncode == 0 and m is not None and passed == count
    print(f"{'OK  ' if ok else 'FAIL'} {name}: {passed} of {count} passed ({time.time() - started:.0f} s)")
    if not ok:
        failed.append(name)
        for line in out.splitlines():
            if line.startswith("FAIL") or "Error" in line or "Traceback" in line:
                print("     " + line)
print(f"\n{total_pass} of {total} checks passed" + (f"; failed: {', '.join(failed)}" if failed else ""))
sys.exit(1 if failed or total == 0 else 0)
