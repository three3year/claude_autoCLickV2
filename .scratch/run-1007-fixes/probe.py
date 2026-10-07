"""真引擎在影片影格上跑找圖目標 (照 credit-store-switch/frames.py 的載入方式).

    .venv/Scripts/python.exe .scratch/run-1007-fixes/probe.py --flow 早_繁中 --video add2 \
        --frames 98-110 --target '{"template":"忙碌指示","limit":{"kind":"grid","cells":[8,9]}}' \
        [--tmpl 新範本名=路徑.png ...]

範本先取流程存檔裡的, --tmpl 另外加/覆蓋。影片與流程同尺度, 倍率 1。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
APP = os.path.join(ROOT, "app")
PROFILE = os.path.join(APP, "dist", "AutoClick", "profiles", "arknights")
FLOWS = os.path.join(PROFILE, "flows")
VIDEOS = r"C:\Users\three\我的電腦\oCam Video"
for p in (APP, os.path.join(ROOT, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import cv2  # noqa: E402

import applog  # noqa: E402
import enginehub  # noqa: E402
import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402


def frames(video, spec):
    want = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        want.update(range(int(a), int(b or a) + 1))
    cap = cv2.VideoCapture(os.path.join(VIDEOS, video + ".mp4"))
    i = 0
    while want:
        ok, img = cap.read()
        if not ok:
            break
        if i in want:
            want.discard(i)
            yield i, img
        i += 1


def make_hub(images, tmp):
    ws = flowfile.Workspace(tmp)
    for n, b in images.items():
        ws.add(n, b)
    applog.set_path(os.path.join(tmp, "autoclick.log"))
    hub = enginehub.EngineHub()
    hub.load(ws.root, config_dir=PROFILE)
    if not hub.ready or hub.coarse_only:
        raise SystemExit(f"引擎載入失敗: {hub.error!r}")
    hub.preload(list(images))
    return hub


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--flow", required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--target", action="append", required=True)
    ap.add_argument("--tmpl", action="append", default=[])
    args = ap.parse_args(argv)

    images = dict(flowfile.read(os.path.join(FLOWS, args.flow + flowfile.EXT))["images"])
    for t in args.tmpl:
        name, _, path = t.partition("=")
        with open(path, "rb") as f:
            images[name] = f.read()
    tgts = [json.loads(t) for t in args.target]
    with tempfile.TemporaryDirectory() as tmp:
        hub = make_hub(images, tmp)
        for i, img in frames(args.video, args.frames):
            for t in tgts:
                f = findtarget.find(t, hub, img, (0, 0), origin=None, scale=1.0)
                q = f.query
                best = getattr(q, "best", None) if q is not None else None
                print(f"f{i:03d} {t['template']}{'〔比色〕' if t.get('colorCheck') else ''}: "
                      + (f"picked={findtarget.fmt_box(f.picked.box)} "
                         f"score={f.picked.score:.3f} color={f.picked.color}"
                         if f.picked else f"none failed={f.failed} best={best}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
