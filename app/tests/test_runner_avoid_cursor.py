from harness import click, find, here

AT = (500, 400)


def moves(harness):
    return [(e[1], e[2]) for e in harness.events if e[0] == "park"]


def test_停到搜尋範圍左下角外側(harness):
    harness.vision.plan("a", [AT])
    harness.run([find("a", confirm="none")], scan_region=[100, 50, 800, 600])
    assert moves(harness)[0] == (98, 651)


def test_範圍貼著螢幕邊緣時夾回螢幕內(harness):
    harness.input._cursor = (5, 5)
    harness.vision.plan("a", [AT])
    harness.run([find("a", confirm="none")], scan_region=[0, 0, 1920, 1080])
    assert moves(harness)[0] == (0, 1079)


def test_沒設範圍時停到桌面左下角(harness):
    harness.input._cursor = (5, 5)
    harness.vision.plan("a", [AT])
    harness.run([find("a", confirm="none")], scan_region=None)
    assert moves(harness)[0] == (0, 1079)


def test_已在停點就不再移動(harness):
    harness.vision.plan("a", [AT])
    harness.run([find("a", confirm="none")], scan_region=[100, 50, 800, 600])
    assert moves(harness) == [(98, 651)]


def test_點擊把游標帶走後_下一次截圖前再停一次(harness):
    harness.input.track_clicks = True
    harness.vision.plan("here", [(300, 300)])
    harness.vision.plan("a", [AT])
    harness.run([here(), click(10, 10), find("a", confirm="none")],
                scan_region=[100, 50, 800, 600])
    assert moves(harness) == [(98, 651), (98, 651)]


def test_停游標送出真實移動事件而非只瞬移(harness):
    harness.vision.plan("a", [AT])
    harness.run([find("a", confirm="none")], scan_region=[100, 50, 800, 600])
    assert [e for e in harness.events if e[0] == "move"] == []
    assert moves(harness) == [(98, 651)]
