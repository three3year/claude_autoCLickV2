from __future__ import annotations

import os
import shutil
import tempfile

import srcommon as sr
from srcommon import bp

import flowfile  # noqa: E402
from automation import findtarget, pickcheck  # noqa: E402

CASES = {
    "tw": {"flow": "早_繁中", "friends": "好友列表", "credit": "信用交易所"},
    "cn": {"flow": "早_簡中", "friends": "好友列表", "credit": "信用交易所"},
}


def targets_named(data, name):
    for i, s in enumerate(data["steps"]):
        for key, t in findtarget.step_targets(s):
            if t.get("template") == name:
                yield i + 1, key, t


def adjust(lang):
    cfg = CASES[lang]
    name = cfg["flow"]
    r = sr.read_flow(name, sr.CONVERTED)
    data, images, pos = r["data"], r["images"], r["pos"]
    conv = sr.load(os.path.join(sr.RESULTS, f"convert_{lang}.json"))
    anchor = tuple(conv[name]["pair"]["new_anchor"])
    region = data["scanRegion"]
    place = sr.place(lang, region)
    have = sr.known_frames(lang)
    rec = {"flow": name, "changes": []}
    tmp = tempfile.mkdtemp(prefix="sr_adj_")
    try:
        hub = bp.make_hub({n: images[n] for n in (cfg["friends"], cfg["credit"])},
                          [cfg["friends"], cfg["credit"]], tmp)
        fr = cfg["friends"]
        size = bp.decode(images[fr]).shape[1::-1]
        found = None
        for v, fn in have.get(fr, []):
            canvas, org = place(sr.frame(v, fn))
            f = sr.find_scaled(hub, {"template": fr, "colorCheck": True}, canvas, org, anchor, 1.0)
            if f.picked is not None:
                found = (v, fn, f.picked.box, canvas, org)
                break
        assert found, f"{lang}: 已知影格上找不到 {fr}"
        v, fn, box, canvas, org = found
        w, h = size
        mx, my = int(round(w * 0.4)), int(round(h * 0.45))
        scr = (box[0] - mx, box[1] - my, box[2] + 2 * mx, box[3] + 2 * my)
        rect = findtarget.fixed_rect_from_screen(scr, anchor, 1.0)
        assert not pickcheck.rect_margin({"template": fr, "limit": rect}, size)
        for no, key, t in targets_named(data, fr):
            old = {"limit": dict(t.get("limit") or {}), "colorCheck": t.get("colorCheck")}
            t.pop("colorCheck", None)
            t["limit"] = dict(rect)
            rec["changes"].append({"step": no, "key": key, "template": fr, "old": old,
                                   "new": {"limit": rect, "colorCheck": None}})
        rows = []
        for s in sr.SCALES:
            f = sr.find_scaled(hub, {"template": fr, "limit": rect}, canvas, org, anchor, s)
            rows.append((s, f.picked is not None, len(f.matches),
                         round(float(f.picked.score), 3) if f.picked else None))
        rec["friends_check"] = {"frame": [v, fn], "rect": rect, "rows": rows}
        print(f"[{name}] {fr}: 矩形 {rect} (範本 {size}); " + ", ".join(
            f"×{s}:{'找到' if ok else '找不到'}/{n}個/{sc}" for s, ok, n, sc in rows))
        cr = cfg["credit"]
        for no, key, t in targets_named(data, cr):
            if t.get("colorCheck"):
                rec["changes"].append({"step": no, "key": key, "template": cr,
                                       "old": {"colorCheck": True}, "new": {"colorCheck": None}})
                t.pop("colorCheck", None)
        rows = []
        for v, fn in have.get(cr, [])[:3]:
            canvas, org = place(sr.frame(v, fn))
            tgt = next(t for _, _, t in targets_named(data, cr))
            per = []
            for s in sr.SCALES:
                f = sr.find_scaled(hub, tgt, canvas, org, anchor, s)
                per.append((s, f.picked is not None, len(f.matches)))
            rows.append({"frame": [v, fn], "rows": per})
            print(f"[{name}] {cr} {v} f{fn}: " + ", ".join(
                f"×{s}:{'找到' if ok else '找不到'}/{n}個" for s, ok, n in per))
        rec["credit_check"] = rows
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    data.pop("flowFormat", None)
    out_path = bp.flow_path(name, sr.CONVERTED)
    missing = flowfile.write(out_path, data, images, pos)
    assert not missing, missing
    sr.dump(os.path.join(sr.RESULTS, f"adjust_{lang}.json"), rec)
    print(f"[{name}] 改了 {len(rec['changes'])} 個找圖目標")


if __name__ == "__main__":
    for lang in ("tw", "cn"):
        adjust(lang)
