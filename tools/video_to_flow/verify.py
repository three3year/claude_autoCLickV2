"""自我驗證: 用引擎公開 API 對影格重跑每張範本, 沒過的標`待重拍`.

範本經 `make_library` + `Engine.register` 一張一張登錄 (一張登錄失敗不拖垮
其他張), 再以 `Engine.query` 在指定影格上查詢; 搜尋區域就是整張影格
(影片＝遊戲畫面＝搜尋範圍)。

每張範本要通過的檢查:

- 取材幀與 present 幀: 找得到, 且中心落在預期位置附近 (預設＝裁切框中心,
  present 可寫明新位置)
- 引用它的每個找圖步驟的 frame (該點的那一幀): 找得到——引擎在這一幀實際
  找到的框就是原點推算用的框
- absent 幀 (還沒出現的那幾幀): 找不到
- 計畫標示 clean: false (找不到乾淨影格): 不論結果都待重拍
"""
from __future__ import annotations

import os
import tempfile

import cv2

from .errors import ToolError


def position_tolerance(box):
    """中心容許偏離的距離 (px): 壓縮失真讓框抖個 1-2px 是常態."""
    return max(6.0, 0.25 * min(box[2], box[3]))


def _center(box):
    x, y, w, h = box
    return x + w // 2, y + h // 2


def make_engine():
    """建構引擎 (載深度驗證模型; 載不起來會降級 coarse-only 並發警告)."""
    import warnings

    from subject_detection.engine import Engine
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Engine()


def frames_needed(templates, steps):
    """驗證要讀的影格編號."""
    need = set()
    for t in templates.values():
        need.add(t["frame"])
        need.update(p["frame"] for p in t["present"])
        need.update(t["absent"])
    for s in steps:
        if s["type"] == "find_click":
            need.add(step_frame(s, templates))
    return need


def step_frame(step, templates):
    """找圖步驟看的是哪一幀 (預設＝範本的取材幀)."""
    return step.get("frame", templates[step["template"]]["frame"])


def verify(engine, crops, templates, steps, frames, config):
    """驗證全部範本; 回傳 {範本名: {"reasons": [...], "boxes": {幀: 框或 None}}}.

    reasons 為空＝通過。boxes 是引擎在各檢查幀實際找到的框 (影片像素)。
    """
    from subject_detection import make_library

    results = {n: {"reasons": [], "boxes": {}} for n in templates}
    with tempfile.TemporaryDirectory(prefix="vtf_verify_") as tmp:
        paths = {}
        for i, (name, img) in enumerate(crops.items()):
            p = os.path.join(tmp, f"t{i:03d}.png")
            ok, buf = cv2.imencode(".png", img)
            if not ok:
                raise ToolError(f"範本「{name}」無法編碼成 PNG")
            buf.tofile(p)
            paths[name] = p
        lib = make_library(paths, config, os.path.join(tmp, "registered"))
        for name, t in templates.items():
            res = results[name]
            try:
                engine.register(lib, name)
            except Exception as e:  # 純色/無結構的框連登錄都過不了
                res["reasons"].append(f"引擎無法登錄這張範本（{e}）")
                continue

            def query(frame):
                if frame not in res["boxes"]:
                    r = engine.query(lib, name, frames[frame])
                    res["boxes"][frame] = tuple(int(v) for v in r.box) if r.found else None
                return res["boxes"][frame]

            checks = [(t["frame"], _center(t["box"]), "取材幀")]
            checks += [(p["frame"], tuple(p["at"]) if p["at"] else _center(t["box"]),
                        "出現幀") for p in t["present"]]
            tol = position_tolerance(t["box"])
            for frame, want, label in checks:
                got = query(frame)
                if got is None:
                    res["reasons"].append(f"{label}（第 {frame} 幀）找不到")
                    continue
                gx, gy = _center(got)
                if ((gx - want[0]) ** 2 + (gy - want[1]) ** 2) ** 0.5 > tol:
                    res["reasons"].append(
                        f"位置不符（第 {frame} 幀：預期中心 {want[0]},{want[1]}、"
                        f"找到 {gx},{gy}）")
            for no, s in enumerate(steps, 1):
                if s["type"] != "find_click" or s["template"] != name:
                    continue
                frame = step_frame(s, templates)
                if query(frame) is None:
                    res["reasons"].append(f"步驟 {no} 該點的那一幀（第 {frame} 幀）找不到")
            for frame in t["absent"]:
                if query(frame) is not None:
                    res["reasons"].append(f"出現前就匹配（第 {frame} 幀不該找得到）")
            if not t["clean"]:
                res["reasons"].append("找不到乾淨影格（計畫標示）")
    for res in results.values():
        res["reasons"] = list(dict.fromkeys(res["reasons"]))  # 去重、保序
    return results


RETAKE_ADVICE = {
    "找不到乾淨影格": "在遊戲裡停在這個畫面、游標移開後，用編輯器的範本面板重新拾取",
    "出現前就匹配": "範本框到了畫面上本來就有的東西；重新框只屬於這個按鈕的部分（文字、圖示）",
    "位置不符": "畫面上可能有長得一樣的東西；框大一點把周邊有辨識度的部分包進來",
    "找不到": "範本可能框到空白處或被游標/特效污染；換一幀或重新框按鈕本體",
    "引擎無法登錄": "範本沒有可辨識的結構（純色）；改框有文字或圖示的地方",
}


def advice(reasons):
    """依原因給重拍建議 (同一建議只說一次)."""
    out = []
    for why in reasons:
        for key, tip in RETAKE_ADVICE.items():   # 由具體到籠統, 取第一個符合的
            if key in why:
                if tip not in out:
                    out.append(tip)
                break
    return out or ["用編輯器的範本面板重新拾取這張範本"]
