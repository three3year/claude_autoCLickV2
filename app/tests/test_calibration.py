"""`校準`模組純邏輯: 資料存取、未校準判定、量測、改寫、重定基準 (暫存目錄真測).

詞彙見 app/CONTEXT.md「校準與畫面倍率」; 檔案邏輯照 test_profile_store 的
手法真檔案測、量測照 harness 的假 query 直接餵。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import calibration  # noqa: E402
from harness import Vision  # noqa: E402

FP_A = {"x": 0, "y": 0, "w": 1920, "h": 1080}
FP_B = {"x": 0, "y": 0, "w": 2560, "h": 1440}


def make_cal(pair=("a", "b"), baseline=100.0, scale=1.0, fp=FP_A):
    return {"pair": list(pair), "baseline": baseline,
            "scale": scale, "fingerprint": fp}


# ---------- 校準資料存取 ----------

def test_校準資料roundtrip(tmp_path):
    cal = make_cal(scale=1.25)
    calibration.save(str(tmp_path), cal)
    assert calibration.load(str(tmp_path)) == cal


def test_缺檔等於沒有校準對(tmp_path):
    assert calibration.load(str(tmp_path)) is None


def test_壞檔與不成形的資料視同沒有校準對(tmp_path):
    p = calibration.path(str(tmp_path))
    with open(p, "w", encoding="utf-8") as f:
        f.write("not json")
    assert calibration.load(str(tmp_path)) is None
    calibration.save(str(tmp_path), {"pair": ["only-one"], "baseline": 100})
    assert calibration.load(str(tmp_path)) is None
    calibration.save(str(tmp_path), {"pair": ["a", "b"], "baseline": 0})
    assert calibration.load(str(tmp_path)) is None, "基準距離必須是正數"


# ---------- 未校準判定 (票 03) ----------

def test_從未校準_scale為null_視為未校準():
    cal = make_cal(scale=None, fp=None)
    assert calibration.is_uncalibrated(cal, FP_A)


def test_指紋不符視為未校準_整包profile複製到別台機器():
    """倍率是別台機器量的: 指紋認出來, 警告機制不被舊倍率騙過."""
    cal = make_cal(scale=1.5, fp=FP_A)
    assert not calibration.is_uncalibrated(cal, FP_A)
    assert calibration.is_uncalibrated(cal, FP_B)


def test_執行期倍率_沒有校準對或未校準都代入1():
    assert calibration.effective_scale(None, FP_A) == 1.0
    assert calibration.effective_scale(make_cal(scale=None, fp=None), FP_A) == 1.0
    assert calibration.effective_scale(make_cal(scale=1.5, fp=FP_A), FP_B) == 1.0
    assert calibration.effective_scale(make_cal(scale=1.5, fp=FP_A), FP_A) == 1.5


def test_執行警告只在未校準時出現():
    assert calibration.run_warning(None, FP_A) is None, "沒有校準對完全不警告"
    assert calibration.run_warning(make_cal(fp=FP_A), FP_A) is None
    msg = calibration.run_warning(make_cal(scale=None, fp=None), FP_A)
    assert msg and "尚未校準" in msg and "倍率 1" in msg


def test_拾取守門只在未校準時擋下():
    assert calibration.pick_gate_message(None, FP_A) is None, "沒有校準對不擋"
    assert calibration.pick_gate_message(make_cal(fp=FP_A), FP_A) is None
    msg = calibration.pick_gate_message(make_cal(scale=None, fp=None), FP_A)
    assert msg and "校準" in msg


# ---------- 量測 (票 02) ----------

def _grab(vision, region=None):
    screen, _ = vision.grab(region)
    return screen


def test_量測回傳兩匹配框中心的直線距離():
    v = Vision()
    v.plan("a", [(100, 100)])
    v.plan("b", [(400, 500)])  # 距離 = hypot(300, 400) = 500
    dist, missing = calibration.measure(v.query, _grab(v), ("a", "b"))
    assert missing == []
    assert dist == 500.0


def test_量測失敗指明哪一張沒找到():
    v = Vision()
    v.plan("a", [None])
    v.plan("b", [(400, 500)])
    dist, missing = calibration.measure(v.query, _grab(v), ("a", "b"))
    assert dist is None
    assert missing == ["a"]


def test_量測兩張都沒找到全部列出():
    v = Vision()
    v.plan("a", [None])
    v.plan("b", [None])
    dist, missing = calibration.measure(v.query, _grab(v), ("a", "b"))
    assert dist is None
    assert missing == ["a", "b"]


def test_量測在搜尋範圍內找時距離不受範圍原點影響():
    """兩張圖同一次擷取, 範圍原點在距離上互相抵銷."""
    v = Vision()
    v.plan("a", [(300, 300)])
    v.plan("b", [(600, 700)])
    dist, _ = calibration.measure(v.query, _grab(v, [200, 250, 800, 600]),
                                  ("a", "b"))
    assert dist == 500.0


# ---------- 偏移改寫 (票 04 / 05 共用) ----------

def test_改寫涵蓋三類偏移含拖曳兩端點():
    steps = [
        {"type": "find_click", "template": "a", "offsetX": 10, "offsetY": -20},
        {"type": "click", "x": 30, "y": 40},
        {"type": "click", "x": 5, "y": -5, "mode": "prev"},
        {"type": "drag", "x1": 10, "y1": 10, "x2": 60, "y2": 80},
        {"type": "wait", "ms": 500},
        {"type": "loop_start", "count": 3},
        {"type": "key", "keys": "enter"},
    ]
    calibration.scale_steps(steps, 1.5)
    assert (steps[0]["offsetX"], steps[0]["offsetY"]) == (15, -30)
    assert (steps[1]["x"], steps[1]["y"]) == (45, 60)
    assert (steps[2]["x"], steps[2]["y"]) == (8, -8), "相對座標也要換算; 四捨五入"
    assert (steps[3]["x1"], steps[3]["y1"], steps[3]["x2"], steps[3]["y2"]) \
        == (15, 15, 90, 120)
    assert steps[4] == {"type": "wait", "ms": 500}
    assert steps[5] == {"type": "loop_start", "count": 3}
    assert steps[6] == {"type": "key", "keys": "enter"}


def test_倍率1改寫等於不動():
    steps = [{"type": "click", "x": 30, "y": 40},
             {"type": "find_click", "template": "a", "offsetX": 7, "offsetY": 3}]
    before = json.loads(json.dumps(steps))
    calibration.scale_steps(steps, 1.0)
    assert steps == before


# ---------- 重定基準 (票 04) ----------

def _flow(steps, **extra):
    data = {"steps": steps, "coordSpace": "region"}
    data.update(extra)
    return data


def _write_flow(profile, name, data):
    flows = profile / "flows"
    flows.mkdir(exist_ok=True)
    (flows / name).write_text(json.dumps(data, ensure_ascii=False),
                              encoding="utf-8")


def _read_flow(profile, name):
    return json.loads((profile / "flows" / name).read_text(encoding="utf-8"))


def test_重定基準改寫全部流程檔含自動存檔並更新校準資料(tmp_path):
    calibration.save(str(tmp_path), make_cal(baseline=200.0, scale=1.25, fp=FP_A))
    _write_flow(tmp_path, "f1.json", _flow([
        {"type": "click", "x": 100, "y": 40},
        {"type": "find_click", "template": "a", "offsetX": 10, "offsetY": -8}]))
    _write_flow(tmp_path, "f2.json", _flow([
        {"type": "drag", "x1": 4, "y1": 4, "x2": 40, "y2": 80, "mode": "prev"}]))
    _write_flow(tmp_path, "_autosave.json", _flow([
        {"type": "click", "x": 8, "y": 8, "mode": "prev"}]))

    files = calibration.rebase(str(tmp_path), FP_A)
    assert sorted(files) == ["_autosave.json", "f1.json", "f2.json"], \
        "漏一份就是混尺度"

    f1 = _read_flow(tmp_path, "f1.json")["steps"]
    assert (f1[0]["x"], f1[0]["y"]) == (125, 50)
    assert (f1[1]["offsetX"], f1[1]["offsetY"]) == (13, -10)
    f2 = _read_flow(tmp_path, "f2.json")["steps"]
    assert (f2[0]["x1"], f2[0]["x2"], f2[0]["y2"]) == (5, 50, 100)
    auto = _read_flow(tmp_path, "_autosave.json")["steps"]
    assert (auto[0]["x"], auto[0]["y"]) == (10, 10)

    cal = calibration.load(str(tmp_path))
    assert cal["baseline"] == 250.0, "基準距離改為本機量值 (舊基準 × 倍率)"
    assert cal["scale"] == 1.0
    assert cal["fingerprint"] == FP_A


def test_重定基準會先遷移舊格式流程檔(tmp_path):
    """任何讀存檔的新路徑都要先過座標空間遷移, 否則舊檔座標整批偏掉."""
    calibration.save(str(tmp_path), make_cal(baseline=100.0, scale=2.0, fp=FP_A))
    _write_flow(tmp_path, "old.json", {  # 無 coordSpace = 舊格式 (螢幕座標)
        "steps": [{"type": "click", "x": 300, "y": 250}],
        "scanRegion": [100, 50, 800, 600]})
    calibration.rebase(str(tmp_path), FP_A)
    data = _read_flow(tmp_path, "old.json")
    assert data["coordSpace"] == "region"
    assert (data["steps"][0]["x"], data["steps"][0]["y"]) == (400, 400), \
        "先換算成範圍座標 (300-100, 250-50) 再乘倍率 2"


def test_重定基準跳過帶來源基準標記的流程(tmp_path):
    """外來流程的尺度由標記定義, 與 profile 基準無關, 不能跟著改寫."""
    calibration.save(str(tmp_path), make_cal(baseline=100.0, scale=2.0, fp=FP_A))
    marked = _flow([{"type": "click", "x": 30, "y": 40}],
                   sourceBaseline={"pair": ["p", "q"], "baseline": 80.0})
    _write_flow(tmp_path, "foreign.json", marked)
    _write_flow(tmp_path, "normal.json", _flow([{"type": "click", "x": 30, "y": 40}]))
    files = calibration.rebase(str(tmp_path), FP_A)
    assert files == ["normal.json"]
    assert _read_flow(tmp_path, "foreign.json") == marked


# ---------- 來源基準標記 (票 06) ----------

def test_來源基準標記讀取():
    marker = {"pair": ["p", "q"], "baseline": 80.0}
    assert calibration.source_baseline({"steps": [],
                                        "sourceBaseline": marker}) == marker
    assert calibration.source_baseline({"steps": []}) is None
    assert calibration.source_baseline(
        {"sourceBaseline": {"pair": ["p"]}}) is None, "不成形的標記視同無標記"


def test_來源基準換算比值():
    """本機量得距離 120、來源基準 80、現行倍率 1.5:
    實體換算 ×1.5 再反除倍率歸一 → 淨比值 1.0。"""
    assert calibration.foreign_ratio(120.0, 80.0, 1.5) == 1.0
    assert calibration.foreign_ratio(200.0, 100.0, 1.0) == 2.0
