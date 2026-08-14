"""Coarse stage: masked multiscale template matching in the gradient domain.

Gradients are invariant to brightness offsets, and the normalized correlation
kills contrast scaling, so color shift / night mode / graying survive without
any color handling. The sweep is coarse-to-fine: scan a geometric scale grid
on a downscaled scene, then refine the surviving candidates at full
resolution with fine scale steps and aspect jitter.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

_SCALE_STEP = 1.09          # geometric step of the coarse scale grid
_COARSE_MAX_DIM = 640       # scene is downscaled to about this for the sweep
_MIN_TPL_PX = 8             # scaled template may not drop below this
_TOP_K = 5                  # candidates handed to refinement / verification
_NMS_IOU = 0.3


@dataclass
class Candidate:
    box: tuple[int, int, int, int]   # (x, y, w, h) in scene coords
    score: float
    scale: float
    aspect: float


def gradient_map(gray: np.ndarray) -> np.ndarray:
    g = gray.astype(np.float32)
    gx = cv2.Scharr(g, cv2.CV_32F, 1, 0)
    gy = cv2.Scharr(g, cv2.CV_32F, 0, 1)
    return cv2.magnitude(gx, gy)


def _window_variance(img: np.ndarray, w: int, h: int,
                     out_shape: tuple[int, int]) -> np.ndarray:
    """Variance of img over each (w, h) sliding window, aligned with the
    matchTemplate result grid."""
    kernel = (w, h)
    mean = cv2.boxFilter(img, cv2.CV_32F, kernel, anchor=(0, 0),
                         normalize=True, borderType=cv2.BORDER_CONSTANT)
    sq = cv2.boxFilter(img * img, cv2.CV_32F, kernel, anchor=(0, 0),
                       normalize=True, borderType=cv2.BORDER_CONSTANT)
    var = sq - mean * mean
    return var[:out_shape[0], :out_shape[1]]


def _match(scene_grad: np.ndarray, tpl_grad: np.ndarray,
           mask: np.ndarray | None) -> np.ndarray:
    # CCOEFF (zero-mean) is essential: gradient magnitudes are non-negative,
    # and without mean subtraction two near-constant positive patches score
    # cosine ~1, saturating flat background regions.
    if mask is not None:
        res = cv2.matchTemplate(scene_grad, tpl_grad, cv2.TM_CCOEFF_NORMED,
                                mask=mask)
    else:
        res = cv2.matchTemplate(scene_grad, tpl_grad, cv2.TM_CCOEFF_NORMED)
    res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
    # OpenCV reports 1.0 for zero-variance windows (flat UI panels have
    # exactly-zero gradients) — a degenerate value, not a match. Kill any
    # window whose local gradient variance is essentially zero.
    th, tw = tpl_grad.shape
    var = _window_variance(scene_grad, tw, th, res.shape)
    res[var < 1e-4] = 0.0
    res[np.abs(res) > 1.001] = 0.0
    return np.clip(res, 0.0, 1.0)


def _resize(img: np.ndarray, w: int, h: int) -> np.ndarray:
    interp = cv2.INTER_AREA if w < img.shape[1] else cv2.INTER_LINEAR
    return cv2.resize(img, (w, h), interpolation=interp)


def _iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def _scale_grid(lo: float, hi: float) -> list[float]:
    scales = []
    s = lo
    while s < hi * 1.0001:
        scales.append(s)
        s *= _SCALE_STEP
    if scales[-1] < hi * 0.999:
        scales.append(hi)
    return scales


def find_candidates(scene_gray: np.ndarray, tpl_gray: np.ndarray,
                    scale_range: tuple[float, float], aspect_jitter: float,
                    mask: np.ndarray | None = None,
                    top_k: int = _TOP_K) -> list[Candidate]:
    """Sweep scales/aspect and return the best-scoring candidate boxes."""
    sh, sw = scene_gray.shape
    th, tw = tpl_gray.shape
    lo, hi = float(scale_range[0]), float(scale_range[1])

    # --- coarse pass on a downscaled scene ---------------------------------
    down = min(1.0, _COARSE_MAX_DIM / max(sh, sw))
    # never let the smallest swept template drop under _MIN_TPL_PX
    min_native = min(th, tw) * lo
    if min_native * down < _MIN_TPL_PX:
        down = min(1.0, _MIN_TPL_PX / min_native)
    ds = _resize(scene_gray, max(1, round(sw * down)), max(1, round(sh * down)))
    scene_grad_small = gradient_map(ds)
    scene_grad_full = gradient_map(scene_gray)

    raw: list[Candidate] = []
    for s in _scale_grid(lo, hi):
        w = round(tw * s * down)
        h = round(th * s * down)
        if w < _MIN_TPL_PX or h < _MIN_TPL_PX:
            continue
        if w >= ds.shape[1] or h >= ds.shape[0]:
            continue
        tpl_s = _resize(tpl_gray, w, h)
        m = _resize(mask, w, h) if mask is not None else None
        res = _match(scene_grad_small, gradient_map(tpl_s), m)
        _, val, _, loc = cv2.minMaxLoc(res)
        raw.append(Candidate(
            box=(round(loc[0] / down), round(loc[1] / down),
                 round(tw * s), round(th * s)),
            score=float(val), scale=s, aspect=1.0))

    raw.sort(key=lambda c: c.score, reverse=True)
    kept: list[Candidate] = []
    for c in raw:
        if all(_iou(c.box, k.box) < _NMS_IOU for k in kept):
            kept.append(c)
        if len(kept) >= top_k:
            break

    # --- refinement at full resolution -------------------------------------
    refined: list[Candidate] = []
    for c in kept:
        refined.append(_refine(scene_grad_full, tpl_gray, mask, c,
                               aspect_jitter))
    refined.sort(key=lambda c: c.score, reverse=True)
    return refined


def _refine(scene_grad: np.ndarray, tpl_gray: np.ndarray,
            mask: np.ndarray | None, cand: Candidate,
            aspect_jitter: float) -> Candidate:
    sh, sw = scene_grad.shape
    th, tw = tpl_gray.shape
    x, y, w, h = cand.box
    # local window with margin around the coarse hit
    mx, my = max(8, w // 2), max(8, h // 2)
    x0, y0 = max(0, x - mx), max(0, y - my)
    x1, y1 = min(sw, x + w + mx), min(sh, y + h + my)
    window = scene_grad[y0:y1, x0:x1]

    aspects = [1.0 - aspect_jitter, 1.0, 1.0 + aspect_jitter] \
        if aspect_jitter > 0 else [1.0]
    best = None
    for s in (cand.scale / _SCALE_STEP ** 0.5, cand.scale,
              cand.scale * _SCALE_STEP ** 0.5):
        for a in aspects:
            w2, h2 = round(tw * s * a), round(th * s)
            if w2 < 4 or h2 < 4 or w2 >= window.shape[1] or h2 >= window.shape[0]:
                continue
            tpl_s = _resize(tpl_gray, w2, h2)
            m = _resize(mask, w2, h2) if mask is not None else None
            res = _match(window, gradient_map(tpl_s), m)
            _, val, _, loc = cv2.minMaxLoc(res)
            c = Candidate(box=(x0 + loc[0], y0 + loc[1], w2, h2),
                          score=float(val), scale=s, aspect=a)
            if best is None or c.score > best.score:
                best = c
    return best if best is not None else cand
