from __future__ import annotations

import argparse
import functools
import json
import os
import shutil
import sys
import tempfile

import shared
from shared import bp

import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402
from video_to_flow import verify as vtf_verify  # noqa: E402
import fixed_rects as fr  # noqa: E402

PER = 6
NEG_STRIDE = 25
NEAR_BUSY = 15
IDLE = 0.5
SPREAD = 8
LOW_BITRATE = {"demo1"}


def _need(cond, msg):
    if not cond:
        raise SystemExit(msg)


def orig_flows():
    return shared.BACKUP_FLOWS if os.path.isdir(shared.BACKUP_FLOWS) else bp.FLOWS


def list_area(lang, positions):
    clip, oy = positions["list_clip"], shared.offset(lang)[1]
    return (clip["top"] + oy, clip["bottom"] + oy)


def list_rect(boxes, lang, region, area):
    y0, y1 = area
    out = [b for b in boxes if b[1] < y0 or b[1] + b[3] > y1]
    _need(not out, f"[{lang}] 日誌裡的列名在清單區 y {y0}–{y1} 外: {out}")
    x0 = min(b[0] for b in boxes) - shared.MARGIN
    x1 = max(b[0] + b[2] for b in boxes) + shared.MARGIN
    box = (x0, y0, x1 - x0, y1 - y0)
    r = findtarget.ratio_rect_from_screen(box, tuple(region))
    _need(r is not None, f"[{lang}] 列名框在搜尋範圍外")
    return r, box


def _change(name, where, step, role, template, old, new, box, kind):
    return {"flow": name, "where": where, "step": step, "role": role, "template": template,
            "old": old, "new": new, "box": box, "kind": kind}


def plan(lang, which, r, positions):
    data = r["data"]
    region = tuple(data["scanRegion"])
    name = shared.LANGS[lang][which]
    busy = flowfile.busy_target(data)
    _need(busy and busy["template"] == shared.BUSY
          and busy.get("limit") == {"kind": "grid", "cells": [8, 9]},
          f"{name}: 忙碌指示不是九宮格 8、9: {busy}")
    brect = shared.busy_rect(lang, region)
    bbox = shared.grow(shared.LANGS[lang]["busy_box"])
    out = [_change(name, "busy", None, "busy", shared.BUSY, busy["limit"], brect, bbox, "busy")]
    steps = data["steps"]
    if which == "morning":
        for i, s in enumerate(steps):
            if bp.is_busy_wait(s, busy):
                _need(s["target"].get("limit") == busy["limit"],
                      f"{name} 第 {i + 1} 步: 等待消失的限定範圍跟忙碌指示不同")
                out.append(_change(name, "target", i + 1, "wait_gone", shared.BUSY,
                                   s["target"].get("limit"), brect, bbox, "busy"))
        if lang == "cn":
            _need([x["step"] for x in out if x["where"] == "target"] == [2],
                  f"{name}: 「忙碌指示 → 等待消失」應該只有第 2 步")
        return out
    area = list_area(lang, positions)
    finds = shared.run_finds(lang)
    for n in shared.FIXED_STEPS + shared.LIST_STEPS:
        s = steps[n - 1]
        tgt = findtarget.target(s)
        _need(s["type"] == "find_click" and tgt.get("limit") is None,
              f"{name} 第 {n} 步不是全畫面的找圖: {s['type']} {tgt.get('limit')}")
        tpl = tgt["template"]
        picks = [b for v in shared.step_positions(lang, n, tpl).values() for b in v]
        if n in shared.LIST_STEPS:
            rect, box = list_rect([b for f in finds if f["template"] == tpl for b in f["boxes"]],
                                  lang, region, area)
            kind = "list"
        else:
            box = shared.grow(fr._union(picks))
            rect, kind = shared.screen_rect(fr._union(picks), region), "fixed"
        out.append(_change(name, "target", n, "find", tpl, None, rect, box, kind))
    n = shared.CONFIRM_STEP
    ct = findtarget.confirm_target(steps[n - 1])
    _need(findtarget.uses_confirm_target(steps[n - 1])
          and ct.get("limit") == {"kind": "grid", "cells": [7]},
          f"{name} 第 {n} 步的確認圖不是九宮格 7: {ct}")
    picks = shared.step_positions(lang, n, ct["template"], ("confirm_appear",))["晚"]
    out.append(_change(name, "confirm", n, "confirm_appear", ct["template"], ct["limit"],
                       shared.screen_rect(fr._union(picks), region),
                       shared.grow(fr._union(picks)), "fixed"))
    return out


