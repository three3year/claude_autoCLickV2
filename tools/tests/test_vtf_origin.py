"""票 04 — 原點推算: 影片像素位置 → 存檔的偏移與相對座標.

計畫只寫影片像素的畫面位置; 組裝依 runner 的`原點`規則模擬執行順序推算
偏移。斷言存檔步驟 (經 app 既有讀取打開) 的偏移與座標模式。
"""
import pytest

import flowfile
import video_to_flow
from automation import flowfmt
from vtf_synth import (FRAME, VIDEO_H, VIDEO_W, center, demo_plan, demo_video,
                       find, make_profile, snapshot)

FP = {"x": 0, "y": 0, "w": 1920, "h": 1080}
# 搜尋範圍比影片大: 偏移仍是影片像素原樣 (影片與實際畫面同尺度)
REGION = [0, 0, round(VIDEO_W * 1.5), round(VIDEO_H * 1.5)]


@pytest.fixture
def demo(tmp_path):
    return demo_video(tmp_path), make_profile(tmp_path, region=REGION)


def run(demo, engine, steps):
    video, profile = demo
    return video_to_flow.assemble(demo_plan(video, profile, steps=steps),
                                  engine=engine)


def saved(res):
    return flowfile.read(res["flow_path"])["data"]["steps"]


def sc(v):
    """影片像素 → 存檔像素: 同尺度, 原樣."""
    return v


def found_center(res, name, frame=None):
    x, y, w, h = res["found"][name][FRAME[name] if frame is None else frame]
    return x + w // 2, y + h // 2


def click(x, y, **kw):
    return dict({"type": "click", "at": [x, y]}, **kw)


def test_相對座標點擊的偏移等於點擊位置減前一個找圖實際找到的中心(demo, engine):
    res = run(demo, engine, [find("開始"), click(150, 100)])

    cx, cy = found_center(res, "開始")
    s = saved(res)[1]
    assert s["type"] == "click" and s["mode"] == "prev"
    assert (s["x"], s["y"]) == (sc(150 - cx), sc(100 - cy))


def test_找圖點擊的偏移等於點擊位置減找到中心且點在中心時為0(demo, engine):
    cx0, cy0 = center("開始")
    res = run(demo, engine, [find("開始", at=[cx0 + 9, cy0 - 4]), find("確定")])

    cx, cy = found_center(res, "開始")
    s = saved(res)
    assert (s[0]["offsetX"], s[0]["offsetY"]) == (sc(cx0 + 9 - cx), sc(cy0 - 4 - cy))
    dx, dy = found_center(res, "確定")
    assert (dx, dy) == tuple(center("確定"))   # 引擎在該幀找到的就是按鈕本身
    assert (s[1]["offsetX"], s[1]["offsetY"]) == (0, 0)


def test_找圖有偏移時後續相對座標以找到中心加偏移為原點(demo, engine):
    cx0, cy0 = center("開始")
    res = run(demo, engine, [find("開始", at=[cx0 + 20, cy0]), click(200, 120)])

    s = saved(res)[1]
    assert (s["x"], s["y"]) == (sc(200 - (cx0 + 20)), sc(120 - cy0))


def test_連續兩個座標點擊第二個以第一個的落點為原點(demo, engine):
    res = run(demo, engine, [find("開始"), click(150, 100), click(170, 90)])

    s = saved(res)[2]
    assert s["mode"] == "prev"
    assert (s["x"], s["y"]) == (sc(20), sc(-10))


def test_拖曳輸出為相對座標拖曳且之後以拖曳終點為原點(demo, engine):
    steps = [find("開始"),
             {"type": "drag", "from": [100, 200], "to": [300, 210]},
             click(310, 200)]
    res = run(demo, engine, steps)

    cx, cy = found_center(res, "開始")
    d, c = saved(res)[1:]
    assert d["type"] == "drag" and d["mode"] == "prev"
    assert (d["x1"], d["y1"], d["x2"], d["y2"]) == (
        sc(100 - cx), sc(200 - cy), sc(300 - cx), sc(210 - cy))
    assert (c["x"], c["y"]) == (sc(10), sc(-10))


def test_取消更新原點的座標點擊不改變後續原點(demo, engine):
    steps = [find("開始"), click(150, 100, updateOrigin=False), click(160, 110)]
    res = run(demo, engine, steps)

    cx, cy = found_center(res, "開始")
    s = saved(res)[2]
    assert (s["x"], s["y"]) == (sc(160 - cx), sc(110 - cy))
    assert saved(res)[1]["updateOrigin"] is False


def test_取消更新原點的找圖不改變後續原點(demo, engine):
    steps = [find("開始"), click(150, 100),
             find("確定", updateOrigin=False), click(160, 110)]
    res = run(demo, engine, steps)

    s = saved(res)[3]
    assert (s["x"], s["y"]) == (sc(10), sc(10))


def test_第一個座標點擊之前沒有原點就報錯且沒有新檔(demo, engine):
    video, profile = demo
    before = snapshot(profile)
    with pytest.raises(video_to_flow.ToolError, match="定位找圖"):
        run(demo, engine, [click(150, 100), find("開始")])
    assert snapshot(profile) == before


def test_拖曳之前沒有原點也報錯(demo, engine):
    with pytest.raises(video_to_flow.ToolError, match="原點"):
        run(demo, engine, [{"type": "drag", "from": [1, 2], "to": [3, 4]}])


def test_定位找圖成為後續相對座標的原點(demo, engine):
    steps = [find("確定", action="none", at=None), click(40, 220)]
    steps[0].pop("at")
    res = run(demo, engine, steps)

    cx, cy = found_center(res, "確定")
    loc, c = saved(res)
    assert loc["action"] == "none" and loc.get("updateOrigin", True) is True
    assert (loc["offsetX"], loc["offsetY"]) == (0, 0)
    assert (c["x"], c["y"]) == (sc(40 - cx), sc(220 - cy))


def test_等待消失的找圖也以找到的位置為原點(demo, engine):
    steps = [find("確定", action="wait_gone"), click(40, 220)]
    steps[0].pop("at")
    res = run(demo, engine, steps)

    cx, cy = found_center(res, "確定")
    c = saved(res)[1]
    assert (c["x"], c["y"]) == (sc(40 - cx), sc(220 - cy))


def test_存檔中沒有任何絕對座標步驟(demo, engine):
    steps = [find("開始"), click(150, 100),
             {"type": "drag", "from": [100, 200], "to": [300, 210]},
             find("確定"), click(40, 220)]
    res = run(demo, engine, steps)

    assert flowfmt.abs_steps(saved(res)) == []


def test_重複區段內的相對座標要有區段內的原點(demo, engine):
    # 第二次起的原點是上一輪結尾, 與第一次不同 → 偏移會錯, 要求區段內先定位
    steps = [find("開始"), {"type": "loop_start", "count": 3},
             click(150, 100), find("確定"), {"type": "loop_end"}]
    with pytest.raises(video_to_flow.ToolError, match="重複區段"):
        run(demo, engine, steps)


def test_重複區段內先找圖再相對點擊可以組裝且結束後沿用區段內的原點(demo, engine):
    steps = [{"type": "loop_start", "count": 3}, find("開始"), click(150, 100),
             {"type": "loop_end"}, click(160, 100)]
    res = run(demo, engine, steps)

    s = saved(res)
    assert [x["type"] for x in s] == ["loop_start", "find_click", "click",
                                      "loop_end", "click"]
    assert (s[4]["x"], s[4]["y"]) == (sc(10), sc(0))
