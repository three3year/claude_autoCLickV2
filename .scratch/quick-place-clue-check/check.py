from __future__ import annotations

import argparse
import json
import os
import sys

import clue
from clue import bp

import flowfile  # noqa: E402

SKIP = ("steps", "flowFormat", flowfile.RETRY_KEY)


def _settings(data):
    return {k: v for k, v in data.items() if k not in SKIP}


def _same_settings(a, b):
    same = (_settings(a) == _settings(b)
            and flowfile.retry_interval_ms(a) == flowfile.retry_interval_ms(b))
    return same, "相同" if same else "不同"


def spec_checks(lang, steps, lay, quick_before):
    cfg = clue.LANGS[lang]
    a, b = lay["check"]
    la, lb = lay["leftover"]
    opn, cond = steps[lay["open"]], steps[a + 1]
    body = steps[a + 2:b]
    pairs = [(body[2 * k], body[2 * k + 1]) for k in range(len(clue.NUMS))]
    close, quick = body[-2], body[-1]
    lcond, lclose = steps[la + 1], steps[la + 2]
    rect = lambda t: (t.get("limit") or {}).get("kind") == "rect"  # noqa: E731
    tg = lambda s: s.get("target") or {}  # noqa: E731
    ct = lambda s: s.get("confirmTarget") or {}  # noqa: E731
    marker = cfg["marker"]
    picks_ok = all(
        p["type"] == "click" and p.get("mode") == "prev" and p.get("updateOrigin") is False
        and p.get("confirm") == "appear" and ct(p).get("template") == clue.selected_name(lang, n)
        and rect(ct(p)) and p.get("onNotFound") == "break"
        and c["type"] == "find_click" and tg(c).get("template") == clue.LABEL[lang] and rect(tg(c))
        and c.get("action") == "none" and c.get("updateOrigin") is False
        and c.get("onNotFound") == "break" and c.get("timeout") <= 1
        for n, (p, c) in zip(clue.NUMS, pairs))
    return [
        ("開面板：找圖點擊開面板鈕，點到面板標記出現",
         tg(opn).get("template") == cfg["open"] and rect(tg(opn)) and opn.get("action") == "click"
         and opn.get("confirm") == "appear" and ct(opn).get("template") == marker,
         f"{tg(opn).get('template')} → {ct(opn).get('template')}"),
        ("檢查區段的條件＝面板標記（僅等待出現、更新原點）",
         tg(cond).get("template") == marker and cond.get("action") == "none"
         and cond.get("updateOrigin") is True and len(body) == 2 * len(clue.NUMS) + 2,
         f"{tg(cond).get('template')}，區段內 {len(body)} 步"),
        ("1–7 號：點篩選鈕（相對座標、不更新原點、確認選中、跳出）＋卡片標籤（僅等待、≤1 秒、跳出）",
         picks_ok, f"卡片標籤＝{clue.LABEL[lang]}"),
        ("區段裡關面板（點面板外、原點的圖離開）後按快速置入（跟改前那步一樣）",
         close["type"] == "click" and close.get("mode") == "prev" and close.get("confirm") == "gone"
         and close.get("x") < 0 and quick == quick_before,
         f"關面板相對 ({close.get('x')},{close.get('y')})"),
        ("補關分岔：面板標記還在才點面板外關掉（短逾時、跳過）",
         tg(lcond).get("template") == marker and lcond.get("onNotFound") == "skip"
         and lcond.get("timeout") <= 1 and lclose.get("confirm") == "gone"
         and (lclose.get("x"), lclose.get("y")) == (close.get("x"), close.get("y")) and lb == la + 3,
         f"條件逾時 {lcond.get('timeout')}s"),
    ]


