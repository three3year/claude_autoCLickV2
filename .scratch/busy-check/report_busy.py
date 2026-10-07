"""票 05 的交付報告: 四份流程的 .md 最上面加「勾忙碌檢查」一節、重產步驟清單 (標出〔忙碌檢查〕).

    .venv/Scripts/python.exe .scratch/busy-check/report_busy.py [--flows 目錄]

先跑 build.py --apply (勾了哪些從 results/build.json 讀)。可以重跑: 本節與步驟清單整段換掉;
報告其他段落不動。節與步驟清單的換法沿用 busy-pause-fixed-rect/report.py。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "busy-pause-fixed-rect"))
import common  # noqa: E402
import report as r05  # noqa: E402  (replace_section)

import build  # noqa: E402

import flowfile  # noqa: E402

DATE = "2026-10-08"
HEADING = f"## {DATE}：勾「忙碌檢查」（取代忙碌暫停）"
STEPS_HEADING = f"## 步驟清單（{DATE} 忙碌檢查後更新）"
OLD_HEADING = "## 2026-10-07：拿掉忙碌等待步驟（改由忙碌暫停接手）"
OLD_NOTE = ("（**{date} 註**：下面說的忙碌暫停已經拿掉，換成本報告最上面那節的「忙碌檢查」；"
            "拿掉等待步驟這件事不變。）")


def step_table(steps):
    import app   # 步驟描述與編輯器同一套 (app.step_desc, 勾了的尾端有〔忙碌檢查〕)
    lines = [STEPS_HEADING, "", "| # | 步驟 | 內容 |", "|---|---|---|"]
    for i, s in enumerate(steps, 1):
        lines.append(f"| {i} | {s['type']} | {app.step_desc(s)} |")
    return lines


def _group(checked):
    groups = {}
    for x in checked:
        why = x["why"]
        key = ("換班點 ⇄" if why.startswith("換班點") else
               "換班拖曳" if why == "換班拖曳" else
               "開頭清彈窗的關閉" if why.startswith("開頭清彈窗") else
               "傳遞線索" if why == "傳遞線索" else "可收獲／幹員信賴／確定")
        groups.setdefault(key, []).append(x["no"])
    return groups


def section(name, rec, n_steps, tw):
    checked = rec["checked"]
    groups = _group(checked)
    lines = [
        HEADING, "",
        "- **執行器改了（ADR 0011，取代 ADR 0010）**：忙碌暫停拿掉了——找圖等待（分岔條件、一般找圖、"
        "生效確認、等待消失）不再因為畫面上有忙碌指示而延後逾時，逾時照常計時；日誌不再有 `busy_pause`。"
        "改成步驟選項「忙碌檢查」：勾了的步驟（座標點擊、拖曳、按鍵、找圖點擊）送出輸入後，"
        "先在「忙碌出現等候」（流程設定，這份用預設 1000ms）內看忙碌指示出不出現：沒出現就放行；"
        "出現就等它消失，才做生效確認（沒設確認的等完就結束）。從送出起 60 秒等不到消失＝停止流程"
        "（不走「找不到時」）。補做重送後不再另等（補做前查忙碌指示的門照舊）。",
        "  - 10/07 晚 `晚_簡中` 實跑：換班時忙碌指示只蓋在畫面下方、列名一直看得到，找圖第一輪就找到並"
        "馬上操作，忙碌暫停完全沒作用（換班段每一步 `busy_pause=0.00`），第一次拖曳被吃掉靠補做第二次才生效。"
        "所以改成由流程作者勾「會讓遊戲忙」的步驟。",
        f"- **勾了哪些步驟**（共 {len(checked)} 步，步驟編號不變，{n_steps} 步）：",
    ]
    for key in ("換班點 ⇄", "換班拖曳", "開頭清彈窗的關閉", "傳遞線索", "可收獲／幹員信賴／確定"):
        nos = groups.get(key)
        if nos:
            lines.append(f"  - {key}：第 {'、'.join(map(str, nos))} 步")
    lines += [
        "  - 換班點 ⇄ 就是 10/07 拿掉「忙碌指示 → 等待消失」步驟的位置（當時緊接在那些等待之前的點擊）。",
        "  - 沒勾、但遇到忙碌時確認可能被拖到逾時的候選：訂單交付（與可收獲同一個分岔）"
        + ("、今日配給的關閉點擊" if name == "早_簡中" else "")
        + "；實跑看到它們的確認逾時再補勾。",
        "- **代價**：勾了的步驟在網路正常、沒出現忙碌時固定多等約 1 秒，"
        f"這份最多多約 {len(checked)} 秒。",
        "- **驗證**：讀回存檔——勾選集合跟預期一致、其他步驟與流程層級設定跟備份逐一相同、範本圖不變、"
        "忙碌指示在（執行前檢查不會擋）、草稿（屬於這份時）一致。執行器行為由 `app/tests/test_runner_busy_check.py`"
        "（假畫面＋虛擬時鐘）覆蓋：送出後 0.5 秒出現、3 秒消失 → 下一步在消失之後；60 秒不消失 → 停止；"
        "沒勾的步驟時間點不變。",
        "- **實跑看什麼**（`autoclick.log`）：",
        "  - 每個勾了的步驟在輸入那筆（`input`／`find.target`）之後有一筆 `busy.check`："
        "`result=gone`（看到忙碌、等到消失，`waited`＝從送出起幾秒）、`not_appeared`（1 秒內沒出現，照常放行）、"
        "`timeout`（60 秒沒消失，流程停止——查當時是不是真的斷線）。",
        "  - 換班段每個 ⇄ 與拖曳都有 `busy.check`；拖曳的 `input.confirm` 應該 `inputs=1`（不再靠補做第二次）。",
        "  - 開頭清彈窗沒有提早跳出；傳遞線索、可收獲、幹員信賴、確定的確認沒有逾時。",
    ]
    if tw:
        lines.append("  - 繁中的忙碌指示是 10/07 換的新圖，這是第一次實機確認：`busy.check` 至少要有一次 `gone`；"
                     "全部 `not_appeared` 就要查範本（限定範圍九宮格 [8, 9]）。")
    lines += [
        "- **已知風險**：沒勾到的步驟遇到忙碌，確認逾時會被吃掉（跟 10/07 以前一樣），實跑發現就補勾；"
        "斷線時勾了的步驟 60 秒後停止流程，不會白點。",
        f"- 修正前的備份：`app/dist/{os.path.basename(build.BACKUP)}/`",
        "- 腳本（`.scratch/busy-check/`，都可重跑）：建構＋讀回驗證 `build.py`（`--apply`／`--check`）；"
        "本報告 `report_busy.py`。勾了哪些在 `results/build.json`。", "",
    ]
    return lines


def annotate_old(text):
    """舊的「拿掉忙碌等待步驟（改由忙碌暫停接手）」一節標題下加一句註 (重跑不重複加)."""
    note = OLD_NOTE.format(date=DATE)
    if OLD_HEADING not in text or note in text:
        return text
    return text.replace(OLD_HEADING + "\n", OLD_HEADING + "\n\n" + note + "\n", 1)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--flows", default=common.FLOWS)
    args = ap.parse_args(argv)
    with open(os.path.join(build.RESULTS, "build.json"), encoding="utf-8") as f:
        built = json.load(f)
    for name in common.FLOW_NAMES:
        path = common.flow_path(name, args.flows)
        md = os.path.splitext(path)[0] + ".md"
        steps = flowfile.read(path)["data"]["steps"]
        rec = built[name]
        if len(steps) != rec["steps"]:
            raise SystemExit(f"{name}: 步驟數跟建構結果不同, 先重跑 build.py")
        with open(md, encoding="utf-8") as f:
            text = f.read()
        text = r05.replace_section(text, re.escape(HEADING),
                                   section(name, rec, len(steps), name.endswith("繁中")),
                                   before_first_h2=True)
        text = annotate_old(text)
        text = r05.replace_section(text, r"## 步驟清單", step_table(steps) + [""])
        with open(md, "w", encoding="utf-8") as f:
            f.write(text.rstrip("\n") + "\n")
        print(f"已更新 {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
