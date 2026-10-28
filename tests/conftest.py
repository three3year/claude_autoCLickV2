import pytest


@pytest.fixture(scope="session")
def engine():
    from subject_detection import Engine
    return Engine()
