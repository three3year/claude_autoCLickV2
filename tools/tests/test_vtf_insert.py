"""`補充`: 補充計畫＋一小段影片 → 插進既有流程 (v2f-rules-agent-docs 07–08).

既有流程用組裝建 (經 app 寫檔), 每個測試複製一份; 補充影片在流程尺度畫好再整張縮放 r 倍
(模擬錄影時視窗大小不同)。只打 `video_to_flow.insert` 與命令列; 斷言經 app 讀回的流程、
templates/、交付報告/ 的檔案, 報錯時整個資料夾逐位元不變。
"""
import json
import os
import shutil
import subprocess
import sys

import cv2
import numpy as np
import pytest

import flowfile
import video_to_flow
from vtf_synth import (ANCHOR, BUTTONS, POS, ROOT, TITLE, TITLE_POS, VIDEO_H, VIDEO_W,
                       box, center, demo_plan, demo_video, expand, find, make_button,
                       make_out, screen, snapshot, write_video)

NEW = make_button(seed=41)
NEW_POS = (120, 120)
NEW_BOX = [*NEW_POS, 48, 36]


def new_center():
    return [NEW_POS[0] + 24, NEW_POS[1] + 18]


BASE_STEPS = [find("開始"),                                         # 1
              {"repeat": 2, "steps": [find("確定", head="find"),     # 2 3
                                      {"click": [330, 200]}]},       # 4 (5 結尾)
              find("下一步", head="find"),                          # 6
              {"click": [220, 100]}]                                # 7


@pytest.fixture(scope="module")
def base_flow(tmp_path_factory, engine):
    tmp = tmp_path_factory.mktemp("base")
    plan = demo_plan(demo_video(tmp), make_out(tmp), steps=BASE_STEPS, name="既有",
                     calibration={"pair": ["圖示", "關閉"]})
    return video_to_flow.assemble(plan, engine=engine)["flow_path"]


@pytest.fixture(scope="module")
def base_flow_fb(tmp_path_factory, engine):
    """主校準對是畫面內的「開始」＋「關閉」, 備用對是「圖示」＋「關閉」."""
    tmp = tmp_path_factory.mktemp("basefb")
    plan = demo_plan(demo_video(tmp), make_out(tmp), steps=BASE_STEPS, name="既有",
                     calibration={"pair": ["開始", "關閉"],
                                  "fallback": {"pair": ["圖示", "關閉"]}})
    return video_to_flow.assemble(plan, engine=engine)["flow_path"]


@pytest.fixture
def flow(base_flow, tmp_path):
    dst = tmp_path / "既有"
    shutil.copytree(base_flow, dst)
    return dst


