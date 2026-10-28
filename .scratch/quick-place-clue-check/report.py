from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys

import clue
import frames
from clue import bp

import flowfile  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "bp_report", os.path.join(clue.SCRATCH, "busy-pause-fixed-rect", "report.py"))
r05 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r05)

DATE = "2026-10-09"
HEADING = f"## {DATE}：快速置入前先查 1–7 號線索"
STEPS_HEADING = f"## 步驟清單（{DATE} 快速置入前先查線索後更新）"


def _results(lang):
    out = {}
    for kind in ("labels", "build", "check", "frames", "sim"):
        p = os.path.join(clue.RESULTS, f"{kind}_{lang}.json")
        if not os.path.isfile(p):
            raise SystemExit(f"缺 {p}: 先跑對應的腳本 (--lang {lang})")
        with open(p, encoding="utf-8") as f:
            out[kind] = json.load(f)
    return out


def step_table(steps):
    import app
    lines = [STEPS_HEADING, "", "| # | 步驟 | 內容 |", "|---|---|---|"]
    for i, s in enumerate(steps, 1):
        lines.append(f"| {i} | {s['type']} | {app.step_desc(s)} |")
    return lines


def _frames_lines(rep):
    out = [f"    - {line}" for line in frames.tally(rep)]
    cur = [x for x in rep["rows"] if x["cursor"]]
    out.append(f"    - 游標壓在圖上的影格不算數（實跑找圖前會先移開游標）：{len(cur)} 筆，"
               "都是「該找到」的。")
    return out


