"""遊戲自繪游標: 學`游標樣本`、靠游標本身的`點擊特效`找點擊.

有些遊戲 (例: 換了自訂游標的明日方舟) 把系統游標藏起來、自己畫一個, 錄影
程式就畫不出它的點擊特效; 但遊戲的游標本身在點擊當下會抖一下——換一兩幀
不同的樣子 (按下、放開各一次)。這裡:

- `learn(video, points, out)`: 從游標停在**不同背景**上的幾幀 (Claude 給每幀
  游標尖端＝熱點的影片像素位置) 學出游標的樣子: 對齊後逐像素取中位數＝游標圖,
  跨幀穩定的像素＝游標本體 (背景每幀不同, 變化大的像素就是背景) → 寫成帶
  alpha 的 PNG + 樣本 JSON `{"kind": "cursor", "template": ..., "hotspot": [x, y]}`。
- `Detector`: 逐幀找到游標 (遮罩比對), 游標停著 (±幾 px) 時比較它這一幀與上一幀
  的樣子 (容許 ±3 px 對齊抖動)——平常幾乎一模一樣, 點擊特效那一幀突然變了。
  全畫面同時微幅變動 (壓縮的關鍵幀跳動) 不算。看到特效＝高信心點擊; 畫面切換
  前一秒半內沒看到特效的, 以游標停留處列為低信心候選 (寧可多報, Claude 覆核)。
"""
from __future__ import annotations

import json
import math
import os
from collections import namedtuple

import cv2
import numpy as np

from . import video as video_mod
from .errors import ToolError

MIN_POINTS = 4            # 學樣本至少要幾幀
LEARN_RADIUS = 96         # 學樣本時以熱點為中心的裁切半徑 (游標最遠伸到哪)
ALIGN = 6                 # 學樣本時各幀互相對齊容許的偏差 (Claude 讀座標的誤差)
STABLE_STD = 20.0         # 跨幀離散程度低於此＝游標本體 (背景每幀不同)
MAX_COVER = 0.6           # 穩定像素佔裁切窗超過此比例＝背景沒有變化, 學不出來
FIT_MIN = 0.5             # 學樣本時每一幀與中位數游標的相似度下限
HOT_SLACK = 6             # 熱點可以落在游標圖外多遠 (尖端常是細線, 學不進去)

TRACK_MIN = 0.5           # 遮罩比對分數 ≥ 此值才算找到游標
TRACK_SURE = 0.7          # 分數 ≥ 此值＝肯定是游標 (低於此才拿熱點那一角來比)
TRACK_NEAR = 0.5          # 在上一幀位置附近找到、分數 ≥ 此值就算同一個游標
LOCK_RADIUS = 8           # 「上一幀位置附近」的範圍 (px)
SWITCH = 0.05             # 整張找到的別處要比原地高出這麼多才換過去
# 游標樣子變化以灰階 RMS 計 (第一支示範影片校準: 點擊 10–28、平常 0–8)
QUIET = 8.0               # 上一幀游標樣子變化低於此＝平靜
SPIKE = 10.0              # 這一幀變化 ≥ 此值＝游標抖了一下 (點擊特效)
GLOBAL_MAX = 1.0          # 全畫面平均灰階差 ≥ 此值＝整張都在變 (關鍵幀、淡入淡出)
JITTER = 3                # 比對樣子變化時容許的對齊抖動 (px)
PAIR_SECONDS = 0.4        # 按下、放開兩次抖動相隔多近算同一次點擊
REACT_SECONDS = 1.5       # 點擊後多久內畫面切換算「有反應」; 也是補低信心候選的回看範圍
SCREEN_CONF = 0.4         # 畫面切換前沒看到特效時補上的候選信心


def _best(img, tpl, mask=None):
    """遮罩比對的最佳 (分數, 左上角); 遮罩讓某些位置算不出分數 (NaN) 時當 -1."""
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED, mask=mask)
    res = np.nan_to_num(res, nan=-1.0, posinf=-1.0, neginf=-1.0)
    _, v, _, loc = cv2.minMaxLoc(res)
    return float(v), loc


