"""`原點`與相對座標的回歸網.

`原點`＝最近一個「有更新原點」的步驟所產生的位置。座標點擊與拖曳只有相對原點
一種座標 (絕對座標已退場, ADR 0014), 所以第一個原點一定來自找圖。
"""


from harness import click, drag, find, here


def test_相對座標以原點為基準(harness):
    harness.run([here(), click(100, 200), click(10, 20)])
    assert harness.clicks() == [(100, 200), (110, 220)]


def test_勾掉更新原點的點擊不改變原點(harness):
    harness.run([
        here(),
        click(100, 200),
        click(500, 500, updateOrigin=False),
        click(1, 1),
    ])
    assert harness.clicks()[-1] == (101, 201)


def test_拖曳終點一律成為原點(harness):
    harness.run([here(), drag(10, 10, 300, 400), click(5, 5)])
    assert harness.clicks() == [(305, 405)]


def test_找圖找到的位置成為原點(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([find("a.png", action="none"), click(3, 4)])
    assert harness.clicks() == [(503, 404)]


def test_找圖勾掉更新原點時不改變原點(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([
        here(),
        click(100, 200),
        find("a.png", action="none", updateOrigin=False),
        click(1, 1),
    ])
    assert harness.clicks()[-1] == (101, 201)


def test_等待消失記錄最後看到的位置當原點(harness):
    harness.vision.plan("a.png", [(500, 400), None])
    harness.run([find("a.png", action="wait_gone", interval=0.1),
                 click(1, 2)])
    assert harness.clicks() == [(501, 402)]


def test_尚無原點時座標點擊與拖曳被跳過(harness):
    harness.run([click(10, 20), drag(1, 2, 3, 4), here(), click(9, 9)])
    assert harness.clicks() == [(9, 9)]
    assert [e[0] for e in harness.events if e[0] == "drag"] == []
    assert "尚無原點" in harness.log_text()


def test_找圖偏移後的位置才是原點(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([find("a.png", action="none", offsetX=10, offsetY=10),
                 click(0, 0)])
    assert harness.clicks() == [(510, 410)]


def test_測試選取片段_以原點為基準的步驟在原點來源之前就擋下():
    import app as app_mod
    near = {"pick": {"kind": "near", "x": 0, "y": 0}}
    check = app_mod.App._fragment_origin_error
    assert check(None, [find("a", target=near)], 4) == [5]
    assert check(None, [find("b"), find("a", target=near)], 0) == []
    # 座標點擊與拖曳一律相對原點: 片段內沒有原點來源就擋
    assert check(None, [click(1, 1), find("b"), drag(0, 0, 1, 1)], 0) == [1]
    assert check(None, [find("b"), click(1, 1), drag(0, 0, 1, 1)], 2) == []
