"""票 01 — 組裝骨架: 轉換計畫 → app 開得起來的流程存檔 + 交付報告.

只打組裝入口 (`video_to_flow.assemble` 與命令列); 斷言的是存檔內容 (經 app 既有
的存檔讀取打開)、profile 的檔案狀態與報告文字, 不斷言內部怎麼切。
"""
import json
import os
import subprocess
import sys

import cv2
import numpy as np
import pytest

import flowfile
import video_to_flow
from vtf_synth import (ROOT, VIDEO_H, VIDEO_W, box, demo_plan, demo_video,
                       make_profile, read_frame, snapshot)

REGION = [100, 50, VIDEO_W, VIDEO_H]   # 搜尋範圍與影片同尺寸


@pytest.fixture
def demo(tmp_path):
    video = demo_video(tmp_path)
    profile = make_profile(tmp_path, region=REGION)
    return video, profile


def run(plan, engine, **kw):
    return video_to_flow.assemble(plan, engine=engine, **kw)


def new_files(before, profile):
    after = snapshot(profile)
    return sorted(set(after) - set(before))


def test_產出存檔能被app既有的讀取打開且步驟與計畫一致(demo, engine):
    video, profile = demo
    res = run(demo_plan(video, profile), engine)

    assert os.path.dirname(res["flow_path"]) == flowfile.flows_dir(str(profile))
    assert res["flow_path"].endswith("日常" + flowfile.EXT)
    assert flowfile.is_flow_file(res["flow_path"])   # 格式標記齊全
    r = flowfile.read(res["flow_path"])
    steps = r["data"]["steps"]
    assert [s["type"] for s in steps] == ["find_click"] * 3
    assert [s["target"]["template"] for s in steps] == ["開始", "確定", "下一步"]
    import json
    import zipfile
    with zipfile.ZipFile(res["flow_path"]) as z:
        assert json.loads(z.read("flow.json"))["flowFormat"] == flowfile.FORMAT
    assert set(r["images"]) == {"開始", "確定", "下一步"}


def test_範本取自指定影格且保持裁切框原尺寸(demo, engine):
    video, profile = demo
    res = run(demo_plan(video, profile), engine)

    r = flowfile.read(res["flow_path"])
    for name, frame in (("開始", 5), ("確定", 20), ("下一步", 35)):
        img = cv2.imdecode(np.frombuffer(r["images"][name], np.uint8),
                           cv2.IMREAD_COLOR)
        x, y, w, h = box(name)
        assert img.shape[:2] == (h, w)
        want = read_frame(video, frame)[y:y + h, x:x + w]
        assert np.array_equal(img, want)


def test_存檔帶草稿的搜尋範圍_不讀profile校準(demo, engine):
    video, profile = demo
    with open(profile / "calibration.json", "w", encoding="utf-8") as f:
        json.dump({"pair": ["a", "b"], "baseline": 100.0, "scale": 1.0,
                   "fingerprint": None}, f)
    res = run(demo_plan(video, profile), engine)

    r = flowfile.read(res["flow_path"])
    assert r["data"]["scanRegion"] == REGION
    assert r["data"]["coordSpace"] == "region"
    assert "calibration" not in r["data"], "計畫沒指定校準對＝流程沒有校準對"


def test_目標檔名已存在時另取不撞名的檔名且原檔不變(demo, engine):
    video, profile = demo
    existing = profile / "flows" / ("日常" + flowfile.EXT)
    existing.write_bytes(b"original")

    res = run(demo_plan(video, profile), engine)

    assert existing.read_bytes() == b"original"
    assert os.path.basename(res["flow_path"]) == "日常_2" + flowfile.EXT
    assert flowfile.is_flow_file(res["flow_path"])


def test_草稿沒有搜尋範圍時報錯且流程目錄沒有新檔(tmp_path, engine):
    video = demo_video(tmp_path)
    profile = make_profile(tmp_path, region=None)
    before = snapshot(profile)

    with pytest.raises(video_to_flow.ToolError, match="搜尋範圍"):
        run(demo_plan(video, profile), engine)

    assert snapshot(profile) == before


