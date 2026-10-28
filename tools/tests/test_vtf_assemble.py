import json
import os
import subprocess
import sys

import cv2
import numpy as np
import pytest

import video_to_flow
from vtf_synth import (ROOT, box, demo_plan, demo_video, make_out, read_frame,
                       saved_flow, snapshot)

REPORT = "交付報告"
TEMPLATES = ["開始.png", "確定.png", "下一步.png", "圖示.png", "關閉.png"]


@pytest.fixture
def demo(tmp_path):
    return demo_video(tmp_path), make_out(tmp_path)


def run(plan, engine, **kw):
    return video_to_flow.assemble(plan, engine=engine, **kw)


def test_產出流程資料夾能被app的讀檔打開且步驟與計畫一致(demo, engine):
    video, out = demo
    res = run(demo_plan(video, out), engine)

    assert res["flow_path"] == str(out / "日常")
    assert sorted(os.listdir(res["flow_path"])) == sorted(["flow.yaml", "templates", REPORT])
    flow = saved_flow(res)
    steps = flow["steps"]
    assert [s["type"] for s in steps] == ["find_click"] * 3
    assert [s["target"]["template"] for s in steps] == ["開始", "確定", "下一步"]
    assert sorted(os.listdir(os.path.join(res["flow_path"], "templates"))) == sorted(TEMPLATES)
    with open(os.path.join(res["flow_path"], "flow.yaml"), encoding="utf-8") as f:
        assert f.read().startswith("format: 1\n")


def test_範本取自指定影格且保持裁切框原尺寸(demo, engine):
    video, out = demo
    res = run(demo_plan(video, out), engine)

    for name, frame in (("開始", 5), ("確定", 20), ("下一步", 35)):
        with open(os.path.join(res["flow_path"], "templates", name + ".png"), "rb") as f:
            img = cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)
        x, y, w, h = box(name)
        assert img.shape[:2] == (h, w)
        want = read_frame(video, frame)[y:y + h, x:x + w]
        assert np.array_equal(img, want)


def test_不寫搜尋範圍_拍攝位置相對座標基準點(demo, engine):
    from vtf_synth import ANCHOR, center
    video, out = demo
    res = run(demo_plan(video, out), engine)

    flow = saved_flow(res)
    assert flow["scan_region"] is None, "不寫搜尋範圍＝全螢幕"
    cx, cy = center("開始")
    assert flow["template_pos"]["開始"] == [cx - ANCHOR[0], cy - ANCHOR[1]]


def test_同名資料夾已存在時加序號且原資料夾不變(demo, engine):
    video, out = demo
    (out / "日常").mkdir()
    (out / "日常" / "原本的.txt").write_text("原本", encoding="utf-8")

    res = run(demo_plan(video, out), engine)

    assert os.listdir(out / "日常") == ["原本的.txt"]
    assert res["flow_path"] == str(out / "日常_2")
    assert saved_flow(res)["steps"]


def test_輸出位置既有資料一律不動只多出一個流程資料夾(demo, engine):
    video, out = demo
    (out / "別的流程").mkdir()
    (out / "別的流程" / "flow.yaml").write_text("format: 1\nsteps: []\n", encoding="utf-8")
    before = snapshot(out)

    res = run(demo_plan(video, out), engine)

    after = snapshot(out)
    assert {k: after[k] for k in before} == before
    added = sorted(set(after) - set(before))
    assert added == sorted(["日常/flow.yaml", f"日常/{REPORT}/總覽.md",
                            f"日常/{REPORT}/步驟-開始.md"]
                           + [f"日常/templates/{t}" for t in TEMPLATES])
    assert res["report_path"] == str(out / "日常" / REPORT)


def test_組裝失敗不留半成品且修好計畫後可重跑(demo, engine):
    video, out = demo
    before = snapshot(out)
    bad = demo_plan(video, out)
    bad["templates"]["開始"]["frame"] = 999

    with pytest.raises(video_to_flow.ToolError, match="999"):
        run(bad, engine)
    assert snapshot(out) == before
    assert os.listdir(out) == []

    first = run(demo_plan(video, out), engine)
    second = run(demo_plan(video, out), engine)
    assert os.path.basename(first["flow_path"]) == "日常"
    assert os.path.basename(second["flow_path"]) == "日常_2"
    assert sorted(os.listdir(out)) == ["日常", "日常_2"], "沒有殘留的暫存資料夾"


def test_輸出位置可由參數指定_優先於計畫(demo, engine, tmp_path):
    video, out = demo
    other = tmp_path / "別處"
    res = run(demo_plan(video, out), engine, out_dir=str(other))
    assert res["flow_path"] == str(other / "日常")
    assert os.listdir(out) == []


def test_沒指定輸出位置時建在流程存放區(demo, engine):
    import apppaths
    video, out = demo
    plan = demo_plan(video, out)
    del plan["out"]
    res = run(plan, engine)
    assert res["flow_path"] == os.path.join(apppaths.flows_root(), "日常")
    assert os.listdir(out) == []


def test_計畫寫了已退場的頂層欄位就報錯(demo, engine):
    video, out = demo
    for key in ("profile", "reportPath", "busyTarget", "retryIntervalMs"):
        plan = demo_plan(video, out)
        plan[key] = "x"
        with pytest.raises(video_to_flow.ToolError, match=key):
            run(plan, engine)


def test_計畫檔內的相對路徑以計畫檔所在目錄為準(demo, engine, tmp_path):
    video, out = demo
    plan = demo_plan(os.path.relpath(video, tmp_path), os.path.relpath(out, tmp_path))
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    res = run(str(plan_path), engine)
    assert res["flow_path"] == str(out / "日常")


def test_命令列入口可指定計畫檔與輸出位置(demo, tmp_path):
    video, out = demo
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(demo_plan(video, out), ensure_ascii=False),
                         encoding="utf-8")
    other = tmp_path / "命令列指定"

    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "video_to_flow"), "assemble",
         str(plan_path), "--out", str(other)],
        capture_output=True, timeout=300)

    stdout = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    assert proc.returncode == 0, err
    folder = other / "日常"
    assert (folder / "flow.yaml").is_file()
    assert str(folder) in stdout


def test_命令列報錯時以非零結束並印出原因(tmp_path):
    video = demo_video(tmp_path)
    plan = demo_plan(video, make_out(tmp_path))
    plan["profile"] = "x"
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "video_to_flow"), "assemble",
         str(plan_path)],
        capture_output=True, timeout=300)

    assert proc.returncode != 0
    assert "profile" in proc.stderr.decode("utf-8", "replace")


def test_寫不出來時輸出位置不留下任何東西(demo, engine, tmp_path):
    video, _ = demo
    blocker = tmp_path / "是檔案不是目錄"
    blocker.write_bytes(b"x")

    with pytest.raises(OSError):
        run(demo_plan(video, blocker), engine)

    assert blocker.read_bytes() == b"x"


def test_寫完自己跑檢查指令_有錯就當工具錯誤且不留半成品(demo, engine, monkeypatch):
    import flow_check
    video, out = demo
    real = flow_check.check

    def broken(folder):
        res = real(folder)
        res.errors.append("假的錯誤")
        return res
    monkeypatch.setattr(flow_check, "check", broken)
    with pytest.raises(video_to_flow.ToolError, match="工具錯誤.*假的錯誤"):
        run(demo_plan(video, out), engine)
    assert os.listdir(out) == []
