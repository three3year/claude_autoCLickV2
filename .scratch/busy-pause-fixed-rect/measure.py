"""票 08 前置: 量每張範本在參考影片上出現的位置 (影片座標), 給 fixed_rects.py 用.

    .venv/Scripts/python.exe .scratch/busy-pause-fixed-rect/measure.py [--lang cn|tw]

- 影片: common.LANGS 的參考影片 (簡中 demo6/demo5/demo1、繁中 demo2/demo3), 每 STRIDE 幀一張。
- 每張範本: 半解析度灰階相關找最高點 (≥0.80) → 全解析度在附近 ±8px 精修, ≥0.90 才記。
  一張影格每張範本只記最高的那一處 (列名這種同畫面多個的, 跨影格自然會量到整段範圍)。
- 另外解析實跑日誌 (autoclick.log) 每次執行的 find.target picked 框: 依執行開頭校準的
  基準距離分版本 (簡中 1650、繁中 1868), 螢幕座標扣掉偏移換回影片座標。
結果寫 results/positions_<lang>.json: {範本: {"video": [[影片, 幀, x, y, w, h, 分數]...],
"log": [[時間, x, y, w, h]...]}}。純 opencv, 不經引擎 (只是量位置; 判定用真引擎的驗證在
fixed_rects.py)。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import common

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import flowfile  # noqa: E402

STRIDE = 3
COARSE, FINE = 0.80, 0.90
LOG = os.path.join(common.APP, "dist", "AutoClick", "autoclick.log")
BASELINE = {1650.0: "cn", 1868.0: "tw"}
SKIP = {"標題列圖示", "標題列關閉鈕"}     # 校準對: 不在搜尋範圍裡找


def templates(lang):
    r = flowfile.read(common.flow_path(common.LANGS[lang]["flow"]))
    out = {}
    for n, blob in r["images"].items():
        if n in SKIP or n.startswith("採購_"):
            continue
        out[n] = cv2.cvtColor(common.decode(blob), cv2.COLOR_BGR2GRAY)
    return out


def scan_video(video, tmpls, found):
    cap = cv2.VideoCapture(os.path.join(common.VIDEO_DIR, video + ".mp4"))
    small = {n: cv2.resize(t, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
             for n, t in tmpls.items()}
    n = 0
    while True:
        if not cap.grab():
            break
        if n % STRIDE == 0:
            ok, img = cap.retrieve()
            if not ok:
                break
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gs = cv2.resize(g, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
            for name, ts in small.items():
                if ts.shape[0] < 6 or ts.shape[1] < 6:
                    ts = None
                t = tmpls[name]
                if ts is not None:
                    res = cv2.matchTemplate(gs, ts, cv2.TM_CCOEFF_NORMED)
                    _, mx, _, loc = cv2.minMaxLoc(res)
                    if mx < COARSE:
                        continue
                    x0, y0 = loc[0] * 2 - 8, loc[1] * 2 - 8
                else:
                    x0 = y0 = None
                if x0 is None:
                    win, (ox, oy) = g, (0, 0)
                else:
                    x0, y0 = max(0, x0), max(0, y0)
                    win = g[y0:y0 + t.shape[0] + 16, x0:x0 + t.shape[1] + 16]
                    ox, oy = x0, y0
                    if win.shape[0] < t.shape[0] or win.shape[1] < t.shape[1]:
                        continue
                res = cv2.matchTemplate(win, t, cv2.TM_CCOEFF_NORMED)
                _, mx, _, loc = cv2.minMaxLoc(res)
                if mx >= FINE:
                    found.setdefault(name, {"video": [], "log": []})["video"].append(
                        [video, n, loc[0] + ox, loc[1] + oy, t.shape[1], t.shape[0],
                         round(float(mx), 3)])
        n += 1
    cap.release()
    return n


LINE = re.compile(r"^(\S+ \S+) find\.target .*?template=(\S+) result=found .*?"
                  r"picked=\((\d+),(\d+),(\d+),(\d+)\)")
CAL = re.compile(r"^\S+ \S+ calibrate result=ok .*?baseline=([\d.]+)")


def scan_log(lang, names, found):
    """實跑日誌裡這個版本的 picked 框 (換回影片座標)."""
    if not os.path.isfile(LOG):
        return 0
    ox, oy = common.LANGS[lang]["offset"]
    cur, k = None, 0
    with open(LOG, encoding="utf-8", errors="replace") as f:
        for line in f:
            # 每次執行開頭校準一次: 校準成功的基準距離決定版本; 校準失敗或 app 重開＝不認得
            if " calibrate " in line or " engine.load.start" in line:
                m = CAL.match(line)
                cur = BASELINE.get(float(m.group(1))) if m else None
                continue
            if cur != lang:
                continue
            m = LINE.match(line)
            if not m or m.group(2) not in names:
                continue
            x, y, w, h = (int(v) for v in m.group(3, 4, 5, 6))
            found.setdefault(m.group(2), {"video": [], "log": []})["log"].append(
                [m.group(1), x - ox, y - oy, w, h])
            k += 1
    return k


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=sorted(common.LANGS), action="append")
    args = ap.parse_args(argv)
    os.makedirs(common.RESULTS, exist_ok=True)
    for lang in args.lang or sorted(common.LANGS):
        tmpls = templates(lang)
        found = {}
        for video in common.LANGS[lang]["videos"]:
            total = scan_video(video, tmpls, found)
            print(f"[{lang}] {video}: {total} 幀", flush=True)
        k = scan_log(lang, set(tmpls), found)
        print(f"[{lang}] 日誌: {k} 筆")
        for n in sorted(tmpls):
            rec = found.get(n, {"video": [], "log": []})
            print(f"  {n}: 影格 {len(rec['video'])}、日誌 {len(rec['log'])}")
        with open(os.path.join(common.RESULTS, f"positions_{lang}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(found, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
