"""Ticket 06 — verification stage: false positives die, recall survives.

Runs on CPU (no GPU dependency); the DINOv2-S model is loaded once by the
session-scoped engine fixture.
"""
from __future__ import annotations

import numpy as np

from synth import load_library, make_scene, make_template, paste, write_profile


def test_positive_still_found_with_verification(engine, tmp_path):
    tpl = make_template(seed=61)
    scene = paste(make_scene(seed=95), tpl, 240, 130)
    profile = load_library(engine, write_profile(tmp_path, {"btn": tpl}))
    res = engine.query(profile, "btn", scene)
    assert res.found is True
    assert "verify_score" in res.debug and "match_score" in res.debug


def test_coarse_false_positive_is_killed_by_verification(engine, tmp_path):
    # with a very loose coarse threshold the coarse stage alone WOULD accept
    # some background patch; verification must reject it
    tpl = make_template(seed=62)
    scene = make_scene(seed=96)  # subject truly absent
    profile = load_library(engine, write_profile(
        tmp_path, {"btn": tpl}, config={"match_threshold": 0.15}))
    res = engine.query(profile, "btn", scene)
    assert res.debug["match_score"] >= 0.15      # coarse stage did accept
    assert res.found is False                    # verification killed it
    assert res.debug["verify_score"] < 0.8


def test_verify_threshold_config_is_live(engine, tmp_path):
    tpl = make_template(seed=63)
    scene = paste(make_scene(seed=97), tpl, 100, 90)
    profile_dir = write_profile(tmp_path, {"btn": tpl},
                                config={"verify_threshold": 1.01})
    profile = load_library(engine, profile_dir)
    assert engine.query(profile, "btn", scene).found is False

    (profile_dir / "config.yaml").write_text("verify_threshold: 0.3",
                                             encoding="utf-8")
    profile = load_library(engine, profile_dir)
    assert engine.query(profile, "btn", scene).found is True


def test_query_is_deterministic(engine, tmp_path):
    tpl = make_template(seed=64)
    scene = paste(make_scene(seed=98), tpl, 300, 210)
    profile = load_library(engine, write_profile(tmp_path, {"btn": tpl}))
    r1 = engine.query(profile, "btn", scene)
    r2 = engine.query(profile, "btn", scene)
    assert r1.found == r2.found
    assert r1.box == r2.box
    assert abs(r1.score - r2.score) < 1e-6


def test_both_stage_scores_are_reported(engine, tmp_path):
    tpl = make_template(seed=65)
    scene = paste(make_scene(seed=99), tpl, 50, 60)
    profile = load_library(engine, write_profile(tmp_path, {"btn": tpl}))
    res = engine.query(profile, "btn", scene)
    assert 0.0 <= res.debug["match_score"] <= 1.0
    assert -1.0 <= res.debug["verify_score"] <= 1.0
    assert isinstance(res.debug["verify_scores"], list)