def add_video(path, r=1.0, title=True, n=30):
    """補充影片: 0–14 幀「確定」＋新鈕, 15–29 幀「下一步」; 整張縮放 r 倍."""
    a = screen([(BUTTONS["確定"], *POS["確定"]), (NEW, *NEW_POS)], title=title)
    b = screen([(BUTTONS["下一步"], *POS["下一步"])], title=title)
    frames = [a] * (n // 2) + [b] * (n - n // 2)
    if r != 1:
        size = (round(VIDEO_W * r), round(VIDEO_H * r))
        frames = [cv2.resize(f, size, interpolation=cv2.INTER_AREA if r < 1
                             else cv2.INTER_LINEAR) for f in frames]
    return write_video(path, frames)


def S(v, r):
    """流程尺度的像素 → 影片像素."""
    return [round(c * r) for c in v] if isinstance(v, (list, tuple)) else round(v * r)


def add_plan(video, r=1.0, steps=None, **extra):
    plan = {"video": str(video),
            "templates": {"新鈕": {"frame": 5, "box": S(NEW_BOX, r)}},
            "steps": steps if steps is not None else [
                {"find": "新鈕", "frame": 5, "at": S(new_center(), r)},
                {"click": S([150, 200], r), "frame": 6}],
            "after": 1, "expect": {"find_click": "開始"}}
    plan.update(extra)
    return plan


def read(folder):
    return flowfile.read_flow(folder)


def refused(flow, plan, match, engine):
    before = snapshot(flow)
    with pytest.raises(video_to_flow.ToolError, match=match):
        video_to_flow.insert(plan, flow, engine=engine)
    assert snapshot(flow) == before, "報錯後既有資料夾逐位元不變"


# ================= 07 插入 (同倍率) =================

def test_插在第N步之後_座標相對插入段自己的原點_新範本進templates(flow, tmp_path, engine):
    res = video_to_flow.insert(add_plan(add_video(tmp_path / "add.mp4")), flow,
                               engine=engine)
    steps = read(flow)["steps"]
    assert [s["type"] for s in steps][:4] == ["find_click", "find", "click", "repeat_start"]
    loc, c = steps[1], steps[2]
    assert loc["target"]["template"] == "新鈕"
    assert loc["target"]["within"] == expand(NEW_BOX)
    assert c["click"] == [150 - new_center()[0], 200 - new_center()[1]]
    assert (res["position"], res["inserted"], res["video_scale"]) == (2, 2, 1.0)
    assert (flow / "templates" / "新鈕.png").is_file()
    assert read(flow)["template_pos"]["新鈕"] == [new_center()[0] - ANCHOR[0],
                                                 new_center()[1] - ANCHOR[1]]


def test_插入後檢查指令無錯_行尾編號重排(flow, tmp_path, engine):
    import flow_check
    video_to_flow.insert(add_plan(add_video(tmp_path / "add.mp4")), flow, engine=engine)
    res = flow_check.check(flow)
    assert res.ok and not res.missing
    text = (flow / "flow.yaml").read_text(encoding="utf-8")
    assert text == flowfile.dump_flow(read(flow))


def test_插入處那份報告與總覽有這次補充的說明(flow, tmp_path, engine):
    video_to_flow.insert(add_plan(add_video(tmp_path / "add.mp4")), flow, engine=engine)
    rdir = flow / "交付報告"
    sec = (rdir / "步驟-開始.md").read_text(encoding="utf-8")
    ov = (rdir / "總覽.md").read_text(encoding="utf-8")
    assert "## 補充" in sec and "找圖（不點）「新鈕」" in sec
    assert "在「找圖點擊「開始」" in sec
    assert "add.mp4" in ov and "影片倍率 ×1.000" in ov and "](步驟-開始.md)" in ov
    import re
    assert not re.search(r"\d{4}-\d{2}-\d{2}", sec), "不加日期分節"


def test_after區段開頭_插在整個區段之後(flow, tmp_path, engine):
    plan = add_plan(add_video(tmp_path / "add.mp4"), after=2, expect={"repeat": 2})
    video_to_flow.insert(plan, flow, engine=engine)
    types = [s["type"] for s in read(flow)["steps"]]
    assert types[:7] == ["find_click", "repeat_start", "find", "click", "repeat_end",
                         "find", "click"]
    assert read(flow)["steps"][5]["target"]["template"] == "新鈕"


def test_into_插在重複區段裡最前面(flow, tmp_path, engine):
    plan = add_plan(add_video(tmp_path / "add.mp4"), into=2, expect={"repeat": 2})
    del plan["after"]
    video_to_flow.insert(plan, flow, engine=engine)
    steps = read(flow)["steps"]
    assert [s["type"] for s in steps][:5] == ["find_click", "repeat_start", "find", "click",
                                              "find"]
    assert steps[2]["target"]["template"] == "新鈕"
    assert steps[4]["target"]["template"] == "確定"


def test_插入段可含區段(flow, tmp_path, engine):
    steps = [{"repeat": 3, "steps": [{"find": "新鈕", "frame": 5}, {"click": [150, 200],
                                                                    "frame": 6}]}]
    video_to_flow.insert(add_plan(add_video(tmp_path / "add.mp4"), steps=steps), flow,
                         engine=engine)
    types = [s["type"] for s in read(flow)["steps"]][:6]
    assert types == ["find_click", "repeat_start", "find", "click", "repeat_end",
                     "repeat_start"]


@pytest.mark.parametrize("extra, match", [
    ({"expect": {"find_click": "確定"}}, "expect"),
    ({"expect": {"find": "開始"}}, "expect"),
    ({"after": 5, "expect": {"repeat": 2}}, "結尾"),
    ({"after": 99}, "超出"),
    ({"into": 1}, "擇一"),
], ids=["範本不符", "開頭鍵不符", "指到區段結尾", "超出流程", "after與into都寫"])
def test_插入點核對不符就報錯_資料夾不變(flow, tmp_path, engine, extra, match):
    refused(flow, add_plan(add_video(tmp_path / "add.mp4"), **extra), match, engine)


def test_插入段沒有原點就報錯(flow, tmp_path, engine):
    steps = [{"click": [150, 200], "frame": 6}, {"find": "新鈕", "frame": 5}]
    refused(flow, add_plan(add_video(tmp_path / "add.mp4"), steps=steps), "定位找圖",
            engine)


def test_插入改變後面舊步驟的原點來源就報錯(flow, tmp_path, engine):
    # 插在「找 確定」之後: 後面那個舊的座標點擊原本以它為原點, 插入後會變成插入段的點擊
    plan = add_plan(add_video(tmp_path / "add.mp4"), after=3, expect={"find": "確定"})
    refused(flow, plan, "原點來源", engine)


def test_插入段尾不更新原點就不會改變後面的原點來源(flow, tmp_path, engine):
    steps = [{"find": "新鈕", "frame": 5, "update_origin": False}]
    plan = add_plan(add_video(tmp_path / "add.mp4"), steps=steps, after=3,
                    expect={"find": "確定"})
    video_to_flow.insert(plan, flow, engine=engine)
    assert read(flow)["steps"][3]["target"]["template"] == "新鈕"


def test_引用既有範本不重裁(flow, tmp_path, engine):
    before = (flow / "templates" / "確定.png").read_bytes()
    plan = add_plan(add_video(tmp_path / "add.mp4"), templates={}, steps=[
        {"find": "確定", "frame": 5}, {"click": [150, 200], "frame": 6}])
    res = video_to_flow.insert(plan, flow, engine=engine)
    assert (flow / "templates" / "確定.png").read_bytes() == before
    assert not (flow / "templates" / "新鈕.png").exists()
    assert read(flow)["steps"][1]["target"]["template"] == "確定"
    assert res["retake"] == {}


def test_引用既有範本要寫frame(flow, tmp_path, engine):
    plan = add_plan(add_video(tmp_path / "add.mp4"), templates={},
                    steps=[{"find": "確定"}])
    refused(flow, plan, "frame", engine)


def test_新範本跟既有撞名就報錯(flow, tmp_path, engine):
    plan = add_plan(add_video(tmp_path / "add.mp4"))
    plan["templates"] = {"確定": plan["templates"]["新鈕"]}
    plan["steps"][0]["find"] = "確定"
    refused(flow, plan, "撞名", engine)


def test_新範本跟既有幾乎一樣_建議改用既有的_不擋(flow, tmp_path, engine):
    plan = add_plan(add_video(tmp_path / "add.mp4"))
    plan["templates"]["確定2"] = {"frame": 5, "box": box("確定")}
    plan["steps"] = [{"find": "確定2", "frame": 5}, {"click": [150, 200], "frame": 6}]
    del plan["templates"]["新鈕"]
    res = video_to_flow.insert(plan, flow, engine=engine)
    assert res["similar"] == {"確定2": "確定"}
    ov = (flow / "交付報告" / "總覽.md").read_text(encoding="utf-8")
    assert "建議改用既有的" in ov


@pytest.mark.parametrize("key", ["calibration", "busy", "name", "out"])
def test_計畫寫了沿用項目就報錯(flow, tmp_path, engine, key):
    plan = add_plan(add_video(tmp_path / "add.mp4"), **{key: "x"})
    refused(flow, plan, "沿用既有流程", engine)


def test_勾了忙碌檢查但既有流程沒有忙碌指示就報錯(flow, tmp_path, engine):
    steps = [{"find": "新鈕", "frame": 5}, {"click": [150, 200], "frame": 6,
                                            "busy_check": True}]
    refused(flow, add_plan(add_video(tmp_path / "add.mp4"), steps=steps), "busy", engine)


def test_命令列insert(flow, tmp_path):
    plan_path = tmp_path / "add.json"
    plan_path.write_text(json.dumps(add_plan(add_video(tmp_path / "add.mp4")),
                                    ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "video_to_flow"),
                           "insert", str(plan_path), str(flow)],
                          capture_output=True, timeout=600)
    out = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert "已插入 2 步" in out and "影片倍率 ×1.000" in out


