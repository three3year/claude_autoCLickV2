"""Engine test fixtures. Shared synthetic template-folder helpers live in synth.py
(unique module name — app/tests/ has its own conftest.py)."""
import pytest


@pytest.fixture(scope="session")
def engine():
    from subject_detection import Engine
    return Engine()
