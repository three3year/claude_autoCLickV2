"""接縫 ①: runner 執行外部步驟 (假啟動模組＋虛擬時鐘, 不真的開程序)."""
import pytest

from harness import click, external, find, repeat, repeat_end

from automation.external import ToolRegistry


@pytest.fixture
def tools(tmp_path):
    d = tmp_path / "RecruitHelper"
    d.mkdir()
    (d / "recruit-step.exe").write_bytes(b"")
    return ToolRegistry({"公開招募": {"dir": str(d), "exe": "recruit-step.exe"}})


@pytest.fixture
def launcher(harness):
    return harness.launcher


def ext_record(harness):
    [r] = harness.filelog.of("external")
    return r


def test_詢問成功後正式執行_結束碼0就繼續下一步(harness, launcher, tools):
    launcher.query(lines=["42"])
    launcher.run(code=0, lines=["完成"], after=30)
    r = harness.run([find("a"), external("公開招募", "--hwnd", "123"), click(5, 0)],
                    tools=tools)
    assert r.ended == "done"
    exe, folder = tools.locate("公開招募")
    assert launcher.launches == [
        (exe, ["--hwnd", "123", "--expected-time"], folder),
        (exe, ["--hwnd", "123"], folder)]
    assert harness.kinds() == ["click", "click"]
    rec = ext_record(harness)
    assert (rec["step"], rec["tool"], rec["exit"], rec["expected"]) == (2, "公開招募", 0, "42")


def test_正式執行結束碼非0_整次失敗_紀錄有結束碼(harness, launcher, tools):
    launcher.run(code=3, lines=["錯誤：不在招募清單"])
    r = harness.run([find("a"), external("公開招募"), click(5, 0)], tools=tools)
    assert r.ended == "error"
    assert harness.kinds() == ["click"]
    text = harness.log_text()
    assert "公開招募" in text and "結束碼 3" in text
    assert "錯誤：不在招募清單" in text
    assert ext_record(harness)["exit"] == 3


@pytest.mark.parametrize("query, reason", [
    (dict(code=2, lines=["壞了"]), "結束碼 2"),
    (dict(code=0, lines=["大約十秒"]), "不是數字"),
    (dict(code=0, lines=["-3"]), "正數"),
])
def test_詢問失敗_整次失敗_不啟動正式執行(harness, launcher, tools, query, reason):
    launcher.query(**query)
    r = harness.run([find("a"), external("公開招募"), click(5, 0)], tools=tools)
    assert r.ended == "error"
    assert len(launcher.launches) == 1
    assert "預期時間" in harness.log_text() and reason in harness.log_text()
    assert harness.kinds() == ["click"]


def test_執行紀錄只收最後5行(harness, launcher, tools):
    launcher.run(code=0, lines=[f"第{i}行" for i in range(1, 8)])
    harness.run([external("公開招募")], tools=tools)
    text = harness.log_text()
    assert all(f"第{i}行" in text for i in range(3, 8))
    assert "第1行" not in text and "第2行" not in text
    assert ext_record(harness)["tail"] == " | ".join(f"第{i}行" for i in range(3, 8))


def test_工具沒登錄_執行到這一步時失敗並說明原因(harness, launcher):
    r = harness.run([click(5, 0), external("公開招募")], tools=ToolRegistry())
    assert r.ended == "error"
    assert launcher.launches == []
    assert "外部工具「公開招募」沒有登錄" in harness.log_text()


class Windows:
    """換掉 automation.win.top_window_at: 記下被問的點, 回答安排好的視窗."""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.asked = []

    def __call__(self, x, y):
        self.asked.append((x, y))
        return self.hwnd


@pytest.fixture
def windows(monkeypatch):
    import automation.runner as runner_mod
    w = Windows(0x2A0B1C)
    monkeypatch.setattr(runner_mod.win, "top_window_at", w)
    return w


def test_hwnd佔位符_詢問與正式執行都收到搜尋範圍中心的視窗(harness, launcher, tools, windows):
    r = harness.run([external("公開招募", "--hwnd", "{hwnd}")],
                    tools=tools, scan_region=[100, 200, 800, 600])
    assert r.ended == "done"
    assert windows.asked == [(500, 500)]
    assert [args for _, args, _ in launcher.launches] == [
        ["--hwnd", "2755356", "--expected-time"], ["--hwnd", "2755356"]]


def test_參數不含hwnd_不查視窗(harness, launcher, tools, windows):
    r = harness.run([external("公開招募", "--n", "3")], tools=tools)
    assert r.ended == "done"
    assert windows.asked == []


def test_佔位符在參數的一部分也代入(harness, launcher, tools, windows):
    harness.run([external("公開招募", "--hwnd={hwnd}", "x{hwnd}y")], tools=tools)
    assert launcher.launches[-1][1] == ["--hwnd=2755356", "x2755356y"]


def test_沒限定搜尋範圍_取整個桌面的中心(harness, launcher, tools, windows):
    harness.run([external("公開招募", "{hwnd}")], tools=tools, scan_region=None)
    assert windows.asked == [(960, 540)]


def test_中心點找不到視窗_整次失敗_不啟動工具(harness, launcher, tools, windows):
    windows.hwnd = None
    r = harness.run([external("公開招募", "{hwnd}")], tools=tools,
                    scan_region=[100, 200, 800, 600])
    assert r.ended == "error"
    assert launcher.launches == []
    text = harness.log_text()
    assert "公開招募" in text and "(500, 500)" in text and "找不到視窗" in text


def test_外部步驟在重複區段裡_每次都執行(harness, launcher, tools):
    r = harness.run([find("a"), repeat(2), external("公開招募"), repeat_end()],
                    tools=tools)
    assert r.ended == "done"
    assert len(launcher.launches) == 4
