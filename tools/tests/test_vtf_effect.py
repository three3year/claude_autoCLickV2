"""影片轉流程支援`生效確認`與`忙碌指示` (effect-confirm 票 05, ADR 0008).

計畫格式接受座標點擊/拖曳的確認欄位、流程層級的補做間隔與忙碌指示、等待消失的
出現等候上限; 拖曳的原點來自找圖時預設`原點的圖離開`; 交付報告列出忙碌指示。
只打組裝入口; 斷言存檔內容、拒絕訊息、報告文字。
"""
import pytest

import flowfile
import video_to_flow
from vtf_synth import (VIDEO_H, VIDEO_W, center, demo_plan, demo_video, find,
                       make_profile, snapshot)

REGION = [0, 0, VIDEO_W, VIDEO_H]


@pytest.fixture
def demo(tmp_path):
    return demo_video(tmp_path), make_profile(tmp_path, region=REGION)


def run(demo, engine, steps, **extra):
    video, profile = demo
    return video_to_flow.assemble(demo_plan(video, profile, steps=steps, **extra),
                                  engine=engine)


def saved(res):
    return flowfile.read(res["flow_path"])["data"]


def refused(demo, engine, steps, match, **extra):
    _, profile = demo
    before = snapshot(profile)
    with pytest.raises(video_to_flow.ToolError, match=match):
        run(demo, engine, steps, **extra)
    assert snapshot(profile) == before


def drag_from(name, dy=-60, **kw):
    x, y = center(name)
    return dict({"type": "drag", "from": [x, y + 20], "to": [x, y + 20 + dy]},
                **kw)


# ---------- 白名單 ----------

def test_座標點擊與拖曳的確認欄位照計畫寫進存檔(demo, engine):
    x, y = center("開始")
    steps = [find("開始", action="none"),
             {"type": "click", "at": [x + 30, y], "confirm": "appear",
              "confirmTemplate": "確定", "timeout": 4, "onNotFound": "skip"},
             find("確定", action="none"),
             drag_from("確定", confirm="next", interval=0.3),
             find("下一步")]
    s = saved(run(demo, engine, steps))["steps"]
    assert (s[1]["confirm"], s[1]["confirm_target"]["template"],
            s[1]["timeout"], s[1]["on_fail"]) == ("appear", "確定", 4, "skip")
    assert (s[3]["confirm"], s[3]["interval"], s[3]["on_fail"]) == (
        "next", 0.3, "stop")


def test_流程層級的忙碌指示(demo, engine):
    steps = [find("開始"), find("確定", action="wait_gone"), find("下一步")]
    data = saved(run(demo, engine, steps,
                     busyTarget={"template": "下一步", "colorCheck": True}))
    assert flowfile.busy_target(data) == {"template": "下一步", "color": True}
    assert "retryIntervalMs" not in data, "補做間隔是固定行為, 不進存檔"


@pytest.mark.parametrize("steps, extra, match", [
    ([find("開始", action="none"), {"type": "click", "at": [1, 1],
                                   "confirm": "maybe"}], {}, "maybe"),
    ([find("開始", action="none"), {"type": "click", "at": [1, 1],
                                   "confirm": "appear"}], {}, "確認圖"),
    ([find("開始", action="none"), {"type": "click", "at": [1, 1],
                                   "timeout": 3}], {}, "生效確認的設定"),
    ([find("開始")], {"busyTarget": {"template": "沒這張"}}, "忙碌指示的範本"),
    ([find("開始")], {"busyTarget": {"template": "開始", "limit": {
        "kind": "origin", "rect": [0, 0, 10, 10]}}}, "限定範圍"),
    ([find("開始")], {"retryIntervalMs": 1000}, "補做間隔已退場"),
    ([find("開始", action="none"), {"type": "click", "at": [5, 5]},
      {"type": "drag", "from": [5, 5], "to": [5, 50], "confirm": "gone"}],
     {}, "原點來自找圖"),
], ids=["confirm值", "appear沒確認圖", "沒confirm寫逾時",
        "忙碌指示範本不在清單", "忙碌指示寫限定範圍", "補做間隔已退場", "原點不是找圖"])
def test_非法值仍被擋(demo, engine, steps, extra, match):
    refused(demo, engine, steps, match, **extra)


# ---------- 預設值 ----------

def test_拖曳的原點來自找圖時預設原點的圖離開_找不到時停止(demo, engine):
    s = saved(run(demo, engine, [find("開始", action="none"),
                                 drag_from("開始")]))["steps"]
    assert (s[1]["confirm"], s[1]["on_fail"], s[1]["timeout"]) == (
        "gone", "stop", 10)


def test_原點不是找圖時拖曳不設確認(demo, engine):
    x, y = center("開始")
    s = saved(run(demo, engine, [find("開始", action="none"),
                                 {"type": "click", "at": [x, y + 40]},
                                 drag_from("開始")]))["steps"]
    assert s[2]["confirm"] == "none" and "on_fail" not in s[2]


# ---------- 交付報告 ----------

def test_交付報告列出忙碌指示(demo, engine):
    res = run(demo, engine, [find("開始")],
              busyTarget={"template": "下一步", "colorCheck": True})
    text = open(res["report_path"], encoding="utf-8").read()
    assert "忙碌指示：「下一步」〔比色〕" in text


def test_沒有忙碌指示時報告寫明(demo, engine):
    res = run(demo, engine, [find("開始")])
    text = open(res["report_path"], encoding="utf-8").read()
    assert "忙碌指示：沒有（補做只看固定的補做間隔）" in text
