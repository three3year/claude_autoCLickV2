"""遊戲自繪游標的點擊特效: 學游標樣本 (learn_cursor) → 帶樣本掃描.

錄影程式畫不出點擊特效 (遊戲把系統游標換成自己畫的), 但遊戲的游標本身在
點擊當下會抖一下 (換一兩幀不同的樣子)。只打入口: `learn_cursor`、`scan`
與命令列; 輸入是 OpenCV 合成的影片 (遊戲自繪游標停在忙碌的畫面上)。
"""
import json
import subprocess
import sys

import cv2
import numpy as np
import pytest

import video_to_flow
from vtf_synth import (ROOT, VIDEO_H, VIDEO_W, cursor_sprite,
                       cursor_video)

CLICKS = [(30, (100, 80)), (70, (300, 160)), (115, (200, 200))]
FRAME_TOL = 2
POS_TOL = 4
# 游標停在不同背景上的幾幀與它的熱點位置 (Claude 從格線圖讀出來的)
LEARN_AT = [(10, (20, 20)), (40, (100, 80)), (60, (100, 80)), (80, (300, 160)),
            (100, (300, 160)), (125, (200, 200))]
SCENES = ((0, 1), (50, 2), (90, 3))


def hits(cands, frame, xy, high=None):
    return [c for c in cands
            if abs(c["frame"] - frame) <= FRAME_TOL
            and abs(c["x"] - xy[0]) <= POS_TOL and abs(c["y"] - xy[1]) <= POS_TOL
            and (high is None or c["confidence"] >= high)]


def high_ones(res):
    return [c for c in res["candidates"] if c["confidence"] >= res["highConfidence"]]


@pytest.fixture(scope="module")
def clicks_video(tmp_path_factory):
    d = tmp_path_factory.mktemp("cursor")
    return cursor_video(d / "clicks.mp4", clicks=CLICKS, scenes=SCENES)


@pytest.fixture(scope="module")
def sample(clicks_video, tmp_path_factory):
    out = tmp_path_factory.mktemp("sample") / "effect-sample.json"
    video_to_flow.learn_cursor(clicks_video, LEARN_AT, out)
    return out


def test_學到的游標樣本是游標本身而且熱點在尖端(sample):
    data = json.loads(sample.read_text(encoding="utf-8"))
    assert data["kind"] == "cursor"
    png = sample.parent / data["template"]
    tpl = cv2.imdecode(np.fromfile(str(png), np.uint8), cv2.IMREAD_UNCHANGED)
    assert tpl.shape[2] == 4                       # alpha＝游標的不透明處
    sprite = cursor_sprite()
    h, w = sprite.shape[:2]
    # 背景被濾掉: 樣本大小貼近游標本身, 不是整個裁切窗
    assert h - 6 <= tpl.shape[0] <= h + 6 and w - 6 <= tpl.shape[1] <= w + 6
    assert tpl[..., 3].mean() / 255 < 0.8
    hx, hy = data["hotspot"]
    # 樣本左上角相對游標圖可能差幾 px; 熱點必須落在樣本裡游標尖端那一點
    alpha = tpl[..., 3] > 0
    ys, xs = np.nonzero(alpha)
    tip = min(zip(xs + ys, xs, ys))[1:]
    assert abs(hx - tip[0]) <= 3 and abs(hy - tip[1]) <= 3


def test_帶游標樣本掃描時每次點擊都有高信心候選且位置是熱點(clicks_video, sample, tmp_path):
    res = video_to_flow.scan(clicks_video, tmp_path / "out", sample=str(sample))

    assert res["mode"] == "cursor"
    for frame, xy in CLICKS:
        assert hits(res["candidates"], frame, xy, res["highConfidence"]), (frame, xy)
    assert len(high_ones(res)) == len(CLICKS)
    assert all(c["kind"] == "click" and c["cue"] == "effect" for c in high_ones(res))


def test_沒有點擊只有畫面切換時沒有高信心候選(sample, tmp_path):
    video = cursor_video(tmp_path / "quiet.mp4", clicks=CLICKS, press_frames=0,
                         scenes=SCENES)
    res = video_to_flow.scan(video, tmp_path / "out", sample=str(sample))
    assert high_ones(res) == []


