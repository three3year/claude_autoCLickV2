"""`避開游標` (一律開, 不是設定): 找圖截圖前把滑鼠停到搜尋範圍左下角外側, 不遮畫面.

停點＝範圍左下角再往外 (x−2, y+h+1); 範圍貼著螢幕邊緣時夾回該螢幕內。
已在停點就不再移動 (每次截圖都移動＋等 0.08s 會拖慢整份流程)。
停游標要走 `win.park` (補送真實移動事件), 不能只瞬移: 遊戲靠輸入事件追蹤游標,
只瞬移時它以為游標還在原處 (晚_繁中: 公告沒出現、沒點過東西, 主畫面跟著使用者
留下的游標偏移, 校準量錯、基建找不到)。
"""
from harness import click, find, here

AT = (500, 400)


def moves(harness):
    return [(e[1], e[2]) for e in harness.events if e[0] == "park"]


def test_停到搜尋範圍左下角外側(harness):
    harness.vision.plan("a", [AT])
    harness.run([find("a", confirm="none")], scan_region=[100, 50, 800, 600])
    assert moves(harness)[0] == (98, 651)


def test_範圍貼著螢幕邊緣時夾回螢幕內(harness):
    harness.input._cursor = (5, 5)   # 假游標預設就停在這個停點
    harness.vision.plan("a", [AT])
    harness.run([find("a", confirm="none")], scan_region=[0, 0, 1920, 1080])
    assert moves(harness)[0] == (0, 1079)


def test_沒設範圍時停到桌面左下角(harness):
    harness.input._cursor = (5, 5)
    harness.vision.plan("a", [AT])
    harness.run([find("a", confirm="none")], scan_region=None)
    assert moves(harness)[0] == (0, 1079)


def test_已在停點就不再移動(harness):
    # 開頭校準 + 找圖共三次截圖, 游標只需移動一次
    harness.vision.plan("a", [AT])
    harness.run([find("a", confirm="none")], scan_region=[100, 50, 800, 600])
    assert moves(harness) == [(98, 651)]


def test_點擊把游標帶走後_下一次截圖前再停一次(harness):
    harness.input.track_clicks = True
    harness.vision.plan("here", [(300, 300)])   # 定位找圖要在搜尋範圍內
    harness.vision.plan("a", [AT])
    harness.run([here(), click(10, 10), find("a", confirm="none")],
                scan_region=[100, 50, 800, 600])
    assert moves(harness) == [(98, 651), (98, 651)]


def test_停游標送出真實移動事件而非只瞬移(harness):
    harness.vision.plan("a", [AT])
    harness.run([find("a", confirm="none")], scan_region=[100, 50, 800, 600])
    assert [e for e in harness.events if e[0] == "move"] == []
    assert moves(harness) == [(98, 651)]
