"""票 03 — 自我驗證與`待重拍`.

用真引擎 (比照引擎端以合成影像跑真引擎的既有測試做法), 只打組裝入口;
斷言存檔裡的範本名與步驟引用、組裝結果的驗證摘要與報告文字。
"""
import pytest

import flowfile
import video_to_flow
from vtf_synth import (BLANK, BUTTONS, FRAME, VIDEO_H, VIDEO_W, box, center,
                       demo_plan, demo_templates, demo_video, find, make_profile,
                       screen, timeline, write_video)

FP = {"x": 0, "y": 0, "w": 1920, "h": 1080}
REGION = [0, 0, VIDEO_W, VIDEO_H]
RETAKE = "待重拍_"


@pytest.fixture
def demo(tmp_path):
    return demo_video(tmp_path), make_profile(tmp_path, region=REGION)


def run(plan, engine):
    return video_to_flow.assemble(plan, engine=engine, fingerprint=FP)


def saved(res):
    return flowfile.read(res["flow_path"])


def report(res):
    with open(res["report_path"], encoding="utf-8") as f:
        return f.read()


def test_框在清楚按鈕上的範本驗證通過且名稱不變(demo, engine):
    video, profile = demo
    res = run(demo_plan(video, profile), engine)

    assert res["retake"] == {}
    assert set(saved(res)["images"]) == {"開始", "確定", "下一步"}
    assert res["verification"] == "full"


def test_框到空白處的範本標待重拍且步驟引用與存檔圖名同步(demo, engine):
    video, profile = demo
    templates = demo_templates()
    templates["空白"] = {"frame": 5, "box": [BLANK[0] + 10, BLANK[1] + 10, 40, 30]}
    steps = [find("開始"),
             {"type": "find_click", "template": "空白", "frame": 5,
              "at": [BLANK[0] + 30, BLANK[1] + 25]},
             find("確定", confirm="appear", confirmTemplate="空白"),
             find("下一步")]

    res = run(demo_plan(video, profile, steps=steps, templates=templates), engine)

    assert list(res["retake"]) == [RETAKE + "空白"]
    r = saved(res)
    assert RETAKE + "空白" in r["images"] and "空白" not in r["images"]
    s = r["data"]["steps"]
    assert s[1]["target"]["template"] == RETAKE + "空白"
    assert s[2]["confirmTarget"]["template"] == RETAKE + "空白"
    assert flowfile.used_templates(s) == sorted(r["images"])
    assert RETAKE + "空白" in report(res)


def test_在該點的那一幀找不到的範本標待重拍(demo, engine):
    video, profile = demo
    # 「確定」只在幀 15-29 出現; 這一步卻說它在第 40 幀 (畫面 C) 點了它
    steps = [find("開始"), find("確定", frame=40), find("下一步")]

    res = run(demo_plan(video, profile, steps=steps), engine)

    assert list(res["retake"]) == [RETAKE + "確定"]
    assert any("找不到" in why for why in res["retake"][RETAKE + "確定"])
    assert saved(res)["data"]["steps"][1]["target"]["template"] == RETAKE + "確定"


def test_在該找不到的幀也匹配到的範本標待重拍原因寫出現前就匹配(demo, engine):
    video, profile = demo
    templates = demo_templates()
    templates["開始"]["absent"] = [2]     # 幀 2 其實已經有「開始」了

    res = run(demo_plan(video, profile, templates=templates), engine)

    assert list(res["retake"]) == [RETAKE + "開始"]
    assert any("出現前就匹配" in why for why in res["retake"][RETAKE + "開始"])
    assert "出現前就匹配" in report(res)


def test_該找不到的幀確實沒有時驗證通過(demo, engine):
    video, profile = demo
    templates = demo_templates()
    templates["確定"]["absent"] = [5, 10]   # 畫面 A 還沒有「確定」

    res = run(demo_plan(video, profile, templates=templates), engine)

    assert res["retake"] == {}


