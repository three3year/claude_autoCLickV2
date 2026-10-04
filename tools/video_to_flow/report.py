"""`交付報告` (Markdown): 隨存檔附上的說明, 流程存檔格式不為它增加任何欄位."""
from __future__ import annotations

import os

from automation import findtarget

from . import verify as verify_mod


def _fmt_region(r):
    return ", ".join(str(int(v)) for v in r)


def _scale_line(res):
    state = res["calibration"]
    if state == "none":
        return "profile 沒有校準對，不換算"
    if state == "uncalibrated":
        return ("profile 有校準對但本機未校準 → 以倍率 1 換算，座標可能偏移；"
                "建議先在 app 按「校準」再重新組裝")
    if res["scale"] == 1.0:
        return "1.000（已校準，不換算）"
    return f"{res['scale']:.3f}（已校準；座標再 ÷{res['scale']:.3f} 換回基準尺度）"


def render(res, plan):
    """把組裝結果與計畫寫的說明排成報告文字."""
    lines = [f"# 交付報告：{os.path.splitext(os.path.basename(res['flow_path']))[0]}", ""]
    lines += [
        "## 概要", "",
        f"- 流程存檔：`{res['flow_path']}`",
        f"- 示範影片：`{res['video']}`（{res['video_size'][0]}×{res['video_size'][1]}）",
        f"- 搜尋範圍：[{_fmt_region(res['region'])}]",
        "- 影片與實際畫面同尺度：影片像素＝螢幕像素，偏移與範本圖都不縮放",
        f"- 畫面倍率：{_scale_line(res)}",
        f"- 步驟數：{res['steps']}",
        f"- 範本數：{res['templates']}",
    ]
    if res["unused"]:
        lines.append(f"- 沒有步驟引用、未放進存檔的範本：{'、'.join(res['unused'])}")
    lines.append("")
    if res["warnings"]:
        lines += ["## 提醒", ""] + [f"- {w}" for w in res["warnings"]] + [""]
    lines += ["## 自我驗證", ""]
    if res["verification"] == "coarse":
        lines += ["**驗證不完整**：深度驗證模型無法載入，引擎只剩粗篩；"
                  "「找得到」可能是誤判，請在遊戲裡實跑確認每一個找圖步驟。", ""]
    else:
        lines += ["每張範本都用引擎（粗篩＋深度驗證）對影格重跑過。", ""]

    lines += ["## 待重拍", ""]
    if res["retake"]:
        lines += ["範本名帶「待重拍_」前綴，範本面板一眼可見；步驟已建好，"
                  "重拍那張圖即可（面板重新拾取後改名去掉前綴）。", "",
                  "| 範本 | 原因 | 重拍建議 |", "|---|---|---|"]
        for name, why in res["retake"].items():
            lines.append(f"| {name} | {'；'.join(why)} | "
                         f"{'；'.join(verify_mod.advice(why))} |")
    else:
        lines.append("無——每張範本都通過驗證。")
    lines.append("")

    notes = plan["report"]
    for title, key, empty in (
            ("分岔建議", "branches",
             "無。影片裡沒出現的彈窗不會被加成分岔；實跑卡住時再自己補。"),
            ("無法用點擊解釋的畫面變化", "unexplained",
             "無。"),

            ("其他說明", "notes", None)):
        if not notes[key] and empty is None:
            continue
        lines += [f"## {title}", ""]
        lines += [f"- {n}" for n in notes[key]] or [empty]
        lines.append("")

    # 按鍵影片裡看不到, 一定來自口頭補充: 流程裡的按鍵步驟一律列出, 再附計畫的說明
    lines += ["## 口頭補充的按鍵", ""]
    keys = [f"- 步驟 {i}：按鍵 `{s['keys']}`"
            for i, s in enumerate(res["step_list"], 1) if s["type"] == "key"]
    lines += keys + [f"- {n}" for n in notes["keys"]] or ["無。"]
    lines.append("")

    lines += ["## 步驟清單", "", "| # | 步驟 | 內容 |", "|---|---|---|"]
    for i, s in enumerate(res["step_list"], 1):
        lines.append(f"| {i} | {_LABELS.get(s['type'], s['type'])} | {_describe(s)} |")
    lines.append("")
    return "\n".join(lines)


_LABELS = {"find_click": "找圖點擊", "click": "座標點擊", "drag": "滑鼠拖曳",
           "wait": "等待", "key": "按鍵", "loop_start": "重複開始",
           "loop_end": "重複結束", "branch_start": "分岔開始",
           "branch_or": "分岔（或）", "branch_end": "分岔結束"}
_ACTION = {"click": "點擊", "none": "僅等待出現", "wait_gone": "等待消失"}
_CONFIRM = {"none": "", "gone": "，點到目標圖消失", "next": "，點到下一步的圖出現",
            "appear": "，點到確認圖出現"}
_NF = {"stop": "停止", "skip": "跳過", "break": "跳出區段"}


def _describe(s):
    """步驟一行摘要 (偏移已是存檔裡的基準尺度數值)."""
    t = s["type"]
    if t == "find_click":
        text = f"「{findtarget.template(s)}」{_ACTION[s['action']]}"
        if s["offsetX"] or s["offsetY"]:
            text += f"，偏移 {s['offsetX']:+d},{s['offsetY']:+d}"
        text += _CONFIRM[s["confirm"]]
        if s["confirm"] == "appear":
            text += f"「{findtarget.confirm_template(s)}」"
        text += f"；逾時 {s['timeout']}s 找不到時{_NF[s['onNotFound']]}"
        if not s["updateOrigin"]:
            text += "；不更新原點"
        return text
    if t == "click":
        return f"相對原點 {s['x']:+d},{s['y']:+d}"
    if t == "drag":
        return f"相對原點 {s['x1']:+d},{s['y1']:+d} → {s['x2']:+d},{s['y2']:+d}"
    if t == "wait":
        return f"{s['ms']} ms"
    if t == "key":
        return s["keys"]
    if t == "loop_start":
        return f"{s['count']} 次"
    return ""