def _read_png(path):
    data = np.fromfile(str(path), np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED) if data.size else None
    if img is None or img.ndim != 3 or img.shape[2] != 4:
        raise ToolError(f"游標樣本圖讀不到或不是帶 alpha 的 PNG：{path}")
    return img


def load_sample(raw, base_dir):
    """游標樣本 {"kind": "cursor", "template": PNG 路徑或 BGRA 陣列, "hotspot": [x, y]}."""
    tpl = raw.get("template")
    if isinstance(tpl, str):
        tpl = _read_png(tpl if os.path.isabs(tpl) else os.path.join(base_dir, tpl))
    if not isinstance(tpl, np.ndarray) or tpl.ndim != 3 or tpl.shape[2] != 4:
        raise ToolError("游標樣本要有 template（帶 alpha 的 PNG 路徑）")
    hs = raw.get("hotspot")
    if (not isinstance(hs, (list, tuple)) or len(hs) != 2
            or not all(isinstance(v, (int, float)) for v in hs)):
        raise ToolError(f"游標樣本要有 hotspot: [x, y]，收到 {hs!r}")
    mask = (tpl[..., 3] > 127).astype(np.uint8) * 255
    if mask.sum() == 0:
        raise ToolError("游標樣本圖的 alpha 全透明")
    return {"kind": "cursor", "bgr": tpl[..., :3].copy(), "mask": mask,
            "hotspot": (float(hs[0]), float(hs[1]))}


# ---------------- 學樣本 ----------------

def _gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _window(frame, x, y, r):
    """以 (x, y) 為中心、半徑 r 的裁切窗; 超出畫面的部分記為無效 (valid=False)."""
    h, w = frame.shape[:2]
    pad = cv2.copyMakeBorder(frame, r, r, r, r, cv2.BORDER_CONSTANT, value=0)
    valid = np.zeros((h + 2 * r, w + 2 * r), bool)
    valid[r:r + h, r:r + w] = True
    sl = (slice(y, y + 2 * r), slice(x, x + 2 * r))
    return pad[sl].astype(np.float32), valid[sl]


