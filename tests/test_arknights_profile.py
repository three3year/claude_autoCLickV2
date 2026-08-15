"""Ticket 01 — the real arknights profile loads and answers queries."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from synth import make_scene, paste

from subject_detection.imio import imread

ARKNIGHTS = Path(__file__).resolve().parent.parent / "profiles" / "arknights"


def test_profile_loads_with_expected_templates(engine):
    profile = engine.load_profile(ARKNIGHTS)
    assert "cn/返回" in profile.templates
    assert "zh/返回" in profile.templates
    assert len(profile.templates) > 80
    # cn/返回 is a multi-capture template (cn + 翻新 sets)
    assert len(profile.templates["cn/返回"].capture_paths) == 2


def test_query_real_template_composited_scene(engine):
    profile = engine.load_profile(ARKNIGHTS)
    tpl_img = imread(ARKNIGHTS / "templates" / "cn" / "返回" / "cn.png")
    scene = paste(make_scene(w=800, h=450, seed=7), tpl_img, 500, 60)

    res = engine.query(profile, "cn/返回", scene)

    assert res.found is True
    x, y, w, h = res.box
    assert abs((x + w / 2) - (500 + tpl_img.shape[1] / 2)) <= 5
    assert abs((y + h / 2) - (60 + tpl_img.shape[0] / 2)) <= 5


def test_query_real_template_absent(engine):
    profile = engine.load_profile(ARKNIGHTS)
    scene = make_scene(w=800, h=450, seed=8)
    res = engine.query(profile, "cn/返回", scene)
    assert res.found is False
