"""自我驗證與`待重拍` (拾取檢查三項; 不唯一標待重拍、流程照寫).

用真引擎 (比照引擎端以合成影像跑真引擎的既有測試做法), 只打組裝入口;
斷言存檔裡的範本名與步驟引用、組裝結果的驗證摘要與報告文字。
"""
import pytest

import flowfile
import video_to_flow
from vtf_synth import (BLANK, BUTTONS, FRAME, box, center, demo_plan,
                       demo_templates, demo_video, find, make_out, screen, timeline,
                       write_video)


@pytest.fixture
def demo(tmp_path):
    return demo_video(tmp_path), make_out(tmp_path)


def run(plan, engine):
    return video_to_flow.assemble(plan, engine=engine)


def saved(res):
    return flowfile.read_flow(res["flow_path"])


def images(res):
    """流程資料夾 templates/ 裡的範本名."""
    import os
    return {fn[:-4] for fn in os.listdir(os.path.join(res["flow_path"], "templates"))}


def report(res):
    import os
    with open(os.path.join(res["report_path"], "總覽.md"), encoding="utf-8") as f:
        return f.read()


def test_框在清楚按鈕上的範本驗證通過且名稱不變(demo, engine):
    video, profile = demo
    res = run(demo_plan(video, profile), engine)

    assert res["retake"] == {}
    assert images(res) == {"開始", "確定", "下一步", "圖示", "關閉"}
    assert res["verification"] == "full"


def test_框到空白處的範本標待重拍_名稱不加前綴只列在報告(demo, engine):
    video, profile = demo
    templates = demo_templates()
    templates["空白"] = {"frame": 5, "box": [BLANK[0] + 10, BLANK[1] + 10, 40, 30]}
    steps = [find("開始"),
             {"find_click": "空白", "frame": 5, "at": [BLANK[0] + 30, BLANK[1] + 25]},
             find("確定", confirm={"appear": "空白"}),
             find("下一步")]

    res = run(demo_plan(video, profile, steps=steps, templates=templates), engine)

    assert list(res["retake"]) == ["空白"]
    r = saved(res)
    assert "空白" in images(res), "範本名與檔名不帶待重拍標記"
    s = r["steps"]
    assert s[1]["target"]["template"] == "空白"
    assert s[2]["confirm_target"]["template"] == "空白"
    assert set(flowfile.template_refs(r)) == images(res)
    assert "| 空白 |" in report(res) and "待重拍_空白" not in report(res)
    assert s[1]["target"]["within"], "待重拍的範本照樣有固定矩形 (用計畫的取材框算)"


def test_在該點的那一幀找不到的範本標待重拍(demo, engine):
    video, profile = demo
    # 「確定」只在幀 15-29 出現; 這一步卻說它在第 40 幀 (畫面 C) 點了它
    steps = [find("開始"), find("確定", frame=40), find("下一步")]

    res = run(demo_plan(video, profile, steps=steps), engine)

    assert list(res["retake"]) == ["確定"]
    assert any("找不到" in why for why in res["retake"]["確定"])
    assert saved(res)["steps"][1]["target"]["template"] == "確定"


def test_在該找不到的幀也匹配到的範本標待重拍原因寫出現前就匹配(demo, engine):
    video, profile = demo
    templates = demo_templates()
    templates["開始"]["absent"] = [2]     # 幀 2 其實已經有「開始」了

    res = run(demo_plan(video, profile, templates=templates), engine)

    assert list(res["retake"]) == ["開始"]
    assert any("出現前就匹配" in why for why in res["retake"]["開始"])
    assert "出現前就匹配" in report(res)


def test_該找不到的幀確實沒有時驗證通過(demo, engine):
    video, profile = demo
    templates = demo_templates()
    templates["確定"]["absent"] = [5, 10]   # 畫面 A 還沒有「確定」

    res = run(demo_plan(video, profile, templates=templates), engine)

    assert res["retake"] == {}


def moving_video(tmp_path):
    """「開始」先在 (60, 40), 第 10 幀起移到 (200, 180)."""
    btn = BUTTONS["開始"]
    frames = timeline((screen([(btn, 60, 40)], title=True), 10),
                      (screen([(btn, 200, 180)], title=True), 10))
    return write_video(tmp_path / "moving.mp4", frames)


def test_找到但中心偏離預期位置過遠標待重拍原因寫位置不符(tmp_path, engine):
    video = moving_video(tmp_path)
    profile = make_out(tmp_path)
    templates = {"開始": {"frame": 5, "box": box("開始"), "present": [15]}}
    steps = [find("開始")]

    res = run(demo_plan(video, profile, steps=steps, templates=templates), engine)

    assert list(res["retake"]) == ["開始"]
    assert any("位置不符" in why for why in res["retake"]["開始"])


