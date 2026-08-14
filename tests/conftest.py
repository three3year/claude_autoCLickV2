"""Shared test helpers: build tiny synthetic game profiles on disk.

Tests exercise the engine only through its public API (load_profile + query),
so these helpers create real profile folders (templates/ + config.yaml) in
tmp_path and composite scenes to query against.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml

rng = np.random.default_rng(1234)


def make_template(w: int = 48, h: int = 36, seed: int = 0) -> np.ndarray:
    """A distinctive little UI-like crop: colored panel, border, glyph strokes."""
    r = np.random.default_rng(seed)
    img = np.full((h, w, 3), r.integers(30, 90, 3, dtype=np.uint8), dtype=np.uint8)
    cv2.rectangle(img, (1, 1), (w - 2, h - 2), tuple(int(c) for c in r.integers(150, 255, 3)), 2)
    for _ in range(4):
        p1 = (int(r.integers(4, w - 4)), int(r.integers(4, h - 4)))
        p2 = (int(r.integers(4, w - 4)), int(r.integers(4, h - 4)))
        cv2.line(img, p1, p2, tuple(int(c) for c in r.integers(120, 255, 3)), 2)
    cv2.circle(img, (w // 2, h // 2), min(w, h) // 4,
               tuple(int(c) for c in r.integers(120, 255, 3)), -1)
    return img


def make_scene(w: int = 640, h: int = 360, seed: int = 99) -> np.ndarray:
    """A busy background so false matches are plausible but wrong."""
    r = np.random.default_rng(seed)
    img = r.integers(0, 120, (h, w, 3), dtype=np.uint8)
    img = cv2.GaussianBlur(img, (0, 0), 3)
    for _ in range(12):
        p1 = (int(r.integers(0, w)), int(r.integers(0, h)))
        p2 = (int(r.integers(0, w)), int(r.integers(0, h)))
        cv2.rectangle(img, p1, p2, tuple(int(c) for c in r.integers(0, 200, 3)), -1)
    return img


def paste(scene: np.ndarray, patch: np.ndarray, x: int, y: int) -> np.ndarray:
    out = scene.copy()
    h, w = patch.shape[:2]
    out[y:y + h, x:x + w] = patch
    return out


def imwrite(path: Path, img: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(path.suffix, img)
    assert ok
    path.write_bytes(buf.tobytes())


def write_profile(root: Path, templates: dict[str, np.ndarray | dict[str, np.ndarray]],
                  config: dict | None = None) -> Path:
    """Create a profile folder.

    templates: name -> image (single capture) or name -> {capture_name: image}.
    """
    profile = root / "profile"
    tdir = profile / "templates"
    tdir.mkdir(parents=True, exist_ok=True)
    for name, val in templates.items():
        if isinstance(val, dict):
            for cap, img in val.items():
                imwrite(tdir / name / f"{cap}.png", img)
        else:
            imwrite(tdir / f"{name}.png", val)
    (profile / "config.yaml").write_text(
        yaml.safe_dump(config or {}), encoding="utf-8")
    return profile


@pytest.fixture(scope="session")
def engine():
    from subject_detection import Engine
    return Engine()
