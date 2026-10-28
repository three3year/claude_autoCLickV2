from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass

import cv2

from automation import findtarget, flowfmt, pickcheck

from .errors import ToolError
from .geom import center as _center

def position_tolerance(box):
    return max(6.0, 0.25 * min(box[2], box[3]))


def make_engine():
    import warnings

    from subject_detection.engine import Engine
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Engine()


DRIFT_MARGIN = 80


def fixed_rect(box, size, anchor, scroll=None, drift=None, toward=None):
    return expand_rect(box, (box[2], box[3]), size, anchor, scroll, drift, toward)


def expand_rect(box, tpl, size, anchor, scroll=None, drift=None, toward=None):
    x, y, w, h = box
    W, H = size
    mx, my = math.ceil(tpl[0] / 2), math.ceil(tpl[1] / 2)
    if drift == "vertical":
        my = max(my, DRIFT_MARGIN)
    elif drift == "horizontal":
        mx = max(mx, DRIFT_MARGIN)
    x0, y0, x1, y1 = x - mx, y - my, x + w + mx, y + h + my
    if scroll == "vertical":
        y0, y1 = 0, H
    elif scroll == "horizontal":
        x0, x1 = 0, W
    if toward == "left":
        x0 = 0
    elif toward == "right":
        x1 = W
    elif toward == "up":
        y0 = 0
    elif toward == "down":
        y1 = H
    clipped = {side for side, out in (("left", x0 < 0), ("top", y0 < 0),
                                      ("right", x1 > W), ("bottom", y1 > H)) if out}
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    return flowfmt.rect_from_screen((x0, y0, x1 - x0, y1 - y0), anchor), clipped


class _Detector:

    def __init__(self, engine, lib):
        self.engine, self.lib = engine, lib

    def query(self, name, image, color_check=False, expected_scale=None):
        return self.engine.query(self.lib, name, image, color_check=color_check,
                                 expected_scale=expected_scale)


def detector(engine, images, config):
    return Checker(engine, images, {}, [], {}, config, None, (1, 1)).detector


def color_modes(name, steps, extra=()):
    tgts = list(extra)
    for s in steps:
        if findtarget.is_find(s):
            tgts.append(findtarget.target(s))
        if findtarget.uses_confirm_target(s):
            tgts.append(findtarget.confirm_target(s))
    modes = {bool(t.get("color")) for t in tgts if t.get("template") == name}
    return sorted(modes) or [False]


@dataclass
class _Member:
    tgt: dict
    frame: int
    origin: tuple | None
    label: str
    box: tuple | None
    picked: tuple | None
    shift: tuple


