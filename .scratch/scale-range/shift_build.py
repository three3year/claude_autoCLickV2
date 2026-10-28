from __future__ import annotations

import argparse
import os
import shutil
import tempfile

import srcommon as sr
from srcommon import bp
from rebuild_shift import HEADERS

import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402

CATEGORY = {
    "tw": {"製造站1列": "標題_製造站", "製造站首列": "標題_製造站",
           "貿易站1列": "標題_貿易站", "貿易站首列": "標題_貿易站",
           "發電站1列": "標題_發電站", "發電站首列": "標題_發電站",
           "辦公室列": "標題_辦公室"},
    "cn": {"製造站1列": "标题_制造站", "制造站首列": "标题_制造站",
           "貿易站1列": "标题_贸易站", "贸易站1列": "标题_贸易站", "贸易站首列": "标题_贸易站",
           "发电站1列": "标题_发电站", "发电站首列": "标题_发电站",
           "办公室列": "标题_办公室"},
}
SHIFT = {"早_繁中": (90, 116), "晚_繁中": (31, 59), "早_簡中": (100, 126), "晚_簡中": (31, 59)}
OFFICE_ROW = {"tw": "辦公室列", "cn": "办公室列"}
SWAP_TOL = 30
BAND = 80
HEADER_TOL = 14
ROW_LABEL_DY = {"tw": 52, "cn": 46}
LIST_TOP = {"tw": 490, "cn": 390}


LAYOUT = {
    "tw": {"first": 157, "label_dy": 61, "gap": 184, "pitch": 196, "header_x": 922,
           "order": ["標題_控制中樞", "標題_會客室", "標題_製造站", "標題_貿易站", "標題_發電站", "標題_辦公室"],
           "rows": [1, 1, 4, 2, 3, 1]},
    "cn": {"first": 144, "label_dy": 53, "gap": 164, "pitch": 173, "header_x": 821,
           "order": ["标题_控制中枢", "标题_会客室", "标题_制造站", "标题_贸易站", "标题_发电站", "标题_办公室"],
           "rows": [1, 1, 4, 2, 3, 1]},
}


def header_tops(lang):
    L = LAYOUT[lang]
    y, out = L["first"], {}
    for name, n in zip(L["order"], L["rows"]):
        out[name] = y
        y = y + L["label_dy"] + (n - 1) * L["pitch"] + L["gap"]
    return out


