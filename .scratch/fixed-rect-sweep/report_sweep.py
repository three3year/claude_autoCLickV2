from __future__ import annotations

import json
import os
import re
import sys

import shared
from shared import bp

import flowfile  # noqa: E402
import report as bpr  # noqa: E402
import sweep  # noqa: E402

DATE = "2026-10-09"
HEADING = f"## {DATE}：剩下的全畫面與九宮格換成固定矩形"
STEPS_HEADING = f"## 步驟清單（{DATE} 固定矩形後更新）"
BACKUP_REL = f"app/dist/{os.path.basename(shared.BACKUP)}/"
M = shared.MARGIN

TODO_STEPS = {6, 8, 10}
SEEN = {
    ("cn", 64): "導航選單滑入途中，下一格就到定位",
    ("tw", 64): "導航選單滑入途中，之後幾格就到定位",
    ("tw", 29): "導航選單打開時右上「14名幹員已進駐宿舍」提示的 zz 圖示，長得像、不是按鈕；框掉它正好",
    ("tw", 60): "導航選單打開時右上「14名幹員已進駐宿舍」提示的 zz 圖示，長得像、不是按鈕；框掉它正好",
}


def step_table(steps):
    import app
    lines = [STEPS_HEADING, "", "| # | 步驟 | 內容 |", "|---|---|---|"]
    for i, s in enumerate(steps, 1):
        lines.append(f"| {i} | {s['type']} | {app.step_desc(s)} |")
    return lines


def _box(b):
    return f"({b[0]},{b[1]}) {b[2]}×{b[3]}"


def _pct(r):
    return (f"({r['x'] * 100:.1f}%,{r['y'] * 100:.1f}%) "
            f"{r['w'] * 100:.1f}%×{r['h'] * 100:.1f}%")


def _ms(x):
    return "—" if x["ms_old"] is None else f"{x['ms_old']} → {x['ms_new']}"


def _avg(rows, key):
    return round(sum(y[key] for y in rows) / len(rows))


def _video(x):
    if x["no_video"]:
        return "影片無對應"
    if x["all_outside"]:
        return f"影片上 {x['video_hits']} 次都在框外"
    valid = [y for y in x["rows"] if y["valid"]]
    return f"{sum(1 for y in valid if y['ok'])}/{len(valid)} 張找得到、位置一樣"


def _note(lang, step):
    if step in TODO_STEPS:
        return "（待辦列後面幾格、補位前的位置）"
    return f"（{SEEN[(lang, step)]}）" if (lang, step) in SEEN else ""


def mismatch_lines(lang, checks):
    out = []
    for x in checks:
        if x.get("shared_with"):
            continue
        where = "忙碌指示" if x["where"] == "busy" else f"第 {x['step']} 步「{x['template']}」"
        if x["where"] == "target" and x["step"] in shared.WIDEN_STEPS:
            out.append(f"  - {where}：兩次實機位置不同（{log_positions(lang, x)}），已併進框（見上）。")
        note = _note(lang, x["step"])
        for g in x["mismatch_groups"]:
            fr = "、".join(f"{v} #{n}" for v, n in g["frames"])
            out.append(f"  - {where}：影片上中心 ({g['center'][0]},{g['center'][1]}) 出現 "
                       f"{g['count']} 次（例如 {fr}），新框 {_box(x['limit_px'])} 裝不下{note}。")
        for v, n, box in x["outside"]:
            c = (box[0] + box[2] / 2, box[1] + box[3] / 2)
            if any(abs(c[0] - g["center"][0]) <= sweep.SPREAD
                   and abs(c[1] - g["center"][1]) <= sweep.SPREAD for g in x["mismatch_groups"]):
                continue
            out.append(f"  - {where}：{v} 第 {n} 幀改前挑到 {_box(box)}，在新框外{note}。")
    return out


