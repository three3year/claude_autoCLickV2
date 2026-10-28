from __future__ import annotations

from dataclasses import dataclass, field

from automation import findtarget

from . import origin as origin_mod
from . import plan as plan_mod
from . import video as video_mod
from .errors import ToolError
from .labels import label

INPUT_TYPES = ("find_click", "click", "drag")


def step_frame(p, i):
    s, ev = p.steps[i], p.evidence[i] or {}
    if ev.get("frame") is not None:
        return ev["frame"]
    if findtarget.is_find(s):
        name = findtarget.template(s)
        if name in p.templates:
            return p.templates[name]["frame"]
        raise ToolError(f"轉換計畫有誤：步驟 {i + 1}：引用既有範本「{name}」的找圖要寫 frame"
                        "（它在影片的哪一幀）")
    return None


def confirm_frame(p, i):
    ev = p.evidence[i] or {}
    if ev.get("confirm_frame") is not None:
        return ev["confirm_frame"]
    name = findtarget.confirm_template(p.steps[i])
    if name in p.templates:
        return p.templates[name]["frame"]
    raise ToolError(f"轉換計畫有誤：步驟 {i + 1}：確認圖用既有範本「{name}」時，confirm 要寫 "
                    "frame（確認圖出現的那一幀）")


def frames_needed(p, extra=()):
    need = set(extra)
    for t in p.templates.values():
        need.add(t["frame"])
        need.update(pr["frame"] for pr in t["present"])
        need.update(t["absent"])
    for i, s in enumerate(p.steps):
        f = step_frame(p, i)
        if f is not None:
            need.add(f)
        if findtarget.uses_confirm_target(s):
            need.add(confirm_frame(p, i))
    if p.busy:
        need.add(p.busy["frame"])
    need.update(d["frame"] for d in p.shared_rects.values() if "frame" in d)
    return need


@dataclass
class Measured:
    steps: list
    busy: dict | None = None
    no_scroll: set = field(default_factory=set)
    busy_unseen: list = field(default_factory=list)
    busy_unchecked: list = field(default_factory=list)
    shared: dict = field(default_factory=dict)
    loosened: list = field(default_factory=list)


def measure(p, checker, busy=None, shifts=None):

    def shift(i):
        return shifts[i] if shifts else (0, 0)

    def locate(i, s, tgt, origin):
        ev = p.evidence[i] or {}
        frame = step_frame(p, i)
        name = tgt["template"]
        fb = p.templates[name]["box"] if name in p.templates else None
        return checker.locate_target(tgt, frame, origin, f"{label(s)}那一步",
                                     at=ev.get("at"), scroll=ev.get("scroll"),
                                     fallback_box=fb, shift=shift(i), shared=ev.get("rect"),
                                     drift=ev.get("drift"), toward=ev.get("shift"))

    def locate_confirm(i, s, ctgt, origin):
        frame = confirm_frame(p, i)
        name = ctgt["template"]
        fb = p.templates[name]["box"] if name in p.templates else None
        _, within = checker.locate_target(ctgt, frame, origin,
                                          f"{label(s)}的確認圖「{name}」",
                                          fallback_box=fb, shift=shift(i),
                                          shared=(p.evidence[i] or {}).get("confirm_rect"))
        return within

    steps = origin_mod.derive(p.steps, p.evidence, p.templates, locate, locate_confirm)
    out = Measured(steps)
    out.no_scroll = {i for i, s in enumerate(steps)
                     if findtarget.is_find(s) and not any(
                         (p.evidence[i] or {}).get(k) for k in plan_mod.RECT_KEYS)}
    out.loosened = loosened(p)
    if busy is not None and "frame" in busy:
        frame = busy["frame"]
        tgt = {k: v for k, v in busy.items() if k not in ("frame", "rect")}
        name = tgt["template"]
        _, within = checker.locate_target(tgt, frame, None, f"忙碌指示「{name}」",
                                          fallback_box=p.templates[name]["box"],
                                          shared=busy.get("rect"))
        if not busy.get("rect"):
            tgt["within"] = within
        out.busy = tgt
    elif busy is not None:
        out.busy = dict(busy)
    out.shared = checker.resolve_shared(p.shared_rects)
    return out


def loosened(p):
    return [(i, k, ev[k]) for i, ev in enumerate(p.evidence) if ev
            for k in ("drift", "shift") if ev.get(k)]


def shared_members(p, steps):
    out = {}
    for name, refs in plan_mod.shared_refs(p).items():
        for i, kind in refs:
            if kind == "busy":
                text = f"忙碌指示「{p.busy['template']}」"
            elif kind == "confirm":
                text = f"{label(steps[i])}的確認圖「{findtarget.confirm_template(steps[i])}」"
            else:
                text = label(steps[i])
            out.setdefault(name, []).append((i, text))
    return out


SAMPLES_PER_SECOND = 4
MAX_SAMPLES = 40


def busy_two_way(p, measured, checker, info, rescale=None):
    busy = measured.busy
    if not busy:
        return
    frames = [step_frame(p, i) for i in range(len(p.steps))]
    for i, s in enumerate(p.steps):
        if s["type"] in ("click", "drag") and frames[i] is None:
            raise ToolError(f"轉換計畫有誤：步驟 {i + 1}：有忙碌指示時，座標點擊與拖曳要寫 "
                            "frame（送出輸入的那一幀），工具要看它之後有沒有忙碌")
    end = max([int(info.get("frames") or 0)] + [f + 1 for f in frames if f is not None])
    step = max(1, round(info.get("fps", 30) / SAMPLES_PER_SECOND))
    intervals = {}
    for i, s in enumerate(p.steps):
        if s["type"] not in INPUT_TYPES:
            continue
        start = frames[i]
        nxt = next((frames[j] for j in range(i + 1, len(frames))
                    if frames[j] is not None), end)
        if nxt <= start:
            continue
        picks = list(range(start + 1, nxt, step))
        if len(picks) > MAX_SAMPLES:
            k = len(picks) / MAX_SAMPLES
            picks = [picks[int(n * k)] for n in range(MAX_SAMPLES)]
        intervals[i] = picks
    want = {f for picks in intervals.values() for f in picks}
    seen = set()
    if want:
        last = max(want)
        for f, img in video_mod.iter_frames(p.video):
            if f > last:
                break
            if f not in want:
                continue
            if rescale is not None:
                img = rescale(img)
            hit = findtarget.find(busy, checker.detector, img, (0, 0), scale=1.0,
                                  anchor=checker.anchor)
            if hit.picked is not None:
                seen.add(f)
    for i, picks in intervals.items():
        s = measured.steps[i]
        saw = any(f in seen for f in picks)
        text = f"{label(s)}（第 {frames[i]} 幀送出）"
        if s.get("busy_check") and not saw:
            measured.busy_unseen.append((i, text))
        elif not s.get("busy_check") and saw:
            measured.busy_unchecked.append((i, text))
