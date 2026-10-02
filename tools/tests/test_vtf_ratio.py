"""票 02 — `影片換算比`與尺度檢查 (含已校準 profile 的`畫面倍率`換回基準尺度).

只打組裝入口; 斷言存檔裡的偏移、範本圖尺寸、報告文字與 profile 檔案狀態。
"""
import json

import cv2
import numpy as np
import pytest

import flowfile
import video_to_flow
from vtf_synth import (VIDEO_H, VIDEO_W, box, center, demo_plan, demo_video,
                       find, make_profile, snapshot)

FP = {"x": 0, "y": 0, "w": 1920, "h": 1080}
OTHER_FP = {"x": 0, "y": 0, "w": 2560, "h": 1440}


def region(k, ky=None):
    return [0, 0, round(VIDEO_W * k), round(VIDEO_H * (ky or k))]


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


def test_搜尋範圍是影片的1點5倍時找圖偏移乘1點5且範本不縮放(tmp_path, engine):
    res, _ = assemble(tmp_path, engine, region(1.5),
                      steps=[off("開始", 10, -3), off("確定", 0, 0),
                             off("下一步", -7, 5)])

    steps = saved_steps(res)
    assert [(s["offsetX"], s["offsetY"]) for s in steps] == [
        (15, -5), (0, 0), (-11, 8)]   # ×1.5 四捨五入 (負值對稱進位)
    r = flowfile.read(res["flow_path"])
    for name in ("開始", "確定", "下一步"):
        img = cv2.imdecode(np.frombuffer(r["images"][name], np.uint8),
                           cv2.IMREAD_COLOR)
        assert list(img.shape[1::-1]) == box(name)[2:]
    assert res["ratio"] == pytest.approx(1.5)


@pytest.mark.parametrize("ky", [1.5 * 1.03, 1.5 * 0.97])
def test_寬高比值差距超過約2趴就報錯且沒有新檔(tmp_path, engine, ky):
    video = demo_video(tmp_path)
    profile = make_profile(tmp_path, region=region(1.5, ky))
    before = snapshot(profile)

    with pytest.raises(video_to_flow.ToolError, match="長寬比"):
        video_to_flow.assemble(demo_plan(video, profile), engine=engine,
                               fingerprint=FP)
    assert snapshot(profile) == before


def test_寬高比值差距在容許內照常組裝(tmp_path, engine):
    res, _ = assemble(tmp_path, engine, region(1.5, 1.5 * 1.01))
    assert res["ratio"] == pytest.approx(1.5, abs=0.01)


@pytest.mark.parametrize("k", [2.0, 0.5])
def test_影片換算比超出引擎尺度範圍就報錯且沒有新檔(tmp_path, engine, k):
    video = demo_video(tmp_path)
    profile = make_profile(tmp_path, region=region(k),
                           config={"scale_range": [0.6, 1.5]})
    before = snapshot(profile)

    with pytest.raises(video_to_flow.ToolError, match="尺度範圍"):
        video_to_flow.assemble(demo_plan(video, profile), engine=engine,
                               fingerprint=FP)
    assert snapshot(profile) == before


def test_profile已校準且畫面倍率不是1時座標再除以倍率(tmp_path, engine):
    cal = {"pair": ["a", "b"], "baseline": 100.0, "scale": 1.25,
           "fingerprint": FP}
    res, profile = assemble(tmp_path, engine, region(1.0),
                            steps=[off("開始", 10, -5)], cal=cal)

    s = saved_steps(res)[0]
    assert (s["offsetX"], s["offsetY"]) == (8, -4)
    assert res["scale"] == pytest.approx(1.25)
    # 校準資料只讀不寫
    with open(profile / "calibration.json", encoding="utf-8") as f:
        assert json.load(f) == cal


def test_影片換算比與畫面倍率一起換算只進位一次(tmp_path, engine):
    cal = {"pair": ["a", "b"], "baseline": 100.0, "scale": 1.2,
           "fingerprint": FP}
    res, _ = assemble(tmp_path, engine, region(1.5),
                      steps=[off("開始", 7, 3)], cal=cal)
    s = saved_steps(res)[0]
    # 7 × 1.5 ÷ 1.2 = 8.75 → 9; 3 × 1.25 = 3.75 → 4
    assert (s["offsetX"], s["offsetY"]) == (9, 4)


@pytest.mark.parametrize("cal", [
    {"pair": ["a", "b"], "baseline": 100.0, "scale": 1.0, "fingerprint": FP},
    {"pair": ["a", "b"], "baseline": 100.0, "scale": None, "fingerprint": None},
    {"pair": ["a", "b"], "baseline": 100.0, "scale": 1.25, "fingerprint": OTHER_FP},
], ids=["倍率1", "從未校準", "指紋不符"])
def test_未校準或倍率為1時座標不變(tmp_path, engine, cal):
    res, _ = assemble(tmp_path, engine, region(1.0),
                      steps=[off("開始", 10, -5)], cal=cal)
    s = saved_steps(res)[0]
    assert (s["offsetX"], s["offsetY"]) == (10, -5)


def test_交付報告寫明影片換算比與畫面倍率換算(tmp_path, engine):
    cal = {"pair": ["a", "b"], "baseline": 100.0, "scale": 1.25,
           "fingerprint": FP}
    res, _ = assemble(tmp_path, engine, region(1.5), cal=cal)
    text = open(res["report_path"], encoding="utf-8").read()
    assert "影片換算比：1.500" in text
    assert "畫面倍率" in text and "1.250" in text


def test_未校準時報告提醒以倍率1換算(tmp_path, engine):
    cal = {"pair": ["a", "b"], "baseline": 100.0, "scale": None,
           "fingerprint": None}
    res, _ = assemble(tmp_path, engine, region(1.0), cal=cal)
    text = open(res["report_path"], encoding="utf-8").read()
    assert "未校準" in text
