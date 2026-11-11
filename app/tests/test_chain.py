from automation import chain
from automation.chain import Entry

TC = r"C:\Program Files\GRYPHLINK\games\Arknights_TC\Arknights.exe"
CN = r"C:\Program Files\Arknights bilibili\games\Arknights Game\Arknights.exe"


def test_空串接不開始():
    assert chain.blocker_text(chain.blockers([], {}, [TC])) == "串接裡沒有流程"


def test_各份問題_未設目標程式_程式沒在執行_依流程分組列出():
    entries = [Entry("早_繁中", 1, TC), Entry("早_簡中", 2, None), Entry("晚_簡中", 1, CN)]
    problems = {"早_繁中": ["範本不存在：\nA\nB（校準對）"], "早_簡中": [], "晚_簡中": []}
    found = chain.blockers(entries, problems, running=[TC])
    assert [(b.flow, b.problems) for b in found] == [
        ("早_繁中", ("範本不存在：\nA\nB（校準對）",)),
        ("早_簡中", ("未設目標程式",)),
        ("晚_簡中", (f"目標程式沒在執行：{CN}",))]
    assert chain.blocker_text(found) == (
        "「早_繁中」\n・範本不存在：\n　A\n　B（校準對）\n\n"
        "「早_簡中」\n・未設目標程式\n\n"
        f"「晚_簡中」\n・目標程式沒在執行：{CN}")


def test_都沒問題_可以開始_執行中的路徑大小寫與斜線不同也算():
    entries = [Entry("早_繁中", 1, TC), Entry("早_簡中", 1, CN)]
    running = [TC.upper(), CN.replace("\\", "/"), r"C:\Windows\explorer.exe"]
    assert chain.blockers(entries, {"早_繁中": [], "早_簡中": []}, running) == []


def test_同一份流程出現兩次_問題只列一次():
    entries = [Entry("早_繁中", 1, None), Entry("早_簡中", 1, CN), Entry("早_繁中", 3, None)]
    found = chain.blockers(entries, {}, running=[CN])
    assert [(b.flow, b.problems) for b in found] == [("早_繁中", ("未設目標程式",))]


def test_讀不到的流程只報讀不到():
    entries = [Entry("壞掉", 1, None, read_error="format 要是 1")]
    found = chain.blockers(entries, {}, running=[])
    assert chain.blocker_text(found) == "「壞掉」\n・讀不到流程：format 要是 1"


def _run_all(c, outcomes):
    """每份都啟動了執行器, 結束時回報 outcomes 裡對應的結果."""
    handed = []
    for out in outcomes:
        turn = c.next()
        if turn is None:
            break
        handed.append(((turn.entry.flow, turn.entry.run), c.progress()))
        c.launched()
        c.report(out)
    return handed


def test_全部完成_依序交出_進度與總結每份一行():
    entries = [Entry("早_繁中", 2, TC), Entry("早_簡中", 1, CN), Entry("收尾", 3, TC)]
    c = chain.Chain(entries)
    assert c.total == 3 and not c.finished
    handed = _run_all(c, [chain.DONE] * 3)
    assert handed == [(("早_繁中", 2), "串接 1/3：早_繁中"),
                      (("早_簡中", 1), "串接 2/3：早_簡中"),
                      (("收尾", 3), "串接 3/3：收尾")]
    assert c.next() is None and c.finished
    assert c.summary() == ["1. 早_繁中：完成", "2. 早_簡中：完成", "3. 收尾：完成"]
    assert (c.last_ran.no, c.last_ran.entry.flow) == (3, "收尾")


def test_同一份流程出現兩次_兩次都交出_總結各一行():
    entries = [Entry("早_繁中", 1, TC), Entry("早_簡中", 1, CN), Entry("早_繁中", 2, TC)]
    c = chain.Chain(entries)
    handed = _run_all(c, [chain.DONE] * 3)
    assert [h[1] for h in handed] == ["串接 1/3：早_繁中", "串接 2/3：早_簡中",
                                      "串接 3/3：早_繁中"]
    assert handed[2][0] == ("早_繁中", 2)
    assert c.summary() == ["1. 早_繁中：完成", "2. 早_簡中：完成", "3. 早_繁中：完成"]
    assert c.last_ran.no == 3


def test_執行器的結果對成串接的結果():
    assert chain.outcome("done", None) == chain.DONE
    assert chain.outcome("stopped", None) == chain.STOPPED
    assert chain.outcome("error", "找不到圖：開始") == chain.failed("找不到圖：開始")


def test_一份失敗_後面同目標程式的跳過_路徑大小寫斜線不同也算_不同目標程式照跑():
    tc_other_spelling = TC.upper().replace("\\", "/")
    entries = [Entry("早_繁中", 1, TC), Entry("早_簡中", 1, CN),
               Entry("晚_繁中", 1, tc_other_spelling), Entry("收尾", 1, CN)]
    c = chain.Chain(entries)
    handed = _run_all(c, [chain.failed("找不到圖：開始"), chain.DONE, chain.DONE])
    assert [h[0][0] for h in handed] == ["早_繁中", "早_簡中", "收尾"]
    assert [h[1] for h in handed] == ["串接 1/4：早_繁中", "串接 2/4：早_簡中",
                                      "串接 4/4：收尾"]
    assert c.next() is None and c.finished
    assert c.summary() == ["1. 早_繁中：失敗（找不到圖：開始）", "2. 早_簡中：完成",
                           "3. 晚_繁中：跳過（因為第 1 份「早_繁中」失敗）",
                           "4. 收尾：完成"]


