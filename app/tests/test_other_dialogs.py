"""步驟編輯器以外的對話框也照說明文字規則 (ui-slim 09): 說明收進 ⓘ、驗證錯誤在底列一行
(不彈窗)、確認圖的找圖設定子對話框跟步驟編輯器的左卡同一套欄位.

對話框真的開 (`_Driver`), 看得到什麼以文字找。
"""
import harness  # noqa: F401  # 先把 app/ 加進 sys.path

import ui_dialogs
from test_editor_scale import make_app  # noqa: F401 (fixture)
from test_fixed_rect_ui import _labels, _target_dialog
from test_pointer_confirm_ui import _combo
from test_template_picker import TITLE, _all, _Driver, _open, picker  # noqa: F401


def _tips(dlg):
    return [w for w in _all(dlg) if w.winfo_class() == "Label"
            and str(w.cget("text")) == "ⓘ"]


def _cal_pair(app, *actions):
    d = _Driver(app.root, "設定校準對")
    d.run(*actions)
    got = ui_dialogs.pick_cal_pair(app)
    if d.error is not None:
        raise d.error
    return got


def test_指定校準對_說明在說明圖示裡_沒選滿底列提示不彈窗(make_app, no_real_dialogs):
    app = make_app(1.0)
    app.store.add("圖示", b"I")
    seen = {}

    def ok_empty(dr):
        dr.press("確定並量測")
        seen["labels"] = _labels(dr.dlg)
        seen["tips"] = len(_tips(dr.dlg))
        seen["long"] = [t for t in _labels(dr.dlg) if len(t) > 30]

    def choose(dr):
        boxes = [w for w in _all(dr.dlg) if w.winfo_class() == "TCombobox"]
        for cb, v in zip(boxes, ("圖示", "cal_left")):
            cb.set(v)
        dr.press("確定並量測")
    got = _cal_pair(app, ok_empty, choose)
    assert "請選滿兩個範本" in seen["labels"]
    assert seen["tips"] == 1 and seen["long"] == [], "沒有常駐的長說明"
    assert not any(no_real_dialogs.values())
    assert got == ("圖示", "cal_left")


def test_確認圖的找圖設定_欄位與左卡相同_每欄有說明圖示(make_app):
    app = make_app(1.0)
    seen = {}

    def look(dr):
        dr._update()
        seen["tips"] = len(_tips(dr.dlg))
        combo = _combo(dr, "最接近指定點")
        btn = next(w for w in _all(dr.dlg) if w.winfo_class() == "TButton"
                   and w.cget("text") == "點選")
        seen["below"] = btn.winfo_rooty() >= combo.winfo_rooty() + combo.winfo_height() - 2
        seen["long"] = [t for t in _labels(dr.dlg) if len(t) > 30]
        dr.close()
    _target_dialog(app, {"template": "a", "pick": {"near": [1, 2]}}, look)
    assert seen["tips"] == 3
    assert seen["below"], "指定點另起一行"
    assert seen["long"] == []


def test_選範本對話框_說明收進說明圖示(picker):
    seen = {}

    def look(dr):
        seen["tips"] = len(_tips(dr.dlg))
        seen["long"] = [t for t in _labels(dr.dlg) if "按「確定」才會" in t]
        dr.press("取消")
    _open(picker, _Driver(picker.root, TITLE), look)
    assert seen["tips"] == 1 and seen["long"] == []
