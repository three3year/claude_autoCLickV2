import contextlib

import numpy as np

import harness

import ui_dialogs
from automation import imgio
from test_editor_scale import _press, make_app  # noqa: F401
from test_fixed_rect_ui import FIXED_ZH, _choose, _labels, _target_dialog


def _overlay(monkeypatch, w, h):
    @contextlib.contextmanager
    def screen_clear(root, extra=()):
        yield

    monkeypatch.setattr(ui_dialogs.ui_overlay, "screen_clear", screen_clear)
    monkeypatch.setattr(ui_dialogs.ui_overlay, "pick",
                        lambda root, mode, prompt, **kw: {
                            "screenX": 300, "screenY": 350, "w": w, "h": h})


def _template(app, name, w, h):
    app.store.add(name, imgio.encode_png(np.zeros((h, w, 3), np.uint8)))


def _warn_labels(dlg):
    return [t for t in _labels(dlg) if t.startswith("⚠")]


def test_框出不足的矩形_對話框出現矩形餘裕警告_確定照存(make_app, monkeypatch):
    app = make_app(1.0)
    _template(app, "a", 50, 50)
    _overlay(monkeypatch, 58, 58)
    seen = {}

    def look(dr):
        seen["warn"] = _warn_labels(dr.dlg)
    got = _target_dialog(app, {"template": "a"}, _choose(FIXED_ZH),
                         _press("框選"), look, _press("確定"))
    assert len(seen["warn"]) == 1
    assert "至少要框 70×70" in seen["warn"][0] and "58×58" in seen["warn"][0]
    assert got["within"] == [150, 120, 58, 58], \
        "只警告不擋存檔"


def test_餘裕足夠_沒有警告(make_app, monkeypatch):
    app = make_app(1.0)
    _template(app, "a", 50, 50)
    _overlay(monkeypatch, 80, 72)
    seen = {}

    def look(dr):
        seen["warn"] = _warn_labels(dr.dlg)
    _target_dialog(app, {"template": "a"}, _choose(FIXED_ZH),
                   _press("框選"), look, _press("確定"))
    assert seen["warn"] == []


def test_餘裕以流程尺度算_倍率不是1時框選值先換回(make_app, monkeypatch):
    app = make_app(2.0)
    _template(app, "a", 50, 50)
    _overlay(monkeypatch, 120, 120)
    seen = {}

    def look(dr):
        seen["warn"] = _warn_labels(dr.dlg)
    got = _target_dialog(app, {"template": "a"}, _choose(FIXED_ZH),
                         _press("框選"), look, _press("確定"))
    assert got["within"][2] == 60
    assert any("60×60" in t and "70×70" in t for t in seen["warn"])


def test_還沒選範本就框矩形_不誤報(make_app, monkeypatch):
    app = make_app(1.0)
    _overlay(monkeypatch, 10, 10)
    seen = {}

    def look(dr):
        seen["warn"] = _warn_labels(dr.dlg)
    _target_dialog(app, {"template": ""}, _choose(FIXED_ZH),
                   _press("框選"), look, _press("確定"))
    assert seen["warn"] == []


def test_重新打開既有的不足矩形_也看得到警告_重拖夠大就清除(make_app, monkeypatch):
    app = make_app(1.0)
    _template(app, "a", 50, 50)
    _overlay(monkeypatch, 90, 90)
    seen = {}

    def before(dr):
        seen["before"] = _warn_labels(dr.dlg)

    def after(dr):
        seen["after"] = _warn_labels(dr.dlg)
    old = [0, 0, 58, 58]
    _target_dialog(app, {"template": "a", "within": old}, before,
                   _press("框選"), after, _press("確定"))
    assert len(seen["before"]) == 1 and "70×70" in seen["before"][0]
    assert seen["after"] == []


import tkinter as tk  # noqa: E402

from harness import CAL_PAIR, miss  # noqa: E402
from automation import pickcheck  # noqa: E402
from test_editor_scale import _shot  # noqa: E402


