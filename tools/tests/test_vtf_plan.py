"""轉換計畫用 flow.yaml 的鍵 (v2f-rules-agent-docs 03).

計畫的步驟鍵跟 flow.yaml 一樣 (開頭鍵即動作、秒、on_fail、busy_check、repeat/branch 巢狀),
只差影片像素位置與證據欄位; 舊鍵、按鍵、within、offset 一律報錯且輸出位置不多任何檔;
預設照 app 的「沒寫＝」表, 等於預設的不寫出。只打組裝入口。
"""
import os

import pytest

import flowfile
import video_to_flow
from vtf_synth import click, demo_plan, demo_video, find, make_out, snapshot


@pytest.fixture
def demo(tmp_path):
    return demo_video(tmp_path), make_out(tmp_path)


def run(demo, engine, steps, **extra):
    video, out = demo
    return video_to_flow.assemble(demo_plan(video, out, steps=steps, **extra),
                                  engine=engine)


def saved(res):
    return flowfile.read_flow(res["flow_path"])["steps"]


def yaml_text(res):
    with open(os.path.join(res["flow_path"], "flow.yaml"), encoding="utf-8") as f:
        return f.read()


def refused(demo, engine, steps, match, **extra):
    _, out = demo
    before = snapshot(out)
    with pytest.raises(video_to_flow.ToolError, match=match):
        run(demo, engine, steps, **extra)
    assert snapshot(out) == before   # 輸出位置沒有新檔


# ---------- 新鍵照 flow.yaml ----------

def test_計畫的鍵與區段寫法跟flow_yaml相同(demo, engine):
    steps = [find("開始", confirm="gone", timeout=5, on_fail="skip", busy_check=False),
             {"repeat": 2, "on_break": "break", "steps": [
                 find("確定", head="find", update_origin=False),
                 {"wait": 0.8}]},
             {"branch": [{"if": find("下一步", on_fail="skip", timeout=3),
                          "then": [click(240, 120)]}]}]
    s = saved(run(demo, engine, steps))
    assert [x["type"] for x in s] == ["find_click", "repeat_start", "find", "wait",
                                      "repeat_end", "branch_start", "find_click",
                                      "click", "branch_end"]
    assert (s[0]["confirm"], s[0]["timeout"], s[0]["on_fail"]) == ("gone", 5, "skip")
    assert s[2]["update_origin"] is False
    assert s[3]["wait"] == 0.8
    assert s[4]["on_break"] == "break"
    assert s[6]["timeout"] == 3


def test_等於預設的值不寫出_工具不帶自己的預設(demo, engine):
    steps = [find("開始", timeout=5, interval=0.3, on_fail="stop", busy_check=False,
                  update_origin=True), find("確定")]
    res = run(demo, engine, steps)
    s = saved(res)
    for x in s:
        assert (x["on_fail"], x["timeout"], x["interval"]) == ("stop", 5, 0.3)
        assert x["confirm"] == "none", "計畫沒寫 confirm＝不確認 (工具不自己推)"
    text = yaml_text(res)
    for k in ("timeout", "interval", "on_fail", "busy_check", "update_origin", "offset",
              "confirm"):
        assert k not in text


def test_時間一律秒(demo, engine):
    steps = [find("開始"), {"drag": [100, 200], "to": [300, 210], "duration": 0.8,
                            "hold": 0.2}, {"wait": 1.5}]
    s = saved(run(demo, engine, steps))
    assert (s[1]["duration"], s[1]["hold"]) == (0.8, 0.2)
    assert s[2]["wait"] == 1.5


def test_確認圖寫成confirm_appear(demo, engine):
    steps = [find("開始", confirm={"appear": "確定", "color": True}), find("確定"),
             find("下一步")]
    s = saved(run(demo, engine, steps))
    assert s[0]["confirm"] == "appear"
    assert s[0]["confirm_target"]["template"] == "確定"
    assert s[0]["confirm_target"]["color"] is True


# ---------- 舊鍵、退場寫法 ----------

@pytest.mark.parametrize("bad, match", [
    ({"type": "find_click", "template": "確定"}, "type.*開頭鍵"),
    (dict(find("確定"), colorCheck=True), "colorCheck.*color"),
    (dict(find("確定"), onNotFound="skip"), "onNotFound.*on_fail"),
    (dict(find("確定"), updateOrigin=False), "updateOrigin.*update_origin"),
    (dict(find("確定"), busyCheck=True), "busyCheck.*busy_check"),
    (dict(find("確定"), action="none"), "action.*find"),
    (dict(find("確定"), confirmTemplate="下一步"), "confirmTemplate.*appear"),
    (dict(find("確定"), timeout=3000), "秒"),
    ({"wait": 800}, "秒"),
    ({"type": "wait", "ms": 800}, "type"),
    ({"drag": [1, 2], "to": [3, 4], "holdMs": 100}, "holdMs.*hold"),
    ({"type": "loop_start", "count": 2}, "type"),
    ({"key": "esc"}, "按鍵"),
    (dict(find("確定"), appearLimitMs=500), "出現等候上限"),
    (dict(find("確定"), limit={"kind": "origin"}), "已退場"),
    (dict(find("確定"), button="right"), "左鍵"),
    (click(1, 2, clicks=2), "連點"),
    (dict(find("確定"), within=[0, 0, 10, 10]), "within.*工具"),
    (dict(find("確定"), offset=[3, 0]), "offset.*at"),
    (dict(find("確定"), confirm={"appear": "下一步", "within": [0, 0, 9, 9]}), "within"),
    ({"click": [1, 2], "mode": "abs"}, "mode"),
], ids=["type", "colorCheck", "onNotFound", "updateOrigin", "busyCheck", "action",
        "confirmTemplate", "毫秒timeout", "毫秒wait", "ms", "holdMs", "loop_start", "按鍵",
        "出現等候上限", "原點矩形", "右鍵", "連點", "within", "offset", "確認圖within",
        "座標模式"])
