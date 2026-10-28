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

MARGIN = 40
SPREAD = 8
NEAR = 450
MIN_HITS = 3
PER_TEMPLATE = 6
LOW_BITRATE = {"demo1"}

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
CARD_PAD = (130, 140, 130, 120)


def _center(b):
    return (b[0] + b[2] / 2, b[1] + b[3] / 2)


def _union(boxes):
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return (x0, y0, x1 - x0, y1 - y0)


def clusters(entries):
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
    out = [(tuple(v[2:6]), "video") for v in rec.get("video", [])]
    for v in rec.get("log", []):
        box = tuple(v[1:5])
        if (abs(box[2] - size[0]) <= max(2, 0.12 * size[0])
                and abs(box[3] - size[1]) <= max(2, 0.12 * size[1])):
            out.append((box, "log"))
    return out


def kept_clusters(groups):
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
    r = common.video_box_to_rect(box, lang, region, MARGIN)
    if not grid:
        return dict(r, y=0.0, h=1.0)
    cell = findtarget.limit_rect({"limit": {"kind": "grid", "cells": grid}},
                                 tuple(region), None)
    g = findtarget.ratio_rect_from_screen(cell, tuple(region))
    return dict(r, y=g["y"], h=g["h"])


def plan(lang, r, positions):
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
    lim = tgt.get("limit") or {}
    if p is None or p["rect"] is None or lim.get("kind") == "origin":
        return None
    if p["rect"] == "list":
        col = list_rect(p["box"], lang, region,
                        lim.get("cells") if lim.get("kind") == "grid" else None)
        if lim.get("kind") == "rect":
            col.update(y=lim["y"], h=lim["h"])
        return col
    return dict(p["rect"])


def rebuild(steps, plans, lang, region):
    out, changes = [], []
    for i, s in enumerate(steps):
        s = json.loads(json.dumps(s))
        for key, tgt in findtarget.step_targets(s):
            if key == findtarget.CONFIRM_TARGET and not findtarget.uses_confirm_target(s):
                continue
            role = "target" if key == findtarget.TARGET else "confirm"
            lim = new_limit(tgt, plans.get(tgt.get("template")), lang, region)
            if lim is None or lim == tgt.get("limit"):
                continue
            changes.append((i + 1, role, tgt["template"], tgt.get("limit"), lim))
            tgt["limit"] = lim
        out.append(s)
    return out, changes


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def pick_frames(rec, k, box):
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
    if lim is None:
        return True
    return (lim[0] <= box[0] and box[0] + box[2] <= lim[0] + lim[2]
            and lim[1] <= box[1] and box[1] + box[3] <= lim[1] + lim[3])


def timed_find(tgt, hub, canvas, org):
    t0 = time.perf_counter()
    f = findtarget.find(tgt, hub, canvas, org, origin=None, scale=1.0)
    return f, (time.perf_counter() - t0) * 1000


def verify_templates(lang, hub, steps, new_steps, positions, plans, frames, place):
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
            if not picks:
                rows.append({"template": b["template"], "limit": b["limit"],
                             "no_frames": True, "ok": True})
            for v in picks:
                video, n, x, y, w, h = v[:6]
                canvas, org = place(frames.get(video, n))
                before, ms_before = timed_find(a, hub, canvas, org)
                after, ms_after = timed_find(b, hub, canvas, org)
                ox, oy = common.LANGS[lang]["offset"]
                want = (before.picked.center if before.picked is not None
                        else (x + ox + w // 2, y + oy + h // 2))
                tol = vtf_verify.position_tolerance((0, 0, w, h))
                d = _dist(after.picked.center, want) if after.picked is not None else None
                inside = before.picked is not None and _inside(before.picked.box, after.limit)
                rows.append({"template": b["template"], "limit": b["limit"],
                             "video": video, "frame": n,
                             "old_found": before.picked is not None,
                             "new_found": after.picked is not None,
                             "dist": None if d is None else round(d, 1),
                             "tol": round(tol, 1),
                             "score": None if after.picked is None else round(after.picked.score, 3),
                             "ms_old": round(ms_before), "ms_new": round(ms_after),
                             "outside": before.picked is not None and not inside,
                             "valid": inside,
                             "ok": not inside or (d is not None and d <= tol)})
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
        rows.append({"frame": fr["id"], "video": fr["source"]["video"],
                     "old": po and [po[0], po[1], list(po[2])],
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
    for x in trows + prows:
        x["low_bitrate"] = x.get("video") in LOW_BITRATE
    for x in [x for x in trows + prows if not x["ok"]]:
        print(f"  [{lang}] 不符{'（demo1 低位元率，不算）' if x['low_bitrate'] else ''}: {x}")
    bad = [x for x in trows + prows if not x["ok"] and not x["low_bitrate"]]
    outside = [x for x in trows if x.get("outside")]
    for x in outside:
        print(f"  [{lang}] 加框前挑到的在框外 (不算): {x['template']} {x['video']} #{x['frame']}")
    have = {x["template"] for x in trows if x.get("valid")}
    no_valid = sorted({x["template"] for x in trows} - have)
    valid_rows = [x for x in trows if x.get("valid")]
    ms = lambda rows, k: round(sum(x[k] for x in rows) / len(rows)) if rows else None  # noqa: E731
    if no_valid:
        print(f"  [{lang}] 沒有可驗的影格 (影片上沒有, 或加框前引擎也找不到)：{'、'.join(no_valid)}")
    print(f"[{lang}] 範本驗證 {sum(x['ok'] for x in valid_rows)}/{len(valid_rows)}；"
          f"平均查詢 {ms(valid_rows, 'ms_old')} → {ms(valid_rows, 'ms_new')} ms")
    print(f"[{lang}] 商品分岔 {sum(x['ok'] for x in prows)}/{len(prows)}；"
          f"一輪 23 個分支 {ms(prows, 'ms_old')} → {ms(prows, 'ms_new')} ms")
    report = {"flow": os.path.basename(path), "plans": plans,
              "changes": [list(c) for c in changes], "templates": trows,
              "products": prows, "no_valid": no_valid, "ok": not bad,
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
