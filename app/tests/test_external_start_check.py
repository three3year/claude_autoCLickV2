"""開始執行／測試選取前檢查外部工具: 缺什麼就擋下並列出 (Tk, 隱藏桌面跑)."""
from types import SimpleNamespace

import pytest
from harness import external, wait

import flowfile
from test_calibration_ui import _CalApp, _warnings

CAL = {"pair": ["p", "q"], "baseline": 100.0}
BAD_YAML = "- 不是對照表\n"


def _tool_dir(tmp_path, make_dir=True, make_exe=True):
    d = tmp_path / "RecruitHelper"
    if make_dir:
        d.mkdir(exist_ok=True)
        if make_exe:
            (d / "recruit-step.exe").write_bytes(b"")
    return d


def _entry(d):
    return f"公開招募:\n  dir: {d}\n  exe: recruit-step.exe\n"


def _app(tkroot, tmp_path, monkeypatch, registry, steps):
    """registry: 流程資料夾 external_tools.yaml 的內容 (None＝沒有這個檔)."""
    rec = _warnings(monkeypatch)
    a = _CalApp(tkroot, tmp_path, cal=CAL)
    folder = tmp_path / "流程"
    folder.mkdir()
    if registry is not None:
        (folder / flowfile.TOOLS_YAML).write_text(registry, encoding="utf-8")
    a.store = SimpleNamespace(folder=str(folder))
    a.steps = steps
    return a, rec


@pytest.mark.parametrize("make, want", [
    (None, "沒有登錄"),
    ({"make_dir": False}, "資料夾不存在"),
    ({"make_exe": False}, "入口檔不存在"),
], ids=["沒登錄", "資料夾不存在", "入口檔不存在"])
def test_外部工具缺東西_開始執行擋下並說缺什麼(tkroot, tmp_path, monkeypatch, make, want):
    registry = None if make is None else _entry(_tool_dir(tmp_path, **make))
    a, rec = _app(tkroot, tmp_path, monkeypatch, registry, [external("公開招募")])
    a.start_run()
    assert a.runner.started == []
    [msg] = rec
    assert "公開招募" in msg and want in msg, msg


def test_登錄檔格式錯_開始執行擋下(tkroot, tmp_path, monkeypatch):
    a, rec = _app(tkroot, tmp_path, monkeypatch, BAD_YAML,
                  [external("公開招募"), external("其他工具")])
    a.start_run()
    assert a.runner.started == []
    [msg] = rec
    assert "格式錯" in msg and msg.count("格式錯") == 1, msg


def test_每個有問題的工具各列一行(tkroot, tmp_path, monkeypatch):
    registry = _entry(_tool_dir(tmp_path, make_exe=False))
    a, rec = _app(tkroot, tmp_path, monkeypatch, registry,
                  [external("公開招募"), external("基建"), external("公開招募")])
    a.start_run()
    [msg] = rec
    assert msg.count("公開招募") == 1 and "入口檔不存在" in msg, msg
    assert "基建" in msg and "沒有登錄" in msg, msg


def test_登錄齊全_照常開始(tkroot, tmp_path, monkeypatch):
    a, rec = _app(tkroot, tmp_path, monkeypatch, _entry(_tool_dir(tmp_path)),
                  [external("公開招募")])
    a.start_run()
    assert rec == [] and len(a.runner.started) == 1


def test_沒有外部步驟_沒有登錄檔也照常開始(tkroot, tmp_path, monkeypatch):
    a, rec = _app(tkroot, tmp_path, monkeypatch, None, [wait(0.01)])
    a.start_run()
    assert rec == [] and len(a.runner.started) == 1


def test_沒有外部步驟_登錄檔格式錯也照常開始(tkroot, tmp_path, monkeypatch):
    a, rec = _app(tkroot, tmp_path, monkeypatch, BAD_YAML, [wait(0.01)])
    a.start_run()
    assert rec == [] and len(a.runner.started) == 1


def test_測試選取_選到有問題的外部步驟擋下_沒選到不擋(tkroot, tmp_path, monkeypatch):
    a, rec = _app(tkroot, tmp_path, monkeypatch, None,
                  [wait(0.01), external("公開招募")])
    a.start_run(steps=a.steps[1:2], test=True)
    assert a.runner.started == []
    assert any("公開招募" in m and "沒有登錄" in m for m in rec), rec
    rec.clear()
    a.start_run(steps=a.steps[0:1], test=True)
    assert rec == [] and len(a.runner.started) == 1


def test_測試選取_開著時補寫登錄_下一次就照新登錄(tkroot, tmp_path, monkeypatch):
    a, rec = _app(tkroot, tmp_path, monkeypatch, None, [external("公開招募")])
    a.start_run(steps=a.steps, test=True)
    assert a.runner.started == [] and rec
    (tmp_path / "流程" / flowfile.TOOLS_YAML).write_text(
        _entry(_tool_dir(tmp_path)), encoding="utf-8")
    rec.clear()
    a.start_run(steps=a.steps, test=True)
    assert rec == [] and len(a.runner.started) == 1
