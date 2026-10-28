from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from synth import load_library, make_scene, paste, write_profile

from subject_detection.bench import load_cases, run_case
from subject_detection.library import load_default_config

BENCH = Path(__file__).resolve().parent.parent / "benchmark"


def orange_button(w=64, h=40):
    img = np.full((h, w, 3), (20, 20, 20), np.uint8)
    cv2.rectangle(img, (2, 2), (w - 3, h - 3), (0, 140, 255), -1)
    cv2.rectangle(img, (2, 2), (w - 3, h - 3), (255, 255, 255), 2)
    cv2.putText(img, "GO", (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                (255, 255, 255), 2, cv2.LINE_AA)
    cv2.line(img, (46, 10), (56, 30), (40, 40, 200), 3)
    return img


def grey(img):
    return cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY),
                        cv2.COLOR_GRAY2BGR)


def _center(box):
    x, y, w, h = box
    return x + w // 2, y + h // 2


@pytest.fixture
def scene_and_lib(engine, tmp_path):
    btn = orange_button()
    scene = make_scene(w=800, h=360, seed=91)
    scene = paste(scene, grey(btn), 100, 150)
    scene = paste(scene, btn, 500, 150)
    lib = load_library(engine, write_profile(tmp_path, {"btn": btn}))
    return scene, lib


def test_不開比色時只差顏色的兩個都是匹配(engine, scene_and_lib):
    scene, lib = scene_and_lib
    res = engine.query(lib, "btn", scene)
    assert sorted(_center(m.box)[0] for m in res.matches) == [132, 532]


def test_開比色時顏色不符的不算匹配(engine, scene_and_lib):
    scene, lib = scene_and_lib
    res = engine.query(lib, "btn", scene, color_check=True)
    assert [_center(m.box) for m in res.matches] == [(532, 170)]
    assert res.matches[0].color >= 0.95
    assert [_center(m.box) for m in res.rejected] == [(132, 170)]
    assert res.rejected[0].color < 0.95


def test_比色只淘汰匹配_不改變其餘結果(engine, scene_and_lib):
    scene, lib = scene_and_lib
    plain = engine.query(lib, "btn", scene)
    checked = engine.query(lib, "btn", scene, color_check=True)
    kept = {m.box: m.score for m in checked.matches}
    assert all(plain_m.score == kept[plain_m.box]
               for plain_m in plain.matches if plain_m.box in kept)


def test_全部比色不符時沒有匹配_未過的關卡是比色(engine, tmp_path):
    btn = orange_button()
    scene = paste(make_scene(w=800, h=360, seed=92), grey(btn), 300, 100)
    lib = load_library(engine, write_profile(tmp_path, {"btn": btn}))
    res = engine.query(lib, "btn", scene, color_check=True)
    assert res.found is False and res.matches == []
    assert res.failed == "color"
    assert len(res.rejected) == 1


def test_比色門檻在引擎參數改了不必重新登錄(engine, tmp_path):
    btn = orange_button()
    scene = paste(make_scene(w=800, h=360, seed=93), grey(btn), 300, 100)
    profile = write_profile(tmp_path, {"btn": btn},
                            config={"color_threshold": 0.95})
    lib = load_library(engine, profile)
    assert engine.query(lib, "btn", scene, color_check=True).matches == []
    meta = Path(lib.artifacts_dir) / "btn" / "meta.json"
    stamp = meta.stat().st_mtime_ns

    lib.config["color_threshold"] = 0.0
    engine.register(lib, "btn")
    assert len(engine.query(lib, "btn", scene, color_check=True).matches) == 1
    lib2 = load_library(engine, write_profile(
        tmp_path, {"btn": btn}, config={"color_threshold": 0.5}))
    assert (Path(lib2.artifacts_dir) / "btn" / "meta.json").stat().st_mtime_ns \
        == stamp, "門檻不是登錄失效鍵"


def test_內建預設有比色門檻():
    assert load_default_config()["color_threshold"] == 0.95


REAL = ["color01_cn_全部收取_demo5f1096", "color03_cn_採購_固源岩_demo6f3532",
        "color04_cn_採購_聚酸酯_demo6f3532", "color05_cn_解锁线索_demo5f1200",
        "color06_cn_解锁线索_demo6f856", "color07_tw_全部收取_add2f80",
        "color09_tw_快速置入_demo2f968", "color10_tw_採購_初級作戰記錄_demo2f3020",
        "color11_tw_採購_招聘許可_demo2f3020", "color12_tw_解鎖線索_demo2f968"]


@pytest.mark.parametrize("name", REAL)
def test_真實影格_開比色後只剩真正的目標(engine, tmp_path, name):
    case = next(c for c in load_cases(BENCH) if c.name == name)
    assert case.expect.get("color_check") is True
    assert "known_failure" not in case.expect
    lib = engine.load_templates({case.name: case.template_path},
                                config=load_default_config(),
                                artifacts_dir=tmp_path / "registered")
    result = run_case(engine, lib, case)
    assert result.verdict == "correct", (name, result.debug.get("matches"),
                                         result.debug.get("color_scores"))
