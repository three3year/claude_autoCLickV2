"""組裝: `轉換計畫` + 目標 profile → 一份一般的流程存檔 + `交付報告`.

順序 (任何一步拒絕都在寫檔之前, profile 一個檔案都不會多)::

    讀計畫 → 讀 profile 草稿的`搜尋範圍` → 裁範本 → 組步驟 → 量校準對 → 寫存檔 → 寫報告

影片尺度就是`流程尺度` (ADR 0009): 偏移與範本圖原樣進存檔, 不讀 profile 的
任何校準資料; `校準對`由計畫指名、`基準距離`在影片影格上量, 第一張的中心就是
`座標基準點` (ADR 0012)——範本拍攝位置相對它 (沒有校準對＝不記拍攝位置)。

存檔一律經 app 既有的 `flowfile.write` 寫出 (格式只由一個地方決定), 檔名走
既有的「不撞名」規則落在 profile 的流程目錄, 絕不覆蓋。
"""
from __future__ import annotations

import os
import shutil
import tempfile

import cv2

import calibration
import flowfile
from automation import findtarget, flowfmt
from subject_detection.library import load_config

from . import defaults
from . import origin as origin_mod
from . import plan as plan_mod
from . import report as report_mod
from . import verify as verify_mod
from . import video as video_mod
from .errors import ToolError


def _profile_region(profile):
    """目標 profile 草稿的`搜尋範圍` [x, y, w, h]; 沒有就拒絕."""
    if not os.path.isfile(os.path.join(profile, "config.yaml")):
        raise ToolError(f"不是 profile 目錄（缺 config.yaml）：{profile}")
    draft = flowfile.read_draft(profile) or {}
    region = draft.get("scanRegion")
    if not region or len(region) != 4 or region[2] <= 0 or region[3] <= 0:
        raise ToolError("目標 profile 的步驟草稿沒有搜尋範圍：請先在 app 裡把"
                        "「搜尋範圍」框在遊戲畫面上（草稿會自動存下來），再重新組裝")
    return [int(v) for v in region], draft


def _size_warnings(region, info):
    """影片與搜尋範圍的尺寸提醒 (不拒絕).

    `示範影片`與實際畫面同尺度 (影片像素＝螢幕像素), 偏移不依搜尋範圍換算;
    搜尋範圍只決定執行時在哪裡找圖, 通常連視窗邊框一起框、比影片略大。
    影片反而比搜尋範圍大＝錄到了範圍外的東西, 或錄影時縮放了畫面——
    前者照樣能跑, 後者範本與偏移都會差一個倍數, 交給使用者判斷。
    """
    if info["width"] <= region[2] and info["height"] <= region[3]:
        return []
    return [f"影片比搜尋範圍大（影片 {info['width']}×{info['height']}、"
            f"搜尋範圍 {region[2]}×{region[3]}）：確認錄影是以實際畫面尺度（不縮放）"
            "錄的，且執行時遊戲畫面落在搜尋範圍內；錄影若有縮放，範本與偏移都會對不上"]


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


