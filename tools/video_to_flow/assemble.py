"""組裝: `轉換計畫` + 目標 profile → 一份一般的流程存檔 + `交付報告`.

順序 (任何一步拒絕都在寫檔之前, profile 一個檔案都不會多)::

    讀計畫 → 讀 profile 草稿的`搜尋範圍` → 裁範本 → 組步驟 → 寫存檔 → 寫報告

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
from automation import flowfmt
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


# 寬、高兩個換算比值容許的相對差距: 超過就是長寬比對不上 (錄影框或搜尋範圍
# 框錯), 硬算會讓每個偏移都差幾個百分點
RATIO_TOLERANCE = 0.02


def _video_ratio(region, info, profile):
    """`影片換算比`＝搜尋範圍寬高 ÷ 影片畫面寬高; 條件可疑就拒絕.

    範本圖不因它縮放 (交給引擎的尺度搜尋), 所以它必須落在 profile 引擎
    設定的尺度範圍內, 否則執行時引擎根本找不到範本。
    """
    rw = region[2] / info["width"]
    rh = region[3] / info["height"]
    if abs(rw - rh) / min(rw, rh) > RATIO_TOLERANCE:
        raise ToolError(
            f"影片與搜尋範圍的長寬比對不上：影片 {info['width']}×{info['height']}、"
            f"搜尋範圍 {region[2]}×{region[3]}（寬比 {rw:.3f}、高比 {rh:.3f}，"
            f"差距超過 {RATIO_TOLERANCE:.0%}）。請確認錄影只錄遊戲視窗、"
            "搜尋範圍框在同一個遊戲畫面上")
    ratio = (rw + rh) / 2
    lo, hi = (float(v) for v in load_config(profile)["scale_range"])
    if not lo <= ratio <= hi:
        raise ToolError(
            f"影片換算比 {ratio:.3f} 超出 profile 引擎設定的尺度範圍 "
            f"[{lo}, {hi}]：範本取自影片、不縮放，執行時引擎會找不到它們。"
            "請用與執行時相近的視窗大小重錄，或調整 profile 的 scale_range")
    return ratio


def _screen_scale(profile, fingerprint):
    """目標 profile 的`畫面倍率` (與執行期同一套判定); 回傳 (倍率, 狀態).

    狀態: none (沒有校準對) / uncalibrated (有校準對但本機未校準, 以 1 代入)
    / calibrated。
    """
    cal = calibration.load(profile)
    if cal is None:
        return 1.0, "none"
    if fingerprint is None:
        fingerprint = calibration.current_fingerprint()
    if calibration.is_uncalibrated(cal, fingerprint):
        return 1.0, "uncalibrated"
    return calibration.effective_scale(cal, fingerprint), "calibrated"


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


def assemble(plan, engine=None, fingerprint=None, report_path=None):
    """組裝一份流程存檔; 回傳結果 dict (flow_path、report_path、…).

    plan: 計畫 dict 或計畫 JSON 檔路徑。engine: 已建好的引擎 (測試共用;
    None＝自行建構)。fingerprint: `機器指紋` (None＝讀當下螢幕配置)。
    report_path: 交付報告位置 (None＝計畫的 reportPath, 再沒有就與存檔
    同名並排)。
    """
    p = plan_mod.load(plan)
    profile = p["profile"]
    region, draft = _profile_region(profile)
    info = video_mod.probe(p["video"])
    ratio = _video_ratio(region, info, profile)
    scale, cal_state = _screen_scale(profile, fingerprint)

    frames = video_mod.read_frames(
        p["video"], verify_mod.frames_needed(p["templates"], p["steps"]))
    crops = {n: _crop(frames, n, t, info) for n, t in p["templates"].items()}

    engine = engine or verify_mod.make_engine()
    checked = verify_mod.verify(engine, crops, p["templates"], p["steps"],
                                frames, load_config(profile))
    found = {n: r["boxes"] for n, r in checked.items()}

    def located(i, step):
        # 引擎在該幀實際找到的框; 找不到 (範本會標待重拍) 時退回取材的裁切框
        t = p["templates"][step["template"]]
        return (found[step["template"]].get(verify_mod.step_frame(step, p["templates"]))
                or t["box"])

    steps = defaults.apply(origin_mod.derive(p["steps"], p["templates"], located))
    # 驗證沒過的範本: 名稱加`待重拍`前綴、步驟引用 (含確認圖) 同步改寫
    images = {n: _png(img) for n, img in crops.items()}
    # 範本元資料 pos＝取材當下的中心螢幕座標 (編輯器推算預設原點的備援):
    # 影片像素 → 目前搜尋範圍內的螢幕座標
    pos = {}
    for n, t in p["templates"].items():
        x, y, w, h = t["box"]
        pos[n] = [region[0] + flowfmt.scale_px(x + w // 2, ratio),
                  region[1] + flowfmt.scale_px(y + h // 2, ratio)]
    retake = {}
    for name, r in checked.items():
        if r["reasons"]:
            new = plan_mod.RETAKE_PREFIX + name
            flowfile.rename_refs(steps, name, new)
            images[new] = images.pop(name)
            pos[new] = pos.pop(name)
            retake[new] = r["reasons"]
    # 影片像素的偏移 → 本機像素 (×換算比) → 當前基準尺度 (÷畫面倍率, ADR 0005);
    # 一次乘完再進位, 重用校準模組的步驟縮放 (哪些欄位是像素只有它說得算)
    calibration.scale_steps(steps, ratio / scale)
    data = {"steps": steps, "runMode": "count", "runCount": 1,
            "scanRegion": region, "avoidHover": bool(draft.get("avoidHover", False)),
            flowfmt.COORD_SPACE: flowfmt.REGION}

    flows = flowfile.flows_dir(profile)
    os.makedirs(flows, exist_ok=True)
    rp = report_path or p["report_path"]
    stem = _free_stem(flows, p["name"], beside=rp is None)
    flow_path = os.path.join(flows, stem + flowfile.EXT)
    rp = str(rp or os.path.join(flows, stem + ".md"))

    used = flowfile.used_templates(steps)
    result = {
        "flow_path": flow_path, "report_path": rp,
        "video": p["video"], "profile": profile,
        "video_size": [info["width"], info["height"]],
        "region": region, "ratio": ratio,
        "scale": scale, "calibration": cal_state,
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
