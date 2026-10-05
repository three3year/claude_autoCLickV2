"""`等待消失`的`出現等候上限` (effect-confirm 票 02, ADR 0008).

設了上限: 上限內一次都沒看到＝通過; 看到了就照常等它消失、受步驟逾時限制。
沒設: 維持「從未出現＝逾時失敗」。用途是換班 ⇌ 後等忙碌指示, 取代固定等待。
"""
from harness import click, find
from test_editor_scale import make_app  # noqa: F401  (fixture)

GONE = dict(action="wait_gone", interval=0.2, timeout=5, onNotFound="stop")


def records(harness):
    return [r for r in harness.filelog.of("find.target")
            if r["role"] == "wait_gone"]


def test_上限內沒看到_通過_後續步驟執行(harness):
    harness.vision.plan("busy", [None])
    t0 = harness.clock.t
    r = harness.run([find("busy", appearLimitMs=1000, **GONE), click(9, 9)])
    assert r.ended == "done"
    assert harness.clicks() == [(9, 9)]
    assert harness.clock.t - t0 < 1.5, "網路快: 約 1 秒就放行"
    [rec] = records(harness)
    assert rec["result"] == "not_appeared"
    # 記最高分與未過原因: 實跑時才分得出「真的沒出現」與「範本/範圍對不上」
    assert rec["failed"] == "match" and "best" in rec


def test_上限內看到_之後消失_通過(harness):
    harness.vision.plan("busy", [None, (960, 1000), (960, 1000), None])
    r = harness.run([find("busy", appearLimitMs=1000, **GONE), click(9, 9)])
    assert r.ended == "done" and harness.clicks() == [(9, 9)]
    assert records(harness)[0]["result"] == "gone"


def test_看到後超過上限才消失_仍等它消失(harness):
    """上限只管「等多久讓它出現」; 看到之後照常等, 受步驟逾時限制."""
    harness.vision.plan("busy", [(960, 1000)] * 10 + [None])
    t0 = harness.clock.t
    r = harness.run([find("busy", appearLimitMs=500, **GONE), click(9, 9)])
    assert r.ended == "done" and harness.clicks() == [(9, 9)]
    assert harness.clock.t - t0 >= 2.0


def test_看到但到逾時都沒消失_走找不到時(harness):
    harness.vision.plan("busy", [(960, 1000)])
    r = harness.run([find("busy", appearLimitMs=1000, **GONE), click(9, 9)])
    assert r.ended == "error", "找不到時＝停止"
    assert harness.clicks() == []
    assert records(harness)[0]["result"] == "not_gone"


def test_沒設上限_從未出現仍是逾時失敗(harness):
    harness.vision.plan("busy", [None])
    r = harness.run([find("busy", **GONE), click(9, 9)])
    assert r.ended == "error" and harness.clicks() == []
    assert "從未出現" in harness.log_text(r)


# ---------- 存檔欄位、對話框、步驟摘要 ----------

def _find_step(**kw):
    return dict({"type": "find_click", "target": {"template": "busy"},
                 "timeout": 5, "interval": 0.3, "action": "wait_gone",
                 "onNotFound": "skip"}, **kw)


def test_對話框保留出現等候上限_步驟摘要顯示(make_app):
    import app as app_mod
    from test_editor_scale import _edit, _press
    a = make_app(1.0)
    a.ws.add("busy", b"B")
    got = _edit(a, _find_step(appearLimitMs=1000, _edit=True),
                _press("確定"), title="編輯：找圖點擊")
    assert got["appearLimitMs"] == 1000
    assert "出現等候上限 1000ms" in app_mod.step_desc(got)


def test_不是等待消失時不存出現等候上限(make_app):
    from test_editor_scale import _edit, _press
    a = make_app(1.0)
    a.ws.add("busy", b"B")
    got = _edit(a, _find_step(action="none", appearLimitMs=1000, _edit=True),
                _press("確定"), title="編輯：找圖點擊")
    assert "appearLimitMs" not in got


def test_出現等候上限存檔往返(tmp_path):
    import flowfile
    path = str(tmp_path / ("f" + flowfile.EXT))
    flowfile.write(path, {"steps": [_find_step(appearLimitMs=800)],
                          "coordSpace": "region"}, {"busy": b"B"})
    assert flowfile.read(path)["data"]["steps"][0]["appearLimitMs"] == 800