def rebuild(data, changes):
    data = json.loads(json.dumps(data))
    for c in changes:
        shared.target_of(data, c)["limit"] = dict(c["new"])
    return data


def diff_limits(a, b):
    out = []
    ka, kb = dict(a), dict(b)
    ba, bb = ka.pop(flowfile.BUSY_KEY, None), kb.pop(flowfile.BUSY_KEY, None)
    sa, sb = ka.pop("steps"), kb.pop("steps")
    _need(ka == kb, "流程層級設定 (忙碌指示以外) 不同")
    if ba != bb:
        _need(ba is not None and bb is not None
              and dict(ba, limit=None) == dict(bb, limit=None), "忙碌指示除了限定範圍還有別的不同")
        out.append(("busy", None, "limit"))
    _need(len(sa) == len(sb), "步數不同")
    for i, (x, y) in enumerate(zip(sa, sb)):
        if x == y:
            continue
        x, y = json.loads(json.dumps(x)), json.loads(json.dumps(y))
        for key in (findtarget.TARGET, findtarget.CONFIRM_TARGET):
            if key in x and key in y and x[key] != y[key]:
                out.append(("step", i + 1, key))
                x[key].pop("limit", None)
                y[key].pop("limit", None)
        _need(x == y, f"第 {i + 1} 步除了限定範圍還有別的不同")
    return out


def _where(c):
    if c["where"] == "busy":
        return ("busy", None, "limit")
    key = findtarget.TARGET if c["where"] == "target" else findtarget.CONFIRM_TARGET
    return ("step", c["step"], key)


