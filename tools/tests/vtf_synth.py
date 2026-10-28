"""名稱刻意不叫 synth: tests/ 的引擎測試已有 synth.py, 同名模組會互相遮蔽。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "tools", ROOT / "app", ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

VIDEO_W, VIDEO_H = 480, 270


def make_button(w=48, h=36, seed=0):
    r = np.random.default_rng(seed)
    img = np.full((h, w, 3), r.integers(30, 90, 3, dtype=np.uint8), dtype=np.uint8)
    cv2.rectangle(img, (1, 1), (w - 2, h - 2),
                  tuple(int(c) for c in r.integers(150, 255, 3)), 2)
    for _ in range(4):
        p1 = (int(r.integers(4, w - 4)), int(r.integers(4, h - 4)))
        p2 = (int(r.integers(4, w - 4)), int(r.integers(4, h - 4)))
        cv2.line(img, p1, p2, tuple(int(c) for c in r.integers(120, 255, 3)), 2)
    cv2.circle(img, (w // 2, h // 2), min(w, h) // 4,
               tuple(int(c) for c in r.integers(120, 255, 3)), -1)
    return img


def make_background(w=VIDEO_W, h=VIDEO_H, seed=99):
    r = np.random.default_rng(seed)
    img = r.integers(0, 120, (h, w, 3), dtype=np.uint8)
    img = cv2.GaussianBlur(img, (0, 0), 3)
    for _ in range(10):
        p1 = (int(r.integers(0, w)), int(r.integers(0, h)))
        p2 = (int(r.integers(0, w)), int(r.integers(0, h)))
        cv2.rectangle(img, p1, p2, tuple(int(c) for c in r.integers(0, 200, 3)), -1)
    cv2.rectangle(img, BLANK[:2], (BLANK[0] + BLANK[2], BLANK[1] + BLANK[3]),
                  (70, 70, 70), -1)
    return img


BLANK = (10, 190, 120, 70)


def screen(buttons, seed=99, title=False):
    img = make_background(seed=seed)
    if title:
        buttons = list(buttons) + [(TITLE[n], *TITLE_POS[n]) for n in TITLE]
    for tpl, x, y in buttons:
        h, w = tpl.shape[:2]
        img[y:y + h, x:x + w] = tpl
    return img


def write_video(path, frames, fps=10):
    path = str(path)
    h, w = frames[0].shape[:2]
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    assert vw.isOpened(), "VideoWriter 開不起來"
    for f in frames:
        vw.write(f)
    vw.release()
    return path


def timeline(*segments):
    out = []
    for img, n in segments:
        out.extend([img] * n)
    return out


def make_out(root, name="out"):
    out = Path(root) / name
    out.mkdir(parents=True, exist_ok=True)
    return out


BUTTONS = {"開始": make_button(seed=1), "確定": make_button(seed=2),
           "下一步": make_button(seed=3)}
POS = {"開始": (60, 40), "確定": (300, 150), "下一步": (200, 60)}
FRAME = {"開始": 5, "確定": 20, "下一步": 35}
SCREENS = [("開始", 0, 15), ("確定", 15, 30), ("下一步", 30, 45)]


def box(name):
    x, y = POS[name]
    h, w = BUTTONS[name].shape[:2]
    return [x, y, w, h]


def center(name):
    x, y, w, h = box(name)
    return [x + w // 2, y + h // 2]


TITLE = {"圖示": make_button(w=48, h=36, seed=5),
         "關閉": make_button(w=48, h=36, seed=11)}
TITLE_POS = {"圖示": (418, 100), "關閉": (360, 214)}


def title_box(name):
    x, y = TITLE_POS[name]
    h, w = TITLE[name].shape[:2]
    return [x, y, w, h]


def demo_video(tmp_path, title=True, name="demo.mp4"):
    bar = [(TITLE[n], *TITLE_POS[n]) for n in TITLE] if title else []
    frames = []
    for name_, lo, hi in SCREENS:
        frames += [screen([(BUTTONS[name_], *POS[name_])] + bar)] * (hi - lo)
    return write_video(Path(tmp_path) / name, frames)


def demo_templates(*names):
    names = names or tuple(BUTTONS)
    return {n: {"frame": FRAME[n], "box": box(n)} for n in names}


TITLE_TEMPLATES = {n: {"frame": 5, "box": title_box(n)} for n in TITLE}
CALIBRATION = {"pair": ["圖示", "關閉"]}
ANCHOR = (TITLE_POS["圖示"][0] + 24, TITLE_POS["圖示"][1] + 18)


def find(name, head="find_click", **kw):
    return dict({head: name, "frame": FRAME[name], "at": center(name)}, **kw)


def click(x, y, **kw):
    return dict({"click": [x, y]}, **kw)


def demo_plan(video, out, steps=None, templates=None, name="日常", **extra):
    tpl = dict(templates if templates is not None else demo_templates())
    tpl.update({n: t for n, t in TITLE_TEMPLATES.items() if n not in tpl})
    plan = {"video": str(video), "out": str(out), "name": name, "templates": tpl,
            "calibration": CALIBRATION,
            "steps": steps if steps is not None else [
                find("開始"), find("確定"), find("下一步")]}
    plan.update(extra)
    if plan["calibration"] is None:
        del plan["calibration"]
    return plan


def expand(b, size=(VIDEO_W, VIDEO_H), anchor=ANCHOR, scroll=None):
    import math
    x, y, w, h = b
    mx, my = math.ceil(w / 2), math.ceil(h / 2)
    x0, y0, x1, y1 = x - mx, y - my, x + w + mx, y + h + my
    if scroll == "vertical":
        y0, y1 = 0, size[1]
    if scroll == "horizontal":
        x0, x1 = 0, size[0]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(size[0], x1), min(size[1], y1)
    return [x0 - anchor[0], y0 - anchor[1], x1 - x0, y1 - y0]


def read_frame(video, index):
    cap = cv2.VideoCapture(str(video))
    try:
        for i in range(index + 1):
            ok, f = cap.read()
            assert ok, f"讀不到第 {i} 幀"
        return f
    finally:
        cap.release()


RING = (0, 220, 255)
RING_FRAMES = 6


def draw_cursor(img, x, y):
    pts = np.array([[x, y], [x, y + 17], [x + 4, y + 13], [x + 7, y + 19],
                    [x + 10, y + 18], [x + 7, y + 12], [x + 12, y + 12]], np.int32)
    cv2.fillPoly(img, [pts], (255, 255, 255))
    cv2.polylines(img, [pts], True, (0, 0, 0), 1)


def draw_ring(img, x, y, k):
    cv2.circle(img, (int(x), int(y)), 6 + 4 * k, RING, 2)


def scan_video(path, clicks=(), drags=(), n_frames=120, fps=20, effect=True,
               scenes=((0, ("開始",)), (60, ("確定", "下一步"))), title=False,
               seeds=None):
    keys = [(0, (20.0, 20.0))]
    events = sorted([(f, "click", p, f, p) for f, p in clicks]
                    + [(f1, "drag", p1, f2, p2) for f1, p1, f2, p2 in drags])
    for f1, kind, p1, f2, p2 in events:
        keys += [(f1 - 4, p1), (f1, p1)]
        if kind == "drag":
            keys += [(f2, p2)]
        keys += [(f2 + RING_FRAMES + 2, p2)]

    def cursor_at(f):
        prev = keys[0]
        for k in keys:
            if k[0] >= f:
                (f0, a), (f1, b) = prev, k
                if f1 == f0:
                    return b
                t = (f - f0) / (f1 - f0)
                return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            prev = k
        return keys[-1][1]

    def screen_at(f):
        k = [i for i, (start, _) in enumerate(scenes) if start <= f][-1]
        return screen([(BUTTONS[n], *POS[n]) for n in scenes[k][1]],
                      seed=seeds[k] if seeds else 99 + k, title=title)

    frames = []
    for f in range(n_frames):
        img = screen_at(f).copy()
        if effect:
            for fc, (x, y) in clicks:
                if fc <= f < fc + RING_FRAMES:
                    draw_ring(img, x, y, f - fc)
            for f1, _, f2, _ in drags:
                if f1 <= f <= f2:
                    cx, cy = cursor_at(f)
                    cv2.circle(img, (int(cx), int(cy)), 12, RING, 2)
        cx, cy = cursor_at(f)
        draw_cursor(img, int(cx), int(cy))
        frames.append(img)
    return write_video(path, frames, fps=fps)


def ring_sample(tolerance=60):
    return {"bgr": list(RING), "tolerance": tolerance}


def snapshot(root):
    out = {}
    for dirpath, _, files in os.walk(root):
        for fn in files:
            p = Path(dirpath) / fn
            out[p.relative_to(root).as_posix()] = p.read_bytes()
    return out


def saved_flow(res):
    import flowfile
    return flowfile.read_flow(res["flow_path"])


CURSOR_W, CURSOR_H = 30, 38


def cursor_sprite(pressed=False):
    img = np.zeros((CURSOR_H, CURSOR_W, 4), np.uint8)
    white = (235, 240, 245, 255)
    cv2.line(img, (1, 1), (16, 22), white, 3)
    dy = 4 if pressed else 0
    cv2.ellipse(img, (18, 24 + dy // 2), (10, 8), 0, 0, 360, (210, 215, 220, 255), -1)
    cv2.ellipse(img, (15, 24 + dy // 2), (4, 3) if not pressed else (6, 5), 0, 0, 360,
                (20, 20, 20, 255), -1)
    for tx in (12, 17, 22):
        cv2.line(img, (tx, 30 + dy // 2), (tx, 36), (225, 230, 235, 255), 2)
    cv2.line(img, (20, 12 + dy), (27, 6 + dy), (180, 190, 200, 255), 2)
    cv2.line(img, (8, 4 + dy), (4, 10 + dy), (200, 205, 210, 255), 2)
    return img


CURSOR_HOTSPOT = (1, 1)


def draw_sprite(img, sprite, x, y, hotspot=CURSOR_HOTSPOT):
    h, w = sprite.shape[:2]
    x0, y0 = int(round(x)) - hotspot[0], int(round(y)) - hotspot[1]
    H, W = img.shape[:2]
    sx0, sy0 = max(0, -x0), max(0, -y0)
    sx1, sy1 = min(w, W - x0), min(h, H - y0)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    roi = img[y0 + sy0:y0 + sy1, x0 + sx0:x0 + sx1]
    sp = sprite[sy0:sy1, sx0:sx1]
    a = sp[..., 3:4].astype(np.float32) / 255
    roi[:] = (sp[..., :3] * a + roi * (1 - a)).astype(np.uint8)


def busy_screen(seed):
    r = np.random.default_rng(seed)
    img = r.integers(20, 200, (VIDEO_H // 10 + 1, VIDEO_W // 10 + 1, 3), dtype=np.uint8)
    img = cv2.resize(img, (VIDEO_W, VIDEO_H), interpolation=cv2.INTER_NEAREST)
    for _ in range(25):
        p1 = (int(r.integers(0, VIDEO_W)), int(r.integers(0, VIDEO_H)))
        cv2.circle(img, p1, int(r.integers(3, 14)),
                   tuple(int(c) for c in r.integers(0, 255, 3)), -1)
    return img


def cursor_video(path, clicks=(), n_frames=160, fps=20, press_frames=2,
                 scenes=((0, 0),), keyframes=(), parked=None):
    start = parked or (20.0, 20.0)
    keys = [(0, start)]
    for f, p in sorted(clicks):
        keys += [(f - 6, keys[-1][1]), (f - 2, p), (f + press_frames + 4, p)]

    def cursor_at(f):
        prev = keys[0]
        for k in keys:
            if k[0] >= f:
                (f0, a), (f1, b) = prev, k
                if f1 <= f0:
                    return b
                t = (f - f0) / (f1 - f0)
                return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            prev = k
        return keys[-1][1]

    shots = {seed: busy_screen(seed) for _, seed in scenes}
    noise = np.random.default_rng(7)
    normal, pressed = cursor_sprite(False), cursor_sprite(True)
    frames = []
    for f in range(n_frames):
        seed = [s for start_f, s in scenes if start_f <= f][-1]
        img = shots[seed].copy()
        down = any(fc <= f < fc + press_frames for fc, _ in clicks)
        x, y = cursor_at(f)
        draw_sprite(img, pressed if down else normal, x, y)
        if f in keyframes:
            img = np.clip(img.astype(np.int16)
                          + noise.normal(0, 6, img.shape).astype(np.int16),
                          0, 255).astype(np.uint8)
        frames.append(img)
    return write_video(path, frames, fps=fps)
