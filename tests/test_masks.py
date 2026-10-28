from __future__ import annotations

import cv2
import numpy as np
import pytest

from synth import imwrite, load_library, make_scene, paste, write_profile

from subject_detection.library import load_default_config


def glyph_card(glyph: str) -> np.ndarray:
    img = np.full((80, 60, 3), 70, dtype=np.uint8)
    cv2.rectangle(img, (2, 2), (57, 77), (220, 220, 220), 1)
    cv2.putText(img, glyph, (8, 60), cv2.FONT_HERSHEY_SIMPLEX, 2.2,
                (245, 245, 245), 5, cv2.LINE_AA)
    return img


def test_similar_templates_are_not_confused(engine, tmp_path):
    scene_with_b = paste(make_scene(seed=82), glyph_card("B"), 200, 100)

    profile_dir = write_profile(tmp_path, {"cardA": glyph_card("A")})
    profile = load_library(engine, profile_dir)
    res = engine.query(profile, "cardA", scene_with_b)

    assert res.found is False


def test_single_image_template_registers_and_queries(engine, tmp_path):
    card = glyph_card("Z")
    scene = paste(make_scene(seed=83), card, 150, 90)
    profile_dir = write_profile(tmp_path, {"cardZ": card})
    profile = load_library(engine, profile_dir)
    res = engine.query(profile, "cardZ", scene)
    assert res.found is True


def test_registration_artifacts_persisted_and_reused(engine, tmp_path):
    profile_dir = write_profile(tmp_path, {"cardP": glyph_card("P")})

    load_library(engine, profile_dir)
    reg = profile_dir / "registered" / "cardP"
    assert (reg / "meta.json").is_file()
    artifact_files = sorted(p.name for p in reg.iterdir())
    mtimes = {p.name: p.stat().st_mtime_ns for p in reg.iterdir()}

    load_library(engine, profile_dir)
    assert sorted(p.name for p in reg.iterdir()) == artifact_files
    assert {p.name: p.stat().st_mtime_ns for p in reg.iterdir()} == mtimes


def test_內建預設沒有遮罩策略鍵():
    assert "mask_strategy" not in load_default_config()


@pytest.mark.parametrize("strategy", ["single", "multi_capture"])
def test_引擎參數帶遮罩策略鍵_報錯(engine, tmp_path, strategy):
    path = tmp_path / "cardZ.png"
    imwrite(path, glyph_card("Z"))
    config = {**load_default_config(), "mask_strategy": strategy}

    with pytest.raises(ValueError, match="mask_strategy"):
        engine.load_templates({"cardZ": path}, config=config,
                              artifacts_dir=tmp_path / "reg")
