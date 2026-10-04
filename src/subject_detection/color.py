"""Color check: an optional extra gate a caller may request per query.

The gradient domain ignores color on purpose (ADR 0001), so subjects that
share a shape and differ only in color — an orange button and its greyed-out
disabled state — both pass coarse matching and verification. When asked, each
verified candidate is compared once more **in color**: the whole template (no
registration mask — color differences mostly live on the flat areas a mask
drops) at the candidate's own scale (a few sizes around its refined box),
searched a few pixels around it with TM_CCOEFF_NORMED. The candidate's own scale is used, not any
caller-side calibration (ADR 0007).
"""
from __future__ import annotations

import cv2
import numpy as np

_MARGIN = 4   # px searched around the refined box (refinement jitter)
# the refinement's scale grid is coarse (~4% steps): compare at a few sizes
# around the candidate's own scale so quantization alone cannot sink a true
# match (an exact copy scores 0.92 at a 1px-off size, 1.00 at the right one)
_SIZE_STEPS = (0.96, 0.98, 1.0, 1.02, 1.04)


def color_score(scene_bgr: np.ndarray, tpl_bgr: np.ndarray,
                box: tuple[int, int, int, int]) -> float:
    """Best color TM_CCOEFF_NORMED of the whole template around `box`."""
    x, y, w, h = box
    th, tw = tpl_bgr.shape[:2]
    k = h / th
    sizes = {(w, h)} | {(round(tw * k * f), round(th * k * f))
                        for f in _SIZE_STEPS}
    cx, cy = x + w / 2, y + h / 2
    sh, sw = scene_bgr.shape[:2]
    best = 0.0
    for sw_, sh_ in sorted(sizes):
        if sw_ < 4 or sh_ < 4:
            continue
        interp = cv2.INTER_AREA if sw_ < tw else cv2.INTER_LINEAR
        tpl = cv2.resize(tpl_bgr, (sw_, sh_), interpolation=interp)
        wx0 = int(cx - sw_ / 2 - _MARGIN)
        wy0 = int(cy - sh_ / 2 - _MARGIN)
        wx1 = int(cx + sw_ / 2 + _MARGIN + 1)
        wy1 = int(cy + sh_ / 2 + _MARGIN + 1)
        x0, y0, x1, y1 = max(0, wx0), max(0, wy0), min(sw, wx1), min(sh, wy1)
        if x1 <= x0 or y1 <= y0:
            continue
        window = scene_bgr[y0:y1, x0:x1].astype(np.float32)
        # a box clipped by the scene edge: pad the missing side(s) so the
        # window stays aligned with where the template should sit
        top, left = y0 - wy0, x0 - wx0
        bottom, right = wy1 - y1, wx1 - x1
        if top or left or bottom or right:
            window = cv2.copyMakeBorder(window, top, bottom, left, right,
                                        cv2.BORDER_REPLICATE)
        res = cv2.matchTemplate(window, tpl.astype(np.float32),
                                cv2.TM_CCOEFF_NORMED)
        res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
        best = max(best, float(res.max()))
    return float(min(best, 1.0))
