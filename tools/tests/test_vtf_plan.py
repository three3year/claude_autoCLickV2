"""票 05 — 預設補值、結構檢查與報告內容.

只打組裝入口; 斷言存檔步驟的欄位、拒絕時的訊息與 profile 檔案狀態、報告文字。
"""
import pytest

import flowfile
import video_to_flow
from vtf_synth import (VIDEO_H, VIDEO_W, demo_plan, demo_video, find,
                       make_profile, snapshot)

FP = {"x": 0, "y": 0, "w": 1920, "h": 1080}
REGION = [0, 0, VIDEO_W, VIDEO_H]


@pytest.fixture
def demo(tmp_path):
    return demo_video(tmp_path), make_profile(tmp_path, region=REGION)


def run(demo, engine, steps, **extra):
    video, profile = demo
    return video_to_flow.assemble(demo_plan(video, profile, steps=steps, **extra),
                                  engine=engine, fingerprint=FP)


def saved(res):
    return flowfile.read(res["flow_path"])["data"]["steps"]


def refused(demo, engine, steps, match, **extra):
    _, profile = demo
    before = snapshot(profile)
    with pytest.raises(video_to_flow.ToolError, match=match):
        run(demo, engine, steps, **extra)
    assert snapshot(profile) == before   # 流程目錄 (與整個 profile) 沒有新檔


# ---------- 預設補值 ----------

def test_找圖點擊下一步是找圖且未指定確認時補點到下一步的圖出現(demo, engine):
    s = saved(run(demo, engine, [find("開始"), find("確定"), find("下一步")]))
    assert [x["confirm"] for x in s[:2]] == ["next", "next"]


def test_找圖點擊下一步不是找圖或已是最後一步時補目標圖消失(demo, engine):
    steps = [find("開始"), {"type": "click", "at": [40, 220]},
             {"type": "loop_start", "count": 2}, find("確定"), {"type": "loop_end"},
             find("下一步")]
    s = saved(run(demo, engine, steps))
    assert s[0]["confirm"] == "gone"      # 下一步是座標點擊
    assert s[3]["confirm"] == "gone"      # 下一步是區段標記
    assert s[5]["confirm"] == "gone"      # 最後一步


def test_不點擊的找圖不補點擊後確認(demo, engine):
    steps = [find("開始", action="none"), find("確定", action="wait_gone"),
             find("下一步")]
    s = saved(run(demo, engine, steps))
    assert [x["confirm"] for x in s[:2]] == ["none", "none"]


def test_找不到時預設停止且逾時預設10秒(demo, engine):
    s = saved(run(demo, engine, [find("開始"), find("確定")]))
    for x in s:
        assert x["onNotFound"] == "stop"
        assert x["timeout"] == 10
        assert x["action"] == "click"
        assert (x["button"], x["clicks"], x["interval"]) == ("left", 1, 0.5)
        assert x["updateOrigin"] is True


def test_計畫有指定時照計畫(demo, engine):
    steps = [find("開始", confirm="gone", onNotFound="skip", timeout=30),
             find("確定", confirm="appear", confirmTemplate="下一步"),
             find("下一步", confirm="none", button="right", clicks=2)]
    s = saved(run(demo, engine, steps))
    assert (s[0]["confirm"], s[0]["onNotFound"], s[0]["timeout"]) == ("gone", "skip", 30)
    assert (s[1]["confirm"], s[1]["confirmTemplate"]) == ("appear", "下一步")
    assert (s[2]["confirm"], s[2]["button"], s[2]["clicks"]) == ("none", "right", 2)


def test_座標點擊與拖曳補齊編輯器的預設欄位(demo, engine):
    steps = [find("開始"), {"type": "click", "at": [40, 220]},
             {"type": "drag", "from": [40, 220], "to": [200, 220]},
             {"type": "key", "keys": "esc"}, {"type": "wait", "ms": 800}]
    s = saved(run(demo, engine, steps))
    assert (s[1]["button"], s[1]["clicks"], s[1]["updateOrigin"]) == ("left", 1, True)
    assert (s[2]["button"], s[2]["ms"], s[2]["holdMs"]) == ("left", 500, 500)
    assert s[3] == {"type": "key", "keys": "esc"}
    assert s[4] == {"type": "wait", "ms": 800}


