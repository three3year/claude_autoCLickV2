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


def main(list_path, out_path):
    sys.stdout.reconfigure(encoding="utf-8")
    items = json.load(open(list_path, encoding="utf-8"))
    names = sorted({it[1] for it in items})
    imgs = {n: imgio.imread(os.path.join(LIVE, n + ".png")) for n in names}
    eng = verify.make_engine()
    det = verify.Checker(eng, imgs, {}, [], {}, load_default_config(), None, (1, 1)).detector
    want = {}
    for key, name, lo, hi in items:
        for f in range(lo, hi + 1):
            want.setdefault(f, []).append((key, name))
    best = {}
    for f, img in video.iter_frames(VIDEO):
        if f > max(want):
            break
        for key, name in want.get(f, []):
            r = det.query(name, img, expected_scale=1.0)
            if not r.matches:
                continue
            m = max(r.matches, key=lambda m: m.score)
            if key not in best or m.score > best[key]["score"]:
                best[key] = {"name": name, "frame": f, "box": [int(v) for v in m.box],
                             "score": round(float(m.score), 3), "n": len(r.matches),
                             "all": [[int(v) for v in x.box] for x in r.matches]}
    json.dump(best, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for key, name, lo, hi in items:
        b = best.get(key)
        print(f"{key}: {name} [{lo},{hi}] → "
              + (f"f{b['frame']} {b['box']} {b['score']} n={b['n']}" if b else "（找不到）"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
