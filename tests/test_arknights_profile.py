"""Ticket 01 — real arknights captures load and answer queries.

The captures live under `benchmark/_assets/templates/` (the benchmark owns its
own inputs; there is no template library any more — ADR 0006). The template
list handed to the engine is built here, the way any caller would.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from synth import make_scene, paste, template_list

from subject_detection.imio import imread
from subject_detection.library import load_config

ARKNIGHTS = Path(__file__).resolve().parent.parent / "profiles" / "arknights"
CAPTURES = ARKNIGHTS / "benchmark" / "_assets" / "templates"


def _library(engine):
    return engine.load_templates(
        template_list(CAPTURES), config=load_config(ARKNIGHTS),
        artifacts_dir=ARKNIGHTS / "benchmark" / "_assets" / "_registered")


def test_real_captures_load_as_a_template_list(engine):
    library = _library(engine)
    assert "cn/返回" in library.templates
    assert "zh/返回" in library.templates
    assert len(library.templates) > 80
    # cn/返回 still has both capture sets on disk (cn + 翻新)
    assert len(library.templates["cn/返回"].capture_paths) == 2


def test_query_real_template_composited_scene(engine):
    library = _library(engine)
    tpl_img = imread(CAPTURES / "cn" / "返回" / "cn.png")
    scene = paste(make_scene(w=800, h=450, seed=7), tpl_img, 500, 60)

    res = engine.query(library, "cn/返回", scene)

    assert res.found is True
    x, y, w, h = res.box
    assert abs((x + w / 2) - (500 + tpl_img.shape[1] / 2)) <= 5
    assert abs((y + h / 2) - (60 + tpl_img.shape[0] / 2)) <= 5


def test_query_real_template_absent(engine):
    library = _library(engine)
    scene = make_scene(w=800, h=450, seed=8)
    res = engine.query(library, "cn/返回", scene)
    assert res.found is False
