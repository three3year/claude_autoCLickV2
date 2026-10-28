from types import SimpleNamespace

import harness

import app as app_mod
import calibration
import ui_dialogs
from test_calibration_ui import OLD, _Btn, _editor, _flow_with_coords, _warnings
from test_editor_scale import make_app  # noqa: F401

MAIN = OLD
FB = ("標題列圖示", "關閉鈕")


def _place(vision, names, a, b):
    vision.plan(names[0], [a])
    vision.plan(names[1], [b])


def _fb_editor(tkroot, monkeypatch, tmp_path, cal=None, pick=FB):
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=cal)
    monkeypatch.setattr(ui_dialogs, "pick_cal_pair", lambda app, **kw: pick)
    for n in (pick or ()):
        a.store.add(n, b"F")
    return a, vision


def test_設定備用校準對_量兩組_存基準距離與偏移(tkroot, monkeypatch, tmp_path):
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path, cal=dict(MAIN))
    _place(vision, MAIN["pair"], (300, 200), (1200, 200))
    _place(vision, FB, (30, 20), (1710, 20))
    a.designate_fallback_pair()
    fb = calibration.fallback_pair(a.flow_cal)
    assert fb["pair"] == list(FB)
    assert abs(fb["baseline"] - 1680 / 0.9) < 0.1
    assert fb["offset"] == [300, 200], "(主基準點 − 備用第一張中心) ÷ 0.9"
    assert a.flow_cal["pair"] == MAIN["pair"] and a.flow_cal["baseline"] == 1000.0
    assert a.autosaved == 1
    assert any("備用校準對" in m and "標題列圖示" in m for m in a.logged)
    assert calibration.fallback_anchor((30, 20), fb["offset"], 0.9) == (300, 200)


def test_主對找不到_拒絕設定備用對_資料不變(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path, cal=dict(MAIN))
    _place(vision, MAIN["pair"], None, (1200, 200))
    _place(vision, FB, (30, 20), (1710, 20))
    a.designate_fallback_pair()
    assert calibration.fallback_pair(a.flow_cal) is None
    assert a.flow_cal == MAIN
    assert any("舊圖示" in m for m in rec) and a.autosaved == 0


def test_備用對找不到_拒絕(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path, cal=dict(MAIN))
    _place(vision, MAIN["pair"], (300, 200), (1200, 200))
    _place(vision, FB, (30, 20), None)
    a.designate_fallback_pair()
    assert calibration.fallback_pair(a.flow_cal) is None
    assert any("關閉鈕" in m for m in rec)


def test_備用對與主對相同_拒絕(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path, cal=dict(MAIN),
                           pick=tuple(MAIN["pair"]))
    a.designate_fallback_pair()
    assert calibration.fallback_pair(a.flow_cal) is None
    assert any("相同" in m for m in rec)


def test_還沒有主對_先提示設定校準對(tkroot, monkeypatch, tmp_path):
    rec = []
    monkeypatch.setattr(app_mod.messagebox, "showinfo",
                        lambda title, msg, **kw: rec.append(msg))
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path)
    a.designate_fallback_pair()
    assert any("校準對" in m for m in rec)
    assert vision.lookups == []


def _with_fb(offset=(100, 50)):
    c = dict(MAIN)
    c[calibration.FALLBACK_KEY] = calibration.make_fallback(FB, 1868.0, offset)
    return c


def test_流程設定顯示備用對(tkroot, monkeypatch, tmp_path):
    a, _ = _fb_editor(tkroot, monkeypatch, tmp_path, cal=_with_fb())
    assert a._fb_text() == "標題列圖示 × 關閉鈕（基準 1868 px）"


def test_測試校準對_主對找不到時寫明用的是備用對(tkroot, monkeypatch, tmp_path):
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path, cal=_with_fb())
    _place(vision, MAIN["pair"], None, (1200, 200))
    _place(vision, FB, (20, 20), (1514, 20))
    a.test_calibration()
    assert any("備用校準對" in m and "×0.800" in m and "(100, 60)" in m
               for m in a.logged)


def test_測試校準對_主對找得到時不提備用(tkroot, monkeypatch, tmp_path):
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path, cal=_with_fb())
    _place(vision, MAIN["pair"], (100, 50), (1300, 50))
    a.test_calibration()
    assert any("×1.200" in m for m in a.logged)
    assert not any("備用" in m for m in a.logged)


def test_測試備用校準對_主對看得到也只用備用對量(tkroot, monkeypatch, tmp_path):
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path, cal=_with_fb())
    _place(vision, MAIN["pair"], (100, 50), (1300, 50))
    _place(vision, FB, (20, 20), (1514, 20))
    a.test_fallback_calibration()
    assert any("×0.800" in m and "(100, 60)" in m for m in a.logged)
    assert set(vision.lookups) == set(FB), "主對不量"


def test_測試備用校準對_沒設_紀錄寫還沒設定(tkroot, monkeypatch, tmp_path, no_real_dialogs):
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path, cal=dict(MAIN))
    a.test_fallback_calibration()
    assert any("還沒設定" in m for m in a.logged)
    assert vision.lookups == [] and not any(no_real_dialogs.values())


def test_換主校準對_備用對的偏移跟著重算(tkroot, monkeypatch, tmp_path):
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=_with_fb((100, 50)),
                        pick=("圖示", "關閉"))
    _flow_with_coords(a)
    _place(vision, MAIN["pair"], (100, 50), (1000, 50))
    _place(vision, ("圖示", "關閉"), (190, 95), (640, 95))
    a.designate_pair()
    assert a.flow_cal["pair"] == ["圖示", "關閉"]
    fb = calibration.fallback_pair(a.flow_cal)
    assert fb["pair"] == list(FB) and fb["baseline"] == 1868.0
    assert fb["offset"] == [200, 100], "舊偏移 (100,50) + 新舊基準點差 (100,50)"
    assert calibration.fallback_anchor((10, 5), fb["offset"], 0.9) == (190, 95)


def test_換成與備用對相同的主對_拒絕(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=_with_fb(), pick=FB)
    a.designate_pair()
    assert a.flow_cal["pair"] == MAIN["pair"]
    assert any("相同" in m for m in rec)


def test_拾取當下主對找不到_改用備用對並提示(make_app, monkeypatch):
    from harness import CAL_PAIR
    from test_editor_scale import _shot
    app = make_app(1.0)
    app.flow_cal[calibration.FALLBACK_KEY] = calibration.make_fallback(FB, 100.0, (50, 30))
    for n in FB:
        app.store.add(n, b"F")
    app.vision.plan(CAL_PAIR[0], [None])
    app.vision.plan(FB[0], [(100, 200)])
    app.vision.plan(FB[1], [(200, 200)])
    monkeypatch.setattr(ui_dialogs.ui_overlay, "pick", lambda root, mode, prompt, **kw: _shot(40, 20, 280, 390))
    app.capture_template()
    [name] = [n for n in app.store.names() if n.startswith("tmpl_")]
    assert app.store.pos_of(name) == [150, 170], "基準點仍是 (150,230) (備用對換回)"
    assert any("備用校準對" in m for _, m in app.logged)