class Checker:

    def __init__(self, engine, crops, templates, steps, frames, config, anchor, size,
                 extra_targets=()):
        from subject_detection import make_library

        self.engine, self.templates, self.frames = engine, templates, frames
        self.anchor, self.size = anchor, size
        self.sizes = {n: (img.shape[1], img.shape[0]) for n, img in crops.items()}
        self.results = {n: {"reasons": [], "boxes": {}} for n in crops}
        self._registered = set()
        self._scale_checked = set()
        with tempfile.TemporaryDirectory(prefix="vtf_verify_") as tmp:
            paths = {}
            for i, (name, img) in enumerate(crops.items()):
                p = os.path.join(tmp, f"t{i:03d}.png")
                ok, buf = cv2.imencode(".png", img)
                if not ok:
                    raise ToolError(f"範本「{name}」無法編碼成 PNG")
                buf.tofile(p)
                paths[name] = p
            self.lib = make_library(paths, config, os.path.join(tmp, "registered"))
            for name in crops:
                try:
                    engine.register(self.lib, name)
                    self._registered.add(name)
                except Exception as e:
                    self.results[name]["reasons"].append(
                        f"引擎無法登錄這張範本（{e}）")
        self.detector = _Detector(engine, self.lib)
        self.registered = frozenset(self._registered)
        self._cache = {}
        self._members = {}
        for name, t in templates.items():
            if name not in crops:
                continue
            if name in self._registered:
                for color in color_modes(name, steps, extra_targets):
                    self._check_template(name, t, color)
                    self._check_scale(name, t["frame"], color)
            if not t["clean"]:
                self.results[name]["reasons"].append("找不到乾淨影格（計畫標示）")

    def _matches(self, name, frame, color):
        key = (name, frame, color)
        if key not in self._cache:
            r = self.engine.query(self.lib, name, self.frames[frame],
                                  color_check=color, expected_scale=1.0)
            self._cache[key] = [tuple(int(v) for v in m.box) for m in r.matches]
        return self._cache[key]

    def _check_template(self, name, t, color):
        res = self.results[name]
        tol = position_tolerance(t["box"])
        checks = [(t["frame"], _center(t["box"]), "取材幀")]
        checks += [(p["frame"], tuple(p["at"]) if p["at"] else _center(t["box"]),
                    "出現幀") for p in t["present"]]
        for frame, want, label in checks:
            boxes = self._matches(name, frame, color)
            if not boxes:
                res["reasons"].append(f"{label}（第 {frame} 幀）找不到")
                continue
            near = min(boxes, key=lambda b: (_center(b)[0] - want[0]) ** 2
                       + (_center(b)[1] - want[1]) ** 2)
            gx, gy = _center(near)
            if ((gx - want[0]) ** 2 + (gy - want[1]) ** 2) ** 0.5 > tol:
                res["reasons"].append(
                    f"位置不符（第 {frame} 幀：預期中心 {want[0]},{want[1]}、"
                    f"找到 {gx},{gy}）")
            else:
                res["boxes"].setdefault(frame, near)
        for frame in t["absent"]:
            if self._matches(name, frame, color):
                res["reasons"].append(f"出現前就匹配（第 {frame} 幀不該找得到）")

    def _check_scale(self, name, frame, color):
        key = (name, color)
        if key in self._scale_checked:
            return
        self._scale_checked.add(key)
        probe = {"template": name, "color": color}
        for w in pickcheck.scale_margin(self.detector, self.frames[frame], (0, 0),
                                        probe, anchor=None, scale=1.0):
            self.results[name]["reasons"].append(f"縮放餘裕：{w.text}")

    def locate_target(self, tgt, frame, origin, label, at=None, scroll=None,
                      fallback_box=None, shift=(0, 0), shared=None, drift=None, toward=None):
        dx, dy = shift
        if origin is not None:
            origin = (origin[0] - dx, origin[1] - dy)
        if at is not None:
            at = [at[0] - dx, at[1] - dy]
        box, within = self._locate(tgt, frame, origin, label, at,
                                   (scroll, drift, toward), fallback_box, (dx, dy), shared)
        if box is not None and (dx, dy) != (0, 0):
            box = (box[0] + dx, box[1] + dy, box[2], box[3])
        return box, within

    def _locate(self, tgt, frame, origin, label, at, rule, fallback_box, shift, shared):
        name = tgt["template"]
        res = self.results[name]
        size = self.sizes[name]
        if frame not in self.frames:
            raise ToolError(f"工具錯誤：第 {frame} 幀沒有讀進來")
        box = fallback_box
        picked = None
        if name in self._registered:
            if name not in self.templates:
                self._check_scale(name, frame, bool(tgt.get("color")))
            f = findtarget.find(tgt, self.detector, self.frames[frame], (0, 0),
                                origin=origin, scale=1.0)
            if f.picked is None:
                why = {"count": f"（挑選規則挑不到：只有 {len(f.matches)} 個匹配）"}.get(
                    f.reason, "")
                res["reasons"].append(f"{label}（第 {frame} 幀）找不到{why}")
                res["boxes"].setdefault(frame, None)
            else:
                picked = box = f.picked.box
                res["boxes"][frame] = box
                gx, gy = _center(box)
                if at is not None:
                    if abs(at[0] - gx) > box[2] or abs(at[1] - gy) > box[3]:
                        res["reasons"].append(
                            f"位置不符（{label}，第 {frame} 幀：點擊位置 {at[0]},{at[1]} "
                            f"離挑中的框 {gx},{gy} 太遠）")
                elif (name in self.templates and frame == self.templates[name]["frame"]
                      and fallback_box is not None):
                    want = _center(fallback_box)
                    if math.dist((gx, gy), want) > position_tolerance(fallback_box):
                        res["reasons"].append(
                            f"位置不符（{label}，第 {frame} 幀：挑中的是 {gx},{gy}，"
                            f"不是取材的 {want[0]},{want[1]}）")
        if shared is not None:
            self._members.setdefault(shared, []).append(
                _Member(tgt, frame, origin, label, box, picked, shift))
            return box, None
        if box is None:
            return fallback_box, None
        moved = (box[0] + shift[0], box[1] + shift[1], box[2], box[3])
        within, clipped = fixed_rect(moved, self.size, self.anchor, *rule)
        for w in pickcheck.rect_margin(dict(tgt, within=within), size):
            if not clipped:
                raise ToolError(f"工具錯誤：{label} 的固定矩形沒過矩形餘裕：{w.text}")
        self._recheck(tgt, within, frame, origin, label, picked, shift)
        return box, within

    def _recheck(self, tgt, within, frame, origin, label, picked, shift):
        if picked is not None:
            res = self.results[tgt["template"]]
            anchor = (self.anchor[0] - shift[0], self.anchor[1] - shift[1])
            full = dict(tgt, within=within)
            f2 = findtarget.find(full, self.detector, self.frames[frame], (0, 0),
                                 origin=origin, scale=1.0, anchor=anchor)
            if (f2.picked is None or math.dist(_center(f2.picked.box), _center(picked))
                    > position_tolerance(picked)):
                res["reasons"].append(
                    f"加上固定矩形後挑到的不是同一個（{label}，第 {frame} 幀）")
            for w in pickcheck.unique(self.detector, self.frames[frame], (0, 0), full,
                                      anchor=anchor, scale=1.0, origin=origin):
                res["reasons"].append(f"唯一（{label}，第 {frame} 幀）：{w.text}")

    def resolve_shared(self, decls):
        out = {}
        for name, members in self._members.items():
            d = decls[name]
            copied = "within" in d
            if copied:
                within, clipped = list(d["within"]), set()
                where = flowfmt.rect_to_screen(within, self.anchor)
                what = f"照抄的框 {list(where)}（流程尺度、執行時的位置）"
            else:
                shifts = {m.shift for m in members}
                if len(shifts) > 1:
                    raise ToolError(
                        f"共用矩形「{name}」的成員有的在插入段第一次拖曳之前、有的在之後"
                        "（對齊位移不同），容器的位置對不上全部成員——拆成兩個共用矩形")
                dx, dy = shifts.pop()
                x, y, w, h = d["box"]
                where = (x + dx, y + dy, w, h)
                what = f"容器框 {d['box']}（第 {d['frame']} 幀）"
                sizes = [m.box[2:] if m.box is not None else self.sizes[m.tgt["template"]]
                         for m in members]
                tpl = (max(w for w, _ in sizes), max(h for _, h in sizes))
                within, clipped = expand_rect(where, tpl, self.size, self.anchor,
                                              d.get("scroll"))
            for m in members:
                if m.picked is None:
                    continue
                x, y, w, h = m.box[0] + m.shift[0], m.box[1] + m.shift[1], *m.box[2:]
                if (x < where[0] or y < where[1] or x + w > where[0] + where[2]
                        or y + h > where[1] + where[3]):
                    raise ToolError(
                        f"共用矩形「{name}」：{m.label}在第 {m.frame} 幀挑中的框 "
                        f"{[x, y, w, h]} 有一部分在{what}外——"
                        + ("新成員不在同一個容器裡，或錄影畫面對不上：確認 same_as 指的那一組"
                           if copied else
                           "容器要框整個容器的所有格子（重框 box）；挑錯目標就改那一步的 "
                           "frame／at 或挑選規則"))
            for m in members:
                m.tgt["within"] = within
                for w in pickcheck.rect_margin(m.tgt, self.sizes[m.tgt["template"]]):
                    if copied:
                        raise ToolError(f"共用矩形「{name}」照抄的框對{m.label}餘裕不足：{w.text}"
                                        "——新成員的圖比同組既有的大；改用影片像素宣告新的共用矩形")
                    if not clipped:
                        raise ToolError(f"工具錯誤：{m.label}的共用矩形「{name}」沒過矩形餘裕："
                                        f"{w.text}")
                self._recheck(m.tgt, within, m.frame, m.origin, m.label, m.picked, m.shift)
            out[name] = within
        return out

    def finish(self):
        for res in self.results.values():
            res["reasons"] = list(dict.fromkeys(res["reasons"]))
        return self.results


