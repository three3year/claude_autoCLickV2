"""票 09 逐案探針: 基建BASE 重截候選、好友列表不比色的唯一性、解鎖線索/快速置入的他者顏色分數.

    .venv/Scripts/python .scratch/scale-range/probe.py
"""
from __future__ import annotations

import os
import shutil
import tempfile

import srcommon as sr
from srcommon import bp

from automation import findtarget, pickcheck  # noqa: E402

CASES = []


def run_tw():
    conv = sr.load(os.path.join(sr.RESULTS, "convert_tw.json"))
    anchor = tuple(conv["早_繁中"]["pair"]["new_anchor"])
    r = sr.read_flow("早_繁中", sr.CONVERTED)
    region = r["data"]["scanRegion"]
    place = sr.place("tw", region)
    images = dict(r["images"])
    # 基建BASE 重截候選 (demo3 f0 最大化主畫面)
    new_base = sr.crop(sr.frame("demo3", 0), (1465, 813, 84, 94))
    images["基建BASE_新"] = bp.encode(new_base)
    d = os.path.join(sr.TEMPLATES, "tw")
    os.makedirs(d, exist_ok=True)
    bp.write_img(os.path.join(d, "基建BASE_新.png"), new_base)
    names = ["基建BASE", "基建BASE_新", "好友列表", "解鎖線索", "快速置入", "信用交易所"]
    tmp = tempfile.mkdtemp(prefix="sr_probe_")
    try:
        hub = bp.make_hub({n: images[n] for n in names}, names, tmp)

        def probe(label, tgt, video, fn, scales=sr.SCALES):
            canvas, org = place(sr.frame(video, fn))
            out = []
            for s in scales:
                f = sr.find_scaled(hub, tgt, canvas, org, anchor, s)
                e = f"×{s}:"
                if f.picked is not None:
                    e += f"{f.picked.score:.3f}@{sr.center(f.picked.box)}"
                    if f.picked.color is not None:
                        e += f" c{f.picked.color:.3f}"
                    e += f" n={len(f.matches)}"
                else:
                    e += f"✘{f.failed}/{f.query.score:.3f}" if f.query else "✘"
                if f.rejected:
                    e += " rej[" + ",".join(f"{m.color:.3f}" for m in f.rejected) + "]"
                out.append(e)
            print(f"  {label} {video} f{fn}: " + " | ".join(out))

        print("== 基建BASE 現有 vs 重截 (固定矩形照流程第 8 步)")
        step8 = findtarget.target(r["data"]["steps"][7])
        for tn in ("基建BASE", "基建BASE_新"):
            tgt = dict(step8, template=tn)
            for v, fn in (("demo3", 0), ("demo2", 39), ("demo2", 276), ("demo2", 1647)):
                probe(tn, tgt, v, fn)
        print("== 拾取檢查 基建BASE_新 (demo3 f0)")
        canvas, org = place(sr.frame("demo3", 0))
        for w in pickcheck.check(hub, canvas, org, {"template": "基建BASE_新"}, anchor, 1.0,
                                 kinds=(pickcheck.SCALE, pickcheck.UNIQUE)):
            print("   ", w)
        print("== 好友列表: 有比色 vs 不比色 (demo2 f1818, f1863, f1800)")
        s122 = findtarget.target(r["data"]["steps"][121])
        for color in (True, False):
            tgt = dict(s122)
            tgt.pop("colorCheck", None)
            if color:
                tgt["colorCheck"] = True
            for fn in (1800, 1818, 1863):
                probe(f"好友列表 color={color}", tgt, "demo2", fn)
        print("== 信用交易所: 有比色 vs 不比色 (demo2 f2727, f2700)")
        s130 = findtarget.target(r["data"]["steps"][129])
        for color in (True, False):
            tgt = dict(s130)
            tgt.pop("colorCheck", None)
            if color:
                tgt["colorCheck"] = True
            for fn in (2700, 2727, 2760):
                probe(f"信用交易所 color={color}", tgt, "demo2", fn)
        print("== 解鎖線索 他者 (add4 f10 灰鎖 0/7) 與本尊 (demo2 已知幀)")
        s76 = findtarget.target(r["data"]["steps"][75])
        have = sr.known_frames("tw")
        for v, fn in [("add4", 10), ("add4", 240)] + have.get("解鎖線索", [])[:2]:
            probe("解鎖線索", s76, v, fn)
        print("== 快速置入 本尊 (add4 面板開著) 與可能的他者")
        s69 = findtarget.target(r["data"]["steps"][68])
        for v, fn in [("add4", 60), ("add4", 100), ("add3", 40)] + have.get("快速置入", [])[:2]:
            probe("快速置入", s69, v, fn)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run_tw()
