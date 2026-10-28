from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "fixed-rect-sweep"))
sys.path.insert(0, os.path.join(HERE, "..", "busy-pause-fixed-rect"))

import shared  # noqa: E402
from shared import bp  # noqa: E402

import flowfile  # noqa: E402
from automation import findtarget, flowfmt  # noqa: E402
import fixed_rects as fr  # noqa: E402

OUT = os.path.join(HERE, "converted", "arknights")
OUT_FLOWS = os.path.join(OUT, "flows")
RESULTS = os.path.join(HERE, "results")
BACKUP = os.path.join(bp.APP, "dist", "profiles-backup-2026-10-09-coord-anchor")
SCRATCH_BACKUP = os.path.join(HERE, "backup")
PER = 3

ANCHORS = {"cn": {"region": [87, 57, 1718, 920], "anchor": (115, 76)},
           "tw": {"region": [0, 0, 1920, 1024], "anchor": (20, 19)}}
FLOWS = {"cn": ["早_簡中", "晚_簡中"], "tw": ["早_繁中", "晚_繁中"]}


def _need(cond, msg):
    if not cond:
        raise SystemExit(msg)


def read_old(path):
    with zipfile.ZipFile(path) as z:
        data = json.loads(z.read("flow.json").decode("utf-8"))
        try:
            meta = json.loads(z.read("templates/_meta.json").decode("utf-8"))
        except KeyError:
            meta = {}
        images = {}
        for fn in z.namelist():
            if fn.startswith("templates/") and fn.lower().endswith(".png") \
                    and not fn[len("templates/"):].startswith("_"):
                images[os.path.splitext(fn[len("templates/"):])[0]] = z.read(fn)
    _need(data.get("coordSpace") == "region" and int(data.get("flowFormat", 0)) == 4,
          f"{path}: 不是預期的舊格式 (格式 4、座標相對搜尋範圍): "
          f"{data.get('flowFormat')} {data.get('coordSpace')}")
    return data, images, dict((meta.get("pos") if isinstance(meta, dict) else {}) or {})


def old_rect_px(lim, region):
    rx, ry, rw, rh = region
    x0, x1 = rx + round(rw * lim["x"]), rx + round(rw * (lim["x"] + lim["w"]))
    y0, y1 = ry + round(rh * lim["y"]), ry + round(rh * (lim["y"] + lim["h"]))
    return (x0, y0, x1 - x0, y1 - y0)


def targets_of(data):
    out = []
    for i, s in enumerate(data.get("steps") or []):
        for key in ("target", "confirmTarget"):
            t = s.get(key)
            if isinstance(t, dict):
                out.append((f"第 {i + 1} 步 {key}", t))
    busy = data.get("busyTarget")
    if isinstance(busy, dict):
        out.append(("忙碌指示", busy))
    return out


def convert(data, pos, lang, region=None):
    anchor = ANCHORS[lang]["anchor"]
    if region is None:
        region = ANCHORS[lang]["region"]
        _need(list(data.get("scanRegion") or []) == region,
              f"存檔的搜尋範圍 {data.get('scanRegion')} 不是預期的 {region}")
    rects, bad = [], []
    for where, t in targets_of(data):
        lim = t.get("limit") or {}
        pick = t.get("pick") or {}
        if lim.get("kind") == "grid":
            bad.append(f"{where}: 九宮格 {lim.get('cells')}")
        if pick.get("kind") == "near" and pick.get("base", "region") != "origin":
            bad.append(f"{where}: 以搜尋範圍為基準的指定點 {pick}")
        elif pick.get("kind") == "near":
            pick.pop("base", None)
        if lim.get("kind") == "rect":
            px = old_rect_px(lim, region)
            new = findtarget.fixed_rect_from_screen(px, anchor, 1.0)
            back = flowfmt.rect_to_screen(new, anchor, 1.0)
            diff = max(abs(a - b) for a, b in zip(px, back))
            rects.append({"where": where, "template": t.get("template"), "old": dict(lim),
                          "old_px": list(px), "new": new, "new_px": list(back), "diff": diff})
            t["limit"] = new
    abs_steps = [no for no, _ in flowfmt.abs_steps(data.get("steps") or [])]
    rx, ry = region[0], region[1]
    flowfmt.remap_flow(data, lambda xy: flowfmt.from_screen((rx + xy[0], ry + xy[1]),
                                                             anchor, 1.0))
    new_pos = {n: list(flowfmt.from_screen(xy, anchor, 1.0)) for n, xy in pos.items()}
    data["coordSpace"] = flowfmt.ANCHOR
    data.pop("flowFormat", None)
    return {"rects": rects, "abs_steps": abs_steps, "pos": len(new_pos),
            "max_diff": max([r["diff"] for r in rects], default=0)}, bad, new_pos


