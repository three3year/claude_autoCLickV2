"""開始執行／測試選取前檢查外部工具: 缺什麼就擋下並列出 (Tk, 隱藏桌面跑)."""
import pytest
from harness import external, wait

from automation.external import ToolRegistry
from test_calibration_ui import _CalApp, _warnings

CAL = {"pair": ["p", "q"], "baseline": 100.0}


def _tool_dir(tmp_path, make_dir=True, make_exe=True):
    d = tmp_path / "RecruitHelper"
    if make_dir:
        d.mkdir(exist_ok=True)
        if make_exe:
            (d / "recruit-step.exe").write_bytes(b"")
    return {"dir": str(d), "exe": "recruit-step.exe"}


def _app(tkroot, tmp_path, monkeypatch, tools, steps):
    rec = _warnings(monkeypatch)
    a = _CalApp(tkroot, tmp_path, cal=CAL)
    a.flow_tools = tools
    a.steps = steps
    return a, rec


@pytest.mark.parametrize("make, want", [
    (None, "沒有登錄"),
    ({"make_dir": False}, "資料夾不存在"),
    ({"make_exe": False}, "入口檔不存在"),
], ids=["沒登錄", "資料夾不存在", "入口檔不存在"])
def test_外部工具缺東西_開始執行擋下並說缺什麼(tkroot, tmp_path, monkeypatch, make, want):
    tools = ToolRegistry({} if make is None else {"公開招募": _tool_dir(tmp_path, **make)})
    a, rec = _app(tkroot, tmp_path, monkeypatch, tools, [external("公開招募")])
    a.start_run()
    assert a.runner.started == []
    [msg] = rec
    assert "公開招募" in msg and want in msg, msg


def test_登錄檔格式錯_開始執行擋下(tkroot, tmp_path, monkeypatch):
    tools = ToolRegistry(problem="最外層要是 {工具名: {dir, exe}}")
    a, rec = _app(tkroot, tmp_path, monkeypatch, tools,
                  [external("公開招募"), external("其他工具")])
    a.start_run()
    assert a.runner.started == []
    [msg] = rec
    assert "格式錯" in msg and msg.count("格式錯") == 1, msg


def test_每個有問題的工具各列一行(tkroot, tmp_path, monkeypatch):
    tools = ToolRegistry({"公開招募": _tool_dir(tmp_path, make_exe=False)})
    a, rec = _app(tkroot, tmp_path, monkeypatch, tools,
                  [external("公開招募"), external("基建"), external("公開招募")])
    a.start_run()
    [msg] = rec
    assert msg.count("公開招募") == 1 and "入口檔不存在" in msg, msg
    assert "基建" in msg and "沒有登錄" in msg, msg


def test_登錄齊全_照常開始(tkroot, tmp_path, monkeypatch):
    tools = ToolRegistry({"公開招募": _tool_dir(tmp_path)})
    a, rec = _app(tkroot, tmp_path, monkeypatch, tools, [external("公開招募")])
    a.start_run()
    assert rec == [] and len(a.runner.started) == 1


def test_沒有外部步驟_沒有登錄檔也照常開始(tkroot, tmp_path, monkeypatch):
    a, rec = _app(tkroot, tmp_path, monkeypatch, ToolRegistry(), [wait(0.01)])
    a.start_run()
    assert rec == [] and len(a.runner.started) == 1


def test_沒有外部步驟_登錄檔格式錯也照常開始(tkroot, tmp_path, monkeypatch):
    a, rec = _app(tkroot, tmp_path, monkeypatch, ToolRegistry(problem="壞了"),
                  [wait(0.01)])
    a.start_run()
    assert rec == [] and len(a.runner.started) == 1


def test_測試選取_選到有問題的外部步驟擋下_沒選到不擋(tkroot, tmp_path, monkeypatch):
    a, rec = _app(tkroot, tmp_path, monkeypatch, ToolRegistry(),
                  [wait(0.01), external("公開招募")])
    a.start_run(steps=a.steps[1:2], test=True)
    assert a.runner.started == []
    assert any("公開招募" in m and "沒有登錄" in m for m in rec), rec
    rec.clear()
    a.start_run(steps=a.steps[0:1], test=True)
    assert rec == [] and len(a.runner.started) == 1
