"""影片與實際畫面同尺度 (1:1) 與`畫面倍率`換回基準尺度.

示範影片是在執行流程的這台機器上、以實際畫面尺度錄的: 影片像素就是螢幕
像素, 偏移不依搜尋範圍大小換算 (搜尋範圍只決定流程在哪裡找圖)。profile
已校準且畫面倍率≠1 時, 座標再換回基準尺度 (ADR 0005)。

只打組裝入口; 斷言存檔裡的偏移、範本圖尺寸、報告文字與 profile 檔案狀態。
"""
import json

import cv2
import numpy as np
import pytest

import flowfile
import video_to_flow
from vtf_synth import (VIDEO_H, VIDEO_W, box, center, demo_plan, demo_video,
                       find, make_profile)

FP = {"x": 0, "y": 0, "w": 1920, "h": 1080}
OTHER_FP = {"x": 0, "y": 0, "w": 2560, "h": 1440}


def region(w, h, x=0, y=0):
    return [x, y, w, h]


def off(name, dx, dy):
    """點在按鈕中心旁 (dx, dy) 的找圖點擊."""
    cx, cy = center(name)
    return find(name, at=[cx + dx, cy + dy])


def assemble(tmp_path, engine, reg, steps=None, config=None, cal=None):
    video = demo_video(tmp_path)
    profile = make_profile(tmp_path, region=reg, config=config)
    if cal is not None:
        with open(profile / "calibration.json", "w", encoding="utf-8") as f:
            json.dump(cal, f)
    plan = demo_plan(video, profile, steps=steps)
    return video_to_flow.assemble(plan, engine=engine, fingerprint=FP), profile


def saved_steps(res):
    return flowfile.read(res["flow_path"])["data"]["steps"]


@pytest.mark.parametrize("reg", [
    region(VIDEO_W, VIDEO_H),
    region(VIDEO_W + 38, VIDEO_H + 63, 133, 45),    # 搜尋範圍連視窗邊框一起框
    region(round(VIDEO_W * 1.5), round(VIDEO_H * 1.5)),
], ids=["同尺寸", "比影片大且長寬比不同", "1.5倍"])
def test_偏移以影片像素原樣存檔不依搜尋範圍大小換算(tmp_path, engine, reg):
    res, _ = assemble(tmp_path, engine, reg,
                      steps=[off("開始", 10, -3), off("確定", 0, 0),
                             off("下一步", -7, 5)])

    steps = saved_steps(res)
    assert [(s["offsetX"], s["offsetY"]) for s in steps] == [
        (10, -3), (0, 0), (-7, 5)]
    r = flowfile.read(res["flow_path"])
    assert r["data"]["scanRegion"] == reg
    for name in ("開始", "確定", "下一步"):
        img = cv2.imdecode(np.frombuffer(r["images"][name], np.uint8),
                           cv2.IMREAD_COLOR)
        assert list(img.shape[1::-1]) == box(name)[2:]


def test_影片比搜尋範圍大時照常組裝但提醒(tmp_path, engine):
    res, _ = assemble(tmp_path, engine, region(VIDEO_W - 80, VIDEO_H))

    assert any("比搜尋範圍大" in w for w in res["warnings"])
    text = open(res["report_path"], encoding="utf-8").read()
    assert "比搜尋範圍大" in text


def test_影片不比搜尋範圍大時沒有提醒(tmp_path, engine):
    res, _ = assemble(tmp_path, engine, region(VIDEO_W + 38, VIDEO_H + 63))
    assert res["warnings"] == []


def test_profile已校準且畫面倍率不是1時座標再除以倍率(tmp_path, engine):
    cal = {"pair": ["a", "b"], "baseline": 100.0, "scale": 1.25,
           "fingerprint": FP}
    res, profile = assemble(tmp_path, engine, region(VIDEO_W, VIDEO_H),
                            steps=[off("開始", 10, -5)], cal=cal)

    s = saved_steps(res)[0]
    assert (s["offsetX"], s["offsetY"]) == (8, -4)
    assert res["scale"] == pytest.approx(1.25)
    # 校準資料只讀不寫
    with open(profile / "calibration.json", encoding="utf-8") as f:
        assert json.load(f) == cal


@pytest.mark.parametrize("cal", [
    {"pair": ["a", "b"], "baseline": 100.0, "scale": 1.0, "fingerprint": FP},
    {"pair": ["a", "b"], "baseline": 100.0, "scale": None, "fingerprint": None},
    {"pair": ["a", "b"], "baseline": 100.0, "scale": 1.25, "fingerprint": OTHER_FP},
], ids=["倍率1", "從未校準", "指紋不符"])
def test_未校準或倍率為1時座標不變(tmp_path, engine, cal):
    res, _ = assemble(tmp_path, engine, region(VIDEO_W, VIDEO_H),
                      steps=[off("開始", 10, -5)], cal=cal)
    s = saved_steps(res)[0]
    assert (s["offsetX"], s["offsetY"]) == (10, -5)


def test_交付報告寫明影片與實際畫面同尺度與畫面倍率換算(tmp_path, engine):
    cal = {"pair": ["a", "b"], "baseline": 100.0, "scale": 1.25,
           "fingerprint": FP}
    res, _ = assemble(tmp_path, engine, region(VIDEO_W, VIDEO_H), cal=cal)
    text = open(res["report_path"], encoding="utf-8").read()
    assert "影片尺度：與實際畫面一致" in text
    assert "換算比" not in text
    assert "畫面倍率" in text and "1.250" in text


def test_未校準時報告提醒以倍率1換算(tmp_path, engine):
    cal = {"pair": ["a", "b"], "baseline": 100.0, "scale": None,
           "fingerprint": None}
    res, _ = assemble(tmp_path, engine, region(VIDEO_W, VIDEO_H), cal=cal)
    text = open(res["report_path"], encoding="utf-8").read()
    assert "未校準" in text