def learn(video, points, out_path, radius=LEARN_RADIUS):
    """從游標停在不同背景上的幾幀學游標樣本; 回傳結果 dict.

    points: [(幀, (x, y)), ...]——每幀游標尖端 (熱點) 的影片像素位置, 誤差容許
    幾 px (各幀會互相對齊)。out_path: 樣本 JSON; 游標圖寫在旁邊同名 .png。
    """
    pts = []
    for p in points:
        try:
            f, (x, y) = p
            pts.append((int(f), (int(round(x)), int(round(y)))))
        except (TypeError, ValueError):
            raise ToolError(f"學游標樣本的位置要寫成 (幀, (x, y))，收到 {p!r}") from None
    if len(pts) < MIN_POINTS:
        raise ToolError(f"學游標樣本至少要 {MIN_POINTS} 幀（游標停在不同背景上），"
                        f"收到 {len(pts)} 幀")
    frames = video_mod.read_frames(video, [f for f, _ in pts])
    out = [f for f, (x, y) in pts
           if not (0 <= x < frames[f].shape[1] and 0 <= y < frames[f].shape[0])]
    if out:
        raise ToolError(f"第 {', '.join(map(str, out))} 幀給的位置超出畫面"
                        f"（影片 {frames[out[0]].shape[1]}×{frames[out[0]].shape[0]}）："
                        "位置要寫游標尖端的影片像素")
    r = int(radius)
    wins = [_window(frames[f], x, y, r) for f, (x, y) in pts]

    # 逐幀對齊: 只用「跨幀穩定」的像素 (游標本體) 比對, 背景不參與;
    # 第一輪在模糊圖上做 (Claude 讀的位置差幾 px 時游標仍大致重疊)
    shifts = [(0, 0)] * len(wins)
    for blur in (2.0, 2.0, 0, 0):
        aligned = [_shift(img, valid, dx, dy) for (img, valid), (dx, dy) in zip(wins, shifts)]
        imgs = [cv2.GaussianBlur(a, (0, 0), blur) if blur else a for a, _ in aligned]
        valid = np.stack([v for _, v in aligned]).all(axis=0)
        med, spread = _robust(np.stack(imgs))
        stable = ((spread < STABLE_STD) & valid).astype(np.uint8)
        stable[:ALIGN, :] = stable[-ALIGN:, :] = 0
        stable[:, :ALIGN] = stable[:, -ALIGN:] = 0
        if stable.sum() < 20:
            break
        ys, xs = np.nonzero(stable)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        ref = med[y0:y1, x0:x1].astype(np.float32)
        m = stable[y0:y1, x0:x1] * 255
        new = []
        for (img, _valid), (dx, dy) in zip(wins, shifts):
            src = cv2.GaussianBlur(img, (0, 0), blur) if blur else img
            # 在原裁切窗上找 ref, 只在原位置 ±ALIGN 內找
            lo_y, lo_x = max(0, y0 - ALIGN), max(0, x0 - ALIGN)
            area = src[lo_y:y1 + ALIGN, lo_x:x1 + ALIGN]
            _, (lx, ly) = _best(area, ref, m)
            new.append((lo_x + lx - x0, lo_y + ly - y0))
        shifts = new
    aligned = [_shift(img, valid, dx, dy) for (img, valid), (dx, dy) in zip(wins, shifts)]
    valid = np.stack([v for _, v in aligned]).all(axis=0)
    med, spread = _robust(np.stack([a for a, _ in aligned]))
    stable = (spread < STABLE_STD) & valid
    if stable[valid].mean() > MAX_COVER:
        raise ToolError("學游標樣本的幾幀背景幾乎一樣，分不出游標與背景："
                        "請挑游標停在不同畫面、不同背景上的幀")

    # 熱點 (對齊後的座標): 各幀 Claude 給的位置 (裁切窗中心) 經對齊修正後取中位數
    # (對齊後的第 u 格＝原裁切窗的第 u + shift 格)
    hot = np.median([(r - dx, r - dy) for dx, dy in shifts], axis=0)
    mask = _sprite_mask(stable, hot)
    ys, xs = np.nonzero(mask)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    tpl = med[y0:y1, x0:x1].clip(0, 255).astype(np.uint8)
    alpha = mask[y0:y1, x0:x1].astype(np.uint8) * 255

    # 每一幀都要像這個游標: 不像的那幾幀多半是位置給錯 (那裡沒有游標)
    bad = []
    fits = {}
    m = alpha
    for (f, _), a in zip(pts, aligned):
        crop = a[0][y0:y1, x0:x1].clip(0, 255).astype(np.uint8)
        s, _ = _best(_gray(crop), _gray(tpl), m)
        fits[f] = round(s, 3)
        if s < FIT_MIN:
            bad.append(f)
    if bad:
        raise ToolError(f"第 {', '.join(map(str, bad))} 幀給的位置看起來不是游標"
                        "（與其他幀的游標對不起來）：請用 scan --frames 輸出那幾幀，"
                        "從格線圖重讀游標尖端的位置，或換別的幀")

    out_path = str(out_path)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    png = os.path.splitext(out_path)[0] + ".png"
    ok, buf = cv2.imencode(".png", np.dstack([tpl, alpha]))
    if not ok:
        raise ToolError("游標樣本圖無法編碼成 PNG")
    buf.tofile(png)
    hotspot = [int(round(hot[0] - x0)), int(round(hot[1] - y0))]
    warnings = []
    if not (-HOT_SLACK <= hotspot[0] < tpl.shape[1] + HOT_SLACK
            and -HOT_SLACK <= hotspot[1] < tpl.shape[0] + HOT_SLACK):
        warnings.append(
            f"熱點 {hotspot} 落在游標圖（{tpl.shape[1]}×{tpl.shape[0]}）外：給的位置可能"
            "不是游標尖端，或尖端太細沒被學進去；候選位置會照這個熱點偏移，"
            "請從格線圖確認尖端位置後重學")
    sample = {"kind": "cursor", "template": os.path.basename(png), "hotspot": hotspot,
              "learnedFrom": [f for f, _ in pts]}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    return {"sample_path": out_path, "template_path": png, "size": [int(x1 - x0), int(y1 - y0)],
            "hotspot": hotspot, "cover": round(float(alpha.mean() / 255), 3), "fits": fits,
            "warnings": warnings}


