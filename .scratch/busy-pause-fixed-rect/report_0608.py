"""票 06–08 的交付報告: 早_簡中、早_繁中的 .md 各加一節、重產步驟清單.

    .venv/Scripts/python.exe .scratch/busy-pause-fixed-rect/report_0608.py [--flows 目錄]

先跑 tw_busy.py、quick_place.py、fixed_rects.py (結果從 results/*.json 讀)。可以重跑:
各節與步驟清單整段換掉, 報告其他段落不動。新的一節放在最前面 (由舊到新插入, 08 在最上面)。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import common
import report as r05

import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402

DATE = "2026-10-07"
H06 = f"## {DATE}：繁中忙碌指示重截"
H07 = f"## {DATE}：快速置入看線索板狀態"
H08 = f"## {DATE}：位置固定的圖加固定矩形"
STEPS_HEADING = f"## 步驟清單（{DATE} 固定矩形後更新）"
LANG_OF = {"早_簡中": "cn", "早_繁中": "tw"}


def load(name):
    p = os.path.join(common.RESULTS, name)
    if not os.path.isfile(p):
        raise SystemExit(f"缺 {p}: 先跑對應的腳本")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def backup_name(ticket):
    return os.path.basename(common.ticket_backup(ticket))


def section06(res):
    new, old = res["results"]["新"]["summary"], res["results"]["舊"]["summary"]
    src = res["source"]

    def s(d, k):
        x = d[k]
        rng = f"，分數 {x['score_min']}–{x['score_max']}" if x["found"] else ""
        return f"{x['found']}/{x['n']} 找到{rng}（平均 {x['ms_avg']} ms）"
    return [H06, "",
            f"- **新範本**：從 `oCam Video/{src['video']}.mp4` 第 {src['frame']} 幀（好友訪問時底部的"
            f"「正在提交反饋至神經……」）裁到只剩字，框 {tuple(src['crop'])}（影片＝實機座標）。"
            "名稱與限定範圍（九宮格 8、9）不變。",
            "- **舊範本的問題**：是從 demo3 第 852 幀附近裁的，那幾幀忙碌字樣底下疊著另一段淡出中的提示字，"
            "裁下來是兩層字的殘影。",
            "- **驗證（真引擎、arknights 門檻，限定範圍照流程設定）**：",
            f"  - 有忙碌的影格（demo2，抽樣）：新 {s(new, 'busy')}；舊 {s(old, 'busy')}。",
            f"  - 疊字的影格（demo3 第 850–858 幀）：新 {s(new, 'busy_overlap')}；舊 {s(old, 'busy_overlap')}。",
            f"  - 沒忙碌的影格（demo2、demo3 每 25 幀）：新 {s(new, 'idle')}（最高分 {new['idle']['best_max']}）；"
            f"舊 {s(old, 'idle')}（最高分 {old['idle']['best_max']}）。",
            "- **注意：舊範本在影片上其實也比得到**（上面的數字）。10/07 實跑繁中全部 not_appeared、"
            "最高約 0.19，比較可能是那幾次點完 ⇌ 後 1 秒內根本沒出現忙碌（伺服器回得快），"
            "不一定是範本壞掉；實機位置跟影片完全一致（例如進駐總覽兩邊都是 (206,150)）。"
            "換成新範本是為了不靠運氣（沒有殘影），實跑時請看日誌 `busy_pause`／`busy_delay` 有沒有數值。",
            "- 晚_繁中用的是同一張舊範本，這次沒有換（規格不含晚班）；要換請說。",
            f"- 修改前的備份：`app/dist/{backup_name('06')}/`",
            "- 腳本：`.scratch/busy-pause-fixed-rect/tw_busy.py`（可重跑；`--apply` 才寫回）", ""]


def section07(lang, res, steps):
    r = res[lang]
    at = r.get("at")
    s = r["summary"]
    src = r["source"]

    def line(kind, label):
        x = s[kind]
        extra = ""
        if x["score"]:
            extra = f"（分數 {x['score'][0]}–{x['score'][1]}"
            extra += (f"、比色 {x['color'][0]}–{x['color'][1]}" if x["color"] else "") + "）"
        if x["best_when_not_found"] is not None:
            extra += f"；沒找到時最高分 {x['best_when_not_found']}"
        return f"  - {label}：{x['ok']}/{x['n']} 符合{extra}"
    word = "线索交流开启中" if lang == "cn" else "線索交流開啟中"
    rect = findtarget.limit_text(r["rect"])
    no = f"第 {at}–{at + 4} 步" if at else "快速置入那一步"
    return [H07, "",
            f"- **改了什麼**：{no}：原本無條件找快速置入來按，改成一個分岔——"
            f"分支 1「交流中〔固定矩形、比色〕→ 僅等待出現（逾時 1.5s→跳過）」，後面不接步驟；"
            "分支 2 是原本的快速置入步驟原樣搬進來（比色、偏移、逾時都不變）。"
            "兩個同時成立時走排在前面的分支 1，所以**線索交流進行中時不按快速置入**；沒在交流才照舊按。"
            "解鎖線索以後的步驟不動。",
            f"- **採用「交流中」，沒走退路（0/7）**。範本：線索板底部中間「{word}」字樣左邊不會動的那段"
            f"（橘線末端＋第一個字），從 `{src['video']}.mp4` 第 {src['frame']} 幀裁，框 {tuple(src['crop'])}"
            "（影片座標）。字樣中間壓著一個會轉的圓環（圓點繞圈、外圈脈動），所以不截整串字。",
            f"- 固定矩形：{rect}（範本框四周外擴 40px）。",
            "- **驗證（真引擎、arknights 門檻，影格換成實機搜尋範圍的畫布、找圖目標照存檔設定）**：",
            line("exchange", "交流中的線索板（分岔走分支 1）"),
            line("board_idle", "沒在交流的線索板（含 0/7；不走分支 1）"),
            line("other", "其他畫面（每 40 幀；交流中找不到）"),
            line("transition", "轉場中（線索板淡入、接收線索面板拉開、忙碌圖示蓋住；只記錄、不計分）"),
            "- **已知風險**：線索板剛淡入的那幾幀，快速置入已經是橘色、交流中的比色還沒過，"
            "這時判定會走分支 2。流程走到這裡前已在線索板上點過每日線索、領取（板子早就穩定），"
            "所以照理碰不到；實跑若交流中還是按了快速置入，查日誌這一步分岔的 `find.target`。",
            f"- 修改前的備份：`app/dist/{backup_name('07')}/`",
            "- 腳本：`.scratch/busy-pause-fixed-rect/quick_place.py`（可重跑；`--apply` 才寫回）", ""]


def section08(lang, res):
    plans = res["plans"]
    added = sorted(n for n, p in plans.items() if p["rect"] is not None
                   and p["kind"] in ("fixed", "list"))
    skipped = sorted((n, p.get("why")) for n, p in plans.items()
                     if p["kind"] in ("fixed", "list") and p["rect"] is None)
    excluded = sorted(n for n, p in plans.items() if p["kind"] == "exclude")
    product = next((p for n, p in plans.items() if p["kind"] == "product"), None)
    t = [x for x in res["templates"] if x.get("valid")]
    pr = res["products"]

    def avg(rows, k):
        return round(sum(x[k] for x in rows) / len(rows)) if rows else 0
    lines = [H08, "",
             f"- **加了框的範本**（{len(added)} 張，共 {len(res['changes'])} 處找圖目標／確認圖）："
             + "、".join(added) + "。",
             "  - 位置固定的圖：影格與實跑日誌上的出現位置分群（中心差 ≤8px 算同一處）。以實機日誌的位置為主"
             "（沒有日誌就用影片上最大的那群），加上離它 450px 內、影片上至少 3 次的位置"
             "（例如別的彈窗的叉叉、待辦項目往左移之前的位置）；框＝這些位置的聯集外擴 40px。"
             "離得更遠的（別的畫面上長得像的東西，例如商店頁右上角也比得到「領取」）不框。",
             "  - 換班清單的列名、訪問基建：會隨捲動上下移，框是一整欄（左右外擴 40px、上下整個畫面；"
             "原本限定畫面上 2/3 的照舊只看上 2/3）。",
             ]
    if product:
        lines.append(f"  - 採購的 23 個商品共用一個商品區框：{findtarget.limit_text(product['rect'])}"
                     "（標註影格上卡片圓心的範圍外擴）。")
    lines += ["  - 確認圖（例如購買物品、獲得物資、待辦事項）也一起套。"
              "以原點為基準的（各「首列」）不動；原本九宮格的換成更緊的框。",
              "- **沒加框**：",
              "  - 位置會隨基建地圖縮放、平移的，以及本來就有自己限定範圍的：" + "、".join(excluded) + "。"]
    for n, why in skipped:
        lines.append(f"  - {n}：{why}。")
    lines += ["- **驗證（真引擎、arknights 門檻，影格換成實機搜尋範圍的畫布）**：",
              f"  - 每張加框的範本在它出現在框裡的影格上（最多 6 張，分散在不同影片）加框前後各找一次；"
              f"加框前找得到的 {len(t)} 張裡，{sum(x['ok'] for x in t)} 張加框後也找得到、位置跟加框前一樣"
              "（加框前就找不到的轉場、比色擋掉的別列不算）。"
              f"平均查詢 {avg(t, 'ms_old')} ms → {avg(t, 'ms_new')} ms。",
              *([f"  - 沒有可驗的影格（影片上沒出現在框裡，或加框前引擎也找不到）："
                 + "、".join(res["no_valid"]) + "。"] if res.get("no_valid") else []),
              *[f"  - 不符（demo1 低位元率，照實列出、不算失敗）：{x['template']} {x['video']} 第 {x['frame']} 幀"
                "——加框前分數就壓在門檻邊上，裁圖後深度驗證分數降到門檻下"
                f"（兩版所有有效影格加框前後的分數差中位數是 0，這是唯一明顯下降的一張）。"
                for x in t if not x["ok"]],
              *([("  - 加框前挑到的位置在框外（轉場中途，例如線索板滑到一半；不算）："
                  + "、".join(f"{x['template']} {x['video']} 第 {x['frame']} 幀" for x in res["outside"]) + "。")]
                if res.get("outside") else []),
              f"  - 採購分岔：{sum(x['ok'] for x in pr)}/{len(pr)} 張標註商店影格加框前後走同一個分支、挑同一格；"
              f"一輪 23 個分支依序判定 {avg(pr, 'ms_old')} ms → {avg(pr, 'ms_new')} ms。", "",
              "  | 範本 | 有效影格 | 加框前平均 ms | 加框後平均 ms | 結果 |", "  |---|---|---|---|---|"]
    by = {}
    for x in t:
        by.setdefault(x["template"], []).append(x)
    for n, rows in by.items():
        okn = sum(x["ok"] for x in rows)
        lines.append(f"  | {n} | {len(rows)} | {avg(rows, 'ms_old')} | {avg(rows, 'ms_new')} | "
                     + ("通過" if okn == len(rows) else f"{okn}/{len(rows)}（不符見上）") + " |")
    lines += ["",
              *(["- **簡中「接收线索」引擎本來就找不到**：加框前後在影片上都找不到，10/07 實機也逾時（最高 0.587）。"
                 "這是原本就有的問題（範本對不上），不是加框造成的；框照影片上的位置加。"] if lang == "cn" else []),
              "- 查詢時間是在 CPU 被其他程式佔滿時量的，同一組數字兩次跑可以差到一倍，只能前後相比。",
              "- **變快多少**：單次查詢大約省三到四成，不是「幾乎瞬間」——引擎每次查詢有固定開銷"
              "（深度驗證），不隨搜尋區域變小而消失。換班、採購每輪實際快多少，要看實跑（票 09，"
              "10/07 簡中：換班找到貿易站到點箭頭約 3 秒、採購一輪約 10 秒）。",
              "- **已知風險**：框是從現有影格與實跑日誌量的。別天位置變了（例如活動彈窗換版面、商店多一排），"
              "那一步會找不到而逾時；實跑發現就放寬那一個框（步驟編輯 → 限定範圍 → 固定矩形 → 重新框選）。",
              f"- 修改前的備份：`app/dist/{backup_name('08')}/`",
              "- 腳本：`.scratch/busy-pause-fixed-rect/measure.py`（量位置）、`fixed_rects.py`"
              "（決定框、驗證；`--apply` 才寫回），都可重跑", ""]
    return lines


def step_table(steps):
    lines = r05.step_table(steps)
    lines[0] = STEPS_HEADING
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--flows", default=common.FLOWS)
    args = ap.parse_args(argv)
    tw = load("tw_busy.json")
    qp = load("quick_place.json")
    for name in common.MORNING:
        lang = LANG_OF[name]
        fr = load(f"fixed_rects_{lang}.json")
        path = common.flow_path(name, args.flows)
        md = os.path.splitext(path)[0] + ".md"
        steps = flowfile.read(path)["data"]["steps"]
        with open(md, encoding="utf-8") as f:
            text = f.read()
        if name == "早_繁中":
            text = r05.replace_section(text, re.escape(H06), section06(tw), before_first_h2=True)
        text = r05.replace_section(text, re.escape(H07), section07(lang, qp, steps),
                                   before_first_h2=True)
        text = r05.replace_section(text, re.escape(H08), section08(lang, fr),
                                   before_first_h2=True)
        text = r05.replace_section(text, r"## 步驟清單", step_table(steps) + [""])
        with open(md, "w", encoding="utf-8") as f:
            f.write(text.rstrip("\n") + "\n")
        print(f"已更新 {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
