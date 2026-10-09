"""`避開游標`: 找圖截圖前把滑鼠停到搜尋範圍左下角外側, 不遮畫面.

停點＝範圍左下角再往外 (x−2, y+h+1); 範圍貼著螢幕邊緣時夾回該螢幕內。
已在停點就不再移動 (每次截圖都移動＋等 0.08s 會拖慢整份流程)。
"""
from harness import find

AT = (500, 400)


def moves(harness):
    return [(e[1], e[2]) for e in harness.events if e[0] == "move"]


def test_停到搜尋範圍左下角外側(harness):
    harness.vision.plan("a", [AT])
    harness.run([find("a", confirm="none")], scan_region=[100, 50, 800, 600],
                avoid_hover=True)
    assert moves(harness)[0] == (98, 651)


def test_範圍貼著螢幕邊緣時夾回螢幕內(harness):
    harness.vision.plan("a", [AT])
    harness.run([find("a", confirm="none")], scan_region=[0, 0, 1920, 1080],
                avoid_hover=True)
    assert moves(harness)[0] == (0, 1079)


def test_沒設範圍時停到桌面左下角(harness):
    harness.vision.plan("a", [AT])
    harness.run([find("a", confirm="none")], scan_region=None, avoid_hover=True)
    assert moves(harness)[0] == (0, 1079)


def test_已在停點就不再移動(harness):
    # 開頭校準 + 找圖共三次截圖, 游標只需移動一次
    harness.vision.plan("a", [AT])
    harness.run([find("a", confirm="none")], scan_region=[100, 50, 800, 600],
                avoid_hover=True)
    assert moves(harness) == [(98, 651)]


def test_沒勾避開游標就不移動(harness):
    harness.vision.plan("a", [AT])
    harness.run([find("a", confirm="none")], scan_region=[100, 50, 800, 600])
    assert moves(harness) == []