# ---------- 結構檢查 ----------

def test_明確要求點到下一步的圖出現但不找圖相連就報錯(demo, engine):
    steps = [find("開始", confirm="next"), {"type": "click", "at": [40, 220]}]
    refused(demo, engine, steps, "找圖相連")


def test_最後一步要求點到下一步的圖出現也報錯(demo, engine):
    refused(demo, engine, [find("開始", confirm="next")], "找圖相連")


@pytest.mark.parametrize("steps", [
    [{"type": "loop_start", "count": 2}, find("開始")],
    [find("開始"), {"type": "loop_end"}],
    [{"type": "branch_start"}, find("開始"), {"type": "loop_end"}],
    [{"type": "loop_start", "count": 2}, {"type": "branch_start"}, find("開始"),
     {"type": "loop_end"}, {"type": "branch_end"}],
], ids=["缺結束", "缺開始", "種類不配", "交錯"])
def test_區段標記不成對或交錯就報錯(demo, engine, steps):
    refused(demo, engine, steps, "區段|標記")


def test_步驟引用計畫範本清單裡沒有的範本就報錯(demo, engine):
    refused(demo, engine, [find("開始"), dict(find("確定"), template="不存在")],
            "不存在")


def test_確認圖不在範本清單裡也報錯(demo, engine):
    refused(demo, engine,
            [find("開始", confirm="appear", confirmTemplate="不存在")], "不存在")


@pytest.mark.parametrize("bad, match", [
    ({"type": "teleport"}, "teleport"),
    (dict(find("開始"), threshold=0.9), "threshold"),
    (dict(find("開始"), offsetX=3), "offsetX"),
    ({"type": "click", "at": [1, 2], "mode": "abs"}, "mode"),
    (dict(find("開始"), action="hover"), "hover"),
    (dict(find("開始"), onNotFound="retry"), "retry"),
], ids=["步驟種類", "已退場的欄位", "偏移欄位", "座標模式", "action值", "onNotFound值"])
def test_步驟種類或欄位不屬於流程既有詞彙就報錯(demo, engine, bad, match):
    refused(demo, engine, [find("開始"), bad], match)


def test_重複開始要寫次數(demo, engine):
    refused(demo, engine, [{"type": "loop_start"}, find("開始"), {"type": "loop_end"}],
            "count")


# ---------- 報告 ----------

def test_交付報告收進計畫寫的分岔建議畫面變化與口頭補充的按鍵(demo, engine):
    notes = {"branches": ["步驟 2 之後可能跳出「每日簽到」彈窗"],
             "unexplained": ["12.4s：畫面整個變暗又恢復"],
             "keys": ["步驟 3：使用者說這裡按了 Esc"]}
    steps = [find("開始"), find("確定"), {"type": "key", "keys": "esc"},
             find("下一步")]
    res = run(demo, engine, steps, report=notes)
    text = open(res["report_path"], encoding="utf-8").read()
    for line in notes["branches"] + notes["unexplained"] + notes["keys"]:
        assert line in text
    assert "分岔建議" in text and "按鍵" in text


def test_交付報告沒有說明時寫無(demo, engine):
    res = run(demo, engine, [find("開始")])
    text = open(res["report_path"], encoding="utf-8").read()
    assert "分岔建議" in text


def test_交付報告列出流程裡的按鍵步驟即使計畫沒寫說明(demo, engine):
    steps = [find("開始"), {"type": "key", "keys": "esc"}, find("確定")]
    res = run(demo, engine, steps)
    text = open(res["report_path"], encoding="utf-8").read()
    section = text.split("## 口頭補充的按鍵")[1].split("##")[0]
    assert "步驟 2" in section and "esc" in section


@pytest.mark.parametrize("extra", [{"confirm": "gone"},
                                   {"confirm": "appear", "confirmTemplate": "確定"}])
def test_不點擊的找圖寫了點擊後確認就報錯(demo, engine, extra):
    refused(demo, engine, [find("開始", action="none", **extra), find("確定")],
            "confirm")
