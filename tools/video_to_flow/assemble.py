"""組裝: `轉換計畫` → 一份一般的流程資料夾 (flow.yaml＋templates/＋交付報告.md).

順序 (任何一步拒絕都在寫檔之前, 輸出位置一個檔案都不會多)::

    讀計畫 → 裁範本 → 組步驟 → 量校準對 → 寫流程資料夾 (含交付報告)

影片尺度就是`流程尺度` (ADR 0009): 偏移與範本圖原樣進流程; `校準對`由計畫指名、
`基準距離`在影片影格上量, 第一張的中心就是`座標基準點` (ADR 0012)——範本拍攝位置
相對它 (沒有校準對＝不記拍攝位置)。不寫搜尋範圍 (＝全螢幕, ADR 0014 決策 5)。

流程一律經 app 的 `flowfile.write_flow` 寫出 (格式只由一個地方決定)。輸出在
`<輸出位置>/<流程名>/` (預設 %USERPROFILE%/AutoClick/), 撞名加序號 (名稱_2…),
絕不覆蓋; 先在同一個位置的暫存資料夾寫完整再改名, 失敗不留半成品。
"""
from __future__ import annotations

import os
import shutil
import tempfile

import cv2

import calibration
import flowfile
from automation import findtarget, flowdefaults, flowfmt
from automation.runner import confirm_next_connected, origin_source
from subject_detection.library import load_default_config

from . import keys
from . import origin as origin_mod
from . import plan as plan_mod
from . import report as report_mod
from . import verify as verify_mod
from . import video as video_mod
from .errors import ToolError


def _measure_one(pair, frame, checker, frames):
    """在第 frame 幀上量一對: 回傳 (Measurement 或 None, 量不到的原因或 None)."""
    unregistered = [n for n in pair if n not in checker.registered]
    if unregistered:
        return None, f"引擎無法登錄 {'、'.join(unregistered)}"
    m = calibration.measure(checker.detector.query, frames[frame], pair)
    if m.missing:
        return None, f"第 {frame} 幀上找不到 {'、'.join(m.missing)}"
    if m.too_close:
        return None, f"第 {frame} 幀上兩張圖重疊，不能當比例尺"
    return m, None


def _measure_pair(c, checker, frames):
    """在影片影格上量`校準對` (與`備用校準對`): 回傳 (流程的校準資料或 None, `座標基準點`
    (影片像素) 或 None, 主對量不到的原因或 None, 備用對量不到的原因或 None).

    與執行開頭的校準同一套量測 (`calibration.measure`, 全範圍查詢); 影片尺度
    就是流程尺度, 所以量到的距離直接就是`基準距離`、第一張的中心就是基準點。
    備用對在同一幀上量: 它自己的距離當基準距離, (基準點 − 備用第一張中心) 當偏移
    (ADR 0013); 備用對量不到只是少了備用, 主對照寫。
    """
    if c is None:
        return None, None, None, None
    pair, frame = c["pair"], c["frame"]
    m, problem = _measure_one(pair, frame, checker, frames)
    if m is None:
        return None, None, problem, None
    cal = calibration.make(pair, round(m.distance, 1))
    fb_problem = None
    if c.get("fallback"):
        fb, fb_problem = _measure_one(c["fallback"]["pair"], frame, checker, frames)
        if fb is not None:
            cal[calibration.FALLBACK_KEY] = calibration.make_fallback(
                c["fallback"]["pair"], round(fb.distance, 1),
                calibration.fallback_offset(m.anchor, fb.anchor, 1.0))
    return cal, m.anchor, None, fb_problem


def _complete(steps):
    """補齊步驟 (就地): 計畫沒寫的`生效確認`照工具的規則推, 其餘照 app 的「沒寫＝」表.

    - 找圖點擊: 下一步是找圖 → 點到下一步的圖出現 (next), 否則 (含最後一步、下一步是
      區段標記) → 目標圖消失 (gone)
    - 拖曳的原點來自找圖: `原點的圖離開` (gone)——捲動被吃掉時重拖, 不在後面靜靜點錯列
      (ADR 0008); 原點不是找圖時不設
    """
    for i, s in enumerate(steps):
        t = s["type"]
        if t == "find_click" and "confirm" not in s:
            s["confirm"] = "next" if confirm_next_connected(steps, i) else "gone"
        elif t == "drag" and "confirm" not in s and origin_source(steps, i) == "find":
            s["confirm"] = "gone"
        steps[i] = flowdefaults.complete(s)
    return steps


def _crop(frames, name, t, info):
    x, y, w, h = t["box"]
    if x < 0 or y < 0 or x + w > info["width"] or y + h > info["height"]:
        raise ToolError(f"範本「{name}」的裁切框 {t['box']} 超出影片畫面"
                        f"（{info['width']}×{info['height']}）")
    return frames[t["frame"]][y:y + h, x:x + w].copy()


