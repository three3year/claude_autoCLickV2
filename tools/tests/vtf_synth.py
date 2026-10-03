"""影片轉流程測試用的合成輸入: 小影片 + 合成 profile (全部落在 tmp_path).

示範影片用 OpenCV 的影片寫入真的編碼成檔 (有壓縮失真, 與真實錄影同一條讀取
路徑); profile 是真的資料夾 (config.yaml + 步驟草稿), 工具只透過檔案看到它。

(名稱刻意不叫 synth: tests/ 的引擎測試已有 synth.py, 同名模組會互相遮蔽。)
"""
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
    """有紋理、有辨識度的假按鈕 (面板+邊框+筆畫+圓點)."""
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
    """忙碌但不含按鈕的底圖; 左下角留一塊純色面板 (`空白處`)."""
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


# 底圖上的純色面板 (x, y, w, h): 框在這裡的範本＝框到空白處
BLANK = (10, 190, 120, 70)


def screen(buttons, seed=99):
    """一個畫面: 底圖 + 若干按鈕 [(按鈕影像, x, y), ...] (x, y 為左上角)."""
    img = make_background(seed=seed)
    for tpl, x, y in buttons:
        h, w = tpl.shape[:2]
        img[y:y + h, x:x + w] = tpl
    return img


def write_video(path, frames, fps=10):
    """把影格清單編碼成影片檔 (mp4v); 回傳路徑."""
    path = str(path)
    h, w = frames[0].shape[:2]
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    assert vw.isOpened(), "VideoWriter 開不起來"
    for f in frames:
        vw.write(f)
    vw.release()
    return path


def timeline(*segments):
    """[(畫面, 幀數), ...] 展開成影格清單."""
    out = []
    for img, n in segments:
        out.extend([img] * n)
    return out


