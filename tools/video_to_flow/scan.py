"""掃描: `示範影片` → 候選點擊清單 + 每個候選前後數幀的縮圖.

讓 Claude 不必逐幀看影片: 找出`點擊特效`出現的時間與位置, 附信心與縮圖,
由 Claude 覆核 (剔誤報、補漏抓) 後寫`轉換計畫`。

兩種偵測 (都在縮到寬 ≤640 的影格上做, 位置換回影片像素):

- **特效樣本** (sample): 錄影程式畫的特效長相描述 `{"bgr": [b, g, r],
  "tolerance": 60}`——第一次處理某位使用者的影片時從影片學到 (見 skill)。
  逐幀找接近該顏色的區塊、跨幀追蹤: 停在原地＝點擊, 一路移動＝拖曳
  (起訖兩點)。一開頭就在、長時間不動、隨整個畫面切換才出現的同色區塊是
  畫面本身的東西, 不算。
- **退路** (fallback, 沒有樣本): 找「局部、短暫、連續幾幀都在原地劇烈變化」
  的區塊 (特效的動畫); 全畫面變化 (過場) 與一路移動的區塊 (游標) 不算。
  寧可多報: 只變一幀的局部變化也列為低信心候選, 誤報交給 Claude 剔除。

信心 ≥ `HIGH` (0.7) 算高信心。
"""
from __future__ import annotations

import json
import math
import os

import cv2
import numpy as np

from . import video as video_mod
from .errors import ToolError

HIGH = 0.7
WORK_WIDTH = 640          # 偵測用的影格寬度上限
TRANSITION_FRAC = 0.15    # 變化像素佔比超過＝畫面切換 (過場), 不是點擊
DIFF_THRESHOLD = 30       # 灰階差超過才算「變了」(壓縮雜訊在這之下)
THUMB_OFFSETS = (-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 1.0)   # 縮圖取的時間點 (秒)
THUMB_WIDTH = 400
MERGE_SECONDS = 0.3


def _load_sample(sample):
    if sample is None:
        return None
    if not isinstance(sample, dict):
        try:
            with open(sample, encoding="utf-8") as f:
                sample = json.load(f)
        except (OSError, ValueError) as e:
            raise ToolError(f"讀不到特效樣本：{sample}（{e}）") from None
    bgr = sample.get("bgr") if isinstance(sample, dict) else None
    if (not isinstance(bgr, list) or len(bgr) != 3
            or not all(isinstance(v, (int, float)) and 0 <= v <= 255 for v in bgr)):
        raise ToolError("特效樣本格式不對：要有 bgr: [b, g, r]（0–255），"
                        f"可選 tolerance；收到 {sample!r}")
    tol = sample.get("tolerance", 60)
    if not isinstance(tol, (int, float)) or tol <= 0:
        raise ToolError(f"特效樣本的 tolerance 要是正數，收到 {tol!r}")
    return {"bgr": np.array(bgr, np.int16), "tolerance": float(tol)}


class _Tracks:
    """把逐幀的區塊串成軌跡 (最近鄰、容許斷一幀)."""

    def __init__(self, radius):
        self.radius = radius
        self.active = []
        self.done = []

    def feed(self, i, blobs):
        still = []
        for t in self.active:
            (still if i - t["pts"][-1]["f"] <= 2 else self.done).append(t)
        self.active = still
        free = list(self.active)
        for b in sorted(blobs, key=lambda b: -b["area"]):
            best, bd = None, self.radius
            for t in free:
                d = math.dist(t["pts"][-1]["c"], b["c"])
                if d <= bd:
                    best, bd = t, d
            if best is None:
                self.active.append({"pts": [dict(b, f=i)]})
            else:
                best["pts"].append(dict(b, f=i))
                free.remove(best)

    def close(self):
        self.done += self.active
        self.active = []
        return self.done


