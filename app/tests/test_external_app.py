"""app 開含外部步驟的流程: 讀進登錄、執行時交給執行器、步驟清單看得到 (Tk, 隱藏桌面跑)."""
import enginehub
import flowfile
from automation import imgio
from automation.flowcheck import STEP_LABELS

import numpy as np


def _png():
    return imgio.encode_png(np.full((20, 40, 3), 100, np.uint8))


def _flow_folder(tmp_path):
    d = tmp_path / "RecruitHelper"
    d.mkdir()
    (d / "recruit-step.exe").write_bytes(b"")
    folder = tmp_path / "流程"
    flow = flowfile.new_flow()
    flow["calibration"] = {"pair": ["p", "q"], "baseline": 100.0}
    flow["steps"] = flowfile.parse_steps([{"external": "公開招募",
                                           "args": ["--hwnd", "{hwnd}"]}])
    flowfile.write_flow(folder, flow, {"p": _png(), "q": _png()})
    (folder / flowfile.TOOLS_YAML).write_text(
        f"公開招募:\n  dir: {d}\n  exe: recruit-step.exe\n", encoding="utf-8")
    return folder, d


def test_開流程讀進登錄_執行時交給執行器(main_app, tmp_path, monkeypatch):
    a = main_app
    folder, d = _flow_folder(tmp_path)
    assert a.open_flow_folder(str(folder))
    started = []
    monkeypatch.setattr(a.runner, "start", lambda steps, *x, **kw: started.append(kw))
    monkeypatch.setattr(a, "ensure_registered", lambda: None)
    monkeypatch.setattr(a, "_show_mini", lambda: None)
    a.hub.state = enginehub.READY
    a.start_run()
    [kw] = started
    assert kw["tools"].locate("公開招募") == (str(d / "recruit-step.exe"), str(d))


def test_新流程沒有登錄(main_app, tmp_path):
    a = main_app
    folder, _ = _flow_folder(tmp_path)
    assert a.open_flow_folder(str(folder))
    a.new_flow()
    assert a.flow_tools.names() == []


def test_步驟清單顯示外部步驟與參數(main_app, tmp_path):
    a = main_app
    folder, _ = _flow_folder(tmp_path)
    assert a.open_flow_folder(str(folder))
    row = a.step_list.get("1.0", "end").splitlines()[0]
    assert STEP_LABELS["external"] in row
    assert "外部 公開招募 --hwnd {hwnd}" in row
