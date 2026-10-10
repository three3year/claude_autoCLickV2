"""tools/ 底下工具的測試夾具 (合成輸入: 影片轉流程在 vtf_synth.py、公開招募在 rt_synth.py)."""
import pytest

import vtf_synth  # noqa: F401  # 把 tools/、app/、src/ 加進 sys.path


@pytest.fixture(scope="session")
def engine():
    """真引擎 (含深度驗證模型), 整個 session 共用一個——建構要載模型."""
    from subject_detection import Engine
    return Engine()
