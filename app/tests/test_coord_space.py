"""`絕對座標`的基準＝`搜尋範圍`左上角.

改這個座標系的理由: 視窗搬家 (或並行時綁到位置不同的視窗) 後, 所有絕對座標
會自動跟著搬過去, 不必重新拾取。
"""
import pytest

from automation import flowfmt
from harness import click, drag


def test_絕對座標以搜尋範圍左上角為基準(harness):
    harness.run([click(30, 40)], scan_region=[100, 200, 800, 600])
    assert harness.clicks() == [(130, 240)]


def test_重新框範圍後絕對座標跟著移動(harness):
    """同一份步驟, 只換搜尋範圍 → 落點跟著範圍走."""
    harness.run([click(30, 40)], scan_region=[0, 0, 800, 600])
    first = harness.clicks()[-1]
    harness.events.clear()
    harness.run([click(30, 40)], scan_region=[500, 300, 800, 600])
    second = harness.clicks()[-1]
    assert first == (30, 40)
    assert second == (530, 340)


def test_拖曳的絕對座標同樣以範圍為基準(harness):
    harness.run([drag(10, 10, 60, 80)], scan_region=[100, 200, 800, 600])
    ev = [e for e in harness.events if e[0] == "drag"][0]
    assert (ev[1], ev[2], ev[3], ev[4]) == (110, 210, 160, 280)


def test_相對座標不受範圍影響(harness):
    """相對座標是以`原點`為基準, 換範圍不影響它與原點的相對關係."""
    harness.run([click(30, 40), click(5, 5, mode="prev")],
                scan_region=[100, 200, 800, 600])
    assert harness.clicks() == [(130, 240), (135, 245)]


def test_沒有搜尋範圍時絕對座標步驟會停下並說明(harness):
    harness.run([click(30, 40)], scan_region=None)
    assert harness.clicks() == []
    assert "請先框選搜尋範圍" in harness.log_text()


def test_沒有搜尋範圍時相對座標步驟仍可執行(harness):
    """只有`絕對座標`需要範圍當基準."""
    harness.run([click(1, 1, mode="prev")], scan_region=None)
    assert "尚無上一個點擊位置" in harness.log_text()


# ---------- 存檔格式遷移 ----------

def test_舊格式的絕對座標會換算成範圍座標():
    data = {"steps": [{"type": "click", "x": 300, "y": 250},
                      {"type": "drag", "x1": 200, "y1": 100,
                       "x2": 400, "y2": 300}],
            "scanRegion": [170, 42, 1618, 947]}
    note = flowfmt.to_region_space(data)
    assert data["steps"][0]["x"] == 300 - 170
    assert data["steps"][0]["y"] == 250 - 42
    assert data["steps"][1]["x1"] == 200 - 170
    assert data["steps"][1]["y2"] == 300 - 42
    assert data[flowfmt.COORD_SPACE] == flowfmt.REGION
    assert "已把 2 個" in note


def test_已是新格式的存檔不會被再換一次():
    data = {"steps": [{"type": "click", "x": 30, "y": 40}],
            "scanRegion": [170, 42, 1618, 947],
            flowfmt.COORD_SPACE: flowfmt.REGION}
    assert flowfmt.to_region_space(data) is None
    assert data["steps"][0]["x"] == 30


def test_相對座標步驟不會被換算():
    data = {"steps": [{"type": "click", "x": 30, "y": 40, "mode": "prev"}],
            "scanRegion": [170, 42, 1618, 947]}
    flowfmt.to_region_space(data)
    assert data["steps"][0]["x"] == 30


def test_沒有絕對座標步驟的舊存檔直接標記為新格式():
    """使用者現有的四份存檔都是這一類 (全部都是相對座標)."""
    data = {"steps": [{"type": "click", "x": 5, "y": 5, "mode": "prev"}],
            "scanRegion": None}
    assert flowfmt.to_region_space(data) is None
    assert data[flowfmt.COORD_SPACE] == flowfmt.REGION


def test_有絕對座標卻沒有搜尋範圍的舊存檔要回報無法換算():
    data = {"steps": [{"type": "click", "x": 300, "y": 250}],
            "scanRegion": None}
    note = flowfmt.to_region_space(data)
    assert note and "無法自動換算" in note
    assert data["steps"][0]["x"] == 300, "換不了就不要亂動"
    assert flowfmt.COORD_SPACE not in data, "沒換成功就不能標記為新格式"


@pytest.mark.parametrize("steps,expected", [
    ([{"type": "click", "x": 1, "y": 1}], [1]),
    ([{"type": "click", "x": 1, "y": 1, "mode": "prev"}], []),
    ([{"type": "drag", "x1": 1, "y1": 1, "x2": 2, "y2": 2}], [1]),
    ([{"type": "wait", "ms": 100}], []),
])
def test_找出使用絕對座標的步驟(steps, expected):
    assert [n for n, _ in flowfmt.abs_steps(steps)] == expected