# ================= 08 影片倍率 =================

def test_影片倍率0點9_座標固定矩形新範本都換回流程尺度(flow, tmp_path, engine):
    r = 0.9
    res = video_to_flow.insert(add_plan(add_video(tmp_path / "add.mp4", r=r), r=r),
                               flow, engine=engine)
    assert abs(res["video_scale"] - r) < 0.01
    steps = read(flow)["steps"]
    loc, c = steps[1], steps[2]
    want = expand(NEW_BOX)
    assert all(abs(a - b) <= 3 for a, b in zip(loc["target"]["within"], want)), \
        (loc["target"]["within"], want)
    wc = [150 - new_center()[0], 200 - new_center()[1]]
    assert all(abs(a - b) <= 2 for a, b in zip(c["click"], wc)), (c["click"], wc)
    img = cv2.imdecode(np.frombuffer((flow / "templates" / "新鈕.png").read_bytes(),
                                     np.uint8), cv2.IMREAD_COLOR)
    assert abs(img.shape[1] - 48) <= 1 and abs(img.shape[0] - 36) <= 1
    ov = (flow / "交付報告" / "總覽.md").read_text(encoding="utf-8")
    assert "影片倍率 ×0.9" in ov and "add.mp4" in ov


def test_拖曳距離也換回流程尺度(flow, tmp_path, engine):
    r = 1.1
    steps = [{"find": "新鈕", "frame": 5, "at": S(new_center(), r)},
             {"drag": S([150, 200], r), "to": S([150, 100], r), "frame": 6}]
    video_to_flow.insert(add_plan(add_video(tmp_path / "add.mp4", r=r), r=r, steps=steps),
                         flow, engine=engine)
    d = read(flow)["steps"][2]
    assert abs((d["drag"][1] - d["to"][1]) - 100) <= 2