def moving_video(tmp_path):
    """「開始」先在 (60, 40), 第 10 幀起移到 (300, 180)."""
    btn = BUTTONS["開始"]
    frames = timeline((screen([(btn, 60, 40)]), 10),
                      (screen([(btn, 300, 180)]), 10))
    return write_video(tmp_path / "moving.mp4", frames)


def test_找到但中心偏離預期位置過遠標待重拍原因寫位置不符(tmp_path, engine):
    video = moving_video(tmp_path)
    profile = make_profile(tmp_path, region=REGION)
    templates = {"開始": {"frame": 5, "box": box("開始"), "present": [15]}}
    steps = [find("開始")]

    res = run(demo_plan(video, profile, steps=steps, templates=templates), engine)

    assert list(res["retake"]) == [RETAKE + "開始"]
    assert any("位置不符" in why for why in res["retake"][RETAKE + "開始"])


def test_出現幀寫明新位置時驗證通過(tmp_path, engine):
    video = moving_video(tmp_path)
    profile = make_profile(tmp_path, region=REGION)
    w, h = box("開始")[2:]
    templates = {"開始": {"frame": 5, "box": box("開始"),
                          "present": [{"frame": 15, "at": [300 + w // 2, 180 + h // 2]}]}}

    res = run(demo_plan(video, profile, steps=[find("開始")],
                        templates=templates), engine)

    assert res["retake"] == {}


def test_計畫標示無乾淨影格的範本不論驗證結果都標待重拍(demo, engine):
    video, profile = demo
    templates = demo_templates()
    templates["確定"]["clean"] = False

    res = run(demo_plan(video, profile, templates=templates), engine)

    assert list(res["retake"]) == [RETAKE + "確定"]
    assert any("乾淨影格" in why for why in res["retake"][RETAKE + "確定"])


def test_驗證結果帶每張範本在參考幀實際找到的框(demo, engine):
    video, profile = demo
    res = run(demo_plan(video, profile), engine)

    for name in ("開始", "確定", "下一步"):
        found = res["found"][name][FRAME[name]]
        x, y, w, h = found
        cx, cy = center(name)
        assert abs(x + w // 2 - cx) <= 3 and abs(y + h // 2 - cy) <= 3


@pytest.fixture
def coarse_engine(monkeypatch):
    """深度驗證模型載不起來的引擎 (降級只剩粗篩)."""
    import subject_detection.verification as verification
    from subject_detection import Engine

    def broken(*a, **kw):
        raise RuntimeError("no model")

    monkeypatch.setattr(verification, "Verifier", broken)
    with pytest.warns(UserWarning):
        eng = Engine()
    assert eng.coarse_only
    return eng


def test_只能粗篩時報告明說驗證不完整(demo, coarse_engine):
    video, profile = demo
    res = run(demo_plan(video, profile), coarse_engine)

    assert res["verification"] == "coarse"
    assert "驗證不完整" in report(res)


def test_只能粗篩時命令列輸出明說驗證不完整(demo, coarse_engine, tmp_path,
                                   monkeypatch, capsys):
    import json

    from subject_detection import engine as engine_mod
    from video_to_flow import cli

    video, profile = demo
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(demo_plan(video, profile), ensure_ascii=False),
                         encoding="utf-8")
    monkeypatch.setattr(engine_mod, "Engine", lambda: coarse_engine)

    assert cli.main(["assemble", str(plan_path)]) == 0
    assert "驗證不完整" in capsys.readouterr().out


def test_該點的那一幀找到的是別處的同款圖時標待重拍原因寫位置不符(tmp_path, engine):
    # 第 15 幀起「開始」搬到 (300, 180); 步驟卻說在第 15 幀點了原位置
    video = moving_video(tmp_path)
    profile = make_profile(tmp_path, region=REGION)
    templates = {"開始": {"frame": 5, "box": box("開始")}}
    steps = [find("開始", frame=15)]

    res = run(demo_plan(video, profile, steps=steps, templates=templates), engine)

    assert list(res["retake"]) == [RETAKE + "開始"]
    assert any("位置不符" in why for why in res["retake"][RETAKE + "開始"])
