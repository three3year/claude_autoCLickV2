import harness

from automation import external, flowcheck, flowdefaults


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


def test_外部步驟當分支開頭_跟其他非找圖步驟一樣被擋():
    ext = st("external", external="公開招募")
    steps = [st("branch_start"), st("find"), st("branch_or"), ext, st("branch_end")]
    assert flowcheck.section_error(steps) == "分岔的每個分支開頭必須是「找圖點擊」步驟"
    steps = [st("branch_start"), st("find"), ext, st("branch_or"), st("find_click"),
             st("branch_end")]
    assert flowcheck.section_error(steps) is None, "分支裡非開頭的位置可以放"


def test_或不在分岔內():
    steps = [st("repeat_start", repeat=2), st("find"), st("branch_or"),
             st("repeat_end")]
    assert flowcheck.section_error(steps) == "「分岔（或）」必須直接位於分岔區段內"


def test_整份流程的錯誤清單():
    flow = {"calibration": {"pair": ["a", "b"], "baseline": 1.0}, "busy": None,
            "steps": [st("click"), st("find_click", busy_check=True)]}
    errs = flowcheck.flow_errors(flow)
    assert len(errs) == 2
    assert errs[0].startswith("步驟 1：座標點擊以原點為基準")
    assert errs[1].startswith("步驟 2：勾了忙碌檢查")


# ---- 「執行」前會擋的檢查 (run_problems) ----

CAL = {"pair": ["c1", "c2"], "baseline": 100.0}
HAVE = {"a", "c1", "c2"}


def run_flow(steps, calibration=CAL, busy=None):
    return {"steps": steps, "calibration": calibration, "busy": busy}


def problems(flow, templates=HAVE, tools=None):
    return flowcheck.run_problems(flow, templates, tools or external.ToolRegistry())


def test_執行前檢查_合格的流程沒有問題():
    assert problems(run_flow([st("find_click")])) == []


def test_執行前檢查_沒有步驟():
    [p] = problems(run_flow([]))
    assert (p.category, p.title, p.text) == (flowcheck.NO_STEPS, "執行", "請先新增步驟")


def test_執行前檢查_沒有校準對():
    [p] = problems(run_flow([st("find_click")], calibration=None))
    assert (p.category, p.title) == (flowcheck.NO_CALIBRATION, "執行")
    assert p.text == ("這份流程沒有校準對（尚未設定），不能執行。\n"
                      "請先在「流程設定…」設定校準對（遊戲畫面內兩張相距夠遠的固定圖）")


def test_執行前檢查_範本缺圖_找圖確認圖校準對忙碌指示一則列出():
    steps = [st("find_click", target={"template": "門"}),
             st("click", confirm="appear", confirm_target={"template": "勾"}),
             st("find", target={"template": ""})]
    flow = run_flow(steps, calibration={"pair": ["c1", "右上"], "baseline": 100.0},
                    busy={"template": "沙漏"})
    [p] = problems(flow, templates={"c1"})
    assert (p.category, p.title) == (flowcheck.MISSING_TEMPLATES, "執行")
    assert p.text == ("範本不存在：\n門\n勾（確認圖）\n(未選擇)\n"
                      "右上（校準對）\n沙漏（忙碌指示）")


def test_執行前檢查_外部工具找不到_沒登錄與路徑不存在都擋(tmp_path):
    steps = [st("find_click"), st("external", external="公開招募"),
             st("external", external="基建")]
    tools = external.ToolRegistry({"基建": {"dir": str(tmp_path / "沒有"), "exe": "x.exe"}})
    [p] = problems(run_flow(steps), tools=tools)
    assert (p.category, p.title) == (flowcheck.TOOLS_NOT_FOUND, "執行")
    assert p.text == ("外部工具找不到：\n"
                      "外部工具「公開招募」沒有登錄（流程資料夾的 external_tools.yaml）\n"
                      f"外部工具「基建」登錄的資料夾不存在：{tmp_path / '沒有'}")


