"""票 07 — 用合成影片照 video-to-flow skill 的程序走一遍.

學特效樣本 (退路掃描 → 取色 → 帶樣本重掃) → 依候選寫轉換計畫 (以程式扮演
Claude 的判斷: 點在按鈕上＝找圖、其餘＝相對座標點擊) → 命令列組裝 → 產出的
存檔經 app 既有的工作區載入打開。只打兩個入口。
"""
import json
import os
import subprocess
import sys

import numpy as np

import flowfile
import video_to_flow
from vtf_synth import (ROOT, VIDEO_H, VIDEO_W, box, center, make_out,
                       scan_video)

CLICKS = [(20, tuple(center("開始"))), (60, tuple(center("確定"))),
          (85, (60, 230))]                       # 最後一下點在空白處
SCENES = ((0, ("開始",)), (40, ("確定",)))
CLEAN = {"開始": 2, "確定": 42}                  # 游標還沒移過來的乾淨影格
ABSENT = {"開始": [45], "確定": [5]}


def inside(xy, b, pad=4):
    x, y, w, h = b
    return x - pad <= xy[0] <= x + w + pad and y - pad <= xy[1] <= y + h + pad


def test_照skill程序走一遍產出app開得起來的流程資料夾(tmp_path):
    video = scan_video(tmp_path / "demo.mp4", clicks=CLICKS, scenes=SCENES)
    work = tmp_path / "work"

    # 學特效樣本: 退路掃描的高信心候選取色中位數
    learn = video_to_flow.scan(video, work / "learn")
    high = [c for c in learn["candidates"]
            if c["confidence"] >= learn["highConfidence"]]
    assert len(high) >= 3
    sample = {"bgr": [int(v) for v in np.median([c["color"] for c in high], axis=0)],
              "tolerance": 60}
    sample_path = work / "effect-sample.json"
    sample_path.write_text(json.dumps(sample), encoding="utf-8")

    # 帶樣本掃描 → 覆核 (這裡: 只留高信心) → 依點擊語意寫步驟
    res = video_to_flow.scan(video, work / "scan", sample=str(sample_path))
    clicks = [c for c in res["candidates"] if c["confidence"] >= res["highConfidence"]]
    assert len(clicks) == len(CLICKS)
    steps, templates = [], {}
    for c in clicks:
        on = [n for n in CLEAN if inside((c["x"], c["y"]), box(n))]
        if on:
            name = on[0]
            templates[name] = {"frame": CLEAN[name], "box": box(name),
                               "absent": ABSENT[name]}
            steps.append({"type": "find_click", "template": name,
                          "frame": CLEAN[name], "at": [c["x"], c["y"]]})
        else:
            steps.append({"type": "click", "at": [c["x"], c["y"]]})
    assert [s["type"] for s in steps] == ["find_click", "find_click", "click"]

    out = make_out(tmp_path)
    plan = {"video": str(video), "out": str(out), "name": "走一遍",
            "templates": templates, "steps": steps,
            "report": {"branches": ["(示範) 這裡可能跳出彈窗"]}}
    plan_path = work / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "video_to_flow"), "assemble",
         str(plan_path)], capture_output=True, timeout=600)
    stdout = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert "待重拍" not in stdout

    folder = out / "走一遍"
    assert os.listdir(out) == ["走一遍"]
    r = flowfile.read_flow(folder)
    assert sorted(os.listdir(folder / "templates")) == ["開始.png", "確定.png"] or \
        set(os.listdir(folder / "templates")) == {"開始.png", "確定.png"}
    assert flowfile.missing_templates(folder, r) == []
    s = r["steps"]
    assert [x["type"] for x in s] == ["find_click", "find_click", "click"]
    assert s[0]["confirm"] == "next" and s[1]["confirm"] == "gone"
    assert r["scan_region"] is None
    assert (folder / "交付報告.md").is_file()