def test_畫面切換前沒看到特效時仍列為低信心候選(sample, tmp_path):
    # 游標停著、畫面切換, 但沒有特效 (可能是按鍵或特效被漏掉): 寧可多報
    video = cursor_video(tmp_path / "miss.mp4", clicks=[(48, (150, 120))],
                         press_frames=0, scenes=((0, 1), (50, 2)))
    res = video_to_flow.scan(video, tmp_path / "out", sample=str(sample))

    low = [c for c in res["candidates"] if c["cue"] == "screen"]
    assert low and all(c["confidence"] < res["highConfidence"] for c in low)
    # 位置＝切換前游標停的地方; 幀＝停留期間 (切換在第 50 幀)
    assert any(abs(c["x"] - 150) <= POS_TOL and abs(c["y"] - 120) <= POS_TOL
               and 40 <= c["frame"] <= 50 for c in low)


def test_壓縮關鍵幀的全畫面跳動不算點擊(sample, tmp_path):
    video = cursor_video(tmp_path / "kf.mp4", clicks=[(30, (100, 80))],
                         press_frames=0, keyframes=(40, 60, 80))
    res = video_to_flow.scan(video, tmp_path / "out", sample=str(sample))
    assert high_ones(res) == []


def test_游標停在畫面邊緣被切掉一半時點擊照樣抓得到(sample, tmp_path):
    edge = (VIDEO_W - 16, VIDEO_H - 20)
    video = cursor_video(tmp_path / "edge.mp4", clicks=[(40, edge)],
                         scenes=((0, 1),))
    res = video_to_flow.scan(video, tmp_path / "out", sample=str(sample))
    assert hits(res["candidates"], 40, edge, res["highConfidence"])


def test_學樣本的幀背景都一樣時清楚報錯(clicks_video, tmp_path):
    same = [(i, (20, 20)) for i in (2, 4, 6, 8, 12)]
    with pytest.raises(video_to_flow.ToolError, match="背景"):
        video_to_flow.learn_cursor(clicks_video, same, tmp_path / "s.json")


def test_學樣本給的位置不是游標時指名是哪幾幀(clicks_video, tmp_path):
    pts = LEARN_AT[:5] + [(125, (400, 40))]          # 最後一幀那裡沒有游標
    with pytest.raises(video_to_flow.ToolError, match="125"):
        video_to_flow.learn_cursor(clicks_video, pts, tmp_path / "s.json")


def test_學樣本至少要四幀(clicks_video, tmp_path):
    with pytest.raises(video_to_flow.ToolError, match="至少"):
        video_to_flow.learn_cursor(clicks_video, LEARN_AT[:2], tmp_path / "s.json")


def test_命令列學樣本再掃描(clicks_video, tmp_path):
    out = tmp_path / "effect-sample.json"
    at = ";".join(f"{f}:{x},{y}" for f, (x, y) in LEARN_AT)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "video_to_flow"), "learn-cursor",
         str(clicks_video), "--at", at, "--out", str(out)],
        capture_output=True, timeout=300)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert out.is_file()
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "video_to_flow"), "scan",
         str(clicks_video), "--out", str(tmp_path / "scan"), "--sample", str(out)],
        capture_output=True, timeout=300)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert "cursor" in proc.stdout.decode("utf-8", "replace")


def test_學樣本給的位置超出畫面時指名是哪一幀(clicks_video, tmp_path):
    pts = LEARN_AT[:5] + [(125, (VIDEO_W + 30, 40))]
    with pytest.raises(video_to_flow.ToolError, match="125.*超出畫面"):
        video_to_flow.learn_cursor(clicks_video, pts, tmp_path / "s.json")


def test_熱點落在游標圖外時提醒(clicks_video, tmp_path):
    # 每幀都指在尖端左上 8px 的空白處: 學得出游標, 但熱點不在游標上
    off = [(f, (x - 8, y - 8)) for f, (x, y) in LEARN_AT]
    res = video_to_flow.learn_cursor(clicks_video, off, tmp_path / "s.json")
    assert any("熱點" in w for w in res["warnings"])
    good = video_to_flow.learn_cursor(clicks_video, LEARN_AT, tmp_path / "g.json")
    assert good["warnings"] == []
