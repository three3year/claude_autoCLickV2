import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
for p in ("tools", "app", "src"):
    sys.path.insert(0, os.path.join(ROOT, p))

from video_to_flow import verify, video  # noqa: E402
from automation import imgio  # noqa: E402
from subject_detection.library import load_default_config  # noqa: E402

VIDEO = r"C:\Users\three\我的電腦\oCam Video\demo2.mp4"
LIVE = os.path.join(os.environ["USERPROFILE"], "AutoClick", "早_繁中", "templates")
R = 160
BACK = (12, 6, 3)


def main(cand_path, out_path):
    sys.stdout.reconfigure(encoding="utf-8")
    cands = json.load(open(cand_path, encoding="utf-8"))["candidates"]
    names = sorted(fn[:-4] for fn in os.listdir(LIVE) if fn.endswith(".png"))
    imgs = {n: imgio.imread(os.path.join(LIVE, n + ".png")) for n in names}
    eng = verify.make_engine()
    det = verify.Checker(eng, imgs, {}, [], {}, load_default_config(), None, (1, 1)).detector
    want = {}
    for c in cands:
        for b in BACK:
            want.setdefault(max(0, c["frame"] - b), []).append(c)
    rows = {c["id"]: {"frame": c["frame"], "x": c["x"], "y": c["y"], "kind": c["kind"],
                      "conf": c["confidence"], "hits": {}} for c in cands}
    for f, img in video.iter_frames(VIDEO):
        if f > max(want):
            break
        for c in want.get(f, []):
            x0, y0 = max(0, c["x"] - R), max(0, c["y"] - R)
            crop = img[y0:c["y"] + R, x0:c["x"] + R]
            for n in names:
                if imgs[n].shape[0] > crop.shape[0] or imgs[n].shape[1] > crop.shape[1]:
                    continue
                r = det.query(n, crop, expected_scale=1.0)
                for m in r.matches:
                    bx, by, bw, bh = m.box
                    bx, by = bx + x0, by + y0
                    inside = bx - 10 <= c["x"] <= bx + bw + 10 and by - 10 <= c["y"] <= by + bh + 10
                    cx, cy = bx + bw // 2, by + bh // 2
                    if inside or abs(cx - c["x"]) + abs(cy - c["y"]) <= 40:
                        prev = rows[c["id"]]["hits"].get(n)
                        if prev is None or m.score > prev["score"]:
                            rows[c["id"]]["hits"][n] = {"score": round(float(m.score), 3),
                                                        "box": [int(bx), int(by), int(bw), int(bh)],
                                                        "frame": f}
    json.dump(rows, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for cid, r in rows.items():
        best = sorted(r["hits"].items(), key=lambda kv: -kv[1]["score"])[:3]
        print(f"#{int(cid):03d} f{r['frame']} ({r['x']},{r['y']}) {r['kind']} {r['conf']:.2f} → "
              + ("、".join(f"{n} {h['score']} {h['box']}" for n, h in best) or "（無）"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