class Geometry:
    def __init__(self, lang, hub, place, anchor, region):
        self.lang, self.hub, self.place, self.anchor = lang, hub, place, anchor
        self.cfg = HEADERS[lang]
        self.frames = [(self.cfg["video"], f) for f in self.cfg["frames"] if f >= LIST_TOP[lang]]
        extra = [k for k in sr.known_frames(lang).get(OFFICE_ROW[lang], [])
                 if k[0] != self.cfg["video"]]
        self.frames += extra[::max(1, len(extra) // 8)]
        x0, x1 = self.cfg["list_x"]
        ox, oy = sr.offset(lang)
        self.oy = oy
        self.col = (x0 + ox, region[1], x1 - x0, region[3])
        self.tops = {h: y + oy for h, y in header_tops(lang).items()}
        self._canvas, self._swaps, self._matches = {}, {}, {}
        self.scroll, prev = {}, None
        for fn in self.frames:
            self.scroll[fn] = self.scroll_of(fn, prev)
            prev = self.scroll[fn] if self.scroll[fn] is not None else prev

    def canvas(self, fn):
        if fn not in self._canvas:
            self._canvas[fn] = self.place(sr.frame(*fn))
        return self._canvas[fn]

    def find(self, fn, tgt, s=1.0):
        canvas, org = self.canvas(fn)
        return sr.find_scaled(self.hub, tgt, canvas, org, self.anchor, s)

    def swaps(self, fn):
        if fn not in self._swaps:
            f = self.find(fn, {"template": "_swap"})
            self._swaps[fn] = sorted(sr.center(m.box) for m in f.matches)
        return self._swaps[fn]

    def col_rect(self):
        return findtarget.fixed_rect_from_screen(self.col, self.anchor, 1.0)

    def header_matches(self, fn, header):
        key = (fn, header)
        if key not in self._matches:
            f = self.find(fn, {"template": header, "limit": self.col_rect()})
            self._matches[key] = [sr.center(m.box) for m in f.matches]
        return self._matches[key]

    def layout_points(self):
        L = LAYOUT[self.lang]
        pts = []
        for h, n in zip(L["order"], L["rows"]):
            top = self.tops[h]
            pts.append(top)
            pts += [top + L["label_dy"] + k * L["pitch"] for k in range(n)]
        return pts

    def scroll_of(self, fn, prev=None):
        ys = []
        for h in LAYOUT[self.lang]["order"]:
            for c in self.header_matches(fn, h):
                if all(abs(c[1] - y) > 6 for y in ys):
                    ys.append(c[1])
        if not ys:
            return None
        pts = self.layout_points()
        best = None
        for y in ys:
            for pnt in pts:
                s = pnt - y
                if s < -40 or s > max(pts):
                    continue
                n = sum(1 for y2 in ys if any(abs((p2 - s) - y2) <= 8 for p2 in pts))
                key = (n, -(abs(s - prev) if prev is not None else 0))
                if best is None or key > best[0]:
                    best = (key, s)
        return best[1]
    def header_center(self, fn, header, scrolled=None):
        s = self.scroll[fn] if scrolled is None else scrolled
        if s is None:
            return None
        y = self.tops[header] - s
        near = [c for c in self.header_matches(fn, header) if abs(c[1] - y) <= 25]
        return min(near, key=lambda c: abs(c[1] - y)) if near else None

    def band_rect(self, header, scrolled):
        y = self.tops[header] - scrolled
        hh = 44
        scr = (self.col[0], int(round(y - BAND - hh / 2)), self.col[2], int(2 * BAND + hh))
        return findtarget.fixed_rect_from_screen(scr, self.anchor, 1.0)

    def offsets(self, header, old_name, old_tgt, origin=None):
        for fn in self.frames:
            h = self.header_center(fn, header)
            if h is None:
                continue
            f = self.find(fn, old_tgt) if origin is None else self._find_with_origin(fn, old_tgt, origin)
            if f is None or f.picked is None:
                continue
            c = sr.center(f.picked.box)
            if origin is None and not (0 < c[1] - h[1] < LAYOUT[self.lang]["pitch"]):
                continue
            return (c[0] - h[0], c[1] - h[1]), fn
        raise SystemExit(f"[{self.lang}] 找不到一幀同時有 {header} 與 {old_name}")

    def _find_with_origin(self, fn, tgt, origin_tgt):
        from automation import findtarget as ft
        canvas, org = self.canvas(fn)
        f1 = ft.find(origin_tgt, self.hub, canvas, org, scale=1.0, anchor=self.anchor)
        if f1.picked is None:
            return None
        return ft.find(tgt, self.hub, canvas, org, origin=sr.center(f1.picked.box),
                       scale=1.0, anchor=self.anchor)

    def nearest_frames(self, header, scrolled, k=4):
        cands = [fn for fn in self.frames if self.scroll[fn] is not None
                 and self.header_center(fn, header) is not None]
        return sorted(cands, key=lambda fn: abs(self.scroll[fn] - scrolled))[:k]


def rebuild_flow(lang, name, geo, header_images):
    r = sr.read_flow(name, sr.CONVERTED)
    data, images, pos = r["data"], dict(r["images"]), dict(r["pos"])
    steps = data["steps"]
    lo, hi = SHIFT[name]
    old_seg = steps[lo - 1:hi]
    cat = CATEGORY[lang]
    tops = {h: (LAYOUT[lang]["header_x"] + sr.offset(lang)[0], y) for h, y in geo.tops.items()}
    new_seg, log, stations = [], [], []
    delta, scrolled = (0, 0), 0
    pending, last_locator = None, None
    for s in old_seg:
        t = s["type"]
        if t == "find_click" and findtarget.template(s) in cat:
            tname = findtarget.template(s)
            header = cat[tname]
            old_tgt = dict(findtarget.target(s))
            if (old_tgt.get("limit") or {}).get("kind") == "origin":
                off, fn = geo.offsets(header, tname, old_tgt, origin=last_locator)
                delta = off
                log.append(f"刪 首列 {tname} (偏移 {off} 於 f{fn})")
                continue
            off, fn = geo.offsets(header, tname, old_tgt)
            delta = off
            last_locator = old_tgt
            band = geo.band_rect(header, scrolled)
            ns = {"type": "find_click",
                  "target": findtarget.make_target(header, limit=band,
                                                   pick={"kind": "top", "n": 1}),
                  "action": "none", "timeout": s.get("timeout", 10),
                  "interval": s.get("interval", 0.5),
                  "onNotFound": s.get("onNotFound", "skip"), "updateOrigin": True,
                  "offsetX": 0, "offsetY": 0}
            new_seg.append(ns)
            pending = {"header": header, "points": [], "last": (0, 0), "scrolled": scrolled,
                       "band": band, "expected": (tops[header][0], tops[header][1] - scrolled)}
            stations.append(pending)
            log.append(f"找 {tname} → 定位 {header} 窄帶 y≈{tops[header][1] - scrolled}"
                       f" (捲 {scrolled}; 列名偏移 {off} 於 f{fn})")
            continue
        if t == "click" and s.get("mode") == "prev":
            ns = dict(s)
            ns["x"], ns["y"] = s["x"] + delta[0], s["y"] + delta[1]
            delta = (0, 0)
            new_seg.append(ns)
            if pending is not None:
                last = (pending["last"][0] + ns["x"], pending["last"][1] + ns["y"])
                pending["points"].append(last)
                pending["last"] = last
            continue
        if t == "drag" and s.get("mode") == "prev":
            ns = dict(s)
            ns["x1"], ns["y1"] = s["x1"] + delta[0], s["y1"] + delta[1]
            ns["x2"], ns["y2"] = s["x2"] + delta[0], s["y2"] + delta[1]
            delta = (0, 0)
            new_seg.append(ns)
            scrolled += s["y1"] - s["y2"]
            pending = None
            continue
        new_seg.append(dict(s))
    checks = []
    for st in stations:
        rows = []
        for fn in geo.nearest_frames(st["header"], st["scrolled"]):
            drift = geo.scroll[fn] - st["scrolled"]
            band = geo.band_rect(st["header"], st["scrolled"] + drift)
            tgt = findtarget.make_target(st["header"], limit=band, pick={"kind": "top", "n": 1})
            hc = geo.header_center(fn, st["header"])
            per = {}
            for s in sr.PICK_SCALES:
                f = geo.find(fn, tgt, s)
                e = {"found": f.picked is not None, "n": len(f.matches)}
                if f.picked is not None:
                    c = sr.center(f.picked.box)
                    c1 = (c[0] / s, c[1] / s)
                    e["center"] = [round(c1[0], 1), round(c1[1], 1)]
                    e["is_header"] = hc is not None and abs(c1[1] - hc[1]) <= HEADER_TOL
                per[str(s)] = e
            pts, hit = [], None
            if hc is not None and st["points"]:
                sw = geo.swaps(fn)
                for dx, dy in st["points"]:
                    p = (hc[0] + dx, hc[1] + dy)
                    near = min(sw, key=lambda c: (c[0] - p[0]) ** 2 + (c[1] - p[1]) ** 2) if sw else None
                    d = ((near[0] - p[0]) ** 2 + (near[1] - p[1]) ** 2) ** 0.5 if near else None
                    pts.append((p, near, round(d, 1) if d is not None else None))
                hit = all(x[2] is not None and x[2] <= SWAP_TOL for x in pts)
            ok = (hc is not None and all(e.get("is_header") for e in per.values())
                  and (hit is None or hit))
            rows.append({"frame": fn, "drift": drift, "header": hc, "scales": per,
                         "points": pts, "ok": ok})
        checks.append({"header": st["header"], "scrolled": st["scrolled"], "rows": rows,
                       "ok": any(r["ok"] for r in rows)})
    steps[lo - 1:hi] = new_seg
    for n, b in header_images.items():
        if n != "_swap":
            images[n] = b
    data.pop("flowFormat", None)
    out_path = bp.flow_path(name, sr.CONVERTED)
    missing = flowfile.write(out_path, data, images, pos)
    assert not missing, missing
    back = flowfile.read(out_path)
    gone = sorted(set(r["images"]) - set(back["images"]))
    return {"flow": name, "before": len(old_seg), "after": len(new_seg),
            "steps_total": len(back["data"]["steps"]), "log": log, "checks": checks,
            "tops": tops, "templates_gone": gone, "templates": len(back["images"])}


def stage_build(lang):
    conv = sr.load(os.path.join(sr.RESULTS, f"convert_{lang}.json"))
    ev = sr.LANGS[lang]["evening"]
    region = sr.read_flow(ev, sr.CONVERTED)["data"]["scanRegion"]
    anchor = tuple(conv[ev]["pair"]["new_anchor"])
    header_images = {}
    for n in [*HEADERS[lang]["crops"], "_swap"]:
        with open(os.path.join(sr.TEMPLATES, lang, n + ".png"), "rb") as f:
            header_images[n] = f.read()
    old_images = {}
    for name in (sr.LANGS[lang]["morning"], ev):
        for n, b in sr.read_flow(name, sr.CONVERTED)["images"].items():
            if n in CATEGORY[lang]:
                old_images.setdefault(n, b)
    tmp = tempfile.mkdtemp(prefix="sr_build_")
    out = {}
    try:
        hub = bp.make_hub({**old_images, **header_images}, [*old_images, *header_images], tmp)
        geo = Geometry(lang, hub, sr.place(lang, region), anchor, region)
        print(f"[{lang}] 標題頂端位置 {geo.tops}")
        print(f"[{lang}] 捲動量: " + ", ".join(f"{fn[0]}f{fn[1]}:{v}" for fn, v in geo.scroll.items()))
        for name in (sr.LANGS[lang]["morning"], ev):
            rec = rebuild_flow(lang, name, geo, header_images)
            out[name] = rec
            print(f"[{name}] 換班段 {rec['before']} → {rec['after']} 步 (全流程 {rec['steps_total']}); "
                  f"退場範本 {rec['templates_gone']}; 標題頂端位置 {rec['tops']}")
            for line in rec["log"]:
                print("    " + line)
            for c in rec["checks"]:
                tag = "OK" if c["ok"] else "NG"
                print(f"    {tag} {c['header']} 捲{c['scrolled']}:")
                for row in c["rows"]:
                    print(f"        {row['frame']} 偏{row['drift']} 標題{row['header']} " + ", ".join(
                        f"×{s}:{'標題' if e.get('is_header') else ('別的' if e['found'] else '無')}/{e['n']}個"
                        for s, e in row["scales"].items()) + " | " + ", ".join(
                        f"{p}->⇌{n} {d}px" for p, n, d in row["points"]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sr.dump(os.path.join(sr.RESULTS, f"shift_{lang}.json"), out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=("cn", "tw"))
    args = ap.parse_args()
    for lang in ([args.lang] if args.lang else ["tw", "cn"]):
        stage_build(lang)


if __name__ == "__main__":
    main()
