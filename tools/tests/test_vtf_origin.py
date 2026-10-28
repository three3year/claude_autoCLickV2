import pytest

import flowfile
import video_to_flow
from automation import flowfmt
from vtf_synth import (FRAME, VIDEO_H, VIDEO_W, center, click, demo_plan,
                       demo_video, find, make_out, snapshot)


@pytest.fixture
def demo(tmp_path):
    return demo_video(tmp_path), make_out(tmp_path)


def run(demo, engine, steps):
    video, profile = demo
    return video_to_flow.assemble(demo_plan(video, profile, steps=steps),
                                  engine=engine)


def saved(res):
    return flowfile.read_flow(res["flow_path"])["steps"]


def sc(v):
    return v


def found_center(res, name, frame=None):
    x, y, w, h = res["found"][name][FRAME[name] if frame is None else frame]
    return x + w // 2, y + h // 2


def test_相對座標點擊的偏移等於點擊位置減前一個找圖實際找到的中心(demo, engine):
    res = run(demo, engine, [find("開始"), click(150, 100)])

    cx, cy = found_center(res, "開始")
    s = saved(res)[1]
    assert s["type"] == "click"
    assert tuple(s["click"]) == (sc(150 - cx), sc(100 - cy))


def test_找圖點擊的偏移等於點擊位置減找到中心且點在中心時為0(demo, engine):
    cx0, cy0 = center("開始")
    res = run(demo, engine, [find("開始", at=[cx0 + 9, cy0 - 4]), find("確定")])

    cx, cy = found_center(res, "開始")
    s = saved(res)
    assert tuple(s[0]["offset"]) == (sc(cx0 + 9 - cx), sc(cy0 - 4 - cy))
    dx, dy = found_center(res, "確定")
    assert (dx, dy) == tuple(center("確定"))
    assert tuple(s[1]["offset"]) == (0, 0)


def test_找圖有偏移時後續相對座標以找到中心加偏移為原點(demo, engine):
    cx0, cy0 = center("開始")
    res = run(demo, engine, [find("開始", at=[cx0 + 20, cy0]), click(200, 120)])

    s = saved(res)[1]
    assert tuple(s["click"]) == (sc(200 - (cx0 + 20)), sc(120 - cy0))


def test_連續兩個座標點擊第二個以第一個的落點為原點(demo, engine):
    res = run(demo, engine, [find("開始"), click(150, 100), click(170, 90)])

    s = saved(res)[2]
    assert tuple(s["click"]) == (sc(20), sc(-10))


def test_拖曳輸出為相對座標拖曳且之後以拖曳終點為原點(demo, engine):
    steps = [find("開始"),
             {"drag": [100, 200], "to": [300, 210]},
             click(310, 200)]
    res = run(demo, engine, steps)

    cx, cy = found_center(res, "開始")
    d, c = saved(res)[1:]
    assert d["type"] == "drag"
    assert (*d["drag"], *d["to"]) == (
        sc(100 - cx), sc(200 - cy), sc(300 - cx), sc(210 - cy))
    assert tuple(c["click"]) == (sc(10), sc(-10))


def test_取消更新原點的座標點擊不改變後續原點(demo, engine):
    steps = [find("開始"), click(150, 100, update_origin=False), click(160, 110)]
    res = run(demo, engine, steps)

    cx, cy = found_center(res, "開始")
    s = saved(res)[2]
    assert tuple(s["click"]) == (sc(160 - cx), sc(110 - cy))
    assert saved(res)[1]["update_origin"] is False


def test_取消更新原點的找圖不改變後續原點(demo, engine):
    steps = [find("開始"), click(150, 100),
             find("確定", update_origin=False), click(160, 110)]
    res = run(demo, engine, steps)

    s = saved(res)[3]
    assert tuple(s["click"]) == (sc(10), sc(10))


def test_第一個座標點擊之前沒有原點就報錯且沒有新檔(demo, engine):
    video, profile = demo
    before = snapshot(profile)
    with pytest.raises(video_to_flow.ToolError, match="定位找圖"):
        run(demo, engine, [click(150, 100), find("開始")])
    assert snapshot(profile) == before


def test_拖曳之前沒有原點也報錯(demo, engine):
    with pytest.raises(video_to_flow.ToolError, match="原點"):
        run(demo, engine, [{"drag": [1, 2], "to": [3, 4]}])


def test_定位找圖成為後續相對座標的原點(demo, engine):
    steps = [find("確定", head="find"), click(40, 220)]
    steps[0].pop("at")
    res = run(demo, engine, steps)

    cx, cy = found_center(res, "確定")
    loc, c = saved(res)
    assert loc["type"] == "find" and loc.get("update_origin", True) is True
    assert tuple(loc["offset"]) == (0, 0)
    assert tuple(c["click"]) == (sc(40 - cx), sc(220 - cy))


def test_等待消失的找圖也以找到的位置為原點(demo, engine):
    steps = [find("確定", head="wait_gone"), click(40, 220)]
    steps[0].pop("at")
    res = run(demo, engine, steps)

    cx, cy = found_center(res, "確定")
    c = saved(res)[1]
    assert tuple(c["click"]) == (sc(40 - cx), sc(220 - cy))


def test_存檔的座標點擊與拖曳不帶座標模式(demo, engine):
    """相對座標是唯一的座標模式 (絕對座標已退場, ADR 0014)."""
    steps = [find("開始"), click(150, 100),
             {"drag": [100, 200], "to": [300, 210]},
             find("確定"), click(40, 220)]
    res = run(demo, engine, steps)

    assert all("mode" not in s for s in saved(res))


def test_重複區段內的相對座標要有區段內的原點(demo, engine):
    steps = [find("開始"), {"repeat": 3, "steps": [click(150, 100), find("確定")]}]
    with pytest.raises(video_to_flow.ToolError, match="重複區段"):
        run(demo, engine, steps)


def test_重複區段內先找圖再相對點擊可以組裝且結束後沿用區段內的原點(demo, engine):
    steps = [{"repeat": 3, "steps": [find("開始"), click(150, 100)]}, click(160, 100)]
    res = run(demo, engine, steps)

    s = saved(res)
    assert [x["type"] for x in s] == ["repeat_start", "find_click", "click",
                                      "repeat_end", "click"]
    assert tuple(s[4]["click"]) == (sc(10), sc(0))
