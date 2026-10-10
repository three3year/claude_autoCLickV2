"""本機狀態資料夾與日誌位置 (flow-folder-format 10): 打包版與原始碼執行各自正確."""
import importlib
import os
import sys

import harness  # noqa: F401  # 先把 app/ 加進 sys.path


def _fresh():
    """conftest 把 state_dir 換成暫存目錄; 這裡要測真的函式 → 重新載入一份."""
    import apppaths
    return importlib.reload(apppaths)


def test_原始碼執行_狀態與日誌在repo的local(monkeypatch):
    ap = _fresh()
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert ap.state_dir() == os.path.join(ap.REPO_ROOT, ".local")
    assert ap.log_path() == os.path.join(ap.REPO_ROOT, ".local", "autoclick.log")
    assert ap.unsaved_dir() == os.path.join(ap.REPO_ROOT, ".local", "unsaved")


def test_打包版_狀態與日誌在LOCALAPPDATA(monkeypatch, tmp_path):
    ap = _fresh()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert ap.state_dir() == os.path.join(str(tmp_path), "AutoClick")
    assert ap.log_path() == os.path.join(str(tmp_path), "AutoClick", "autoclick.log")


def test_流程預設位置在使用者資料夾的AutoClick(monkeypatch, tmp_path):
    ap = _fresh()
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    assert ap.flows_root() == os.path.join(str(tmp_path), "AutoClick")


def test_本機狀態寫了讀得回來_沒有或壞了回空(local_paths):
    import apppaths
    assert apppaths.load_state() == {}
    apppaths.save_state({"last_flow": "C:/x/早班"})
    assert apppaths.load_state() == {"last_flow": "C:/x/早班"}
    with open(os.path.join(apppaths.state_dir(), "state.json"), "w") as f:
        f.write("{壞")
    assert apppaths.load_state() == {}