def log_positions(lang, x):
    roles = ("confirm_appear",) if x["where"] == "confirm" else shared.FIND_ROLES
    pos = shared.step_positions(lang, x["step"], x["template"], roles)
    if len(pos) == 1:
        return "、".join(_box(b) for b in pos["晚"])
    return "；".join(f"{k} " + "、".join(_box(b) for b in v) for k, v in pos.items())


def busy_lines(lang, x, has_wait_step):
    cfg = shared.LANGS[lang]
    neg = x["negative"]
    pos = [y for y in x["rows"] if y["valid"]]
    lines = [f"- **忙碌指示**（流程層級設定）：九宮格 8、9 → 固定矩形 {_pct(x['new'])}，"
             f"實機 {_box(x['limit_px'])}＝字的位置 {_box(cfg['busy_box'])}（{cfg['busy_src']}）外擴 {M}。"
             f"早晚兩份 {cfg['morning']}、{cfg['evening']} 用同一個框。"]
    if has_wait_step:
        lines.append("  - 第 2 步「忙碌指示 → 等待消失」（開頭清彈窗每一輪先等忙碌消失）用同一個框。")
    vids = sorted({y["video"] for y in x["rows"]})
    lines.append(
        f"  - 驗證：有忙碌字樣的影格（{'、'.join(vids)}）{sum(1 for y in pos if y['ok'])}/{len(pos)} 張"
        f"新框找得到、位置跟改前一樣；沒忙碌的影格（{cfg['video']} 每 {sweep.NEG_STRIDE} 幀）"
        f"{sum(1 for y in neg if y['ok'])}/{len(neg)} 張改前、改後都找不到；"
        f"忙碌字淡入淡出或疊在別的提示字上的 {len(x['negative_skipped'])} 張不算反例。"
        f"單次找圖平均 {_ms(x)} ms。")
    if lang == "tw":
        lines.append("  - **風險**：繁中框是從影片量的，10/08 晚_繁中整輪沒有忙碌，實機還沒驗到。"
                     "框錯不會報錯，只會一直 `busy.check result=not_appeared`；"
                     "之後看到遊戲真的在轉圈，要查日誌那一步有沒有 `gone`。")
    return lines


