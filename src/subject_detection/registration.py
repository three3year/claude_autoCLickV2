"""Registration: turn a template's captures into query-time artifacts.

Artifacts per template: a reference grayscale image plus a valid-pixel mask
that keeps the subject's stable structure and drops translucent bleed and
mutable regions. Strategies (config `mask_strategy`):

- multi_capture: captures of the same element (different sets / game states)
  are aligned onto the largest one; pixels whose gradient energy disagrees
  across captures are unstable (bleed, counters) and leave the mask.
- single: gradient-stability heuristic on one capture — structure stays,
  flat areas leave. multi_capture with one capture degrades to this.

Artifacts are persisted under <profile>/registered/<template_name>/ together
with capture content hashes and the registration-relevant config subset, so
loads reuse them and any relevant change re-registers (see ticket 05).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .imio import imread, imwrite
from .matching import gradient_map

_REG_VERSION = 2
# config keys that change registration artifacts (threshold-type keys do not)
_REG_CONFIG_KEYS = ("mask_strategy", "scale_range")

_EDGE_PERCENTILE = 99.0
_EDGE_FLOOR = 0.12       # relative gradient below this = no structure
_STABILITY_CUT = 0.55    # relative disagreement above (1 - cut) = unstable
_MIN_COVERAGE = 0.12     # mask below this fraction falls back to edge-only


@dataclass
class Artifacts:
    ref_bgr: np.ndarray           # reference capture, color uint8
    ref_gray: np.ndarray          # reference capture, grayscale uint8
    mask: np.ndarray | None       # float32 [0,1], ref-sized; None = all valid
    embedding: np.ndarray | None = None   # subject embedding, L2-normalized


def _norm_grad(gray: np.ndarray) -> np.ndarray:
    g = cv2.GaussianBlur(gradient_map(gray), (0, 0), 1.2)
    scale = np.percentile(g, _EDGE_PERCENTILE)
    return g / (scale + 1e-6)


def _align_to_ref(ref_gray: np.ndarray, cap_gray: np.ndarray) -> np.ndarray | None:
    """Resize a capture to the reference frame, correcting small translation
    offsets (hand-cropped captures differ in framing). Returns a ref-sized
    grayscale image, or None when alignment is hopeless."""
    rh, rw = ref_gray.shape
    resized = cv2.resize(cap_gray, (rw, rh), interpolation=cv2.INTER_AREA
                         if cap_gray.shape[0] > rh else cv2.INTER_LINEAR)
    # search the central crop of the capture inside the reference
    mx, my = max(2, rw // 8), max(2, rh // 8)
    core = resized[my:rh - my, mx:rw - mx]
    if core.shape[0] < 4 or core.shape[1] < 4:
        return resized
    res = cv2.matchTemplate(gradient_map(ref_gray), gradient_map(core),
                            cv2.TM_CCOEFF_NORMED)
    res = np.nan_to_num(res, nan=-1.0)
    _, val, _, loc = cv2.minMaxLoc(res)
    dx, dy = loc[0] - mx, loc[1] - my
    if abs(dx) > rw // 4 or abs(dy) > rh // 4:
        return resized  # implausible shift; trust plain resize
    m = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(resized, m, (rw, rh), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)


def _edge_mask(norm_grad: np.ndarray) -> np.ndarray:
    edge = np.clip(norm_grad / _EDGE_FLOOR, 0.0, 1.0)
    edge[edge < 0.5] = 0.0
    return edge


def _single_mask(ref_gray: np.ndarray) -> np.ndarray:
    mask = _edge_mask(_norm_grad(ref_gray))
    mask = cv2.dilate(mask, np.ones((3, 3), np.float32))
    return mask.astype(np.float32)


def _multi_mask(ref_gray: np.ndarray, others: list[np.ndarray]) -> np.ndarray:
    grads = [_norm_grad(ref_gray)] + [_norm_grad(o) for o in others]
    stack = np.stack(grads)
    g_max = stack.max(axis=0)
    g_min = stack.min(axis=0)
    disagreement = (g_max - g_min) / (g_max + g_min + 1e-6)   # 0 stable, 1 unstable
    stable = (disagreement < _STABILITY_CUT).astype(np.float32)
    edge = _edge_mask(np.median(stack, axis=0))
    mask = edge * stable
    mask = cv2.dilate(mask, np.ones((3, 3), np.float32))
    if mask.mean() < _MIN_COVERAGE:
        # captures disagree everywhere (bad alignment?) — safer to keep all edges
        return _single_mask(ref_gray)
    return mask.astype(np.float32)


def compute_artifacts(captures: list[np.ndarray], strategy: str) -> Artifacts:
    ref_bgr = max(captures, key=lambda c: c.shape[0] * c.shape[1])
    ref = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
    grays = [cv2.cvtColor(c, cv2.COLOR_BGR2GRAY)
             for c in captures if c is not ref_bgr]
    if strategy == "multi_capture" and len(captures) > 1:
        others = [_align_to_ref(ref, g) for g in grays]
        mask = _multi_mask(ref, [o for o in others if o is not None])
    elif strategy in ("multi_capture", "single"):
        mask = _single_mask(ref)
    else:
        raise ValueError(f"unknown mask_strategy: {strategy!r}")
    return Artifacts(ref_bgr=ref_bgr, ref_gray=ref, mask=mask)


# --- persistence ------------------------------------------------------------

def _sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _reg_config(config: dict) -> dict:
    return {k: config[k] for k in _REG_CONFIG_KEYS if k in config}


def expected_meta(capture_paths: list[Path], config: dict) -> dict:
    return {
        "version": _REG_VERSION,
        "captures": {p.name: _sha1(p) for p in capture_paths},
        "config": _reg_config(config),
    }


def _load_artifacts(reg_dir: Path, meta: dict) -> Artifacts | None:
    try:
        stored = json.loads((reg_dir / "meta.json").read_text(encoding="utf-8"))
        if stored != meta:
            return None
        ref_bgr = imread(reg_dir / "ref.png", cv2.IMREAD_COLOR)
        ref = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
        mask = imread(reg_dir / "mask.png", cv2.IMREAD_GRAYSCALE)
        if mask.shape != ref.shape:
            return None
        return Artifacts(ref_bgr=ref_bgr, ref_gray=ref,
                         mask=mask.astype(np.float32) / 255.0)
    except Exception:
        return None  # missing/corrupt artifacts are rebuilt, never fatal


def _store_artifacts(reg_dir: Path, art: Artifacts, meta: dict) -> None:
    reg_dir.mkdir(parents=True, exist_ok=True)
    imwrite(reg_dir / "ref.png", art.ref_bgr)
    mask = art.mask if art.mask is not None \
        else np.ones_like(art.ref_gray, dtype=np.float32)
    imwrite(reg_dir / "mask.png", (np.clip(mask, 0, 1) * 255).astype(np.uint8))
    (reg_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def load_or_register(profile_root: Path, name: str,
                     capture_paths: list[Path], config: dict,
                     embed_fn=None) -> Artifacts:
    """embed_fn(Artifacts) -> np.ndarray computes the subject embedding when
    the engine has a verifier; the embedding is persisted next to the other
    artifacts and reloaded with them."""
    reg_dir = profile_root / "registered" / name
    meta = expected_meta(capture_paths, config)
    art = _load_artifacts(reg_dir, meta)
    rebuilt = art is None
    if rebuilt:
        art = compute_artifacts([imread(p) for p in capture_paths],
                                str(config.get("mask_strategy", "multi_capture")))
        _store_artifacts(reg_dir, art, meta)
    emb_path = reg_dir / "embedding.npy"
    if not rebuilt and emb_path.is_file():
        try:
            art.embedding = np.load(emb_path)
        except Exception:
            art.embedding = None
    if art.embedding is None and embed_fn is not None:
        art.embedding = embed_fn(art)
        np.save(emb_path, art.embedding)
    return art