def section(lang, res, steps):
    cfg = clue.LANGS[lang]
    tw = lang == "tw"
    lay = clue.new_layout(steps, lang)
    no = lambda i: i + 1  # noqa: E731
    r0, r1 = lay["recv"]
    a, b = lay["check"]
    la, lb = lay["leftover"]
    u0 = lay["unlock"][0]
    label = clue.LABEL[lang]
    other = next(n for n in cfg["labels"] if n != label)
    ls = res["labels"]["summary"]
    sims = res["sim"]["results"]
    checks = res["check"]
    flow_ok = all(x["ok"] for x in checks["flow"])
    quick = "快速置入" + ("" if tw else "（按鈕字是「快捷置入」）")
    lines = [
        HEADING, "",
        f"規格：`.scratch/quick-place-clue-check/spec.md`；票 `.scratch/quick-place-clue-check/issues/"
        f"{'02-tw' if tw else '01-cn'}-clue-check.md`；影片 `oCam Video/{cfg['video']}.mp4`"
        f"（{'繁中最大化' if tw else '簡中視窗'}）。", "",
        "- **為什麼**：以前的規則是「線索板下方顯示交流中就不按快速置入，否則就按」。10/08 早班 `早_繁中` "
        "畫面明明在交流中，分岔第一輪卻走了快速置入；而且沒在交流時手上的線索也不一定湊得齊 1–7 號，"
        "湊不齊時按下去只放一部分。改成照使用者的手動做法：開線索面板逐號看，7 號都有才按。"
        "另外接收好友線索以前排在最後，當天收到的要隔天才用得到，改成先收。",
        f"- **改了什麼**（步驟 {cfg['steps']} → {len(steps)}）：",
        f"  - 「接收{'線索' if tw else '线索'} → 全部收取 → 關彈窗」那個分岔整段搬到「領取」後面"
        f"（第 {no(r0)}–{no(r1)} 步），內容不變。",
        f"  - 刪掉「交流中／快速置入」分岔（改前第 {cfg['receive_no'] + 1}–{cfg['receive_no'] + 5} 步）；"
        "交流中範本沒人用了，存檔裡也拿掉。",
        f"  - 第 {no(lay['open'])} 步：點線索板右下角 CONFIDENTIAL「{'線索' if tw else '线索'}」鈕打開面板，"
        f"點到面板標記「{cfg['marker']}」出現（逾時 {clue.OPEN_TIMEOUT}s→跳過）。新開的面板預設就在「全部」分頁。",
        f"  - 第 {no(a)}–{no(b)} 步：檢查區段（一個分岔，條件是面板標記，找到時把原點設在它上面）。"
        "1→7 號每一號兩步：",
        f"    - 點 N 號篩選鈕（相對面板標記的座標、不更新原點，7 號共用同一個原點），點到「{cfg['selected'].format('N')}」"
        f"（白底實心的 N 號鈕）出現；沒出現照補做規則再點，{clue.PICK_TIMEOUT} 秒還沒出現→**跳出**。",
        f"    - 找清單第一格的卡片標籤「{label}」→ 僅等待出現（{clue.CARD_TIMEOUT} 秒內沒看到→**跳出**＝這號沒有，不往下查）。",
        f"    - 7 號都過了：點面板左邊的線索板空白處關面板（點到面板標記離開原位），再按{quick}"
        f"（這步跟改前一字不差）。",
        f"  - 第 {no(la)}–{no(lb)} 步：跳出後補關面板——面板標記 {clue.LEFTOVER_TIMEOUT} 秒內還看得到就點同一個空白處關掉，"
        "看不到就跳過。",
        f"  - 第 {no(u0)} 步起：解鎖線索分岔、回線索板的入口、傳遞線索照舊（編號往後挪）。",
        f"- **新範本**（都從 {cfg['video']} 裁，各配固定矩形）：{cfg['open']}（開面板鈕）、{cfg['marker']}"
        f"（面板開著的標記）、{label}（卡片標籤）、{clue.selected_name(lang, 1)}–{clue.selected_name(lang, 7)}"
        "（選中的篩選鈕）。卡片標籤在兩個候選之間比過："
        f"「{label}」有卡片 {ls[label]['pos_min']}–{ls[label]['pos_max']}、沒卡片最高 {ls[label]['neg_best']}；"
        f"「{other}」有卡片 {ls[other]['pos_min']}–{ls[other]['pos_max']}、沒卡片最高 {ls[other]['neg_best']}"
        + ("，兩個一樣穩，跟簡中版一致" if tw else
           "（游標斜壓在標籤上時「相关搜集者」會掉到 0.67 找不到，「来自」較穩）")
        + f"，採用「{label}」。",
        "- **走向**：",
        "  - 7 號都有：依序點 1–7（每號第一輪就看到卡片），關面板，按快速置入；後面解鎖線索找得到就點。",
        f"  - 第 N 號沒有（清單是「{'暫無線索' if tw else '暂无线索'}」）或判不出來：點到 N 號就停，關面板，**不按**；"
        "後面解鎖線索找不到、約 2 秒跳過，傳遞線索照做。判不出來一律當成沒有——出錯只會少按一次，不會誤按。",
        "  - 篩選鈕點了沒選中：補做；一直沒選中也當成沒有、不按。",
        "- **驗證**：",
        f"  - **真引擎＋影格**（`frames.py`，{cfg['video']} 每 3 幀，arknights 門檻、實機搜尋範圍的畫布）："
        f"{'全部符合' if res['frames']['ok'] else '**有不符**'}——",
        *_frames_lines(res["frames"]),
        f"  - **無頭執行器**（`sim.py`，假畫面＋虛擬時鐘；片段＝第 {res['sim']['slice'][0]}–{res['sim']['slice'][1]} 步，"
        "接收分岔到傳遞關閉；線索板模擬器的鈕、卡片、面板邊界都照影片的位置擺，流程的相對座標要真的點得到）："
        f"{sum(x['ok'] for x in sims)}/{len(sims)} 個劇本符合預期，每個劇本都先接收才開面板、最後都有傳遞。", "",
        "    | 劇本 | 結果 | 點了什麼 |",
        "    |---|---|---|",
    ]
    for x in sims:
        lines.append(f"    | {x['title']} | {'通過' if x['ok'] else '**不符**'} | {x['note'].split('；')[0]}；"
                     f"{x['note'].split('；')[1]} |")
    draft = checks.get("draft")
    lines += [
        "",
        f"  - **讀回檢查**（`check.py`）：{'全部通過' if flow_ok else '**有不通過**'}——新步驟逐欄位照規格、"
        "接收分岔搬過來一字不差、交流中分岔已刪、其他步驟依序原封不動、流程層級設定不變、新範本都在、"
        "舊範本（交流中以外）一字不差、區段完整"
        + ("；草稿與工作區和存檔相同。" if draft and all(x["ok"] for x in draft) else
           f"（草稿屬於別份存檔 `{checks.get('draft_owner', '')}`，沒動）。" if not draft else
           "；**草稿與存檔不同**。"),
        "- **實跑看什麼**（`autoclick.log`）：",
        f"  - 接收分岔（第 {no(r0 + 1)} 步起）的紀錄在開面板（第 {no(lay['open'])} 步）之前。",
        f"  - 第 {no(a + 2)}、{no(a + 4)}、…、{no(a + 14)} 步（點 1–7 號）各一筆 `input.confirm mode=appear`："
        "`result=found` 是選中了，`inputs` 是點了幾下（1＝第一下就生效）；`timeout`＝一直沒選中。",
        f"  - 第 {no(a + 3)}、{no(a + 5)}、…、{no(a + 15)} 步（卡片標籤）各一筆 `find.target`：`found` 是有卡片、"
        "`timeout` 是這號沒有（就停在這號）。停的號碼要跟當天畫面上缺的那號一致。",
        f"  - 湊齊時第 {no(a + 17)} 步快速置入有點、之後解鎖線索找得到；缺號時第 {no(la + 1)} 步補關面板有找到面板標記並關掉。",
        "- **已知風險**：",
        f"  - 卡片標籤用「{label}」：兩支影片裡每張卡都有，但沒看過所有種類的卡片；萬一某種卡沒有這個標籤，"
        "那一號會被當成沒有、不按（只少按，不誤按）。",
        "  - 選中的篩選鈕、面板標記都只在影片上驗過，還沒在實機截圖上驗。座標點擊的 `input.confirm` 只記"
        "點了幾下、不記分數；實跑若某號一直 `timeout`，要另外截當時的畫面驗那張範本。",
        "  - 確認選中 N 號之後馬上看卡片：影片裡每一次換號，篩選鈕和清單都在同一幀換好（影格驗證的「換號那一刻」"
        "每號都查過），所以不會看到上一號的卡片。萬一實機某次清單比篩選鈕晚換，空號可能被誤判成有；"
        "實跑若缺號卻按了快速置入，查那號卡片標籤的 `find.target`。",
        f"  - 關面板點的是面板左邊的線索板空白處（影片 {cfg['close_at']}）；面板滑出後不會再補做"
        "（補做前先看面板標記還在不在）。",
        "  - 花的時間（無頭執行器的虛擬時間，整段接收到傳遞，不含遊戲本身的反應）："
        + "、".join(f"{x['title']} {x['t_end']} 秒" for x in sims[:3]) + "。實機每一步還要加遊戲反應時間。",
        f"- **步驟清單**：本報告最後的步驟清單照新編號重產；前面各段寫的步驟編號仍是當時的"
        f"（第 {no(r0)} 步以後的編號都變了）。",
        f"- 修改前的備份：`app/dist/{os.path.basename(clue.BACKUP)}/`" if res["build"].get("backup")
        else "- 修改前的備份：（試跑目錄，沒有備份）",
        f"- 腳本（`.scratch/quick-place-clue-check/`，都可重跑，`--lang {lang}`）：裁範本 `crop.py`；"
        "建構 `build.py`（`--apply` 寫回）；真引擎影格 `frames.py`；無頭執行器 `sim.py`；讀回檢查 `check.py`；"
        "本報告 `report.py`。結果在 `results/`，範本原圖在 `templates/`。", "",
    ]
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=sorted(clue.LANGS), required=True)
    ap.add_argument("--flows", default=bp.FLOWS)
    args = ap.parse_args(argv)
    cfg = clue.LANGS[args.lang]
    res = _results(args.lang)
    path = bp.flow_path(cfg["flow"], args.flows)
    md = os.path.splitext(path)[0] + ".md"
    steps = flowfile.read(path)["data"]["steps"]
    if not clue.is_new(steps, args.lang) or len(steps) != res["build"]["steps"]:
        raise SystemExit(f"{cfg['flow']}: 存檔跟建構結果不同, 先重跑 build.py --apply")
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