def _robust(stack):
    """逐像素的中位數與離散程度 (|差|的 75 百分位, 三色平均).

    要四分之三的幀都一樣才算穩定: 少數幾幀給錯不會帶偏, 但半數幀剛好都是
    暗背景時, 那片暗背景也不會被當成游標。
    """
    med = np.median(stack, axis=0)
    spread = np.percentile(np.abs(stack - med), 75, axis=0).mean(axis=2)
    return med, spread


def _shift(img, valid, dx, dy):
    """把裁切窗平移 (dx, dy), 移出去的地方記為無效."""
    m = np.float32([[1, 0, -dx], [0, 1, -dy]])
    h, w = valid.shape
    out = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
    v = cv2.warpAffine(valid.astype(np.uint8), m, (w, h), flags=cv2.INTER_NEAREST,
                       borderValue=0).astype(bool)
    return out, v


def _sprite_mask(stable, hot):
    """穩定像素裡屬於游標的部分: 離熱點最近的那一塊, 加上緊鄰它的碎塊."""
    # 壓縮失真與游標自己的小動畫讓本體破成碎片: 先把小縫補起來再挑連通塊
    m = cv2.morphologyEx(stable.astype(np.uint8), cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, labels = cv2.connectedComponents(m, connectivity=8)
    if n <= 1:
        raise ToolError("學不出游標的形狀（沒有跨幀穩定的像素）：請確認給的位置是游標尖端")
    ys, xs = np.nonzero(labels)
    d = np.hypot(xs - hot[0], ys - hot[1])
    k = int(d.argmin())
    if d[k] > 15:
        raise ToolError("給的位置附近找不到游標（離穩定像素太遠）：位置要寫游標尖端")
    main = labels == labels[ys[k], xs[k]]
    keep = main.copy()
    near = cv2.dilate(main.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    for lab in range(1, n):
        part = labels == lab
        if (part & near).any() and part.sum() >= 4:
            keep |= part
    return keep


# ---------------- 偵測 ----------------

class _View:
    """一種比對用的游標樣子: 整個游標, 或只有熱點附近那一角 (游標一半跑出畫面時用)."""

    def __init__(self, gray, mask):
        self.tpl, self.mask = gray, mask
        self.th, self.tw = gray.shape
        er = cv2.erode(mask, np.ones((3, 3), np.uint8))
        self.core = er if er.sum() > 0.3 * mask.sum() else mask
        self.n = float((self.core > 0).sum())
        # 粗找用的縮圖倍率: 讓縮小後的游標仍有 ~16 px
        self.cs = min(1.0, max(0.2, 16.0 / min(self.th, self.tw)))
        self.small_tpl = cv2.resize(gray, None, fx=self.cs, fy=self.cs,
                                    interpolation=cv2.INTER_AREA)
        sm = cv2.resize(mask, None, fx=self.cs, fy=self.cs, interpolation=cv2.INTER_NEAREST)
        self.small_mask = sm if sm.any() else None

    def locate(self, padded, small_cache):
        """回傳 (分數, 樣本左上角在補邊座標的位置)."""
        small = small_cache.get(self.cs)
        if small is None:
            small = cv2.resize(padded, None, fx=self.cs, fy=self.cs,
                               interpolation=cv2.INTER_AREA) if self.cs < 1 else padded
            small_cache[self.cs] = small
        _, (x, y) = _best(small, self.small_tpl, self.small_mask)
        # 縮圖上的位置換回原尺寸, 在附近幾 px 內精確找
        m = int(math.ceil(2 / self.cs)) + 1
        return self.near(padded, int(x / self.cs), int(y / self.cs), m)

    def near(self, padded, lx, ly, r):
        """只在左上角 (lx, ly) 附近 ±r 找: 回傳 (分數, 樣本左上角位置)."""
        x0, y0 = max(0, lx - r), max(0, ly - r)
        win = padded[y0:ly + self.th + r, x0:lx + self.tw + r]
        if win.shape[0] < self.th or win.shape[1] < self.tw:
            return -1.0, (0, 0)
        v, (x, y) = _best(win, self.tpl, self.mask)
        return v, (x0 + x, y0 + y)

    def change(self, padded, prev, lx, ly):
        """游標這一幀與上一幀同一處的樣子差 (灰階 RMS, 容許 ±JITTER 對齊)."""
        J = JITTER
        cur = padded[ly:ly + self.th, lx:lx + self.tw]
        pw = prev[max(0, ly - J):ly + self.th + J, max(0, lx - J):lx + self.tw + J]
        if pw.shape[0] < self.th or pw.shape[1] < self.tw:
            return None
        r = cv2.matchTemplate(pw.astype(np.float32), cur.astype(np.float32),
                              cv2.TM_SQDIFF, mask=self.core)
        return math.sqrt(max(0.0, float(r.min())) / self.n)


# 每幀追蹤紀錄: 找到游標? 熱點 (x, y)、游標樣子變化 (RMS; 無法比較時 None)、
# 全畫面平均灰階差、是否畫面切換
_Rec = namedtuple("_Rec", "found x y change gdiff trans")


class Detector:
    """逐幀追游標、看它在停住時有沒有抖一下 (遊戲畫的點擊特效)."""

    def __init__(self, info, sample):
        self.fps = info["fps"]
        self.frame_size = (info["width"], info["height"])
        gray = _gray(sample["bgr"])
        mask = sample["mask"]
        self.hot = sample["hotspot"]
        th, tw = gray.shape
        self.size = (th, tw)
        self.views = [_View(gray, mask)]
        # 熱點那一角 (Windows 式游標的熱點在左上, 會被切掉的是右邊與下邊)
        ph = min(th, max(int(self.hot[1]) + 10, th // 2))
        pw = min(tw, max(int(self.hot[0]) + 10, tw // 2))
        if (ph, pw) != (th, tw) and mask[:ph, :pw].sum() > 0.15 * mask.sum():
            self.views.append(_View(gray[:ph, :pw].copy(), mask[:ph, :pw].copy()))
        self.pad = max(th, tw)
        self.prev = None          # 上一幀 (補邊後的灰階)
        self.last = None          # 上一幀找到游標時: (樣子, 位置)
        self.prev_small = None
        self.recs = []            # 每幀一筆 _Rec
        self.count = 0

    def feed(self, i, frame):
        self.count = i + 1
        gray = _gray(frame)
        P = self.pad
        padded = cv2.copyMakeBorder(gray, P, P, P, P, cv2.BORDER_REPLICATE)
        # 整張找一次: 整個游標不夠像時看熱點那一角是否明顯更像 (游標被畫面邊緣切掉)
        cache = {}
        view = self.views[0]
        score, loc = view.locate(padded, cache)
        if score < TRACK_SURE:
            for v in self.views[1:]:
                sc, lc = v.locate(padded, cache)
                if sc >= TRACK_SURE and sc >= score + 0.1:
                    view, score, loc = v, sc, lc
        if self.last is not None:
            # 也在上一幀的位置附近找 (同一個樣子): 點擊特效那幾幀游標樣子變了、
            # 分數掉一些, 仍要鎖在原地——整張找的結果要明顯更像才換過去
            # (游標移走了, 或上一幀其實鎖錯在背景上)
            v, (lx, ly) = self.last
            sc, lc = v.near(padded, lx, ly, LOCK_RADIUS)
            if sc >= TRACK_NEAR and not (score >= sc + SWITCH
                                         and math.dist(loc, lc) > LOCK_RADIUS):
                view, score, loc = v, sc, lc
        found = score >= TRACK_MIN
        self.last = (view, loc) if found else None
        small = cv2.resize(gray, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
        gd, trans = 0.0, False
        if self.prev_small is not None:
            diff = cv2.absdiff(small, self.prev_small)
            gd = float(diff.mean())
            trans = float((diff > 30).mean()) > 0.15
        change = None
        if found and self.prev is not None:
            change = view.change(padded, self.prev, *loc)
        hx, hy = loc[0] - P + self.hot[0], loc[1] - P + self.hot[1]
        self.recs.append(_Rec(found, hx, hy, change, gd, trans))
        self.prev, self.prev_small = padded, small

    @property
    def still(self):
        return max(3.0, 0.05 * min(self.size))

    def candidates(self):
        recs = self.recs
        presses = []
        for k in range(1, len(recs)):
            cur, prev = recs[k], recs[k - 1]
            if not (cur.found and prev.found) or cur.change is None or prev.change is None:
                continue
            if math.dist((cur.x, cur.y), (prev.x, prev.y)) > self.still:
                continue
            if prev.change < QUIET and cur.change >= SPIKE and cur.gdiff < GLOBAL_MAX:
                presses.append({"frame": k, "c": (prev.x, prev.y)})
        out = []
        gap = max(1, round(PAIR_SECONDS * self.fps))
        for p in presses:
            last = out[-1] if out else None
            if (last and p["frame"] - last["endFrame"] <= gap
                    and math.dist(p["c"], last["c"]) <= 2 * self.still):
                last["endFrame"] = p["frame"]
                last["paired"] = True
                continue
            out.append({"frame": p["frame"], "endFrame": p["frame"], "c": p["c"],
                        "kind": "click", "cue": "effect", "paired": False,
                        "color": None, "area": 0})
        react = max(1, round(REACT_SECONDS * self.fps))
        onsets = [k for k in range(1, len(recs)) if recs[k].trans and not recs[k - 1].trans]
        for c in out:
            reacted = any(c["frame"] <= t <= c["endFrame"] + react for t in onsets)
            c["conf"] = 0.8 + 0.1 * c.pop("paired") + 0.1 * reacted
        # 畫面切換前一段時間沒看到特效: 以切換前游標最後停住的地方補低信心候選
        for t in onsets:
            if any(t - react <= c["frame"] <= t for c in out if c["cue"] == "effect"):
                continue
            spot = None
            for k in range(t - 1, max(0, t - react) - 1, -1):
                cur, prev = recs[k], recs[k - 1] if k > 0 else None
                if (cur.found and prev is not None and prev.found
                        and math.dist((cur.x, cur.y), (prev.x, prev.y)) <= self.still):
                    spot = (k, (cur.x, cur.y))
                    break
            if spot is None:
                continue
            dup = [c for c in out if c["cue"] == "screen"
                   and abs(c["frame"] - spot[0]) <= react
                   and math.dist(c["c"], spot[1]) <= self.still]
            if dup:   # 同一處停留後連續幾次切換 (淡入淡出): 併成一個
                dup[0]["endFrame"] = max(dup[0]["endFrame"], t)
                continue
            out.append({"frame": spot[0], "endFrame": t, "c": spot[1], "kind": "click",
                        "cue": "screen", "conf": SCREEN_CONF, "color": None, "area": 0})
        out.sort(key=lambda c: c["frame"])
        return out

    def to_video(self, xy):
        """熱點換成影片像素 (游標一半跑出畫面時熱點可能算到邊外一點: 夾回畫面內)."""
        w, h = self.frame_size
        return [min(w - 1, max(0, int(round(xy[0])))),
                min(h - 1, max(0, int(round(xy[1]))))]
