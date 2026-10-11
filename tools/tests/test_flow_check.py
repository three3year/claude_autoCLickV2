"""檢查指令: 對 tmp_path 裡手寫的流程資料夾跑, 斷言結束碼、訊息與檔案狀態.

不載引擎、不開視窗; 只打命令列入口 (`flow_check.main` 與子程序) 與 `check`。
"""
import subprocess
import sys

import pytest

import flow_check
from vtf_synth import ROOT, snapshot

HEAD = """format: 1
calibration:
  pair: [圖示, 關閉]
  baseline: 400.0
"""


def make_flow(tmp_path, steps, head=HEAD, images=("圖示", "關閉", "開始", "確定"),
              name="流程"):
    folder = tmp_path / name
    (folder / "templates").mkdir(parents=True)
    for n in images:
        (folder / "templates" / f"{n}.png").write_bytes(b"png")
    (folder / "flow.yaml").write_text(head + "steps:\n" + steps, encoding="utf-8")
    return folder


def run(folder, *args, capsys):
    code = flow_check.main([str(folder), *args])
    return code, capsys.readouterr().out


OK = """  - {find_click: 開始}
  - {click: [10, 20]}
  - {find: 確定}
"""


def test_合法流程_結束碼0_一個檔都不寫(tmp_path, capsys):
    folder = make_flow(tmp_path, OK)
    before = snapshot(folder)
    code, out = run(folder, capsys=capsys)
    assert code == 0, out
    assert "沒有錯誤（3 步）" in out
    assert snapshot(folder) == before


@pytest.mark.parametrize("steps, head, want", [
    ("  - {find_click: 開始, colour: true}\n", HEAD, ["步驟 1", "colour"]),
    ("  - branch:\n      - if: {click: [1, 2]}\n", HEAD, ["步驟 2", "if 必須是找圖步驟"]),
    ("  - repeat: 2\n", HEAD, ["步驟 1", "steps"]),
    ("  - {click: [10, 20]}\n  - {find_click: 開始}\n", HEAD,
     ["步驟 1", "座標點擊以原點為基準", "沒有任何原點來源"]),
    ("  - {drag: [0, 0], to: [0, -100]}\n", HEAD, ["步驟 1", "滑鼠拖曳以原點為基準"]),
    ("  - {find_click: 開始, pick: {near: [0, 0]}}\n", HEAD,
     ["步驟 1", "指定點", "原點"]),
    ("  - {find_click: 開始, busy_check: true}\n", HEAD,
     ["步驟 1", "busy_check", "沒有設忙碌指示"]),
    ("  - {find_click: 開始}\n  - {click: [1, 2], confirm: gone}\n"
     "  - {click: [1, 2], confirm: gone}\n", HEAD, ["步驟 3", "原點的圖離開"]),
    ("  - {find_click: 開始, confirm: next}\n", HEAD, ["步驟 1", "找圖步驟"]),
    (OK, "format: 1\n", ["校準對"]),
    (OK, "format: 2\n", ["format"]),
], ids=["未知鍵", "分支開頭不是找圖", "區段不完整", "點擊前沒原點", "拖曳前沒原點",
        "指定點沒原點", "忙碌檢查沒忙碌指示", "原點的圖離開不是找圖", "下一步不相連",
        "沒有校準對", "格式版本"])
def test_每類錯誤_結束碼非零_訊息含步驟與原因(tmp_path, capsys, steps, head, want):
    folder = make_flow(tmp_path, steps, head=head)
    before = snapshot(folder)
    code, out = run(folder, capsys=capsys)
    assert code == 1, out
    assert out.startswith("錯誤")
    for w in want:
        assert w in out, out
    assert snapshot(folder) == before


def test_有忙碌指示時勾忙碌檢查沒問題(tmp_path, capsys):
    head = HEAD + "busy: {template: 開始}\n"
    folder = make_flow(tmp_path, "  - {find_click: 確定, busy_check: true}\n", head=head)
    assert run(folder, capsys=capsys)[0] == 0


def test_缺圖_列成要在app截的範本_結束碼0(tmp_path, capsys):
    folder = make_flow(tmp_path, OK + "  - {find_click: 新按鈕}\n")
    code, out = run(folder, capsys=capsys)
    assert code == 0, out
    assert "要在 app 截的範本" in out and "新按鈕" in out
    assert not out.startswith("錯誤")


def test_缺校準對的圖也列進缺圖(tmp_path, capsys):
    folder = make_flow(tmp_path, OK, images=("開始", "確定"))
    res = flow_check.check(folder)
    assert res.ok and res.missing == ["圖示", "關閉"]


def test_沒被引用的圖_列出但不動(tmp_path, capsys):
    folder = make_flow(tmp_path, OK, images=("圖示", "關閉", "開始", "確定", "舊圖"))
    code, out = run(folder, "--normalize", capsys=capsys)
    assert code == 0
    assert "舊圖" in out
    assert (folder / "templates" / "舊圖.png").is_file()


def test_normalize_把手改過編號過期的檔寫回標準排版(tmp_path, capsys):
    import flowfile
    steps = ("  - {find_click: 開始}    # 7\n"
             "  - {click: [10, 20], update_origin: true}\n"
             "  - repeat: 2    # 1\n    steps:\n      - {find: 確定, timeout: 10}\n")
    folder = make_flow(tmp_path, steps)
    code, out = run(folder, "--normalize", capsys=capsys)
    assert code == 0, out
    assert "已重寫 flow.yaml" in out
    text = (folder / "flow.yaml").read_text(encoding="utf-8")
    flow = flowfile.read_flow(folder)
    assert text == flowfile.dump_flow(flow)
    assert "- {find_click: 開始}    # 1" in text
    assert "- repeat: 2    # 3" in text
    assert "update_origin" not in text and "timeout" not in text, "等於預設的不寫"
    # 已是標準排版: 再跑一次不改檔
    before = snapshot(folder)
    code, out = run(folder, "--normalize", capsys=capsys)
    assert code == 0 and "已重寫" not in out
    assert snapshot(folder) == before


def test_normalize_有錯誤時不寫(tmp_path, capsys):
    folder = make_flow(tmp_path, "  - {click: [1, 2]}    # 9\n")
    before = snapshot(folder)
    code, _ = run(folder, "--normalize", capsys=capsys)
    assert code == 1
    assert snapshot(folder) == before


def test_讀不到資料夾_報錯(tmp_path, capsys):
    code, out = run(tmp_path / "沒有這個", capsys=capsys)
    assert code == 1 and "讀不到" in out


def test_命令列子程序(tmp_path):
    folder = make_flow(tmp_path, "  - {click: [1, 2]}\n")
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "flow_check"),
                           str(folder)], capture_output=True, timeout=120)
    out = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 1, proc.stderr.decode("utf-8", "replace")
    assert "步驟 1" in out
