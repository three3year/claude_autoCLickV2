"""固定矩形的`停點差`與`遞補方向`、補充引用既有範本的待確認、交付報告的三個程式錯
(rect-drift-shift 01–04).

只打組裝與補充兩個公開入口; 斷言經 app 讀回的各步 `within`、結果的待重拍與待確認、交付報告文字、
報錯訊息與「資料夾不變」。標準示範影片: 畫面 A「開始」、B「確定」(300,150)、C「下一步」。
"""
import math
import re
import shutil

import cv2
import pytest

import flowfile
import video_to_flow
from automation import pickcheck
from vtf_synth import (ANCHOR, BUTTONS, POS, VIDEO_H, VIDEO_W, box, center, demo_plan,
                       demo_video, find, make_button, make_out, screen, snapshot, write_video)

DRIFT = 80        # 停點差: 沿宣告方向每邊至少外推這麼多 (流程尺度)
DRAG = {"drag": [240, 200], "to": [240, 100], "frame": 10}


def want(b, drift=None, toward=None, size=(VIDEO_W, VIDEO_H), anchor=ANCHOR):
    """固定矩形的期望值: 每邊外推一半; 停點差那一軸取一半與 80 的較大值; 遞補方向那一端拉到
    影片邊; 裁到影片、相對基準點."""
    x, y, w, h = b
    mx, my = math.ceil(w / 2), math.ceil(h / 2)
    if drift == "vertical":
        my = max(my, DRIFT)
    if drift == "horizontal":
        mx = max(mx, DRIFT)
    x0, y0, x1, y1 = x - mx, y - my, x + w + mx, y + h + my
    if toward == "left":
        x0 = 0
    if toward == "right":
        x1 = size[0]
    if toward == "up":
        y0 = 0
    if toward == "down":
        y1 = size[1]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(size[0], x1), min(size[1], y1)
    return [x0 - anchor[0], y0 - anchor[1], x1 - x0, y1 - y0]


def close(a, b, tol=3):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def saved(res):
    return flowfile.read_flow(res["flow_path"])


def assemble(tmp_path, engine, steps, video=None, templates=None, **extra):
    p = demo_plan(video or demo_video(tmp_path), make_out(tmp_path), steps=steps,
                  templates=templates, **extra)
    return video_to_flow.assemble(p, engine=engine)


def assemble_refused(tmp_path, engine, steps, match, **extra):
    p = demo_plan(demo_video(tmp_path), make_out(tmp_path), steps=steps, **extra)
    before = snapshot(p["out"])
    with pytest.raises(video_to_flow.ToolError, match=match):
        video_to_flow.assemble(p, engine=engine)
    assert snapshot(p["out"]) == before, "報錯時輸出位置一個檔案都不多"


def report(folder, name):
    return (folder / "交付報告" / name).read_text(encoding="utf-8")


def section(text, heading):
    """報告裡 `heading` 這一節 (到下一個 ## 為止)."""
    return text.split(heading + "\n", 1)[1].split("\n## ")[0]


# ================= 02 停點差 (組裝) =================

def test_停點差_沿宣告方向每邊80_另一軸外推一半(tmp_path, engine):
    steps = [find("開始"), DRAG, find("確定", head="find", drift="vertical")]
    res = assemble(tmp_path, engine, steps)
    w = saved(res)["steps"][2]["target"]["within"]
    assert w == want(box("確定"), drift="vertical")
    assert w[3] == 36 + 2 * DRIFT and w[2] == 48 * 2
    assert res["retake"] == {}


WIDE = make_button(w=170, h=36, seed=61)
WIDE_POS = (150, 120)


def test_停點差_範本該軸一半超過80時照外推一半(tmp_path, engine):
    img = screen([(WIDE, *WIDE_POS)], title=True)
    video = write_video(tmp_path / "wide.mp4", [img] * 20)
    wbox = [*WIDE_POS, 170, 36]
    steps = [{"find": "圖示", "frame": 5}, DRAG,
             {"find": "寬", "frame": 5, "drift": "horizontal"}]
    res = assemble(tmp_path, engine, steps, video=video,
                   templates={"寬": {"frame": 5, "box": wbox}})
    w = saved(res)["steps"][2]["target"]["within"]
    assert w == want(wbox, drift="horizontal")
    assert w[2] == 170 + 2 * 85, "170 寬的一半 85 大於 80"


