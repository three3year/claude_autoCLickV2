import harness
from harness import click, drag, find, tgt

import app as app_mod
import flowfile
from test_confirm_next_ui import _MiniApp
from test_editor_scale import _edit, _press, make_app  # noqa: F401


def _combo(dr, value_contains):
    from test_template_picker import _all
    for w in _all(dr.dlg):
        if w.winfo_class() == "TCombobox" and any(
                value_contains in v for v in w.cget("values")):
            return w
    raise AssertionError(f"找不到含「{value_contains}」的下拉選單")


def _pick(value_contains, choice):
    def act(dr):
        cb = _combo(dr, value_contains)
        cb.set(next(v for v in cb.cget("values") if choice in v))
        cb.event_generate("<<ComboboxSelected>>")
        dr.dlg.update()
    return act


def test_座標點擊對話框保留確認圖設定_找不到時預設停止(make_app):
    a = make_app(1.0)
    a.store.add("ok", b"O")
    got = _edit(a, click(10, 10, confirm="appear", _edit=True,
                         confirm_target=tgt("ok", color=True)),
                _press("確定"), title="編輯：座標點擊")
    assert got["confirm"] == "appear"
    assert got["confirm_target"] == {"template": "ok", "color": True}
    assert got["on_fail"] == "stop"
    assert (got["timeout"], got["interval"]) == (5, 0.3), "「沒寫＝」表的預設"


def test_拖曳對話框改成下一步的圖出現(make_app):
    a = make_app(1.0)
    got = _edit(a, drag(1, 2, 3, 4, _edit=True),
                _pick("做到下一步", "下一步"), _press("確定"),
                title="編輯：滑鼠拖曳")
    assert got["confirm"] == "next"
    assert "confirm_target" not in got and got["on_fail"] == "stop"


def test_改回不確認時不留任何確認欄位(make_app):
    a = make_app(1.0)
    a.store.add("ok", b"O")
    got = _edit(a, click(10, 10, confirm="appear", confirm_target=tgt("ok"),
                         timeout=3, on_fail="skip", _edit=True),
                _pick("不確認", "不確認"), _press("確定"), title="編輯：座標點擊")
    assert got["confirm"] == "none"
    for k in ("confirm_target", "timeout", "interval", "on_fail"):
        assert k not in got, k


def test_確認圖出現卻沒選確認圖_擋下_錯誤在底列不彈窗(make_app, no_real_dialogs):
    from test_fixed_rect_ui import _labels
    a = make_app(1.0)
    seen = {}

    def ok_then_cancel(dr):
        dr.press("確定")
        seen["open"] = dr.dlg.winfo_exists()
        seen["labels"] = _labels(dr.dlg)
        dr.press("取消")

    got = _edit(a, click(10, 10, _edit=True),
                _pick("做到確認圖", "確認圖"), ok_then_cancel,
                title="編輯：座標點擊")
    assert got is None and seen["open"]
    assert "「做到確認圖出現為止」需選擇確認圖" in seen["labels"]
    assert not any(no_real_dialogs.values())


def test_步驟摘要顯示座標點擊與拖曳的確認方式():
    s = app_mod.step_desc(click(1, 2, confirm="appear", confirm_target=tgt("ok")))
    assert "做到確認圖「ok」出現（逾時5s→停止）" in s
    s = app_mod.step_desc(drag(1, 2, 3, 4, confirm="next", on_fail="skip"))
    assert "做到下一步的圖出現（逾時5s→跳過）" in s
    assert "做到" not in app_mod.step_desc(click(1, 2))


def test_下一步不是找圖的座標點擊與拖曳有警告標記(tkroot):
    tkroot.withdraw()
    a = _MiniApp(tkroot, [click(1, 2, confirm="next"), click(3, 4),
                          drag(1, 2, 3, 4, confirm="next"), find("a"),
                          drag(1, 2, 3, 4, confirm="next")])
    try:
        a.render_steps()
        lines = a.step_list.get("1.0", "end").splitlines()
        assert ["⚠" in ln for ln in lines] == [True, False, False, False, True]
        assert a._confirm_next_bad(a.steps) == [0, 4], "執行與測試選取前也會擋"
    finally:
        a.step_list.destroy()


def test_座標點擊與拖曳的確認圖是被引用的範本_改名跟著改():
    steps = [click(1, 2, confirm="appear", confirm_target=tgt("ok")),
             drag(1, 2, 3, 4, confirm="appear", confirm_target=tgt("ok2")),
             click(1, 2, confirm_target=tgt("stale"))]
    assert flowfile.used_templates(steps) == ["ok", "ok2"]
    assert flowfile.rename_refs(steps, "ok", "確認") == 1
    assert steps[0]["confirm_target"]["template"] == "確認"


def test_執行前檢查_座標點擊的確認圖不在本流程就擋下(tkroot, monkeypatch, tmp_path):
    from test_calibration_ui import _CalApp, _warnings
    rec = _warnings(monkeypatch)
    a = _CalApp(tkroot, tmp_path, cal={"pair": ["p", "q"], "baseline": 100.0})
    a.steps = [click(1, 2, confirm="appear", confirm_target=tgt("不見了"))]
    a.start_run()
    assert a.runner.started == []
    assert any("不見了（確認圖）" in m for m in rec)


def test_拖曳對話框可選原點的圖離開_摘要顯示(make_app):
    a = make_app(1.0)
    got = _edit(a, drag(1, 2, 3, 4, _edit=True),
                _pick("原點的圖離開", "原點的圖離開"), _press("確定"),
                title="編輯：滑鼠拖曳")
    assert got["confirm"] == "gone" and got["on_fail"] == "stop"
    assert "做到原點的圖離開（逾時5s→停止）" in app_mod.step_desc(got)


def test_原點不是來自找圖時有警告標記且執行前擋下(tkroot):
    from harness import wait
    tkroot.withdraw()
    leaves = dict(confirm="gone")
    a = _MiniApp(tkroot, [find("row1", type="find"), wait(0.3),
                          drag(0, 0, 0, -100, **leaves),
                          drag(0, 0, 0, -100, **leaves),
                          click(5, 5), click(0, 0, **leaves),
                          find("x", type="find", update_origin=False),
                          click(0, 0, **leaves)])
    try:
        a.render_steps()
        lines = a.step_list.get("1.0", "end").splitlines()
        assert ["⚠" in ln for ln in lines] == [False, False, False, True,
                                              False, True, False, True]
        assert a._origin_leaves_bad(a.steps) == [3, 5, 7]
        assert a._origin_leaves_bad(a.steps[2:3]) == [0], \
            "測試選取片段沒包含原點來源＝擋"
    finally:
        a.step_list.destroy()


def test_執行時原點的圖離開不成立就擋下(tkroot, monkeypatch, tmp_path):
    from test_calibration_ui import _CalApp, _warnings
    rec = _warnings(monkeypatch)
    a = _CalApp(tkroot, tmp_path, cal={"pair": ["p", "q"], "baseline": 100.0})
    a.steps = [click(1, 2), drag(0, 0, 0, 9, confirm="gone")]
    a.start_run()
    assert a.runner.started == []
    assert any("原點的圖離開" in m and "步驟 2" in m for m in rec)
