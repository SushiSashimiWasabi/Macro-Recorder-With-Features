"""(2.13) Runs one test file and watches for a hang: python _hang_watch.py SECONDS test.py source_dir

If the test is still running after SECONDS, it prints which window callbacks ran most (a window kept busy by
the same callbacks over and over shows up here), then where every thread is (faulthandler), and ends."""
import collections
import faulthandler
import os
import runpy
import sys
import threading

seconds = int(sys.argv[1])
sys.argv = sys.argv[2:]
counts = collections.Counter()

try:
    import tkinter

    real_call = tkinter.CallWrapper.__call__

    def counted(self, *args):
        f = self.func
        if getattr(f, "__qualname__", "").endswith("<locals>.callit"):  # (after / after_idle: the function it calls)
            inner = [c.cell_contents for c in (f.__closure__ or ()) if callable(getattr(c, "cell_contents", None))]
            f = next((g for g in inner if not isinstance(g, tkinter.Misc)), f)
        code = getattr(f, "__code__", None)
        where = f"{os.path.basename(code.co_filename)}:{code.co_firstlineno}" if code else ""
        counts[f"{getattr(f, '__qualname__', type(f).__name__)}@{where}"] += 1
        return real_call(self, *args)
    tkinter.CallWrapper.__call__ = counted
except Exception:
    pass


def tell():
    top = "; ".join(f"{name} x{n}" for name, n in counts.most_common(10)) or "none"
    sys.stderr.write(f"\nCallbacks: {sum(counts.values())} in all, most: {top}\n")
    sys.stderr.flush()


timer = threading.Timer(max(1, seconds - 5), tell)
timer.daemon = True
timer.start()
faulthandler.dump_traceback_later(seconds, exit=True)
runpy.run_path(sys.argv[0], run_name="__main__")
