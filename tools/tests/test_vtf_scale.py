"""影片與實際畫面同尺度 (1:1), 影片尺度就是流程尺度 (ADR 0009).

示範影片是在執行流程的這台機器上、以實際畫面尺度錄的: 影片像素就是螢幕
像素, 偏移原樣進流程 (工具不寫搜尋範圍)。`校準對`由計畫指名, `基準距離`在影片
影格上量。

只打組裝入口; 斷言流程裡的偏移、範本圖尺寸與報告文字。
"""
import json

import cv2
import numpy as np
import pytest

import calibration
import flowfile
import video_to_flow
from vtf_synth import (VIDEO_H, VIDEO_W, box, center, demo_plan, demo_templates,
                       demo_video, find, make_out, title_box)


def title_center(name):
    x, y, w, h = title_box(name)
    return x + w // 2, y + h // 2


def off(name, dx, dy):
    """點在按鈕中心旁 (dx, dy) 的找圖點擊."""
    cx, cy = center(name)
    return find(name, at=[cx + dx, cy + dy])


def assemble(tmp_path, engine, steps=None):
    video = demo_video(tmp_path)
    out = make_out(tmp_path)
    plan = demo_plan(video, out, steps=steps)
    return video_to_flow.assemble(plan, engine=engine), out


def saved_steps(res):
    return flowfile.read_flow(res["flow_path"])["steps"]


def test_偏移以影片像素原樣進流程_範本圖不縮放(tmp_path, engine):
    res, _ = assemble(tmp_path, engine,
                      steps=[off("開始", 10, -3), off("確定", 0, 0),
                             off("下一步", -7, 5)])

    steps = saved_steps(res)
    assert [tuple(s["offset"]) for s in steps] == [
        (10, -3), (0, 0), (-7, 5)]
    assert flowfile.read_flow(res["flow_path"])["scan_region"] is None
    for name in ("開始", "確定", "下一步"):
        with open(f"{res['flow_path']}/templates/{name}.png", "rb") as f:
            img = cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)
        assert list(img.shape[1::-1]) == box(name)[2:]


# ---------- 校準對 (flow-scale 票 05) ----------

def title_plan(tmp_path, pair=("圖示", "關閉"), **extra):
    video = demo_video(tmp_path, title=True)
    profile = make_out(tmp_path)
    templates = demo_templates()
    for n in ("圖示", "關閉"):
        templates[n] = {"frame": 5, "box": title_box(n)}
    plan = demo_plan(video, profile, templates=templates, **extra)
    if pair:
        plan["calibration"] = {"pair": list(pair)}
    return plan


def test_產出的流程帶校準對與基準距離_兩張圖是流程的範本(tmp_path, engine):
    res = video_to_flow.assemble(title_plan(tmp_path), engine=engine)

    r = flowfile.read_flow(res["flow_path"])
    (ax, ay), (bx, by) = title_center("圖示"), title_center("關閉")
    assert r["calibration"] == {"pair": ["圖示", "關閉"], "baseline": float(abs(bx - ax))}
    assert ay == by
    import os
    tdir = os.path.join(res["flow_path"], "templates")
    assert {"圖示.png", "關閉.png"} <= set(os.listdir(tdir)), "校準對的圖跟著流程"


def test_交付報告列出校準對與基準距離(tmp_path, engine):
    res = video_to_flow.assemble(title_plan(tmp_path), engine=engine)
    text = open(res["report_path"], encoding="utf-8").read()
    assert "校準對：圖示 × 關閉" in text and "基準距離" in text
    assert "不能執行" not in text


def test_沒有指定校準對_報告明說流程不能執行(tmp_path, engine):
    res = video_to_flow.assemble(title_plan(tmp_path, pair=None), engine=engine)
    assert calibration.flow_pair(flowfile.read_flow(res["flow_path"])) is None
    text = open(res["report_path"], encoding="utf-8").read()
    assert "不能執行" in text


def test_校準對量不到_報告明說原因且流程不帶校準對(tmp_path, engine):
    plan = title_plan(tmp_path)
    plan["calibration"]["frame"] = 35       # 那一幀沒有「開始」
    plan["calibration"]["pair"] = ["開始", "關閉"]
    res = video_to_flow.assemble(plan, engine=engine)
    assert calibration.flow_pair(flowfile.read_flow(res["flow_path"])) is None
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


# ---------- 備用校準對 (scale-range 票 08) ----------

def test_計畫寫備用組_同一幀量兩組_偏移對齊座標基準點(tmp_path, engine):
    """主對＝畫面內的「開始」＋標題列「關閉」, 備用＝標題列圖示＋關閉鈕."""
    plan = title_plan(tmp_path, pair=("開始", "關閉"))
    plan["calibration"]["fallback"] = {"pair": ["圖示", "關閉"]}
    res = video_to_flow.assemble(plan, engine=engine)
    cal = calibration.flow_pair(flowfile.read_flow(res["flow_path"]))
    fb = calibration.fallback_pair(cal)
    (ix, iy), (cx, cy) = title_center("圖示"), title_center("關閉")
    assert fb["pair"] == ["圖示", "關閉"]
    assert fb["baseline"] == float(abs(cx - ix))
    ax, ay = center("開始")
    assert fb["offset"] == [ax - ix, ay - iy], "備用第一張中心 → 座標基準點 (影片像素＝流程尺度)"
    assert calibration.fallback_anchor((ix, iy), fb["offset"], 1.0) == (ax, ay)
    text = open(res["report_path"], encoding="utf-8").read()
    assert "備用校準對：圖示 × 關閉" in text


def test_備用對量不到_流程不帶備用對_報告寫明(tmp_path, engine):
    plan = title_plan(tmp_path, pair=("圖示", "關閉"))
    plan["calibration"]["frame"] = 35
    plan["calibration"]["fallback"] = {"pair": ["開始", "關閉"]}   # 第 35 幀沒有「開始」
    res = video_to_flow.assemble(plan, engine=engine)
    cal = calibration.flow_pair(flowfile.read_flow(res["flow_path"]))
    assert cal["pair"] == ["圖示", "關閉"]
    assert calibration.fallback_pair(cal) is None
    text = open(res["report_path"], encoding="utf-8").read()
    assert "備用校準對量不到" in text and "開始" in text


def test_備用組與主對相同_計畫被拒(tmp_path, engine):
    import pytest

    from video_to_flow.errors import ToolError
    plan = title_plan(tmp_path)
    plan["calibration"]["fallback"] = {"pair": ["關閉", "圖示"]}
    with pytest.raises(ToolError, match="相同"):
        video_to_flow.assemble(plan, engine=engine)