def video_check(lang, name, old_data, new_data, images, frames):
    region, anchor = ANCHORS[lang]["region"], ANCHORS[lang]["anchor"]
    with open(os.path.join(shared.RESULTS, f"positions_{lang}.json"), encoding="utf-8") as f:
        positions = json.load(f)["video"]
    place = bp.frame_region(lang, region)
    seen, jobs = set(), []
    for (where, old_t), (_, new_t) in zip(targets_of(old_data), targets_of(new_data)):
        lim = old_t.get("limit") or {}
        if lim.get("kind") != "rect":
            continue
        key = (old_t.get("template"), json.dumps(lim, sort_keys=True),
               json.dumps(old_t.get("pick"), sort_keys=True), bool(old_t.get("colorCheck")))
        if key in seen:
            continue
        seen.add(key)
        vids = positions.get(old_t["template"], [])
        jobs.append((where, old_t, new_t, fr_spread(vids, PER)))
    names = sorted({j[1]["template"] for j in jobs})
    rows = []
    if not jobs:
        return rows
    with tempfile.TemporaryDirectory(prefix="anchor_") as tmp:
        hub = bp.make_hub(images, names, tmp)
        for where, old_t, new_t, vids in jobs:
            px = old_rect_px(old_t["limit"], region)
            old_equiv = dict(old_t, limit={"kind": "rect", "x": px[0], "y": px[1],
                                           "w": px[2], "h": px[3]})
            for v in vids:
                video, n = v[0], v[1]
                canvas, org = place(frames.get(video, n))
                a = findtarget.find(old_equiv, hub, canvas, org, origin=None, scale=1.0,
                                    anchor=(0, 0))
                b = findtarget.find(new_t, hub, canvas, org, origin=None, scale=1.0,
                                    anchor=anchor)
                same = (a.picked is None) == (b.picked is None) and (
                    a.picked is None or fr._dist(a.picked.center, b.picked.center) <= 1.0)
                rows.append({"flow": name, "where": where, "template": old_t["template"],
                             "video": video, "frame": n,
                             "old": None if a.picked is None else list(a.picked.box),
                             "new": None if b.picked is None else list(b.picked.box),
                             "limit_old": list(a.limit), "limit_new": list(b.limit),
                             "ok": same})
            if not vids:
                rows.append({"flow": name, "where": where, "template": old_t["template"],
                             "video": None, "frame": None, "old": None, "new": None,
                             "limit_old": None, "limit_new": None, "ok": True,
                             "no_video": True})
    return rows


def fr_spread(items, k):
    if len(items) <= k:
        return list(items)
    step = len(items) / k
    return [items[int(i * step)] for i in range(k)]


def backup():
    _need(not bp.autoclick_running(), "AutoClick 正在執行: 請先關掉")
    if not os.path.isdir(BACKUP):
        shutil.copytree(os.path.dirname(bp.PROFILE), BACKUP)
        print(f"已備份 profiles 到 {BACKUP}")
    else:
        print(f"備份已在: {BACKUP}")
    if not os.path.isdir(SCRATCH_BACKUP):
        os.makedirs(SCRATCH_BACKUP)
        for name in [n for v in FLOWS.values() for n in v]:
            shutil.copy2(bp.flow_path(name), SCRATCH_BACKUP)
        shutil.copy2(os.path.join(bp.FLOWS, flowfile.DRAFT_NAME), SCRATCH_BACKUP)
        print(f"四份存檔與草稿已另存一份到 {SCRATCH_BACKUP}")


