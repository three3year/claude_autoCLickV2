import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from subject_detection.engine import Match, QueryResult  # noqa: E402

from automation import pickcheck  # noqa: E402

ORG = (100, 200)
ANCHOR = (150, 230)


def screen(w=800, h=600):
    return np.zeros((h, w, 3), np.uint8)


class Detector:
    def __init__(self):
        self.answers = {}
        self.calls = []

    def plan(self, scale, answer, match=0.9, verify=0.95):
        self.answers[round(scale, 3)] = (answer, match, verify)

    def query(self, name, image, color_check=False, expected_scale=None):
        h, w = image.shape[:2]
        self.calls.append((name, expected_scale, (w, h), bool(color_check)))
        key = round(expected_scale, 3) if expected_scale is not None else None
        answer, match, verify = self.answers.get(key, (None, 0.4, None))
        if answer is None:
            return QueryResult(found=False, box=None, score=match, failed="match",
                               debug={"match_score": match})
        if isinstance(answer, tuple) and answer[0] == "miss":
            _, gate, score = answer
            debug = {"match_score": match}
            if gate == "verify":
                debug["verify_score"] = score
            return QueryResult(found=False, box=None, score=score, failed=gate,
                               debug=debug)
        matches = [Match((cx - 20, cy - 10, 40, 20), p[2] if len(p) > 2 else 0.95)
                   for p in answer for cx, cy in [p[:2]]]
        debug = {"match_score": match}
        if verify is not None:
            debug["verify_score"] = verify
        return QueryResult(found=True, box=matches[0].box, score=matches[0].score,
                           matches=matches, debug=debug)


def _rect(w, h):
    return {"template": "t", "within": [0, 0, w, h]}


def test_矩形餘裕不足_警告並建議至少多大():
    [w] = pickcheck.rect_margin(_rect(58, 58), (50, 50))
    assert w.kind == "rect" and w.template == "t"
    assert w.scores["min"] == (70, 70)
    assert "至少要框 70×70" in w.text and "58×58" in w.text


def test_矩形餘裕足夠_不警告():
    assert pickcheck.rect_margin(_rect(72, 72), (50, 50)) == []
    assert pickcheck.rect_margin(_rect(70, 70), (50, 50)) == [], "剛好 20% 也算夠"


def test_只有一邊不足也警告():
    [w] = pickcheck.rect_margin(_rect(100, 60), (50, 50))
    assert w.scores["min"] == (70, 70)


def test_沒範本不警告_不是固定矩形不警告():
    assert pickcheck.rect_margin(_rect(10, 10), None) == []
    assert pickcheck.rect_margin({"template": "t"}, (50, 50)) == []


def test_最小矩形的算法_向上取整():
    assert pickcheck.min_rect((50, 50)) == (70, 70)
    assert pickcheck.min_rect((55, 23)) == (77, 33)


def test_縮放餘裕_真的以兩個預期尺度各查一次_影像跟著縮():
    d = Detector()
    d.plan(0.85, [(300, 200)])
    d.plan(1.15, [(300, 200)])
    out = pickcheck.scale_margin(d, screen(800, 600), ORG, {"template": "t"},
                                 ANCHOR, 1.0)
    assert out == []
    assert [(n, s, size) for n, s, size, _ in d.calls] == [
        ("t", 0.85, (680, 510)), ("t", 1.15, (920, 690))]


def test_縮放餘裕_以當下倍率為基準再乘():
    d = Detector()
    d.plan(0.9 * 0.85, [(300, 200)])
    d.plan(0.9 * 1.15, [(300, 200)])
    assert pickcheck.scale_margin(d, screen(), ORG, {"template": "t"}, ANCHOR,
                                  0.9) == []
    assert [round(s, 3) for _, s, _, _ in d.calls] == [0.765, 1.035]


def test_縮到0_85找不到_警告寫明哪一關與分數與倍率():
    d = Detector()
    d.plan(0.85, ("miss", "match", 0.55))
    d.plan(1.15, [(300, 200)])
    [w] = pickcheck.scale_margin(d, screen(), ORG, {"template": "t"}, ANCHOR, 1.0)
    assert w.kind == "scale"
    assert (w.scores["scale"], w.scores["gate"], w.scores["score"]) == (0.85, "match", 0.55)
    assert "×0.85" in w.text and "粗篩最高 0.550" in w.text and "找不到" in w.text


def test_找得到但粗篩貼門檻_警告():
    d = Detector()
    d.plan(0.85, [(300, 200)], match=0.6)
    d.plan(1.15, [(300, 200)], match=0.75)
    [w] = pickcheck.scale_margin(d, screen(), ORG, {"template": "t"}, ANCHOR, 1.0)
    assert (w.scores["scale"], w.scores["gate"], w.scores["score"]) == (0.85, "match", 0.6)
    assert "粗篩最高 0.600" in w.text


