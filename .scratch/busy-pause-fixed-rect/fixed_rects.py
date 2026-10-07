"""票 08: 早班兩版加固定矩形 (見 issues/08-morning-fixed-rects.md).

    .venv/Scripts/python.exe .scratch/busy-pause-fixed-rect/fixed_rects.py [--lang cn|tw] [--apply]

先跑 measure.py (results/positions_<lang>.json: 每張範本在參考影片與實跑日誌上的位置)。

每張範本的框 (影片座標, 再換成搜尋範圍的比例, common.video_box_to_rect):
- 位置固定 (fixed): 影格與實跑日誌的出現位置依中心分群 (±SPREAD px)。以實機日誌的位置為主
  (沒有日誌就用影片上最大的那群), 再加上離主位置 NEAR px 內、影片上至少 MIN_HITS 次的群
  (例如別的彈窗的叉叉、待辦項目點掉一個後往左移之前的位置); 框＝這些位置的聯集外擴 MARGIN。
  太遠的群 (別的畫面上長得像的東西, 例如商店頁的收取) 照列出來、不框。日誌只算跟範本同尺寸的框
  (晚班流程有同名但不同圖的範本)。沒有任何出現紀錄就不加。
- 換班清單的列名與訪問基建 (LIST): 會隨捲動上下移, 左右不動 → 一整欄: 左右＝出現位置的聯集
  外擴 MARGIN, 上下＝整個搜尋範圍; 原本限定九宮格上 2/3 的 (別點到畫面最底下) 上下照舊。
- 採購的 23 個商品 (PRODUCT): 共用一個商品區框＝標註影格的卡片圓心範圍外擴 (採購中心範本的
  annotations.json)。
- 不加 (EXCLUDE): 位置隨基建地圖縮放平移的 (會客室、製造站卡片)、以原點為基準的首列、
  忙碌指示、已有固定矩形的交流中、校準對。
步驟上的套法: 找圖目標與確認圖都套; 以原點為基準的限定範圍不動; 其他 (不限定、九宮格) 換成框。

驗證 (接縫三, 真引擎、arknights 門檻, 影格換成實機搜尋範圍的畫布):
- 每張加框的範本挑最多 PER_TEMPLATE 張出現在框裡的影格, 加框前、加框後的找圖目標各執行一次:
  加框前找得到的影格 (有效影格), 加框後也要找得到、挑到的位置跟加框前一樣 (容許值內);
  加框前就找不到的 (轉場、比色擋掉的別列…) 不算數; 加框前挑到的位置在框外的 (例如線索板滑到一半)
  另列出來, 也不算數。兩次的查詢時間都記下 (平均只算有效影格)。
  沒有任何有效影格的範本照實列出。
- 商品: 採購中心標註影格上, 23 個分支依序判定, 加框前後走的分支與挑到的位置要一樣。
- demo1 (低位元率) 影格上的不符照實列出、不算失敗 (同採購分岔的驗證)。
結果寫 results/fixed_rects_<lang>.json; --apply 驗證全過才寫回 (先備份、讀回驗證、草稿同步)。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time

import common

import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402
from automation.runner import branch_layout  # noqa: E402
from video_to_flow import verify as vtf_verify  # noqa: E402

MARGIN = 40            # 外擴 (影片像素)
SPREAD = 8             # 位置固定: 中心彼此差不超過 (px)
NEAR = 450            # 離主位置多遠以內的群算同一個步驟會出現的位置 (px)
MIN_HITS = 3           # 只在影片上出現的群至少幾次才算 (轉場中途的零星匹配不算)
PER_TEMPLATE = 6
LOW_BITRATE = {"demo1"}   # 0.5 Mbps: 範本分數本來就壓在門檻邊上, 不符照實列出、不算失敗 (同採購分岔的驗證)

EXCLUDE = {
    "cn": {"会客室", "制造中", "制造站首列", "贸易站首列", "忙碌指示", "交流中",
           "標題列圖示", "標題列關閉鈕"},
    "tw": {"會客室", "生產面板箭頭", "製造站首列", "貿易站首列", "忙碌指示", "交流中",
           "標題列圖示", "標題列關閉鈕"},
}
LIST = {
    "cn": {"製造站1列", "貿易站1列", "发电站1列", "办公室列", "访问基建"},
    "tw": {"製造站1列", "貿易站1列", "發電站1列", "辦公室列", "訪問基建"},
}
PRODUCT_PREFIX = "採購_"
ANNOTATIONS = os.path.join(common.ROOT, ".scratch", "credit-store-templates",
                           "annotations.json")
FRAMES_DIR = os.path.join(common.ROOT, ".scratch", "credit-store-templates", "frames")
CARD_PAD = (130, 140, 130, 120)    # 卡片圓心範圍外擴: 左、上、右、下 (影片像素)


# ================= 決定框 =================

def _center(b):
    return (b[0] + b[2] / 2, b[1] + b[3] / 2)


def _union(boxes):
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return (x0, y0, x1 - x0, y1 - y0)


def clusters(entries):
    """把出現紀錄依中心分群 (±SPREAD): [{"boxes", "video", "log", "center"}], 大的在前."""
    groups = []
    for box, src in entries:
        c = _center(box)
        for g in groups:
            if abs(g["center"][0] - c[0]) <= SPREAD and abs(g["center"][1] - c[1]) <= SPREAD:
                g["boxes"].append(box)
                g[src] += 1
                break
        else:
            groups.append({"center": c, "boxes": [box], "video": 0, "log": 0, src: 1})
    return sorted(groups, key=lambda g: -(g["video"] + g["log"]))


def entries_of(rec, size):
    """影格與日誌的出現紀錄 [(box, "video"|"log")]; 日誌只算跟範本差不多大的框 (±12%:
    引擎估的尺度會讓框差幾 px; 晚班流程有同名但不同圖的範本, 尺寸差很多)."""
    out = [(tuple(v[2:6]), "video") for v in rec.get("video", [])]
    for v in rec.get("log", []):
        box = tuple(v[1:5])
        if (abs(box[2] - size[0]) <= max(2, 0.12 * size[0])
                and abs(box[3] - size[1]) <= max(2, 0.12 * size[1])):
            out.append((box, "log"))
    return out


def kept_clusters(groups):
    """框進去的群: 主位置 (有實機日誌的群; 沒有就影片上最大的那群), 加上離主位置 NEAR px 內、
    影片上至少 MIN_HITS 次的群。其他的 (別的畫面上長得像的東西) 回傳在第二個值。"""
    main = [g for g in groups if g["log"]] or groups[:1]
    keep, drop = [], []
    for g in groups:
        near = any(_dist(g["center"], m["center"]) <= NEAR for m in main)
        if g in main or (near and g["video"] >= MIN_HITS):
            keep.append(g)
        else:
            drop.append(g)
    return keep, drop


def _desc(groups):
    return [{"center": [round(v) for v in g["center"]], "video": g["video"], "log": g["log"]}
            for g in groups]


def decide_fixed(rec, size):
    """位置固定的框 (影片座標) 或 None, 不加的原因, 統計."""
    ent = entries_of(rec, size)
    stats = {"video": sum(1 for e in ent if e[1] == "video"),
             "log": sum(1 for e in ent if e[1] == "log")}
    if not ent:
        return None, "影格與日誌都沒有出現紀錄", stats
    keep, drop = kept_clusters(clusters(ent))
    stats.update(kept=_desc(keep), dropped=_desc(drop))
    return _union([b for g in keep for b in g["boxes"]]), None, stats


def decide_list(rec, size):
    ent = entries_of(rec, size)
    stats = {"video": sum(1 for e in ent if e[1] == "video"),
             "log": sum(1 for e in ent if e[1] == "log")}
    if not ent:
        return None, "影格與日誌都沒有出現紀錄", stats
    xs = [_center(b)[0] for b, _src in ent]
    stats["x_spread"] = round(max(xs) - min(xs), 1)
    if max(xs) - min(xs) > SPREAD:
        return None, f"左右位置不固定 (中心差 {max(xs) - min(xs):.0f}px)", stats
    return _union([b for b, _src in ent]), None, stats


def product_box(lang):
    with open(ANNOTATIONS, encoding="utf-8") as f:
        frames = [fr for fr in json.load(f)["frames"]
                  if fr["set"] == lang and "video" in fr["source"]]
    cs = [c["center"] for fr in frames for c in fr["cards"]]
    l, t, r, b = CARD_PAD
    x0, y0 = min(c[0] for c in cs) - l, min(c[1] for c in cs) - t
    x1, y1 = max(c[0] for c in cs) + r, max(c[1] for c in cs) + b
    return (round(x0), round(y0), round(x1 - x0), round(y1 - y0)), frames


def list_rect(box, lang, region, grid=None):
    """一整欄: 左右照 box 外擴, 上下＝整個搜尋範圍 (原本九宮格限定的就照九宮格的上下)."""
    r = common.video_box_to_rect(box, lang, region, MARGIN)
    if grid:
        rows = [(c - 1) // 3 for c in grid]
        y0, y1 = min(rows) / 3, (max(rows) + 1) / 3
    else:
        y0, y1 = 0.0, 1.0
    return dict(r, y=round(y0, 4), h=round(y1 - y0, 4))


def plan(lang, r, positions):
    """{範本: {"rect": 固定矩形 或 None, "kind", "box", "why", "stats"}}."""
    region = r["data"]["scanRegion"]
    names = findtarget.referenced_templates(r["data"]["steps"])
    pbox, _frames = product_box(lang)
    prect = common.video_box_to_rect(pbox, lang, region, 0)
    out = {}
    for n in names:
        if n in EXCLUDE[lang]:
            out[n] = {"kind": "exclude", "rect": None}
            continue
        if n.startswith(PRODUCT_PREFIX):
            out[n] = {"kind": "product", "rect": prect, "box": pbox}
            continue
        rec = positions.get(n, {})
        img = common.decode(r["images"][n])
        size = (img.shape[1], img.shape[0])
        if n in LIST[lang]:
            box, why, st = decide_list(rec, size)
            kind = "list"
        else:
            box, why, st = decide_fixed(rec, size)
            kind = "fixed"
        rect = None
        if box is not None:
            rect = (common.video_box_to_rect(box, lang, region, MARGIN)
                    if kind == "fixed" else "list")
        out[n] = {"kind": kind, "rect": rect, "box": box, "why": why, "stats": st}
    return out


def new_limit(tgt, p, lang, region):
    """這個找圖目標加框後的限定範圍; 不改回 None."""
    lim = tgt.get("limit") or {}
    if p is None or p["rect"] is None or lim.get("kind") == "origin":
        return None
    if p["rect"] == "list":
        return list_rect(p["box"], lang, region,
                         lim.get("cells") if lim.get("kind") == "grid" else None)
    return dict(p["rect"])


def rebuild(steps, plans, lang, region):
    """回傳 (新 steps, 改了哪些 [(步驟號, 角色, 範本, 舊限定, 新限定)])."""
    out, changes = [], []
    for i, s in enumerate(steps):
        s = json.loads(json.dumps(s))
        for key, role in ((findtarget.TARGET, "target"),
                          (findtarget.CONFIRM_TARGET, "confirm")):
            if key == findtarget.TARGET and s.get("type") != "find_click":
                continue
            if key == findtarget.CONFIRM_TARGET and not findtarget.uses_confirm_target(s):
                continue
            tgt = s.get(key)
            if not tgt:
                continue
            lim = new_limit(tgt, plans.get(tgt.get("template")), lang, region)
            if lim is None or lim == tgt.get("limit"):
                continue
            changes.append((i + 1, role, tgt["template"], tgt.get("limit"), lim))
            tgt["limit"] = lim
        out.append(s)
    return out, changes


# ================= 驗證 (真引擎) =================

def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def pick_frames(rec, k, box):
    """出現在框裡的影格挑 k 張: 盡量分散到不同影片、不同時間."""
    x0, y0, w, h = box
    vids = [v for v in rec.get("video", [])
            if x0 <= v[2] and v[2] + v[4] <= x0 + w and y0 <= v[3] and v[3] + v[5] <= y0 + h]
    by = {}
    for v in vids:
        by.setdefault(v[0], []).append(v)
    picks = []
    while len(picks) < k and any(by.values()):
        for video in list(by):
            lst = by[video]
            if not lst:
                continue
            j = (len(picks) * 7919) % len(lst) if len(picks) else len(lst) // 2
            picks.append(lst.pop(j))
            if len(picks) >= k:
                break
    return picks


def _inside(box, lim):
    """box 整個在限定矩形 lim 裡 (lim 是 None＝整個搜尋範圍)."""
    if lim is None:
        return True
    return (lim[0] <= box[0] and box[0] + box[2] <= lim[0] + lim[2]
            and lim[1] <= box[1] and box[1] + box[3] <= lim[1] + lim[3])


def timed_find(tgt, hub, canvas, org):
    t0 = time.perf_counter()
    f = findtarget.find(tgt, hub, canvas, org, origin=None, scale=1.0)
    return f, (time.perf_counter() - t0) * 1000


def verify_templates(lang, hub, steps, new_steps, positions, plans, frames, place):
    """每張加了框的範本 (以步驟上的找圖目標為準, 一種設定驗一次)."""
    rows = []
    done = set()
    for s_old, s_new in zip(steps, new_steps):
        for key in (findtarget.TARGET, findtarget.CONFIRM_TARGET):
            a, b = s_old.get(key), s_new.get(key)
            if not a or not b or a == b:
                continue
            sig = json.dumps(b, sort_keys=True)
            if sig in done or b["template"].startswith(PRODUCT_PREFIX):
                continue
            done.add(sig)
            if findtarget.needs_origin(b):
                continue
            picks = pick_frames(positions.get(b["template"], {}), PER_TEMPLATE,
                                plans[b["template"]]["box"])
            if not picks:    # 只有實機日誌的紀錄, 影片上沒有 (照實列出)
                rows.append({"template": b["template"], "limit": b["limit"],
                             "no_frames": True, "ok": True})
            for v in picks:
                video, n, x, y, w, h = v[:6]
                canvas, org = place(frames.get(video, n))
                fo, to = timed_find(a, hub, canvas, org)
                fn, tn = timed_find(b, hub, canvas, org)
                ox, oy = common.LANGS[lang]["offset"]
                want = (fo.picked.center if fo.picked is not None
                        else (x + ox + w // 2, y + oy + h // 2))
                tol = vtf_verify.position_tolerance((0, 0, w, h))
                d = _dist(fn.picked.center, want) if fn.picked is not None else None
                rows.append({"template": b["template"], "limit": b["limit"],
                             "video": video, "frame": n,
                             "old_found": fo.picked is not None,
                             "new_found": fn.picked is not None,
                             "dist": None if d is None else round(d, 1),
                             "tol": round(tol, 1),
                             "score": None if fn.picked is None else round(fn.picked.score, 3),
                             "ms_old": round(to), "ms_new": round(tn),
                             # 加框前就找不到 (轉場、比色擋掉的別列…) 的影格不算數;
                             # 加框前挑到的在框外 (轉場中途的位置) 另列
                             "outside": fo.picked is not None and not _inside(fo.picked.box, fn.limit),
                             "valid": fo.picked is not None and _inside(fo.picked.box, fn.limit),
                             "ok": (fo.picked is None or not _inside(fo.picked.box, fn.limit)
                                    or (d is not None and d <= tol))})
    return rows


def verify_products(lang, hub, steps, new_steps, place):
    _box, frames = product_box(lang)

    def conds(st):
        i = next(k for k, s in enumerate(st) if s.get("type") == "find_click"
                 and findtarget.template(s).startswith(PRODUCT_PREFIX))
        bs = max(k for k in range(i) if st[k].get("type") == "branch_start")
        segs, _end = branch_layout(st, bs)
        return [findtarget.target(st[s]) for s in segs]

    old, new = conds(steps), conds(new_steps)
    rows = []
    for fr in frames:
        img = common.read_img(os.path.join(FRAMES_DIR, fr["id"] + ".png"))
        canvas, org = place(img)
        res = {}
        for tag, tg in (("old", old), ("new", new)):
            t0 = time.perf_counter()
            pick = None
            for k, t in enumerate(tg):
                f = findtarget.find(t, hub, canvas, org, origin=None, scale=1.0)
                if f.picked is not None:
                    pick = (k + 1, t["template"], f.picked.center)
                    break
            res[tag] = (pick, (time.perf_counter() - t0) * 1000)
        po, pn = res["old"][0], res["new"][0]
        ok = (po is None and pn is None) or (
            po is not None and pn is not None and po[0] == pn[0]
            and _dist(po[2], pn[2]) <= 3)
        rows.append({"frame": fr["id"], "old": po and [po[0], po[1], list(po[2])],
                     "new": pn and [pn[0], pn[1], list(pn[2])],
                     "ms_old": round(res["old"][1]), "ms_new": round(res["new"][1]),
                     "ok": ok})
    return rows


def run_lang(lang, args, frames):
    path = common.flow_path(common.LANGS[lang]["flow"], args.flows)
    r = flowfile.read(path)
    with open(os.path.join(common.RESULTS, f"positions_{lang}.json"), encoding="utf-8") as f:
        positions = json.load(f)
    region = r["data"]["scanRegion"]
    plans = plan(lang, r, positions)
    steps = r["data"]["steps"]
    new_steps, changes = rebuild(steps, plans, lang, region)
    err = common.section_error(new_steps)
    if err:
        raise SystemExit(f"[{lang}] 區段不完整: {err}")
    for n, p in plans.items():
        if p["kind"] in ("fixed", "list") and p["rect"] is None:
            print(f"  [{lang}] 不加框：{n}（{p['why']}；{p['stats']}）")
    print(f"[{lang}] {len(changes)} 處找圖目標加框；載入引擎…", flush=True)
    names = findtarget.referenced_templates(steps)
    tmp = tempfile.mkdtemp(prefix="fixed_rects_")
    place = common.frame_region(lang, region)
    try:
        hub = common.make_hub(r["images"], [n for n in names if n in r["images"]], tmp)
        trows = verify_templates(lang, hub, steps, new_steps, positions, plans, frames, place)
        prows = verify_products(lang, hub, steps, new_steps, place)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for x in trows:
        x["low_bitrate"] = x.get("video") in LOW_BITRATE
    for x in prows:
        x["low_bitrate"] = x["frame"].split("_")[1] in LOW_BITRATE
    for x in [x for x in trows + prows if not x["ok"]]:
        print(f"  [{lang}] 不符{'（demo1 低位元率，不算）' if x['low_bitrate'] else ''}: {x}")
    bad = [x for x in trows + prows if not x["ok"] and not x["low_bitrate"]]
    outside = [x for x in trows if x.get("outside")]
    for x in outside:
        print(f"  [{lang}] 加框前挑到的在框外 (不算): {x['template']} {x['video']} #{x['frame']}")
    have = {x["template"] for x in trows if x.get("valid")}
    nof = sorted({x["template"] for x in trows} - have)
    trows_f = [x for x in trows if x.get("valid")]
    ms = lambda rows, k: round(sum(x[k] for x in rows) / len(rows)) if rows else None  # noqa: E731
    if nof:
        print(f"  [{lang}] 沒有可驗的影格 (影片上沒有, 或加框前引擎也找不到)：{'、'.join(nof)}")
    print(f"[{lang}] 範本驗證 {sum(x['ok'] for x in trows_f)}/{len(trows_f)}；"
          f"平均查詢 {ms(trows_f, 'ms_old')} → {ms(trows_f, 'ms_new')} ms")
    print(f"[{lang}] 商品分岔 {sum(x['ok'] for x in prows)}/{len(prows)}；"
          f"一輪 23 個分支 {ms(prows, 'ms_old')} → {ms(prows, 'ms_new')} ms")
    report = {"flow": os.path.basename(path), "plans": plans,
              "changes": [list(c) for c in changes], "templates": trows,
              "products": prows, "no_valid": nof, "ok": not bad,
              "outside": [{k: x[k] for k in ("template", "video", "frame")} for x in outside]}
    return report, (path, r, new_steps)


def apply(path, r, new_steps, flows):
    if new_steps == r["data"]["steps"]:
        print(f"{os.path.basename(path)}: 已是新版, 不動")
        return
    data = dict(r["data"], steps=new_steps)
    back = common.write_flow(path, data, r["images"], r["pos"])
    if back["data"]["steps"] != new_steps:
        raise SystemExit("讀回的步驟與寫入的不同")
    print(f"{os.path.basename(path)}: 已寫回")
    if common.sync_draft(path, os.path.dirname(flows)):
        print("    草稿與工作區已同步")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--lang", choices=sorted(common.LANGS), action="append")
    ap.add_argument("--flows", default=common.FLOWS)
    args = ap.parse_args(argv)
    langs = args.lang or sorted(common.LANGS)
    frames = common.Frames()
    reports, built = {}, {}
    try:
        for lang in langs:
            reports[lang], built[lang] = run_lang(lang, args, frames)
    finally:
        frames.close()
    for lang in langs:
        with open(os.path.join(common.RESULTS, f"fixed_rects_{lang}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(reports[lang], f, ensure_ascii=False, indent=1)
    bad = [lang for lang in langs if not reports[lang]["ok"]]
    if args.apply and not bad:
        common.preflight(args.flows, common.ticket_backup("08"))
        for lang in langs:
            apply(*built[lang], args.flows)
    print("通過" if not bad else f"**不通過**: {'、'.join(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
