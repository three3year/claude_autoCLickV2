"""單範本隨用載入 (startup-speed 票 05): 即時找圖/比對測試只載當下那張.

以 harness 的 Vision 假件當 hub/偵測器, 螢幕擷取與清場以樁替換——
斷言「只有目標範本被單張載入, 沒有整庫登錄」。
"""
import contextlib
from types import SimpleNamespace

import harness as harness_mod
from harness import Screen

import ui_dialogs


class _Root:
    def update(self):
        pass


def _fake_app(vision, names=("a", "b", "c")):
    return SimpleNamespace(
        root=_Root(),
        hub=vision,
        detector=vision,
        profile=SimpleNamespace(templates={n: object() for n in names}),
        scan_region=None,
        ensure_registered=lambda: None,
    )


def test_即時找圖只單張載入目標範本(monkeypatch):
    vision = harness_mod.Vision(default=(500, 400))
    vision.state = "ready"
    app = _fake_app(vision)
    monkeypatch.setattr(ui_dialogs.ui_overlay, "screen_clear",
                        lambda root, extra=(): contextlib.nullcontext())
    monkeypatch.setattr(ui_dialogs.capture, "grab",
                        lambda region=None: (Screen((0, 0)), (0, 0)))
    monkeypatch.setattr(ui_dialogs.time, "sleep", lambda s: None)

    pos = ui_dialogs._find_template_now(app, None, {"template": "b"})
    assert pos == (500, 400)
    assert vision.ensured == ["b"]      # 只載當下那張
    assert vision.lookups == ["b"]


def test_即時找圖範本載入失敗_回None不炸(monkeypatch):
    vision = harness_mod.Vision()
    vision.state = "ready"
    vision.missing("b")
    app = _fake_app(vision)

    pos = ui_dialogs._find_template_now(app, None, {"template": "b"})
    assert pos is None
    assert vision.lookups == []  # 載入失敗就不查詢