def test_主校準對量不到時用備用對(base_flow_fb, tmp_path, engine):
    flow = tmp_path / "既有"
    shutil.copytree(base_flow_fb, flow)
    res = video_to_flow.insert(add_plan(add_video(tmp_path / "add.mp4")), flow,
                               engine=engine)
    assert "備用校準對" in res["scale_from"]
    loc = read(flow)["steps"][1]
    assert all(abs(a - b) <= 2 for a, b in
               zip(loc["target"]["within"], expand(NEW_BOX, anchor=center("開始"))))


def test_倍率超出支援範圍就報錯(flow, tmp_path, engine):
    r = 1.25     # 支援倍率範圍 ×0.85–1.15 之外 (縮太小的合成圖連校準對都找不到, 用放大的)
    refused(flow, add_plan(add_video(tmp_path / "add.mp4", r=r), r=r), "支援倍率範圍",
            engine)


def test_影片量不到校準對_用scale_image(flow, tmp_path, engine):
    r = 0.95
    video = add_video(tmp_path / "add.mp4", r=r, title=False)
    shot = screen([(BUTTONS["確定"], *POS["確定"])], title=True)
    shot = cv2.resize(shot, (round(VIDEO_W * r), round(VIDEO_H * r)),
                      interpolation=cv2.INTER_AREA)
    img_path = tmp_path / "同取景.png"
    ok, buf = cv2.imencode(".png", shot)
    img_path.write_bytes(buf.tobytes())
    res = video_to_flow.insert(add_plan(video, r=r, scale_image=str(img_path)), flow,
                               engine=engine)
    assert "scale_image" in res["scale_from"]
    assert abs(res["video_scale"] - r) < 0.01


def test_影片量不到校準對又沒有圖片就報錯(flow, tmp_path, engine):
    video = add_video(tmp_path / "add.mp4", title=False)
    refused(flow, add_plan(video), "scale_image", engine)


def test_計畫直接寫倍率數值也報錯(flow, tmp_path, engine):
    refused(flow, add_plan(add_video(tmp_path / "add.mp4"), scale=0.9), "不收手打的倍率",
            engine)


def test_寫回後檢查指令沒過就還原_資料夾不變(flow, tmp_path, engine, monkeypatch):
    import flow_check
    real = flow_check.check

    def broken(folder):
        res = real(folder)
        res.errors.append("假的錯誤")
        return res
    monkeypatch.setattr(flow_check, "check", broken)
    refused(flow, add_plan(add_video(tmp_path / "add.mp4")), "工具錯誤.*假的錯誤", engine)


def test_補充改寫插入處那份的這段做什麼(flow, tmp_path, engine):
    video_to_flow.insert(add_plan(add_video(tmp_path / "add.mp4")), flow, engine=engine)
    sec = (flow / "交付報告" / "步驟-開始.md").read_text(encoding="utf-8")
    body = sec.split("## 這段做什麼")[1].split("## ")[0]
    assert "找圖點擊「開始」" in body and "找圖（不點）「新鈕」" in body
    names = sorted(p.name for p in (flow / "交付報告").iterdir())
    assert "步驟-開始_2.md" not in names, "插進既有段落時不另開一份"


def test_插入段自成頂層區段時開新的一份_不寫進同名舊檔(flow, tmp_path, engine):
    steps = [{"branch": [{"if": {"find": "新鈕", "frame": 5, "timeout": 3, "on_fail": "skip"},
                          "then": [{"click": [150, 200], "frame": 6}]}]}]
    plan = add_plan(add_video(tmp_path / "add.mp4"), steps=steps, after=2,
                    expect={"repeat": 2})
    rdir = flow / "交付報告"
    (rdir / "分岔-新鈕.md").write_text("# 舊的同名檔\n", encoding="utf-8")
    video_to_flow.insert(plan, flow, engine=engine)
    assert (rdir / "分岔-新鈕.md").read_text(encoding="utf-8") == "# 舊的同名檔\n"
    new = (rdir / "分岔-新鈕_2.md").read_text(encoding="utf-8")
    assert "## 補充" in new and "新鈕" in new
    assert "](分岔-新鈕_2.md)" in (rdir / "總覽.md").read_text(encoding="utf-8")
