import os

import pytest

import flowfile
import video_to_flow
from vtf_synth import (center, click, demo_plan, demo_video, find, make_out,
                       snapshot)


@pytest.fixture
def demo(tmp_path):
    return demo_video(tmp_path), make_out(tmp_path)


def run(demo, engine, steps, **extra):
    video, out = demo
    return video_to_flow.assemble(demo_plan(video, out, steps=steps, **extra),
                                  engine=engine)


def saved(res):
    return flowfile.read_flow(res["flow_path"])


def overview(res):
    with open(os.path.join(res["report_path"], "總覽.md"), encoding="utf-8") as f:
        return f.read()


def refused(demo, engine, steps, match, **extra):
    _, out = demo
    before = snapshot(out)
    with pytest.raises(video_to_flow.ToolError, match=match):
        run(demo, engine, steps, **extra)
    assert snapshot(out) == before


def drag_from(name, dy=-60, **kw):
    x, y = center(name)
    return dict({"drag": [x, y + 20], "to": [x, y + 20 + dy]}, **kw)


def test_座標點擊與拖曳的確認欄位照計畫寫進存檔(demo, engine):
    x, y = center("開始")
    steps = [find("開始", head="find"),
             click(x + 30, y, confirm={"appear": "確定"}, timeout=4, on_fail="skip"),
             find("確定", head="find"),
             drag_from("確定", confirm="next", interval=0.3),
             find("下一步")]
    s = saved(run(demo, engine, steps))["steps"]
    assert (s[1]["confirm"], s[1]["confirm_target"]["template"],
            s[1]["timeout"], s[1]["on_fail"]) == ("appear", "確定", 4, "skip")
    assert (s[3]["confirm"], s[3]["interval"], s[3]["on_fail"]) == ("next", 0.3, "stop")


def test_拖曳沒寫confirm就是不確認_工具不自己補(demo, engine):
    s = saved(run(demo, engine, [find("開始", head="find"), drag_from("開始")]))["steps"]
    assert s[1]["confirm"] == "none" and "on_fail" not in s[1]


def test_流程層級的忙碌指示_帶固定矩形(demo, engine):
    from vtf_synth import box, expand
    steps = [find("開始"), find("確定", head="wait_gone"), find("下一步")]
    data = saved(run(demo, engine, steps,
                     busy={"template": "下一步", "color": True, "frame": 35}))
    assert data["busy"] == {"template": "下一步", "color": True,
                            "within": expand(box("下一步"))}


@pytest.mark.parametrize("steps, extra, match", [
    ([find("開始", head="find"), click(1, 1, confirm="maybe")], {}, "maybe"),
    ([find("開始", head="find"), click(1, 1, confirm={"appear": "沒這張"})], {},
     "確認圖"),
    ([find("開始", head="find"), click(1, 1, timeout=3)], {}, "生效確認"),
    ([find("開始")], {"busy": {"template": "沒這張"}}, "忙碌指示的範本"),
    ([find("開始")], {"busy": {"template": "開始", "within": [0, 0, 10, 10]}},
     "within"),
    ([find("開始")], {"busy": {"template": "開始", "pick": {"near": [0, 0]}}}, "near"),
    ([find("開始", busy_check=True)], {}, "busy_check.*忙碌指示"),
    ([find("開始", head="find"), click(5, 5), drag_from("開始", confirm="gone")],
     {}, "原點來自找圖"),
], ids=["confirm值", "確認圖不在清單", "沒confirm寫逾時", "忙碌指示範本不在清單",
        "忙碌指示寫within", "忙碌指示用near", "勾忙碌檢查沒忙碌指示", "原點不是找圖"])
def test_非法值被擋(demo, engine, steps, extra, match):
    refused(demo, engine, steps, match, **extra)


def test_交付報告列出忙碌指示(demo, engine):
    res = run(demo, engine, [find("開始")],
              busy={"template": "下一步", "color": True, "frame": 35})
    assert "忙碌指示：「下一步」，固定矩形" in overview(res)


def test_沒有忙碌指示時報告寫明(demo, engine):
    res = run(demo, engine, [find("開始")])
    assert "忙碌指示：沒有" in overview(res)