def test_舊鍵與退場寫法報錯且指出新鍵(demo, engine, bad, match):
    refused(demo, engine, [find("開始"), bad], match)


def test_報告的按鍵一節已刪_寫了報錯(demo, engine):
    refused(demo, engine, [find("開始")], "unexplained", report={"keys": ["按了 Esc"]})


@pytest.mark.parametrize("bad, match", [
    ({"teleport": [1, 2]}, "開頭的鍵"),
    (dict(find("開始"), threshold=0.9), "threshold"),
    (dict(find("開始"), on_fail="retry"), "on_fail"),
    (dict(find("開始"), scroll="diagonal"), "scroll"),
    (click(1, 2, scroll="vertical"), "scroll"),
    (click(1, 2, at=[1, 2]), "at 只用在找圖"),
    (click(1, 2, timeout=3), "生效確認"),
], ids=["不認得的開頭鍵", "不認得的鍵", "on_fail值", "scroll值", "點擊不能宣告捲動",
        "點擊不寫at", "沒確認不寫timeout"])
def test_步驟寫錯由app的讀檔規則擋下(demo, engine, bad, match):
    refused(demo, engine, [find("開始"), bad], match)


def test_步驟引用計畫範本清單裡沒有的範本就報錯(demo, engine):
    refused(demo, engine, [find("開始"), dict(find("確定"), find_click="不存在")],
            "不存在")


def test_確認圖不在範本清單裡也報錯(demo, engine):
    refused(demo, engine, [find("開始", confirm={"appear": "不存在"})], "不存在")


# ---------- app 執行前會擋的 (照 flowcheck) ----------

def test_點到下一步的圖出現但不找圖相連就報錯(demo, engine):
    refused(demo, engine, [find("開始", confirm="next"), click(40, 220)], "找圖步驟")


def test_最後一步要求點到下一步的圖出現也報錯(demo, engine):
    refused(demo, engine, [find("開始", confirm="next")], "找圖步驟")


def test_原點的圖離開要原點來自找圖(demo, engine):
    refused(demo, engine, [find("開始"), click(40, 220),
                           click(50, 220, confirm="gone")], "原點的圖離開")


def test_重複區段要寫次數與步驟(demo, engine):
    refused(demo, engine, [{"repeat": 2}], "steps")
    refused(demo, engine, [{"repeat": 0, "steps": [find("開始")]}], "repeat")


def test_分岔的分支開頭要是找圖(demo, engine):
    refused(demo, engine, [{"branch": [{"if": click(1, 2)}]}], "if 必須是找圖步驟")


# ---------- 報告說明 ----------

def test_交付報告收進計畫寫的分岔建議與畫面變化(demo, engine):
    notes = {"branches": ["關掉結算之後可能跳出「每日簽到」彈窗"],
             "unexplained": ["12.4s：畫面整個變暗又恢復"],
             "notes": ["使用者說這段每天都一樣"]}
    res = run(demo, engine, [find("開始"), find("確定"), find("下一步")], report=notes)
    with open(os.path.join(res["report_path"], "總覽.md"), encoding="utf-8") as f:
        text = f.read()
    for line in notes["branches"] + notes["unexplained"] + notes["notes"]:
        assert line in text
    assert "流程不支援按鍵，請改用點擊" in text
    assert "口頭補充的按鍵" not in text


# ---------- 校準對 (新流程必填) ----------

STEPS3 = [find("開始"), find("確定"), find("下一步")]


@pytest.mark.parametrize("cal, match", [
    (None, "必須有校準對"),
    ({"pair": ["開始", "沒這張"]}, "校準對的範本「沒這張」"),
    ({"pair": ["開始", "開始"]}, "兩個不同的範本名"),
    ({"pair": ["開始"]}, "兩個不同的範本名"),
    ({"pair": ["開始", "確定"], "frame": -1}, "非負整數"),
    ({"pair": ["開始", "確定"], "baseline": 100}, "pair, frame"),
])
def test_校準對沒寫或寫錯時拒絕(demo, engine, cal, match):
    refused(demo, engine, STEPS3, match, calibration=cal)
