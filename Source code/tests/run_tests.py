"""Runs every test_*.py here, each in its own Python, and says whether all of them passed.

    py "Source code/tests/run_tests.py"            (add --one-by-one to run them one after another)

GitHub runs this before it builds and publishes a new version (see .github/workflows/build.yml), so
a version that breaks recording, playback, results or the Discord card never reaches anyone. The
tests send no real mouse or keyboard input and use throwaway settings folders.

Tests that don't open windows run a few at a time (quicker); the ones that open windows run one by
one afterwards, so they don't take the focus from each other."""
import glob
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

here = os.path.dirname(os.path.abspath(__file__))
src = os.path.dirname(here)
# these open windows (Edit, Settings, Picture watch, dashboards...): one at a time
WINDOW_TESTS = {"test_automation.py", "test_chains.py", "test_editor.py", "test_pictures.py", "test_preview1.py", "test_remote.py",
                "test_settings_undo.py", "test_stage3.py", "test_stage4.py", "test_windows.py"}
AT_ONCE = 4  # how many of the other tests run side by side


def run(path):
    started = time.time()
    proc = subprocess.run([sys.executable, "-X", "utf8", path, src], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600)
    return path, proc, time.time() - started


def report(path, proc, took):
    name = os.path.basename(path)
    out = proc.stdout + proc.stderr
    m = re.search(r"(\d+) of (\d+) passed", out)
    passed, count = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    ok = proc.returncode == 0 and m is not None and passed == count
    print(f"{'OK  ' if ok else 'FAIL'} {name}: {passed} of {count} passed ({took:.0f} s)", flush=True)
    if not ok:
        for line in out.splitlines():
            if line.startswith("FAIL") or "Error" in line or "Traceback" in line:
                print("     " + line)
    return ok, passed, count


def main():
    began = time.time()
    paths = sorted(glob.glob(os.path.join(here, "test_*.py")))
    one_by_one = "--one-by-one" in sys.argv
    side_by_side = [] if one_by_one else [p for p in paths if os.path.basename(p) not in WINDOW_TESTS]
    alone = [p for p in paths if p not in side_by_side]
    finished = []
    if side_by_side:
        with ThreadPoolExecutor(AT_ONCE) as pool:
            finished += list(pool.map(run, side_by_side))
    finished += [run(p) for p in alone]
    failed, total_pass, total = [], 0, 0
    for path, proc, took in sorted(finished, key=lambda r: r[0]):
        ok, passed, count = report(path, proc, took)
        total_pass += passed
        total += count
        if not ok:
            failed.append(os.path.basename(path))
    print(f"\n{total_pass} of {total} checks passed in {time.time() - began:.0f} s"
          + (f"; failed: {', '.join(failed)}" if failed else ""))
    sys.exit(1 if failed or total == 0 else 0)


if __name__ == "__main__":
    main()
