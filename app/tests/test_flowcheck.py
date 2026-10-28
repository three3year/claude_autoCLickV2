import harness

from automation import flowcheck, flowdefaults


def st(t, **kw):
    if t in ("find_click", "find", "wait_gone"):
        kw.setdefault("target", {"template": "a"})
    if t == "click":
        kw.setdefault("click", [0, 0])
    return flowdefaults.complete(dict(kw, type=t))


def test_成對巢狀的區段沒有錯誤():
    steps = [st("repeat_start", repeat=2), st("branch_start"), st("find_click"),
             st("branch_or"), st("find"), st("branch_end"), st("repeat_end")]
    assert flowcheck.section_error(steps) is None


def test_交錯區段():
    steps = [st("repeat_start", repeat=2), st("branch_start"), st("find_click"),
             st("repeat_end"), st("branch_end")]
    err = flowcheck.section_error(steps)
    assert err.startswith("區段交錯：步驟 4「重複結束」之前") and "步驟 2" in err


def test_缺結束與缺開始():
    assert "步驟 1「重複開始」缺少對應的結束標記" in flowcheck.section_error(
        [st("repeat_start", repeat=2), st("find")])
    assert "步驟 2「重複結束」缺少對應的開始標記" in flowcheck.section_error(
        [st("find"), st("repeat_end")])


def test_分岔分支開頭不是找圖():
    steps = [st("branch_start"), st("find"), st("branch_or"), st("click"),
             st("branch_end")]
    assert flowcheck.section_error(steps) == "分岔的每個分支開頭必須是「找圖點擊」步驟"


def test_或不在分岔內():
    steps = [st("repeat_start", repeat=2), st("find"), st("branch_or"),
             st("repeat_end")]
    assert flowcheck.section_error(steps) == "「分岔（或）」必須直接位於分岔區段內"


def test_app執行前檢查呼叫同一個函式():
    import app as app_mod
    steps = [st("repeat_start", repeat=2), st("branch_start"), st("find_click"),
             st("repeat_end"), st("branch_end")]
    assert app_mod.App._flow_error(None, steps) == flowcheck.section_error(steps)


def test_整份流程的錯誤清單():
    flow = {"calibration": {"pair": ["a", "b"], "baseline": 1.0}, "busy": None,
            "steps": [st("click"), st("find_click", busy_check=True)]}
    errs = flowcheck.flow_errors(flow)
    assert len(errs) == 2
    assert errs[0].startswith("步驟 1：座標點擊以原點為基準")
    assert errs[1].startswith("步驟 2：勾了忙碌檢查")