def test_出現幀寫明新位置時驗證通過(tmp_path, engine):
    video = moving_video(tmp_path)
    profile = make_out(tmp_path)
    w, h = box("開始")[2:]
    templates = {"開始": {"frame": 5, "box": box("開始"),
                          "present": [{"frame": 15, "at": [200 + w // 2, 180 + h // 2]}]}}

    res = run(demo_plan(video, profile, steps=[find("開始")],
                        templates=templates), engine)

    assert res["retake"] == {}


def test_計畫標示無乾淨影格的範本不論驗證結果都標待重拍(demo, engine):
    video, profile = demo
    templates = demo_templates()
    templates["確定"]["clean"] = False

    res = run(demo_plan(video, profile, templates=templates), engine)

    assert list(res["retake"]) == ["確定"]
    assert any("乾淨影格" in why for why in res["retake"]["確定"])


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
    # 第 15 幀起「開始」搬到 (200, 180); 步驟卻說在第 15 幀點了原位置
    video = moving_video(tmp_path)
    profile = make_out(tmp_path)
    templates = {"開始": {"frame": 5, "box": box("開始")}}
    steps = [find("開始", frame=15)]

    res = run(demo_plan(video, profile, steps=steps, templates=templates), engine)

    assert list(res["retake"]) == ["開始"]
    assert any("位置不符" in why for why in res["retake"]["開始"])


# ---------- `拾取檢查`: 縮放餘裕與唯一 (照固定矩形查) ----------

def twin_video(tmp_path, dx=150):
    """每一幀都有兩個一模一樣的「開始」(第二個在右邊 dx 處, 同一列)."""
    from vtf_synth import POS
    x, y = POS["開始"]
    frames = [screen([(BUTTONS["開始"], x, y), (BUTTONS["開始"], x + dx, y)],
                     title=True)] * 30
    return write_video(tmp_path / "twin.mp4", frames)


def test_同款在固定矩形外_唯一照框查所以通過(tmp_path, engine):
    video = twin_video(tmp_path)
    out = make_out(tmp_path)
    templates = {"開始": {"frame": 5, "box": box("開始")}}
    res = run(demo_plan(video, out, steps=[find("開始")], templates=templates), engine)
    assert res["retake"] == {}


def test_同款在固定矩形內_沒設挑選規則_標待重拍原因寫唯一_框不縮(tmp_path, engine):
    video = twin_video(tmp_path)
    out = make_out(tmp_path)
    templates = {"開始": {"frame": 5, "box": box("開始")}}
    steps = [find("開始", scroll="horizontal")]     # 橫向捲動軸: 框拉到影片兩端, 兩個都在框裡
    res = run(demo_plan(video, out, steps=steps, templates=templates), engine)
    assert list(res["retake"]) == ["開始"]
    why = res["retake"]["開始"]
    assert any("唯一" in w and "2 個匹配" in w for w in why), why
    assert saved(res)["steps"][0]["target"]["within"][2] == 480, "不自動縮框"
    assert "換一張畫面上唯一的圖當參考點" in report(res), "待重拍建議表有唯一的修法"


def test_同款在框內_設了由上到下第1個_不查唯一(tmp_path, engine):
    video = twin_video(tmp_path)
    out = make_out(tmp_path)
    templates = {"開始": {"frame": 5, "box": box("開始")}}
    steps = [find("開始", pick={"left": 1}, scroll="horizontal")]
    res = run(demo_plan(video, out, steps=steps, templates=templates), engine)
    assert res["retake"] == {}


def test_縮放餘裕沒過_標待重拍並寫原因與分數(demo, engine, monkeypatch):
    from automation import pickcheck
    video, profile = demo
    real = pickcheck.scale_margin

    def flaky(detector, screen_, origin_, tgt, anchor=None, scale=1.0, origin=None):
        if tgt["template"] == "確定":
            return [pickcheck.PickWarning(pickcheck.SCALE, "確定",
                                      "縮到 ×0.85（畫面倍率 ×0.850）時範本「確定」粗篩最高 0.620 貼近門檻（要 ≥ 0.7）",
                                      scale=0.85, gate="match", score=0.62)]
        return real(detector, screen_, origin_, tgt, anchor, scale, origin)
    monkeypatch.setattr(pickcheck, "scale_margin", flaky)
    res = run(demo_plan(video, profile), engine)
    assert list(res["retake"]) == ["確定"]
    [why] = res["retake"]["確定"]
    assert why.startswith("縮放餘裕：") and "0.620" in why and "×0.85" in why
    assert "重截或裁小" in report(res)
    assert saved(res)["steps"][1]["target"]["template"] == "確定"


def test_合成按鈕的縮放餘裕本身通過(demo, engine):
    """真的跑拾取檢查 (沒有樁): 清楚的按鈕縮到 ×0.85 / ×1.15 都還找得到."""
    video, profile = demo
    res = run(demo_plan(video, profile), engine)
    assert res["retake"] == {}
