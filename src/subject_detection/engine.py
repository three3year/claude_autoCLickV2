"""Public engine API: Engine.load_profile + Engine.query.

Query pipeline: gradient-domain multiscale coarse matching produces ranked
candidates; the best candidate above match_threshold is the answer (the
embedding verification stage is layered on top in a later ticket).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .imio import imread
from .matching import find_candidates
from .profile import Profile, load_profile_dir


@dataclass
class QueryResult:
    found: bool
    box: tuple[int, int, int, int] | None  # (x, y, w, h) in search-region coords
    score: float
    debug: dict = field(default_factory=dict)


class Engine:
    """Game-agnostic detection engine. Construct once; query many times."""

    def __init__(self) -> None:
        self._capture_cache: dict[Path, np.ndarray] = {}

    def load_profile(self, profile_dir: str | Path) -> Profile:
        return load_profile_dir(profile_dir)

    def query(self, profile: Profile, template_name: str,
              search_region: np.ndarray) -> QueryResult:
        if template_name not in profile.templates:
            raise KeyError(f"unknown template: {template_name!r}")
        template = profile.templates[template_name]
        tpl_img = self._load_capture(template.capture_paths[0])

        scene_gray = cv2.cvtColor(search_region, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.cvtColor(tpl_img, cv2.COLOR_BGR2GRAY)

        cfg = profile.config
        candidates = find_candidates(
            scene_gray, tpl_gray,
            scale_range=tuple(cfg["scale_range"]),
            aspect_jitter=float(cfg["aspect_jitter"]))
        debug = {
            "candidates": [{"box": c.box, "score": round(c.score, 4),
                            "scale": round(c.scale, 3),
                            "aspect": round(c.aspect, 3)}
                           for c in candidates],
        }
        if not candidates:
            debug["match_score"] = 0.0
            return QueryResult(found=False, box=None, score=0.0, debug=debug)

        best = candidates[0]
        score = best.score
        debug["match_score"] = round(score, 4)
        found = score >= float(cfg["match_threshold"])
        box = best.box if found else None
        return QueryResult(found=found, box=box, score=score, debug=debug)

    def _load_capture(self, path: Path) -> np.ndarray:
        if path not in self._capture_cache:
            self._capture_cache[path] = imread(path)
        return self._capture_cache[path]
