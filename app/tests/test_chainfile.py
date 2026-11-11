import os

import pytest

import flowfile


def _write(root, name, text):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, name + flowfile.CHAIN_SUFFIX), "w", encoding="utf-8") as f:
        f.write(text)


def _text(root, name):
    with open(os.path.join(root, name + flowfile.CHAIN_SUFFIX), encoding="utf-8") as f:
        return f.read()


def test_讀寫來回不變_沒寫輪數等於1_存檔不寫出(tmp_path):
    items = [{"flow": "早_繁中", "run": 1}, {"flow": "早_簡中", "run": 2},
             {"flow": "早_繁中", "run": 1}]
    flowfile.write_chain(tmp_path, "早班", items)
    assert _text(tmp_path, "早班") == ("format: 1\n"
                                       "flows:\n"
                                       "  - {flow: 早_繁中}\n"
                                       "  - {flow: 早_簡中, run: 2}\n"
                                       "  - {flow: 早_繁中}\n")
    assert flowfile.read_chain(tmp_path, "早班") == items


def test_手寫沒寫輪數_讀進來是1(tmp_path):
    _write(tmp_path, "晚班", "format: 1\nflows:\n  - flow: 晚_繁中\n  - {flow: 晚_簡中, run: 3}\n")
    assert flowfile.read_chain(tmp_path, "晚班") == [{"flow": "晚_繁中", "run": 1},
                                                    {"flow": "晚_簡中", "run": 3}]


def test_空串接寫成空清單(tmp_path):
    flowfile.write_chain(tmp_path, "空", [])
    assert _text(tmp_path, "空") == "format: 1\nflows: []\n"
    assert flowfile.read_chain(tmp_path, "空") == []


@pytest.mark.parametrize("text, what", [
    ("format: 1\nflows:\n  - {flow: 早_繁中, run: forever}\n", "run"),
    ("format: 1\nflows:\n  - {flow: 早_繁中, run: 0}\n", "run"),
    ("format: 1\nflows:\n  - {flow: 早_繁中, run: -2}\n", "run"),
    ("format: 1\nflows:\n  - {flow: 早_繁中, run: 1.5}\n", "run"),
    ("format: 1\nflows:\n  - {flow: 早_繁中, run: true}\n", "run"),
    ("format: 1\nflows:\n  - {flow: 早_繁中, delay: 3}\n", "delay"),
    ("format: 1\nname: 早班\nflows: []\n", "name"),
    ("format: 1\nflows:\n  - {run: 2}\n", "缺 flow"),
    ("format: 1\nflows:\n  - 早_繁中\n", "第 1 項"),
    ("flows: []\n", "format"),
    ("format: 1\nflows:\n  - {flow: 早_繁中}\n  - {flow: ../別處}\n", "第 2 項"),
])
def test_讀檔擋下(tmp_path, text, what):
    _write(tmp_path, "壞", text)
    with pytest.raises(flowfile.FlowError, match=what):
        flowfile.read_chain(tmp_path, "壞")


def _flow_folder(root, name):
    flowfile.write_flow(os.path.join(str(root), name), flowfile.new_flow())


def test_列出串接檔_依名稱排序_不含流程資料夾與其他檔(tmp_path):
    _flow_folder(tmp_path, "早_繁中")
    flowfile.write_chain(tmp_path, "晚班", [])
    flowfile.write_chain(tmp_path, "早班", [{"flow": "早_繁中", "run": 1}])
    (tmp_path / "筆記.yaml").write_text("x: 1\n", encoding="utf-8")
    assert flowfile.list_chains(tmp_path) == ["早班", "晚班"]


def test_流程存放區不存在_沒有串接檔(tmp_path):
    assert flowfile.list_chains(tmp_path / "沒有") == []


def test_串接檔不在可加入的流程清單裡(tmp_path):
    _flow_folder(tmp_path, "早_繁中")
    flowfile.write_chain(tmp_path, "早班", [{"flow": "早_繁中", "run": 1}])
    assert [os.path.basename(p) for p in flowfile.list_flow_folders(str(tmp_path))] == ["早_繁中"]


def test_新增串接檔_是空的串接(tmp_path):
    flowfile.create_chain(tmp_path, "早班")
    assert flowfile.list_chains(tmp_path) == ["早班"]
    assert flowfile.read_chain(tmp_path, "早班") == []


@pytest.mark.parametrize("name, what", [
    ("早/班", "不能有 /"), ("", "不能是空的"), (" 早班", "空白"), ("早班.", "句點"),
    ("早班", "已經有"), ("EARLY", "已經有"),
])
def test_新增擋下不能當檔名或同名的名稱(tmp_path, name, what):
    flowfile.create_chain(tmp_path, "早班")
    flowfile.create_chain(tmp_path, "early")
    with pytest.raises(flowfile.FlowError, match=what):
        flowfile.create_chain(tmp_path, name)
    assert flowfile.list_chains(tmp_path) == ["early", "早班"]


def test_改名_內容跟著走(tmp_path):
    items = [{"flow": "早_繁中", "run": 2}]
    flowfile.write_chain(tmp_path, "早班", items)
    flowfile.rename_chain(tmp_path, "早班", "白天")
    assert flowfile.list_chains(tmp_path) == ["白天"]
    assert flowfile.read_chain(tmp_path, "白天") == items


def test_改名只改大小寫可以(tmp_path):
    flowfile.create_chain(tmp_path, "early")
    flowfile.rename_chain(tmp_path, "early", "Early")
    assert flowfile.list_chains(tmp_path) == ["Early"]


@pytest.mark.parametrize("name, what", [("晚班", "已經有"), ("早:班", "不能有 :")])
def test_改名擋下同名或不能當檔名(tmp_path, name, what):
    flowfile.create_chain(tmp_path, "早班")
    flowfile.create_chain(tmp_path, "晚班")
    with pytest.raises(flowfile.FlowError, match=what):
        flowfile.rename_chain(tmp_path, "早班", name)
    assert flowfile.list_chains(tmp_path) == ["早班", "晚班"]


def test_刪除串接檔_流程不受影響(tmp_path):
    _flow_folder(tmp_path, "早_繁中")
    flowfile.write_chain(tmp_path, "早班", [{"flow": "早_繁中", "run": 1}])
    flowfile.delete_chain(tmp_path, "早班")
    assert flowfile.list_chains(tmp_path) == []
    assert os.path.isfile(tmp_path / "早_繁中" / flowfile.FLOW_YAML)