def run(langs, with_video):
    backup()
    os.makedirs(OUT_FLOWS, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)
    draft_src = os.path.join(bp.FLOWS, flowfile.DRAFT_NAME)
    draft_of = bp.current_flow()
    report = {}
    frames = shared.SeqFrames() if with_video else None
    for lang in langs:
        rep = {"flows": {}, "ok": True}
        for name in FLOWS[lang]:
            src = bp.flow_path(name)
            old_data, images, pos = read_old(src)
            data = json.loads(json.dumps(old_data))
            info, bad, new_pos = convert(data, pos, lang)
            _need(not bad, f"{name}: 有不能換的設定:\n  " + "\n  ".join(bad))
            dest = os.path.join(OUT_FLOWS, name + flowfile.EXT)
            missing = flowfile.write(dest, data, images, new_pos)
            _need(not missing, f"{name}: 存檔缺圖 {missing}")
            back = flowfile.read(dest)
            _need(back["data"]["flowFormat"] == 5 and back["data"]["coordSpace"] == "anchor", f"{name}: 讀回的格式標記不對")
            _need(back["data"]["steps"] == data["steps"] and back["pos"] == new_pos, f"{name}: 讀回的內容與寫入不同")
            refused = False
            try:
                flowfile.read(src)
            except flowfile.OldFormatError:
                refused = True
            _need(refused, f"{name}: dist 的原檔沒有被新版拒絕")
            rows = video_check(lang, name, old_data, data, images, frames) if with_video else []
            bad_rows = [r for r in rows if not r["ok"]]
            rep["flows"][name] = {
                "rects": len(info["rects"]), "max_diff": info["max_diff"],
                "abs_steps": info["abs_steps"], "pos": info["pos"],
                "pos_before": {n: pos[n] for n in list(pos)[:3]},
                "pos_after": {n: new_pos[n] for n in list(new_pos)[:3]},
                "sample": info["rects"][:3],
                "video_rows": rows, "video_checked": len([r for r in rows if r.get("video")]),
                "video_targets": len({(r["template"], r["where"]) for r in rows}),
                "no_video": sorted({r["template"] for r in rows if r.get("no_video")}),
                "mismatch": bad_rows, "dest": dest,
            }
            rep["ok"] = rep["ok"] and info["max_diff"] <= 1 and not bad_rows
            if draft_of and os.path.normcase(os.path.abspath(src)) == draft_of:
                with open(draft_src, encoding="utf-8") as f:
                    draft = json.load(f)
                _need(draft.get("coordSpace") == "region", "草稿不是舊格式")
                _need(draft["steps"] == old_data["steps"],
                      "草稿的步驟與存檔不同 (有未存檔的改動), 不能照存檔的搜尋範圍換")
                dinfo, dbad, _ = convert(draft, {}, lang, region=ANCHORS[lang]["region"])
                _need(not dbad, "草稿有不能換的設定")
                draft.pop("flowFormat", None)
                flowfile.write_draft(OUT, draft)
                d2 = flowfile.read_draft(OUT)
                _need(d2["steps"] == data["steps"],
                      "草稿換算後與存檔的步驟不同 (草稿裡有未存檔的改動?)")
                rep["flows"][name]["draft"] = {"rects": len(dinfo["rects"]),
                                               "max_diff": dinfo["max_diff"],
                                               "scanRegion": draft.get("scanRegion")}
            print(f"[{lang}] {name}: 固定矩形 {len(info['rects'])} 個 (最大差 {info['max_diff']}px), "
                  f"拍攝位置 {info['pos']} 個, 影片比對 {len(rows)} 列, 不一致 {len(bad_rows)}")
        with open(os.path.join(RESULTS, f"convert_{lang}.json"), "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        report[lang] = rep
    if frames:
        frames.close()
    return report


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=["cn", "tw"])
    ap.add_argument("--no-video", action="store_true")
    a = ap.parse_args(argv)
    rep = run([a.lang] if a.lang else ["cn", "tw"], not a.no_video)
    print("OK" if all(r["ok"] for r in rep.values()) else "有不一致, 看 results/convert_*.json")


if __name__ == "__main__":
    main()
