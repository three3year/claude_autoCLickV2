"""步驟編輯器版面 B (ui-slim 07/08): 兩欄、哪些欄位看得到、找圖目標直接在主對話框設、
驗證錯誤在底列、寬度固定、確定永遠在工作區內、⚠ 一行.

沿用 test_editor_scale 的最小 App 與 `_Driver`／`_edit`: 對話框真的開、真的發事件;
斷言對話框回傳的步驟與看得到的欄位標題 (以標題文字找), 不看內部欄位。
"""
import harness  # noqa: F401  # 先把 app/ 加進 sys.path
from harness import click, drag, find, tgt

import ui_dialogs
from automation import flowdefaults, win
from test_editor_scale import _edit, _press, make_app  # noqa: F401 (fixture)
from test_fixed_rect_ui import FIXED_ZH, RECT, _choose, _labels, _overlay
from test_pointer_confirm_ui import _combo, _pick
from test_template_picker import _all

FIND_LEFT = ["範本", "限定範圍", "挑選規則", "比色"]
TITLES = ["範本", "限定範圍", "挑選規則", "比色", "動作", "點擊偏移", "生效確認", "確認圖",
          "忙碌檢查", "原點", "等待逾時", "找不到時", "偏移", "起點", "終點", "拖曳時間",
          "放開前停頓", "等待時間", "重複次數", "跳出到此時"]


def _shown_titles(dlg):
    """看得到的欄位標題 (依畫面由上到下、由左到右)."""
    dlg.update()
    got = [(w.winfo_rootx(), w.winfo_rooty(), str(w.cget("text"))) for w in _all(dlg)
           if w.winfo_class() == "TLabel" and str(w.cget("text")) in TITLES
           and w.winfo_ismapped()]
    left = min(x for x, _, _ in got)
    cols = {}
    for x, y, text in got:
        cols.setdefault(x - left > 300, []).append((y, text))
    return [t for side in sorted(cols) for _, t in sorted(cols[side])]


def _look(seen, key="titles"):
    def act(dr):
        seen[key] = _shown_titles(dr.dlg)
    return act


def _cancel(dr):
    dr.press("取消")


def _open(app, step, *actions, title):
    return _edit(app, dict(step, _edit=True), *actions, _cancel, title=title)


# ---------- 找圖: 哪些欄位看得到 ----------

def test_找圖點擊_左卡找什麼_右卡找到之後(make_app):
    seen = {}
    _open(make_app(1.0), find("a"), _look(seen), title="編輯：找圖點擊")
    assert seen["titles"] == FIND_LEFT + ["動作", "點擊偏移", "生效確認", "忙碌檢查", "原點",
                                          "等待逾時", "找不到時"]


def test_找圖_確認圖只在確認圖出現時出現(make_app):
    a = make_app(1.0)
    seen = {}
    _open(a, find("a"), _pick("點到確認圖", "確認圖"), _look(seen),
          _pick("點到確認圖", "下一步"), _look(seen, "next"), title="編輯：找圖點擊")
    assert seen["titles"][4:] == ["動作", "點擊偏移", "生效確認", "確認圖", "忙碌檢查", "原點",
                                  "等待逾時", "找不到時"]
    assert "確認圖" not in seen["next"]


def test_找圖不點擊_沒有點擊偏移生效確認與忙碌檢查(make_app):
    seen = {}
    _open(make_app(1.0), find("a", confirm="appear", confirm_target=tgt("b")),
          _pick("不點擊", "等待消失"), _look(seen), title="編輯：找圖點擊")
    assert seen["titles"] == FIND_LEFT + ["動作", "原點", "等待逾時", "找不到時"]


def test_每個欄位標題旁都有說明圖示(make_app):
    seen = {}

    def tips(dr):
        seen["n"] = sum(1 for w in _all(dr.dlg) if w.winfo_class() == "Label"
                        and str(w.cget("text")) == "ⓘ" and w.winfo_ismapped())
        seen["titles"] = _shown_titles(dr.dlg)
    _open(make_app(1.0), find("a"), tips, title="編輯：找圖點擊")
    assert seen["n"] == len(seen["titles"])


