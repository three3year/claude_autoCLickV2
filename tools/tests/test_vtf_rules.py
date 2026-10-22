"""影片轉流程的產出規則 (v2f-rules-agent-docs 04–06): 固定矩形、忙碌檢查、交付報告資料夾.

只打組裝入口 (與報告的區段切法這個純函式); 斷言經 app 讀回的流程、結果裡的清單、
報告資料夾的檔案與文字。
"""
import os
import re

import pytest

import flowfile
import video_to_flow
from video_to_flow import report as report_mod
from video_to_flow import verify as verify_mod
from vtf_synth import (BUTTONS, POS, VIDEO_H, box, center, click, demo_plan,
                       demo_video, expand, find, make_button, make_out, screen,
                       timeline, title_box, write_video)


@pytest.fixture
def demo(tmp_path):
    return demo_video(tmp_path), make_out(tmp_path)


def run(demo, engine, steps, **extra):
    video, out = demo
    return video_to_flow.assemble(demo_plan(video, out, steps=steps, **extra),
                                  engine=engine)


def saved(res):
    return flowfile.read_flow(res["flow_path"])


def report_files(res):
    d = res["report_path"]
    return {fn: open(os.path.join(d, fn), encoding="utf-8").read()
            for fn in sorted(os.listdir(d))}


def found(res, name, frame):
    return res["found"][name][frame]


# ================= 04 固定矩形 =================

def test_每個找圖目標的固定矩形是挑中的框外推50_中心不變(demo, engine):
    res = run(demo, engine, [find("開始"), find("確定"), find("下一步")])
    for s, (name, frame) in zip(saved(res)["steps"], (("開始", 5), ("確定", 20),
                                                       ("下一步", 35))):
        w = s["target"]["within"]
        assert w == expand(found(res, name, frame))
        bx, by, bw, bh = found(res, name, frame)
        assert (w[2], w[3]) == (2 * bw, 2 * bh)


def moving_video(tmp_path):
    """「開始」先在 (60, 40), 第 10 幀起移到 (200, 160)."""
    btn = BUTTONS["開始"]
    frames = timeline((screen([(btn, 60, 40)], title=True), 10),
                      (screen([(btn, 200, 160)], title=True), 10))
    return write_video(tmp_path / "moving.mp4", frames)


