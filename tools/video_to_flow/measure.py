"""量測核心: 計畫的步驟 (影片像素) → 流程步驟 (偏移、固定矩形), `assemble` 與 `insert` 共用.

輸入的影格已是`流程尺度` (補充時先整張縮放 1/影片倍率), anchor 是`座標基準點`在影格上的
位置。這裡做的事兩個入口一模一樣: 原點推算、每個找圖目標挑框＋固定矩形＋拾取檢查、
忙碌指示的固定矩形、`共用矩形`、忙碌檢查的兩向報告、捲動軸沒宣告的找圖。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from automation import findtarget

from . import origin as origin_mod
from . import plan as plan_mod
from . import video as video_mod
from .errors import ToolError
from .labels import label

INPUT_TYPES = ("find_click", "click", "drag")   # 送出輸入的步驟 (可勾忙碌檢查)


def step_frame(p, i):
    """第 i 步 (0-based) 在影片裡看的那一幀; 座標點擊/拖曳沒寫＝None."""
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
    """第 i 步確認圖的證據影格 (預設＝確認圖範本的取材幀)."""
    ev = p.evidence[i] or {}
    if ev.get("confirm_frame") is not None:
        return ev["confirm_frame"]
    name = findtarget.confirm_template(p.steps[i])
    if name in p.templates:
        return p.templates[name]["frame"]
    raise ToolError(f"轉換計畫有誤：步驟 {i + 1}：確認圖用既有範本「{name}」時，confirm 要寫 "
                    "frame（確認圖出現的那一幀）")


def frames_needed(p, extra=()):
    """驗證要讀的影格編號."""
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
    steps: list                                     # 流程步驟 (偏移、固定矩形已算好)
    busy: dict | None = None                        # 忙碌指示的找圖目標 (含 within)
    no_scroll: set = field(default_factory=set)     # 沒宣告捲動軸的找圖步驟索引
    busy_unseen: list = field(default_factory=list)     # 勾了、之後沒看到 [(索引, 文字)]
    busy_unchecked: list = field(default_factory=list)  # 沒勾、之後看到了
    shared: dict = field(default_factory=dict)          # 共用矩形 {名: within}
    loosened: list = field(default_factory=list)        # 停點差／遞補方向 [(索引, 鍵, 值)]


def measure(p, checker, busy=None, shifts=None):
    """原點推算＋每個找圖目標挑框與固定矩形; busy: 忙碌指示 (組裝＝計畫的, 帶證據影格 frame;
    補充＝既有流程的, 原樣用); shifts: 補充對齊時每步的`對齊位移` (見 align.apply).
    回傳 `Measured`."""

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
    # 共用矩形的成員、宣告停點差或遞補方向的都算已宣告 (固定矩形的來源一步只能有一個)
    out.no_scroll = {i for i, s in enumerate(steps)
                     if findtarget.is_find(s) and not any(
                         (p.evidence[i] or {}).get(k) for k in plan_mod.RECT_KEYS)}
    out.loosened = loosened(p)
    if busy is not None and "frame" in busy:   # 計畫的忙碌指示: 在證據影格上挑框
        frame = busy["frame"]
        tgt = {k: v for k, v in busy.items() if k not in ("frame", "rect")}
        name = tgt["template"]
        _, within = checker.locate_target(tgt, frame, None, f"忙碌指示「{name}」",
                                          fallback_box=p.templates[name]["box"],
                                          shared=busy.get("rect"))
        if not busy.get("rect"):               # 共用矩形的成員: resolve_shared 就地寫 within
            tgt["within"] = within
        out.busy = tgt
    elif busy is not None:                     # 既有流程的: 原樣用
        out.busy = dict(busy)
    out.shared = checker.resolve_shared(p.shared_rects)
    return out


def loosened(p):
    """宣告了`停點差`或`遞補方向`的找圖 → [(步驟索引, "drift"/"shift", 方向)] (依流程順序)."""
    return [(i, k, ev[k]) for i, ev in enumerate(p.evidence) if ev
            for k in ("drift", "shift") if ev.get(k)]


def shared_members(p, steps):
    """`共用矩形`的成員 (報告用內容指稱) → {名: [(步驟索引或 None (忙碌指示), 文字)]}."""
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
    """`忙碌檢查`的兩向報告: 每個送出輸入的步驟, 從它那一幀到下一個有影格的步驟那一幀之間
    (最後一步到影片結束) 抽樣找忙碌指示. 只報告, 不擋. 就地填 measured 的兩份清單."""
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
