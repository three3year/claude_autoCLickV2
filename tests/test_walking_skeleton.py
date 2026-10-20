"""Ticket 01 — walking skeleton: public API round trip at fixed scale."""
from __future__ import annotations

import pytest

from synth import (imwrite, load_library, make_scene, make_template, paste,
                   write_profile)


def test_query_finds_subject_within_tolerance(engine, tmp_path):
    tpl = make_template(seed=1)
    scene = paste(make_scene(seed=50), tpl, 210, 120)
    profile_dir = write_profile(tmp_path, {"btn": tpl})

    profile = load_library(engine, profile_dir)
    res = engine.query(profile, "btn", scene)

    assert res.found is True
    x, y, w, h = res.box
    cx, cy = x + w / 2, y + h / 2
    assert abs(cx - (210 + tpl.shape[1] / 2)) <= 5
    assert abs(cy - (120 + tpl.shape[0] / 2)) <= 5
    assert 0.0 <= res.score <= 1.0


def test_query_absent_subject_reports_not_found(engine, tmp_path):
    tpl = make_template(seed=2)
    scene = make_scene(seed=51)  # subject never pasted
    profile_dir = write_profile(tmp_path, {"btn": tpl})

    profile = load_library(engine, profile_dir)
    res = engine.query(profile, "btn", scene)

    assert res.found is False


def test_match_threshold_from_config_is_effective(engine, tmp_path):
    tpl = make_template(seed=3)
    scene = paste(make_scene(seed=52), tpl, 100, 100)
    profile_dir = write_profile(tmp_path, {"btn": tpl},
                                config={"match_threshold": 1.01})

    profile = load_library(engine, profile_dir)
    res = engine.query(profile, "btn", scene)

    assert res.found is False  # impossible threshold => nothing passes


def test_engine_is_reusable_across_queries_and_profiles(engine, tmp_path):
    tpl_a = make_template(seed=4)
    tpl_b = make_template(seed=5)
    p1 = write_profile(tmp_path / "a", {"a": tpl_a})
    p2 = write_profile(tmp_path / "b", {"b": tpl_b})

    prof1 = load_library(engine, p1)
    prof2 = load_library(engine, p2)

    scene1 = paste(make_scene(seed=53), tpl_a, 30, 40)
    scene2 = paste(make_scene(seed=54), tpl_b, 300, 200)
    assert engine.query(prof1, "a", scene1).found
    assert engine.query(prof2, "b", scene2).found
    assert engine.query(prof1, "a", scene1).found  # repeatable


@pytest.mark.parametrize("n_paths", [1, 2])
def test_一個範本給清單_報錯_只收一張圖路徑(engine, tmp_path, n_paths):
    # ADR 0016: 多張圖登錄路徑退場; 給清單 (就算只有一個路徑) 也不收
    paths = [tmp_path / f"cap{i}.png" for i in range(n_paths)]
    for p in paths:
        imwrite(p, make_template(seed=6))

    with pytest.raises(ValueError, match="一張圖"):
        engine.load_templates({"multi": paths}, artifacts_dir=tmp_path / "reg")


def test_unknown_template_name_raises(engine, tmp_path):
    profile_dir = write_profile(tmp_path, {"btn": make_template(seed=7)})
    profile = load_library(engine, profile_dir)
    try:
        engine.query(profile, "nope", make_scene())
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for unknown template name")


def test_default_config_used_when_profile_config_is_minimal(engine, tmp_path):
    tpl = make_template(seed=8)
    scene = paste(make_scene(seed=56), tpl, 50, 50)
    profile_dir = write_profile(tmp_path, {"btn": tpl}, config={})

    profile = load_library(engine, profile_dir)
    res = engine.query(profile, "btn", scene)
    assert res.found is True
