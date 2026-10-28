from __future__ import annotations

import json
import os
import re
import sys

import notice
from notice import bp

import report as r05  # noqa: E402

import flowfile  # noqa: E402

DATE = "2026-10-07"
HEADING = {"cn": f"## {DATE} 晚：開頭關公告",
           "tw": f"## {DATE} 晚：開頭關公告、換忙碌指示"}
STEPS_HEADING = f"## 步驟清單（{DATE} 開頭關公告後更新）"

TW_OLD_RISK = re.compile(r"  - 繁中的忙碌指示範本目前比不到.*")
TW_NEW_RISK = ("  - 繁中的忙碌指示已換新圖（10/07 晚，見最上面那節「開頭關公告、換忙碌指示」），"
               "待實跑確認 `busy_pause`。")


def _load(name):
    with open(os.path.join(notice.RESULTS, name), encoding="utf-8") as f:
        return json.load(f)


def _rng(vals):
    vals = [v for v in vals if v is not None]
    return f"{min(vals):.3f}–{max(vals):.3f}" if vals else "-"


def section(lang, check, frames, sim, n_steps, src_timeout):
    cfg = notice.LANGS[lang]
    n0 = n_steps - 1
    tmpl, r = cfg["template"], cfg["rect"]
    pos, home, low = frames["positive"], frames["home"], frames["low_bitrate"]
    shown, hidden = sim["shown"], sim["hidden"]
    pvid = pos[0]["video"]
    flow_ok = all(x["ok"] for x in check["flow"])
    draft = check.get("draft")
    lines = [
        HEADING[lang], "",
        f"- **改了什麼**：開頭加一步（新的第 1 步）：找「{tmpl}」→ 點擊，點到消失；"
        f"逾時 {notice.TIMEOUT} 秒，找不到就跳過，接著照原本的第 1 步找基建入口。"
        "遊戲登入後跳出的公告蓋住基建入口時，原本流程會在第 1 步等 30 秒後停止。",
        f"  - 步驟設定從 `{cfg['src']}` 開頭清彈窗迴圈裡的同一步原樣複製，只把逾時 {src_timeout:g} 秒改成 "
        f"{notice.TIMEOUT} 秒；固定矩形照搬（x {r['x']}、y {r['y']}、w {r['w']}、h {r['h']}）。"
        f"範本圖也從 `{cfg['src']}` 搬，不換算：同一個客戶端的校準對基準距離、搜尋範圍都相同。",
        f"  - 公告在畫面上：約一輪就點掉；已經在主畫面：多花 {notice.TIMEOUT} 秒。",
        f"  - 原本的 {n0} 步一字不改，編號全部 +1（{n0} → {n_steps} 步）。"
        "**本節以下各段提到的步驟編號，現在都要 +1。**",
    ]
    if cfg["swap_busy"]:
        lines.append(
            f"- **忙碌指示換圖**：換成 `{cfg['src']}` 那張（票 06 從 demo2 第 2000 幀重截、裁到只剩字），"
            "限定範圍維持九宮格 [8, 9]。舊圖字底下疊著另一段淡出中的提示字。")
    lines += [
        "- **驗證**：",
        f"  - 讀回：存檔{'與草稿（草稿目前就是這份）' if draft else ''}都 {n_steps} 步、第 1 步符合規格、"
        f"第 2–{n_steps} 步跟原本的第 1–{n0} 步逐一相同、範本跟早班位元組相同"
        + ("，工作區也有" if draft else "")
        + ("，忙碌指示圖跟早班相同" if cfg["swap_busy"] else "")
        + ("。" if flow_ok and (not draft or all(x["ok"] for x in draft)) else "。**有不符，見 check.json。**"),
        f"  - 真引擎＋影格（arknights 門檻、影格貼到實機搜尋範圍的畫布）：{pvid} 有公告的影格 "
        f"{sum(x['ok'] for x in pos)}/{len(pos)} 找到且在固定矩形內（{_rng([x['score'] for x in pos])}，"
        f"第 {'、'.join(str(x['frame']) for x in pos)} 幀）；"
        f"{cfg['evening_video']} 主畫面影格 {sum(x['ok'] for x in home)}/{len(home)} 找不到"
        + (f"（最高相似度 {max(x['best'] or 0 for x in home):.3f}，"
           f"第 {'、'.join(str(x['frame']) for x in home)} 幀，每 {frames['stride']} 幀抽一張、"
           "基建入口找得到的才算；示範影片裡主畫面只有開頭這段）。"
           if home else "（**一張主畫面影格都沒找到**，見 frames json）。"),
    ]
    if lang == "cn":
        lines.append(
            f"    demo6 上沒有公告，改用 demo5（票 08 驗證固定矩形用的也是這三格）；"
            f"demo1 低位元率 {sum(x['found'] for x in low)}/{len(low)}，照實列出、不算數（同票 08）。")
    else:
        lines.append(
            "    demo2 上圓形叉叉出現在四個彈窗（簽到、會客室…），第 186–216 幀那個是公告（活動公告／系統公告／資訊速報）。"
            "忙碌指示新圖沿用票 06 的驗證（demo2 有忙碌 38/38、沒忙碌 63 張都找不到），沒有重驗。")
    lines += [
        "  - 無頭執行器（第 1–2 步，假畫面＋虛擬時鐘）：公告在 → 點 X 一次、確認消失"
        f"（{shown['step1_secs']} 秒）→ 點基建入口；公告不在 → {hidden['step1_secs']} 秒逾時跳過 → 點基建入口，"
        "點基建入口前沒有任何點擊；兩個劇本從點基建入口起的事件序列"
        + ("相同。" if sim["same_after_base"] else "**不同**。"),
        "- **已知風險**：",
        "  - 只處理公告。先跳出的是簽到或活動彈窗時，公告約 4 秒後才出來，這一步會漏關，"
        "流程在找基建入口那步 30 秒後停止。早班清彈窗的迴圈沒搬（規格決定，實跑遇到再處理）。",
    ]
    if cfg["swap_busy"]:
        lines.append(
            "  - 忙碌指示新圖還沒在實機驗證過。實跑如果沒忙碌卻一直暫停（日誌 `busy_pause` 很大），"
            "就換回備份裡的舊圖。")
    lines += [
        "- **實跑看什麼**（`autoclick.log` 的 `find.target step=1`）：公告在 → `role=confirm_gone result=gone clicks=1`；"
        "已在主畫面 → `role=find result=timeout`，約 2 秒。"
        + ("找圖步驟出現 `busy_pause` 大於 0，表示新的忙碌指示比得到；沒遇到網路慢就看不到，不算失敗。"
           if cfg["swap_busy"] else ""),
        f"- 修正前的備份：`app/dist/{os.path.basename(notice.BACKUP)}/`",
        "- 腳本（`.scratch/evening-notice-close/`，都可重跑）：建構 `build.py`；讀回 `check.py`；"
        "真引擎影格 `frames.py`；無頭執行器 `sim.py`；本報告 `report_notice.py`。結果在 `results/`。",
        "",
    ]
    return lines