def evening_section(lang, res, name):
    cfg = shared.LANGS[lang]
    checks = [x for x in res["checks"] if x["flow"] == name]
    busy = next(x for x in checks if x["where"] == "busy")
    steps = [x for x in checks if x["where"] != "busy"]
    area = res["list_area"]
    widen = [x for x in steps if x["where"] == "target" and x["step"] in shared.WIDEN_STEPS]
    lines = [HEADING, "",
             f"規格：`.scratch/fixed-rect-sweep/spec.md`；票 `.scratch/fixed-rect-sweep/issues/{cfg['ticket']}`"
             "（忙碌指示是票 01）。只改流程存檔，app 沒改、不用重新打包。", "",
             f"- **為什麼**：晚班有 {len(shared.FIXED_STEPS) + len(shared.LIST_STEPS)} 個找圖目標在整個畫面找、"
             "待辦事項與忙碌指示用九宮格；範圍越大每次找圖越慢，也越容易把別處相似的東西當成目標。",
             f"- **位置固定的圖**：框＝{cfg['run'][:16]} 實跑日誌該步實際找到的位置（`picked`）"
             f"外擴 {M} 像素（實機螢幕座標），換成搜尋範圍的比例。同一張範本出現在多步的（例如返回、進駐總覽），"
             "各步用自己那一步的位置。",
             f"- **換班清單的列名**：左右＝該列名在這次日誌所有出現位置（含比色擋掉的別列）的左右範圍外擴 {M}；"
             f"上下＝換班清單顯示區 y {area['screen'][0]}–{area['screen'][1]}（實機）："
             f"在晚班影片 {cfg['video']} 有列名的 {area['clip_video']['frames']} 張影格上量——"
             f"上緣是清單捲動時被切掉的那條線（影片 y {area['clip_video']['top']}），下緣是畫面底；"
             "這次日誌裡列名的所有出現位置都在這個範圍裡。捲到哪都找得到，左右框死不會找到旁邊欄位的同款字。"]
    for x in widen:
        lines.append(
            f"- **{x['template']}（第 {x['step']} 步）多併一個位置**：10/08 同一天兩次實機位置就不同"
            f"（{log_positions(lang, x)}），差距超過外擴的 {M} 像素，只照晚班那次框，下次很可能逾時、整段待辦沒收。"
            f"所以框＝晚班與同一天早班實跑（同一張圖、同尺寸）的位置聯集外擴 {M}。"
            "**這一步偏離規格「以今晚日誌為準、不自動放大框」，待使用者核可**；要照規格改回，"
            "把 `shared.WIDEN_STEPS` 清空重跑 `sweep.py --apply`。兩個樣本就差 50 多像素，"
            "聯集也不保證涵蓋第三種位置。其他步驟早晚兩次實機位置一致（差幾像素內）。")
    lines += ["- **沒動**：第 18 步（位置隨基建地圖縮放、平移）、以原點為基準的各首列、"
              "已經是固定矩形的第 1 步關公告。", ""]
    lines += busy_lines(lang, busy, False)
    lines += ["", "- **加框的步驟**（步驟編號不變；日誌位置與新框都是實機螢幕座標）：", "",
              "  | 步驟 | 範本 | 改前 | 日誌位置 | 新框 | 影片驗證 | 單次找圖 ms（改前 → 改後） |",
              "  |---|---|---|---|---|---|---|"]
    for x in steps:
        role = "（確認圖）" if x["where"] == "confirm" else ""
        old = "九宮格 7" if x["old"] else "全畫面"
        logpos = "—" if x["kind"] == "list" else log_positions(lang, x)
        lines.append(f"  | {x['step']} | {x['template']}{role} | {old} | {logpos} | "
                     f"{_box(x['limit_px'])} | {_video(x)} | {_ms(x)} |")
    valid = [y for x in steps for y in x["rows"] if y["valid"]]
    lines += ["", f"- **驗證（真引擎、arknights 門檻，影格換成實機搜尋範圍的畫布）**：每個改過的找圖目標在"
                  f"晚班影片 {cfg['video']} 上這張範本出現的影格挑最多 {sweep.PER} 張，改前、改後各找一次。"
                  f"改前找得到且在新框裡的 {len(valid)} 張，改後 {sum(1 for y in valid if y['ok'])} 張找得到、"
                  f"位置一樣；平均單次找圖 {_avg(valid, 'ms_old')} → {_avg(valid, 'ms_new')} ms。"
                  "量的時候明日方舟和其他程式同時在跑、CPU 忙，同一組數字兩次跑可以差到一倍，只能前後相比。"]
    lst = [y for x in steps if x["kind"] == "list" for y in x["rows"] if y["valid"]]
    fix = [y for x in steps if x["kind"] != "list" for y in x["rows"] if y["valid"]]
    if fix:
        o, n = _avg(fix, "ms_old"), _avg(fix, "ms_new")
        lines.append(f"  - 位置固定的步驟 {len(fix)} 張平均 {o} → {n} ms（省 {round((1 - n / o) * 100)}%）。")
    if lst:
        lines.append(
            f"  - 換班列名 {len(lst)} 張平均 {_avg(lst, 'ms_old')} → {_avg(lst, 'ms_new')} ms：框成一整欄後"
            "**沒有變快**（列名比色、同畫面多個匹配都要深度驗證，固定開銷佔大部分）；"
            "這 8 步加框的好處只剩不會找到旁邊欄位的同款字。")
    nov = [f"第 {x['step']} 步「{x['template']}」" for x in steps if x["no_video"]]
    if nov:
        lines.append("- **影片無對應**（影片上沒出現，框只靠日誌）：" + "、".join(nov) + "。")
    out = [f"第 {x['step']} 步「{x['template']}」" for x in steps if x["all_outside"]]
    if out:
        lines.append("- **影片上都在框外、框內沒有可驗的影格**（框只靠日誌）：" + "、".join(out) + "。"
                     "待辦三項在影片上排在待辦列第 2、3 格；實機上前一項點掉後會補位到第一格"
                     "（10/08 實跑三項都在第一格找到），所以只框第一格——這是從實跑推論，影片上沒驗到。")
    mm = mismatch_lines(lang, [busy] + steps)
    lines.append("- **位置不一致**（框以日誌為準，影片的不一致沒有自動放大；括號是看過影格後的判斷；"
                 "實跑若那一步逾時再放寬）：" + ("" if mm else "沒有。"))
    lines += mm
    lines += ["- **實跑看什麼**（`autoclick.log`）：",
              "  - 加框的步驟 `find.target` 的 `limit=` 從 `all` 變成框的實機座標，沒有因框錯而 `result=timeout`。",
              f"  - 總時間跟 2026-10-08 比（{name}約 {cfg['evening_secs']} 秒）。",
              "  - 框錯的那一步：步驟編輯 → 限定範圍 → 固定矩形 → 重新框選，放寬那一個就好。",
              "- **已知風險**：",
              "  - 框是從一次實跑量的；別天位置變了（例如活動換版面），那一步會找不到而逾時。",
              "  - 待辦三項只框了待辦列第一格。待辦點掉一個後其他往左補位，重複區段每一次都會在第一格"
              "找到下一項；若那天第一格是別種待辦（不是這三種），重複區段會提早結束。",
              f"- 修改前的備份：`{BACKUP_REL}`",
              "- 腳本（`.scratch/fixed-rect-sweep/`，都可重跑）：量位置 `positions.py`；決定框＋驗證 `sweep.py`"
              "（`--apply` 才寫回）；本報告 `report_sweep.py`。結果在 `results/sweep_<lang>.json`。", ""]
    return lines


