"""Registration: turn a template's image into query-time artifacts.

Artifacts per template: a reference grayscale image plus a valid-pixel mask
from the gradient-stability heuristic on that one image — structure stays,
flat areas leave. A template is exactly one image (ADR 0016: the multi-capture
alignment and stability mask are gone).

Artifacts are persisted under <artifacts_dir>/<template_name>/ (the caller
picks the directory) together with the image's content hash and the
registration-relevant config subset, so loads reuse them and any relevant
change re-registers (see ticket 05).
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

_REG_VERSION = 3   # 3: one image per template, no mask strategy (ADR 0016)
# config keys that change registration artifacts (threshold-type keys do not)
_REG_CONFIG_KEYS = ("scale_range",)

_EDGE_PERCENTILE = 99.0
_EDGE_FLOOR = 0.12       # relative gradient below this = no structure


@dataclass
class Artifacts:
    ref_bgr: np.ndarray           # the template image, color uint8
    ref_gray: np.ndarray          # the template image, grayscale uint8
    mask: np.ndarray | None       # float32 [0,1], ref-sized; None = all valid
    embedding: np.ndarray | None = None   # subject embedding, L2-normalized


def _norm_grad(gray: np.ndarray) -> np.ndarray:
    g = cv2.GaussianBlur(gradient_map(gray), (0, 0), 1.2)
    scale = np.percentile(g, _EDGE_PERCENTILE)
    return g / (scale + 1e-6)


def _edge_mask(norm_grad: np.ndarray) -> np.ndarray:
    edge = np.clip(norm_grad / _EDGE_FLOOR, 0.0, 1.0)
    edge[edge < 0.5] = 0.0
    return edge


def _single_mask(ref_gray: np.ndarray) -> np.ndarray:
    mask = _edge_mask(_norm_grad(ref_gray))
    mask = cv2.dilate(mask, np.ones((3, 3), np.float32))
    return mask.astype(np.float32)


def compute_artifacts(image: np.ndarray) -> Artifacts:
    ref = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return Artifacts(ref_bgr=image, ref_gray=ref, mask=_single_mask(ref))


# --- persistence ------------------------------------------------------------

def _sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _reg_config(config: dict) -> dict:
    return {k: config[k] for k in _REG_CONFIG_KEYS if k in config}


def expected_meta(image_path: Path, config: dict) -> dict:
    return {
        "version": _REG_VERSION,
        "image": {image_path.name: _sha1(image_path)},
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


def load_or_register(artifacts_dir: Path, name: str,
                     image_path: Path, config: dict,
                     embed_fn=None) -> Artifacts:
    """embed_fn(Artifacts) -> np.ndarray computes the subject embedding when
    the engine has a verifier; the embedding is persisted next to the other
    artifacts and reloaded with them."""
    reg_dir = Path(artifacts_dir) / name
    meta = expected_meta(image_path, config)
    art = _load_artifacts(reg_dir, meta)
    rebuilt = art is None
    if rebuilt:
        art = compute_artifacts(imread(image_path))
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
