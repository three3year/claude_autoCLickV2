from __future__ import annotations

import argparse
import os
import shutil
import tempfile

import srcommon as sr
from srcommon import bp

import calibration  # noqa: E402
import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402

SHIFT = {"早_繁中": (90, 116), "晚_繁中": (31, 59), "早_簡中": (100, 126), "晚_簡中": (31, 59)}
CREDIT = os.path.join(sr.HERE, "..", "credit-store-templates")


def tol_of(size):
    return max(6.0, 0.25 * min(size))


def credit_frames(lang):
    ann = sr.load(os.path.join(CREDIT, "annotations.json"))
    out = {}
    for fr in ann["frames"]:
        if fr["set"] != lang:
            continue
        path = os.path.join(CREDIT, "frames", fr["id"] + ".png")
        if not os.path.isfile(path):
            continue
        for card in fr["cards"]:
            if card.get("soldOut"):
                continue
            out.setdefault("採購_" + card["name"], []).append((path, tuple(card["center"])))
    return out


def flow_targets(name, data):
    lo, hi = SHIFT[name]
    out = []
    for i, s in enumerate(data["steps"]):
        no = i + 1
        if lo <= no <= hi:
            continue
        for key, t in findtarget.step_targets(s):
            if key == findtarget.CONFIRM_TARGET and not findtarget.uses_confirm_target(s):
                continue
            out.append((f"第 {no} 步 {key}", t))
    busy = flowfile.busy_target(data)
    if busy:
        out.append(("忙碌指示", busy))
    cal = calibration.flow_pair(data)
    for n in cal["pair"]:
        out.append(("校準對", {"template": n}))
    fb = calibration.fallback_pair(cal)
    for n in fb["pair"]:
        out.append(("備用校準對", {"template": n}))
    return out


LOW_BITRATE = {"demo1"}


def pick_frames(name, have, credit, per):
    rows = have.get(name, [])
    good = [r for r in rows if r[0] not in LOW_BITRATE]
    if good:
        rows = good
    if not rows and name in credit:
        rows = [("credit", p, c) for p, c in credit[name]]
    if not rows:
        return []
    if len(rows) <= per:
        return rows
    step = len(rows) / per
    return [rows[int(i * step)] for i in range(per)]


def load_frame(row):
    if row[0] == "credit":
        return bp.read_img(row[1])
    return sr.frame(row[0], row[1])


def replay(lang, per):
    out = {}
    have = sr.known_frames(lang)
    credit = credit_frames(lang)
    conv = sr.load(os.path.join(sr.RESULTS, f"convert_{lang}.json"))
    for name in (sr.LANGS[lang]["morning"], sr.LANGS[lang]["evening"]):
        r = sr.read_flow(name, sr.CONVERTED)
        data, images = r["data"], r["images"]
        sizes = {n: bp.decode(b).shape[1::-1] for n, b in images.items()}
        region = data["scanRegion"]
        anchor = tuple(conv[name]["pair"]["new_anchor"])
        place = sr.place(lang, region)
        tmp = tempfile.mkdtemp(prefix="sr_replay_")
        rows, no_video, need_origin = [], [], []
        try:
            hub = bp.make_hub(images, sorted(images), tmp)
            seen = set()
            for where, tgt in flow_targets(name, data):
                tname = tgt.get("template", "")
                key = (tname, str(tgt.get("limit")), str(tgt.get("pick")), bool(tgt.get("colorCheck")))
                if key in seen:
                    continue
                seen.add(key)
                if findtarget.needs_origin(tgt):
                    need_origin.append((where, tname))
                    continue
                frames = pick_frames(tname, have, credit, per)
                if not frames:
                    no_video.append((where, tname))
                    continue
                for row in frames:
                    canvas, org = place(load_frame(row))
                    base = None
                    rec = {"where": where, "template": tname, "frame": list(row[:2]),
                           "color": bool(tgt.get("colorCheck")), "scales": {}}
                    for s in sr.SCALES:
                        f = sr.find_scaled(hub, tgt, canvas, org, anchor, s)
                        e = {"found": f.picked is not None,
                             "best": round(float(f.query.score), 3) if f.query is not None else None,
                             "failed": f.failed, "matches": len(f.matches)}
                        if f.picked is not None:
                            c = sr.center(f.picked.box)
                            e["center_x1"] = [round(c[0] / s, 1), round(c[1] / s, 1)]
                            e["score"] = round(float(f.picked.score), 3)
                            if f.picked.color is not None:
                                e["color"] = round(float(f.picked.color), 3)
                            if s == 1.0:
                                base = e["center_x1"]
                        if f.rejected:
                            e["rejected_colors"] = [round(float(m.color), 3) for m in f.rejected]
                        rec["scales"][str(s)] = e
                    ok = all(e["found"] for e in rec["scales"].values())
                    if ok and base is not None:
                        tol = tol_of(sizes.get(tname, (24, 24)))
                        for e in rec["scales"].values():
                            d = max(abs(e["center_x1"][0] - base[0]), abs(e["center_x1"][1] - base[1]))
                            e["drift"] = round(d, 1)
                            if d > tol:
                                ok = False
                    at1 = rec["scales"]["1.0"]["found"]
                    rec["kind"] = "ok" if ok else ("material" if not at1 else "scale")
                    rec["ok"] = ok
                    rows.append(rec)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        bad = [x for x in rows if x["kind"] == "scale"]
        material = [x for x in rows if x["kind"] == "material"]
        out[name] = {"rows": rows, "no_video": no_video, "need_origin": need_origin,
                     "n_rows": len(rows), "n_bad": len(bad), "n_material": len(material)}
        print(f"[{name}] 重放 {len(rows)} 張影格×5 倍率: 通過 {len(rows) - len(bad) - len(material)}, "
              f"縮放不過 {len(bad)}, 影格對不上 {len(material)} "
              f"({', '.join(sorted({x['template'] for x in material}))}); 影片無對應 {len(no_video)} "
              f"({', '.join(sorted({t for _, t in no_video}))}); 需原點略過 {len(need_origin)}")
        for x in bad:
            print(f"    ✘ {x['where']} {x['template']} {x['frame']}: " + ", ".join(
                f"×{s}:{'找到' if e['found'] else '找不到'}/{e.get('failed')}/{e.get('best')}/漂{e.get('drift')}"
                for s, e in x["scales"].items()))
        margins = {}
        for x in rows:
            if not x["color"]:
                continue
            m = margins.setdefault(x["template"], {"own": [], "other": []})
            for s, e in x["scales"].items():
                if "color" in e:
                    m["own"].append((e["color"], s, x["frame"]))
                for c in e.get("rejected_colors", []):
                    m["other"].append((c, s, x["frame"]))
        for t, m in margins.items():
            own = min(m["own"])[0] if m["own"] else None
            other = max(m["other"])[0] if m["other"] else None
            m["margin"] = round(own - other, 3) if own is not None and other is not None else None
            print(f"    比色 {t}: 本尊最低 {own} 他者最高 {other} 餘裕 {m['margin']}")
        out[name]["color_margins"] = margins
    sr.dump(os.path.join(sr.RESULTS, f"replay_{lang}.json"), out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=("cn", "tw"))
    ap.add_argument("--per", type=int, default=3)
    args = ap.parse_args()
    for lang in ([args.lang] if args.lang else ["tw", "cn"]):
        replay(lang, args.per)


if __name__ == "__main__":
    main()
