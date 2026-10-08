"""交付報告: 早班 .md 最上面加「收取信用改成等物資彈窗出現」一節, 重產步驟清單.

    .venv/Scripts/python.exe .scratch/credit-collect-confirm/report.py --lang tw|cn [--flows 目錄]

先跑 build.py --apply、check.py、sim.py (從 results/ 讀它們的結果)。可以重跑: 本節與步驟清單
整段換掉, 報告其他段落不動。節與步驟清單的換法沿用 busy-pause-fixed-rect/report.py。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import collect
from collect import bp

r05 = collect.load_module("bp_report", os.path.join(collect.SCRATCH, "busy-pause-fixed-rect",
                                               "report.py"), common=bp)

import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402

DATE = "2026-10-08"
HEADING = f"## {DATE} 下午：收取信用改成等物資彈窗出現"
STEPS_HEADING = f"## 步驟清單（{DATE} 收取信用改等物資彈窗後更新）"


def _results(lang):
    out = {}
    for kind in ("build", "check", "sim"):
        p = os.path.join(collect.RESULTS, f"{kind}_{lang}.json")
        if not os.path.isfile(p):
            raise SystemExit(f"缺 {p}: 先跑 {kind}.py --lang {lang}")
        with open(p, encoding="utf-8") as f:
            out[kind] = json.load(f)
    return out


def step_table(steps):
    import app   # 步驟描述與編輯器同一套 (app.step_desc)
    lines = [STEPS_HEADING, "", "| # | 步驟 | 內容 |", "|---|---|---|"]
    for i, s in enumerate(steps, 1):
        lines.append(f"| {i} | {s['type']} | {app.step_desc(s)} |")
    return lines


def section(lang, res, steps):
    import app
    n = res["build"]["step"]
    got = steps[n]                      # 緊接的下一步 (0 起算的 n＝編號 n+1)
    got_name = findtarget.template(got)
    tw = lang == "tw"
    sims = res["sim"]["results"]
    checks = res["check"]
    flow_ok = all(x["ok"] for x in checks["flow"])
    draft = checks.get("draft")
    lines = [
        HEADING, "",
        f"規格：`.scratch/credit-collect-confirm/spec.md`；票 `.scratch/credit-collect-confirm/issues/"
        f"{'01-tw' if tw else '02-cn'}-collect-confirm.md`。", "",
        "- **為什麼**：10/08 08:51 實跑 `早_簡中`，信用交易所點下後 1 秒就找到並點了收取信用，"
        "那時商店頁還沒載好（找圖分數 0.918），這一下被遊戲吃掉；這一步沒有生效確認不會補做，"
        "接著等物資彈窗 8 秒逾時跳出，信用點沒領到、後面採購買不起。"
        + ("繁中這次沒出問題，但有同樣的風險，兩版改成同一個做法。" if tw else
           "示範影片也看得到同樣的現象（f2967、f3002 沒反應，載好後 f3017 那一下才有效，見下面「從影片剔除的操作」）。"),
        f"- **改了什麼**：第 {n} 步「收取信用」（收取信用分岔的條件）只改三個欄位，其餘不動"
        f"（逾時 3 秒、偏移、比色、限定範圍、忙碌檢查不勾）。步驟數 {res['build']['steps']}、編號不變。",
        "  - 生效確認：不確認 → **確認圖出現**。",
        f"  - 確認圖：照抄第 {n + 1} 步「{got_name}」的找圖目標（範本、限定範圍都相同）。",
        "  - 找不到時：跳過 → **跳出**。",
        f"  - 現在這一步：{app.step_desc(steps[n - 1])}",
        "- **走向**：",
        "  - 點了、物資彈窗出現 → 後面照舊"
        + (f"（第 {n + 1} 步點獲得物資到消失）" if tw
           else f"（第 {n + 1} 步等获得物资出現、第 {n + 2} 步相對它點座標關掉）")
        + "，接著採購。",
        "  - 點了沒看到物資彈窗 → 照引擎原有的補做規則再點：距上次輸入過 1 秒（流程的補做間隔）、"
        "按鈕還在原位、畫面上沒有忙碌指示。3 秒內還等不到 → **跳出收取信用分岔，直接採購**"
        f"（以前要等第 {n + 1} 步 8 秒逾時才跳出）。",
        "  - 收取信用按鈕找不到 → 照舊約 3 秒後跳過整個分岔，直接採購。",
        "- **代價**：正常情況多約 0.3 秒（點完等一個輪詢間隔才看到彈窗）。",
        "- **驗證**：",
        f"  - **讀回檢查**（`check.py`）：{'全部通過' if flow_ok else '**有不通過**'}——"
        f"只有第 {n} 步不同、只差三個欄位、確認圖＝第 {n + 1} 步的找圖目標、其他步驟／流程層級設定／"
        "範本與備份一字不差、區段完整"
        + ("；草稿與工作區和存檔相同。" if draft and all(x["ok"] for x in draft) else
           "（草稿屬於別份存檔）。" if not draft else "；**草稿與存檔不同**。"),
        f"  - **無頭執行器**（`sim.py`，假畫面＋虛擬時鐘；片段＝收取信用分岔到公開招募，"
        f"商店模擬器沿用 credit-store-switch）：{sum(x['ok'] for x in sims)}/{len(sims)} 個劇本符合預期，"
        "每個劇本開始採購之後的事件序列都和改動前的版本相同。", "",
        "    | 劇本 | 結果 | 收取信用點幾下 | 到開始採購 | 改動前 |",
        "    |---|---|---|---|---|",
    ]
    for x in sims:
        new, old = x["new"], x["old"]
        lines.append(f"    | {x['desc']} | {'通過' if x['ok'] else '**不符**'} | {new['credit_clicks']} | "
                     f"{new['secs_to_purchase']} 秒 | 點 {old['credit_clicks']} 下、"
                     f"{old['secs_to_purchase']} 秒 |")
    lines += [
        "",
        "- **實跑看什麼**（`autoclick.log`）：",
        f"  - 第 {n} 步有一筆 `find.target role=confirm_appear`：`result=found` 表示物資彈窗出現，"
        "`clicks` 是點了幾下（1＝第一下就生效；2 以上＝有補做）；`result=timeout` 表示 3 秒內沒看到彈窗、"
        "跳出分岔——查那天信用有沒有領到。",
        "  - 物資彈窗出現後原本的關彈窗步驟正常，接著開始採購。",
        "- **已知風險**：",
        "  - 「今天已經收過信用」時按鈕長什麼樣子還沒有證據；不論消失、變灰或照樣可點，新設定都只會跳過或跳出、接著採購，不會停止流程。",
        "  - 補做要按鈕還在原位：遊戲在載入完成的瞬間把按鈕挪了位置時不會補做，3 秒後跳出。",
        "  - 3 秒內共點約 3 下（第一下＋補做 2 次；規格寫的「約 3 次補做機會」指的是這 3 下）；"
        "頁面載入比這更久時還是會跳出（信用沒領到，只少買幾樣）。",
    ]
    if not tw:
        lines.append("  - handoff 待辦第 5 項（08:51 获得物资逾時）推測就是第一下被吃造成的，下次實跑一起觀察。")
        lines.append(f"- **步驟清單**：本報告最後的步驟清單照插入第 2 步之後的編號重產（收取信用 {n}、获得物资 {n + 1}、"
                     f"座標點擊關彈窗 {n + 2}）；前面各段寫的步驟編號仍是當時的。")
    lines += [
        f"- 修改前的備份：`app/dist/{os.path.basename(os.path.dirname(os.path.dirname(res['build']['orig_flows'])))}/`"
        if res["build"].get("orig_flows") else "- 修改前的備份：（試跑目錄，沒有備份）",
        f"- 腳本（`.scratch/credit-collect-confirm/`，都可重跑，`--lang {lang}`）：建構 `build.py`（`--apply` 寫回）；"
        "讀回檢查 `check.py`；無頭執行器 `sim.py`；本報告 `report.py`。結果在 `results/`。", "",
    ]
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=sorted(collect.LANGS), required=True)
    ap.add_argument("--flows", default=bp.FLOWS)
    args = ap.parse_args(argv)
    cfg = collect.LANGS[args.lang]
    res = _results(args.lang)
    path = bp.flow_path(cfg["flow"], args.flows)
    md = os.path.splitext(path)[0] + ".md"
    steps = flowfile.read(path)["data"]["steps"]
    if len(steps) != res["build"]["steps"] or collect.credit_index(steps, args.lang) + 1 != res["build"]["step"]:
        raise SystemExit(f"{cfg['flow']}: 存檔跟建構結果不同, 先重跑 build.py")
    if steps[res["build"]["step"] - 1].get("confirm") != "appear":
        raise SystemExit(f"{cfg['flow']}: 還沒改 (先跑 build.py --apply)")
    with open(md, encoding="utf-8") as f:
        text = f.read()
    text = r05.replace_section(text, re.escape(HEADING), section(args.lang, res, steps),
                               before_first_h2=True)
    text = r05.replace_section(text, r"## 步驟清單", step_table(steps) + [""])
    with open(md, "w", encoding="utf-8") as f:
        f.write(text.rstrip("\n") + "\n")
    print(f"已更新 {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