def test_急停_正在跑的記中斷_其餘記未執行_不再交出下一份():
    entries = [Entry("早_繁中", 1, TC), Entry("早_簡中", 1, CN), Entry("收尾", 1, CN)]
    c = chain.Chain(entries)
    handed = _run_all(c, [chain.STOPPED, chain.DONE])
    assert [h[0][0] for h in handed] == ["早_繁中"]
    assert c.next() is None and c.finished
    assert c.summary() == ["1. 早_繁中：中斷（急停）", "2. 早_簡中：未執行（急停）",
                           "3. 收尾：未執行（急停）"]
    assert c.last_ran.no == 1


def test_最後一項被跳過_最後實際跑過的是它前面跑過的那份():
    entries = [Entry("早_繁中", 1, TC), Entry("早_簡中", 1, CN), Entry("晚_繁中", 1, TC)]
    c = chain.Chain(entries)
    _run_all(c, [chain.failed("找不到圖：開始"), chain.DONE])
    assert c.next() is None and c.finished
    assert (c.last_ran.no, c.last_ran.entry.flow) == (2, "早_簡中")


def test_交出了但執行器沒啟動就失敗的那份_不算實際跑過():
    entries = [Entry("早_繁中", 1, TC), Entry("早_簡中", 1, CN)]
    c = chain.Chain(entries)
    _run_all(c, [chain.DONE])
    assert c.next().no == 2
    c.report(chain.failed("找不到視窗"))
    assert c.next() is None and c.finished
    assert c.summary() == ["1. 早_繁中：完成", "2. 早_簡中：失敗（找不到視窗）"]
    assert (c.last_ran.no, c.last_ran.entry.flow) == (1, "早_繁中")


def test_急停後才回報失敗_急停優先_這份記中斷_不跳過其他():
    entries = [Entry("早_繁中", 1, TC), Entry("晚_繁中", 1, TC)]
    c = chain.Chain(entries)
    c.next()
    c.stop()
    c.report(chain.failed("找不到視窗"))
    assert c.next() is None
    assert c.summary() == ["1. 早_繁中：中斷（急停）", "2. 晚_繁中：未執行（急停）"]
    assert c.last_ran is None


def test_全部完成才算整條完成():
    c = chain.Chain([Entry("早_繁中", 1, TC), Entry("早_簡中", 1, CN)])
    _run_all(c, [chain.DONE, chain.DONE])
    assert c.next() is None and c.all_done
    c = chain.Chain([Entry("早_繁中", 1, TC), Entry("早_簡中", 1, CN)])
    _run_all(c, [chain.DONE, chain.failed("找不到圖：開始")])
    assert c.next() is None and not c.all_done


def test_急停會設串接擁有的停止旗標():
    c = chain.Chain([Entry("早_繁中", 1, TC)])
    assert not c.stop_event.is_set()
    c.stop()
    assert c.stop_event.is_set() and c.stopped


def test_一份都沒交出就結束_沒有最後實際跑過的():
    c = chain.Chain([Entry("早_繁中", 1, TC)])
    c.stop()
    assert c.next() is None and c.finished
    assert c.last_ran is None
    assert c.summary() == ["1. 早_繁中：未執行（急停）"]


def test_兩份之間急停_不再交出下一份_其餘記未執行():
    entries = [Entry("早_繁中", 1, TC), Entry("早_簡中", 1, CN), Entry("收尾", 1, CN)]
    c = chain.Chain(entries)
    assert c.next().no == 1
    c.launched()
    c.report(chain.DONE)
    c.stop()
    assert c.next() is None and c.finished
    assert c.summary() == ["1. 早_繁中：完成", "2. 早_簡中：未執行（急停）",
                           "3. 收尾：未執行（急停）"]
    assert c.last_ran.no == 1


def test_執行中急停_還沒回報結果_這份記中斷():
    entries = [Entry("早_繁中", 1, TC), Entry("早_簡中", 1, CN)]
    c = chain.Chain(entries)
    c.next()
    c.stop()
    assert c.next() is None and c.finished
    assert c.summary() == ["1. 早_繁中：中斷（急停）", "2. 早_簡中：未執行（急停）"]


def test_急停時已跳過的維持跳過():
    entries = [Entry("早_繁中", 1, TC), Entry("早_簡中", 1, CN),
               Entry("晚_繁中", 1, TC), Entry("收尾", 1, CN)]
    c = chain.Chain(entries)
    c.next()
    c.report(chain.failed("找不到視窗"))
    assert c.next().no == 2
    c.stop()
    c.report(chain.STOPPED)
    assert c.next() is None and c.finished
    assert c.summary() == ["1. 早_繁中：失敗（找不到視窗）", "2. 早_簡中：中斷（急停）",
                           "3. 晚_繁中：跳過（因為第 1 份「早_繁中」失敗）",
                           "4. 收尾：未執行（急停）"]


def test_急停後才回報完成_這份記完成_其餘未執行():
    c = chain.Chain([Entry("早_繁中", 1, TC), Entry("早_簡中", 1, CN)])
    c.next()
    c.stop()
    c.report(chain.DONE)
    assert c.next() is None
    assert c.summary() == ["1. 早_繁中：完成", "2. 早_簡中：未執行（急停）"]
