import math
import os
import shutil

import cv2
import pytest

import flowfile
import video_to_flow
from vtf_synth import (ANCHOR, VIDEO_H, VIDEO_W, demo_plan, make_button, make_out,
                       screen, snapshot, write_video)

GOODS = {"甲": make_button(seed=51), "乙": make_button(w=64, h=48, seed=52),
         "丙": make_button(seed=53), "忙": make_button(w=40, h=24, seed=54)}
GPOS = {"甲": (100, 50), "乙": (220, 130), "丙": (160, 50), "忙": (240, 60)}
SHOP = [80, 30, 220, 150]
WHY = "商品每天換格子，兩排都可能出現"


def gbox(name, pos=None):
    x, y = pos or GPOS[name]
    h, w = GOODS[name].shape[:2]
    return [x, y, w, h]


def gcenter(name, pos=None):
    x, y, w, h = gbox(name, pos)
    return [x + w // 2, y + h // 2]


def shop_video(path, names=("甲", "乙", "忙"), pos=None, r=1.0, n=20):
    pos = dict(GPOS, **(pos or {}))
    img = screen([(GOODS[k], *pos[k]) for k in names], title=True)
    frames = [img] * n
    if r != 1:
        size = (round(VIDEO_W * r), round(VIDEO_H * r))
        frames = [cv2.resize(f, size, interpolation=cv2.INTER_AREA if r < 1
                             else cv2.INTER_LINEAR) for f in frames]
    return write_video(path, frames)


def templates(*names):
    return {n: {"frame": 5, "box": gbox(n)} for n in names}


def g(name, head="find_click", rect="區", **kw):
    s = {head: name, "frame": 5, "at": gcenter(name)}
    if rect:
        s["rect"] = rect
    return dict(s, **kw)


def shared(box=SHOP, **kw):
    return {"區": dict({"frame": 5, "box": list(box), "why": WHY}, **kw)}


def plan(tmp_path, steps, names=("甲", "乙"), video=None, rects=None, **extra):
    video = video or shop_video(tmp_path / "shop.mp4")
    return demo_plan(video, make_out(tmp_path), steps=steps, templates=templates(*names),
                     shared_rects=shared() if rects is None else rects, **extra)


def run(tmp_path, engine, steps, **kw):
    return video_to_flow.assemble(plan(tmp_path, steps, **kw), engine=engine)


def refused(tmp_path, engine, steps, match, **kw):
    p = plan(tmp_path, steps, **kw)
    before = snapshot(p["out"])
    with pytest.raises(video_to_flow.ToolError, match=match):
        video_to_flow.assemble(p, engine=engine)
    assert snapshot(p["out"]) == before, "報錯時輸出位置一個檔案都不多"


def saved(res):
    return flowfile.read_flow(res["flow_path"])


def want_rect(container, boxes, scroll=None, size=(VIDEO_W, VIDEO_H), anchor=ANCHOR):
    x, y, w, h = container
    mx = math.ceil(max(b[2] for b in boxes) / 2)
    my = math.ceil(max(b[3] for b in boxes) / 2)
    x0, y0, x1, y1 = x - mx, y - my, x + w + mx, y + h + my
    if scroll == "vertical":
        y0, y1 = 0, size[1]
    if scroll == "horizontal":
        x0, x1 = 0, size[0]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(size[0], x1), min(size[1], y1)
    return [x0 - anchor[0], y0 - anchor[1], x1 - x0, y1 - y0]


def found(res, *names):
    return [res["found"][n][5] for n in names]


def report(res, name):
    with open(os.path.join(res["report_path"], name), encoding="utf-8") as f:
        return f.read()


def test_兩個成員共用一個框_逐字相同_等於容器外推最大成員框一半(tmp_path, engine):
    res = run(tmp_path, engine, [g("甲"), g("乙")])
    a, b = (s["target"]["within"] for s in saved(res)["steps"])
    assert a == b == want_rect(SHOP, found(res, "甲", "乙"))
    assert res["retake"] == {}


def test_只有一個成員也可以(tmp_path, engine):
    res = run(tmp_path, engine, [g("甲")], names=("甲",))
    w = saved(res)["steps"][0]["target"]["within"]
    assert w == want_rect(SHOP, found(res, "甲"))


def test_共用矩形宣告捲動軸_那一軸到影片兩端(tmp_path, engine):
    res = run(tmp_path, engine, [g("甲"), g("乙")], rects=shared(scroll="vertical"))
    w = saved(res)["steps"][0]["target"]["within"]
    assert w == want_rect(SHOP, found(res, "甲", "乙"), scroll="vertical")
    assert w[3] == VIDEO_H


def test_容器貼邊被裁_裁過的一側不報錯(tmp_path, engine):
    edge = [60, 0, 420, 190]
    res = run(tmp_path, engine, [g("甲"), g("乙")], rects=shared(box=edge))
    w = saved(res)["steps"][0]["target"]["within"]
    assert w == want_rect(edge, found(res, "甲", "乙"))
    assert w[1] + ANCHOR[1] == 0 and w[0] + ANCHOR[0] + w[2] == VIDEO_W


def test_成員挑中的框超出容器_報錯且不產生資料夾(tmp_path, engine):
    small = [80, 30, 160, 120]
    refused(tmp_path, engine, [g("甲"), g("乙")], r"共用矩形「區」.*「乙」.*第 5 幀.*容器",
            rects=shared(box=small))


@pytest.mark.parametrize("steps, rects, match", [
    ([g("甲", rect="別區")], None, "「別區」.*不在 shared_rects"),
    ([g("甲", rect=None)], None, "「區」.*沒有.*引用"),
    ([g("甲", scroll="vertical")], None, "rect 跟 scroll 不能同寫"),
    ([g("甲")], shared(within=[0, 0, 10, 10]), "within"),
    ([g("甲")], shared(offset=[0, 0]), "offset"),
    ([g("甲")], shared(color=True), "不認得的欄位 color"),
    ([g("甲")], {"區": {"frame": 5, "box": SHOP}}, "why"),
    ([g("甲")], {"區": {"same_as": 1, "expect": {"find": "甲"}, "why": WHY}}, "same_as.*補充"),
    ([g("甲")], shared(box=[0, 0, 0, 10]), "box"),
    ([g("甲")], shared(scroll="diagonal"), "scroll"),
    ([{"click": [150, 200], "rect": "區"}], None, "rect（共用矩形）只用在找圖"),
], ids=["名字不存在", "沒人引用", "rect與scroll同寫", "宣告寫within", "宣告寫offset",
        "宣告不認得的鍵", "沒寫why", "組裝寫same_as", "box不成形", "scroll不成形",
        "座標點擊寫rect"])
def test_計畫寫錯就報錯(tmp_path, engine, steps, rects, match):
    refused(tmp_path, engine, steps, match, rects=rects, names=("甲",))


def test_套上共用矩形後照跑唯一檢查_有挑選規則的略過(tmp_path, engine):
    img = screen([(GOODS["甲"], *GPOS["甲"]), (GOODS["甲"], 100, 130)], title=True)
    video = write_video(tmp_path / "two.mp4", [img] * 20)
    res = run(tmp_path, engine, [g("甲")], names=("甲",), video=video)
    assert any("唯一" in why for why in res["retake"].get("甲", [])), res["retake"]
    res = run(tmp_path, engine, [g("甲", pick={"top": 1})], names=("甲",), video=video)
    assert not any("唯一" in why for why in res["retake"].get("甲", [])), res["retake"]


def test_成員不列進捲動待確認_同段沒宣告的照舊列(tmp_path, engine):
    steps = [g("甲", head="find"), {"drag": [150, 200], "to": [150, 100]},
             g("乙", rect=None), g("乙")]
    res = run(tmp_path, engine, steps)
    assert [t for _, t in res["scroll_confirm"]] == ["找圖點擊「乙」"]
    assert [i for i, _ in res["scroll_confirm"]] == [2]


def test_確認圖引用共用矩形_外推量照最大的成員(tmp_path, engine):
    steps = [g("甲", confirm={"appear": "乙", "rect": "區"})]
    res = run(tmp_path, engine, steps)
    s = saved(res)["steps"][0]
    want = want_rect(SHOP, found(res, "甲", "乙"))
    assert s["target"]["within"] == s["confirm_target"]["within"] == want
    mx = math.ceil(found(res, "乙")[0][2] / 2)
    assert want[2] == SHOP[2] + 2 * mx, "外推量取確認圖 (較大的) 的框"


def test_忙碌指示是唯一引用者也算有人引用(tmp_path, engine):
    res = run(tmp_path, engine, [g("甲", rect=None)], names=("甲", "忙"),
              busy={"template": "忙", "rect": "區"})
    assert saved(res)["busy"]["within"] == want_rect(SHOP, found(res, "忙"))


def test_確認圖超出容器就報錯(tmp_path, engine):
    small = [80, 30, 160, 120]
    refused(tmp_path, engine, [g("甲", confirm={"appear": "乙", "rect": "區"})],
            r"共用矩形「區」.*確認圖「乙」.*容器", rects=shared(box=small))


def test_忙碌指示超出容器就報錯(tmp_path, engine):
    small = [80, 30, 100, 80]
    refused(tmp_path, engine, [g("甲")], r"共用矩形「區」.*忙碌指示「忙」.*容器",
            rects=shared(box=small), names=("甲", "忙"),
            busy={"template": "忙", "rect": "區"})


@pytest.mark.parametrize("confirm", [{"gone": True, "rect": "區"}, {"rect": "區"}],
                         ids=["gone", "沒寫appear"])
def test_gone與next確認寫rect就報錯(tmp_path, engine, confirm):
    refused(tmp_path, engine, [g("甲", confirm=confirm)], "rect 只用在 appear",
            names=("甲",))


def test_區段報告與總覽列出共用矩形(tmp_path, engine):
    res = run(tmp_path, engine, [g("甲"), g("乙", confirm={"appear": "甲", "rect": "區"})])
    sec = report(res, "步驟-甲.md")
    block = sec.split("## 共用矩形")[1].split("\n## ")[0]
    for want in ("「區」", WHY, "找圖點擊「甲」", "找圖點擊「乙」", "找圖點擊「乙」的確認圖「甲」",
                 "捲動軸：沒有"):
        assert want in block, want
    ov = report(res, "總覽.md")
    block = ov.split("## 共用矩形")[1].split("\n## ")[0]
    assert "「區」" in block and "](步驟-甲.md)" in block


def test_成員跨段_第一段完整列出_其他段一行指過去(tmp_path, engine):
    steps = [g("甲"), {"repeat": 2, "steps": [g("乙", head="find")]}]
    res = run(tmp_path, engine, steps, rects=shared(scroll="horizontal"))
    first = report(res, "步驟-甲.md").split("## 共用矩形")[1]
    assert "找圖（不點）「乙」" in first
    assert "捲動軸：橫向" in first
    other = report(res, "重複-乙.md").split("## 共用矩形")[1].split("\n## ")[0]
    assert "「區」" in other and "](步驟-甲.md)" in other and WHY not in other


def test_沒有共用矩形的流程_報告沒有這一節(tmp_path, engine):
    res = run(tmp_path, engine, [g("甲", rect=None)], rects={})
    for fn in os.listdir(res["report_path"]):
        assert "## 共用矩形" not in report(res, fn), fn


def test_忙碌指示成員也列在成員裡(tmp_path, engine):
    res = run(tmp_path, engine, [g("甲")], names=("甲", "忙"),
              busy={"template": "忙", "rect": "區"})
    assert "忙碌指示「忙」" in report(res, "步驟-甲.md").split("## 共用矩形")[1]


BASE_STEPS = [g("甲"), g("乙"), {"click": [150, 200]}]


@pytest.fixture(scope="module")
def base_flow(tmp_path_factory, engine):
    tmp = tmp_path_factory.mktemp("shopbase")
    p = plan(tmp, BASE_STEPS, video=shop_video(tmp / "base.mp4"))
    return video_to_flow.assemble(p, engine=engine)["flow_path"]


@pytest.fixture
def flow(base_flow, tmp_path):
    dst = tmp_path / "既有"
    shutil.copytree(base_flow, dst)
    return dst


def S(v, r):
    return [round(c * r) for c in v]


def add_plan(video, steps=None, rects=None, r=1.0, **extra):
    p = {"video": str(video),
         "templates": {"丙": {"frame": 5, "box": S(gbox("丙"), r)}},
         "steps": steps if steps is not None else [
             {"find_click": "丙", "frame": 5, "at": S(gcenter("丙"), r), "rect": "區"}],
         "shared_rects": rects if rects is not None else {
             "區": {"same_as": 1, "expect": {"find_click": "甲"}, "why": WHY}},
         "after": 3, "expect": {"click": None}}
    p.update(extra)
    return p


def add_video(path, pos=None, r=1.0):
    return shop_video(path, names=("甲", "乙", "丙"), pos=pos, r=r)


def insert_refused(flow, p, match, engine):
    before = snapshot(flow)
    with pytest.raises(video_to_flow.ToolError, match=match):
        video_to_flow.insert(p, flow, engine=engine)
    assert snapshot(flow) == before, "報錯後既有資料夾逐位元不變"


def test_same_as_照抄第N步的框_逐字相同(flow, tmp_path, engine):
    old = flowfile.read_flow(flow)["steps"][0]["target"]["within"]
    video_to_flow.insert(add_plan(add_video(tmp_path / "add.mp4")), flow, engine=engine)
    steps = flowfile.read_flow(flow)["steps"]
    assert steps[3]["target"]["template"] == "丙"
    assert steps[3]["target"]["within"] == old


@pytest.mark.parametrize("decl, match", [
    ({"same_as": 1, "expect": {"find_click": "乙"}}, "same_as: 第 1 步是.*不符.*# N"),
    ({"same_as": 99, "expect": {"find_click": "甲"}}, "超出流程"),
    ({"same_as": 3, "expect": {"click": None}}, "沒有固定矩形"),
], ids=["expect不符", "超出流程", "沒有固定矩形"])
def test_same_as核對不符就報錯_資料夾不變(flow, tmp_path, engine, decl, match):
    p = add_plan(add_video(tmp_path / "add.mp4"), rects={"區": dict(decl, why=WHY)})
    insert_refused(flow, p, match, engine)


def test_新成員落在照抄的框外就報錯_資料夾不變(flow, tmp_path, engine):
    video = add_video(tmp_path / "add.mp4", pos={"丙": (380, 20)})
    p = add_plan(video, steps=[{"find_click": "丙", "frame": 5, "at": gcenter("丙", (380, 20)),
                                "rect": "區"}],
                 templates={"丙": {"frame": 5, "box": gbox("丙", (380, 20))}})
    insert_refused(flow, p, r"共用矩形「區」.*「丙」.*照抄的框.*外", engine)


def test_影片倍率0點9_影片像素宣告換回流程尺度(flow, tmp_path, engine):
    r = 0.9
    box2 = [140, 40, 100, 70]
    rects = {"新區": {"frame": 5, "box": S(box2, r), "why": WHY}}
    steps = [{"find_click": "丙", "frame": 5, "at": S(gcenter("丙"), r), "rect": "新區"}]
    res = video_to_flow.insert(add_plan(add_video(tmp_path / "add.mp4", r=r), steps=steps,
                                        rects=rects, r=r), flow, engine=engine)
    assert abs(res["video_scale"] - r) < 0.01
    got = flowfile.read_flow(flow)["steps"][3]["target"]["within"]
    want = want_rect(box2, [gbox("丙")])
    assert all(abs(a - b) <= 3 for a, b in zip(got, want)), (got, want)
    sec = (flow / "交付報告" / "步驟-甲.md").read_text(encoding="utf-8")
    assert f"容器框 {S(box2, r)}（第 5 幀）" in sec, "報告的容器框照計畫寫的影片像素"


def test_插入處報告與總覽記下沿用來源(flow, tmp_path, engine):
    video_to_flow.insert(add_plan(add_video(tmp_path / "add.mp4")), flow, engine=engine)
    rdir = flow / "交付報告"
    sec = (rdir / "步驟-甲.md").read_text(encoding="utf-8")
    ov = (rdir / "總覽.md").read_text(encoding="utf-8")
    want = "沿用找圖點擊「甲」那一步的共用矩形"
    assert want in sec.split("## 共用矩形")[1] and want in ov.split("## 共用矩形")[1]
    assert "](步驟-甲.md)" in ov.split("## 共用矩形")[1]


def test_補充的新成員不列進捲動待確認(flow, tmp_path, engine):
    steps = [{"find": "丙", "frame": 5, "at": gcenter("丙"), "rect": "區"},
             {"drag": [150, 200], "to": [150, 100], "frame": 6},
             {"find_click": "丙", "frame": 7, "at": gcenter("丙")}]
    res = video_to_flow.insert(add_plan(add_video(tmp_path / "add.mp4"), steps=steps,
                                        align=None), flow, engine=engine)
    assert [t for _, t in res["scroll_confirm"]] == ["找圖點擊「丙」"]
