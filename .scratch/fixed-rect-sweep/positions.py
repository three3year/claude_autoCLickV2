"""量位置: 晚班每張範本在晚班示範影片上出現的位置, 與忙碌指示在各參考影片上的位置.

    .venv/Scripts/python.exe .scratch/fixed-rect-sweep/positions.py [--lang cn|tw]

- 晚班範本: 晚班流程 (shared.LANGS 的 evening) 裡的範本, 在晚班影片 (簡中 demo4、繁中 demo3)
  每 STRIDE 幀找一次 (opencv 灰階相關, 同 busy-pause-fixed-rect/measure.py 的 scan_video:
  半解析度 ≥0.80 → 全解析度精修 ≥0.90 才記, 一張影格每張範本只記最高那一處)。
- 忙碌指示: 在晚班影片＋早班參考影片 (bp.LANGS 的 videos) 每 STRIDE 幀, 畫面下半部全解析度
  灰階相關 ≥FINE 才記 (簡中的字只有 21px 高, 上面那套的半解析度粗找會整個漏掉)。
- 換班清單顯示區的上緣 (列名框的上下, 規格「換班列名的框」): 列名出現的影格裡, 清單每一列右邊
  ⇄ 藍條那一欄 (BAR_X) 最上面的藍色像素——捲動時列被切掉的那條線。取至少 MIN_CLIP 張影格
  都量到的最小值 (別的畫面上偶爾也有藍色, 只出現一兩格的不算)。下緣＝畫面底 (清單一直延伸到底)。
結果寫 results/positions_<lang>.json: {"video": {範本: [[影片, 幀, x, y, w, h, 分數]...]},
"busy": [...], "list_clip": {"top", "bottom", "frames"}}——影片座標。只是量位置 (挑驗證影格用); 判定用真引擎, 在 sweep.py。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import shared
from shared import bp

import cv2  # noqa: E402

import flowfile  # noqa: E402
import measure as bpm  # noqa: E402  (busy-pause-fixed-rect 的量法)

SKIP = bpm.SKIP       # 校準對: 不在搜尋範圍裡找
BAR_X = {"cn": 1622, "tw": 1832}   # ⇄ 藍條那一欄 (影片 x)
MIN_CLIP = 3
STRIDE = bpm.STRIDE
FINE = bpm.FINE


def gray_templates(name, only=None):
    r = flowfile.read(bp.flow_path(name))
    return {n: cv2.cvtColor(bp.decode(blob), cv2.COLOR_BGR2GRAY)
            for n, blob in r["images"].items()
            if n not in SKIP and (only is None or n in only)}


def scan_busy(video, tmpl):
    """忙碌指示在這支影片下半部的位置 (全解析度): [[影片, 幀, x, y, w, h, 分數]]."""
    cap = cv2.VideoCapture(os.path.join(bp.VIDEO_DIR, video + ".mp4"))
    out, n = [], 0
    while cap.grab():
        if n % STRIDE == 0:
            ok, img = cap.retrieve()
            if not ok:
                break
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            top = g.shape[0] // 2
            res = cv2.matchTemplate(g[top:], tmpl, cv2.TM_CCOEFF_NORMED)
            _, mx, _, loc = cv2.minMaxLoc(res)
            if mx >= FINE:
                out.append([video, n, loc[0], loc[1] + top, tmpl.shape[1], tmpl.shape[0],
                            round(float(mx), 3)])
        n += 1
    cap.release()
    return out


def list_clip(lang, found):
    """清單顯示區上下緣 (影片 y): 列名出現的影格上 ⇄ 藍條那一欄的藍色範圍."""
    from collections import Counter
    import numpy as np
    video = shared.LANGS[lang]["video"]
    frames = sorted({v[1] for n, rec in found.items() if n.endswith("1列") for v in rec["video"]})
    fr = shared.SeqFrames()
    fr.prefetch([(video, n) for n in frames])
    tops, height = Counter(), None
    x = BAR_X[lang]
    for n in frames:
        img = fr.get(video, n).astype(int)
        height = img.shape[0]
        c = img[:, x - 3:x + 3].mean(axis=1)            # B, G, R
        ys = np.where((c[:, 0] > 90) & (c[:, 0] > c[:, 2] + 50))[0]
        ys = ys[ys > 100]                                # 標題列、頂端按鈕列不算
        if len(ys):
            tops[int(ys.min())] += 1
    fr.close()
    seen = [y for y, k in tops.items() if k >= MIN_CLIP]
    if not seen:
        raise SystemExit(f"[{lang}] 量不到清單切線: 沒有一個 y 在 {MIN_CLIP} 張以上影格出現 ({sorted(tops.items())[:8]})")
    top = min(seen)
    return {"top": top, "bottom": height, "frames": len(frames),
            "tops": sorted(tops.items())[:8]}


def run(lang):
    cfg = shared.LANGS[lang]
    found = {}
    total = bpm.scan_video(cfg["video"], gray_templates(cfg["evening"]), found)
    print(f"[{lang}] {cfg['video']}: {total} 幀", flush=True)
    busy = []
    tmpl = gray_templates(cfg["evening"], {shared.BUSY})[shared.BUSY]
    for video in [cfg["video"]] + [v for v in bp.LANGS[lang]["videos"] if v != cfg["video"]]:
        busy += scan_busy(video, tmpl)
        print(f"[{lang}] 忙碌指示 {video}: 累計 {len(busy)} 幀", flush=True)
    clip = list_clip(lang, found)
    print(f"[{lang}] 清單顯示區 (影片 y): {clip}", flush=True)
    out = {"video": {n: rec["video"] for n, rec in found.items()}, "busy": busy,
           "list_clip": clip}
    for n in sorted(out["video"]):
        print(f"  {n}: {len(out['video'][n])} 幀")
    os.makedirs(shared.RESULTS, exist_ok=True)
    with open(os.path.join(shared.RESULTS, f"positions_{lang}.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=sorted(shared.LANGS), action="append")
    args = ap.parse_args(argv)
    for lang in args.lang or sorted(shared.LANGS):
        run(lang)
    return 0


if __name__ == "__main__":
    sys.exit(main())
