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

from .matching import find_candidates
from .profile import Profile, load_profile_dir
from .registration import load_or_register


@dataclass
class QueryResult:
    found: bool
    box: tuple[int, int, int, int] | None  # (x, y, w, h) in search-region coords
    score: float
    debug: dict = field(default_factory=dict)


class Engine:
    """Game-agnostic detection engine. Construct once; query many times."""

    def __init__(self) -> None:
        pass

    def load_profile(self, profile_dir: str | Path) -> Profile:
        profile = load_profile_dir(profile_dir)
        for t in profile.templates.values():
            t.artifacts = load_or_register(profile.root, t.name,
                                           t.capture_paths, profile.config)
        return profile

    def query(self, profile: Profile, template_name: str,
              search_region: np.ndarray) -> QueryResult:
        if template_name not in profile.templates:
            raise KeyError(f"unknown template: {template_name!r}")
        template = profile.templates[template_name]
        art = template.artifacts

        scene_gray = cv2.cvtColor(search_region, cv2.COLOR_BGR2GRAY)
        tpl_gray = art.ref_gray

        cfg = profile.config
        candidates = find_candidates(
            scene_gray, tpl_gray,
            scale_range=tuple(cfg["scale_range"]),
            aspect_jitter=float(cfg["aspect_jitter"]),
            mask=art.mask)
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