def assemble(plan, engine=None, report_path=None):
    """組裝一份流程存檔; 回傳結果 dict (flow_path、report_path、…).

    plan: 計畫 dict 或計畫 JSON 檔路徑。engine: 已建好的引擎 (測試共用;
    None＝自行建構)。report_path: 交付報告位置 (None＝計畫的 reportPath,
    再沒有就與存檔同名並排)。
    """
    p = plan_mod.load(plan)
    profile = p["profile"]
    region, draft = _profile_region(profile)
    info = video_mod.probe(p["video"])
    warnings = _size_warnings(region, info)

    need = verify_mod.frames_needed(p["templates"], p["steps"])
    if p["calibration"]:
        need.add(p["calibration"]["frame"])
    frames = video_mod.read_frames(p["video"], need)
    crops = {n: _crop(frames, n, t, info) for n, t in p["templates"].items()}

    engine = engine or verify_mod.make_engine()
    # 範本層級的檢查先跑; 找圖步驟照它的找圖目標挑, 要知道那一步之前的原點,
    # 所以逐步驗證在原點推算時進行 (挑中的框＝原點推算用的框)
    checker = verify_mod.Checker(engine, crops, p["templates"], p["steps"],
                                 frames, load_config(profile),
                                 extra_targets=[p["busy"]] if p["busy"] else [])
    steps = defaults.apply(origin_mod.derive(p["steps"], p["templates"],
                                             checker.locate))
    checked = checker.finish()
    cal, anchor, cal_problem, fb_problem = _measure_pair(p["calibration"], checker,
                                                         frames)
    found = {n: r["boxes"] for n, r in checked.items()}
    # 驗證沒過的範本: 名稱加`待重拍`前綴、步驟引用 (含確認圖) 同步改寫
    images = {n: _png(img) for n, img in crops.items()}
    # 範本元資料 pos＝拍攝位置 (取材框的中心, 相對影片上量到的`座標基準點`, 倍率 1;
    # 編輯器推算預設原點的備援); 沒有校準對就沒有基準點, 不記
    pos = {}
    if anchor is not None:
        for n, t in p["templates"].items():
            x, y, w, h = t["box"]
            pos[n] = list(flowfmt.from_screen((x + w // 2, y + h // 2), anchor))
    data = {"steps": steps, "runMode": "count", "runCount": 1,
            "scanRegion": region, "avoidHover": bool(draft.get("avoidHover", False)),
            flowfmt.COORD_SPACE: flowfmt.ANCHOR}
    if cal:
        data[calibration.FLOW_KEY] = cal
    if p["retry_interval_ms"] is not None:
        data[flowfile.RETRY_KEY] = p["retry_interval_ms"]
    if p["busy"]:
        b = p["busy"]
        data[flowfile.BUSY_KEY] = findtarget.make_target(
            b["template"], limit=b.get("limit"), pick=b.get("pick"),
            color=b.get("colorCheck", False))
    retake = {}
    for name, r in checked.items():
        if r["reasons"]:
            new = plan_mod.RETAKE_PREFIX + name
            flowfile.rename_flow_refs(data, name, new)   # 步驟與校準對一起改
            images[new] = images.pop(name)
            if name in pos:
                pos[new] = pos.pop(name)
            retake[new] = r["reasons"]

    flows = flowfile.flows_dir(profile)
    os.makedirs(flows, exist_ok=True)
    rp = report_path or p["report_path"]
    stem = _free_stem(flows, p["name"], beside=rp is None)
    flow_path = os.path.join(flows, stem + flowfile.EXT)
    rp = str(rp or os.path.join(flows, stem + ".md"))

    used = flowfile.flow_refs(data)
    result = {
        "flow_path": flow_path, "report_path": rp,
        "video": p["video"], "profile": profile,
        "video_size": [info["width"], info["height"]],
        "region": region, "warnings": warnings,
        "calibration": data.get(calibration.FLOW_KEY),
        "calibration_frame": (p["calibration"] or {}).get("frame"),
        "calibration_problem": cal_problem,
        "fallback": calibration.fallback_pair(data.get(calibration.FLOW_KEY)),
        "fallback_problem": fb_problem,
        "busy": flowfile.busy_target(data),
        "retry_interval_ms": flowfile.retry_interval_ms(data),
        "steps": len(steps),
        "templates": len(used),
        "verification": "coarse" if engine.coarse_only else "full",
        "retake": {n: why for n, why in retake.items() if n in used},
        "unused": sorted(n for n in images if n not in used),
        "found": found,
        "step_list": steps,
    }
    _place(flow_path, rp, data, images, pos, report_mod.render(result, p))
    return result


def _free_stem(flows, name, beside):
    """流程目錄裡未被占用的檔名主幹 (不覆蓋既有存檔).

    與 `flowfile.free_path` 同一條加序號規則 (name、name_2、name_3…); 報告與
    存檔並排時兩個檔名要一起空著, 報告才保證與存檔同名。
    """
    stem, n = name, 1
    while (os.path.exists(os.path.join(flows, stem + flowfile.EXT))
           or (beside and os.path.exists(os.path.join(flows, stem + ".md")))):
        n += 1
        stem = f"{name}_{n}"
    return stem


def _place(flow_path, report_path, data, images, pos, report_text):
    """存檔與報告先在暫存目錄寫完整, 再一起落地; 任何一步失敗都不留半成品."""
    with tempfile.TemporaryDirectory(prefix="vtf_out_") as tmp:
        staged = os.path.join(tmp, "flow" + flowfile.EXT)
        flowfile.write(staged, data, images, pos)
        staged_report = os.path.join(tmp, "report.md")
        with open(staged_report, "w", encoding="utf-8") as f:
            f.write(report_text)
        os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
        shutil.move(staged, flow_path)
        try:
            shutil.move(staged_report, report_path)
        except BaseException:
            os.remove(flow_path)
            raise