# ---------- 找圖目標直接在主對話框設 ----------

def test_限定範圍挑選規則比色_在主對話框設完存進找圖目標(make_app, monkeypatch):
    a = make_app(1.0)
    a.store.add("a", b"A")
    _overlay(monkeypatch)

    def nth(dr):
        spin = next(w for w in _all(dr.dlg) if w.winfo_class() == "TSpinbox"
                    and w.winfo_ismapped() and w.cget("to") == 99)
        spin.set(2)

    def color(dr):
        lbl = next(w for w in _all(dr.dlg) if w.winfo_class() == "Label"
                   and "顏色不符" in str(w.cget("text")))
        lbl.event_generate("<Button-1>")
        dr._update()

    got = _edit(a, dict(find("a"), _edit=True), _choose(FIXED_ZH), _press("框選"),
                _pick("分數最高", "由上到下"), nth, color, _press("確定"),
                title="編輯：找圖點擊")
    assert got["target"] == {"template": "a", "within": RECT, "pick": {"top": 2},
                             "color": True}


def test_不限定時座標行收起_框選停用(make_app):
    seen = {}

    def look(dr):
        btn = next(w for w in _all(dr.dlg) if w.winfo_class() == "TButton"
                   and w.cget("text") == "框選")
        seen["disabled"] = btn.instate(["disabled"])
        seen["coords"] = [t for t in _labels(dr.dlg) if t.startswith("固定矩形 (")
                          or t == "（還沒框選）"]
        dr._update()
        seen["mapped"] = any(w.winfo_ismapped() for w in _all(dr.dlg)
                             if w.winfo_class() == "TLabel"
                             and str(w.cget("text")).startswith("固定矩形 ("))
    _open(make_app(1.0), find("a", target={"within": list(RECT)}),
          _choose(ui_dialogs.LIMIT_ZH["none"]), look, title="編輯：找圖點擊")
    assert seen["disabled"] and not seen["mapped"]


def test_最接近指定點_原點XY點選另起一行(make_app):
    seen = {}

    def look(dr):
        dr._update()
        combo = _combo(dr, "最接近指定點")
        pick_btn = next(w for w in _all(dr.dlg) if w.winfo_class() == "TButton"
                        and w.cget("text") == "點選")
        seen["below"] = pick_btn.winfo_rooty() > combo.winfo_rooty() + combo.winfo_height() - 2
    _open(make_app(1.0), find("a", target={"pick": {"near": [3, 4]}}), look,
          title="編輯：找圖點擊")
    assert seen["below"]


# ---------- 驗證錯誤在底列、⚠ 一行 ----------

def test_沒選範本_錯誤在底列_對話框不關_不彈窗(make_app, no_real_dialogs):
    seen = {}

    def ok(dr):
        dr.press("確定")
        seen["open"] = dr.dlg.winfo_exists()
        seen["labels"] = _labels(dr.dlg)
    got = _edit(make_app(1.0), flowdefaults.new_step("find_click"), ok, _cancel,
                title="新增：找圖點擊")
    assert got is None and seen["open"]
    assert "請選擇範本圖片" in seen["labels"]
    assert not any(no_real_dialogs.values())


def test_點到下一步的圖出現_下一步不是找圖_一行警告_照樣可存(make_app):
    a = make_app(1.0)
    a.store.add("a", b"A")
    seen = {}

    def look(dr):
        dr._update()
        seen["warn"] = [t for t in _labels(dr.dlg) if t.startswith("⚠")]
    got = _edit(a, find("a", _index=0), _pick("點到確認圖", "下一步"), look,
                _press("確定"), title="新增：找圖點擊")
    assert seen["warn"] == ["⚠ 下一步要是找圖步驟"]
    assert got["confirm"] == "next"


def test_拖曳原點的圖離開_原點不是找圖_一行警告(make_app):
    a = make_app(1.0)
    a.steps = [click(1, 2)]
    seen = {}

    def look(dr):
        seen["warn"] = [t for t in _labels(dr.dlg) if t.startswith("⚠")]
    _edit(a, dict(drag(0, 0, 0, 9), _index=1), _pick("原點的圖離開", "原點的圖離開"), look,
          _cancel, title="新增：滑鼠拖曳")
    assert seen["warn"] == ["⚠ 原點要來自找圖步驟（前面放一個找圖）"]