def test_執行前檢查_勾了忙碌檢查卻沒設忙碌指示():
    steps = [st("find_click", busy_check=True), st("find"),
             st("find_click", busy_check=True)]
    [p] = problems(run_flow(steps))
    assert (p.category, p.title) == (flowcheck.BUSY_NOT_SET, "執行")
    assert p.text == ("有步驟勾了「忙碌檢查」，但這份流程沒有設定忙碌指示：\n"
                      "步驟 1, 3\n"
                      "請先在「流程設定…」設定忙碌指示，或取消這些步驟的勾選")
    assert problems(run_flow(steps, busy={"template": "a"})) == []


def test_執行前檢查_區段結構錯():
    [p] = problems(run_flow([st("find"), st("repeat_end")]))
    assert (p.category, p.title) == (flowcheck.SECTION_ERROR, "執行")
    assert p.text == "步驟 2「重複結束」缺少對應的開始標記"


def test_執行前檢查_原點的圖離開_原點不是找圖():
    steps = [st("click", confirm="gone"), st("find_click"), st("click", confirm="gone"),
             st("click"), st("click", confirm="gone")]
    [p] = problems(run_flow(steps))
    assert (p.category, p.title) == (flowcheck.ORIGIN_LEAVES_NOT_FIND, "執行")
    assert p.text == ("「原點的圖離開」需要原點來自找圖步驟：\n"
                      "步驟 1, 5 前面最近的原點來自點擊／拖曳（或沒有原點）。\n"
                      "請在它前面放找圖步驟當原點，或改用確認圖")


def test_執行前檢查_點到下一步的圖出現_下一步不是找圖():
    steps = [st("click", confirm="next"), st("wait"), st("find_click", confirm="next"),
             st("find"), st("click", confirm="next")]
    [p] = problems(run_flow(steps))
    assert (p.category, p.title) == (flowcheck.CONFIRM_NEXT_NOT_FIND, "執行")
    assert p.text == ("「點到下一步的圖出現」需要下一個步驟是找圖步驟：\n"
                      "步驟 1, 5 的下一步不是找圖（或已是最後一步）。\n"
                      "請把下一個找圖步驟排在其後")


def test_執行前檢查_全部列出_依單獨執行的檢查順序():
    assert [p.category for p in problems(run_flow([], calibration=None))] == [
        flowcheck.NO_STEPS, flowcheck.NO_CALIBRATION]
    steps = [st("click", confirm="gone"),
             st("find_click", target={"template": "沒圖"}, busy_check=True),
             st("external", external="公開招募"), st("click", confirm="next"),
             st("repeat_end")]
    assert [p.category for p in problems(run_flow(steps, calibration=None))] == [
        flowcheck.NO_CALIBRATION, flowcheck.MISSING_TEMPLATES,
        flowcheck.TOOLS_NOT_FOUND, flowcheck.BUSY_NOT_SET, flowcheck.SECTION_ERROR,
        flowcheck.ORIGIN_LEAVES_NOT_FIND, flowcheck.CONFIRM_NEXT_NOT_FIND]


def test_執行前檢查_不擋相對座標前面沒有原點_flow_errors才擋():
    flow = run_flow([st("click"), st("find_click")])
    assert problems(flow) == []
    assert flowcheck.flow_errors(flow)[0].startswith("步驟 1：座標點擊以原點為基準")


def test_執行前檢查_對磁碟上的流程資料夾_範本與外部工具登錄取自該資料夾(tmp_path):
    import flowfile
    folder = tmp_path / "早_繁中"
    flow = flowfile.new_flow()
    flow.update(calibration=CAL, steps=[st("find_click", target={"template": "門"}),
                                        st("external", external="公開招募")])
    flowfile.write_flow(str(folder), flow, images={"c1": b"png", "c2": b"png"})
    (folder / flowfile.TOOLS_YAML).write_text("- 不是對照表\n", encoding="utf-8")

    flow = flowfile.read_flow(str(folder))
    got = flowcheck.run_problems(flow, flowfile.folder_template_names(str(folder)),
                                 flow["tools"])
    assert [(p.category, p.text) for p in got] == [
        (flowcheck.MISSING_TEMPLATES, "範本不存在：\n門"),
        (flowcheck.TOOLS_NOT_FOUND, "外部工具找不到：\n外部工具登錄（external_tools.yaml）"
                                    "格式錯：最外層要是 {工具名: {dir, exe}}")]