def test_停點差_放寬後框到同款_列出唯一不過(tmp_path, engine):
    a = make_button(seed=71)
    img = screen([(a, 200, 100), (a, 200, 170)], title=True)   # 上下相距 70
    video = write_video(tmp_path / "two.mp4", [img] * 20)
    tpl = {"甲": {"frame": 5, "box": [200, 100, 48, 36]}}
    plain = [{"find": "圖示", "frame": 5}, DRAG,
             {"find_click": "甲", "frame": 5, "at": [224, 118]}]
    res = assemble(tmp_path, engine, plain, video=video, templates=tpl)
    assert not any("唯一" in why for why in res["retake"].get("甲", [])), res["retake"]
    (tmp_path / "out").rename(tmp_path / "out_plain")
    plain[2]["drift"] = "vertical"
    res = assemble(tmp_path, engine, plain, video=video, templates=tpl)
    assert any("唯一" in why for why in res["retake"].get("甲", [])), res["retake"]


@pytest.mark.parametrize("steps, match", [
    ([find("確定", head="find", drift="vertical")], r"步驟 1.*drift.*之前沒有拖曳"),
    ([find("開始"), {"drag": [240, 200], "to": [240, 100], "drift": "vertical"}],
     r"步驟 2.*drift（停點差）只用在找圖"),
    ([find("開始"), DRAG, find("確定", drift="diagonal")], r"步驟 3.*drift 只能是"),
    ([find("開始"), DRAG, find("確定", drift="vertical", scroll="vertical")],
     r"步驟 3.*scroll 跟 drift 不能同寫"),
    ([find("開始"), DRAG, find("確定", drift="vertical", shift="left")],
     r"步驟 3.*drift 跟 shift 不能同寫"),
], ids=["前面沒有拖曳", "寫在拖曳", "值不認得", "跟scroll同寫", "跟shift同寫"])
def test_停點差寫錯就報錯_資料夾不變(tmp_path, engine, steps, match):
    assemble_refused(tmp_path, engine, steps, match)


def test_停點差跟共用矩形同寫就報錯(tmp_path, engine):
    rects = {"區": {"frame": 20, "box": [280, 130, 100, 80], "why": "測試"}}
    assemble_refused(tmp_path, engine,
                     [find("開始"), DRAG, find("確定", drift="vertical", rect="區")],
                     r"步驟 3.*rect 跟 drift 不能同寫", shared_rects=rects)


def test_宣告停點差或遞補方向的不列進捲動待確認_提示也建議停點差(tmp_path, engine):
    steps = [find("開始"), DRAG, find("確定", head="find", drift="vertical"),
             find("下一步", shift="left"), find("確定", frame=25)]
    res = assemble(tmp_path, engine, steps)
    assert [t for _, t in res["scroll_confirm"]] == ["找圖點擊「開始」", "找圖點擊「確定」"]
    sec = report(tmp_path / "out" / "日常", "步驟-開始.md")
    assert "停點差" in section(sec, "## 待確認")


def test_段落報告列出停點差與遞補方向的步驟(tmp_path, engine):
    steps = [find("開始"), DRAG, find("確定", head="find", drift="vertical"),
             find("下一步", shift="left")]
    res = assemble(tmp_path, engine, steps)
    built = section(report(tmp_path / "out" / "日常", "步驟-開始.md"), "## 怎麼建的")
    drift = next(x for x in built.split("\n") if "找圖（不點）「確定」" in x and "停點差" in x)
    assert "直向" in drift
    shift = next(x for x in built.split("\n") if "找圖點擊「下一步」" in x and "遞補方向" in x)
    assert "往左" in shift
    assert not any("停點差" in x and "「開始」" in x for x in built.split("\n"))
    assert res["loosened"] == [(2, "drift", "vertical"), (3, "shift", "left")]


# ================= 03 遞補方向 (組裝) =================

@pytest.mark.parametrize("toward", ["left", "right", "up", "down"])
def test_遞補方向_只朝那一端拉到影片邊緣_另一軸外推一半(tmp_path, engine, toward):
    res = assemble(tmp_path, engine, [find("確定", shift=toward)])
    w = saved(res)["steps"][0]["target"]["within"]
    assert w == want(box("確定"), toward=toward)
    x0, y0 = w[0] + ANCHOR[0], w[1] + ANCHOR[1]
    edges = {"left": x0 == 0, "right": x0 + w[2] == VIDEO_W,
             "up": y0 == 0, "down": y0 + w[3] == VIDEO_H}
    assert [k for k, v in edges.items() if v] == [toward]


