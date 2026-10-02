"""讀`示範影片`: 一律循序解碼 (壓縮影片的隨機跳幀不保證落在同一幀).

影格編號＝從 0 起算、循序解碼的第幾幀; 時間＝編號 ÷ fps。掃描與組裝都走
這一條解碼路徑, 兩邊說的「第 N 幀」才是同一張畫面。
"""
from __future__ import annotations

import os

import cv2

from .errors import ToolError


def _open(path):
    path = str(path)
    if not os.path.isfile(path):
        raise ToolError(f"找不到示範影片：{path}")
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        raise ToolError(f"讀不到示範影片（無法解碼）：{path}")
    return cap


def probe(path):
    """影片基本資訊 {width, height, fps, frames}; 讀不到或沒有任何影格丟 ToolError.

    frames 是容器宣告的幀數 (可能不準, 只供參考); 實際以循序解碼為準。
    """
    cap = _open(path)
    try:
        ok, frame = cap.read()
        if not ok or frame is None:
            raise ToolError(f"示範影片沒有任何可解碼的影格：{path}")
        h, w = frame.shape[:2]
        fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    finally:
        cap.release()
    return {"width": w, "height": h, "fps": fps, "frames": n}


def iter_frames(path):
    """循序產出 (影格編號, BGR 影像)."""
    cap = _open(path)
    try:
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                return
            yield i, frame
            i += 1
    finally:
        cap.release()


def read_frames(path, indices):
    """取出指定編號的影格 {編號: 影像}; 超出影片長度丟 ToolError."""
    want = sorted({int(i) for i in indices})
    if not want:
        return {}
    if want[0] < 0:
        raise ToolError(f"影格編號不能是負數：{want[0]}")
    out = {}
    last = want[-1]
    count = 0
    for i, frame in iter_frames(path):
        count = i + 1
        if i in want:
            out[i] = frame
        if i >= last:
            break
    missing = [i for i in want if i not in out]
    if missing:
        raise ToolError(f"影格 {', '.join(map(str, missing))} 超出影片長度"
                        f"（影片共 {count} 幀，編號 0–{count - 1}）")
    return out