class _Lib:
    config = {"match_threshold": 0.6, "verify_threshold": 0.8}

    def __init__(self, app):
        self.app = app

    @property
    def templates(self):
        from types import SimpleNamespace
        return {n: SimpleNamespace(artifacts=None) for n in self.app.store.names()}


def _engine(app, monkeypatch):
    app.library = _Lib(app)
    app.hub.ensure_template = lambda name: None
    monkeypatch.setattr(pickcheck, "resize_image", lambda img, s: img.resized(s))


def _check_logs(app):
    return [(lvl, m) for lvl, m in app.logged if "拾取檢查" in m]


def test_截範本後縮放餘裕_0_85粗篩沒過_紀錄區警告_面板標記(make_app, monkeypatch):
    app = make_app(1.0)
    _engine(app, monkeypatch)
    app.vision.plan("tmpl_001", [miss("match", 0.6), (300, 400)])
    monkeypatch.setattr(ui_dialogs.ui_overlay, "pick", lambda root, mode, prompt, **kw: _shot(40, 20, 210, 250))
    app.capture_template()
    assert "tmpl_001" in app.store.names()
    logs = _check_logs(app)
    assert len(logs) == 1 and logs[0][0] == "warn"
    assert "×0.85" in logs[0][1] and "粗篩最高 0.600" in logs[0][1]
    assert "tmpl_001" in app.pick_warnings(), "面板標記"
    scales = [s for n, s in app.vision.expected_scales if n == "tmpl_001"]
    assert [round(s, 3) for s in scales] == [0.85, 1.15], "真的以兩個預期尺度各查一次"


def test_截範本後縮放餘裕全通過_無警告無標記(make_app, monkeypatch):
    app = make_app(1.0)
    _engine(app, monkeypatch)
    app.vision.plan("tmpl_001", [(300, 400)])
    monkeypatch.setattr(ui_dialogs.ui_overlay, "pick", lambda root, mode, prompt, **kw: _shot(40, 20, 210, 250))
    app.capture_template()
    assert _check_logs(app) == []
    assert app.pick_warnings() == {}


def test_先警告後通過_標記消失(make_app, monkeypatch):
    app = make_app(1.0)
    _engine(app, monkeypatch)
    app.vision.plan("tmpl_001", [miss("match", 0.5), (300, 400)])
    monkeypatch.setattr(ui_dialogs.ui_overlay, "pick", lambda root, mode, prompt, **kw: _shot(40, 20, 210, 250))
    app.capture_template()
    assert "tmpl_001" in app.pick_warnings()
    app.vision.plan("tmpl_001", [(300, 400)])
    from types import SimpleNamespace
    app.check_template_scale("tmpl_001", SimpleNamespace(
        frame=(app.vision.grab(None)[0], (0, 0)), anchor=(0, 0), k=1.0))
    assert app.pick_warnings() == {}
    assert _check_logs(app)[-1][0] == "ok"


def test_沒有校準對時截範本也查縮放餘裕_以倍率1為基準(make_app, monkeypatch):
    app = make_app(pair=False)
    _engine(app, monkeypatch)
    app.vision.plan("tmpl_001", [miss("match", 0.55), (300, 400)])
    monkeypatch.setattr(ui_dialogs.ui_overlay, "pick", lambda root, mode, prompt, **kw: _shot(40, 20))
    app.capture_template()
    scales = [round(s, 3) for n, s in app.vision.expected_scales if n == "tmpl_001"]
    assert scales == [0.85, 1.15]
    [(lvl, m)] = _check_logs(app)
    assert lvl == "warn" and "粗篩最高 0.550" in m


def test_選範本對話框現場截圖_確定後也查縮放餘裕(make_app, monkeypatch):
    from test_template_picker import TITLE, _Driver, _open
    app = make_app(1.0)
    _engine(app, monkeypatch)
    monkeypatch.setattr(ui_dialogs.ui_overlay, "pick",
                        lambda root, mode, prompt, **kw: _shot(40, 20, 170, 240))
    app.vision.plan("tmpl_001", [miss("verify", 0.7), (300, 400)])
    d = _Driver(app.root, TITLE)
    got = _open(app, d, lambda dr: (dr.press("截圖新增"), dr.press("確定")))
    assert got == "tmpl_001"
    [(lvl, m)] = _check_logs(app)
    assert lvl == "warn" and "驗證最高 0.700" in m