def check_flow(lang, data, images, orig):
    cfg = clue.LANGS[lang]
    steps, before = data["steps"], orig["data"]["steps"]
    a = clue.locate(before, lang)
    lay = clue.new_layout(steps, lang)
    rb, re_ = a["recv"]
    ub = a["unlock"][0]
    receive, unlock_entry = before[rb:re_ + 1], before[ub:a["entry"] + 1]
    mine = clue.check_steps(lang, orig["data"]["scanRegion"], before[a["quick"]])
    g = lay["get"]
    head, tail = steps[:g + 1], steps[g + 1:]
    want_mid = receive + mine + unlock_entry
    mid = tail[:len(want_mid)]
    rest = tail[len(want_mid):]
    new_names = clue.new_template_names(lang)
    want_imgs = clue.load_templates(lang)
    old_kept = {n for n in orig["images"] if n != cfg["chat"]}
    chat_gone = not any(clue.template_of(s) == cfg["chat"] for s in steps)
    first_new = g + 1 + len(receive)
    return spec_checks(lang, steps, lay, before[a["quick"]]) + [
        ("領取之前的步驟不變", head == before[:a["get"] + 1], f"{len(head)} 步"),
        ("接收分岔搬到領取之後、一字不差", mid[:len(receive)] == receive,
         f"第 {g + 2}–{g + 1 + len(receive)} 步"),
        ("新步驟照規格", mid[len(receive):len(receive) + len(mine)] == mine,
         f"第 {first_new + 1}–{first_new + len(mine)} 步（{len(mine)} 步）"),
        ("檢查區段與補關分岔的位置", (lay["open"], lay["check"][0], lay["leftover"][1])
         == (first_new, first_new + 1, first_new + len(mine) - 1),
         f"開面板 {lay['open'] + 1}、檢查 {lay['check'][0] + 1}–{lay['check'][1] + 1}、"
         f"補關 {lay['leftover'][0] + 1}–{lay['leftover'][1] + 1}"),
        ("解鎖分岔與線索入口接在後面、一字不差", mid[len(receive) + len(mine):] == unlock_entry,
         f"解鎖 {lay['unlock'][0] + 1}、入口 {lay['entry'] + 1}"),
        ("交流中分岔已刪", chat_gone and cfg["chat"] not in images, "已刪" if chat_gone else "還在"),
        ("其他步驟依序原封不動", rest == before[re_ + 1:], f"後面 {len(rest)} 步"),
        ("步驟數", len(steps) == len(before) - (a["chat"][1] - a["chat"][0] + 1) + len(mine),
         f"{len(before)} → {len(steps)}"),
        ("流程層級設定不變", *_same_settings(data, orig["data"])),
        ("新範本都在、跟裁的一樣", all(images.get(n) == want_imgs[n] for n in new_names),
         "、".join(new_names)),
        ("舊範本 (交流中以外) 都在、一字不差",
         all(images.get(n) == orig["images"][n] for n in old_kept)
         and set(images) == old_kept | set(new_names),
         f"{len(old_kept)} + {len(new_names)} = {len(images)} 張"),
        ("區段完整", bp.section_error(steps) is None, bp.section_error(steps) or "完整"),
    ]


def check_draft(flow, draft, ws_images):
    data = flow["data"]
    return [
        ("草稿步驟與存檔相同", draft["steps"] == data["steps"],
         "相同" if draft["steps"] == data["steps"] else "不同"),
        ("草稿設定與存檔相同", *_same_settings(draft, data)),
        ("工作區範本與存檔相同", ws_images == flow["images"], f"{len(ws_images)} 張"),
    ]


def _ws_images(profile):
    out = {}
    for n, p in flowfile.Workspace(profile).images().items():
        with open(p, "rb") as f:
            out[n] = f.read()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=sorted(clue.LANGS), required=True)
    ap.add_argument("--flows", default=bp.FLOWS)
    ap.add_argument("--orig", default=clue.BACKUP_FLOWS, help="改動前的流程資料夾 (預設本功能的備份)")
    args = ap.parse_args(argv)
    cfg = clue.LANGS[args.lang]
    path = bp.flow_path(cfg["flow"], args.flows)
    profile = os.path.dirname(args.flows)
    flow = flowfile.read(path)
    orig = flowfile.read(bp.flow_path(cfg["flow"], args.orig))
    res = {"orig": args.orig, "flow": check_flow(args.lang, flow["data"], flow["images"], orig)}
    owner = bp.current_flow(profile)
    if owner == os.path.normcase(os.path.abspath(path)):
        draft = flowfile.read_draft(profile)
        res["draft"] = (check_draft(flow, draft, _ws_images(profile)) if draft
                        else [("草稿", False, "讀不到")])
    else:
        res["draft_owner"] = os.path.basename(owner or "")
    bad = []
    for kind, title in (("flow", f"存檔（對 {args.orig}）"), ("draft", "草稿＋工作區")):
        if kind not in res:
            continue
        print(f"== {cfg['flow']} {title}")
        for item, ok, note in res[kind]:
            print(f"  {'OK ' if ok else 'NG '} {item}：{note}")
            if not ok:
                bad.append((kind, item))
    if "draft" not in res:
        print(f"  （草稿屬於別份存檔：{res['draft_owner'] or '沒有'}，不動）")
    os.makedirs(clue.RESULTS, exist_ok=True)
    with open(os.path.join(clue.RESULTS, f"check_{args.lang}.json"), "w", encoding="utf-8") as f:
        json.dump({k: v if not isinstance(v, list) else
                   [{"item": a, "ok": b, "note": c} for a, b, c in v]
                   for k, v in res.items()}, f, ensure_ascii=False, indent=1)
    print("讀回檢查通過" if not bad else f"**不通過**：{bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