RETAKE_ADVICE = {
    "找不到乾淨影格": "在遊戲裡停在這個畫面、游標移開後，用編輯器的範本面板重新拾取",
    "縮放餘裕": "範本在縮放後貼近門檻（視窗模式／最大化會縮放畫面）；重截或裁小：框按鈕本體、"
             "避開會變的數字與透出的背景，或換一幀",
    "唯一": "固定矩形裡有多個同款：這張圖不能當參考點；換一張畫面上唯一的圖當參考點，"
          "或設挑選規則（第 N 個／最接近指定點）",
    "出現前就匹配": "範本框到了畫面上本來就有的東西；重新框只屬於這個按鈕的部分（文字、圖示）；"
               "只差顏色時開比色",
    "位置不符": "畫面上可能有長得一樣的東西；框大一點把周邊有辨識度的部分包進來，"
            "或用挑選規則指定是哪一個",
    "加上固定矩形後": "框附近有同款圖；換一張唯一的圖或設挑選規則",
    "找不到": "範本可能框到空白處或被游標/特效污染；換一幀或重新框按鈕本體；"
           "有設挑選規則時確認設定",
    "引擎無法登錄": "範本沒有可辨識的結構（純色）；改框有文字或圖示的地方",
}


def advice(reasons):
    out = []
    for why in reasons:
        for key, tip in RETAKE_ADVICE.items():
            if key in why:
                if tip not in out:
                    out.append(tip)
                break
    return out or ["用編輯器的範本面板重新拾取這張範本"]
