"""掃描: 每個客戶端兩份流程現在的範本, 在該客戶端每支示範影片上每 STRIDE 幀配對一次 (順序讀)。

    .venv/Scripts/python.exe .scratch/benchmark-rebuild/scan.py [--lang cn|tw] [--stride 8]

半解析度粗找, ≥ COARSE 的峰回全解析度精修。結果 tmp/scan_<lang>.json:
  templates: {key: {"names": [[流程, 名]...], "size": [w, h]}}
  videos: {影片: {"frames": [幀...], "size": [w, h],
                  "max": {key: [每幀粗找最高分×100]},
                  "peaks": {key: {幀: [[分數, x, y]...]}}}}   (全解析度, 分數 ≥ KEEP)
低優先權、少執行緒 (使用者可能在玩遊戲)。
"""
from __future__ import annotations

import argparse
import ctypes
import os
import sys
import time
from multiprocessing import Pool

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bcommon as bc  # noqa: E402

COARSE = 0.5   # 半解析度粗找的門檻
KEEP = 0.6     # 全解析度精修後留下的門檻


def low_priority():
    if os.name == "nt":
        BELOW_NORMAL = 0x4000
        ctypes.windll.kernel32.SetPriorityClass(
            ctypes.windll.kernel32.GetCurrentProcess(), BELOW_NORMAL)
    cv2.setNumThreads(2)


def scan_video(args):
    lang, video, stride = args
    low_priority()
    tpls = {k: v[0] for k, v in bc.lang_templates(lang).items()}
    small = {k: cv2.resize(bc.gray(t), None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
             for k, t in tpls.items()}
    gt = {k: bc.gray(t) for k, t in tpls.items()}
    frames, size = [], None
    mx = {k: [] for k in tpls}
    pk = {k: {} for k in tpls}
    t0 = time.time()
    for n, img in bc.iter_frames(video, stride):
        g = bc.gray(img)
        size = [g.shape[1], g.shape[0]]
        gs = cv2.resize(g, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        frames.append(n)
        for k, ts in small.items():
            r = cv2.matchTemplate(gs, ts, cv2.TM_CCOEFF_NORMED)
            r[~np.isfinite(r)] = 0
            th, tw = ts.shape
            best = float(r.max())
            mx[k].append(int(round(best * 100)))
            if best < COARSE:
                continue
            found = []
            for _ in range(10):
                _, v, _, (x, y) = cv2.minMaxLoc(r)
                if v < COARSE:
                    break
                r[max(0, y - th // 2):y + th // 2 + 1, max(0, x - tw // 2):x + tw // 2 + 1] = -1
                # 全解析度精修: 粗找位置 ×2 附近 ±4px
                T = gt[k]
                H, W = T.shape
                x0, y0 = max(0, 2 * x - 4), max(0, 2 * y - 4)
                win = g[y0:y0 + H + 8, x0:x0 + W + 8]
                if win.shape[0] < H or win.shape[1] < W:
                    continue
                rr = cv2.matchTemplate(win, T, cv2.TM_CCOEFF_NORMED)
                rr[~np.isfinite(rr)] = 0
                _, s, _, (dx, dy) = cv2.minMaxLoc(rr)
                if s >= KEEP:
                    found.append([round(float(s), 4), x0 + dx, y0 + dy])
            if found:
                pk[k][n] = sorted(found, reverse=True)
    print(f"{video}: {len(frames)} 幀, {time.time() - t0:.0f}s", flush=True)
    return video, {"frames": frames, "size": size, "max": mx, "peaks": pk}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=["cn", "tw"])
    ap.add_argument("--stride", type=int, default=8)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    low_priority()
    for lang in ([a.lang] if a.lang else ["cn", "tw"]):
        tpls = bc.lang_templates(lang)
        jobs = [(lang, v, a.stride) for v in bc.VIDEOS[lang]]
        with Pool(a.workers) as pool:
            videos = dict(pool.map(scan_video, jobs))
        bc.dump(os.path.join(bc.TMP, f"scan_{lang}.json"), {
            "stride": a.stride,
            "templates": {k: {"names": v[1], "size": [v[0].shape[1], v[0].shape[0]]}
                          for k, v in tpls.items()},
            "videos": videos})
        print(f"{lang}: {len(tpls)} 張範本, 寫 tmp/scan_{lang}.json", flush=True)


if __name__ == "__main__":
    main()