def _blobs(mask, img, min_area, max_area, join):
    """mask 的區塊; 相距 join px 內的碎片併成一塊 (特效圓環常被游標或背景
    紋理切成幾段弧, 各段的重心都不在點擊處)。面積/重心/顏色以原 mask 像素算."""
    k = join | 1
    grouped = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    n, labels = cv2.connectedComponents(grouped, connectivity=8)
    out = []
    on = mask.astype(bool)
    for lab in range(1, n):
        sel = (labels == lab) & on
        area = int(sel.sum())
        if not min_area <= area <= max_area:
            continue
        ys, xs = np.nonzero(sel)
        color = img[sel].mean(axis=0)
        out.append({"c": (float(xs.mean()), float(ys.mean())), "area": area,
                    "color": [int(round(v)) for v in color]})
    return out


class _Detector:
    def __init__(self, info, sample):
        w, h = info["width"], info["height"]
        self.s = min(1.0, WORK_WIDTH / w)
        self.size = (max(1, round(w * self.s)), max(1, round(h * self.s)))
        self.diag = math.hypot(*self.size)
        self.fps = info["fps"]
        self.sample = sample
        self.prev = None
        self.transitions = set()
        radius = (0.08 if sample else 0.04) * self.diag
        self.tracks = _Tracks(radius)
        self.count = 0
        area = self.size[0] * self.size[1]
        self.min_area = max(12, int(area * 0.00008))
        self.max_area = int(area * 0.05)

    def feed(self, i, frame):
        self.count = i + 1
        img = cv2.resize(frame, self.size, interpolation=cv2.INTER_AREA) \
            if self.s < 1 else frame
        gray = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (3, 3), 0)
        prev, self.prev = self.prev, gray
        changed = None
        if prev is not None:
            changed = (cv2.absdiff(gray, prev) > DIFF_THRESHOLD).astype(np.uint8)
            if changed.mean() > TRANSITION_FRAC:
                self.transitions.add(i)
        kernel = np.ones((3, 3), np.uint8)
        if self.sample:
            far = np.abs(img.astype(np.int16) - self.sample["bgr"]).max(axis=2)
            mask = (far <= self.sample["tolerance"]).astype(np.uint8)
        else:
            if changed is None or i in self.transitions:
                self.tracks.feed(i, [])
                return
            mask = cv2.morphologyEx(changed, cv2.MORPH_OPEN, kernel)
        self.tracks.feed(i, _blobs(mask, img, self.min_area, self.max_area,
                                   max(5, round(0.025 * self.diag))))

    def candidates(self):
        out = []
        for t in self.tracks.close():
            out += (self._sample_track(t["pts"]) if self.sample
                    else self._still_runs(t["pts"]))
        return self._merge(out)

    def _sample_track(self, pts):
        """特效樣本: 一條同色軌跡＝一次點擊 (停在原地) 或一次拖曳 (一路移動)."""
        first, last = pts[0], pts[-1]
        cand = {"frame": first["f"], "endFrame": last["f"],
                "color": first["color"], "area": first["area"]}
        if math.dist(first["c"], last["c"]) > 0.03 * self.diag:
            return [dict(cand, kind="drag", conf=0.9, c=first["c"],
                         frm=first["c"], to=last["c"])]
        dur = (last["f"] - first["f"] + 1) / self.fps
        if first["f"] == 0 or dur > 2.0 or first["f"] in self.transitions:
            return []   # 一開頭就在/久久不動/隨過場出現: 畫面本身的同色東西
        med = (float(np.median([p["c"][0] for p in pts])),
               float(np.median([p["c"][1] for p in pts])))
        return [dict(cand, kind="click", c=med,
                     conf=0.8 + 0.15 * min(1.0, (len(pts) - 1) / 3))]

    @property
    def still(self):
        """「停在原地」的容許漂移 (工作尺度 px): 圓環長大蓋過有紋理的按鈕時,
        重心會漂幾 px; 移動中的游標另由 `_still_runs` 的兩幀規則排除。"""
        return max(4.0, 0.012 * self.diag)

    def _still_runs(self, pts):
        """退路: 軌跡切成「停在原地」的幾段, 每段一個候選.

        一路移動的部分是游標 (退路分不出拖曳), 丟掉; 孤立的短暫區塊
        (hover 反白之類) 列為低信心候選——寧可多報。
        """
        runs, run = [], [pts[0]]
        for p in pts[1:]:
            if math.dist(p["c"], run[0]["c"]) <= self.still:
                run.append(p)
            else:
                runs.append(run)
                run = [p]
        runs.append(run)
        out = []
        for run in runs:
            n = len(run)
            if len(runs) > 1 and n <= 2:
                # 移動途中: 逐幀相減時游標每個位置出現兩次 (出現、再消失),
                # 看起來像停了兩幀
                continue
            out.append({"frame": run[0]["f"], "endFrame": run[-1]["f"],
                        "color": run[0]["color"], "area": run[0]["area"],
                        "c": (float(np.median([p["c"][0] for p in run])),
                              float(np.median([p["c"][1] for p in run]))),
                        "kind": "click", "conf": 0.3 + min(0.6, 0.15 * (n - 1))})
        return out

    def _merge(self, cands):
        """同一次特效被拆成幾段 (某幀區塊被游標切開) → 併成一個, 取最早幀."""
        gap = max(1, round(MERGE_SECONDS * self.fps))
        near = 2 * self.still
        out = []
        for c in sorted(cands, key=lambda c: c["frame"]):
            for o in out:
                if (o["kind"] == c["kind"] == "click"
                        and c["frame"] - o["endFrame"] <= gap
                        and math.dist(o["c"], c["c"]) <= near):
                    o["endFrame"] = max(o["endFrame"], c["endFrame"])
                    if c["conf"] > o["conf"]:   # 位置取比較可信的那段
                        o.update(c=c["c"], conf=c["conf"], color=c["color"])
                    break
            else:
                out.append(c)
        return out

    def to_video(self, xy):
        return [int(round(xy[0] / self.s)), int(round(xy[1] / self.s))]


