"""流程 .md 報告: 加「採購中心改成一個分岔」一節、重產步驟清單 (見 spec.md「報告」).

    .venv/Scripts/python.exe .scratch/credit-store-switch/report.py --lang tw
    .venv/Scripts/python.exe .scratch/credit-store-switch/report.py --lang cn [--flow 早_簡中]

先跑 build.py、sim.py、frames.py (驗證結果從 results/*.json 讀)。可以重跑: 本節與
步驟清單整段換掉; 報告其他段落 (概要、流程內容) 不動, 要另外手改。
步驟清單的文字用 app 自己的 step_desc (與編輯器步驟清單同一套)。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import common
from common import NO_COLOR, PRIORITY

import flowfile  # noqa: E402

DATE = "2026-10-07"
HEADING = f"## {DATE}：採購中心改成一個分岔（找到就買）"
STEPS_HEADING = f"## 步驟清單（{DATE} 更新）"

# 採購中心範本報告 (oCam Video/採購中心範本/報告.md) 裡沒有畫面可驗的商品
UNVERIFIED = {
    "tw": ["源岩", "代糖", "酯原料", "異鐵碎片", "雙酮", "酮凝集", "碳", "碳素", "碳素組",
           "技巧概要·卷1", "技巧概要·卷2"],
    "cn": ["源岩", "代糖", "酯原料", "異鐵碎片", "雙酮", "酮凝集", "破損裝置", "碳", "碳素組",
           "龍門幣", "技巧概要·卷1"],
}
TICKET = {"tw": "01-tw-switch.md", "cn": "02-cn-switch-and-replace.md"}
BACKUP_FLOW = {"tw": "早_繁中", "cn": "早_簡中_demo6"}


def block_span(steps):
    start, nav = common.purchase_span(steps)
    return start + 1, nav   # 1-based: 重複區段開始 … 重複區段結束


def step_table(steps):
    import app   # 步驟描述與編輯器同一套 (app.step_desc)
    lines = [STEPS_HEADING, "", "| # | 步驟 | 內容 |", "|---|---|---|"]
    for i, s in enumerate(steps, 1):
        lines.append(f"| {i} | {s['type']} | {app.step_desc(s)} |")
    return lines


def tail_text(steps):
    base, tail = common.buy_tail(steps[slice(*common.purchase_span(steps))])
    import app
    return "；".join(app.step_desc(s) for s in tail)


def sim_lines(sim):
    out = [f"  - **接縫一（無頭執行器，模擬商店）**：{sum(r['ok'] for r in sim['results'])}/"
           f"{len(sim['results'])} 個劇本符合預期的事件序列。", "",
           "    | 劇本 | 結果 | 實際點擊順序 |", "    |---|---|---|"]
    for r in sim["results"]:
        got = " → ".join(r["got"])
        if len(got) > 160:
            got = got[:160] + "…"
        out.append(f"    | {r['desc']} | {'通過' if r['ok'] else '**失敗**'} | {got} |")
    return out + [""]


def frame_lines(fr):
    res = fr["results"]
    low = [o for o in res if o["low_bitrate"]]
    out = [f"  - **接縫二（真引擎＋標註商店影格）**：{sum(o['ok'] for o in res)}/{len(res)} 張影格"
           "分岔挑到的卡等於預期（還沒售完的卡中優先最高的那種，同種取最上面那格，位置在容許值內）"
           + (f"；demo1 的 {len(low)} 張照實列出（低位元率 0.5 Mbps，不算失敗）" if low else "")
           + "。", "",
           "    | 影格 | 預期 | 分岔走的分支 | 結果 |", "    |---|---|---|---|"]
    for o in res:
        e, p = o["expected"], o["picked"]
        want = "不走任何分支" if e is None else e["item"]
        if p is None:
            got = "不走任何分支"
        else:
            got = f"分支 {p['branch']} {p['item']}（分數 {p['score']}"
            got += f"、比色 {p['color']}" if p["color"] is not None else "、不比色"
            got += f"、距預期 {p['dist']}px）" if "dist" in p else "）"
        if o["ok"]:
            verdict = "通過"
        else:
            q = o.get("expected_query") or {}
            why = f"{e['item']}範本最高 {q.get('best')}、未過 {q.get('failed')}" if e else ""
            verdict = ("不符（demo1 低位元率；" if o["low_bitrate"] else "**不符**（") + why + "）"
        out.append(f"    | `{o['id']}` | {want} | {got} | {verdict} |")
    return out + [""]


def section(lang, steps, dropped, sim, fr):
    label = common.LANGS[lang]["label"]
    lo, hi = block_span(steps)
    lines = [HEADING, "",
             f"規格：`.scratch/credit-store-switch/spec.md`；票 `.scratch/credit-store-switch/issues/{TICKET[lang]}`。", "",
             f"- **新結構**（第 {lo}–{hi} 步）：收取信用照舊 → **重複區段 ×{common.ROUNDS}**"
             f"｛**分岔 {len(PRIORITY)} 個分支**，分岔結尾「跳出到此 → 再往外跳一層」｝→ 導航 → 公開招募。",
             f"  - 每個分支：找圖 `採購_X`〔由上到下第 1、比色〕→ 點擊，點到確認圖（購買物品）出現，"
             "逾時 1.5 秒 → **跳出**；之後的購買步驟照原本的寫法原樣複製："
             f"{tail_text(steps)}。",
             "  - 分岔每輪截一張圖、23 張依序找（本機一輪約 3.2–3.5 秒，所以每輪實際只比對一張截圖）；"
             "畫面上同時有好幾種商品時走排在最前面的分支。買完一件回到下一輪重看畫面。"
             "同一種商品有好幾格時一格一格買，固定先買由上到下第 1 個（同列取左邊）。",
             "  - **結束購買**（跳出整個重複區段，接著導航 → 公開招募）：畫面上已沒有還沒售罄的白名單商品"
             "（分岔逾時，這一輪約 3.3 秒）、點了商品沒出現購買物品（買不起）、獲得物資等不到。最多 10 輪（一頁 10 張卡）。",
             "  - 已售罄的卡不會被點：新範本在自己的售完卡上都不匹配（粗篩就擋掉）；售罄斜帶在獲得物資彈窗消失前就蓋上，"
             "剛買的卡不會被當成還能買。",
             "- **優先順序**（分支順序，繁中、簡中相同）："
             + "、".join(f"{i}. {n}" for i, n in enumerate(PRIORITY, 1)) + "。",
             "- **比色**：商品全部開比色（只差顏色的初級／基礎作戰記錄才分得開）；**例外：技巧概要·卷2 不開**"
             "——它在 demo6 上比色 0.94，差門檻 0.95 一點會找不到；卷1 範本在卷2 卡上粗篩只有 0.49，不開比色也不會認錯。",
             "- **代價：買不起就結束**。排前面的商品買不起時，後面便宜的也不會買（分岔記不住「這件買不起」，"
             "要做得另外設計）。使用者接受這個代價換取結構簡單。",
             f"- **範本**：新增採購中心範本 23 張（`oCam Video/採購中心範本/{common.LANGS[lang]['folder']}/`，"
             "名稱一律 `採購_X`、去掉 `待重拍_` 前綴"
             + ("，簡中流程也用繁體名" if lang == "cn" else "") + "）。"
             f"不再有步驟引用而移出存檔的舊商品範本：{'、'.join(dropped) or '無'}。"
             "購買物品、獲得物資、收取信用照留。存檔裡每個步驟引用的範本都在存檔內（讀回檢查過）。",
             "- **驗證**（腳本在 `.scratch/credit-store-switch/`）："]
    lines += sim_lines(sim)
    lines += frame_lines(fr)
    lines += ["- **已知風險**：",
              f"  - 沒在真畫面上驗證過的商品（{label}）：{'、'.join(UNVERIFIED[lang])}。實跑時特別留意這幾種有沒有漏買或點錯。"]
    if lang == "cn":
        lines.append("  - 簡中碳素只在 demo1 測過，而且全部失敗（低位元率）；簡中待重拍的幾張（加急許可、招聘許可、裝置、"
                     "赤金、初級／基礎作戰記錄、碳素）都只在 demo1 上失敗，實際畫面沒有壓縮。")
    lines += ["  - 第一輪若在商店頁還沒載好時截圖，會直接判定沒商品、結束購買。前面收取信用分岔的 3 秒逾時"
              "或彈窗處理，應已足夠等頁面載好。",
              "  - 買不起就結束（見上）。",
              "  - 獲得物資彈窗還在時，剛買商品的範本會比到彈窗中央的獎勵圖示（0.80–0.96，比色也過）；"
              "每輪都等「獲得物資」確定消失才找下一件，這個誤匹配和獲得物資範本在同一格或更早消失，邊際約 1 格"
              "（使用者決定不另加等待）。實跑若點到彈窗中央，查 `autoclick.log` 的 `find.target`。",
              "  - 傢俱零件和其他偶爾上架、沒有範本的商品不買。",
              f"- 修改前的備份：`{common.BACKUP}`（`arknights/flows/{BACKUP_FLOW[lang]}.autoclickpack` 是改之前的版本）",
              "- 建構腳本：`.scratch/credit-store-switch/build.py --lang " + lang + "`（可重跑）", ""]
    return lines


def replace_section(text, heading_re, new_lines, before_first_h2=False):
    """把 heading_re 那一節 (到下一個 `## ` 為止) 換成 new_lines; 沒有就插入.

    插入位置: before_first_h2＝第一個 `## ` 之前; 否則檔尾。
    """
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


def removed_templates(lang, steps_refs):
    """備份裡改之前的流程引用、現在不再引用的範本."""
    old = os.path.join(common.ROOT, common.BACKUP, "arknights", "flows",
                       BACKUP_FLOW[lang] + flowfile.EXT)
    before = set(flowfile.flow_refs(flowfile.read(old)["data"]))
    return sorted(before - steps_refs)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=sorted(common.LANGS), required=True)
    ap.add_argument("--flow", help="流程名 (預設依語系)")
    args = ap.parse_args(argv)

    path = common.flow_path(args.lang, args.flow)
    md = os.path.splitext(path)[0] + ".md"
    data = flowfile.read(path)["data"]
    steps = data["steps"]
    res = os.path.join(common.HERE, "results")
    with open(os.path.join(res, f"sim_{args.lang}.json"), encoding="utf-8") as f:
        sim = json.load(f)
    with open(os.path.join(res, f"frames_{args.lang}.json"), encoding="utf-8") as f:
        fr = json.load(f)
    name = os.path.basename(path)
    for what, r in (("sim", sim), ("frames", fr)):
        if r["flow"] != name:
            raise SystemExit(f"{what} 結果是 {r['flow']} 的, 不是 {name}: 先重跑驗證")

    dropped = removed_templates(args.lang, set(flowfile.flow_refs(data)))
    with open(md, encoding="utf-8") as f:
        text = f.read()
    text = replace_section(text, re.escape(HEADING), section(args.lang, steps, dropped,
                                                             sim, fr), before_first_h2=True)
    text = replace_section(text, r"## 步驟清單", step_table(steps) + [""])
    with open(md, "w", encoding="utf-8") as f:
        f.write(text.rstrip("\n") + "\n")
    print(f"已更新 {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
