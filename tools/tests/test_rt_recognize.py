"""公開招募 票 02 — 辨識入口: 假招募畫面 + 迷你快照 → 五格的標籤與嚴格判定.

用 session 共用的真引擎; 假畫面用工具自己的渲染器畫 (見 rt_synth.fake_screen)。
只斷言外部行為 (每格的標籤、狀態、整張通過與否), 不斷言分數確切值。
"""
import cv2
import numpy as np
import pytest

import recruit_tags
from recruit_tags import layout
from rt_synth import TAG_ID as TAG, fake_screen, pool

# 不含「X幹員」與「近戰位/遠程位」: 那兩族字面只差一兩個字, 引擎會讓同族範本也過門檻
FIVE = ["支援機械", "新手", "費用回復", "輸出", "生存"]
POOL = pool([("芬", 3, ["先鋒幹員", "近戰位", "費用回復"])])


def labels(res):
    return [c["tag"]["name"] if c["tag"] else None for c in res["cells"]]


def test_五格全對且通過嚴格標準(engine):
    res = recruit_tags.recognize(fake_screen(FIVE), POOL, engine=engine)

    assert labels(res) == FIVE
    assert [c["status"] for c in res["cells"]] == ["pass"] * 5
    assert res["passed"] is True
    for c in res["cells"]:
        assert c["margin"] >= 0.1
        assert c["runner_up"]["name"] not in (None, c["tag"]["name"])


@pytest.mark.parametrize("scale", [0.886, 1.0])
def test_視窗與最大化尺度都認得(engine, scale):
    res = recruit_tags.recognize(fake_screen(FIVE, scale=scale), POOL, engine=engine)

    assert labels(res) == FIVE
    assert res["scale"] == pytest.approx(scale, abs=0.002)


def test_某格放非標籤文字時該格未辨識且整張不通過(engine):
    res = recruit_tags.recognize(fake_screen(["支援機械", "新手", "招募預算", "輸出", "生存"]),
                                 POOL, engine=engine)

    assert res["cells"][2]["status"] == "unrecognized"
    assert res["cells"][2]["tag"] is None
    assert labels(res)[:2] == FIVE[:2]
    assert res["passed"] is False


def test_字面互為子字串的標籤不混淆(engine):
    # 「支援」是「支援機械」的前半、「資深幹員」是「高級資深幹員」的後半
    five = ["支援機械", "支援", "高級資深幹員", "資深幹員", "元素"]

    res = recruit_tags.recognize(fake_screen(five), POOL, engine=engine)

    c = res["cells"]
    assert [x["best"]["name"] for x in c] == five
    assert c[0]["found"] == [TAG["支援機械"]] and c[1]["found"] == [TAG["支援"]]
    assert c[2]["found"] == [TAG["高級資深幹員"]]
    assert TAG["高級資深幹員"] not in c[3]["found"]


def test_兩張以上範本過門檻時該格混淆列出全部且不認標籤(engine):
    # 「重裝幹員」格: 其他「X幹員」範本 (只差兩個字) 也過粗篩與驗證門檻
    res = recruit_tags.recognize(fake_screen(["重裝幹員", "新手", "費用回復", "輸出", "生存"]),
                                 POOL, engine=engine)

    c = res["cells"][0]
    assert c["status"] == "confused" and c["tag"] is None
    assert TAG["重裝幹員"] in c["found"] and len(c["found"]) >= 2
    assert c["best"]["name"] == "重裝幹員"
    assert res["passed"] is False


def test_格外同字的文字不混進來(engine):
    img = fake_screen(FIVE)

    res = recruit_tags.recognize(img, POOL, engine=engine)

    assert all(c["found"] == [c["tag"]["id"]] for c in res["cells"])


def test_截圖長寬比不對時拒絕並說原因(engine):
    img = np.full((1080, 1920, 3), 200, np.uint8)

    with pytest.raises(recruit_tags.ToolError, match="長寬比"):
        recruit_tags.recognize(img, POOL, engine=engine)


def test_標籤格版面覆寫生效(engine):
    moved = [(x + 120, y - 200, w, h) for x, y, w, h in layout.CELLS]
    img = fake_screen(FIVE, cells=moved, distractor=False)

    default = recruit_tags.recognize(img, POOL, engine=engine)
    override = recruit_tags.recognize(img, POOL, engine=engine, cells=moved)

    assert default["passed"] is False
    assert labels(override) == FIVE and override["passed"] is True
    assert override["layout"] == [list(c) for c in moved]


def test_截圖可給路徑含中文(engine, tmp_path):
    p = tmp_path / "招募.png"
    cv2.imencode(".png", fake_screen(FIVE))[1].tofile(str(p))

    res = recruit_tags.recognize(str(p), POOL, engine=engine)

    assert labels(res) == FIVE


def test_結果帶渲染設定與快照資訊(engine):
    res = recruit_tags.recognize(fake_screen(FIVE), POOL, engine=engine)

    assert res["render"]["font"] == "NotoSansTC-VF.ttf"
    assert res["render"]["size"] == 24 and res["render"]["weight"] == 500
    assert res["pool"]["server"] == "tw"


def test_客戶端與快照伺服器不符時拒絕(engine):
    with pytest.raises(recruit_tags.ToolError, match="伺服器"):
        recruit_tags.recognize(fake_screen(FIVE), POOL, engine=engine, client="cn")