def _imwrite(path, img, ext=".png", params=()):
    ok, buf = cv2.imencode(ext, img, list(params))
    if not ok:
        raise ToolError(f"無法輸出影像：{path}")
    buf.tofile(str(path))


def _grid(img):
    """疊座標格線 (每 50px 細線、每 100px 標數字), 方便讀出影片像素位置."""
    out = img.copy()
    h, w = out.shape[:2]
    over = out.copy()
    for x in range(0, w, 50):
        cv2.line(over, (x, 0), (x, h), (0, 255, 255) if x % 100 == 0 else (200, 200, 200), 1)
    for y in range(0, h, 50):
        cv2.line(over, (0, y), (w, y), (0, 255, 255) if y % 100 == 0 else (200, 200, 200), 1)
    out = cv2.addWeighted(over, 0.45, out, 0.55, 0)
    for x in range(100, w, 100):
        cv2.putText(out, str(x), (x + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (0, 0, 0), 3)
        cv2.putText(out, str(x), (x + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (0, 255, 255), 1)
    for y in range(100, h, 100):
        cv2.putText(out, str(y), (2, y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (0, 0, 0), 3)
        cv2.putText(out, str(y), (2, y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (0, 255, 255), 1)
    return out


def _tile(frame, scale, label, marks, strong):
    t = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) \
        if scale < 1 else frame.copy()
    for kind, a, b in marks:
        pa = (int(a[0] * scale), int(a[1] * scale))
        if kind == "line":
            pb = (int(b[0] * scale), int(b[1] * scale))
            cv2.arrowedLine(t, pa, pb, (0, 0, 255), 2 if strong else 1, tipLength=0.05)
        cv2.circle(t, pa, 14, (0, 0, 255), 2 if strong else 1)
    cv2.rectangle(t, (0, 0), (len(label) * 8 + 6, 16), (0, 0, 0), -1)
    cv2.putText(t, label, (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    return t


def scan(video, out_dir, sample=None, frames=()):
    """掃描示範影片; 回傳結果 dict (同時寫 candidates.json 到 out_dir).

    sample: 特效樣本 (dict 或 JSON 檔路徑; None＝退路偵測)。
    frames: 另外輸出這些影格的原尺寸 PNG 與座標格線版 (寫範本框時讀座標用)。
    縮圖與輸出一律寫到 out_dir (呼叫端給 session 暫存目錄, 不進 repo)。
    """
    video = str(video)
    info = video_mod.probe(video)
    smp = _load_sample(sample)
    det = _Detector(info, smp)
    for i, frame in video_mod.iter_frames(video):
        det.feed(i, frame)
    total = det.count
    fps = info["fps"]

    raw = det.candidates()
    cands = []
    for k, c in enumerate(raw, 1):
        item = {"id": k, "frame": c["frame"], "time": round(c["frame"] / fps, 3),
                "endFrame": c["endFrame"], "kind": c["kind"],
                "confidence": round(min(1.0, c["conf"]), 2), "color": c["color"]}
        item["x"], item["y"] = det.to_video(c["c"])
        if c["kind"] == "drag":
            item["from"] = det.to_video(c["frm"])
            item["to"] = det.to_video(c["to"])
            item["x"], item["y"] = item["from"]
        offs = sorted({min(total - 1, max(0, c["frame"] + round(o * fps)))
                       for o in THUMB_OFFSETS} | ({c["endFrame"]} if c["kind"] == "drag" else set()))
        item["thumbFrames"] = offs
        item["thumb"] = f"c{k:03d}_f{c['frame']:05d}.jpg"
        cands.append(item)

    os.makedirs(out_dir, exist_ok=True)
    wanted = {}
    for c in cands:
        for f in c["thumbFrames"]:
            wanted.setdefault(f, []).append(c)
    dumps = {int(f) for f in frames}
    bad = sorted(f for f in dumps if not 0 <= f < total)
    if bad:
        raise ToolError(f"--frames 的影格 {', '.join(map(str, bad))} 超出影片長度"
                        f"（影片共 {total} 幀）")
    scale = min(1.0, THUMB_WIDTH / info["width"])
    tiles = {c["id"]: {} for c in cands}
    frame_files = {}
    last = max(list(wanted) + list(dumps), default=-1)
    if last >= 0:
        for i, frame in video_mod.iter_frames(video):
            if i in dumps:
                base = os.path.join(out_dir, f"f{i:05d}")
                _imwrite(base + ".png", frame)
                _imwrite(base + "_grid.png", _grid(frame))
                frame_files[i] = base + ".png"
            for c in wanted.get(i, ()):
                pos = (c["x"], c["y"])
                marks = [("line", c["from"], c["to"])] if c["kind"] == "drag" \
                    else [("dot", pos, None)]
                dt = (i - c["frame"]) / fps
                label = f"f{i} {dt:+.2f}s"
                tiles[c["id"]][i] = _tile(frame, scale, label, marks,
                                          strong=i in (c["frame"], c["endFrame"]))
            if i >= last:
                break
    for c in cands:
        imgs = [tiles[c["id"]][f] for f in c["thumbFrames"] if f in tiles[c["id"]]]
        cols = 4
        th, tw = imgs[0].shape[:2]
        rows = math.ceil(len(imgs) / cols)
        sheet = np.zeros((rows * th, cols * tw, 3), np.uint8)
        for k, im in enumerate(imgs):
            r, q = divmod(k, cols)
            sheet[r * th:(r + 1) * th, q * tw:(q + 1) * tw] = im
        _imwrite(os.path.join(out_dir, c["thumb"]), sheet, ".jpg",
                 (cv2.IMWRITE_JPEG_QUALITY, 85))

    result = {"video": video, "width": info["width"], "height": info["height"],
              "fps": fps, "frames": total,
              "mode": "sample" if smp else "fallback",
              "highConfidence": HIGH, "candidates": cands}
    path = os.path.join(out_dir, "candidates.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    result["candidates_path"] = path
    result["frame_files"] = frame_files
    return result
