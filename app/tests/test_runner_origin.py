"""`原點`與相對座標的回歸網.

`原點`＝最近一個「有更新原點」的步驟所產生的位置。`並行執行`時每份流程的
`原點`必須完全獨立, 所以先把單流程的語意鎖住。
"""


from harness import click, drag, find


def test_相對座標以原點為基準(harness):
    harness.run([click(100, 200), click(10, 20, mode="prev")])
    assert harness.clicks() == [(100, 200), (110, 220)]


def test_勾掉更新原點的點擊不改變原點(harness):
    harness.run([
        click(100, 200),
        click(500, 500, updateOrigin=False),
        click(1, 1, mode="prev"),
    ])
    assert harness.clicks()[-1] == (101, 201)


def test_拖曳終點一律成為原點(harness):
    harness.run([drag(10, 10, 300, 400), click(5, 5, mode="prev")])
    assert harness.clicks() == [(305, 405)]


def test_找圖找到的位置成為原點(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([find("a.png", action="none"), click(3, 4, mode="prev")])
    assert harness.clicks() == [(503, 404)]


def test_找圖勾掉更新原點時不改變原點(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([
        click(100, 200),
        find("a.png", action="none", updateOrigin=False),
        click(1, 1, mode="prev"),
    ])
    assert harness.clicks()[-1] == (101, 201)


def test_等待消失記錄最後看到的位置當原點(harness):
    harness.vision.plan("a.png", [(500, 400), None])
    harness.run([find("a.png", action="wait_gone", interval=0.1),
                 click(1, 2, mode="prev")])
    assert harness.clicks() == [(501, 402)]


def test_尚無原點時相對座標步驟被跳過(harness):
    harness.run([click(10, 20, mode="prev"), click(9, 9)])
    assert harness.clicks() == [(9, 9)]
    assert "尚無上一個點擊位置" in harness.log_text()


def test_找圖偏移後的位置才是原點(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([find("a.png", action="none", offsetX=10, offsetY=10),
                 click(0, 0, mode="prev")])
    assert harness.clicks() == [(510, 410)]