def test_同一張範本在不同步驟各用各的幀算_不取聯集(tmp_path, engine):
    video = moving_video(tmp_path)
    w, h = box("開始")[2:]
    later = [200 + w // 2, 160 + h // 2]
    templates = {"開始": {"frame": 5, "box": box("開始"),
                          "present": [{"frame": 15, "at": later}]}}
    steps = [find("開始", head="find"), find("開始", frame=15, at=later)]
    res = video_to_flow.assemble(demo_plan(video, make_out(tmp_path), steps=steps,
                                           templates=templates), engine=engine)
    a, b = (s["target"]["within"] for s in saved(res)["steps"])
    assert a == expand(found(res, "開始", 5))
    assert b == expand(found(res, "開始", 15))
    assert a != b


def test_宣告捲動軸_那一軸到影片兩端_另一軸照50(demo, engine):
    res = run(demo, engine, [find("開始", scroll="vertical"),
                             find("確定", scroll="horizontal")])
    a, b = (s["target"]["within"] for s in saved(res)["steps"])
    assert a == expand(found(res, "開始", 5), scroll="vertical")
    assert a[3] == VIDEO_H
    assert b == expand(found(res, "確定", 20), scroll="horizontal")


def test_框超出畫面裁到影片邊_裁過的一側不標待重拍(demo, engine):
    # 「圖示」在 (418, 100) 48×36: 右邊外推 24px 會超出 480 寬的影片
    res = run(demo, engine, [{"find_click": "圖示", "frame": 5,
                              "at": list(center_of(title_box("圖示")))}, find("確定")])
    w = saved(res)["steps"][0]["target"]["within"]
    assert w == expand(found(res, "圖示", 5))
    from vtf_synth import ANCHOR
    assert w[0] + ANCHOR[0] + w[2] == 480, "裁到影片右緣"
    assert "圖示" not in res["retake"]


def center_of(b):
    return b[0] + b[2] // 2, b[1] + b[3] // 2


def test_確認圖與等待消失也有固定矩形(demo, engine):
    steps = [find("開始", confirm={"appear": "確定"}), find("確定", head="wait_gone"),
             find("下一步")]
    res = run(demo, engine, steps)
    s = saved(res)["steps"]
    assert s[0]["confirm_target"]["within"] == expand(found(res, "確定", 20))
    assert s[1]["target"]["within"] == expand(found(res, "確定", 20))


def test_同段有拖曳但沒宣告捲動軸的找圖列進待確認(demo, engine):
    steps = [find("開始", head="find"), {"drag": [84, 100], "to": [84, 40]},
             find("確定", scroll="vertical"), find("下一步")]
    res = run(demo, engine, steps)
    texts = [t for _, t in res["scroll_confirm"]]
    assert texts == ["找圖（不點）「開始」", "找圖點擊「下一步」"]
    assert "找圖點擊「下一步」" in report_files(res)["總覽.md"]


def test_沒有拖曳的段落不列捲動待確認(demo, engine):
    res = run(demo, engine, [find("開始"), find("確定")])
    assert res["scroll_confirm"] == []


def test_矩形餘裕沒過是工具錯誤(demo, engine, monkeypatch):
    real = verify_mod.fixed_rect

    def tight(box_, size, anchor, *rule):
        rect, _ = real(box_, size, anchor, *rule)
        return [rect[0] + rect[2] // 4, rect[1], rect[2] // 2, rect[3]], set()
    monkeypatch.setattr(verify_mod, "fixed_rect", tight)
    with pytest.raises(video_to_flow.ToolError, match="工具錯誤.*矩形餘裕"):
        run(demo, engine, [find("開始")])


# ================= 05 忙碌檢查 =================

BUSY = make_button(w=60, h=24, seed=31)
BUSY_POS = (150, 200)


def busy_video(tmp_path):
    """開始 (0–9) → 點了之後忙碌指示出現 (10–19, 確定已在) → 只剩確定 (20–39)."""
    a = screen([(BUTTONS["開始"], *POS["開始"])], title=True)
    b = screen([(BUTTONS["確定"], *POS["確定"]), (BUSY, *BUSY_POS)], title=True)
    c = screen([(BUTTONS["確定"], *POS["確定"])], title=True)
    return write_video(tmp_path / "busy.mp4", timeline((a, 10), (b, 10), (c, 20)))


def busy_plan(tmp_path, steps):
    templates = {"開始": {"frame": 5, "box": box("開始")},
                 "確定": {"frame": 25, "box": box("確定")},
                 "忙碌": {"frame": 12, "box": [*BUSY_POS, 60, 24]}}
    return demo_plan(busy_video(tmp_path), make_out(tmp_path), steps=steps,
                     templates=templates, busy={"template": "忙碌"})


def test_忙碌檢查照計畫原樣_沒寫的不勾_兩向都報(tmp_path, engine):
    steps = [find("開始"), find("確定", frame=25, busy_check=True)]
    res = video_to_flow.assemble(busy_plan(tmp_path, steps), engine=engine)
    s = saved(res)["steps"]
    assert [x["busy_check"] for x in s] == [False, True]
    assert [t for _, t in res["busy_unchecked"]] == ["找圖點擊「開始」（第 5 幀送出）"]
    assert [t for _, t in res["busy_unseen"]] == ["找圖點擊「確定」（第 25 幀送出）"]
    text = report_files(res)["總覽.md"]
    assert "沒勾忙碌檢查、但之後的影格看到忙碌指示" in text
    assert "找圖點擊「開始」（第 5 幀送出）" in text


def test_勾了且之後看到忙碌_沒勾且之後沒看到_都不報(tmp_path, engine):
    steps = [find("開始", busy_check=True), find("確定", frame=25)]
    res = video_to_flow.assemble(busy_plan(tmp_path, steps), engine=engine)
    assert res["busy_unseen"] == [] and res["busy_unchecked"] == []
    assert saved(res)["busy"]["within"] == expand(found(res, "忙碌", 12))


def test_有忙碌指示時座標點擊要寫frame(tmp_path, engine):
    steps = [find("開始", head="find"), click(200, 200)]
    with pytest.raises(video_to_flow.ToolError, match="frame"):
        video_to_flow.assemble(busy_plan(tmp_path, steps), engine=engine)


# ================= 06 交付報告資料夾 =================

def test_每個頂層區段一份_檔名取開頭找圖的範本名_撞名加序號(demo, engine):
    steps = [{"branch": [{"if": find("開始", head="find", on_fail="skip", timeout=1)}]},
             {"repeat": 2, "steps": [find("確定", head="find")]},
             find("下一步", head="find"), click(240, 120),
             {"repeat": 2, "steps": [find("確定", head="find")]}]
    res = run(demo, engine, steps)
    files = report_files(res)
    assert sorted(files) == sorted(["總覽.md", "分岔-開始.md", "重複-確定.md",
                                    "步驟-下一步.md", "重複-確定_2.md"])
    ov = files["總覽.md"]
    links = re.findall(r"\]\(([^)]+\.md)\)", ov.split("## 各段報告")[1].split("##")[0])
    assert links == ["分岔-開始.md", "重複-確定.md", "步驟-下一步.md", "重複-確定_2.md"]


def test_報告文字裡沒有步驟編號(demo, engine):
    from vtf_synth import BLANK
    templates = {"空白": {"frame": 5, "box": [BLANK[0] + 10, BLANK[1] + 10, 40, 30]}}
    from vtf_synth import demo_templates
    templates.update(demo_templates())
    steps = [find("開始"), {"find_click": "空白", "frame": 5}, find("確定")]
    res = run(demo, engine, steps, templates=templates)
    assert "空白" in res["retake"]
    for name, text in report_files(res).items():
        assert not re.search(r"步驟\s*\d", text), (name, re.findall(r".{20}步驟\s*\d.{20}", text))


def test_總覽與各段的內容(demo, engine):
    steps = [find("開始", head="find"), {"drag": [84, 100], "to": [84, 40]},
             find("確定")]
    res = run(demo, engine, steps, report={"unexplained": ["第 3 秒畫面變暗"],
                                           "branches": ["可能有簽到彈窗"]})
    files = report_files(res)
    ov = files["總覽.md"]
    for want in ("校準對：圖示 × 關閉", "來源影片", "搜尋範圍", "忙碌指示",
                 "## 待重拍", "## 待確認", "### 捲動清單",
                 "## 無法用點擊解釋的畫面變化（流程不支援按鍵，請改用點擊）",
                 "第 3 秒畫面變暗", "可能有簽到彈窗"):
        assert want in ov, want
    assert "口頭補充的按鍵" not in ov
    sec = files["步驟-開始.md"]
    for want in ("## 這段做什麼", "## 怎麼建的", "## 已知風險", "## 待重拍", "## 待確認",
                 "找圖（不點）「開始」", "拖曳 相對原點", "有拖曳捲動"):
        assert want in sec, want


def test_區段切法是純函式(demo):
    from automation import flowdefaults

    def st(t, **kw):
        if t in ("find_click", "find", "wait_gone"):
            kw.setdefault("target", {"template": kw.pop("name", "x")})
        return flowdefaults.complete(dict(kw, type=t))
    steps = [st("click", click=[0, 0]), st("find", name="甲"), st("repeat_start", repeat=2),
             st("find", name="乙"), st("repeat_end"), st("wait", wait=1),
             st("branch_start"), st("find", name="丙"), st("branch_or"),
             st("find", name="丁"), st("branch_end")]
    secs = report_mod.sections(steps)
    assert [(s.name, s.kind, s.start, s.end) for s in secs] == [
        ("步驟-甲", "steps", 0, 2), ("重複-乙", "repeat", 2, 5),
        ("步驟-等待", "steps", 5, 6), ("分岔-丙", "branch", 6, 11)]
