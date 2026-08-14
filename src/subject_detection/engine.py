"""Public engine API: Engine.load_profile + Engine.query.

Walking-skeleton matcher: fixed-scale grayscale template matching. The
two-stage pipeline (gradient multiscale coarse pass + embedding verification)
replaces the internals ticket by ticket; this module's surface stays put.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .imio import imread
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
        th, tw = tpl_gray.shape
        sh, sw = scene_gray.shape
        if th > sh or tw > sw:
            return QueryResult(found=False, box=None, score=0.0)

        res = cv2.matchTemplate(scene_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        score = float(max_val)
        found = score >= float(profile.config["match_threshold"])
        box = (max_loc[0], max_loc[1], tw, th) if found else None
        return QueryResult(found=found, box=box, score=score,
                           debug={"match_score": score})

    def _load_capture(self, path: Path) -> np.ndarray:
        if path not in self._capture_cache:
            self._capture_cache[path] = imread(path)
        return self._capture_cache[path]
