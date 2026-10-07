"""票 06: 繁中忙碌指示重截 (見 issues/06-tw-busy-template.md).

    .venv/Scripts/python.exe .scratch/busy-pause-fixed-rect/tw_busy.py [--apply]

舊範本是從 demo3 第 852 幀附近裁的: 那幾幀忙碌字樣底下疊著另一段淡出中的提示字,
裁下來的圖是兩層字 (殘影), 實機上永遠比不到 (10/07 日誌 best 約 0.19)。
新範本從 demo2 (繁中、最大化 1920×1024) 好友訪問時的忙碌字樣裁: 底下是純暗帶,
裁法照簡中 (10/05): 只框字 (灰階 >120 的外框 +1px)。

驗證走 app 的真實偵測路徑 (arknights 門檻), 影格換成實機搜尋範圍的畫布 (common.frame_region),
執行流程層級的忙碌指示找圖目標 (限定範圍照流程裡的設定, 畫面倍率 1):
- 有忙碌的影格 (opencv 灰階相關 ≥0.9, 抽樣) 要找得到; demo3 那幾幀疊字的也列出。
- 沒有忙碌的影格 (相關 <0.3, demo2/demo3 每 25 幀抽一張) 要找不到。
- 淡入淡出中間 (0.3–0.9) 的影格不算。
結果寫 results/tw_busy.json。--apply: 換掉早_繁中的忙碌指示範本 (名稱、限定範圍不變),
先備份、讀回驗證、草稿同步。晚_繁中用的若是同一張舊圖, 只回報不改 (規格不含晚班)。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time

import common

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402

FLOW = "早_繁中"
EVENING = "晚_繁中"
SOURCE = ("demo2", 2000)
CROP = (1069, 944, 272, 25)          # x, y, w, h (影片 1:1 = 流程尺度)
VIDEOS = {"demo2": 3284, "demo3": 913}
POS_STRIDE, NEG_STRIDE = 10, 25


def cut(frames):
    x, y, w, h = CROP
    img = frames.get(*SOURCE)[y:y + h, x:x + w].copy()
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ys, xs = np.where(g > 120)
    # 裁切框＝字的外框 +1px (確認來源影格上沒裁到字)
    if xs.min() < 1 or ys.min() < 1 or xs.max() > w - 2 or ys.max() > h - 2:
        raise SystemExit("裁切框切到字了: 重量 CROP")
    return img


def label(frames, tmpl):
    """依 opencv 灰階相關把影格分成有忙碌 / 沒忙碌 (抽樣), 回傳 [(video, n, kind, corr)]."""
    t = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY)
    out = []
    for video, total in VIDEOS.items():
        pos = 0
        for n in range(total):
            if n % 5:          # 先每 5 幀看一次, 再各自抽樣
                continue
            img = frames.get(video, n)
            g = cv2.cvtColor(img[660:1024, 640:1920], cv2.COLOR_BGR2GRAY)
            corr = float(cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED).max())
            if corr >= 0.9:
                if pos % (POS_STRIDE // 5) == 0:
                    out.append((video, n, "busy", corr))
                pos += 1
            elif corr < 0.3 and n % NEG_STRIDE == 0:
                out.append((video, n, "idle", corr))
    # demo3 疊字那幾幀 (舊範本的來源; 字被別的提示字蓋住一半)
    out += [("demo3", n, "busy_overlap", None) for n in range(850, 859, 2)]
    return out


def evaluate(hub, busy, frames, samples, place):
    rows = []
    for video, n, kind, corr in samples:
        canvas, org = place(frames.get(video, n))
        t0 = time.perf_counter()
        f = findtarget.find(busy, hub, canvas, org, origin=None, scale=1.0)
        ms = (time.perf_counter() - t0) * 1000
        q = f.query
        rows.append({"video": video, "frame": n, "kind": kind,
                     "corr": None if corr is None else round(corr, 3),
                     "found": f.picked is not None,
                     "score": round(f.picked.score, 3) if f.picked else None,
                     "box": list(f.picked.box) if f.picked else None,
                     "best": None if q is None else round(q.score, 3),
                     "failed": f.failed, "ms": round(ms)})
    return rows


def summarize(rows, tag):
    by = {}
    for r in rows:
        by.setdefault(r["kind"], []).append(r)
    out = {}
    for kind, rs in by.items():
        hit = [r for r in rs if r["found"]]
        scores = [r["score"] for r in hit]
        bests = [r["best"] for r in rs if r["best"] is not None]
        out[kind] = {"n": len(rs), "found": len(hit),
                     "score_min": min(scores) if scores else None,
                     "score_max": max(scores) if scores else None,
                     "best_max": max(bests) if bests else None,
                     "ms_avg": round(sum(r["ms"] for r in rs) / len(rs))}
        print(f"  [{tag}] {kind}: {len(hit)}/{len(rs)} 找到"
              + (f"，分數 {out[kind]['score_min']}–{out[kind]['score_max']}" if scores else "")
              + f"，最高分 {out[kind]['best_max']}，平均 {out[kind]['ms_avg']} ms")
    return out


def original_image(name, flows):
    """換掉之前的舊範本: 已經 --apply 過時現在的存檔裡是新圖, 舊圖從票 06 的備份讀.

    改的不是正式流程目錄 (試跑), 或備份還沒做 (還沒套用過) 時回 None。
    """
    if os.path.normcase(os.path.abspath(flows)) != os.path.normcase(common.FLOWS):
        return None
    p = os.path.join(common.ticket_backup("06"), "arknights", "flows", FLOW + flowfile.EXT)
    if not os.path.isfile(p):
        return None
    return flowfile.read(p)["images"].get(name)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="驗證通過後寫回早_繁中")
    ap.add_argument("--flows", default=common.FLOWS)
    args = ap.parse_args(argv)

    path = common.flow_path(FLOW, args.flows)
    r = flowfile.read(path)
    busy = flowfile.busy_target(r["data"])
    name = busy["template"]
    old = original_image(name, args.flows) or r["images"][name]
    ev = flowfile.read(common.flow_path(EVENING, args.flows))
    ev_busy = flowfile.busy_target(ev["data"])
    ev_same_old = ev_busy is not None and ev["images"].get(ev_busy["template"]) == old

    frames = common.Frames()
    tmp = tempfile.mkdtemp(prefix="tw_busy_")
    try:
        new = cut(frames)
        common.write_img(os.path.join(common.RESULTS, "tw_busy_new.png"), new)
        print("標註影格…", flush=True)
        samples = label(frames, new)
        print("載入引擎…", flush=True)
        imgs = {"新": common.encode(new), "舊": old}
        hub = common.make_hub(imgs, list(imgs), tmp)
        res = {}
        place = common.frame_region("tw", r["data"]["scanRegion"])
        for tag in ("新", "舊"):
            tgt = dict(busy, template=tag)
            rows = evaluate(hub, tgt, frames, samples, place)
            res[tag] = {"summary": summarize(rows, tag), "rows": rows}
    finally:
        frames.close()
        shutil.rmtree(tmp, ignore_errors=True)

    s = res["新"]["summary"]
    ok = (s["busy"]["found"] == s["busy"]["n"] and s["idle"]["found"] == 0)
    out = {"source": {"video": SOURCE[0], "frame": SOURCE[1], "crop": CROP},
           "limit": busy.get("limit"), "ok": ok,
           "evening_same_old": ev_same_old, "results": res}
    os.makedirs(common.RESULTS, exist_ok=True)
    with open(os.path.join(common.RESULTS, "tw_busy.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("新範本" + ("通過" if ok else "**不通過**"))
    print(f"晚_繁中 用的是同一張舊範本: {'是' if ev_same_old else '否'}")
    if not ok:
        return 1
    if not args.apply:
        return 0

    common.preflight(args.flows, common.ticket_backup("06"))
    blob = common.encode(new)
    if r["images"][name] == blob:
        print("早_繁中 已是新範本, 不動")
        return 0
    r["images"][name] = blob
    x, y, w, h = CROP
    ox, oy = common.LANGS["tw"]["offset"]   # pos 是螢幕座標
    r["pos"][name] = [x + ox + w // 2, y + oy + h // 2]
    back = common.write_flow(path, r["data"], r["images"], r["pos"])
    if back["images"][name] != blob or back["data"]["steps"] != r["data"]["steps"]:
        raise SystemExit("讀回的內容與寫入的不同")
    print("已換掉 早_繁中 的忙碌指示範本")
    if common.sync_draft(path, os.path.dirname(args.flows)):
        print("    草稿與工作區已同步")
    return 0


if __name__ == "__main__":
    sys.exit(main())
