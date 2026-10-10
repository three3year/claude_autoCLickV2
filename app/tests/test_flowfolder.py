"""流程資料夾 (flow.yaml＋templates/) 的讀寫 (flow-folder-format 票 07).

照 test_flowfile 的手法: 用暫存資料夾真的讀寫檔案, 斷言檔案內容與讀回來的流程
(記憶體模型), 不看內部函式。定案樣本 (晚_簡中, 票 02) 就是排版的規格。
"""
import os

import pytest

from harness import (branch_end, branch_or, branch_start, click, drag, find,
                     repeat, repeat_end, tgt, wait)

import flowfile
from automation import flowdefaults

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "..", ".scratch",
                      "project-cleanup", "prototypes", "flow-yaml", "out",
                      "A_巢狀_一步一行.yaml")


def sample_text():
    """定案樣本去掉開頭那行原型註解."""
    with open(SAMPLE, encoding="utf-8") as f:
        return f.read().split("\n", 1)[1]


def flow(steps, **extra):
    f = flowfile.new_flow()
    f["steps"] = steps
    f.update(extra)
    return f


def parse_error(text):
    with pytest.raises(flowfile.FlowError) as e:
        flowfile.parse_flow(text)
    return str(e.value)


# ---------- 往返 ----------

def test_定案樣本讀進來再寫回_文字完全相同():
    text = sample_text()
    assert flowfile.dump_flow(flowfile.parse_flow(text)) == text


def test_記憶體流程寫出再讀回_得到相同的流程(tmp_path):
    cal = {"pair": ["左上", "右下"], "baseline": 1719.2,
           "fallback": {"pair": ["圖示", "關閉"], "baseline": 1650.0, "offset": [33, 61]}}
    steps = [find("公告", target={"within": [1, 2, 30, 40]}, confirm="gone",
                  timeout=2, on_fail="skip", busy_check=True),
             find("鈴", confirm="appear",
                  confirm_target=tgt("待辦", within=[0, 1, 9, 9], color=True)),
             repeat(3), branch_start(),
             find("收獲", on_fail="skip", timeout=3),
             branch_or(), find("交付", type="find", update_origin=False),
             click(5, 5), branch_end(on_break="break"), repeat_end(),
             find("卡", type="wait_gone", target={"pick": {"top": 2}}),
             click(10, -20, confirm="next"), find("下", target={"pick": {"near": [3, 4]}}),
             drag(1, 2, 3, 4, confirm="gone", busy_check=True, duration=0.3),
             wait(0.5)]
    data = flow(steps, run=3, scan_region=[0, 0, 800, 600], calibration=cal,
                busy=tgt("忙碌", within=[5, 5, 50, 20]),
                template_pos={"公告": [1, 2], "左上": [0, 0]},
                engine={"scale_range": [0.6, 1.5]})
    flowfile.write_flow(tmp_path, data, {})
    back = flowfile.read_flow(tmp_path)
    assert back == data


def test_讀進來補齊預設_寫出去等於預設的不寫(tmp_path):
    text = ("format: 1\nsteps:\n  - {find_click: a}    # 1\n"
            "  - {click: [1, 2]}    # 2\n  - {drag: [0, 0], to: [0, 9]}    # 3\n")
    f = flowfile.parse_flow(text)
    a, c, d = f["steps"]
    assert (a["on_fail"], a["timeout"], a["interval"], a["offset"]) == ("stop", 10, 0.3,
                                                                        [0, 0])
    assert c["update_origin"] is True and "timeout" not in c
    assert (d["duration"], d["hold"]) == (0.5, 0.5)
    assert f["run"] == 1 and f["scan_region"] is None and f["engine"] == {}
    assert flowfile.dump_flow(f) == text


def test_步驟編號連區段標記也算一號():
    text = flowfile.dump_flow(flow([repeat(2), find("a", on_fail="skip"),
                                    repeat_end(), click(1, 1)]))
    assert "- repeat: 2    # 1" in text
    assert "- {find_click: a, on_fail: skip}    # 2" in text
    assert "- {click: [1, 1]}    # 4" in text, "repeat 的結尾標記佔了 3 號"


def test_engine段原樣往返():
    f = flowfile.parse_flow("format: 1\nengine: {scale_range: [0.6, 1.5], "
                            "match_threshold: 0.65}\nsteps: []\n")
    assert f["engine"] == {"scale_range": [0.6, 1.5], "match_threshold": 0.65}
    assert "engine: {scale_range: [0.6, 1.5], match_threshold: 0.65}" in \
        flowfile.dump_flow(f)


def test_拍攝位置只寫被引用的範本():
    f = flow([find("a")], template_pos={"a": [1, 2], "沒人用": [3, 4]})
    text = flowfile.dump_flow(f)
    assert "a: [1, 2]" in text and "沒人用" not in text


# ---------- 讀檔報錯 ----------

def test_yaml語法錯_指出第幾行():
    msg = parse_error("format: 1\nsteps:\n  - {find_click: a]\n  - {wait: 1}\n")
    assert "第 3 行" in msg, msg