def spread(items, k):
    by = {}
    for v in items:
        by.setdefault(v[0], []).append(v)
    picks = []
    per = -(-k // max(1, len(by)))
    for lst in by.values():
        lst.sort(key=lambda v: v[1])
        n = min(per, len(lst))
        picks += [lst[(j * len(lst)) // n + len(lst) // (2 * n)] for j in range(n)]
    return picks[:k]


def clusters(lang, vids):
    ox, oy = shared.offset(lang)
    groups = []
    for v in vids:
        b = (v[2] + ox, v[3] + oy, v[4], v[5])
        c = (b[0] + b[2] / 2, b[1] + b[3] / 2)
        for g in groups:
            if abs(g["c"][0] - c[0]) <= SPREAD and abs(g["c"][1] - c[1]) <= SPREAD:
                g["frames"].append([v[0], v[1]])
                g["boxes"].append(b)
                break
        else:
            groups.append({"c": c, "frames": [[v[0], v[1]]], "boxes": [b]})
    return groups


def compare(hub, old_t, new_t, frame_list, frames, place):
    rows = []
    for v in frame_list:
        video, n, _x, _y, w, h = v[:6]
        canvas, org = place(frames.get(video, n))
        before, ms_before = fr.timed_find(old_t, hub, canvas, org)
        after, ms_after = fr.timed_find(new_t, hub, canvas, org)
        tol = vtf_verify.position_tolerance((0, 0, w, h))
        pick = before.picked
        valid = pick is not None and fr._inside(pick.box, after.limit)
        d = (None if pick is None or after.picked is None
             else round(fr._dist(after.picked.center, pick.center), 1))
        rows.append({"video": video, "frame": n,
                     "old": None if pick is None else list(pick.box),
                     "new": None if after.picked is None else list(after.picked.box),
                     "score": None if after.picked is None else round(float(after.picked.score), 3),
                     "dist": d, "tol": round(tol, 1),
                     "ms_old": round(ms_before), "ms_new": round(ms_after),
                     "valid": valid,
                     "outside": pick is not None and not valid,
                     "low_bitrate": video in LOW_BITRATE,
                     "ok": not valid or (d is not None and d <= tol)})
    return rows


@functools.lru_cache(maxsize=None)
def frame_count(video):
    import cv2
    cap = cv2.VideoCapture(os.path.join(bp.VIDEO_DIR, video + ".mp4"))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return total


def frame_plan(lang, c, positions):
    if c["kind"] != "busy":
        return spread(positions["video"].get(c["template"], []), PER), []
    busy = positions["busy"]
    video = shared.LANGS[lang]["video"]
    near = {(v[0], v[1] + d) for v in busy for d in range(-NEAR_BUSY, NEAR_BUSY + 1)}
    neg = [(video, n) for n in range(0, frame_count(video), NEG_STRIDE) if (video, n) not in near]
    return spread(busy, 3 * PER), neg


def _result(c, lim, rows, vids, lang):
    valid = [x for x in rows if x["valid"]]

    def avg(key):
        return round(sum(x[key] for x in valid) / len(valid)) if valid else None
    return {"flow": c["flow"], "step": c["step"], "where": c["where"], "role": c["role"],
            "template": c["template"], "kind": c["kind"], "box": list(c["box"]),
            "limit_px": list(lim), "new": c["new"], "old": c["old"],
            "rows": rows, "video_hits": len(vids),
            "mismatch_groups": [{"center": [round(v) for v in g["c"]], "count": len(g["frames"]),
                                 "frames": g["frames"][:3]}
                                for g in clusters(lang, vids)
                                if not all(fr._inside(b, lim) for b in g["boxes"])],
            "outside": [[x["video"], x["frame"], x["old"]] for x in rows if x["outside"]],
            "no_video": not vids, "all_outside": bool(vids) and not valid,
            "ms_old": avg("ms_old"), "ms_new": avg("ms_new"),
            "ok": all(x["ok"] or x["low_bitrate"] for x in rows)}


def verify_change(lang, c, hub, r, positions, frames, place):
    old_t = c["target_obj"]
    new_t = dict(old_t, limit=c["new"])
    vids = positions["video"].get(c["template"], [])
    lim = findtarget.limit_rect({"limit": c["new"]}, tuple(r["data"]["scanRegion"]), None)
    rows = compare(hub, old_t, new_t, frame_plan(lang, c, positions)[0], frames, place)
    return _result(c, lim, rows, vids, lang)


def verify_busy(lang, c, hub, r, positions, frames, place):
    import cv2
    old_t = c["target_obj"]
    new_t = dict(old_t, limit=c["new"])
    pos_frames, neg_frames = frame_plan(lang, c, positions)
    pos = compare(hub, old_t, new_t, pos_frames, frames, place)
    tmpl = cv2.cvtColor(bp.decode(r["images"][shared.BUSY]), cv2.COLOR_BGR2GRAY)
    neg, skipped = [], []
    for video, n in neg_frames:
        img = frames.get(video, n)
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corr = float(cv2.matchTemplate(g[g.shape[0] // 2:], tmpl, cv2.TM_CCOEFF_NORMED).max())
        if corr >= IDLE:
            skipped.append([video, n, round(corr, 3)])
            continue
        canvas, org = place(img)
        before, ms_before = fr.timed_find(old_t, hub, canvas, org)
        after, ms_after = fr.timed_find(new_t, hub, canvas, org)
        neg.append({"video": video, "frame": n, "old_found": before.picked is not None,
                    "new_found": after.picked is not None, "ms_old": round(ms_before),
                    "ms_new": round(ms_after),
                    "ok": before.picked is None and after.picked is None})
    lim = findtarget.limit_rect({"limit": c["new"]}, tuple(r["data"]["scanRegion"]), None)
    res = _result(c, lim, pos, positions["busy"], lang)
    res.update(negative=neg, negative_skipped=skipped,
               ok=res["ok"] and not res["all_outside"] and bool(neg)
               and all(x["ok"] for x in neg))
    return res


def run_lang(lang):
    with open(os.path.join(shared.RESULTS, f"positions_{lang}.json"), encoding="utf-8") as f:
        positions = json.load(f)
    built, checks = [], []
    for which in ("morning", "evening"):
        name = shared.LANGS[lang][which]
        r = flowfile.read(os.path.join(orig_flows(), name + flowfile.EXT))
        changes = plan(lang, which, r, positions)
        for c in changes:
            c["target_obj"] = shared.target_of(r["data"], c)
        new = rebuild(r["data"], changes)
        err = bp.section_error(new["steps"])
        _need(err is None, f"{name}: 區段不完整: {err}")
        got = diff_limits(r["data"], new)
        _need(sorted(got, key=str) == sorted(map(_where, changes), key=str),
              f"{name}: 改動的地方跟規劃不同")
        built.append((name, r, new, changes))
    mo, ev = built[0][1], built[1][1]
    _need(mo["images"][shared.BUSY] == ev["images"][shared.BUSY],
          f"[{lang}] 早晚兩份的忙碌指示圖不同: 不能共用一個驗證")
    _need(mo["data"]["scanRegion"] == ev["data"]["scanRegion"],
          f"[{lang}] 早晚兩份的搜尋範圍不同")
    frames = shared.SeqFrames()
    keys = set()
    for _n, _r, _new, changes in built:
        for c in changes:
            pos, neg = frame_plan(lang, c, positions)
            keys |= {(v[0], v[1]) for v in pos} | set(neg)
    print(f"[{lang}] 預讀 {len(keys)} 張影格…", flush=True)
    frames.prefetch(keys)
    names = findtarget.referenced_templates(ev["data"]["steps"], [shared.BUSY])
    tmp = tempfile.mkdtemp(prefix="fixed_rect_sweep_")
    place = bp.frame_region(lang, ev["data"]["scanRegion"])
    print(f"[{lang}] 載入引擎…", flush=True)
    try:
        hub = bp.make_hub(ev["images"], [n for n in names if n in ev["images"]], tmp)
        for name, r, new, changes in built:
            for c in changes:
                src = next((x for x in checks if c["kind"] == "busy" and x["kind"] == "busy"
                            and x["new"] == c["new"] and x["old"] == c["old"]), None)
                if src is not None:
                    checks.append(dict(src, flow=name, step=c["step"], where=c["where"],
                                       role=c["role"], shared_with=f"{src['flow']} {src['where']}"))
                    continue
                fn = verify_busy if c["kind"] == "busy" else verify_change
                x = fn(lang, c, hub, r, positions, frames, place)
                checks.append(x)
                print(f"  [{lang}] {name} {x['where']}#{x['step']} {x['template']}: "
                      f"{'通過' if x['ok'] else '**不符**'} 有效 "
                      f"{sum(1 for y in x['rows'] if y['valid'])}/{len(x['rows'])} "
                      f"{x['ms_old']}→{x['ms_new']} ms"
                      + (f" 不一致群 {len(x['mismatch_groups'])}" if x["mismatch_groups"] else "")
                      + (" 影片無對應" if x["no_video"] else "")
                      + (" 影片上都在框外" if x["all_outside"] else ""), flush=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        frames.close()
    for _n, _r, _new, changes in built:
        for c in changes:
            c.pop("target_obj")
    area = {"clip_video": positions["list_clip"], "screen": list_area(lang, positions)}
    return checks, built, area


def apply(built):
    bp.preflight(bp.FLOWS, shared.BACKUP)
    for name, r, new, changes in built:
        path = bp.flow_path(name)
        cur = flowfile.read(path)
        if cur["data"] == new:
            print(f"{name}: 已是新版, 不動")
        else:
            planned = set(map(_where, changes))
            _need(cur["data"] == r["data"] or set(diff_limits(r["data"], cur["data"])) <= planned,
                  f"{name}: 現在的存檔除了這次要改的限定範圍還有別的不同 (有別人改過?), 不動")
            back = bp.write_flow(path, new, r["images"], r["pos"])
            _need(back["data"] == new, f"{name}: 讀回的跟寫入的不同")
            _need(back["images"] == r["images"], f"{name}: 讀回的範本跟改前不同")
            print(f"{name}: 已寫回 ({len(changes)} 處)")
        if bp.sync_draft(path):
            print(f"    草稿與工作區已同步 ({name})")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--lang", choices=sorted(shared.LANGS), action="append")
    args = ap.parse_args(argv)
    langs = args.lang or sorted(shared.LANGS)
    out, built, area = {}, {}, {}
    for lang in langs:
        out[lang], built[lang], area[lang] = run_lang(lang)
    bad = []
    for lang in langs:
        res = {"orig": orig_flows(), "list_area": area[lang],
               "changes": [c for *_x, changes in built[lang] for c in changes],
               "checks": out[lang], "ok": all(x["ok"] for x in out[lang])}
        with open(os.path.join(shared.RESULTS, f"sweep_{lang}.json"), "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        if not res["ok"]:
            bad.append(lang)
    if args.apply and not bad:
        for lang in langs:
            apply(built[lang])
    print("通過" if not bad else f"**不通過**: {'、'.join(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
