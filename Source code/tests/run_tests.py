"""Runs the test_*.py files here, each in its own Python, and says whether all of them passed.

    py "Source code/tests/run_tests.py"                     every test (add --one-by-one: one after another)
    py "Source code/tests/run_tests.py" --group security    one group (or several: --group timing,discord)
    py "Source code/tests/run_tests.py" --test remote       one test file (test_remote.py), or several
    py "Source code/tests/run_tests.py" --list              the groups and their files

GitHub runs these on every push (see .github/workflows/tests.yml), each group as its own job, and
before it builds and publishes a new version, so a version that breaks something never reaches anyone.
The tests send no real mouse or keyboard input and use throwaway settings folders.

On GitHub's computers (the CI variable is set) checks that need Kong's real PC (a second screen and
such) print "SKIP (PC only)" instead of running; they're counted in the summary.

    --coverage        measure how much of the app's code the tests ran (needs: pip install coverage)
    --summary FILE    also write the results as a Markdown table (GitHub shows it on the run's page)

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
WINDOW_TESTS = {"test_automation.py", "test_chains.py", "test_editor.py", "test_pictures.py", "test_preview1.py",
                "test_preview2.py", "test_preview3.py", "test_preview3_edges.py", "test_preview3_actions.py", "test_preview4.py",
                "test_security.py", "test_remote.py", "test_settings_undo.py", "test_stage3.py", "test_stage4.py",
                "test_windows.py"}
AT_ONCE = 4  # how many of the other tests run side by side

# (2.12) the groups GitHub runs as separate jobs (each file in one group)
GROUPS = {
    "basic": ["test_steps.py", "test_playback.py", "test_editor.py", "test_windows.py", "test_settings_undo.py",
              "test_stage3.py", "test_stage4.py", "test_automation.py", "test_chains.py", "test_pictures.py",
              "test_results.py", "test_real_screen.py", "test_preview1.py", "test_preview2.py",
              "test_updater_folder.py", "test_preview4.py"],
    "security": ["test_files.py", "test_security.py"],
    "timing": ["test_preview3.py"],
    "discord": ["test_remote.py"],
    "edges": ["test_preview3_edges.py"],
    "edit-actions": ["test_preview3_actions.py"],
}
GROUP_NAMES = {"basic": "Basic (recording, playback, Edit, results, Settings)",
               "security": "Shared files and security",
               "timing": "Timing (alarm / timer, stuck guard, late result, colour)",
               "discord": "Discord and the phone remote",
               "edges": "Break-it edge tests",
               "edit-actions": "Edit actions (Do maths, Go to, Type into a window…)"}


def group_of(name):
    return next((g for g, files in GROUPS.items() if name in files), "other")


COVDATA = os.path.join(os.path.dirname(src), "covdata")  # (coverage files, one per test file)


HANG_AFTER = 150  # seconds before a test counts as hung (the slowest takes ~45 s; jobs stop at 10 min)


def run(path, coverage=False):
    started = time.time()
    cmd = [sys.executable, "-X", "utf8"]
    env = None
    if coverage:
        # an absolute place: a test that changes folders can't put its coverage file somewhere else
        os.makedirs(COVDATA, exist_ok=True)
        env = dict(os.environ, COVERAGE_FILE=os.path.join(COVDATA, ".coverage"))
        cmd += ["-m", "coverage", "run", "-p", f"--source={src}", "--omit=*/tests/*"]
    args = [path, src]
    if not coverage:
        # (2.13) a test that hangs prints where every thread is stuck and ends, before the runner gives up on it
        # (Macs: sooner, so the whole run fits in GitHub's 30 minutes and every test still reports)
        args = ["-c", "import faulthandler, runpy, sys; faulthandler.dump_traceback_later(%d, exit=True); "
                      "sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')" % HANG_AFTER,
                path, src]
    try:
        proc = subprocess.run(cmd + args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=900, env=env)
    except subprocess.TimeoutExpired as exc:
        # (2.13) a test that hangs is a FAIL with what it printed so far, not a crash of the whole run
        def text(b):
            return b.decode("utf-8", "replace") if isinstance(b, bytes) else (b or "")
        proc = subprocess.CompletedProcess(exc.cmd, 1, text(exc.stdout),
                                           text(exc.stderr) + "\nFAIL the test hung: stopped after 900 s (Error)")
    return path, proc, time.time() - started


def report(path, proc, took):
    name = os.path.basename(path)
    out = proc.stdout + proc.stderr
    m = re.search(r"(\d+) of (\d+) passed", out)
    passed, count = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    ok = proc.returncode == 0 and m is not None and passed == count
    # (2.12) skipped checks: "SKIP (PC only)" (needs Kong's real PC) and "SKIP (Windows only)" (on a Mac)
    skipped = sum(1 for line in out.splitlines() if line.startswith("SKIP ("))
    print(f"{'OK  ' if ok else 'FAIL'} {name}: {passed} of {count} passed ({took:.0f} s)"
          + (f", {skipped} skipped (PC / Windows only)" if skipped else ""), flush=True)
    why = []
    if not ok:
        in_trace = False
        hung = False
        for line in out.splitlines():
            # every FAIL line, and every traceback in full (where it happened, not only its last line)
            if line.startswith("Timeout ("):  # (2.13) it hung: where every thread was, to the end
                hung = True
                line = "FAIL the test hung. " + line
            if hung:
                print("     " + line)
                why.append(line.rstrip())
                continue
            if line.startswith("Traceback"):
                in_trace = True
            if in_trace or line.startswith("FAIL") or "Error" in line:
                print("     " + line)
                why.append(line.rstrip())
            if in_trace and line and not line.startswith((" ", "Traceback", "During handling", "The above")):
                in_trace = False  # (the "SomeError: ..." line ends it)
        if not why:
            why.append(f"exit code {proc.returncode}, no result line")
        if os.environ.get("GITHUB_ACTIONS"):
            # (2.13) also as a note on the run's page, which anyone can read without signing in. A hung test:
            # the test's own thread (the one that runs <module>), most recent call first, is what matters
            note = why
            if hung:
                blocks, cur = [], []
                for w in why[1:]:
                    if w.startswith(("Thread 0x", "Current thread")) and cur:
                        blocks.append(cur)
                        cur = []
                    cur.append(w.strip())
                blocks.append(cur)
                main_block = next((b for b in blocks if any("<module>" in w for w in b)), blocks[-1])
                note = [why[0]] + [w for w in main_block if "frozen runpy" not in w and "<string>" not in w]
            text = " | ".join(note[:14])[:2500].replace("%", "%25").replace("\r", "").replace("\n", " ")
            print(f"::error title={name} failed::{text}", flush=True)
    return ok, passed, count, skipped, why


def _pick(paths, argv):
    def arg(flag):
        if flag in argv and argv.index(flag) + 1 < len(argv):
            return [x.strip() for x in argv[argv.index(flag) + 1].split(",") if x.strip()]
        return []
    groups, tests = arg("--group"), arg("--test")
    if not groups and not tests or "all" in groups:
        return paths
    want = set()
    for g in groups:
        if g not in GROUPS:
            sys.exit(f"No group \"{g}\". Groups: {', '.join(GROUPS)}")
        want |= set(GROUPS[g])
    for t in tests:
        name = t if t.endswith(".py") else t + ".py"
        name = name if name.startswith("test_") else "test_" + name
        if not os.path.isfile(os.path.join(here, name)):
            sys.exit(f"No test file {name}")
        want.add(name)
    return [p for p in paths if os.path.basename(p) in want]


def write_summary(file, rows, began, coverage):
    lines = ["## Test results", "", "| Group | File | Result | Checks | Skipped (PC / Windows only) | Time |",
             "|---|---|---|---|---|---|"]
    for name, ok, passed, count, skipped, took, _why in rows:
        lines.append(f"| {GROUP_NAMES.get(group_of(name), 'Other')} | {name} | {'✅' if ok else '❌'} | "
                     f"{passed} of {count} | {skipped} | {took:.0f} s |")
    total_p, total = sum(r[2] for r in rows), sum(r[3] for r in rows)
    lines += ["", f"**{total_p} of {total} checks passed** in {time.time() - began:.0f} s, "
                  f"{sum(r[4] for r in rows)} checks skipped (PC only, or Windows only on a Mac)."]
    if coverage is not None:
        lines.append(f"Code covered by these tests: **{coverage}**")
    bad = [r for r in rows if not r[1]]
    if bad:
        lines += ["", "### Why they failed"]
        for name, *_rest, why in bad:
            lines.append(f"- **{name}**")
            lines += [f"  - `{w[:200]}`" for w in why[:60]]
    with open(file, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def coverage_total():
    try:
        # (combined into a file of its own: the group's files in covdata stay for the summary job)
        env = dict(os.environ, COVERAGE_FILE=os.path.join(COVDATA, "group.coverage"))
        subprocess.run([sys.executable, "-m", "coverage", "combine", "--keep", COVDATA], capture_output=True,
                       timeout=300, env=env)
        out = subprocess.run([sys.executable, "-m", "coverage", "report"], capture_output=True, text=True,
                             timeout=300, env=env).stdout
        m = re.search(r"TOTAL.*?(\d+%)", out)
        return m.group(1) if m else None
    except Exception:
        return None


def main():
    argv = sys.argv[1:]
    if "--list" in argv:
        for g, files in GROUPS.items():
            print(f"{g}: {GROUP_NAMES[g]}\n    " + ", ".join(files))
        return
    began = time.time()
    coverage = "--coverage" in argv
    paths = _pick(sorted(glob.glob(os.path.join(here, "test_*.py"))), argv)
    one_by_one = "--one-by-one" in argv
    side_by_side = [] if one_by_one else [p for p in paths if os.path.basename(p) not in WINDOW_TESTS]
    alone = [p for p in paths if p not in side_by_side]
    failed, rows = [], []

    def done(result):
        # (2.13) each test is told the moment it ends (on GitHub also as a note on the run's page), so a run that
        # is stopped part way still shows which tests finished and which one hung
        path, proc, took = result
        ok, passed, count, skipped, why = report(path, proc, took)
        rows.append((os.path.basename(path), ok, passed, count, skipped, took, why))
        if not ok:
            failed.append(os.path.basename(path))
    if side_by_side:
        from concurrent.futures import as_completed
        with ThreadPoolExecutor(AT_ONCE) as pool:
            for fut in as_completed([pool.submit(run, p, coverage) for p in side_by_side]):
                done(fut.result())
    for p in alone:
        print(f"     ... {os.path.basename(p)}", flush=True)
        done(run(p, coverage))
    rows.sort(key=lambda r: r[0])
    total_pass, total = sum(r[2] for r in rows), sum(r[3] for r in rows)
    print(f"\n{total_pass} of {total} checks passed in {time.time() - began:.0f} s"
          + (f"; failed: {', '.join(failed)}" if failed else ""))
    cov = coverage_total() if coverage else None
    if cov:
        print(f"Code covered: {cov}")
    if "--summary" in argv and argv.index("--summary") + 1 < len(argv):
        write_summary(argv[argv.index("--summary") + 1], rows, began, cov)
    sys.exit(1 if failed or total == 0 else 0)


if __name__ == "__main__":
    main()
