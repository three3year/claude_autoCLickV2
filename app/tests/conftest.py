import pytest

from harness import Harness


@pytest.fixture
def harness(monkeypatch):
    return Harness(monkeypatch)
