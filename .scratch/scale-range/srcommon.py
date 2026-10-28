from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
APP = os.path.join(ROOT, "app")
for p in (APP, os.path.join(APP, "tests"), os.path.join(ROOT, "tools"),
          os.path.join(HERE, "..", "busy-pause-fixed-rect"),
          os.path.join(HERE, "..", "fixed-rect-sweep")):
    if p not in sys.path:
        sys.path.insert(0, p)

import common as bp  # noqa: E402
from shared import SeqFrames  # noqa: E402

PROFILE = bp.PROFILE
FLOWS = bp.FLOWS
RESULTS = os.path.join(HERE, "results")
TEMPLATES = os.path.join(HERE, "templates")
CONVERTED = os.path.join(HERE, "converted", "arknights", "flows")
BACKUP = os.path.join(bp.APP, "dist", "profiles-backup-2026-10-09-scale-range")

SCALES = (0.85, 0.883, 1.0, 1.13, 1.15)
PICK_SCALES = (0.85, 1.0, 1.15)

LANGS = {
    "cn": {"morning": "早_簡中", "evening": "晚_簡中", "offset": (95, 57),
           "menu": ("demo4", 0), "size": (1696, 912),
           "videos": ["demo6", "demo5", "demo1", "demo4", "add3"]},
    "tw": {"morning": "早_繁中", "evening": "晚_繁中", "offset": (0, 0),
           "menu": ("demo3", 0), "size": (1920, 1024),
           "videos": ["demo2", "demo3", "add4"]},
}
FLOW_LANG = {"早_簡中": "cn", "晚_簡中": "cn", "早_繁中": "tw", "晚_繁中": "tw"}
OLD_FLOWS = ["日常_影片", "arknightMorning_cn", "arknightNight", "arknightNight_cn", "舊_早_簡中"]

_frames = SeqFrames()


def frame(video, n):
    return _frames.get(video, n)


def prefetch(keys):
    _frames.prefetch(list(keys))


def read_flow(name, flows=FLOWS):
    import flowfile
    return flowfile.read(bp.flow_path(name, flows))


def offset(lang):
    return LANGS[lang]["offset"]


def to_screen(lang, xy):
    ox, oy = offset(lang)
    return (int(xy[0]) + ox, int(xy[1]) + oy)


def box_to_screen(lang, box):
    x, y = to_screen(lang, box[:2])
    return (x, y, int(box[2]), int(box[3]))


def place(lang, region):
    return bp.frame_region(lang, region)


def crop(img, box):
    x, y, w, h = [int(v) for v in box]
    return img[y:y + h, x:x + w].copy()


def scaled(canvas, org, anchor, s, origin=None):
    from automation import pickcheck
    img = pickcheck.resize_image(canvas, s) if s != 1.0 else canvas

    def pt(p):
        return None if p is None else (round(p[0] * s), round(p[1] * s))
    return img, pt(org), pt(anchor), pt(origin)


def find_scaled(hub, tgt, canvas, org, anchor, s, origin=None):
    from automation import findtarget
    img, org2, anchor2, origin2 = scaled(canvas, org, anchor, s, origin)
    f = findtarget.find(tgt, hub, img, org2, origin=origin2, scale=s, anchor=anchor2)
    return f


def unscale_box(box, s):
    return tuple(round(v / s) for v in box)


def center(box):
    return (box[0] + box[2] // 2, box[1] + box[3] // 2)


def dump(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, default=str)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def known_frames(lang):
    have = {}
    p = os.path.join(HERE, "..", "fixed-rect-sweep", "results", f"positions_{lang}.json")
    d = load(p)
    for name, rows in d.get("video", {}).items():
        have.setdefault(name, []).extend((r[0], r[1]) for r in rows)
    if "busy" in d:
        have.setdefault("忙碌指示", []).extend((r[0], r[1]) for r in d["busy"])
    p = os.path.join(HERE, "..", "busy-pause-fixed-rect", "results", f"positions_{lang}.json")
    for name, v in load(p).items():
        rows = v.get("video") if isinstance(v, dict) else None
        if rows:
            have.setdefault(name, []).extend((r[0], r[1]) for r in rows)
    p = os.path.join(HERE, "..", "quick-place-clue-check", "results", f"frames_{lang}.json")
    d = load(p)
    for r in d.get("rows", []):
        if r.get("found"):
            have.setdefault(r["template"], []).append((d["video"], r["frame"]))
    return {n: sorted(set(v)) for n, v in have.items()}
