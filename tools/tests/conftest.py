"""影片轉流程工具的測試夾具 (合成輸入在 vtf_synth.py)."""
import pytest

import vtf_synth  # noqa: F401  # 把 tools/、app/、src/ 加進 sys.path


@pytest.fixture(autouse=True)
def _no_real_flows_root(monkeypatch, tmp_path):
    """計畫沒寫 out 的組裝會建在流程存放區: 換成暫存目錄, 不碰使用者真的 flows/."""
    import apppaths
    monkeypatch.setattr(apppaths, "flows_root", lambda: str(tmp_path / "flows"))


@pytest.fixture(scope="session")
def engine():
    """真引擎 (含深度驗證模型), 整個 session 共用一個——建構要載模型."""
    from subject_detection import Engine
    return Engine()