def test_找得到但驗證貼門檻_警告():
    d = Detector()
    d.plan(0.85, [(300, 200)])
    d.plan(1.15, [(300, 200)], verify=0.82)
    [w] = pickcheck.scale_margin(d, screen(), ORG, {"template": "t"}, ANCHOR, 1.0)
    assert (w.scores["scale"], w.scores["gate"], w.scores["score"]) == (1.15, "verify", 0.82)
    assert "驗證最高 0.820" in w.text


def test_兩端都差_兩則警告():
    d = Detector()
    d.plan(0.85, None)
    d.plan(1.15, ("miss", "verify", 0.7))
    out = pickcheck.scale_margin(d, screen(), ORG, {"template": "t"}, ANCHOR, 1.0)
    assert [w.scores["scale"] for w in out] == [0.85, 1.15]
    assert out[1].scores["gate"] == "verify"


def test_coarse_only時沒有驗證分數_只看粗篩():
    d = Detector()
    d.plan(0.85, [(300, 200)], verify=None)
    d.plan(1.15, [(300, 200)], verify=None)
    assert pickcheck.scale_margin(d, screen(), ORG, {"template": "t"}, ANCHOR, 1.0) == []


def test_縮放餘裕照限定範圍裁_固定矩形跟著縮():
    d = Detector()
    d.plan(0.85, [(10, 10)])
    d.plan(1.15, [(10, 10)])
    tgt = {"template": "t", "within": [100, 50, 200, 100]}
    pickcheck.scale_margin(d, screen(800, 600), ORG, tgt, ANCHOR, 1.0)
    sizes = [size for _, _, size, _ in d.calls]
    for got, want in zip(sizes, [(170, 85), (230, 115)]):
        assert abs(got[0] - want[0]) <= 1 and abs(got[1] - want[1]) <= 1, sizes


def test_縮放餘裕不看挑選規則():
    d = Detector()
    d.plan(0.85, [(300, 200)])
    d.plan(1.15, [(300, 200)])
    tgt = {"template": "t", "pick": {"top": 3}}
    assert pickcheck.scale_margin(d, screen(), ORG, tgt, ANCHOR, 1.0) == []


def test_固定矩形但沒有基準點_無法查就沉默():
    d = Detector()
    tgt = {"template": "t", "within": [0, 0, 10, 10]}
    assert pickcheck.scale_margin(d, screen(), ORG, tgt, None, 1.0) == []
    assert d.calls == []


def test_兩個匹配_警告並列出位置():
    d = Detector()
    d.plan(1.0, [(300, 200), (500, 200)])
    [w] = pickcheck.unique(d, screen(), ORG, {"template": "t"}, ANCHOR, 1.0)
    assert w.kind == "unique"
    assert w.scores["matches"] == [(400, 400), (600, 400)], "螢幕座標"
    assert "2 個匹配" in w.text and "(400,400)" in w.text


def test_一個或零個匹配_不警告():
    d = Detector()
    d.plan(1.0, [(300, 200)])
    assert pickcheck.unique(d, screen(), ORG, {"template": "t"}, ANCHOR, 1.0) == []
    d2 = Detector()
    d2.plan(1.0, None)
    assert pickcheck.unique(d2, screen(), ORG, {"template": "t"}, ANCHOR, 1.0) == []


def test_有挑選規則就跳過():
    d = Detector()
    d.plan(1.0, [(300, 200), (500, 200)])
    for pick in ({"top": 2}, {"left": 1},
                 {"near": [0, 0]}):
        assert pickcheck.unique(d, screen(), ORG, {"template": "t", "pick": pick},
                                ANCHOR, 1.0, origin=(0, 0)) == []
    assert d.calls == []


def test_唯一照限定範圍查_並帶比色():
    d = Detector()
    d.plan(1.0, [(300, 200), (320, 200)])
    tgt = {"template": "t", "color": True,
           "within": [100, 50, 200, 100]}
    [w] = pickcheck.unique(d, screen(800, 600), ORG, tgt, ANCHOR, 1.0)
    [(_, s, size, color)] = d.calls
    assert (s, size, color) == (1.0, (200, 100), True)
    assert "限定範圍內" in w.text


def test_check_三項一起_可指定只查哪幾項():
    d = Detector()
    d.plan(0.85, None)
    d.plan(1.15, [(300, 200)])
    d.plan(1.0, [(300, 200), (500, 200)])
    tgt = {"template": "t", "within": [0, 0, 30, 30]}
    out = pickcheck.check(d, screen(), ORG, tgt, ANCHOR, 1.0, template_size=(50, 50))
    assert [w.kind for w in out] == ["rect", "scale", "unique"]
    only = pickcheck.check(d, screen(), ORG, tgt, ANCHOR, 1.0, template_size=(50, 50),
                           kinds=(pickcheck.RECT,))
    assert [w.kind for w in only] == ["rect"]
    assert str(out[0]).startswith("〔矩形餘裕〕")
