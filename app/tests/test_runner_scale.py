"""執行期`畫面倍率`套用: 三類偏移 (含拖曳兩端點) ×倍率換算落點.

倍率 1 的恆等回歸由既有 runner 測試 (全數未改) 把守; 本檔只驗倍率≠1。
斷言對象是假 win.click / win.drag 收到的最終落點 (= 中心/基準點 + 偏移×倍率)。
"""
from harness import click, drag, find


def test_找圖偏移乘上倍率(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([find("a.png", offset=[10, -20])], scale=1.5)
    assert harness.clicks() == [(515, 370)], "落點 = 中心 + 偏移×1.5 (四捨五入)"


def test_相對座標乘上倍率(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([find("a.png"), click(10, -6)], scale=1.5)
    assert harness.clicks() == [(500, 400), (515, 391)], \
        "原點 (螢幕座標) 不換算, 相對偏移 ×1.5 (負值對稱四捨五入)"


def test_拖曳兩端點都乘上倍率(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([find("a.png"), drag(10, 10, 60, 80)], scale=1.5)
    ev = [e for e in harness.events if e[0] == "drag"][0]
    assert (ev[1], ev[2], ev[3], ev[4]) == (515, 415, 590, 520)


def test_搜尋範圍本身不乘倍率(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([find("a.png")], scan_region=[100, 50, 800, 600], scale=2.0)
    assert harness.grabs() == [(100, 50, 800, 600)], \
        "搜尋範圍是本機量測的螢幕座標, 不換算"


def test_找圖不點擊時原點也含倍率後的偏移(harness):
    """wait_gone / none 記錄的原點 = 找到位置 + 偏移×倍率."""
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([find("a.png", type="find", offset=[10, 0]),
                 click(0, 0)], scale=2.0)
    assert harness.clicks() == [(520, 400)]


def test_點擊後確認的補點同樣乘上倍率(harness):
    harness.vision.plan("a.png", [(500, 400), (500, 400), None])
    harness.run(retry_interval=0, steps=[find("a.png", confirm="gone", interval=0.1,
                      offset=[4, 0])], scale=1.5)
    assert harness.clicks() == [(506, 400), (506, 400)]