def _png(img):
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ToolError("範本圖無法編碼成 PNG")
    return buf.tobytes()


DEFAULT_OUT = os.path.join(os.path.expanduser("~"), "AutoClick")
REPORT_NAME = "交付報告.md"


def assemble(plan, engine=None, out_dir=None):
    """組裝一份流程資料夾; 回傳結果 dict (flow_path＝流程資料夾、report_path、…).

    plan: 計畫 dict 或計畫 JSON 檔路徑。engine: 已建好的引擎 (測試共用;
    None＝自行建構)。out_dir: 輸出位置 (流程資料夾建在它底下; None＝計畫的 out,
    再沒有就是 DEFAULT_OUT)。
    """
    p = plan_mod.load(plan)
    out = os.path.abspath(out_dir or p["out"] or DEFAULT_OUT)
    info = video_mod.probe(p["video"])

    need = verify_mod.frames_needed(p["templates"], p["steps"])
    if p["calibration"]:
        need.add(p["calibration"]["frame"])
    frames = video_mod.read_frames(p["video"], need)
    crops = {n: _crop(frames, n, t, info) for n, t in p["templates"].items()}

    engine = engine or verify_mod.make_engine()
    # 範本層級的檢查先跑; 找圖步驟照它的找圖目標挑, 要知道那一步之前的原點,
    # 所以逐步驗證在原點推算時進行 (挑中的框＝原點推算用的框)
    checker = verify_mod.Checker(engine, crops, p["templates"], p["steps"],
                                 frames, load_default_config(),
                                 extra_targets=[p["busy"]] if p["busy"] else [])
    steps = _complete(origin_mod.derive(p["steps"], p["templates"],
                                             checker.locate))
    checked = checker.finish()
    cal, anchor, cal_problem, fb_problem = _measure_pair(p["calibration"], checker,
                                                         frames)
    found = {n: r["boxes"] for n, r in checked.items()}
    images = {n: _png(img) for n, img in crops.items()}
    # 範本元資料 pos＝拍攝位置 (取材框的中心, 相對影片上量到的`座標基準點`, 倍率 1;
    # 編輯器推算預設原點的備援); 沒有校準對就沒有基準點, 不記
    pos = {}
    if anchor is not None:
        for n, t in p["templates"].items():
            x, y, w, h = t["box"]
            pos[n] = list(flowfmt.from_screen((x + w // 2, y + h // 2), anchor))
    flow = flowfile.new_flow()
    flow.update(steps=steps, calibration=cal, template_pos=pos)
    if p["busy"]:
        b = p["busy"]
        flow["busy"] = findtarget.make_target(
            b["template"], pick=keys.flow_pick(b.get("pick")),
            color=b.get("colorCheck", False))
    # 驗證沒過的範本 (`待重拍`) 只列在交付報告; 範本名與檔名不帶標記
    retake = {name: r["reasons"] for name, r in checked.items() if r["reasons"]}

    folder = _free_dir(out, p["name"])
    used = flowfile.template_refs(flow)
    result = {
        "flow_path": folder, "report_path": os.path.join(folder, REPORT_NAME),
        "video": p["video"],
        "video_size": [info["width"], info["height"]],
        "warnings": [],
        "calibration": flow["calibration"],
        "calibration_frame": (p["calibration"] or {}).get("frame"),
        "calibration_problem": cal_problem,
        "fallback": calibration.fallback_pair(flow["calibration"]),
        "fallback_problem": fb_problem,
        "busy": flow["busy"],
        "steps": len(steps),
        "templates": len(used),
        "verification": "coarse" if engine.coarse_only else "full",
        "retake": {n: why for n, why in retake.items() if n in used},
        "unused": sorted(n for n in images if n not in used),
        "found": found,
        "step_list": steps,
    }
    _place(folder, flow, images, report_mod.render(result, p))
    return result


def _free_dir(out, name):
    """輸出位置底下未被占用的流程資料夾 (name、name_2、name_3…; 不覆蓋既有的)."""
    stem, n = name, 1
    while os.path.exists(os.path.join(out, stem)):
        n += 1
        stem = f"{name}_{n}"
    return os.path.join(out, stem)


def _place(folder, flow, images, report_text):
    """流程資料夾先在同一個輸出位置的暫存資料夾寫完整 (flow.yaml、templates/、交付報告),
    再改名成正式名稱; 任何一步失敗都不留半成品."""
    parent = os.path.dirname(folder)
    os.makedirs(parent, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".vtf_", dir=parent)
    try:
        flowfile.write_flow(tmp, flow, images)
        with open(os.path.join(tmp, REPORT_NAME), "w", encoding="utf-8") as f:
            f.write(report_text)
        os.rename(tmp, folder)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
