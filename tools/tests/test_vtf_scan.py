"""票 06 — 掃描: 示範影片 → 候選點擊 + 縮圖.

只打掃描入口 (`video_to_flow.scan` 與命令列); 輸入是 OpenCV 合成的影片
(假按鈕、假游標、在指定幀畫假點擊特效), 斷言候選清單、輸出檔案。
"""
import json
import subprocess
import sys

import cv2
import numpy as np
import pytest

import video_to_flow
from vtf_synth import ROOT, ring_sample, scan_video

CLICKS = [(20, (100, 80)), (50, (300, 160)), (90, (200, 200))]
FRAME_TOL = 2
POS_TOL = 6


def hits(cands, frame, xy, high=None):
    return [c for c in cands
            if abs(c["frame"] - frame) <= FRAME_TOL
            and abs(c["x"] - xy[0]) <= POS_TOL and abs(c["y"] - xy[1]) <= POS_TOL
            and (high is None or c["confidence"] >= high)]


def high_ones(res):
    return [c for c in res["candidates"] if c["confidence"] >= res["highConfidence"]]


@pytest.fixture
def clicks_video(tmp_path):
    return scan_video(tmp_path / "clicks.mp4", clicks=CLICKS)


@pytest.fixture
def quiet_video(tmp_path):
    """游標照樣移動、畫面照樣切換, 但沒有任何點擊特效."""
    return scan_video(tmp_path / "quiet.mp4", clicks=CLICKS, effect=False)


def test_有特效樣本時每次特效都有高信心候選且沒有多出來的(clicks_video, tmp_path):
    res = video_to_flow.scan(clicks_video, tmp_path / "out", sample=ring_sample())

    assert res["mode"] == "sample"
    for frame, xy in CLICKS:
        assert hits(res["candidates"], frame, xy, res["highConfidence"]), (frame, xy)
    assert len(high_ones(res)) == len(CLICKS)
    assert all(c["kind"] == "click" for c in high_ones(res))


def test_特效樣本可以是檔案路徑(clicks_video, tmp_path):
    sample = tmp_path / "effect-sample.json"
    sample.write_text(json.dumps(ring_sample()), encoding="utf-8")
    res = video_to_flow.scan(clicks_video, tmp_path / "out", sample=str(sample))
    assert len(high_ones(res)) == len(CLICKS)


def test_沒有特效樣本時每次特效一個不漏(clicks_video, tmp_path):
    res = video_to_flow.scan(clicks_video, tmp_path / "out")

    assert res["mode"] == "fallback"
    for frame, xy in CLICKS:
        assert hits(res["candidates"], frame, xy), (frame, xy)


def test_沒有特效樣本時特效清楚的候選也是高信心(clicks_video, tmp_path):
    res = video_to_flow.scan(clicks_video, tmp_path / "out")
    for frame, xy in CLICKS:
        assert hits(res["candidates"], frame, xy, res["highConfidence"]), (frame, xy)


def test_沒有任何特效的影片沒有高信心候選(quiet_video, tmp_path):
    assert high_ones(video_to_flow.scan(quiet_video, tmp_path / "a")) == []
    assert high_ones(video_to_flow.scan(quiet_video, tmp_path / "b",
                                        sample=ring_sample())) == []


def test_有特效樣本時拖曳辨識為起訖兩點(tmp_path):
    video = scan_video(tmp_path / "drag.mp4", clicks=[(20, (100, 80))],
                       drags=[(60, (80, 230), 75, (380, 230))])
    res = video_to_flow.scan(video, tmp_path / "out", sample=ring_sample())

    drags = [c for c in high_ones(res) if c["kind"] == "drag"]
    assert len(drags) == 1
    d = drags[0]
    assert abs(d["frame"] - 60) <= FRAME_TOL and abs(d["endFrame"] - 75) <= FRAME_TOL
    assert np.allclose(d["from"], (80, 230), atol=POS_TOL)
    assert np.allclose(d["to"], (380, 230), atol=POS_TOL)
    assert hits(res["candidates"], 20, (100, 80), res["highConfidence"])


def test_每個候選輸出前後數幀縮圖到指定目錄(clicks_video, tmp_path):
    out = tmp_path / "縮圖"
    res = video_to_flow.scan(clicks_video, out, sample=ring_sample())

    assert res["candidates"]
    for c in res["candidates"]:
        thumb = out / c["thumb"]
        assert thumb.is_file()
        img = cv2.imdecode(np.fromfile(str(thumb), np.uint8), cv2.IMREAD_COLOR)
        assert img is not None and img.shape[0] > 0
        assert c["thumbFrames"] and min(c["thumbFrames"]) < c["frame"] < max(c["thumbFrames"])


def test_候選清單以JSON輸出且欄位足以寫轉換計畫(clicks_video, tmp_path):
    out = tmp_path / "out"
    res = video_to_flow.scan(clicks_video, out, sample=ring_sample())

    data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert res["candidates_path"] == str(out / "candidates.json")
    assert (data["width"], data["height"]) == (480, 270)
    assert data["fps"] == pytest.approx(20)
    assert data["frames"] == 120
    for c in data["candidates"]:
        for key in ("id", "frame", "time", "x", "y", "confidence", "kind", "color"):
            assert key in c
        assert c["time"] == pytest.approx(c["frame"] / 20)


def test_可另外輸出指定影格的原尺寸圖與座標格線版(clicks_video, tmp_path):
    out = tmp_path / "out"
    res = video_to_flow.scan(clicks_video, out, frames=[5, 61])

    for n in (5, 61):
        for name in (f"f{n:05d}.png", f"f{n:05d}_grid.png"):
            img = cv2.imdecode(np.fromfile(str(out / name), np.uint8), cv2.IMREAD_COLOR)
            assert img.shape[:2] == (270, 480)
    assert sorted(res["frame_files"]) == [5, 61]


def test_讀不到影片就清楚報錯(tmp_path):
    with pytest.raises(video_to_flow.ToolError, match="找不到示範影片"):
        video_to_flow.scan(tmp_path / "nope.mp4", tmp_path / "out")
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not a video at all")
    with pytest.raises(video_to_flow.ToolError, match="讀不到|沒有任何"):
        video_to_flow.scan(junk, tmp_path / "out")


def test_特效樣本格式不對就報錯(clicks_video, tmp_path):
    with pytest.raises(video_to_flow.ToolError, match="特效樣本"):
        video_to_flow.scan(clicks_video, tmp_path / "out", sample={"bgr": "yellow"})


def test_命令列掃描(clicks_video, tmp_path):
    out = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "video_to_flow"), "scan",
         str(clicks_video), "--out", str(out), "--frames", "5,61"],
        capture_output=True, timeout=300)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert (out / "candidates.json").is_file()
    assert (out / "f00005.png").is_file()
    assert "候選點擊" in proc.stdout.decode("utf-8", "replace")
