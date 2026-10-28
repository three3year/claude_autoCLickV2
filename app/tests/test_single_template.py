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
        grab_frame=lambda: ui_dialogs.capture.grab(None),
        root=_Root(),
        hub=vision,
        detector=vision,
        library=SimpleNamespace(templates={n: object() for n in names}),
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

    pos = ui_dialogs._find_template_now(
        app, (Screen((0, 0)), (0, 0)), {"type": "find_click", "target": {"template": "b"}})
    assert pos == (500, 400)
    assert vision.ensured == ["b"]
    assert vision.lookups == ["b"]


def test_即時找圖範本載入失敗_回None不炸(monkeypatch):
    vision = harness_mod.Vision()
    vision.state = "ready"
    vision.missing("b")
    app = _fake_app(vision)

    pos = ui_dialogs._find_template_now(
        app, (Screen((0, 0)), (0, 0)), {"type": "find_click", "target": {"template": "b"}})
    assert pos is None
    assert vision.lookups == []