@pytest.mark.parametrize("steps, match", [
    ([find("開始"), {"click": [150, 200], "shift": "left"}],
     r"步驟 2.*shift（遞補方向）只用在找圖"),
    ([find("確定", shift="sideways")], r"步驟 1.*shift 只能是"),
    ([find("確定", shift="left", scroll="horizontal")], r"步驟 1.*scroll 跟 shift 不能同寫"),
], ids=["寫在座標點擊", "值不認得", "跟scroll同寫"])
def test_遞補方向寫錯就報錯_資料夾不變(tmp_path, engine, steps, match):
    assemble_refused(tmp_path, engine, steps, match)


def test_遞補方向跟共用矩形同寫就報錯(tmp_path, engine):
    rects = {"區": {"frame": 20, "box": [280, 130, 100, 80], "why": "測試"}}
    assemble_refused(tmp_path, engine, [find("確定", shift="left", rect="區")],
                     r"步驟 1.*rect 跟 shift 不能同寫", shared_rects=rects)


# ================= 補充 =================
# 既有流程: 開始 → 拖曳 → 定位確定 (停點差) → 點擊 → 重複 2 次 [找確定 → 點擊]
#   1 找圖點擊開始  2 拖曳  3 找確定  4 點擊  5 重複開頭  6 找確定  7 點擊  8 重複結尾
# 段落報告: 步驟-開始 (1–4)、重複-確定 (5–8)。

BASE_STEPS = [find("開始"), DRAG, find("確定", head="find", drift="vertical"),
              {"click": [330, 220]},
              {"repeat": 2, "steps": [find("確定", head="find"), {"click": [330, 220]}]}]
NEW = make_button(seed=41)
NEW_POS = (120, 120)
NEW_BOX = [*NEW_POS, 48, 36]
NEW_C = [NEW_POS[0] + 24, NEW_POS[1] + 18]
DY = 40     # 補充影片開錄時清單停在別處: 確定與新鈕整批往下 DY
OK_V = (POS["確定"][0], POS["確定"][1] + DY)


@pytest.fixture(scope="module")
def base_flow(tmp_path_factory, engine):
    tmp = tmp_path_factory.mktemp("rrbase")
    plan = demo_plan(demo_video(tmp), make_out(tmp), steps=BASE_STEPS, name="既有")
    return video_to_flow.assemble(plan, engine=engine)["flow_path"]


@pytest.fixture
def flow(base_flow, tmp_path):
    dst = tmp_path / "既有"
    shutil.copytree(base_flow, dst)
    return dst


def add_video(path, r=1.0):
    """0–14 幀: 確定＋新鈕整批偏 DY; 15–29 幀: 清單往上拖了 100 之後 (新鈕在 NEW_POS)."""
    a = screen([(BUTTONS["確定"], *OK_V), (NEW, NEW_POS[0], NEW_POS[1] + DY)], title=True)
    b = screen([(NEW, *NEW_POS)], title=True)
    frames = [a] * 15 + [b] * 15
    if r != 1:
        size = (round(VIDEO_W * r), round(VIDEO_H * r))
        frames = [cv2.resize(f, size, interpolation=cv2.INTER_AREA if r < 1
                             else cv2.INTER_LINEAR) for f in frames]
    return write_video(path, frames)


def S(v, r):
    return [round(c * r) for c in v]


def add_plan(video, steps, r=1.0, templates=None, **extra):
    p = {"video": str(video),
         "templates": templates if templates is not None else {
             "新鈕": {"frame": 20, "box": S(NEW_BOX, r)}},
         "steps": steps, "after": 4, "expect": {"click": None}}
    p.update(extra)
    return p


def insert(flow, plan, engine):
    return video_to_flow.insert(plan, flow, engine=engine)


def insert_refused(flow, plan, match, engine):
    before = snapshot(flow)
    with pytest.raises(video_to_flow.ToolError, match=match):
        video_to_flow.insert(plan, flow, engine=engine)
    assert snapshot(flow) == before, "報錯後既有資料夾逐位元不變"


def steps_of(flow):
    return flowfile.read_flow(flow)["steps"]


def test_補充_停點差_框沿直向每邊80(flow, tmp_path, engine):
    steps = [{"find": "新鈕", "frame": 20, "drift": "vertical", "update_origin": False}]
    insert(flow, add_plan(add_video(tmp_path / "add.mp4"), steps), engine)
    w = steps_of(flow)[4]["target"]["within"]
    assert w == want(NEW_BOX, drift="vertical")


