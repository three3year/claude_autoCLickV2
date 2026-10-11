"""組裝: `轉換計畫` → 一份新的流程資料夾 (flow.yaml＋templates/＋交付報告/).

順序 (任何一步拒絕都在寫檔之前, 輸出位置一個檔案都不會多)::

    讀計畫 → 裁範本 → 量校準對 (新流程必填) → 原點推算＋固定矩形＋自我驗證 →
    忙碌檢查兩向報告 → 寫進暫存資料夾 → 檢查指令 → 改名成正式名稱

影片尺度就是`流程尺度` (ADR 0009): 偏移與範本圖原樣進流程; `基準距離`在影片影格上量,
第一張的中心就是`座標基準點` (ADR 0012)——固定矩形與範本拍攝位置相對它。不寫搜尋範圍
(＝全螢幕)。流程一律經 app 的 `flowfile.write_flow` 寫出 (格式只由一個地方決定)。
輸出在 `<輸出位置>/<流程名>/` (預設 %USERPROFILE%/AutoClick/), 撞名加序號, 絕不覆蓋。
"""
from __future__ import annotations

import os
import shutil
import tempfile

import cv2

import calibration
import flowfile
from automation import flowcheck, flowfmt
from subject_detection.library import load_default_config

from . import measure as measure_mod
from . import plan as plan_mod
from . import report as report_mod
from . import verify as verify_mod
from . import video as video_mod
from .errors import ToolError


def measure_one(pair, frame, checker, frames):
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
    """量`校準對` (與`備用校準對`): 回傳 (流程的校準資料, `座標基準點`, 備用對量不到的原因).

    主對量不到＝報錯 (新流程不產跑不動的流程); 備用對量不到只是不帶備用對。
    與執行開頭的校準同一套量測 (`calibration.measure`, 全範圍查詢)。
    """
    pair, frame = c["pair"], c["frame"]
    m, problem = measure_one(pair, frame, checker, frames)
    if m is None:
        raise ToolError(f"校準對量不到（{problem}）：換一幀兩張都在的（calibration.frame）"
                        "或換兩張遊戲畫面內的固定圖")
    cal = calibration.make(pair, round(m.distance, 1))
    fb_problem = None
    if c.get("fallback"):
        fb, fb_problem = measure_one(c["fallback"]["pair"], frame, checker, frames)
        if fb is not None:
            cal[calibration.FALLBACK_KEY] = calibration.make_fallback(
                c["fallback"]["pair"], round(fb.distance, 1),
                calibration.fallback_offset(m.anchor, fb.anchor, 1.0))
    return cal, m.anchor, fb_problem


def crop(frames, name, t, size):
    x, y, w, h = t["box"]
    if x < 0 or y < 0 or x + w > size[0] or y + h > size[1]:
        raise ToolError(f"範本「{name}」的裁切框 {t['box']} 超出影片畫面"
                        f"（{size[0]}×{size[1]}）")
    return frames[t["frame"]][y:y + h, x:x + w].copy()


def png(img):
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ToolError("範本圖無法編碼成 PNG")
    return buf.tobytes()


DEFAULT_OUT = os.path.join(os.path.expanduser("~"), "AutoClick")


def scroll_confirm(steps, measured):
    """同一份報告段落 (頂層區段) 有拖曳、找圖又沒宣告捲動軸的 → [(索引, 文字)]."""
    secs = report_mod.sections(steps)
    out = []
    for sec in secs:
        if not any(steps[i]["type"] == "drag" for i in range(sec.start, sec.end)):
            continue
        for i in range(sec.start, sec.end):
            if i in measured.no_scroll:
                out.append((i, measure_mod.label(steps[i])))
    return out


def retake_of(checked, used):
    return {n: r["reasons"] for n, r in checked.items() if r["reasons"] and n in used}


