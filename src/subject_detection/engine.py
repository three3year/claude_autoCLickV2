"""Public engine API: Engine.load_templates + Engine.query.

The caller delivers a **template list** (name → image path) together with the
config and the artifacts directory; the engine never scans a directory and
holds no assumptions about the caller's storage layout (see `library.py`).

Query pipeline: gradient-domain multiscale coarse matching produces ranked
candidates; the best candidate above match_threshold is the answer, then the
embedding verification stage decides.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import cv2
import numpy as np

from .library import Library, make_library
from .matching import find_candidates
from .registration import Artifacts, load_or_register


@dataclass
class QueryResult:
    found: bool
    box: tuple[int, int, int, int] | None  # (x, y, w, h) in search-region coords
    score: float
    debug: dict = field(default_factory=dict)


class Engine:
    """Game-agnostic detection engine. Construct once (the verification
    model loads here and stays resident); query many times."""

    def __init__(self) -> None:
        try:
            from .verification import Verifier
            self._verifier = Verifier()
        except Exception as exc:  # no torch / no weights: coarse-only mode
            warnings.warn(f"verification unavailable, running coarse-only: {exc}")
            self._verifier = None

    @property
    def coarse_only(self) -> bool:
        """True when the verification model failed to load (a warning was
        emitted at construction): queries run the coarse stage only."""
        return self._verifier is None

    def _embed_template(self, art: Artifacts) -> np.ndarray:
        from .verification import masked_fill
        return self._verifier.embed([masked_fill(art.ref_bgr, art.mask)])[0]

    def load_templates(self, templates, config=None,
                       artifacts_dir=None) -> Library:
        """收`範本清單` (範本名 → 圖檔路徑) 並登錄全部, 回傳可查詢的模板庫.

        templates: {name: path} 或 {name: [path, ...]} (多路徑＝一個多截圖範本);
        artifacts_dir: 登錄產物的存放位置, 由呼叫端指定。
        """
        library = make_library(templates, config, artifacts_dir)
        for name in library.templates:
            self.register(library, name)
        return library

    def register(self, library: Library, name: str) -> None:
        """單一範本的登錄產物載入/重建; 已載入 (artifacts 在) 的直接沿用."""
        t = library.templates[name]
        if t.artifacts is None:
            embed_fn = (self._embed_template
                        if self._verifier is not None else None)
            t.artifacts = load_or_register(library.artifacts_dir, t.name,
                                           t.capture_paths, library.config,
                                           embed_fn=embed_fn)

    def query(self, library: Library, template_name: str,
              search_region: np.ndarray) -> QueryResult:
        if template_name not in library.templates:
            raise KeyError(f"unknown template: {template_name!r}")
        template = library.templates[template_name]
        art = template.artifacts

        scene_gray = cv2.cvtColor(search_region, cv2.COLOR_BGR2GRAY)
        tpl_gray = art.ref_gray

        cfg = library.config
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

        debug["match_score"] = round(candidates[0].score, 4)
        passing = [c for c in candidates
                   if c.score >= float(cfg["match_threshold"])]
        if not passing:
            return QueryResult(found=False, box=None,
                               score=candidates[0].score, debug=debug)

        if self._verifier is None or art.embedding is None:
            best = passing[0]
            return QueryResult(found=True, box=best.box, score=best.score,
                               debug=debug)

        # verification: embed every passing candidate crop (masked) in one
        # batch and compare with the registered subject embedding
        from .verification import masked_fill
        sh, sw = scene_gray.shape
        crops = []
        for c in passing:
            x, y, w, h = c.box
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(sw, x + w), min(sh, y + h)
            mask = art.mask
            if mask is not None and (x0, y0, x1, y1) != (x, y, x + w, y + h):
                # candidate is clipped by the scene edge: crop the mask to
                # the visible fraction so it stays aligned with the crop
                mh, mw = mask.shape
                mask = mask[round((y0 - y) / h * mh):round((y1 - y) / h * mh),
                            round((x0 - x) / w * mw):round((x1 - x) / w * mw)]
            crops.append(masked_fill(search_region[y0:y1, x0:x1], mask))
        embs = self._verifier.embed(crops)
        sims = embs @ art.embedding
        order = int(np.argmax(sims))
        best, verify_score = passing[order], float(sims[order])
        debug["verify_scores"] = [round(float(s), 4) for s in sims]
        debug["verify_score"] = round(verify_score, 4)
        found = verify_score >= float(cfg["verify_threshold"])
        return QueryResult(found=found, box=best.box if found else None,
                           score=verify_score, debug=debug)
