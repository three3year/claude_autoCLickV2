from __future__ import annotations

from pathlib import Path

from synth import load_library, make_scene, make_template, paste, write_profile

from subject_detection.bench import load_cases
from subject_detection.imio import imread
from subject_detection.library import load_default_config

BENCH = Path(__file__).resolve().parent.parent / "benchmark"


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
    case = next(c for c in load_cases(BENCH) if c.name == name)
    return case.template_path, imread(case.screenshot_path), case.expect


def test_真實影格_小圖示不被別的尺度的雜訊峰擠出候選(engine, tmp_path):
    for name in ("pos02_cn_待办铃铛_demo5f416", "pos08_tw_生產面板箭頭_demo2f705",
                 "conf08_tw_標題列圖示_demo2f1152"):
        tpl, scene, expect = real_case(name)
        lib = engine.load_templates({"icon": tpl}, config=load_default_config(),
                                    artifacts_dir=tmp_path / "registered")
        res = engine.query(lib, "icon", scene)
        assert any(_near(m.box, expect["center"], 15) for m in res.matches), name


def test_真實影格_商店同款多格全部回報(engine, tmp_path):
    for name in ("multi01_cn_採購_聚酸酯_demo5f3300", "multi03_cn_採購_聚酸酯_demo5f3820",
                 "multi07_tw_採購_初級作戰記錄_demo2f2880"):
        tpl, scene, expect = real_case(name)
        lib = engine.load_templates({"card": tpl}, config=load_default_config(),
                                    artifacts_dir=tmp_path / "registered")
        res = engine.query(lib, "card", scene)
        for want in expect["centers"]:
            assert any(_near(m.box, want, 15) for m in res.matches), (name, want)


def test_真實影格_預期尺度1_開比色仍找到且框與全掃一致(engine, tmp_path):
    for name in ("color04_cn_採購_聚酸酯_demo6f3532", "color10_tw_採購_初級作戰記錄_demo2f3020",
                 "color01_cn_全部收取_demo5f1096"):
        tpl, scene, expect = real_case(name)
        th, tw = imread(tpl).shape[:2]
        lib = engine.load_templates({"row": tpl}, config=load_default_config(),
                                    artifacts_dir=tmp_path / "registered")
        full = engine.query(lib, "row", scene, color_check=True)
        near = engine.query(lib, "row", scene, color_check=True,
                            expected_scale=1.0)
        assert near.found and len(near.matches) == len(full.matches), name
        for a, b in zip(near.matches, full.matches):
            assert _near(a.box, _center(b.box), 2), name
            assert a.box[2:] == (tw, th), name
        for want in expect.get("centers") or [expect["center"]]:
            assert any(_near(m.box, want, 15) for m in near.matches), name
