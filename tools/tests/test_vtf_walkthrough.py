import json
import os
import subprocess
import sys

import numpy as np

import flowfile
import video_to_flow
from vtf_synth import (CALIBRATION, ROOT, TITLE_TEMPLATES, box, center, make_out,
                       scan_video)

CLICKS = [(20, tuple(center("開始"))), (60, tuple(center("確定"))),
          (85, (60, 230))]
SCENES = ((0, ("開始",)), (40, ("確定",)))
CLEAN = {"開始": 2, "確定": 42}
ABSENT = {"開始": [45], "確定": [5]}


def inside(xy, b, pad=4):
    x, y, w, h = b
    return x - pad <= xy[0] <= x + w + pad and y - pad <= xy[1] <= y + h + pad


def test_照skill程序走一遍產出app開得起來的流程資料夾(tmp_path):
    video = scan_video(tmp_path / "demo.mp4", clicks=CLICKS, scenes=SCENES, title=True,
                       seeds=(99, 99))
    work = tmp_path / "work"

    learn = video_to_flow.scan(video, work / "learn")
    high = [c for c in learn["candidates"]
            if c["confidence"] >= learn["highConfidence"]]
    assert len(high) >= 3
    sample = {"bgr": [int(v) for v in np.median([c["color"] for c in high], axis=0)],
              "tolerance": 60}
    sample_path = work / "effect-sample.json"
    sample_path.write_text(json.dumps(sample), encoding="utf-8")

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
            steps.append({"find_click": name, "frame": CLEAN[name],
                          "at": [c["x"], c["y"]]})
        else:
            steps.append({"click": [c["x"], c["y"]], "frame": c["frame"]})
    assert [next(iter(s)) for s in steps] == ["find_click", "find_click", "click"]
    steps[0]["confirm"], steps[1]["confirm"] = "next", "gone"
    templates.update(TITLE_TEMPLATES)

    out = make_out(tmp_path)
    plan = {"video": str(video), "out": str(out), "name": "走一遍",
            "templates": templates, "steps": steps, "calibration": CALIBRATION,
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
    assert set(os.listdir(folder / "templates")) == {"開始.png", "確定.png", "圖示.png",
                                                     "關閉.png"}
    assert flowfile.missing_templates(folder, r) == []
    s = r["steps"]
    assert [x["type"] for x in s] == ["find_click", "find_click", "click"]
    assert s[0]["confirm"] == "next" and s[1]["confirm"] == "gone"
    assert r["scan_region"] is None
    assert (folder / "交付報告" / "總覽.md").is_file()
    assert all(x.get("target", {}).get("within") for x in s if x["type"] == "find_click")