def assemble(plan, engine=None, out_dir=None):
    """組裝一份流程資料夾; 回傳結果 dict (flow_path＝流程資料夾、report_path＝交付報告/、…).

    plan: 計畫 dict 或計畫 JSON 檔路徑。engine: 已建好的引擎 (測試共用; None＝自行建構)。
    out_dir: 輸出位置 (None＝計畫的 out, 再沒有就是 DEFAULT_OUT)。
    """
    p = plan_mod.load(plan, plan_mod.ASSEMBLE)
    out = os.path.abspath(out_dir or p.out or DEFAULT_OUT)
    info = video_mod.probe(p.video)
    size = (info["width"], info["height"])
    frames = video_mod.read_frames(
        p.video, measure_mod.frames_needed(p, [p.calibration["frame"]]))
    crops = {n: crop(frames, n, t, size) for n, t in p.templates.items()}

    engine = engine or verify_mod.make_engine()
    checker = verify_mod.Checker(engine, crops, p.templates, p.steps, frames,
                                 load_default_config(), None, size,
                                 extra_targets=[p.busy] if p.busy else [])
    cal, anchor, fb_problem = _measure_pair(p.calibration, checker, frames)
    checker.anchor = anchor
    measured = measure_mod.measure(p, checker, p.busy)
    measure_mod.busy_two_way(p, measured, checker, info)
    checked = checker.finish()
    steps = measured.steps

    flow = flowfile.new_flow()
    flow.update(steps=steps, calibration=cal, busy=measured.busy)
    errs = flowcheck.flow_errors(flow)
    if errs:
        raise ToolError("轉換計畫有誤（app 執行前會擋下）：" + "；".join(errs))
    used = flowfile.template_refs(flow)
    # 範本拍攝位置＝取材框的中心, 相對`座標基準點` (編輯器推算預設原點的備援)
    flow["template_pos"] = {
        n: list(flowfmt.from_screen((t["box"][0] + t["box"][2] // 2,
                                     t["box"][1] + t["box"][3] // 2), anchor))
        for n, t in p.templates.items() if n in used}
    images = {n: png(img) for n, img in crops.items()}

    folder = _free_dir(out, p.name)
    result = {
        "flow_path": folder, "report_path": os.path.join(folder, report_mod.DIR),
        "video": p.video, "video_size": list(size), "warnings": [],
        "calibration": cal, "calibration_frame": p.calibration["frame"],
        "fallback": calibration.fallback_pair(cal), "fallback_problem": fb_problem,
        "busy": measured.busy,
        "steps": len(steps), "templates": len(used),
        "verification": "coarse" if engine.coarse_only else "full",
        "retake": retake_of(checked, used),
        "unused": sorted(n for n in images if n not in used),
        "scroll_confirm": scroll_confirm(steps, measured),
        "busy_unseen": measured.busy_unseen,
        "busy_unchecked": measured.busy_unchecked,
        "found": {n: r["boxes"] for n, r in checked.items()},
        "frames": {i: measure_mod.step_frame(p, i) for i in range(len(steps))},
        "step_list": steps,
    }
    files = report_mod.render(result, p, steps)
    result["report_files"] = sorted(files)
    _place(folder, flow, images, files)
    return result


def _free_dir(out, name):
    """輸出位置底下未被占用的流程資料夾 (name、name_2、name_3…; 不覆蓋既有的)."""
    stem, n = name, 1
    while os.path.exists(os.path.join(out, stem)):
        n += 1
        stem = f"{name}_{n}"
    return os.path.join(out, stem)


def _place(folder, flow, images, files):
    """先在同一個輸出位置的暫存資料夾寫完整 (flow.yaml、templates/、交付報告/) 並跑檢查指令,
    再改名成正式名稱; 任何一步失敗都不留半成品."""
    from flow_check import check

    parent = os.path.dirname(folder)
    os.makedirs(parent, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".vtf_", dir=parent)
    try:
        flowfile.write_flow(tmp, flow, images)
        report_mod.write(tmp, files)
        res = check(tmp)
        if not res.ok or res.missing:
            raise ToolError("工具錯誤：組裝出來的流程沒通過檢查指令："
                            + "；".join(res.errors + [f"缺圖 {n}" for n in res.missing]))
        os.rename(tmp, folder)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
