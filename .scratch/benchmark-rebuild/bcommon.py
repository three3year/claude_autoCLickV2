"""幀號一律從頭順序讀 (demo4、demo6 幀率不固定, 跳轉讀幀不準)。"""
from __future__ import annotations

import hashlib
import json
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TMP = os.path.join(HERE, "tmp")
FRAMES = os.path.join(TMP, "frames")
CANDIDATES = os.path.join(TMP, "candidates")
VIDEO_DIR = r"C:\Users\three\我的電腦\oCam Video"
FLOWS_DIR = os.path.join(ROOT, "flows")
SCRATCH = os.path.dirname(HERE)

FLOWS = {"早_簡中": "cn", "晚_簡中": "cn", "早_繁中": "tw", "晚_繁中": "tw"}
VIDEOS = {"cn": ["demo6", "demo5", "demo4", "add1", "add3", "add5"],
          "tw": ["demo2", "demo3", "add2", "add4"]}
CURSOR_SCALES = {"cn": (1.0,), "tw": (1.1, 1.13)}


def lang_of_video(video):
    return next(lang for lang, vs in VIDEOS.items() if video in vs)


def imread(path, flags=cv2.IMREAD_COLOR):
    return cv2.imdecode(np.fromfile(path, np.uint8), flags)


def imwrite(path, img):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ext = os.path.splitext(path)[1] or ".png"
    params = [cv2.IMWRITE_PNG_COMPRESSION, 9] if ext.lower() == ".png" else []
    cv2.imencode(ext, img, params)[1].tofile(path)


