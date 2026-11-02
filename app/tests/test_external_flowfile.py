import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flowfile  # noqa: E402

HEAD = "format: 1\nsteps:\n"


def steps_of(yaml_steps):
    return flowfile.parse_flow(HEAD + yaml_steps)["steps"]


def test_外部步驟往返_參數與備註原樣寫回():
    text = (HEAD
            + "  - {external: 公開招募, args: [--hwnd, '{hwnd}', --mode, 加急], note: 早班最後}    # 1\n")
    flow = flowfile.parse_flow(text)
    [s] = flow["steps"]
    assert s == {"type": "external", "external": "公開招募",
                 "args": ["--hwnd", "{hwnd}", "--mode", "加急"], "note": "早班最後"}
    assert flowfile.dump_flow(flow) == text


def test_外部步驟沒寫args等於空清單_等於預設的不寫出來():
    [s] = steps_of("  - {external: 公開招募}\n")
    assert s["args"] == [] and s["note"] == ""
    out = flowfile.dump_flow({**flowfile.new_flow(), "steps": [s]})
    assert "  - {external: 公開招募}    # 1\n" in out


def test_外部步驟可以放在重複區段裡():
    flow = flowfile.parse_flow(HEAD + "  - repeat: 2    # 1\n    steps:\n"
                               "      - {external: 公開招募}    # 2\n")
    assert [s["type"] for s in flow["steps"]] == ["repeat_start", "external", "repeat_end"]
    assert "      - {external: 公開招募}    # 2" in flowfile.dump_flow(flow)


@pytest.mark.parametrize("item, what", [
    ("{external: 公開招募, args: [--n, 3]}", "args"),
    ("{external: 公開招募, args: --hwnd}", "args"),
    ("{external: '', args: []}", "external"),
    ("{external: 公開招募, note: [a]}", "note"),
    ("{external: 公開招募, timeout: 3}", "timeout"),
])
def test_外部步驟寫錯讀不進來(item, what):
    with pytest.raises(flowfile.FlowError) as e:
        steps_of(f"  - {item}\n")
    assert what in str(e.value)


def test_外部步驟不能當分支開頭():
    with pytest.raises(flowfile.FlowError):
        steps_of("  - branch:\n      - if: {external: 公開招募}\n")


REGISTRY = "公開招募:\n  dir: {dir}\n  exe: recruit-step.exe\n"


def flow_folder(tmp_path, steps_yaml, registry=None):
    folder = tmp_path / "流程"
    folder.mkdir()
    (folder / flowfile.FLOW_YAML).write_text(HEAD + steps_yaml, encoding="utf-8")
    if registry is not None:
        (folder / flowfile.TOOLS_YAML).write_text(registry, encoding="utf-8")
    return folder


def tool_dir(tmp_path, exe="recruit-step.exe"):
    d = tmp_path / "RecruitHelper"
    d.mkdir()
    (d / exe).write_bytes(b"")
    return d


def test_讀流程時一起讀外部工具登錄_找得到入口檔與工作目錄(tmp_path):
    d = tool_dir(tmp_path)
    folder = flow_folder(tmp_path, "  - {external: 公開招募}\n",
                         REGISTRY.format(dir=d))
    tools = flowfile.read_flow(folder)["tools"]
    assert tools.names() == ["公開招募"]
    assert tools.locate("公開招募") == (str(d / "recruit-step.exe"), str(d))


@pytest.mark.parametrize("registry, reason", [
    (None, "沒有登錄"),
    ("別的工具:\n  dir: C:\\x\n  exe: a.exe\n", "沒有登錄"),
    ("公開招募:\n  dir: C:\\不存在的資料夾\n  exe: a.exe\n", "資料夾不存在"),
    ("公開招募: [壞的]\n", "格式錯"),
    ("公開招募: {dir: x}\n", "格式錯"),
    ("- 不是對照表\n", "格式錯"),
    ("公開招募: {dir: [\n", "格式錯"),
])
def test_登錄缺漏_讀流程照樣成功_找工具時說明原因(tmp_path, registry, reason):
    folder = flow_folder(tmp_path, "  - {external: 公開招募}\n", registry)
    tools = flowfile.read_flow(folder)["tools"]
    with pytest.raises(LookupError) as e:
        tools.locate("公開招募")
    assert reason in str(e.value)


def test_登錄了但入口檔不存在(tmp_path):
    d = tool_dir(tmp_path, exe="別的.exe")
    folder = flow_folder(tmp_path, "  - {external: 公開招募}\n", REGISTRY.format(dir=d))
    with pytest.raises(LookupError) as e:
        flowfile.read_flow(folder)["tools"].locate("公開招募")
    assert "入口檔不存在" in str(e.value) and "recruit-step.exe" in str(e.value)


def test_存檔不動登錄檔(tmp_path):
    d = tool_dir(tmp_path)
    text = "# 手寫註解\n" + REGISTRY.format(dir=d)
    folder = flow_folder(tmp_path, "  - {external: 公開招募, args: [a]}\n", text)
    flow = flowfile.read_flow(folder)
    store = flowfile.FlowTemplates.open(folder, tmp_path / "unsaved")
    store.save(flow)
    assert (folder / flowfile.TOOLS_YAML).read_text(encoding="utf-8") == text
    assert flowfile.read_flow(folder)["steps"] == flow["steps"]


def test_沒有外部步驟也沒有登錄檔_存檔不產生登錄檔(tmp_path):
    folder = tmp_path / "新流程"
    store = flowfile.FlowTemplates.new(tmp_path / "unsaved")
    store.save(flowfile.new_flow(), folder)
    assert not (folder / flowfile.TOOLS_YAML).exists()
    assert flowfile.read_flow(folder)["tools"].names() == []
