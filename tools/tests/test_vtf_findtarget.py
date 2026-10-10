"""票 08 — 計畫的找圖步驟與確認圖可寫比色、挑選規則、限定範圍.

用真引擎跑合成示範影片, 只打組裝入口; 斷言存檔裡的找圖目標、待重拍結果、
組裝拒絕時輸出位置一個檔案都沒多。自我驗證與執行時走同一個找圖目標模組
(裁範圍 → 查詢 → 比色 → 挑選), 驗證通過就代表執行時會挑到同一個。
"""
import json

import cv2
import numpy as np
import pytest

import flowfile
import video_to_flow
from video_to_flow import ToolError
from vtf_synth import (VIDEO_H, VIDEO_W, box, center, demo_plan, demo_video,
                       find, make_button, make_out, screen, snapshot,
                       timeline, write_video)

REGION = [0, 0, VIDEO_W, VIDEO_H]


def run(plan, engine):
    return video_to_flow.assemble(plan, engine=engine)


def saved_steps(res):
    return flowfile.read_flow(res["flow_path"])["steps"]


# ---------- 同款多張: 挑選規則 ----------

CARD = make_button(w=44, h=32, seed=21)
CARDS = [(200, 40), (200, 110), (200, 180)]     # 一欄三張同款 (左上角)


def card_center(i):
    x, y = CARDS[i]
    return [x + 22, y + 16]


@pytest.fixture
def cards(tmp_path):
    frames = timeline((screen([(CARD, x, y) for x, y in CARDS]), 10))
    video = write_video(tmp_path / "cards.mp4", frames)
    templates = {"卡": {"frame": 5, "box": [*CARDS[1], 44, 32]}}   # 取材自第二張
    return video, make_out(tmp_path), templates


def test_同款多張時由上到下第N驗證通過且點對(cards, engine):
    video, profile, templates = cards
    steps = [{"type": "find_click", "template": "卡", "frame": 5,
              "at": card_center(1), "pick": {"kind": "top", "n": 2}}]
    res = run(demo_plan(video, profile, steps=steps, templates=templates), engine)

    assert res["retake"] == {}
    [s] = saved_steps(res)
    assert s["target"] == {"template": "卡", "pick": {"top": 2}}
    assert s["offset"] == [0, 0]


def test_挑選規則設錯被標待重拍(cards, engine):
    video, profile, templates = cards
    steps = [{"type": "find_click", "template": "卡", "frame": 5,
              "at": card_center(1), "pick": {"kind": "top", "n": 1}}]
    res = run(demo_plan(video, profile, steps=steps, templates=templates), engine)

    assert list(res["retake"]) == ["卡"]
    assert any("位置不符" in why for why in res["retake"]["卡"])


# ---------- 限定範圍與指定點: 影片像素 → 相對原點/搜尋範圍 ----------

def located_plan(video, profile, second):
    """開始 (定位, 更新原點) → 確定 (帶限定範圍/指定點)."""
    return demo_plan(video, profile, steps=[
        find("開始", action="none"), dict(find("確定"), **second),
        find("下一步")])


def test_指定點從影片像素換算成相對原點(tmp_path, engine):
    video = demo_video(tmp_path)
    profile = make_out(tmp_path)
    ox, oy = center("開始")
    second = {"pick": {"kind": "near", "at": center("確定")}}
    res = run(located_plan(video, profile, second), engine)

    assert res["retake"] == {}
    s = saved_steps(res)[1]
    assert "limit" not in s["target"]
    cx, cy = center("確定")
    assert s["target"]["pick"] == {"near": [cx - ox, cy - oy]}


def test_九宮格與以搜尋範圍為基準的指定點已退場(tmp_path, engine):
    video = demo_video(tmp_path)
    profile = make_out(tmp_path)
    before = snapshot(profile)
    for second in ({"limit": {"kind": "grid", "cells": [5, 6, 8, 9]}},
                   {"pick": {"kind": "near", "base": "region", "at": [320, 170]}},
                   {"pick": {"kind": "near", "base": "origin", "at": [320, 170]}}):
        with pytest.raises(ToolError):
            run(located_plan(video, profile, second), engine)
    assert snapshot(profile) == before