def dump(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def flow_templates(flow):
    d = os.path.join(FLOWS_DIR, flow, "templates")
    return {os.path.splitext(n)[0]: imread(os.path.join(d, n))
            for n in sorted(os.listdir(d)) if n.lower().endswith(".png")}


def template_path(flow, name):
    return os.path.join(FLOWS_DIR, flow, "templates", name + ".png")


def lang_templates(lang):
    out = {}
    for flow, lg in FLOWS.items():
        if lg != lang:
            continue
        for name, img in flow_templates(flow).items():
            key = hashlib.md5(cv2.imencode(".png", img)[1].tobytes()).hexdigest()[:12]
            if key not in out:
                out[key] = (img, [])
            out[key][1].append((flow, name))
    return out


def frame_path(video, n):
    return os.path.join(FRAMES, f"{video}_{n:05d}.png")


def read_frames(video, wanted):
    wanted = set(wanted)
    out = {}
    for n in list(wanted):
        p = frame_path(video, n)
        if os.path.isfile(p):
            out[n] = imread(p)
            wanted.discard(n)
    if not wanted:
        return out
    cap = cv2.VideoCapture(os.path.join(VIDEO_DIR, video + ".mp4"))
    n, last = 0, max(wanted)
    while n <= last and cap.grab():
        if n in wanted:
            ok, img = cap.retrieve()
            if not ok:
                raise SystemExit(f"讀不到 {video} 第 {n} 幀")
            imwrite(frame_path(video, n), img)
            out[n] = img
        n += 1
    cap.release()
    missing = sorted(wanted - set(out))
    if missing:
        raise SystemExit(f"{video} 沒有第 {missing[:5]} 幀")
    return out


def frame(video, n):
    return read_frames(video, [n])[n]


def iter_frames(video, stride=1):
    cap = cv2.VideoCapture(os.path.join(VIDEO_DIR, video + ".mp4"))
    n = 0
    while cap.grab():
        if n % stride == 0:
            ok, img = cap.retrieve()
            if ok:
                yield n, img
        n += 1
    cap.release()


def gray(img):
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def match_map(scene, tpl):
    r = cv2.matchTemplate(gray(scene), gray(tpl), cv2.TM_CCOEFF_NORMED)
    r[~np.isfinite(r)] = 0
    return r


def peaks(scene, tpl, thr=0.6, top=12):
    r = match_map(scene, tpl)
    th, tw = tpl.shape[:2]
    out = []
    r = r.copy()
    for _ in range(top):
        _, mx, _, (x, y) = cv2.minMaxLoc(r)
        if mx < thr:
            break
        out.append((round(float(mx), 4), int(x), int(y), tw, th))
        x0, y0 = max(0, x - tw // 2), max(0, y - th // 2)
        r[y0:y + th // 2 + 1, x0:x + tw // 2 + 1] = -1
    return out


def best(scene, tpl):
    r = match_map(scene, tpl)
    _, mx, _, (x, y) = cv2.minMaxLoc(r)
    th, tw = tpl.shape[:2]
    return round(float(mx), 4), (int(x), int(y), tw, th)


def center(box):
    x, y, w, h = box
    return [round(x + w / 2, 1), round(y + h / 2, 1)]


def color_diff(scene, box, tpl):
    x, y, w, h = box
    patch = scene[y:y + h, x:x + w].astype(np.float32)
    if patch.shape[:2] != tpl.shape[:2]:
        return 255.0
    return float(np.abs(patch - tpl.astype(np.float32)).mean())


_cursor = {}


def _cursor_sprites(lang):
    if lang not in _cursor:
        spr = imread(os.path.join(HERE, "cursor_sprite.png"), cv2.IMREAD_GRAYSCALE)
        msk = imread(os.path.join(HERE, "cursor_mask.png"), cv2.IMREAD_GRAYSCALE)
        out = []
        for s in CURSOR_SCALES[lang]:
            g = cv2.resize(spr, None, fx=s, fy=s, interpolation=cv2.INTER_LINEAR)
            m = cv2.resize(msk, None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST)
            m = (m > 0).astype(np.uint8) * 255
            ys, xs = np.nonzero(m)
            out.append((g, m, (int(xs.min()), int(ys.min()),
                               int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))))
        _cursor[lang] = out
    return _cursor[lang]


CURSOR_THRESHOLD = 0.62


def find_cursor(img, lang):
    g = gray(img)
    found = None
    for spr, m, (bx, by, bw, bh) in _cursor_sprites(lang):
        r = cv2.matchTemplate(g, spr, cv2.TM_CCOEFF_NORMED, mask=m)
        r[~np.isfinite(r)] = 0
        _, mx, _, (x, y) = cv2.minMaxLoc(r)
        if mx >= CURSOR_THRESHOLD and (found is None or mx > found[0]):
            found = (mx, (x + bx, y + by, bw, bh))
    return None if found is None else found[1]


def overlaps(a, b, pad=0):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw + pad <= bx or bx + bw + pad <= ax
                or ay + ah + pad <= by or by + bh + pad <= ay)


def cursor_touches(img, lang, boxes, pad=4):
    c = find_cursor(img, lang)
    return c is not None and any(overlaps(c, b, pad) for b in boxes)


def unstable(video, n, boxes, k=2, thr=6.0):
    fr = read_frames(video, [m for m in (n - k, n, n + k) if m >= 0])
    if n - k < 0:
        return False
    a = gray(fr[n]).astype(np.float32)
    for m in (n - k, n + k):
        if m not in fr:
            continue
        b = gray(fr[m]).astype(np.float32)
        for x, y, w, h in boxes:
            if float(np.abs(a[y:y + h, x:x + w] - b[y:y + h, x:x + w]).mean()) > thr:
                return True
    return False


_busy_tpls = {}

BUSY_ON = 0.6


def busy_on(img, lang):
    if lang not in _busy_tpls:
        _busy_tpls[lang] = {cv2.imencode(".png", t)[1].tobytes(): t
                            for f, lg in FLOWS.items() if lg == lang
                            for n, t in flow_templates(f).items() if n == "忙碌指示"}
    return any(best(img, t)[0] >= BUSY_ON for t in _busy_tpls[lang].values())


def scene_quality(video, n):
    m = max(n, 2)
    fr = read_frames(video, [m - 2, m, m + 2])
    g = [cv2.resize(gray(fr[k]), None, fx=0.5, fy=0.5).astype(np.float32) for k in (m - 2, m, m + 2)]
    d = max(float(np.abs(g[1] - g[0]).mean()), float(np.abs(g[1] - g[2]).mean()))
    return d, float(cv2.Laplacian(g[1], cv2.CV_32F).var())


def calm_scene(video, n, max_diff=10.0, min_sharp=800.0):
    d, sharp = scene_quality(video, n)
    return d <= max_diff and sharp >= min_sharp
