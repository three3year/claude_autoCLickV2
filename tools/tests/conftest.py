import pytest

import vtf_synth  # noqa: F401


@pytest.fixture(autouse=True)
def _no_real_flows_root(monkeypatch, tmp_path):
    import apppaths
    monkeypatch.setattr(apppaths, "flows_root", lambda: str(tmp_path / "flows"))


@pytest.fixture(scope="session")
def engine():
    from subject_detection import Engine
    return Engine()