def test_補充_影片倍率不是1時80仍是流程尺度(flow, tmp_path, engine):
    r = 0.9
    steps = [{"find": "新鈕", "frame": 20, "drift": "vertical", "update_origin": False}]
    res = insert(flow, add_plan(add_video(tmp_path / "add.mp4", r=r), steps, r=r), engine)
    assert abs(res["video_scale"] - r) < 0.01
    w = steps_of(flow)[4]["target"]["within"]
    assert close(w, want(NEW_BOX, drift="vertical")), (w, want(NEW_BOX, drift="vertical"))
    assert abs(w[3] - (36 + 2 * DRIFT)) <= 2


ALIGN = {"find": "確定", "frame": 5, "at": [OK_V[0] + 24, OK_V[1] + 18], "step": 3}


def aligned_steps():
    """定位確定 (第一次拖曳前, 停點差) → 往上拖 100 → 找新鈕 (停點差) → 點新鈕."""
    return [{"find": "確定", "frame": 5, "drift": "vertical"},
            {"drag": [300, 230], "to": [300, 130], "frame": 6},
            {"find": "新鈕", "frame": 20, "at": NEW_C, "drift": "vertical"},
            {"click": NEW_C, "frame": 21}]


def test_補充_有對齊時先平移再放寬(flow, tmp_path, engine):
    res = insert(flow, add_plan(add_video(tmp_path / "add.mp4"), aligned_steps(),
                                align=ALIGN), engine)
    assert close(res["align"]["shift"], [0, -DY], 1)
    loc, _, new, _ = steps_of(flow)[4:8]
    assert close(loc["target"]["within"], want(box("確定"), drift="vertical"), 2)
    assert close(new["target"]["within"], want(NEW_BOX, drift="vertical"), 2)
    assert res["loosened"] == [(0, "drift", "vertical"), (2, "drift", "vertical")]


def test_補充_停點差但結果流程裡之前沒有拖曳就報錯(flow, tmp_path, engine):
    steps = [{"find": "新鈕", "frame": 20, "drift": "vertical", "update_origin": False}]
    plan = add_plan(add_video(tmp_path / "add.mp4"), steps, after=1,
                    expect={"find_click": "開始"})
    insert_refused(flow, plan, r"drift.*之前沒有拖曳", engine)


def test_補充_插入點前的拖曳算數_插入段自己沒有拖曳也可以(flow, tmp_path, engine):
    steps = [{"find": "新鈕", "frame": 20, "drift": "vertical", "update_origin": False}]
    res = insert(flow, add_plan(add_video(tmp_path / "add.mp4"), steps), engine)
    assert res["scroll_confirm"] == []


def test_補充_報告的補充說明列出停點差(flow, tmp_path, engine):
    insert(flow, add_plan(add_video(tmp_path / "add.mp4"), aligned_steps(), align=ALIGN),
           engine)
    for text in (section(report(flow, "步驟-開始.md"), "## 補充"),
                 section(report(flow, "總覽.md"), "## 補充")):
        assert re.search(r"找圖（不點）「新鈕」[^；。]*停點差[^；。]*直向|停點差[^。]*新鈕", text), text


@pytest.mark.parametrize("toward", ["left", "right", "up", "down"])
def test_補充_遞補方向不要求寫對齊(flow, tmp_path, engine, toward):
    steps = [{"find_click": "新鈕", "frame": 20, "at": NEW_C, "shift": toward,
              "update_origin": False}]
    res = insert(flow, add_plan(add_video(tmp_path / "add.mp4"), steps), engine)
    assert steps_of(flow)[4]["target"]["within"] == want(NEW_BOX, toward=toward)
    assert res["align"] is None
    assert res["loosened"] == [(0, "shift", toward)]


def test_補充_遞補方向寫錯就報錯(flow, tmp_path, engine):
    steps = [{"find": "新鈕", "frame": 20, "shift": "left", "drift": "vertical",
              "update_origin": False}]
    insert_refused(flow, add_plan(add_video(tmp_path / "add.mp4"), steps),
                   "drift 跟 shift 不能同寫", engine)


# ================= 04 補充引用的既有範本 =================

@pytest.fixture
def scale_fails(monkeypatch):
    """既有範本「確定」的縮放餘裕不過 (其他範本照真的查)."""
    real = pickcheck.scale_margin

    def fake(detector, screen_, origin, tgt, **kw):
        out = list(real(detector, screen_, origin, tgt, **kw))
        if tgt.get("template") == "確定":
            out.append(pickcheck.PickWarning(pickcheck.SCALE, "確定",
                                             "×0.85 找不到範本「確定」（測試）"))
        return out
    monkeypatch.setattr(pickcheck, "scale_margin", fake)


def existing_steps():
    return [{"find": "確定", "frame": 5, "update_origin": False}]