@pytest.mark.parametrize("text, words", [
    ("steps: []\n", ["缺 format"]),
    ("format: 2\nsteps: []\n", ["format", "2"]),
    ("format: 1\nfoo: 1\nsteps: []\n", ["頂層", "foo"]),
    ("format: 1\nengine: {scale_rang: [1, 2]}\nsteps: []\n", ["engine", "scale_rang"]),
    ("format: 1\nsteps:\n  - {find_click: a, timout: 3}\n", ["步驟 1", "timout"]),
    ("format: 1\nsteps:\n  - {wait: 1}\n  - {find: a, within: [1, 2]}\n",
     ["步驟 2", "within"]),
    ("format: 1\nsteps:\n  - {find_click: a, on_fail: retry}\n", ["步驟 1", "on_fail"]),
    ("format: 1\nsteps:\n  - {find: a, confirm: gone}\n", ["步驟 1", "confirm"]),
    ("format: 1\nsteps:\n  - {click: [1, 2], timeout: 3}\n", ["步驟 1", "timeout",
                                                              "生效確認"]),
    ("format: 1\nsteps:\n  - {click: [1, 2], busy_check: yes please}\n",
     ["步驟 1", "busy_check"]),
    ("format: 1\nsteps:\n  - {find_click: a, pick: {kind: top, n: 2}}\n",
     ["步驟 1", "pick"]),
    ("format: 1\nsteps:\n  - {find_click: a, click: [1, 2]}\n", ["步驟 1"]),
    ("format: 1\nsteps:\n  - repeat: 3\n", ["步驟 1", "區段不完整"]),
    ("format: 1\nsteps:\n  - {wait: 1}\n  - branch: []\n", ["步驟 2", "區段不完整"]),
    ("format: 1\nsteps:\n  - branch:\n      - if: {click: [1, 2]}\n",
     ["步驟 2", "if", "找圖"]),
    ("format: 1\nsteps:\n  - branch:\n      - if: {find: a}\n      - then: []\n",
     ["步驟 4", "if"]),
], ids=["缺format", "format不是1", "頂層未知鍵", "engine未知鍵", "步驟未知鍵",
        "找圖目標型別錯", "列舉值錯", "不點擊的找圖寫確認", "沒確認寫逾時", "布林型別錯",
        "舊的挑選規則寫法", "兩個開頭的鍵", "repeat沒有steps", "branch沒有分支",
        "if不是找圖", "分支沒有if"])
def test_寫錯就報錯並指出哪一步哪個鍵(text, words):
    msg = parse_error(text)
    for w in words:
        assert w in msg, (w, msg)


def test_範本名不合法_讀檔與寫檔都擋下(tmp_path):
    for bad in ("a/b", "a:b", " a", "a ", "a.", 'a"b', "a|b", "a?b", "a*b", "a<b", ""):
        assert flowfile.template_name_problem(bad), bad
    assert flowfile.template_name_problem("主画面设置钮") is None
    assert "步驟 1" in parse_error("format: 1\nsteps:\n  - {find_click: 'a/b'}\n")
    with pytest.raises(flowfile.FlowError):
        flowfile.write_flow(tmp_path, flow([find("a?")]), {})
    assert not (tmp_path / "flow.yaml").exists()


def test_讀檔報錯時沒有流程資料_呼叫端保留原本的流程(tmp_path):
    (tmp_path / "flow.yaml").write_text("format: 9\nsteps: []\n", encoding="utf-8")
    with pytest.raises(flowfile.FlowError):
        flowfile.read_flow(tmp_path)


def test_沒有flow_yaml_明確報錯(tmp_path):
    with pytest.raises(flowfile.FlowError) as e:
        flowfile.read_flow(tmp_path)
    assert "flow.yaml" in str(e.value)


# ---------- 寫檔: templates/ 等於引用集合 ----------

def test_寫檔_templates只留被引用的範本_缺圖回報(tmp_path):
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "舊的.png").write_bytes(b"OLD")
    (tmp_path / "templates" / "a.png").write_bytes(b"A0")
    cal = {"pair": ["左", "右"], "baseline": 100.0}
    data = flow([find("a"), find("b", confirm="appear", confirm_target=tgt("c"))],
                calibration=cal, busy=tgt("忙"))
    missing = flowfile.write_flow(tmp_path, data, {"b": b"B", "左": b"L", "右": b"R",
                                                   "沒人用": b"U"})
    names = sorted(os.listdir(tmp_path / "templates"))
    assert names == sorted(["a.png", "b.png", "左.png", "右.png"])
    assert (tmp_path / "templates" / "a.png").read_bytes() == b"A0", "已在的圖不動"
    assert set(missing) == {"忙", "c"}


def test_寫檔_圖檔路徑互換也不會互相蓋掉(tmp_path):
    t = tmp_path / "templates"
    t.mkdir()
    (t / "a.png").write_bytes(b"AAA")
    (t / "b.png").write_bytes(b"BBB")
    flowfile.write_flow(tmp_path, flow([find("a"), find("b")]),
                        {"a": str(t / "b.png"), "b": str(t / "a.png")})
    assert (t / "a.png").read_bytes() == b"BBB" and (t / "b.png").read_bytes() == b"AAA"


def test_寫檔_不留暫存檔_重寫整份(tmp_path):
    flowfile.write_flow(tmp_path, flow([find("a")]), {"a": b"A"})
    (tmp_path / "flow.yaml").write_text("# 手寫註解\n" + (tmp_path / "flow.yaml")
                                        .read_text(encoding="utf-8"), encoding="utf-8")
    flowfile.write_flow(tmp_path, flow([find("a"), wait(1)]), {})
    text = (tmp_path / "flow.yaml").read_text(encoding="utf-8")
    assert "手寫註解" not in text and "{wait: 1}" in text
    assert sorted(os.listdir(tmp_path)) == ["flow.yaml", "templates"]


def test_開檔列出缺圖(tmp_path):
    flowfile.write_flow(tmp_path, flow([find("a"), find("b")]), {"a": b"A"})
    f = flowfile.read_flow(tmp_path)
    assert flowfile.missing_templates(tmp_path, f) == ["b"]


def test_完整步驟與預設表一致():
    """讀進來的每一步都是「沒寫＝」表補齊後的完整步驟."""
    f = flowfile.parse_flow(sample_text())
    assert all(s == flowdefaults.complete(s) for s in f["steps"])
