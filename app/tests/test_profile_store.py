"""profile 目錄結構: 列舉/建立/應用狀態 (暫存目錄真測, 不 mock)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import profile_store  # noqa: E402


def test_建立profile會帶入目錄結構與預設config(tmp_path):
    dest = profile_store.create_profile(str(tmp_path), "mygame")
    assert os.path.isdir(os.path.join(dest, "templates"))
    assert os.path.isdir(os.path.join(dest, "flows"))
    with open(os.path.join(dest, "config.yaml"), encoding="utf-8") as f:
        cfg = f.read()
    with open(profile_store.default_config_path(), encoding="utf-8") as f:
        assert cfg == f.read(), "新 profile 的 config 應是引擎預設 config 的完整複本"


def test_列舉只算有templates目錄的資料夾(tmp_path):
    profile_store.create_profile(str(tmp_path), "a")
    profile_store.create_profile(str(tmp_path), "b")
    os.makedirs(tmp_path / "junk")  # 沒有 templates/ → 不是 profile
    (tmp_path / "app_state.json").write_text("{}", encoding="utf-8")
    assert profile_store.list_profiles(str(tmp_path)) == ["a", "b"]


def test_profiles目錄不存在時列舉回空(tmp_path):
    assert profile_store.list_profiles(str(tmp_path / "nope")) == []


@pytest.mark.parametrize("bad", ["", "  ", "a/b", "a\\b", "..", "x:y", "a?b"])
def test_非法profile名稱擋下(tmp_path, bad):
    with pytest.raises(ValueError):
        profile_store.create_profile(str(tmp_path), bad)


def test_已存在的profile名稱擋下(tmp_path):
    profile_store.create_profile(str(tmp_path), "a")
    with pytest.raises(ValueError):
        profile_store.create_profile(str(tmp_path), "a")


def test_應用狀態存讀(tmp_path):
    assert profile_store.load_state(str(tmp_path)) == {}
    profile_store.save_state(str(tmp_path), {"profile": "a"})
    assert profile_store.load_state(str(tmp_path)) == {"profile": "a"}


def test_資料根目錄_原始碼執行是repo根目錄(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    root = profile_store.data_root()
    assert os.path.isdir(os.path.join(root, "app")), "repo 根目錄應含 app/"
    assert os.path.isdir(os.path.join(root, "src")), "repo 根目錄應含 src/"


def test_資料根目錄_frozen是exe旁(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable",
                        r"C:\somewhere\AutoClick\AutoClick.exe")
    assert profile_store.data_root() == r"C:\somewhere\AutoClick"
