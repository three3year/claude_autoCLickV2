import os
import re

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = ("app.py", "ui_dialogs.py", "ui_overlay.py", "ui_theme.py")


def read(name):
    with open(os.path.join(APP_DIR, name), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("source", SOURCES)
def test_用到的色票鍵都存在(source):
    from ui_theme import C

    used = set(re.findall(r'C\["(\w+)"\]', read(source)))
    missing = sorted(k for k in used if k not in C)
    assert not missing, f"{source} 用到不存在的色票鍵: {missing}"


@pytest.mark.parametrize("source", SOURCES)
def test_用到的_ttk_樣式都有定義(source):
    """style=... 指定的樣式名稱必須在 ui_theme 裡設定過, 否則會靜默變成預設樣式."""
    theme = read("ui_theme.py")
    used = set(re.findall(r'style="([\w.]+\.T\w+)"', read(source)))
    missing = sorted(s for s in used if f'"{s}"' not in theme)
    assert not missing, f"{source} 用到未定義的樣式: {missing}"