def test_既有範本沒過縮放餘裕_列待確認不列待重拍(flow, tmp_path, engine, scale_fails):
    res = insert(flow, add_plan(add_video(tmp_path / "add.mp4"), existing_steps(),
                                templates={}), engine)
    assert "確定" not in res["retake"]
    info = res["existing"]["確定"]
    assert any("縮放餘裕" in why for why in info["reasons"])
    assert info["steps"] == 3, "結果流程裡引用它的: 原本兩步＋這次一步"
    assert info["files"] == ["步驟-開始.md", "重複-確定.md"]
    ov = report(flow, "總覽.md")
    assert "確定" not in section(ov, "## 待重拍")
    confirm = section(ov, "## 待確認")
    line = next(x for x in confirm.split("\n") if "既有範本「確定」" in x)
    assert "3 步" in line and "](步驟-開始.md)" in line and "](重複-確定.md)" in line
    sec = report(flow, "步驟-開始.md")
    assert "](重複-確定.md)" in section(sec, "## 待確認")
    assert "確定" not in section(sec, "## 待重拍")


def test_既有範本在那一幀找不到_也列待確認(flow, tmp_path, engine):
    # 確認圖用既有的「確定」, 但第 20 幀上沒有它
    steps = [{"find_click": "新鈕", "frame": 20, "at": NEW_C, "update_origin": False,
              "confirm": {"appear": "確定", "frame": 20}}]
    res = insert(flow, add_plan(add_video(tmp_path / "add.mp4"), steps), engine)
    assert "確定" not in res["retake"]
    info = res["existing"]["確定"]
    assert any("找不到" in why for why in info["reasons"]), info
    assert info["steps"] == 3


def test_新裁範本沒過照舊列待重拍(flow, tmp_path, engine):
    steps = [{"find": "新鈕", "frame": 20, "update_origin": False}]
    res = insert(flow, add_plan(add_video(tmp_path / "add.mp4"), steps, templates={
        "新鈕": {"frame": 20, "box": NEW_BOX, "clean": False}}), engine)
    assert "新鈕" in res["retake"] and res["existing"] == {}
    assert "新鈕" in section(report(flow, "總覽.md"), "## 待重拍")


# ================= 01 交付報告的程式錯 =================

def branch_steps():
    return [{"branch": [{"if": {"find": "新鈕", "frame": 20, "timeout": 3, "on_fail": "skip"},
                         "then": [{"click": NEW_C, "frame": 21}]}]}]


def test_新段落的連結照流程順序插進總覽清單(flow, tmp_path, engine):
    insert(flow, add_plan(add_video(tmp_path / "add.mp4"), branch_steps()), engine)
    links = re.findall(r"\]\((.+?\.md)\)", section(report(flow, "總覽.md"),
                                                   "## 各段報告（依流程順序）"))
    assert links == ["步驟-開始.md", "分岔-新鈕.md", "重複-確定.md"]


def test_補充說明沒有多餘的分隔號(flow, tmp_path, engine):
    insert(flow, add_plan(add_video(tmp_path / "add.mp4"), branch_steps()), engine)
    for name in ("總覽.md", "分岔-新鈕.md"):
        text = section(report(flow, name), "## 補充")
        assert "：；" not in text and "分岔：找圖（不點）「新鈕」" in text, text


def test_兩次補充的條目接成同一個清單(flow, tmp_path, engine):
    video = add_video(tmp_path / "add.mp4")
    steps = [{"find": "新鈕", "frame": 20, "update_origin": False}]
    insert(flow, add_plan(video, steps), engine)
    insert(flow, add_plan(video, steps, templates={}), engine)   # 第二次引用已插入的範本
    body = section(report(flow, "總覽.md"), "## 補充").strip()
    rows = body.split("\n")
    assert len(rows) == 2 and all(r.startswith("- ") for r in rows), body


def test_待重拍待確認加了條目就沒有無(flow, tmp_path, engine, scale_fails):
    steps = [{"find": "新鈕", "frame": 20, "update_origin": False},
             {"find": "確定", "frame": 5, "update_origin": False}]
    insert(flow, add_plan(add_video(tmp_path / "add.mp4"), steps, templates={
        "新鈕": {"frame": 20, "box": NEW_BOX, "clean": False}}), engine)
    for name in ("總覽.md", "步驟-開始.md"):
        text = report(flow, name)
        for heading in ("## 待重拍", "## 待確認"):
            body = section(text, heading)
            assert not re.search(r"^無", body, re.M), (name, heading, body)
            assert body.strip(), (name, heading)
