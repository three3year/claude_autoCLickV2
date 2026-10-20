"""Shared test helpers: build tiny synthetic game profiles on disk.

Tests exercise the engine only through its public API (load_templates +
query), so these helpers create real profile folders (templates/ +
config.yaml) in tmp_path, then play the caller's part: scan the folder into a
**template list** and hand it to the engine (`load_library`). The engine itself
never scans — `template_list` here is the test's stand-in for whatever the real
caller does (the app scans its workspace; bench uses per-case images).

(Lives outside conftest.py so the name stays unique: app/tests/ has its own
conftest.py, and `from conftest import ...` would resolve ambiguously.)
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import yaml

from subject_detection.imio import imwrite  # noqa: F401  (shared helper)
from subject_detection.library import load_config

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

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


def write_profile(root: Path, templates: dict[str, np.ndarray],
                  config: dict | None = None) -> Path:
    """Create a profile folder: one image per template (ADR 0016)."""
    profile = root / "profile"
    tdir = profile / "templates"
    tdir.mkdir(parents=True, exist_ok=True)
    for name, img in templates.items():
        imwrite(tdir / f"{name}.png", img)
    (profile / "config.yaml").write_text(
        yaml.safe_dump(config or {}), encoding="utf-8")
    return profile


def template_list(templates_dir: Path) -> dict[str, Path]:
    """Scan an image folder into a template list: {name: path}.

    Name = relative path without extension. This is the caller's job, not
    the engine's.
    """
    templates_dir = Path(templates_dir)
    found: dict[str, Path] = {}
    if templates_dir.is_dir():
        for child in sorted(templates_dir.rglob("*")):
            if child.is_file() and child.suffix.lower() in _IMAGE_EXTS:
                found[child.relative_to(templates_dir)
                      .with_suffix("").as_posix()] = child
    return found


def load_library(engine, profile_dir: Path):
    """Play the caller: hand the engine this profile's template list."""
    profile_dir = Path(profile_dir)
    return engine.load_templates(template_list(profile_dir / "templates"),
                                 config=load_config(profile_dir),
                                 artifacts_dir=profile_dir / "registered")
