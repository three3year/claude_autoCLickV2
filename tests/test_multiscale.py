"""Ticket 03 — gradient-domain multiscale coarse matching (public API only)."""
from __future__ import annotations

import time

import cv2
import numpy as np

from conftest import make_scene, make_template, paste, write_profile


def _scaled_paste(scene, tpl, x, y, scale, fx_extra=1.0):
    patch = cv2.resize(tpl, None, fx=scale * fx_extra, fy=scale,
                       interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    return paste(scene, patch, x, y), patch.shape[1], patch.shape[0]


def _assert_hit(res, x, y, w, h, tol=8):
    assert res.found is True
    bx, by, bw, bh = res.box
    assert abs((bx + bw / 2) - (x + w / 2)) <= tol
    assert abs((by + bh / 2) - (y + h / 2)) <= tol


def test_finds_subject_at_smaller_scale(engine, tmp_path):
    tpl = make_template(w=64, h=48, seed=21)
    scene, w, h = _scaled_paste(make_scene(seed=70), tpl, 220, 130, 0.7)
    profile = engine.load_profile(write_profile(tmp_path, {"btn": tpl}))
    res = engine.query(profile, "btn", scene)
    _assert_hit(res, 220, 130, w, h)


def test_finds_subject_at_larger_scale(engine, tmp_path):
    tpl = make_template(w=64, h=48, seed=22)
    scene, w, h = _scaled_paste(make_scene(seed=71), tpl, 150, 90, 1.3)
    profile = engine.load_profile(write_profile(tmp_path, {"btn": tpl}))
    res = engine.query(profile, "btn", scene)
    _assert_hit(res, 150, 90, w, h)


def test_robust_to_brightness_drop(engine, tmp_path):
    tpl = make_template(w=64, h=48, seed=23)
    scene, w, h = _scaled_paste(make_scene(seed=72), tpl, 300, 200, 0.85)
    dark = (scene.astype(np.float32) * 0.5).astype(np.uint8)
    profile = engine.load_profile(write_profile(tmp_path, {"btn": tpl}))
    res = engine.query(profile, "btn", dark)
    _assert_hit(res, 300, 200, w, h)


def test_robust_to_color_tint(engine, tmp_path):
    tpl = make_template(w=64, h=48, seed=24)
    scene, w, h = _scaled_paste(make_scene(seed=73), tpl, 100, 60, 1.1)
    tinted = scene.astype(np.float32)
    tinted[..., 0] = np.clip(tinted[..., 0] * 1.3 + 15, 0, 255)
    tinted[..., 2] = np.clip(tinted[..., 2] * 0.75, 0, 255)
    tinted = tinted.astype(np.uint8)
    profile = engine.load_profile(write_profile(tmp_path, {"btn": tpl}))
    res = engine.query(profile, "btn", tinted)
    _assert_hit(res, 100, 60, w, h)


def test_scale_range_config_limits_sweep(engine, tmp_path):
    tpl = make_template(w=64, h=48, seed=25)
    scene, _, _ = _scaled_paste(make_scene(seed=74), tpl, 220, 130, 0.65)
    profile = engine.load_profile(write_profile(
        tmp_path, {"btn": tpl}, config={"scale_range": [0.95, 1.05]}))
    res = engine.query(profile, "btn", scene)
    assert res.found is False  # 0.65x sits far outside the configured sweep


def test_aspect_jitter_tolerates_mild_distortion(engine, tmp_path):
    tpl = make_template(w=64, h=48, seed=26)
    scene, w, h = _scaled_paste(make_scene(seed=75), tpl, 180, 110, 1.0,
                                fx_extra=1.08)
    profile = engine.load_profile(write_profile(tmp_path, {"btn": tpl}))
    res = engine.query(profile, "btn", scene)
    _assert_hit(res, 180, 110, w, h)


def test_debug_exposes_coarse_candidates(engine, tmp_path):
    tpl = make_template(w=64, h=48, seed=27)
    scene, _, _ = _scaled_paste(make_scene(seed=76), tpl, 220, 130, 0.8)
    profile = engine.load_profile(write_profile(tmp_path, {"btn": tpl}))
    res = engine.query(profile, "btn", scene)
    assert "match_score" in res.debug
    assert isinstance(res.debug.get("candidates"), list)
    assert len(res.debug["candidates"]) >= 1
    top = res.debug["candidates"][0]
    assert "score" in top and "box" in top and "scale" in top


def test_near_fullscreen_coarse_stays_fast(engine, tmp_path):
    tpl = make_template(w=48, h=36, seed=28)
    scene, w, h = _scaled_paste(make_scene(w=1280, h=720, seed=77), tpl,
                                900, 500, 0.9)
    profile = engine.load_profile(write_profile(tmp_path, {"btn": tpl}))
    engine.query(profile, "btn", scene)  # warm caches
    t0 = time.perf_counter()
    res = engine.query(profile, "btn", scene)
    elapsed = (time.perf_counter() - t0) * 1000
    _assert_hit(res, 900, 500, w, h)
    assert elapsed < 500, f"coarse query took {elapsed:.0f}ms"
