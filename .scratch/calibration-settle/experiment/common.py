import os, sys, glob, time, json
ROOT = r"C:\Users\three\我的電腦\AiProject\claude_autoClickV2"
sys.path.insert(0, os.path.join(ROOT, "app")); sys.path.insert(0, os.path.join(ROOT, "src"))
HERE = os.path.dirname(os.path.abspath(__file__))
import cv2, numpy as np
import applog, enginehub, flowfile, calibration
from automation import findtarget, flowfmt
applog.set_path(os.path.join(HERE, "replay.log"))

def frame(i):
    return cv2.imread(os.path.join(HERE, "frames", f"f{i:04d}.png"))

def load(flow_name):
    folder = os.path.join(ROOT, "flows", flow_name)
    f = flowfile.read_flow(folder)
    tdir = os.path.join(folder, "templates")
    imgs = {os.path.splitext(os.path.basename(p))[0]: p for p in glob.glob(os.path.join(tdir, "*.png"))}
    from subject_detection.library import load_default_config
    cfg = load_default_config(); cfg.update(f.get("engine") or {})
    hub = enginehub.EngineHub(); hub.load()
    assert hub.ready and not hub.coarse_only, hub.error
    reg = os.path.join(HERE, "reg_" + flow_name); os.makedirs(reg, exist_ok=True)
    hub.bind(imgs, cfg, reg)
    hub.preload(sorted(imgs))
    return f, hub, imgs

def targets(f):
    out, seen = [], set()
    def walk(steps):
        for i, s in enumerate(steps):
            for key, t in findtarget.step_targets(s):
                if key == findtarget.CONFIRM_TARGET and not findtarget.uses_confirm_target(s):
                    continue
                k = (t.get("template"), str(t.get("within")), str(t.get("pick")))
                if k in seen: continue
                seen.add(k); out.append((i + 1, key, t))
    walk(f["steps"])
    if f.get("busy"):
        out.append((0, "busy", f["busy"]))
    return out
