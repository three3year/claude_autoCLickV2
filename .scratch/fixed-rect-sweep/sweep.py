"""決定框、驗證 (接縫一)、寫回: 四份流程剩下的九宮格與全畫面換成固定矩形 (見 spec.md).

    .venv/Scripts/python.exe .scratch/fixed-rect-sweep/sweep.py [--lang cn|tw] [--apply]

先跑 positions.py (results/positions_<lang>.json)。

改前的流程從備份讀 (shared.BACKUP; 還沒備份＝還沒寫回過, 就讀現在的), 所以可以重跑。
框 (規格「Implementation Decisions」):
- 忙碌指示 (四份的流程層級設定, 與早_簡中「忙碌指示 → 等待消失」那一步): shared.LANGS 的
  busy_box 外擴 MARGIN。
- 晚班位置固定的圖 (shared.FIXED_STEPS) 與第 3 步確認圖: 10/08 晚實跑日誌該步、該角色找到的
  位置 (同一步有多筆就取聯集) 外擴 MARGIN。shared.WIDEN_STEPS (待辦鈴鐺) 再併上同一天早班實跑
  同一張圖 (同尺寸) 的位置——同一天兩次實機就不在同一處, 只照晚班那次框下次很可能逾時
  (偏離規格「以今晚日誌為準」, 見票 02、03)。
- 換班列名 (shared.LIST_STEPS): 左右＝這次實跑日誌裡該範本所有出現位置 (matches＋rejected)
  的左右範圍外擴 MARGIN; 上下＝換班清單顯示區 (positions.py 在晚班影片上量的清單切線與畫面底,
  換成實機座標)。日誌裡列名的所有出現位置都要在清單區裡, 不然中止。
改前的設定要跟規格寫的一樣 (晚班這些步驟全畫面、確認圖九宮格 7、忙碌指示九宮格 8、9)——
不一樣就中止 (步驟編號變了, 不要改錯步)。

驗證 (真引擎、arknights 門檻, 影格換成實機搜尋範圍的畫布, 同 busy-pause-fixed-rect 票 08;
影格逐幀順序讀, 見 shared.SeqFrames):
- 每個改過的找圖目標, 在晚班影片上這張範本出現的影格挑最多 PER 張, 改前、改後各找一次:
  改前找得到的 (有效影格) 改後也要找得到、挑到的位置一樣 (容許值內); 兩次的找圖時間都記下。
  改前挑到的在新框外的影格＝「不一致」(影片位置新框裝不下): 照實列出, 框仍以日誌為準, 不算失敗。
  影片上沒出現＝「影片無對應」; 出現了但都在新框外＝「影片上都在框外」; 都不擋。
- 另外把 opencv 量到的影片位置 (positions.py) 依位置分群, 新框裝不下的群也列成不一致
  (引擎驗證只抽樣, 這裡看全部)。
- 忙碌指示: 有忙碌字樣的影格 (positions.py 的 busy) 上新框找得到、位置跟改前一樣;
  沒忙碌的影格上改前、改後都找不到。沒忙碌＝晚班影片每 NEG_STRIDE 幀、離有忙碌的影格超過
  NEAR_BUSY 幀, 且畫面下半部跟範本的 opencv 相關 < IDLE (淡入淡出、疊在別的提示字上的忙碌字樣
  不算反例, 照實列出)。
- demo1 (低位元率) 的不符照實列出、不算失敗 (同票 08)。
結果寫 results/sweep_<lang>.json; --apply 驗證全過才寫回 (AutoClick 要關著; 先整個 profiles
備份到 shared.BACKUP, 讀回驗證只有規劃的限定範圍不同, 草稿屬於它就同步)。
"""
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
import fixed_rects as fr  # noqa: E402  (busy-pause-fixed-rect 票 08 的框與驗證小工具)

PER = 6
NEG_STRIDE = 25
NEAR_BUSY = 15
IDLE = 0.5           # 反例: 畫面下半部 opencv 灰階相關 < IDLE 才算沒忙碌 (沒忙碌的背景約 0.31–0.39,
                     # 看得到忙碌字 ≥0.74; 中間是淡入淡出、疊在別的提示字上的)
SPREAD = 8           # 影片位置分群: 中心差不超過 (px)
LOW_BITRATE = {"demo1"}


def _need(cond, msg):
    if not cond:
        raise SystemExit(msg)


def orig_flows():
    return shared.BACKUP_FLOWS if os.path.isdir(shared.BACKUP_FLOWS) else bp.FLOWS


# ================= 決定框 =================

def list_area(lang, positions):
    """換班清單顯示區的上下緣 (實機螢幕 y)."""
    clip, oy = positions["list_clip"], shared.offset(lang)[1]
    return (clip["top"] + oy, clip["bottom"] + oy)


def list_rect(boxes, lang, region, area):
    """換班列名: 左右＝出現位置外擴 MARGIN, 上下＝清單顯示區; 回傳 (固定矩形, 實機框)."""
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
    """[{"flow", "where", "step", "role", "template", "old", "new", "box", "kind"}]: 要改的地方.

    where: "busy"(流程層級)、"target"、"confirm"。box＝新框的實機螢幕座標 (外擴後、裁前)。
    """
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
    """改前的 data → 改後的 data (只換 changes 指定的限定範圍)."""
    data = json.loads(json.dumps(data))
    for c in changes:
        shared.target_of(data, c)["limit"] = dict(c["new"])
    return data


def diff_limits(a, b):
    """兩份 data 的差異: 只允許限定範圍不同; 回傳不同的地方 [(where, step, key)] 或中止."""
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
    """改動 c 在 diff_limits 結果裡的寫法."""
    if c["where"] == "busy":
        return ("busy", None, "limit")
    key = findtarget.TARGET if c["where"] == "target" else findtarget.CONFIRM_TARGET
    return ("step", c["step"], key)


# ================= 驗證 (真引擎) =================

def spread(items, k):
    """均勻挑 k 個 (依影片分開、各自依時間均分)."""
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
    """影片位置 (換成實機座標) 依中心分群 (±SPREAD)."""
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
    """改前 / 改後各找一次: 每張影格一列."""
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
    """這個改動要驗的影格: (有出現的 [[影片, 幀, x, y, w, h, …]], 反例候選 [(影片, 幀)])."""
    if c["kind"] != "busy":
        return spread(positions["video"].get(c["template"], []), PER), []
    busy = positions["busy"]
    video = shared.LANGS[lang]["video"]
    near = {(v[0], v[1] + d) for v in busy for d in range(-NEAR_BUSY, NEAR_BUSY + 1)}
    neg = [(video, n) for n in range(0, frame_count(video), NEG_STRIDE) if (video, n) not in near]
    return spread(busy, 3 * PER), neg


def _result(c, lim, rows, vids, lang):
    """一個改動的驗證結果 (verify_change / verify_busy 共用的欄位)."""
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
            # 影片無對應: 影片上沒出現; 都在框外: 出現了但沒有一張在新框裡 (框只靠日誌)
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
    """忙碌指示: 有忙碌的影格找得到 (位置跟改前一樣), 沒忙碌的影格改前改後都找不到."""
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
    # 驗證用晚班流程的範本 (早班的忙碌指示圖、搜尋範圍跟晚班同版相同才共用驗證)
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
                # 忙碌指示: 早晚同版同一張圖、同一個框, 第一筆驗過的共用
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
            # 現在的存檔只能是改前的 (備份), 或只差規劃要改的限定範圍 (上一版寫回的框)
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
