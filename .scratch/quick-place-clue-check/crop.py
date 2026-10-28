from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile

import clue
from clue import bp

from automation import findtarget  # noqa: E402


def cut(lang):
    cfg = clue.LANGS[lang]
    todo = clue.crops(lang)
    frames = clue.read_frames(cfg["video"], {n for n, _ in todo.values()})
    d = os.path.join(clue.TEMPLATES, lang)
    os.makedirs(d, exist_ok=True)
    out = {}
    for name, (n, (x, y, w, h)) in todo.items():
        img = frames[n][y:y + h, x:x + w].copy()
        bp.write_img(clue.template_path(lang, name), img)
        out[name] = img
    return out


def sheet(lang, imgs):
    import numpy as np
    h = max(i.shape[0] for i in imgs.values())
    pad = [np.pad(i, ((0, h - i.shape[0]), (0, 6), (0, 0)), constant_values=255)
           for i in imgs.values()]
    bp.write_img(os.path.join(clue.TEMPLATES, lang, "_sheet.png"), np.hstack(pad))


def list_frames(lang):
    has = clue.LANGS[lang]["has"]
    return [(f, has[n], n) for f, n in clue.picked_frames(lang)]


def compare(lang, imgs):
    import flowfile
    cfg = clue.LANGS[lang]
    region = flowfile.read(bp.flow_path(cfg["flow"]))["data"]["scanRegion"]
    place = bp.frame_region(lang, region)
    names = list(cfg["labels"])
    blobs = {n: bp.encode(imgs[n]) for n in names}
    items = list_frames(lang)
    frames = clue.read_frames(cfg["video"], {f for f, _, _ in items})
    tmp = tempfile.mkdtemp(prefix="clue_labels_")
    rows = {n: [] for n in names}
    try:
        hub = bp.make_hub(blobs, names, tmp)
        for name in names:
            box = cfg["boxes"][name][1]
            tgt = {"template": name,
                   "limit": clue.rect(lang, region, box, clue.MARGIN["label"])}
            hidden = set()
            for n in clue.NUMS:
                hidden |= clue.occluded({f: frames[f] for f, _, k in items if k == n}, box)
            for f, has, n in items:
                canvas, org = place(frames[f])
                r = findtarget.find(tgt, hub, canvas, org, origin=None, scale=1.0)
                score = None if r.picked is None else round(float(r.picked.score), 3)
                best = None if r.query is None else round(float(r.query.score), 3)
                rows[name].append({"frame": f, "num": n, "has": has, "cursor": f in hidden,
                                   "found": r.picked is not None, "score": score, "best": best,
                                   "ok": f in hidden or (r.picked is not None) == has})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    summary = {}
    for name, rs in rows.items():
        counted = [x for x in rs if not x["cursor"]]
        pos = [x["score"] for x in counted if x["has"] and x["score"] is not None]
        neg = [x["best"] for x in counted if not x["has"] and x["best"] is not None]
        summary[name] = {"ok": sum(x["ok"] for x in counted), "total": len(counted),
                         "cursor": [x["frame"] for x in rs if x["cursor"]],
                         "pos_min": min(pos) if pos else None,
                         "pos_max": max(pos) if pos else None,
                         "neg_best": max(neg) if neg else None}
    return {"flow": cfg["flow"], "video": cfg["video"], "stride": clue.STRIDE,
            "summary": summary, "rows": rows, "chosen": clue.LABEL[lang]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=sorted(clue.LANGS), required=True)
    args = ap.parse_args(argv)
    imgs = cut(args.lang)
    sheet(args.lang, imgs)
    print(f"已裁 {len(imgs)} 張範本到 {os.path.join(clue.TEMPLATES, args.lang)}")
    rep = compare(args.lang, imgs)
    os.makedirs(clue.RESULTS, exist_ok=True)
    with open(os.path.join(clue.RESULTS, f"labels_{args.lang}.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    for name, s in rep["summary"].items():
        print(f"  {name}: {s['ok']}/{s['total']} 判對；有卡片 {s['pos_min']}–{s['pos_max']}，"
              f"沒卡片最高 {s['neg_best']}；游標壓住不算 {s['cursor']}"
              + ("  ← 採用" if name == rep["chosen"] else ""))
        for x in rep["rows"][name]:
            if not x["ok"]:
                print(f"    不符: {x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