# ---------- 座標點擊、拖曳 ----------

def test_座標點擊_不確認時沒有逾時與找不到時(make_app):
    seen = {}
    _open(make_app(1.0), click(1, 2), _look(seen), _pick("做到確認圖", "確認圖"),
          _look(seen, "appear"), title="編輯：座標點擊")
    assert seen["titles"] == ["偏移", "原點", "生效確認", "忙碌檢查"]
    assert seen["appear"] == ["偏移", "原點", "生效確認", "確認圖", "忙碌檢查",
                              "等待逾時", "找不到時"]


def test_拖曳_左卡起點終點時間停頓_沒有原點勾選(make_app):
    seen = {}
    _open(make_app(1.0), drag(1, 2, 3, 4, confirm="next"), _look(seen),
          title="編輯：滑鼠拖曳")
    assert seen["titles"] == ["起點", "終點", "拖曳時間", "放開前停頓", "生效確認", "忙碌檢查",
                              "等待逾時", "找不到時"]


# ---------- 寬度固定、高度在工作區內 ----------

def _width(seen, key):
    def act(dr):
        dr._update()
        seen.setdefault(key, []).append(dr.dlg.winfo_width())
    return act


def test_切任何選項寬度都不變(make_app, monkeypatch):
    _overlay(monkeypatch)
    seen = {}
    w = _width(seen, "w")
    _open(make_app(1.0), find("a"), w, _pick("點到確認圖", "確認圖"), w,
          _choose(FIXED_ZH), _press("框選"), w, _pick("分數最高", "最接近"), w,
          _pick("不點擊", "等待消失"), w, title="編輯：找圖點擊")
    assert len(set(seen["w"])) == 1, seen["w"]


def test_找圖_座標點擊_拖曳的對話框一樣寬(make_app):
    seen = {}
    for step, title in ((find("a"), "編輯：找圖點擊"), (click(1, 2), "編輯：座標點擊"),
                        (drag(1, 2, 3, 4), "編輯：滑鼠拖曳")):
        _open(make_app(1.0), step, _width(seen, "w"), title=title)
    assert len(set(seen["w"])) == 1, seen["w"]


def test_全部攤開的需求高度小於工作區(make_app, monkeypatch):
    _overlay(monkeypatch)
    a = make_app(1.0)
    seen = {}

    def height(dr):
        dr._update()
        x1, y1, x2, y2 = win.monitor_work_area(dr.dlg.winfo_id())
        seen["h"], seen["limit"] = dr.dlg.winfo_reqheight(), y2 - y1
    _open(a, find("a", confirm="appear", confirm_target=tgt("b", color=True),
                  target={"pick": {"near": [0, 0]}, "within": list(RECT)}),
          height, title="編輯：找圖點擊")
    assert seen["h"] < seen["limit"]


# ---------- 簡單步驟 ----------

def test_簡單步驟各一列_回傳值照舊(make_app):
    a = make_app(1.0)
    seen = {}

    def set_spin(value):
        def act(dr):
            next(w for w in _all(dr.dlg) if w.winfo_class() == "TSpinbox").set(value)
        return act
    got = _edit(a, {"type": "wait", "wait": 1.0}, _look(seen, "wait"), set_spin(2.5),
                _press("確定"), title="新增：等待")
    assert got == {"type": "wait", "wait": 2.5} and seen["wait"] == ["等待時間"]
    got = _edit(a, {"type": "repeat_start", "repeat": 3}, set_spin(4), _press("確定"),
                title="新增：重複開始")
    assert got == {"type": "repeat_start", "repeat": 4}
    got = _edit(a, {"type": "branch_end", "_edit": True}, _look(seen, "end"),
                _pick("繼續往下", "再往外"), _press("確定"), title="編輯：分岔結束")
    assert got == {"type": "branch_end", "on_break": "break"}
    assert seen["end"] == ["跳出到此時"]
