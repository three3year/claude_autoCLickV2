from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile

import clue
from clue import bp

import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402
from video_to_flow import verify as vtf_verify  # noqa: E402


def flow_targets(steps, lang):
    cfg = clue.LANGS[lang]
    lay = clue.new_layout(steps, lang)
    a, b = lay["check"]
    sec = steps[a:b + 1]
    out = {"open": findtarget.target(steps[lay["open"]]),
           "marker": findtarget.confirm_target(steps[lay["open"]]),
           "label": next(findtarget.target(s) for s in sec
                         if findtarget.template(s) == clue.LABEL[lang]),
           "quick": next(findtarget.target(s) for s in sec
                         if findtarget.template(s) == cfg["quick"])}
    picks = [s for s in sec if s.get("type") == "click" and s.get("confirm") == "appear"]
    for n, s in zip(clue.NUMS, picks):
        out[n] = findtarget.confirm_target(s)
    boxes = {"open": cfg["boxes"][cfg["open"]][1], "marker": cfg["boxes"][cfg["marker"]][1],
             "label": cfg["boxes"][clue.LABEL[lang]][1], "quick": cfg["quick_box"]}
    boxes.update({n: clue.button_box(lang, n) for n in clue.NUMS})
    return out, boxes


def _inside(box, lim):
    if lim is None:
        return True
    return (lim[0] <= box[0] and box[0] + box[2] <= lim[0] + lim[2]
            and lim[1] <= box[1] and box[1] + box[3] <= lim[1] + lim[3])


def probe(lang, hub, tgt, box, canvas, org, want):
    f = findtarget.find(tgt, hub, canvas, org, origin=None, scale=1.0)
    p = f.picked
    rec = {"template": tgt["template"], "want": want, "found": p is not None,
           "score": None if p is None else round(float(p.score), 3),
           "best": None if f.query is None else round(float(f.query.score), 3)}
    if p is None:
        rec["ok"] = not want
        return rec
    rec["picked"] = list(p.box)
    rec["inside"] = _inside(p.box, f.limit)
    ok = want and rec["inside"]
    if box is not None:
        cx, cy = clue.screen_xy(lang, clue.center(box))
        rec["dist"] = round(((p.center[0] - cx) ** 2 + (p.center[1] - cy) ** 2) ** 0.5, 1)
        rec["tol"] = vtf_verify.position_tolerance((0, 0, box[2], box[3]))
        ok = ok and rec["dist"] <= rec["tol"]
    rec["ok"] = ok
    return rec


def plan(lang):
    cfg = clue.LANGS[lang]
    out = [(f, "closed", {"open": True, "quick": True, "marker": False}) for f in cfg["closed"]]
    out += [(f, "all", {"marker": True, **{n: False for n in clue.NUMS}}) for f in cfg["all"]]
    for f, n in clue.picked_frames(lang):
        want = {"marker": True, "label": cfg["has"][n]}
        want.update({m: m == n for m in clue.NUMS})
        out.append((f, n, want))
    for n, (a, _) in cfg["picked"].items():
        out.append((a - 1, f"switch{n}", {n: False}))
        out += [(f, f"switch{n}", {"label": cfg["has"][n]}) for f in (a, a + 1)]
    return out


def run_lang(lang, flows):
    cfg = clue.LANGS[lang]
    r = flowfile.read(bp.flow_path(cfg["flow"], flows))
    steps = r["data"]["steps"]
    if not clue.is_new(steps, lang):
        raise SystemExit(f"{cfg['flow']}: 還沒改 (先跑 build.py --apply)")
    tgts, boxes = flow_targets(steps, lang)
    items = plan(lang)
    frames = clue.read_frames(cfg["video"], {f for f, _, _ in items})
    hidden = {}
    for scene in {s for _, s, _ in items}:
        group = {f: frames[f] for f, s, _ in items if s == scene}
        for role, box in boxes.items():
            if box is not None:
                hidden[(scene, role)] = clue.occluded(group, box)
    place = bp.frame_region(lang, r["data"]["scanRegion"])
    names = sorted({t["template"] for t in tgts.values()})
    tmp = tempfile.mkdtemp(prefix="clue_frames_")
    rows = []
    try:
        hub = bp.make_hub(r["images"], names, tmp)
        for f, scene, want in items:
            canvas, org = place(frames[f])
            for role, w in want.items():
                rec = probe(lang, hub, tgts[role], boxes[role], canvas, org, w)
                rec.update(frame=f, scene=scene, role=role,
                           cursor=w and f in hidden.get((scene, role), ()))
                rows.append(rec)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    counted = [x for x in rows if not x["cursor"]]
    return {"flow": cfg["flow"], "video": cfg["video"], "stride": clue.STRIDE,
            "targets": {str(k): v for k, v in tgts.items()},
            "rows": rows, "ok": all(x["ok"] for x in counted)}


def tally(rep):
    rows = [x for x in rep["rows"] if not x["cursor"]]
    out = []
    for name in dict.fromkeys(x["template"] for x in rep["rows"]):
        parts = []
        for want in (True, False):
            xs = [x for x in rows if x["template"] == name and x["want"] == want]
            if not xs:
                continue
            good = sum(x["ok"] for x in xs)
            if want:
                sc = [x["score"] for x in xs if x["score"] is not None]
                parts.append(f"該找到 {good}/{len(xs)}"
                             + (f"（{min(sc):.3f}–{max(sc):.3f}）" if sc else ""))
            else:
                best = [x["best"] for x in xs if x["best"] is not None]
                parts.append(f"該找不到 {good}/{len(xs)}" + (f"（最高 {max(best):.3f}）" if best else ""))
        out.append(f"{name}：{'；'.join(parts)}")
    return out


def summary(rep):
    rows = [x for x in rep["rows"] if not x["cursor"]]
    out = [f"  {line}" for line in tally(rep)]
    cur = [x for x in rep["rows"] if x["cursor"]]
    if cur:
        out.append(f"  游標壓住、不算數 {len(cur)} 筆："
                   + "、".join(sorted({f"{x['template']}@{x['frame']}" for x in cur})))
    for x in rows:
        if not x["ok"]:
            out.append(f"  不符: {x}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--flows", default=bp.FLOWS)
    ap.add_argument("--lang", choices=sorted(clue.LANGS), required=True)
    args = ap.parse_args(argv)
    rep = run_lang(args.lang, args.flows)
    os.makedirs(clue.RESULTS, exist_ok=True)
    with open(os.path.join(clue.RESULTS, f"frames_{args.lang}.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(f"[{rep['flow']}] {rep['video']}")
    print("\n".join(summary(rep)))
    print("通過" if rep["ok"] else "**不通過**")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
