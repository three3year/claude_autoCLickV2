from __future__ import annotations

import argparse
import os
import shutil
import tempfile

import srcommon as sr
from srcommon import bp

import calibration  # noqa: E402
import flowfile  # noqa: E402
from automation import findtarget, flowfmt, pickcheck  # noqa: E402

HEADERS = {
    "tw": {"video": "demo3", "list_x": (860, 1000),
           "crops": {"標題_控制中樞": (500, (866, 136, 112, 44)),
                     "標題_會客室": (500, (866, 381, 112, 44)),
                     "標題_製造站": (500, (866, 626, 112, 44)),
                     "標題_貿易站": (550, (866, 828, 112, 44)),
                     "標題_發電站": (650, (866, 292, 112, 44)),
                     "標題_辦公室": (650, (866, 929, 112, 44))},
           "swap": (500, (1812, 250, 44, 44)),
           "frames": range(380, 770, 10)},
    "cn": {"video": "demo4", "list_x": (766, 890),
           "crops": {"标题_控制中枢": (400, (770, 124, 102, 40)),
                     "标题_会客室": (400, (770, 341, 102, 40)),
                     "标题_制造站": (400, (770, 558, 102, 40)),
                     "标题_贸易站": (500, (770, 658, 102, 40)),
                     "标题_发电站": (600, (770, 246, 102, 40)),
                     "标题_办公室": (600, (770, 811, 102, 40))},
           "swap": (400, (1604, 444, 40, 36)),
           "frames": range(340, 810, 10)},
}


def crop_headers(lang):
    cfg = HEADERS[lang]
    d = os.path.join(sr.TEMPLATES, lang)
    os.makedirs(d, exist_ok=True)
    images = {}
    for name, (fn, box) in cfg["crops"].items():
        img = sr.crop(sr.frame(cfg["video"], fn), box)
        bp.write_img(os.path.join(d, name + ".png"), img)
        images[name] = bp.encode(img)
    fn, box = cfg["swap"]
    img = sr.crop(sr.frame(cfg["video"], fn), box)
    bp.write_img(os.path.join(d, "_swap.png"), img)
    images["_swap"] = bp.encode(img)
    return images


def list_rect(lang, region, anchor):
    x0, x1 = HEADERS[lang]["list_x"]
    ox, oy = sr.offset(lang)
    scr = (x0 + ox, region[1], x1 - x0, region[3])
    return findtarget.fixed_rect_from_screen(scr, anchor, 1.0)


def stage_headers(lang):
    cfg = HEADERS[lang]
    images = crop_headers(lang)
    conv = sr.load(os.path.join(sr.RESULTS, f"convert_{lang}.json"))
    ev = sr.LANGS[lang]["evening"]
    region = sr.read_flow(ev, sr.CONVERTED)["data"]["scanRegion"]
    anchor = tuple(conv[ev]["pair"]["new_anchor"])
    place = sr.place(lang, region)
    rect = list_rect(lang, region, anchor)
    names = [n for n in images if n != "_swap"]
    frames = list(cfg["frames"])
    sr.prefetch([(cfg["video"], f) for f in frames])
    tmp = tempfile.mkdtemp(prefix="sr_hdr_")
    out = {"rect": rect, "headers": {}}
    try:
        hub = bp.make_hub(images, list(images), tmp)
        for name in names:
            tgt = {"template": name, "limit": rect}
            rows, bad = [], 0
            for fn in frames:
                canvas, org = place(sr.frame(cfg["video"], fn))
                per = {}
                for s in sr.PICK_SCALES:
                    f = sr.find_scaled(hub, tgt, canvas, org, anchor, s)
                    per[str(s)] = {"n": len(f.matches),
                                   "best": round(float(f.query.score), 3) if f.query else None,
                                   "center": sr.center(f.picked.box) if f.picked else None,
                                   "score": round(float(f.picked.score), 3) if f.picked else None}
                ns = {e["n"] for e in per.values()}
                visible = per["1.0"]["n"] >= 1
                ok = all(e["n"] <= 1 for e in per.values()) and (len(ns) == 1)
                if visible:
                    ok = ok and all(e["n"] == 1 for e in per.values())
                if not ok:
                    bad += 1
                rows.append({"frame": fn, "visible": visible, "ok": ok, "scales": per})
            vis = sum(1 for r in rows if r["visible"])
            out["headers"][name] = {"rows": rows, "visible": vis, "bad": bad}
            print(f"[{lang}] {name}: 看得到 {vis}/{len(rows)} 幀, 不過 {bad}")
            for r in rows:
                if not r["ok"]:
                    print("    ✘ f%d " % r["frame"] + ", ".join(
                        f"×{s}:{e['n']}個/{e['best']}" for s, e in r["scales"].items()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sr.dump(os.path.join(sr.RESULTS, f"headers_{lang}.json"), out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("headers", "stations", "build"))
    ap.add_argument("--lang", choices=("cn", "tw"))
    args = ap.parse_args()
    langs = [args.lang] if args.lang else ["tw", "cn"]
    for lang in langs:
        if args.stage == "headers":
            stage_headers(lang)
        else:
            raise SystemExit("尚未實作")


if __name__ == "__main__":
    main()
