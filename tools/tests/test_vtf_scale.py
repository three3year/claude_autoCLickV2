"""影片尺度就是流程尺度 (ADR 0009); 新流程必須有校準對 (v2f-rules-agent-docs 05).

`校準對`由計畫指名, `基準距離`在影片影格上量; 沒寫或量不到主對＝報錯、不組裝,
備用對量不到只是不帶備用對。只打組裝入口; 斷言流程裡的偏移、校準資料與報告文字。
"""
import os

import cv2
import numpy as np
import pytest

import calibration
import flowfile
import video_to_flow
from vtf_synth import (box, center, demo_plan, demo_video, find, make_out, snapshot,
                       title_box)


def title_center(name):
    x, y, w, h = title_box(name)
    return x + w // 2, y + h // 2


def off(name, dx, dy):
    """點在按鈕中心旁 (dx, dy) 的找圖點擊."""
    cx, cy = center(name)
    return find(name, at=[cx + dx, cy + dy])


def plan(tmp_path, **extra):
    return demo_plan(demo_video(tmp_path), make_out(tmp_path), **extra)


def overview(res):
    with open(os.path.join(res["report_path"], "總覽.md"), encoding="utf-8") as f:
        return f.read()


def test_偏移以影片像素原樣進流程_範本圖不縮放(tmp_path, engine):
    res = video_to_flow.assemble(
        plan(tmp_path, steps=[off("開始", 10, -3), off("確定", 0, 0), off("下一步", -7, 5)]),
        engine=engine)

    steps = flowfile.read_flow(res["flow_path"])["steps"]
    assert [tuple(s["offset"]) for s in steps] == [(10, -3), (0, 0), (-7, 5)]
    for name in ("開始", "確定", "下一步"):
        with open(f"{res['flow_path']}/templates/{name}.png", "rb") as f:
            img = cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)
        assert list(img.shape[1::-1]) == box(name)[2:]


def test_產出的流程帶校準對與基準距離_兩張圖是流程的範本(tmp_path, engine):
    res = video_to_flow.assemble(plan(tmp_path), engine=engine)

    r = flowfile.read_flow(res["flow_path"])
    (ax, ay), (bx, by) = title_center("圖示"), title_center("關閉")
    d = round(((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5, 1)
    assert r["calibration"]["pair"] == ["圖示", "關閉"]
    assert abs(r["calibration"]["baseline"] - d) <= 1.0
    tdir = os.path.join(res["flow_path"], "templates")
    assert {"圖示.png", "關閉.png"} <= set(os.listdir(tdir)), "校準對的圖跟著流程"


def test_交付報告總覽列出校準對與基準距離(tmp_path, engine):
    res = video_to_flow.assemble(plan(tmp_path), engine=engine)
    text = overview(res)
    assert "校準對：圖示 × 關閉" in text and "基準距離" in text


def test_沒有指定校準對_報錯不組裝(tmp_path, engine):
    p = plan(tmp_path, calibration=None)
    before = snapshot(p["out"])
    with pytest.raises(video_to_flow.ToolError, match="必須有校準對"):
        video_to_flow.assemble(p, engine=engine)
    assert snapshot(p["out"]) == before


def test_校準對量不到_報錯不組裝(tmp_path, engine):
    p = plan(tmp_path, calibration={"pair": ["開始", "關閉"], "frame": 35})  # 第 35 幀沒有「開始」
    before = snapshot(p["out"])
    with pytest.raises(video_to_flow.ToolError, match="校準對量不到.*開始"):
        video_to_flow.assemble(p, engine=engine)
    assert snapshot(p["out"]) == before


def test_自我驗證的查詢帶預期尺度1_縮放餘裕查兩端_量校準對用全範圍(tmp_path, engine):
    class Spy:
        """真引擎外面包一層, 記下每次查詢收到的預期尺度."""

        def __init__(self, inner):
            self.inner, self.seen = inner, []

        def __getattr__(self, name):
            return getattr(self.inner, name)

        def query(self, lib, name, image, color_check=False, expected_scale=None):
            self.seen.append((name, expected_scale))
            return self.inner.query(lib, name, image, color_check=color_check,
                                    expected_scale=expected_scale)

    spy = Spy(engine)
    video_to_flow.assemble(plan(tmp_path), engine=spy)
    verify = [s for n, s in spy.seen if n not in ("圖示", "關閉")]
    assert 1.0 in verify and set(verify) <= {1.0, 0.85, 1.15}, "縮放餘裕另查 ×0.85 / ×1.15"
    cal = [s for n, s in spy.seen if n in ("圖示", "關閉")]
    assert None in cal, "量基準距離與執行開頭的校準一樣用全範圍查"


# ---------- 備用校準對 ----------

def test_計畫寫備用組_同一幀量兩組_偏移對齊座標基準點(tmp_path, engine):
    """主對＝畫面內的「開始」＋「關閉」, 備用＝「圖示」＋「關閉」."""
    p = plan(tmp_path, calibration={"pair": ["開始", "關閉"],
                                    "fallback": {"pair": ["圖示", "關閉"]}})
    res = video_to_flow.assemble(p, engine=engine)
    cal = calibration.flow_pair(flowfile.read_flow(res["flow_path"]))
    fb = calibration.fallback_pair(cal)
    (ix, iy) = title_center("圖示")
    assert fb["pair"] == ["圖示", "關閉"]
    ax, ay = center("開始")
    assert fb["offset"] == [ax - ix, ay - iy], "備用第一張中心 → 座標基準點"
    assert calibration.fallback_anchor((ix, iy), fb["offset"], 1.0) == (ax, ay)
    assert "備用校準對：圖示 × 關閉" in overview(res)


def test_備用對量不到_流程不帶備用對_報告寫明(tmp_path, engine):
    p = plan(tmp_path, calibration={"pair": ["圖示", "關閉"], "frame": 35,
                                    "fallback": {"pair": ["開始", "關閉"]}})
    res = video_to_flow.assemble(p, engine=engine)
    cal = calibration.flow_pair(flowfile.read_flow(res["flow_path"]))
    assert cal["pair"] == ["圖示", "關閉"]
    assert calibration.fallback_pair(cal) is None
    assert res["fallback_problem"] and "開始" in res["fallback_problem"]
    text = overview(res)
    assert "備用校準對量不到" in text and "開始" in text


def test_備用組與主對相同_計畫被拒(tmp_path, engine):
    p = plan(tmp_path, calibration={"pair": ["圖示", "關閉"],
                                    "fallback": {"pair": ["關閉", "圖示"]}})
    with pytest.raises(video_to_flow.ToolError, match="相同"):
        video_to_flow.assemble(p, engine=engine)
