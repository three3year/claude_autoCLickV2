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
    warnings = _size_warnings(region, info)
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
    # 影片像素＝螢幕像素, 以影片左上角對齊搜尋範圍左上角近似
    pos = {}
    for n, t in p["templates"].items():
        x, y, w, h = t["box"]
        pos[n] = [region[0] + x + w // 2, region[1] + y + h // 2]
    retake = {}
    for name, r in checked.items():
        if r["reasons"]:
            new = plan_mod.RETAKE_PREFIX + name
            flowfile.rename_refs(steps, name, new)
            images[new] = images.pop(name)
            pos[new] = pos.pop(name)
            retake[new] = r["reasons"]
    # 影片像素＝本機像素 → 當前基準尺度 (÷畫面倍率, ADR 0005); 重用校準模組的
    # 步驟縮放 (哪些欄位是像素只有它說得算)
    if scale != 1.0:
        calibration.scale_steps(steps, 1.0 / scale)
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
        "region": region, "warnings": warnings,
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