def step_table(steps):
    lines = r05.step_table(steps)
    lines[0] = STEPS_HEADING
    return lines


def main():
    check, sim = _load("check.json"), _load("sim.json")
    for lang, cfg in notice.LANGS.items():
        name = cfg["flow"]
        frames = _load(f"frames_{lang}.json")
        md = os.path.join(bp.FLOWS, name + ".md")
        with open(md, encoding="utf-8") as f:
            text = f.read()
        steps = flowfile.read(bp.flow_path(name))["data"]["steps"]
        src = flowfile.read(bp.flow_path(cfg["src"]))["data"]["steps"]
        src_timeout = next(s["timeout"] for s in src if notice.is_notice_step(s, lang))
        text = r05.replace_section(text, re.escape(HEADING[lang]),
                                   section(lang, check[name], frames, sim[name],
                                           len(steps), src_timeout),
                                   before_first_h2=True)
        if cfg["swap_busy"] and TW_NEW_RISK not in text:
            text, n = TW_OLD_RISK.subn(TW_NEW_RISK, text)
            if n != 1:
                raise SystemExit(f"{name}.md: 「忙碌指示範本目前比不到」那條找到 {n} 處, 預期 1 處")
        text = r05.replace_section(text, r"## 步驟清單", step_table(steps) + [""])
        with open(md, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"{name}.md: 已更新（步驟 {len(steps)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
