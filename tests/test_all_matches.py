"""find-target 票 02 — 一次查詢回報所有匹配 (公開 API: Engine.query).

查詢的結果是主體在搜尋區域中的**所有**匹配 (零到多個), 每個帶邊界框與分數;
多個匹配時取哪一個是呼叫端的事 (ADR 0007)。`found/box/score` 保留為「分數
最高的那個匹配」, 既有呼叫端不必改。
"""
from __future__ import annotations

from pathlib import Path

from synth import load_library, make_scene, make_template, paste, write_profile

from subject_detection.bench import load_cases
from subject_detection.imio import imread
from subject_detection.library import load_config

ARKNIGHTS = Path(__file__).resolve().parent.parent / "profiles" / "arknights"


def _center(box):
    x, y, w, h = box
    return x + w / 2, y + h / 2


def _near(box, xy, tol=6):
    cx, cy = _center(box)
    return abs(cx - xy[0]) <= tol and abs(cy - xy[1]) <= tol


def test_同一尺度上的一排同款全部回報(engine, tmp_path):
    tpl = make_template(w=48, h=36, seed=31)
    scene = make_scene(w=800, h=360, seed=81)
    xs = [40, 190, 340, 490, 640]
    for x in xs:
        scene = paste(scene, tpl, x, 150)
    lib = load_library(engine, write_profile(tmp_path, {"card": tpl}))

    res = engine.query(lib, "card", scene)

    assert len(res.matches) == len(xs)
    for x in xs:
        assert any(_near(m.box, (x + 24, 150 + 18)) for m in res.matches), x


def test_單一實例恰好一個匹配_且就是found的那個(engine, tmp_path):
    tpl = make_template(w=56, h=40, seed=32)
    scene = paste(make_scene(seed=82), tpl, 300, 120)
    lib = load_library(engine, write_profile(tmp_path, {"btn": tpl}))

    res = engine.query(lib, "btn", scene)

    assert len(res.matches) == 1
    m = res.matches[0]
    assert res.found and m.box == res.box and m.score == res.score
    assert _near(m.box, (300 + 28, 120 + 20))
    assert m.color is None, "沒要求比色就沒有比色分數"


def test_多個匹配時found是分數最高的那個(engine, tmp_path):
    tpl = make_template(w=48, h=36, seed=33)
    scene = make_scene(w=800, h=360, seed=83)
    scene = paste(scene, tpl, 100, 100)
    scene = paste(scene, tpl, 500, 200)
    lib = load_library(engine, write_profile(tmp_path, {"btn": tpl}))

    res = engine.query(lib, "btn", scene)

    assert len(res.matches) == 2
    best = max(res.matches, key=lambda m: m.score)
    assert res.box == best.box and res.score == best.score


def test_沒有匹配時有最高分與未過的關卡(engine, tmp_path):
    tpl = make_template(w=48, h=36, seed=34)
    lib = load_library(engine, write_profile(tmp_path, {"btn": tpl}))

    res = engine.query(lib, "btn", make_scene(seed=84))

    assert res.found is False and res.matches == []
    assert res.failed in ("match", "verify")
    assert 0.0 <= res.score < 1.0


def test_有匹配時沒有未過的關卡(engine, tmp_path):
    tpl = make_template(w=48, h=36, seed=35)
    scene = paste(make_scene(seed=85), tpl, 80, 60)
    lib = load_library(engine, write_profile(tmp_path, {"btn": tpl}))
    assert engine.query(lib, "btn", scene).failed is None


def real_case(name):
    """基準測試集裡的真實影格 case: (模板圖, 截圖, expect)."""
    case = next(c for c in load_cases(ARKNIGHTS) if c.name == name)
    return case.template_path, imread(case.screenshot_path), case.expect


def test_真實影格_基建總覽上四張製造站卡全部回報(engine, tmp_path):
    """同款四張全部是匹配 (不開比色時同形狀的貿易站卡也會進來——那是比色的事)."""
    for name in ("r0_multi_製造站卡_d3f300", "r1_multi_製造站卡_d2f662",
                 "r2_multi_製造站卡_d2f683"):
        tpl, scene, expect = real_case(name)
        lib = engine.load_templates({"card": tpl}, config=load_config(ARKNIGHTS),
                                    artifacts_dir=tmp_path / "registered")
        res = engine.query(lib, "card", scene)
        for want in expect["centers"]:
            assert any(_near(m.box, want, 15) for m in res.matches), (name, want)