def test_找圖設定確定_兩個匹配_紀錄區出現唯一警告_設定照存(make_app, monkeypatch):
    app = make_app(1.0)
    _engine(app, monkeypatch)
    _template(app, "a", 50, 50)
    app.vision.plan("a", [[(300, 400), (500, 400)]])
    got = _target_dialog(app, {"template": "a"}, _press("確定"))
    assert got == {"within": None, "pick": None, "color": False}
    msgs = [m for _, m in _check_logs(app)]
    assert any("2 個匹配" in m and "(300,400)" in m for m in msgs), msgs
    assert "a" in app.pick_warnings()
    assert app.vision.lookups[:2] == list(CAL_PAIR), "確定時在當下截圖上量了校準對"


def test_找圖設定確定_改選由上到下第2個_沒有唯一警告(make_app, monkeypatch):
    app = make_app(1.0)
    _engine(app, monkeypatch)
    _template(app, "a", 50, 50)
    app.vision.plan("a", [[(300, 400), (500, 400)]])
    got = _target_dialog(app, {"template": "a", "pick": {"top": 2}},
                         _press("確定"))
    assert got["pick"] == {"top": 2}
    assert not any("匹配" in m for _, m in _check_logs(app))
    assert app.pick_warnings() == {}


def test_找圖設定確定_畫面上找不到_唯一沉默(make_app, monkeypatch):
    app = make_app(1.0)
    _engine(app, monkeypatch)
    _template(app, "a", 50, 50)
    app.vision.plan("a", [None])
    _target_dialog(app, {"template": "a"}, _press("確定"))
    assert not any("匹配" in m for _, m in _check_logs(app))


def test_找圖設定確定_校準量不到_略過並寫一行(make_app, monkeypatch):
    app = make_app(1.0)
    _engine(app, monkeypatch)
    _template(app, "a", 50, 50)
    app.vision.plan(CAL_PAIR[0], [None])
    got = _target_dialog(app, {"template": "a"}, _press("確定"))
    assert got is not None, "不擋確定"
    assert any("略過" in m for _, m in _check_logs(app))


def _result_labels(app):
    for w in app.root.winfo_children():
        if isinstance(w, tk.Toplevel) and w.winfo_exists() and w.title() == "比對測試結果":
            texts = [c.cget("text") for c in w.winfo_children()
                     if isinstance(c, tk.Label) and c.cget("text")]
            w.destroy()
            return texts
    return []


def test_比對測試也跑唯一與縮放餘裕_結果一起顯示(make_app, monkeypatch):
    import numpy as np
    app = make_app(1.0)
    _engine(app, monkeypatch)
    _template(app, "a", 50, 50)
    app.vision.plan("a", [[(300, 400), (500, 400)]])
    monkeypatch.setattr(ui_dialogs, "_annotate_find",
                        lambda screen, org, f, origin=None, anchor=None:
                        np.zeros((60, 80, 3), np.uint8))
    ui_dialogs.show_match_test(app, {"template": "a"})
    texts = _result_labels(app)
    line = next(t for t in texts if t.startswith("拾取檢查"))
    assert "2 個匹配" in line
    assert "a" in app.pick_warnings()


def test_比對測試通過時結果寫通過(make_app, monkeypatch):
    import numpy as np
    app = make_app(1.0)
    _engine(app, monkeypatch)
    _template(app, "a", 50, 50)
    app.vision.plan("a", [(300, 400)])
    monkeypatch.setattr(ui_dialogs, "_annotate_find",
                        lambda screen, org, f, origin=None, anchor=None:
                        np.zeros((60, 80, 3), np.uint8))
    ui_dialogs.show_match_test(app, {"template": "a"})
    texts = _result_labels(app)
    assert any(t.startswith("拾取檢查：通過") for t in texts)