def make_profile(root, region=None, config=None, draft_extra=None, name="p"):
    """合成 profile: config.yaml + 步驟草稿 (含搜尋範圍); 回傳 profile 路徑.

    region=None 時草稿沒有搜尋範圍。
    """
    profile = Path(root) / "profiles" / name
    (profile / "flows").mkdir(parents=True, exist_ok=True)
    (profile / "config.yaml").write_text(
        yaml.safe_dump(config if config is not None else {"scale_range": [0.5, 2.0]}),
        encoding="utf-8")
    draft = {"steps": [{"type": "wait", "ms": 1234}], "runMode": "count",
             "runCount": 1, "scanRegion": region, "avoidHover": False,
             "coordSpace": "region"}
    draft.update(draft_extra or {})
    with open(profile / "flows" / "_autosave.json", "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False)
    return profile


# ---------- 標準示範影片: 三個畫面依序出現 ----------
# 畫面 A (幀 0-14): 「開始」; 畫面 B (15-29): 「確定」; 畫面 C (30-44): 「下一步」

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
    """按鈕框中心 (與 runner 同一條取中心規則: x + w // 2)."""
    x, y, w, h = box(name)
    return [x + w // 2, y + h // 2]


def demo_video(tmp_path):
    frames = []
    for name, lo, hi in SCREENS:
        frames += [screen([(BUTTONS[name], *POS[name])])] * (hi - lo)
    return write_video(Path(tmp_path) / "demo.mp4", frames)


def demo_templates(*names):
    names = names or tuple(BUTTONS)
    return {n: {"frame": FRAME[n], "box": box(n)} for n in names}


def find(name, **kw):
    """點在按鈕中心的找圖點擊 (計畫用影片像素寫位置)."""
    return dict({"type": "find_click", "template": name, "frame": FRAME[name],
                 "at": center(name)}, **kw)


def demo_plan(video, profile, steps=None, templates=None, name="日常", **extra):
    plan = {"video": str(video), "profile": str(profile), "name": name,
            "templates": templates if templates is not None else demo_templates(),
            "steps": steps if steps is not None else [
                find("開始"), find("確定"), find("下一步")]}
    plan.update(extra)
    return plan


def read_frame(video, index):
    """解碼影片的第 index 幀 (循序讀, 與工具同一條解碼路徑)."""
    cap = cv2.VideoCapture(str(video))
    try:
        for i in range(index + 1):
            ok, f = cap.read()
            assert ok, f"讀不到第 {i} 幀"
        return f
    finally:
        cap.release()


# ---------- 掃描用影片: 假游標 + 假點擊特效 ----------

RING = (0, 220, 255)       # 假點擊特效的顏色 (BGR 黃)
RING_FRAMES = 6            # 特效持續幀數 (半徑逐幀變大)


def draw_cursor(img, x, y):
    """白色箭頭游標 (黑邊), 尖端在 (x, y)."""
    pts = np.array([[x, y], [x, y + 17], [x + 4, y + 13], [x + 7, y + 19],
                    [x + 10, y + 18], [x + 7, y + 12], [x + 12, y + 12]], np.int32)
    cv2.fillPoly(img, [pts], (255, 255, 255))
    cv2.polylines(img, [pts], True, (0, 0, 0), 1)


def draw_ring(img, x, y, k):
    cv2.circle(img, (int(x), int(y)), 6 + 4 * k, RING, 2)


def scan_video(path, clicks=(), drags=(), n_frames=120, fps=20, effect=True,
               scenes=((0, ("開始",)), (60, ("確定", "下一步")))):
    """合成一支示範影片.

    clicks: [(幀, (x, y))]——游標先移過去停住, 該幀起畫特效 (effect=False 不畫);
    drags: [(起幀, (x1, y1), 訖幀, (x2, y2))]——按住期間特效跟著游標;
    scenes: [(起幀, (按鈕名, ...))]——畫面切換 (換底圖＝全畫面變化, 不是點擊)。
    """
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
        return screen([(BUTTONS[n], *POS[n]) for n in scenes[k][1]], seed=99 + k)

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
    """與假特效相符的特效樣本 (第一次處理時從影片學到的那份描述)."""
    return {"bgr": list(RING), "tolerance": tolerance}


def snapshot(profile):
    """profile 內每個檔案的 (相對路徑 → 內容 bytes): 斷言「什麼都沒動」用."""
    out = {}
    for dirpath, _, files in os.walk(profile):
        for fn in files:
            p = Path(dirpath) / fn
            out[p.relative_to(profile).as_posix()] = p.read_bytes()
    return out


# ---------- 遊戲自繪游標: 錄影程式沒畫特效, 游標本身在點擊時抖一下 ----------

CURSOR_W, CURSOR_H = 30, 38


def cursor_sprite(pressed=False):
    """遊戲自繪的游標 (BGRA; alpha＝不透明處): 尖端 (熱點) 在左上角 (1, 1).

    一支白色長矛 + 下方一顆有黑眼的骷髏頭; pressed＝點擊當下那一兩幀的樣子
    (骷髏頭往下一沉、眼睛變大)——遊戲畫的`點擊特效`。
    """
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
    """把 BGRA 游標畫到 img 上, 熱點落在 (x, y); 超出畫面的部分裁掉."""
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
    """紋理很多的畫面 (底色區塊 + 小方格), 游標在上面才看得出背景在變."""
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
    """合成一支「遊戲自繪游標」的示範影片 (沒有錄影程式的點擊特效).

    clicks: [(幀, (x, y))]——游標先移過去停住, 從該幀起畫 pressed 樣子
        press_frames 幀 (遊戲的點擊特效), 之後恢復一般樣子;
    scenes: [(起幀, 底圖種子)]——畫面切換;
    keyframes: 這些幀整張疊一層雜訊 (模擬壓縮的關鍵幀跳動: 全畫面都在變);
    parked: 開頭游標停的位置 (預設 (20, 20))。
    """
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
