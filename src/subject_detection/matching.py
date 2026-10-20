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
_TOP_K = 20                 # candidates handed to refinement / verification:
                            # enough for a row of a dozen identical subjects
_BEST_K = 5                 # per-scale best peaks always refined too (the
                            # single-instance pool), on top of top_k
_PEAKS_PER_SCALE = 64       # local peaks examined per scale (before NMS)
_NMS_IOU = 0.3
_EXPECTED_STEPS = 2         # expected scale given: sweep this many grid steps
                            # each side of it (fixed here, not a config knob)


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
                     out_shape: tuple[int, int],
                     mask: np.ndarray | None) -> np.ndarray:
    """Variance of img over each (w, h) sliding window — under the mask when
    given — aligned with the matchTemplate result grid."""
    if mask is None:
        mean = cv2.boxFilter(img, cv2.CV_32F, (w, h), anchor=(0, 0),
                             normalize=True, borderType=cv2.BORDER_CONSTANT)
        sq = cv2.boxFilter(img * img, cv2.CV_32F, (w, h), anchor=(0, 0),
                           normalize=True, borderType=cv2.BORDER_CONSTANT)
    else:
        k = mask / max(float(mask.sum()), 1e-6)
        mean = cv2.filter2D(img, cv2.CV_32F, k, anchor=(0, 0),
                            borderType=cv2.BORDER_CONSTANT)
        sq = cv2.filter2D(img * img, cv2.CV_32F, k, anchor=(0, 0),
                          borderType=cv2.BORDER_CONSTANT)
    var = sq - mean * mean
    return var[:out_shape[0], :out_shape[1]]


def _masked_variance(img: np.ndarray, mask: np.ndarray | None) -> float:
    if mask is None:
        return float(img.var())
    wsum = max(float(mask.sum()), 1e-6)
    mean = float((img * mask).sum()) / wsum
    return float((((img - mean) ** 2) * mask).sum()) / wsum


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
    # Windows with (near-)zero gradient variance under the mask are flat UI
    # panels or empty background; OpenCV's normalization degenerates there
    # (reporting up to 1.0), so kill any window whose masked variance is far
    # below the template's own — a real match needs comparable structure.
    th, tw = tpl_grad.shape
    var = _window_variance(scene_grad, tw, th, res.shape, mask)
    floor = max(1e-4, 0.0025 * _masked_variance(tpl_grad, mask))
    res[var < floor] = 0.0
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


def _expected_grid(expected: float) -> list[float]:
    """The scales swept around an expected scale: centered on it, so the
    expected scale itself is always on the grid (an off-grid sweep lands the
    box a few px off, enough to fail the color check)."""
    return [expected * _SCALE_STEP ** k
            for k in range(-_EXPECTED_STEPS, _EXPECTED_STEPS + 1)]


def _local_peaks(res: np.ndarray, w: int, h: int,
                 threshold: float | None) -> list[tuple[int, int, float]]:
    """(x, y, score) of the result map's peaks at one scale.

    The global maximum always counts (the single-instance behavior); with a
    threshold, every other local maximum at or above it counts too, so
    several identical subjects at the same scale all survive. Peaks closer
    than half a template are one peak (same-scale NMS).
    """
    _, val, _, loc = cv2.minMaxLoc(res)
    peaks = [(loc[0], loc[1], float(val))]
    if threshold is None or val < threshold:
        return peaks
    k = cv2.getStructuringElement(cv2.MORPH_RECT,
                                  (max(3, w // 2) | 1, max(3, h // 2) | 1))
    ys, xs = np.nonzero((res >= cv2.dilate(res, k)) & (res >= threshold))
    order = np.argsort(-res[ys, xs])[:_PEAKS_PER_SCALE]
    for i in order:
        x, y = int(xs[i]), int(ys[i])
        if all(_iou((x, y, w, h), (px, py, w, h)) < _NMS_IOU
               for px, py, _ in peaks):
            peaks.append((x, y, float(res[y, x])))
    return peaks


def _nms(cands: list[Candidate], limit: int | None = None) -> list[Candidate]:
    """Greedy non-maximum suppression by score (input order irrelevant)."""
    kept: list[Candidate] = []
    for c in sorted(cands, key=lambda c: c.score, reverse=True):
        if all(_iou(c.box, k.box) < _NMS_IOU for k in kept):
            kept.append(c)
            if limit is not None and len(kept) >= limit:
                break
    return kept


def find_candidates(scene_gray: np.ndarray, tpl_gray: np.ndarray,
                    scale_range: tuple[float, float], aspect_jitter: float,
                    mask: np.ndarray | None = None,
                    top_k: int = _TOP_K,
                    peak_threshold: float | None = None,
                    expected_scale: float | None = None) -> list[Candidate]:
    """Sweep scales/aspect and return candidate boxes, best first.

    Every scale contributes its best peak plus — given `peak_threshold` —
    every other local peak at or above it, so repeated identical subjects
    are all candidates. Refined candidates that converge on the same spot
    are merged (NMS). Given `expected_scale`, the coarse grid is the few
    scales centered on it instead of the whole `scale_range`."""
    sh, sw = scene_gray.shape
    th, tw = tpl_gray.shape
    if expected_scale is not None:
        grid = _expected_grid(float(expected_scale))
    else:
        grid = _scale_grid(float(scale_range[0]), float(scale_range[1]))
    lo = grid[0]

    # --- coarse pass on a downscaled scene ---------------------------------
    down = min(1.0, _COARSE_MAX_DIM / max(sh, sw))
    # never let the smallest swept template drop under _MIN_TPL_PX
    min_native = min(th, tw) * lo
    if min_native * down < _MIN_TPL_PX:
        down = min(1.0, _MIN_TPL_PX / min_native)
    ds = _resize(scene_gray, max(1, round(sw * down)), max(1, round(sh * down)))
    scene_grad_small = gradient_map(ds)
    scene_grad_full = gradient_map(scene_gray)

    # the coarse sweep runs unmasked (fast FFT path); the mask weighs in at
    # refinement, where the final score is computed
    best: list[Candidate] = []    # each scale's global maximum
    extra: list[Candidate] = []   # the other above-threshold peaks
    for s in grid:
        w = round(tw * s * down)
        h = round(th * s * down)
        if w < _MIN_TPL_PX or h < _MIN_TPL_PX:
            continue
        if w >= ds.shape[1] or h >= ds.shape[0]:
            continue
        tpl_s = _resize(tpl_gray, w, h)
        res = _match(scene_grad_small, gradient_map(tpl_s), None)
        for i, (px, py, val) in enumerate(_local_peaks(res, w, h,
                                                       peak_threshold)):
            (extra if i else best).append(Candidate(
                box=(round(px / down), round(py / down),
                     round(tw * s), round(th * s)),
                score=val, scale=s, aspect=1.0))

    # the single-instance pool is refined on its own, never crowded out or
    # suppressed by extra peaks: on a busy screen a small template's coarse
    # scores are noisy, so a wrong-scale peak can outscore and overlap the
    # true match before refinement. Duplicates merge in the NMS after it.
    # The two pools mostly hold the same candidates: refine each one once
    # (refinement is deterministic, so dropping a duplicate changes nothing).
    pool = _nms(best, _BEST_K) + _nms(best + extra, top_k)
    kept = list({id(c): c for c in pool}.values())

    # --- refinement at full resolution -------------------------------------
    refined = [_refine(scene_grad_full, tpl_gray, mask, c, aspect_jitter)
               for c in kept]
    return _nms(refined)


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
