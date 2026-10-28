import importlib
import os
import sys

import harness


def _fresh():
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


def test_原始碼執行_流程存放區在repo的flows(monkeypatch):
    ap = _fresh()
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert ap.flows_root() == os.path.join(ap.REPO_ROOT, "flows")


def test_打包版_exe在專案底下_流程存放區在那個專案的flows(monkeypatch, tmp_path):
    ap = _fresh()
    repo = tmp_path / "專案"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "apppaths.py").write_text("", encoding="utf-8")
    exe_dir = repo / "app" / "dist" / "AutoClick"
    exe_dir.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "AutoClick.exe"))
    assert ap.flows_root() == os.path.join(str(repo), "flows")


def test_打包版_往上找不到專案_流程存放區在使用者資料夾的AutoClick(monkeypatch, tmp_path):
    ap = _fresh()
    exe_dir = tmp_path / "隨身碟" / "AutoClick"
    exe_dir.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "AutoClick.exe"))
    home = tmp_path / "home"
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    assert ap.flows_root() == os.path.join(str(home), "AutoClick")


def test_本機狀態寫了讀得回來_沒有或壞了回空(local_paths):
    import apppaths
    assert apppaths.load_state() == {}
    apppaths.save_state({"last_flow": "C:/x/早班"})
    assert apppaths.load_state() == {"last_flow": "C:/x/早班"}
    with open(os.path.join(apppaths.state_dir(), "state.json"), "w") as f:
        f.write("{壞")
    assert apppaths.load_state() == {}