def morning_section(lang, res, name):
    checks = [x for x in res["checks"] if x["flow"] == name]
    busy = next(x for x in checks if x["where"] == "busy")
    has_wait = any(x["where"] == "target" for x in checks)
    lines = [HEADING, "",
             "規格：`.scratch/fixed-rect-sweep/spec.md`；票 `.scratch/fixed-rect-sweep/issues/01-busy-indicator-rects.md`。"
             "這份只改忙碌指示（其他位置固定的圖 10/07 已加框）。", ""]
    lines += busy_lines(lang, busy, has_wait)
    lines += ["- **實跑看什麼**：勾了忙碌檢查的步驟 `busy.check` 照常有 `gone`／`not_appeared`；"
              + ("第 2 步等待消失沒有卡住。" if has_wait else "")
              + "框錯時遊戲在轉圈也只會一直 `not_appeared`。",
              f"- 修改前的備份：`{BACKUP_REL}`",
              "- 腳本：`.scratch/fixed-rect-sweep/sweep.py`（`--apply` 才寫回）、`report_sweep.py`。", ""]
    return lines


def main(argv=None):
    for lang in sorted(shared.LANGS):
        with open(os.path.join(shared.RESULTS, f"sweep_{lang}.json"), encoding="utf-8") as f:
            res = json.load(f)
        if not res["ok"]:
            raise SystemExit(f"[{lang}] 驗證沒過: 不寫報告")
        for which in ("morning", "evening"):
            name = shared.LANGS[lang][which]
            path = bp.flow_path(name)
            data = flowfile.read(path)["data"]
            for c in res["changes"]:
                if c["flow"] == name and shared.target_of(data, c).get("limit") != c["new"]:
                    raise SystemExit(f"{name}: 存檔還沒寫回 (先跑 sweep.py --apply)")
            md = os.path.splitext(path)[0] + ".md"
            with open(md, encoding="utf-8") as f:
                text = f.read()
            sec = (morning_section if which == "morning" else evening_section)(lang, res, name)
            text = bpr.replace_section(text, re.escape(HEADING), sec, before_first_h2=True)
            text = bpr.replace_section(text, r"## 步驟清單", step_table(data["steps"]) + [""])
            with open(md, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"{name}.md: 已更新")
    return 0


if __name__ == "__main__":
    sys.exit(main())
