import os
import sys
import tempfile
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk  # noqa: E402

import applog  # noqa: E402
import app as app_mod  # noqa: E402
import enginehub  # noqa: E402

applog.set_path(os.path.join(tempfile.gettempdir(), "slim_probe.log"))
import apppaths  # noqa: E402

_local = tempfile.mkdtemp(prefix="slim_probe_")
apppaths.state_dir = lambda: os.path.join(_local, "state")
apppaths.flows_root = lambda: os.path.join(_local, "flows")
enginehub._default_engine_factory = lambda: SimpleNamespace(
    coarse_only=False,
    register=lambda profile, name: None,
    query=lambda profile, name, screen: None,
)

from automation import win  # noqa: E402

win.set_dpi_aware()
root = tk.Tk()
a = app_mod.App(root)
root.update()
heavy = [m for m in ("cv2", "mss", "torch", "numpy") if m in sys.modules]
print("HEAVY=" + (",".join(heavy) or "none"), flush=True)
deadline = time.monotonic() + 5
while a.hub.state == enginehub.LOADING and time.monotonic() < deadline:
    root.update()
    time.sleep(0.02)
root.destroy()