def test_確認圖的找圖目標用點擊後的原點換算(tmp_path, engine):
    video = demo_video(tmp_path)
    profile = make_out(tmp_path)
    at = center("開始")
    bx, by, bw, bh = box("確定")
    steps = [find("開始", confirm="appear",
                  confirmTarget={"template": "確定", "colorCheck": True,
                                 "pick": {"kind": "near", "at": [bx, by]}}),
             find("確定"), find("下一步")]
    res = run(demo_plan(video, profile, steps=steps), engine)

    s = saved_steps(res)[0]
    assert s["confirm_target"] == {
        "template": "確定", "color": True,
        "pick": {"near": [bx - at[0], by - at[1]]}}


# ---------- 比色: 只差顏色的 absent 幀 ----------

def orange_button():
    img = np.full((36, 60, 3), (20, 20, 20), np.uint8)
    cv2.rectangle(img, (2, 2), (57, 33), (0, 140, 255), -1)
    cv2.rectangle(img, (2, 2), (57, 33), (255, 255, 255), 2)
    cv2.putText(img, "GO", (14, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (255, 255, 255), 2, cv2.LINE_AA)
    cv2.line(img, (42, 8), (52, 28), (40, 40, 200), 3)
    return img


@pytest.fixture
def greyed(tmp_path):
    btn = orange_button()
    grey = cv2.cvtColor(cv2.cvtColor(btn, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    frames = timeline((screen([(grey, 300, 120)]), 15),
                      (screen([(btn, 300, 120)]), 15))
    video = write_video(tmp_path / "grey.mp4", frames)
    templates = {"置入": {"frame": 20, "box": [300, 120, 60, 36],
                          "absent": [5]}}
    return video, make_out(tmp_path), templates


def test_只差顏色的absent幀_不開比色會被匹配(greyed, engine):
    video, profile, templates = greyed
    steps = [{"type": "find_click", "template": "置入", "frame": 20,
              "at": [330, 138]}]
    res = run(demo_plan(video, profile, steps=steps, templates=templates), engine)
    assert list(res["retake"]) == ["置入"]
    assert any("出現前就匹配" in why for why in res["retake"]["置入"])


def test_只差顏色的absent幀_開比色後不再被匹配(greyed, engine):
    video, profile, templates = greyed
    steps = [{"type": "find_click", "template": "置入", "frame": 20,
              "at": [330, 138], "colorCheck": True}]
    res = run(demo_plan(video, profile, steps=steps, templates=templates), engine)
    assert res["retake"] == {}
    assert saved_steps(res)[0]["target"]["color"] is True


# ---------- 組裝拒絕不完整設定 ----------

@pytest.mark.parametrize("bad, why", [
    ({"limit": {"kind": "origin", "rect": [10, 10, 50, 50]}}, "已退場"),
    ({"pick": {"kind": "near", "at": [10, 10]}}, "原點"),
    ({"pick": {"kind": "top", "n": 0}}, "N"),
    ({"pick": {"kind": "left"}}, "N"),
    ({"limit": {"kind": "grid", "cells": [8]}}, "已退場"),
    ({"pick": {"kind": "near", "base": "region", "at": [1, 1]}}, "near"),
    ({"colorCheck": "yes"}, "colorCheck"),
    ({"pick": {"kind": "best"}}, "pick"),
], ids=["限定範圍已退場", "指定點卻沒有原點",
        "N小於1", "沒寫N", "九宮格已退場", "指定點不再有基準",
        "colorCheck不是布林", "不認得的挑選規則"])
def test_組裝拒絕不完整設定且輸出位置不多任何檔案(tmp_path, engine, bad, why):
    video = demo_video(tmp_path)
    profile = make_out(tmp_path)
    before = snapshot(profile)
    plan = demo_plan(video, profile, steps=[dict(find("開始"), **bad),
                                            find("確定"), find("下一步")])
    with pytest.raises(ToolError) as e:
        run(plan, engine)
    assert why in str(e.value)
    assert snapshot(profile) == before


def test_confirmTemplate與confirmTarget不能同時寫(tmp_path, engine):
    video = demo_video(tmp_path)
    profile = make_out(tmp_path)
    plan = demo_plan(video, profile, steps=[
        find("開始", confirm="appear", confirmTemplate="確定",
             confirmTarget={"template": "確定"}), find("確定"), find("下一步")])
    with pytest.raises(ToolError):
        run(plan, engine)
