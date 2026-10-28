from __future__ import annotations

import argparse
import json
import os
import re
import sys

import common

import flowfile  # noqa: E402

DATE = "2026-10-07"
HEADING = f"## {DATE}：拿掉忙碌等待步驟（改由忙碌暫停接手）"
STEPS_HEADING = f"## 步驟清單（{DATE} 忙碌暫停後更新）"


def step_table(steps):
    import app
    lines = [STEPS_HEADING, "", "| # | 步驟 | 內容 |", "|---|---|---|"]
    for i, s in enumerate(steps, 1):
        lines.append(f"| {i} | {s['type']} | {app.step_desc(s)} |")
    return lines


def section(name, rec, sims):
    removed = rec["removed"]
    lines = [HEADING, "",
             "- **執行器改了（ADR 0010）**：所有找圖在等待時（分岔條件、一般找圖、生效確認、等待消失），"
             "這一輪沒找到就查一次忙碌指示；畫面上有忙碌指示的時間不算進逾時，同一步驟最多多等 60 秒。"
             "日誌 `find.target`／`input.confirm` 多一欄 `busy_pause`（這一步暫停了幾秒）。",
             f"- 所以換班後專門等忙碌指示消失的「忙碌指示 → 等待消失」步驟拿掉了，共 {len(removed)} 步"
             f"（{rec['before']} → {rec['after']} 步）。改動前的編號與位置：", ""]
    for x in removed:
        lines.append(f"  - 第 {x['no']} 步（{x['before']} 之後，接 {x['after']}）")
    lines += ["",
              "- **驗證（無頭執行器，假畫面＋虛擬時鐘）**：每個拿掉的位置切一段（前面的列名找圖 → 點擊 → 下一個找圖），"
              "跑兩個劇本："
              f"點擊後忙碌 15 秒（比下一步的逾時長）、這段時間下一步的圖不出現；以及完全沒忙碌。", ""]
    seen = set()
    for s in sims:
        key = tuple(s["segment"])
        if key in seen:
            continue
        seen.add(key)
        w, n = s["with_busy"], s["no_busy"]
        lines.append(
            f"  - 第 {s['segment'][0]}–{s['segment'][1]} 步，下一步「{w['next']}」："
            f"有忙碌時等到忙碌結束才找到（暫停 {w['busy_pause']} 秒）、流程照常走完；"
            f"沒忙碌時直接走，一次都沒查忙碌指示。" + ("" if s["ok"] else "**不符預期**"))
    back = sorted({n for s in sims for n in s["click_then_click"]})
    lines += ["", "- **已知風險**："]
    if back:
        lines.append(
            "  - 拿掉之後有「點擊緊接點擊」的地方（改動後第 "
            + "、".join(str(n) for n in back)
            + " 步之後）：座標點擊不找圖，所以兩下之間**不會**等忙碌。以前這裡最多等 1 秒看忙碌指示出不出現；"
              "現在第二下立刻送出。實跑若第二下被吃掉（換班沒換成），要在中間加回等待或改成找圖點擊。")
    if name.endswith("繁中"):
        lines.append("  - 繁中的忙碌指示範本目前比不到（10/07 日誌全部 not_appeared，最高約 0.19），"
                     "在換掉之前繁中**沒有**忙碌暫停的效果：網路慢時下一步照原本的逾時判定。"
                     "重截見 `.scratch/busy-pause-fixed-rect/issues/06-tw-busy-template.md`。")
    lines.append("  - 網路斷線時忙碌指示一直在：每一步最多多等 60 秒，之後照常逾時、走「找不到時」。")
    lines += ["",
              f"- 修正前的備份：`app/dist/{os.path.basename(common.BACKUP)}/`",
              "- 建構腳本：`.scratch/busy-pause-fixed-rect/remove_busy_waits.py`；"
              "驗證：`.scratch/busy-pause-fixed-rect/sim_busy.py`（都可重跑）", ""]
    return lines


def replace_section(text, heading_re, new_lines, before_first_h2=False):
    lines = text.split("\n")
    idx = next((i for i, l in enumerate(lines) if re.match(heading_re, l)), None)
    if idx is not None:
        end = next((j for j in range(idx + 1, len(lines)) if lines[j].startswith("## ")),
                   len(lines))
        lines[idx:end] = new_lines
    elif before_first_h2:
        at = next(i for i, l in enumerate(lines) if l.startswith("## "))
        lines[at:at] = new_lines
    else:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += [""] + new_lines
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--flows", default=common.FLOWS)
    args = ap.parse_args(argv)
    with open(os.path.join(common.RESULTS, "remove_busy_waits.json"),
              encoding="utf-8") as f:
        removed = json.load(f)
    with open(os.path.join(common.RESULTS, "sim_busy.json"), encoding="utf-8") as f:
        sims = json.load(f)
    for name in common.FLOW_NAMES:
        path = common.flow_path(name, args.flows)
        md = os.path.splitext(path)[0] + ".md"
        steps = flowfile.read(path)["data"]["steps"]
        if len(steps) != removed[name]["after"]:
            raise SystemExit(f"{name}: 步驟數跟建構結果不同, 先重跑建構與驗證")
        with open(md, encoding="utf-8") as f:
            text = f.read()
        text = replace_section(text, re.escape(HEADING),
                               section(name, removed[name], sims[name]),
                               before_first_h2=True)
        text = replace_section(text, r"## 步驟清單", step_table(steps) + [""])
        with open(md, "w", encoding="utf-8") as f:
            f.write(text.rstrip("\n") + "\n")
        print(f"已更新 {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
