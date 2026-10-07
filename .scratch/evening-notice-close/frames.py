"""接縫一: 真引擎＋影片影格, 驗證晚班新的第 1 步 (見 spec.md「接縫一」).

    .venv/Scripts/python.exe .scratch/evening-notice-close/frames.py [--flows 目錄] [--lang cn|tw]

用 app 的真實偵測路徑 (enginehub, arknights profile 的門檻); 影格貼到實機搜尋範圍大小的畫布上
(同 busy-pause-fixed-rect 票 08 的 fixed_rects.py), 找圖目標照存檔裡的設定 (含固定矩形) 找一次。
- 正例: 有公告的影格 (notice.LANGS 的 positive) 上要找得到, 挑到的框整個在固定矩形裡,
  中心離影片上的位置 (換成螢幕座標) 在容許值內。demo1 (低位元率) 照實列出、不算數。
- 反例: 晚班示範影片每 STRIDE 幀一張, 晚班「找基建入口」那一步 (新的第 2 步) 的找圖目標
  找得到的＝主畫面影格; 這些影格上公告 X 都要找不到。主畫面影格至少要有 MIN_HOME 張。
結果寫 results/frames_<lang>.json; 任一不符時結束碼 1。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time

import notice
from notice import bp

import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402
from video_to_flow import verify as vtf_verify  # noqa: E402

STRIDE = 4
MIN_HOME = 4


def _inside(box, lim):
    if lim is None:
        return True
    return (lim[0] <= box[0] and box[0] + box[2] <= lim[0] + lim[2]
            and lim[1] <= box[1] and box[1] + box[3] <= lim[1] + lim[3])


def _find(tgt, hub, canvas, org):
    t0 = time.perf_counter()
    f = findtarget.find(tgt, hub, canvas, org, origin=None, scale=1.0)
    return f, round((time.perf_counter() - t0) * 1000)


def _best(f):
    return None if f.query is None else round(float(f.query.score), 3)


def positive(lang, hub, tgt, frames, place, items):
    ox, oy = bp.LANGS[lang]["offset"]
    rows = []
    for video, n, (x, y, w, h) in items:
        canvas, org = place(frames.get(video, n))
        f, ms = _find(tgt, hub, canvas, org)
        want = (x + ox + w // 2, y + oy + h // 2)
        p = f.picked
        d = None if p is None else round(((p.center[0] - want[0]) ** 2
                                          + (p.center[1] - want[1]) ** 2) ** 0.5, 1)
        tol = vtf_verify.position_tolerance((0, 0, w, h))
        rows.append({"video": video, "frame": n, "found": p is not None,
                     "picked": None if p is None else list(p.box),
                     "score": None if p is None else round(float(p.score), 3),
                     "limit": None if f.limit is None else list(f.limit),
                     "inside": p is not None and _inside(p.box, f.limit),
                     "want_center": list(want), "dist": d, "tol": tol, "ms": ms,
                     "ok": p is not None and _inside(p.box, f.limit) and d <= tol})
    return rows


def negative(lang, hub, tgt, base_tgt, frames, place, video):
    import cv2
    cap = cv2.VideoCapture(os.path.join(bp.VIDEO_DIR, video + ".mp4"))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    rows = []
    for n in range(0, total, STRIDE):
        canvas, org = place(frames.get(video, n))
        fb, _ = _find(base_tgt, hub, canvas, org)
        if fb.picked is None:
            continue
        f, ms = _find(tgt, hub, canvas, org)
        rows.append({"video": video, "frame": n,
                     "base": list(fb.picked.box), "base_score": round(float(fb.picked.score), 3),
                     "found": f.picked is not None,
                     "picked": None if f.picked is None else list(f.picked.box),
                     "best": _best(f), "failed": f.failed, "ms": ms,
                     "ok": f.picked is None})
    return rows


def run_lang(lang, flows, frames):
    cfg = notice.LANGS[lang]
    r = flowfile.read(bp.flow_path(cfg["flow"], flows))
    steps = r["data"]["steps"]
    if not notice.is_notice_step(steps[0], lang):
        raise SystemExit(f"{cfg['flow']}: 第 1 步不是關公告那步 (先跑 build.py --apply)")
    tgt, base_tgt = findtarget.target(steps[0]), findtarget.target(steps[1])
    names = [tgt["template"], base_tgt["template"]]
    place = bp.frame_region(lang, r["data"]["scanRegion"])
    tmp = tempfile.mkdtemp(prefix="notice_frames_")
    try:
        hub = bp.make_hub(r["images"], names, tmp)
        pos = positive(lang, hub, tgt, frames, place, cfg["positive"])
        low = positive(lang, hub, tgt, frames, place, cfg["low_bitrate"])
        neg = negative(lang, hub, tgt, base_tgt, frames, place, cfg["evening_video"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ok = all(x["ok"] for x in pos) and all(x["ok"] for x in neg) and len(neg) >= MIN_HOME
    return {"flow": cfg["flow"], "target": tgt, "base_target": base_tgt, "stride": STRIDE,
            "positive": pos, "low_bitrate": low, "home": neg, "ok": ok}


def summary(rep):
    pos, neg, low = rep["positive"], rep["home"], rep["low_bitrate"]
    sc = [x["score"] for x in pos if x["score"] is not None]
    best = [x["best"] for x in neg if x["best"] is not None]
    lines = [f"[{rep['flow']}] 有公告 {sum(x['ok'] for x in pos)}/{len(pos)} 找到且在框內"
             + (f"（{min(sc):.3f}–{max(sc):.3f}）" if sc else ""),
             f"[{rep['flow']}] 主畫面 {sum(x['ok'] for x in neg)}/{len(neg)} 找不到"
             + (f"（最高相似度 {max(best):.3f}）" if best else "")
             + f"；影格 {', '.join(str(x['frame']) for x in neg)}"]
    if low:
        lines.append(f"[{rep['flow']}] demo1 低位元率（不算數）找到 {sum(x['found'] for x in low)}/{len(low)}")
    for x in pos + neg:
        if not x["ok"]:
            lines.append(f"  不符: {x}")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--flows", default=bp.FLOWS)
    ap.add_argument("--lang", choices=sorted(notice.LANGS), action="append")
    args = ap.parse_args(argv)
    frames = bp.Frames()
    bad = []
    os.makedirs(notice.RESULTS, exist_ok=True)
    try:
        for lang in args.lang or list(notice.LANGS):
            rep = run_lang(lang, args.flows, frames)
            with open(os.path.join(notice.RESULTS, f"frames_{lang}.json"), "w",
                      encoding="utf-8") as f:
                json.dump(rep, f, ensure_ascii=False, indent=1)
            print("\n".join(summary(rep)), flush=True)
            if not rep["ok"]:
                bad.append(lang)
    finally:
        frames.close()
    print("通過" if not bad else f"**不通過**: {'、'.join(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
