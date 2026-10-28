from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile

import common
from common import PRIORITY

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import applog  # noqa: E402
import enginehub  # noqa: E402
import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402
from automation.runner import branch_layout  # noqa: E402
from video_to_flow import verify as vtf_verify  # noqa: E402

TEMPLATES_DIR = os.path.join(common.ROOT, ".scratch", "credit-store-templates")
INNER_BOX = (-50, -52, 50, 20)
LOW_BITRATE = {"demo1"}


def read_img(path):
    img = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"讀不到影格: {path}")
    return img


def branch_targets(steps):
    start, nav = common.purchase_span(steps)
    bs = next(i for i in range(start, nav) if steps[i].get("type") == "branch_start")
    segs, _end = branch_layout(steps, bs)
    return [findtarget.target(steps[s]) for s in segs]


def expected(frame, sizes):
    live = [c for c in frame["cards"] if not c["soldOut"] and c["name"] in PRIORITY]
    if not live:
        return None
    best = min(PRIORITY.index(c["name"]) for c in live)
    name = PRIORITY[best]
    cards = [c for c in live if c["name"] == name]
    card = min(cards, key=lambda c: (round(c["center"][1] / 100), c["center"][0]))
    w, h = sizes[name]
    s = w / (INNER_BOX[2] - INNER_BOX[0])
    off = ((INNER_BOX[0] + INNER_BOX[2]) / 2 * s, (INNER_BOX[1] + INNER_BOX[3]) / 2 * s)
    want = (card["center"][0] + off[0], card["center"][1] + off[1])
    return name, want, vtf_verify.position_tolerance((0, 0, w, h))


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def card_at(frame, pt):
    best = min(frame["cards"], key=lambda c: _dist(c["center"], pt))
    return best if _dist(best["center"], pt) < 130 else None


def card_text(card):
    return None if card is None else card["name"] + ("（售完）" if card["soldOut"] else "")


def make_hub(images, names, tmp):
    ws = flowfile.Workspace(tmp)
    for n in names:
        ws.add(n, images[n])
    applog.set_path(os.path.join(tmp, "autoclick.log"))
    hub = enginehub.EngineHub()
    hub.load(ws.root, config_dir=common.PROFILE)
    if not hub.ready:
        raise SystemExit(f"引擎載入失敗: {hub.error!r}")
    if hub.coarse_only:
        raise SystemExit("深度驗證模型載不起來 (coarse-only): 驗證結果不等於實際執行, 中止")
    hub.preload(names)
    return hub


def judge(frame, tgts, hub, sizes):
    img = read_img(os.path.join(TEMPLATES_DIR, "frames", frame["id"] + ".png"))
    picks = []
    found = {}
    for k, t in enumerate(tgts):
        f = findtarget.find(t, hub, img, (0, 0), origin=None, scale=1.0)
        found[t["template"]] = f
        if f.picked is not None:
            picks.append((k, t["template"], f.picked))
    exp = expected(frame, sizes)
    out = {"id": frame["id"], "video": frame["source"].get("video"),
           "low_bitrate": frame["source"].get("video") in LOW_BITRATE,
           "live": [c["name"] for c in frame["cards"] if not c["soldOut"]],
           "sold": [c["name"] for c in frame["cards"] if c["soldOut"]]}
    if picks:
        k, name, m = picks[0]
        card = card_at(frame, m.center)
        out["picked"] = {"branch": k + 1, "item": common.item_of(name),
                         "center": list(m.center), "score": round(m.score, 3),
                         "color": None if m.color is None else round(m.color, 3),
                         "card": None if card is None else
                         {"name": card["name"], "soldOut": card["soldOut"],
                          "center": card["center"]}}
    else:
        out["picked"] = None
    out["others"] = [{"branch": k + 1, "item": common.item_of(n),
                      "card": card_text(card_at(frame, m.center))}
                     for k, n, m in picks[1:]]
    if exp is None:
        out["expected"] = None
        out["ok"] = out["picked"] is None
        return out
    name, want, tol = exp
    out["expected"] = {"item": name, "center": [round(v, 1) for v in want],
                       "tol": round(tol, 1)}
    f = found[common.template_name(name)]
    out["expected_query"] = {"best": None if f.query is None else round(f.query.score, 3),
                             "failed": f.failed}
    p = out["picked"]
    if p is not None:
        d = _dist(p["center"], want)
        p["dist"] = round(d, 1)
        out["ok"] = p["item"] == name and d <= tol
    else:
        out["ok"] = False
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=sorted(common.LANGS), required=True)
    ap.add_argument("--flow", help="流程名或路徑 (預設依語系)")
    args = ap.parse_args(argv)

    path = common.flow_path(args.lang, args.flow)
    r = flowfile.read(path)
    tgts = branch_targets(r["data"]["steps"])
    names = [t["template"] for t in tgts]
    if [common.item_of(n) for n in names] != PRIORITY:
        raise SystemExit("分岔的分支順序不是 spec 的優先順序")
    sizes = {}
    for n in names:
        img = cv2.imdecode(np.frombuffer(r["images"][n], np.uint8), cv2.IMREAD_COLOR)
        sizes[common.item_of(n)] = (img.shape[1], img.shape[0])

    with open(os.path.join(TEMPLATES_DIR, "annotations.json"), encoding="utf-8") as f:
        frames = [fr for fr in json.load(f)["frames"] if fr["set"] == args.lang]

    tmp = tempfile.mkdtemp(prefix="credit_switch_")
    try:
        print("載入引擎…", flush=True)
        hub = make_hub(r["images"], names, tmp)
        results = [judge(fr, tgts, hub, sizes) for fr in frames]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = 0
    for o in results:
        p, e = o["picked"], o["expected"]
        tag = "通過" if o["ok"] else ("不符（demo1 低位元率）" if o["low_bitrate"] else "不符")
        bad += not o["ok"] and not o["low_bitrate"]
        got = "不走任何分支" if p is None else (
            f"分支 {p['branch']} {p['item']} @{tuple(p['center'])} 分數 {p['score']}"
            + (f" 比色 {p['color']}" if p["color"] is not None else "")
            + (f" 距預期 {p['dist']}px" if "dist" in p else "")
            + (f" → 卡：{p['card']['name']}{'（售完）' if p['card']['soldOut'] else ''}"
               if p["card"] else " → 不在卡上"))
        want = "不走任何分支" if e is None else f"{e['item']} @{tuple(e['center'])} ±{e['tol']}"
        print(f"[{tag}] {o['id']}: 預期 {want}；實際 {got}")
        if not o["ok"] and e is not None:
            q = o["expected_query"]
            print(f"      預期商品的查詢：最高 {q['best']}、未過 {q['failed']}")
    os.makedirs(os.path.join(common.HERE, "results"), exist_ok=True)
    with open(os.path.join(common.HERE, "results", f"frames_{args.lang}.json"), "w",
              encoding="utf-8") as f:
        json.dump({"flow": os.path.basename(path), "results": results}, f,
                  ensure_ascii=False, indent=1)
    print(f"{sum(o['ok'] for o in results)}/{len(results)} 通過；"
          f"非 demo1 不符 {bad} 張")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