def test_profile既有資料一律不動只多出存檔與報告(demo, engine):
    video, profile = demo
    (profile / "workspace" / "templates").mkdir(parents=True)
    (profile / "workspace" / "templates" / "舊圖.png").write_bytes(b"png")
    (profile / "flows" / ("其他" + flowfile.EXT)).write_bytes(b"other")
    with open(profile / "calibration.json", "w", encoding="utf-8") as f:
        json.dump({"pair": ["a", "b"], "baseline": 100.0, "scale": 1.0,
                   "fingerprint": None}, f)
    before = snapshot(profile)

    res = run(demo_plan(video, profile), engine)

    after = snapshot(profile)
    assert {k: after[k] for k in before} == before
    added = new_files(before, profile)
    assert added == sorted(["flows/日常" + flowfile.EXT, "flows/日常.md"])
    assert res["report_path"].endswith("日常.md")


def test_交付報告列出搜尋範圍影片同尺度步驟數與範本數(demo, engine):
    video, profile = demo
    res = run(demo_plan(video, profile), engine)

    with open(res["report_path"], encoding="utf-8") as f:
        text = f.read()
    assert "搜尋範圍" in text and "100, 50, 480, 270" in text
    assert "影片與實際畫面同尺度" in text
    assert "步驟數：3" in text
    assert "範本數：3" in text


def test_組裝失敗不留半成品且修好計畫後可重跑(demo, engine):
    video, profile = demo
    before = snapshot(profile)
    bad = demo_plan(video, profile)
    bad["templates"]["開始"]["frame"] = 999   # 影片只有 45 幀

    with pytest.raises(video_to_flow.ToolError, match="999"):
        run(bad, engine)
    assert snapshot(profile) == before

    first = run(demo_plan(video, profile), engine)
    second = run(demo_plan(video, profile), engine)
    assert os.path.basename(first["flow_path"]) == "日常" + flowfile.EXT
    assert os.path.basename(second["flow_path"]) == "日常_2" + flowfile.EXT
    assert not [k for k in snapshot(profile) if k.endswith(".tmp")]


def test_報告位置可由呼叫端指定(demo, engine, tmp_path):
    video, profile = demo
    out = tmp_path / "out" / "報告.md"
    res = run(demo_plan(video, profile), engine, report_path=str(out))
    assert res["report_path"] == str(out)
    assert out.is_file()
    assert not (profile / "flows" / "日常.md").exists()


def test_計畫檔內的相對路徑以計畫檔所在目錄為準(demo, engine, tmp_path):
    video, profile = demo
    plan = demo_plan(os.path.relpath(video, tmp_path),
                     os.path.relpath(profile, tmp_path))
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    res = run(str(plan_path), engine)
    assert os.path.isfile(res["flow_path"])


def test_命令列入口可指定計畫檔(demo, tmp_path):
    video, profile = demo
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(demo_plan(video, profile), ensure_ascii=False),
                         encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "video_to_flow"), "assemble",
         str(plan_path)],
        capture_output=True, timeout=300)

    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    assert proc.returncode == 0, err
    flow = profile / "flows" / ("日常" + flowfile.EXT)
    assert flow.is_file()
    assert str(flow) in out


def test_命令列報錯時以非零結束並印出原因(tmp_path):
    video = demo_video(tmp_path)
    profile = make_profile(tmp_path, region=None)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(demo_plan(video, profile), ensure_ascii=False),
                         encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "video_to_flow"), "assemble",
         str(plan_path)],
        capture_output=True, timeout=300)

    assert proc.returncode != 0
    assert "搜尋範圍" in proc.stderr.decode("utf-8", "replace")


def test_報告寫不出來時不留下存檔(demo, engine, tmp_path):
    video, profile = demo
    blocker = tmp_path / "是檔案不是目錄"
    blocker.write_bytes(b"x")
    before = snapshot(profile)

    with pytest.raises(OSError):
        run(demo_plan(video, profile), engine,
            report_path=str(blocker / "報告.md"))

    assert snapshot(profile) == before


def test_預設報告與存檔同名並排即使有殘留的同名報告(demo, engine):
    video, profile = demo
    stale = profile / "flows" / "日常.md"
    stale.write_text("舊報告", encoding="utf-8")

    res = run(demo_plan(video, profile), engine)

    assert os.path.basename(res["flow_path"]) == "日常_2" + flowfile.EXT
    assert os.path.basename(res["report_path"]) == "日常_2.md"
    assert stale.read_text(encoding="utf-8") == "舊報告"
