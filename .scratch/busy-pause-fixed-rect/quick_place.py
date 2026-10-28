"""「交流中」範本: 線索板底部中間的「线索交流开启中／線索交流開啟中」字樣中間壓著一個會轉的
圓環 (圓點繞著轉、外圈會脈動), 只截左邊不會動的那段: 橘線末端＋第一個字「线／線」,
右緣停在第二個字之前 (圓點最左約到第二個字)。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile

import common

import cv2  # noqa: E402

import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402

NAME = "交流中"
QUICK = "快速置入"
TIMEOUT = 1.5
MARGIN = 40

SOURCE = {
    "cn": ("demo6", 1090, (770, 788, 74, 26)),
    "tw": ("demo2", 1140, (870, 886, 82, 30)),
}
BAND = {"cn": (790, 812, 600, 1200), "tw": (888, 912, 500, 1400)}
BOARD = {
    "cn": [("demo6", 900, 1200), ("demo5", 1200, 1560)],
    "tw": [("demo2", 900, 1260)],
}
OTHER_STRIDE = 40


def exchange_line(img, lang):
    y0, y1, x0, x1 = BAND[lang]
    hsv = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    m = ((hsv[..., 0] > 3) & (hsv[..., 0] < 25) & (hsv[..., 1] > 150)
         & (hsv[..., 2] > 150))
    return int(m.sum(1).max()) > 200


def quick_index(steps):
    hits = [i for i, s in enumerate(steps)
            if s.get("type") == "find_click" and findtarget.template(s) == QUICK]
    if len(hits) != 1:
        raise SystemExit(f"快速置入步驟應該剛好一個, 找到 {len(hits)} 個")
    return hits[0]


def already_done(steps, i):
    return (i >= 2 and steps[i - 1].get("type") == "branch_or"
            and findtarget.template(steps[i - 2]) == NAME)


def cond_step(rect):
    return {"type": "find_click", "interval": 0.3, "confirm": "none", "action": "none",
            "timeout": TIMEOUT, "onNotFound": "skip", "offsetX": 0, "offsetY": 0,
            "target": findtarget.make_target(NAME, limit=rect, color=True),
            "button": "left", "clicks": 1, "updateOrigin": False}


def rebuild(steps, rect):
    i = quick_index(steps)
    if already_done(steps, i):
        out = [dict(s) for s in steps]
        out[i - 2] = cond_step(rect)
        return out, i - 3
    new = steps[:i] + [{"type": "branch_start"}, cond_step(rect),
                       {"type": "branch_or"}, steps[i], {"type": "branch_end"}]
    return new + steps[i + 1:], i


def cut(frames, lang):
    video, n, (x, y, w, h) = SOURCE[lang]
    return frames.get(video, n)[y:y + h, x:x + w].copy()


def settled(img, lang, tmpl):
    _video, _n, (x, y, w, h) = SOURCE[lang]
    roi = cv2.cvtColor(img[y - 3:y + h + 3, x - 3:x + w + 3], cv2.COLOR_BGR2GRAY)
    t = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY)
    return float(cv2.matchTemplate(roi, t, cv2.TM_CCOEFF_NORMED).max()) >= 0.9


def samples(frames, lang, quick_img, tmpl):
    out = []
    q = cv2.cvtColor(quick_img, cv2.COLOR_BGR2GRAY)
    seen = set()
    for video, a, b in BOARD[lang]:
        for n in range(a, b, 4):
            img = frames.get(video, n)
            seen.add((video, n))
            if exchange_line(img, lang):
                out.append((video, n, "exchange" if settled(img, lang, tmpl)
                            else "transition"))
                continue
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            if float(cv2.matchTemplate(g, q, cv2.TM_CCOEFF_NORMED).max()) >= 0.9:
                out.append((video, n, "board_idle"))
    if lang == "cn" and ("demo6", 952) not in seen:
        out.append(("demo6", 952, "board_idle"))
    for video in common.LANGS[lang]["videos"]:
        cap = cv2.VideoCapture(os.path.join(common.VIDEO_DIR, video + ".mp4"))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        for n in range(0, total, OTHER_STRIDE):
            if (video, n) in seen:
                continue
            if exchange_line(frames.get(video, n), lang):
                continue
            out.append((video, n, "other"))
    return out


def evaluate(lang, hub, cond, quick, frames, place, rows_in):
    rows = []
    for video, n, kind in rows_in:
        canvas, org = place(frames.get(video, n))
        fe = findtarget.find(cond, hub, canvas, org, origin=None, scale=1.0)
        row = {"video": video, "frame": n, "kind": kind,
               "exchange": fe.picked is not None,
               "score": round(fe.picked.score, 3) if fe.picked else None,
               "color": (round(fe.picked.color, 3) if fe.picked and fe.picked.color
                         is not None else None),
               "best": None if fe.query is None else round(fe.query.score, 3),
               "failed": fe.failed}
        if kind == "other":
            row["ok"] = not row["exchange"]
        else:
            fq = findtarget.find(quick, hub, canvas, org, origin=None, scale=1.0)
            row["branch"] = 1 if fe.picked else (2 if fq.picked else None)
            if kind == "transition":
                row["ok"] = True
            elif kind == "exchange":
                row["ok"] = row["branch"] == 1
            else:
                row["ok"] = row["branch"] != 1
        rows.append(row)
    return rows


def summarize(lang, rows):
    out = {}
    for kind in ("exchange", "board_idle", "other", "transition"):
        rs = [r for r in rows if r["kind"] == kind]
        hit = [r for r in rs if r["exchange"]]
        sc = [r["score"] for r in hit]
        cc = [r["color"] for r in hit if r["color"] is not None]
        miss_best = [r["best"] for r in rs if not r["exchange"] and r["best"] is not None]
        out[kind] = {"n": len(rs), "exchange_found": len(hit), "ok": sum(r["ok"] for r in rs),
                     "score": [min(sc), max(sc)] if sc else None,
                     "color": [min(cc), max(cc)] if cc else None,
                     "best_when_not_found": max(miss_best) if miss_best else None}
        print(f"  [{lang}] {kind}: {out[kind]['ok']}/{len(rs)} 符合；交流中找到 {len(hit)}"
              + (f"（分數 {min(sc)}–{max(sc)}" + (f"、比色 {min(cc)}–{max(cc)}" if cc else "")
                 + "）" if sc else "")
              + (f"；沒找到時最高分 {out[kind]['best_when_not_found']}"
                 if out[kind]["best_when_not_found"] is not None else ""))
    return out


def run_lang(lang, args, frames):
    path = common.flow_path(common.LANGS[lang]["flow"], args.flows)
    r = flowfile.read(path)
    region = r["data"]["scanRegion"]
    video, n, box = SOURCE[lang]
    rect = common.video_box_to_rect(box, lang, region, MARGIN)
    img = cut(frames, lang)
    steps = r["data"]["steps"]
    quick = findtarget.target(steps[quick_index(steps)])
    cond = cond_step(rect)["target"]
    tmp = tempfile.mkdtemp(prefix="quick_place_")
    try:
        imgs = {NAME: common.encode(img), QUICK: r["images"][QUICK]}
        print(f"[{lang}] 標註影格…", flush=True)
        rows_in = samples(frames, lang, common.decode(r["images"][QUICK]), img)
        print(f"[{lang}] 載入引擎…", flush=True)
        hub = common.make_hub(imgs, list(imgs), tmp)
        rows = evaluate(lang, hub, cond, quick, frames,
                        common.frame_region(lang, region), rows_in)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    summ = summarize(lang, rows)
    ok = all(r_["ok"] for r_ in rows)
    common.write_img(os.path.join(common.RESULTS, f"quick_place_{lang}.png"), img)
    return {"flow": os.path.basename(path), "source": {"video": video, "frame": n,
            "crop": box}, "rect": rect, "ok": ok, "summary": summ,
            "bad": [r_ for r_ in rows if not r_["ok"]]}, (path, r, rect, img)


def apply(path, r, rect, img, flows):
    steps, at = rebuild(r["data"]["steps"], rect)
    err = common.section_error(steps)
    if err:
        raise SystemExit(f"{os.path.basename(path)}: 區段不完整: {err}")
    images = dict(r["images"])
    images[NAME] = common.encode(img)
    if steps == r["data"]["steps"] and images == r["images"]:
        print(f"{os.path.basename(path)}: 已是新版, 不動")
        return at
    data = dict(r["data"], steps=steps)
    back = common.write_flow(path, data, images, r["pos"])
    if back["data"]["steps"] != steps:
        raise SystemExit("讀回的步驟與寫入的不同")
    print(f"{os.path.basename(path)}: 第 {at + 1} 步的快速置入換成分岔（第 {at + 1}–{at + 5} 步）")
    if common.sync_draft(path, os.path.dirname(flows)):
        print("    草稿與工作區已同步")
    return at


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--lang", choices=sorted(common.LANGS), action="append")
    ap.add_argument("--flows", default=common.FLOWS)
    args = ap.parse_args(argv)
    langs = args.lang or sorted(common.LANGS)

    os.makedirs(common.RESULTS, exist_ok=True)
    out_path = os.path.join(common.RESULTS, "quick_place.json")
    report = {}
    if os.path.isfile(out_path):
        with open(out_path, encoding="utf-8") as f:
            report = json.load(f)
    frames = common.Frames()
    built = {}
    try:
        for lang in langs:
            report[lang], built[lang] = run_lang(lang, args, frames)
    finally:
        frames.close()
    bad = [lang for lang in langs if not report[lang]["ok"]]
    for lang in bad:
        for r_ in report[lang]["bad"][:20]:
            print(f"  [{lang}] 不符: {r_}")
    if args.apply and not bad:
        common.preflight(args.flows, common.ticket_backup("07"))
        for lang in langs:
            report[lang]["at"] = apply(*built[lang], args.flows) + 1
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("通過" if not bad else f"**不通過**: {'、'.join(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
