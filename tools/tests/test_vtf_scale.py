"""影片與實際畫面同尺度 (1:1), 影片尺度就是流程尺度 (ADR 0009).

示範影片是在執行流程的這台機器上、以實際畫面尺度錄的: 影片像素就是螢幕
像素, 偏移不依搜尋範圍大小換算 (搜尋範圍只決定流程在哪裡找圖), 也不讀
profile 的校準資料。`校準對`由計畫指名, `基準距離`在影片影格上量。

只打組裝入口; 斷言存檔裡的偏移、範本圖尺寸、報告文字與 profile 檔案狀態。
"""
import json

import cv2
import numpy as np
import pytest

import calibration
import flowfile
import video_to_flow
from vtf_synth import (VIDEO_H, VIDEO_W, box, center, demo_plan, demo_templates,
                       demo_video, find, make_profile, title_box)


def title_center(name):
    x, y, w, h = title_box(name)
    return x + w // 2, y + h // 2


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
    return video_to_flow.assemble(plan, engine=engine), profile


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


def test_不讀profile的校準資料_座標原樣(tmp_path, engine):
    """影片尺度就是流程尺度 (ADR 0009): profile 的舊校準資料一律不看、不寫."""
    cal = {"pair": ["a", "b"], "baseline": 100.0, "scale": 1.25,
           "fingerprint": None}
    res, profile = assemble(tmp_path, engine, region(VIDEO_W, VIDEO_H),
                            steps=[off("開始", 10, -5)], cal=cal)

    s = saved_steps(res)[0]
    assert (s["offsetX"], s["offsetY"]) == (10, -5)
    with open(profile / "calibration.json", encoding="utf-8") as f:
        assert json.load(f) == cal


# ---------- 校準對 (flow-scale 票 05) ----------

def title_plan(tmp_path, pair=("圖示", "關閉"), **extra):
    video = demo_video(tmp_path, title=True)
    profile = make_profile(tmp_path, region=region(VIDEO_W, VIDEO_H))
    templates = demo_templates()
    for n in ("圖示", "關閉"):
        templates[n] = {"frame": 5, "box": title_box(n)}
    plan = demo_plan(video, profile, templates=templates, **extra)
    if pair:
        plan["calibration"] = {"pair": list(pair)}
    return plan


def test_產出的流程帶校準對與基準距離_兩張圖是流程的範本(tmp_path, engine):
    res = video_to_flow.assemble(title_plan(tmp_path), engine=engine)

    r = flowfile.read(res["flow_path"])
    (ax, ay), (bx, by) = title_center("圖示"), title_center("關閉")
    assert calibration.flow_pair(r["data"]) == {
        "pair": ["圖示", "關閉"], "baseline": float(abs(bx - ax))}
    assert ay == by
    assert {"圖示", "關閉"} <= set(r["images"]), "校準對的圖跟著存檔"


def test_交付報告列出校準對與基準距離(tmp_path, engine):
    res = video_to_flow.assemble(title_plan(tmp_path), engine=engine)
    text = open(res["report_path"], encoding="utf-8").read()
    assert "校準對：圖示 × 關閉" in text and "基準距離" in text
    assert "不能執行" not in text


def test_沒有指定校準對_報告明說流程不能執行(tmp_path, engine):
    res = video_to_flow.assemble(title_plan(tmp_path, pair=None), engine=engine)
    assert calibration.flow_pair(flowfile.read(res["flow_path"])["data"]) is None
    text = open(res["report_path"], encoding="utf-8").read()
    assert "不能執行" in text


def test_校準對量不到_報告明說原因且流程不帶校準對(tmp_path, engine):
    plan = title_plan(tmp_path)
    plan["calibration"]["frame"] = 35       # 那一幀沒有「開始」
    plan["calibration"]["pair"] = ["開始", "關閉"]
    res = video_to_flow.assemble(plan, engine=engine)
    assert calibration.flow_pair(flowfile.read(res["flow_path"])["data"]) is None
    text = open(res["report_path"], encoding="utf-8").read()
    assert "量不到" in text and "開始" in text and "不能執行" in text


def test_自我驗證的查詢帶預期尺度1(tmp_path, engine):
    class Spy:
        """真引擎外面包一層, 記下每次查詢收到的預期尺度."""

        def __init__(self, inner):
            self.inner, self.seen = inner, []

        def __getattr__(self, name):
            return getattr(self.inner, name)

        def query(self, lib, name, image, color_check=False,
                  expected_scale=None):
            self.seen.append((name, expected_scale))
            return self.inner.query(lib, name, image, color_check=color_check,
                                    expected_scale=expected_scale)

    spy = Spy(engine)
    video_to_flow.assemble(title_plan(tmp_path), engine=spy)
    verify = [s for n, s in spy.seen if n not in ("圖示", "關閉")]
    assert verify and all(s == 1.0 for s in verify)
    cal = [s for n, s in spy.seen if n in ("圖示", "關閉")]
    assert None in cal, "量基準距離與執行開頭的校準一樣用全範圍查"
