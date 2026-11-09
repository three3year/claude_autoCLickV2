"""拾取與按確定後的拾取檢查: 先`避開游標`等主畫面停穩, 凍結停穩那張; 量完游標移回原位."""
from harness import CAL_PAIR, Screen

import app as app_mod
import ui_dialogs
from test_editor_scale import REGION, _press, _shot, make_app  # noqa: F401
from test_fixed_rect_ui import _target_dialog
from test_pickcheck_ui import _engine, _template

STOP = (REGION[0] - 2, REGION[1] + REGION[3] + 1)
HOME = (900, 600)
# 倉庫那張逐次收斂: 倍率 0.5 → 0.8 → 1.0 → 1.0, 第 4 次才停穩
CONVERGING = [(200, 230), (230, 230), (250, 230), (250, 230)]


def _record_grabs(monkeypatch, fake_cursor):
    """每次截圖: (那張圖, 截圖範圍, 當時游標在哪)."""
    seen = []

    def grab(region=None):
        org = (region[0], region[1]) if region else (0, 0)
        img = Screen(org, (region[2], region[3]) if region else (1920, 1080))
        seen.append((img, tuple(region) if region else None, fake_cursor.cursor_pos()))
        return img, org
    monkeypatch.setattr(app_mod.capture, "grab", grab)
    return seen


def test_截圖新增_凍結的是停穩那張_用停穩那次的倍率_拾取後游標回原位(
        make_app, monkeypatch, fake_cursor):
    app = make_app(1.0)
    app.vision.plan(CAL_PAIR[1], CONVERGING)
    fake_cursor.move(*HOME)
    grabs = _record_grabs(monkeypatch, fake_cursor)
    shown = []

    def pick(root, mode, prompt, **kw):
        shown.append((kw["shot"], fake_cursor.cursor_pos()))
        return _shot(40, 20, 210, 250)
    monkeypatch.setattr(ui_dialogs.ui_overlay, "pick", pick)
    app.capture_template()
    assert len(grabs) == 4 and all(cur == STOP for _img, _r, cur in grabs), \
        "每張都在游標移到停點後截"
    [(shot, cursor_when_shown)] = shown
    assert shot[0] is grabs[-1][0], "覆蓋層凍結的就是停穩那張"
    assert cursor_when_shown == HOME, "凍結後、框選前游標已移回原位"
    [name] = [n for n in app.store.names() if n.startswith("tmpl_")]
    assert app.store.pos_of(name) == [80, 30], "拍攝位置照停穩的倍率 ×1.0 換算"
    assert fake_cursor.cursor_pos() == HOME


def test_找圖設定按確定_拾取檢查用停穩後的倍率_檢查完游標回原位(
        make_app, monkeypatch, fake_cursor):
    app = make_app(1.0)
    _engine(app, monkeypatch)
    _template(app, "a", 50, 50)
    app.vision.plan(CAL_PAIR[1], CONVERGING)
    app.vision.plan("a", [(300, 400)])
    fake_cursor.move(*HOME)
    grabs = _record_grabs(monkeypatch, fake_cursor)
    _target_dialog(app, {"template": "a"}, _press("確定"))
    assert len(grabs) == 4 and all(r == tuple(REGION) and cur == STOP
                                   for _img, r, cur in grabs)
    scales = [round(s, 3) for n, s in app.vision.expected_scales if n == "a"]
    assert scales == [0.85, 1.15, 1.0], "縮放餘裕與唯一都以停穩後的 ×1.0 為準"
    assert fake_cursor.cursor_pos() == HOME


def test_找圖設定按確定_等停穩時出錯_對話框照關_紀錄區寫失敗_游標回原位(
        make_app, monkeypatch, fake_cursor):
    app = make_app(1.0)
    _engine(app, monkeypatch)
    _template(app, "a", 50, 50)
    fake_cursor.move(*HOME)

    def boom(*a, **k):
        raise RuntimeError("壞掉了")
    monkeypatch.setattr(ui_dialogs.calibration, "calibrate", boom)
    got = _target_dialog(app, {"template": "a"}, _press("確定"))
    assert got is not None
    assert any(lvl == "error" and "拾取檢查失敗" in m and "壞掉了" in m
               for lvl, m in app.logged)
    assert not app.recognition.busy
    assert fake_cursor.cursor_pos() == HOME
