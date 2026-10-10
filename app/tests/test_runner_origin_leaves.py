"""`原點的圖離開` (effect-confirm 票 04, ADR 0008).

座標點擊與拖曳的生效確認之一: 產生目前`原點`的那個找圖步驟, 它的找圖目標在它
當時挑中的框不再有匹配＝生效 (例: 找「發電站1列」→ 拖曳捲動, 1 列離開原本的框
＝有捲動)。不必另選確認圖, 操作前不多查一次。原點不是來自找圖＝無法執行。
"""
from harness import click, drag, find, here

ROW1 = (500, 400)
LEAVES = dict(confirm="gone", interval=0.2)


def recs(harness):
    return harness.filelog.of("input.confirm")


def test_來源框仍有匹配就在補做間隔後重拖_框不見就生效_原點變終點(harness):
    # 找圖 1 次 + 輪詢: 0.2..1.0 還在原框 (1.0 那次重拖), 之後捲走了
    harness.vision.plan("row1", [ROW1] * 6 + [(500, 100)])
    harness.run([find("row1", action="none"),
                 drag(0, 100, 0, -200, **LEAVES),
                 click(3, 3)])
    drags = [e[1:5] for e in harness.events if e[0] == "drag"]
    assert drags == [(500, 500, 500, 200)] * 2, "兩次拖曳座標相同"
    assert harness.clicks() == [(503, 203)], "生效後原點＝拖曳終點"
    [rec] = recs(harness)
    assert (rec["mode"], rec["result"], rec["inputs"]) == ("gone", "gone", 2)


def test_操作前不多查一次(harness):
    harness.vision.plan("row1", [ROW1, None])
    harness.run([find("row1", action="none"), drag(0, 100, 0, -200, **LEAVES)])
    assert harness.lookups() == ["row1", "row1"], "找圖一次 + 拖曳後輪詢一次"


def test_沿用來源找圖目標的限定範圍與比色_同款圖顏色不符不算還在(harness):
    """捲動後舊框位置換成別類 (形狀同、顏色不同) 的列: 開了比色就不算還在."""
    orange, other = (500, 400, 0.99, 0.99), (500, 400, 0.99, 0.60)
    harness.vision.plan("anchor", [ROW1])
    harness.vision.plan("row1", [[orange], [other]])
    lim = {"kind": "rect", "x": 400, "y": 300, "w": 200, "h": 200}   # 基準點 (0,0)
    harness.run([find("anchor", action="none"),
                 find("row1", target={"colorCheck": True, "limit": lim},
                      action="none"),
                 drag(0, 100, 0, -200, **LEAVES)])
    [rec] = recs(harness)
    assert rec["result"] == "gone" and rec["inputs"] == 1
    assert harness.vision.color_checks[-1] == ("row1", True)


def test_原點來自點擊_無法執行_不送輸入_走找不到時(harness):
    r = harness.run([here(), click(100, 100), drag(0, 0, 0, -100, **LEAVES),
                     click(9, 9)])
    assert r.ended == "error", "預設停止"
    assert [e[0] for e in harness.events if e[0] != "park"] == ["click"], "拖曳沒送"
    [rec] = recs(harness)
    assert rec["result"] == "cannot_run"
    assert "原點不是來自找圖" in harness.log_text(r)


def test_原點來自拖曳_無法執行(harness):
    harness.vision.plan("row1", [ROW1])
    r = harness.run([find("row1", action="none"), drag(0, 0, 0, -100),
                     click(0, 0, confirm="gone", onNotFound="skip")])
    assert r.ended == "done"
    assert recs(harness)[-1]["result"] == "cannot_run"
    assert harness.clicks() == []


def test_沒有原點_無法執行(harness):
    r = harness.run([click(10, 10, confirm="gone", onNotFound="skip")])
    assert r.ended == "done" and harness.clicks() == []
    assert recs(harness) == [], "沒有原點: 相對座標先被跳過"
    assert "尚無原點" in harness.log_text(r)


def test_原點來自等待消失最後看到的位置_也算找圖來源(harness):
    harness.vision.plan("x", [ROW1, None])
    harness.vision.plan("row1", [ROW1, None])
    harness.run([find("row1", action="none"),
                 find("x", action="wait_gone", updateOrigin=False),
                 click(0, 0, confirm="gone", interval=0.2)])
    assert recs(harness)[0]["result"] == "gone"
