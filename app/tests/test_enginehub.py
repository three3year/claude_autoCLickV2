"""引擎生命週期介面 (startup-speed 票 01): 狀態、委派、預載/單張載入.

假引擎經 engine_factory 注入——不碰 torch、不開執行緒, 測試直接把狀態
撥成任意值。介面形狀＝runner 偵測接縫 (query) 的超集, 與 harness 假件一致。
"""
import warnings

import pytest

import harness  # noqa: F401  # 先把 app/ 加進 sys.path

import enginehub


class FakeProfile:
    def __init__(self, names=("a", "b")):
        self.templates = {n: object() for n in names}


class FakeEngine:
    def __init__(self, coarse_only=False):
        self.coarse_only = coarse_only
        self.registered = []
        self.queries = []
        self.expected_scales = []

    def register(self, profile, name):
        self.registered.append(name)

    def query(self, profile, name, search_region, color_check=False,
              expected_scale=None):
        self.queries.append((profile, name, search_region, color_check))
        self.expected_scales.append(expected_scale)
        return "RESULT"


def _ready_hub(tmp_path, engine=None):
    engine = engine or FakeEngine()
    hub = enginehub.EngineHub(engine_factory=lambda: engine)
    hub.load()
    assert hub.ready
    return hub, engine


def test_初始為載入中_load後就緒(tmp_path):
    engine = FakeEngine()
    hub = enginehub.EngineHub(engine_factory=lambda: engine)
    assert hub.state == enginehub.LOADING
    assert not hub.ready
    hub.load()
    assert hub.state == enginehub.READY
    assert hub.ready


def test_引擎建構失敗_狀態failed且保留錯誤(tmp_path):
    boom = RuntimeError("no torch")
    def factory():
        raise boom
    hub = enginehub.EngineHub(engine_factory=factory)
    hub.load()
    assert hub.state == enginehub.FAILED
    assert not hub.ready
    assert hub.error is boom


def test_query委派引擎與當前範本清單(tmp_path):
    hub, engine = _ready_hub(tmp_path)
    p = FakeProfile()
    hub.library = p
    r = hub.query("a", "SCREEN")
    assert r == "RESULT"
    hub.query("a", "SCREEN", color_check=True)
    assert engine.queries == [(p, "a", "SCREEN", False),
                              (p, "a", "SCREEN", True)]


def test_query把預期尺度交給引擎_沒給就是None(tmp_path):
    hub, engine = _ready_hub(tmp_path)
    hub.library = FakeProfile()
    hub.query("a", "SCREEN")
    hub.query("a", "SCREEN", expected_scale=0.9)
    assert engine.expected_scales == [None, 0.9]


def test_preload逐一登錄(tmp_path):
    hub, engine = _ready_hub(tmp_path)
    hub.library = FakeProfile()
    hub.preload(["a", "b"])
    assert engine.registered == ["a", "b"]


def test_preload未知範本丟KeyError(tmp_path):
    hub, engine = _ready_hub(tmp_path)
    hub.library = FakeProfile()
    with pytest.raises(KeyError):
        hub.preload(["a", "nope"])
    assert engine.registered == ["a"]  # 錯在哪張就停在哪張


def test_ensure_template單張登錄(tmp_path):
    hub, engine = _ready_hub(tmp_path)
    hub.library = FakeProfile()
    hub.ensure_template("b")
    assert engine.registered == ["b"]


def test_coarse_only跟隨引擎(tmp_path):
    hub, _ = _ready_hub(tmp_path, FakeEngine(coarse_only=True))
    assert hub.coarse_only
    hub2 = enginehub.EngineHub(engine_factory=FakeEngine)
    assert not hub2.coarse_only  # 尚未載入 = 尚未降級


def test_gating決策矩陣():
    assert enginehub.gating_message(enginehub.READY) is None
    assert "載入中" in enginehub.gating_message(enginehub.LOADING)
    assert "失敗" in enginehub.gating_message(enginehub.FAILED)


def test_load只建引擎_不碰範本清單也不整庫登錄(tmp_path):
    engine = FakeEngine()
    hub = enginehub.EngineHub(engine_factory=lambda: engine)
    lib = hub.bind({"a": str(tmp_path / "a.png")}, {"k": 1}, tmp_path / "reg")
    hub.load()
    assert hub.state == enginehub.READY
    assert hub.library is lib, "背景載入不覆蓋 app 已綁好的範本清單"
    # 不整庫登錄: 登錄產物由`範本預載`/單張載入在使用當下載入 (ADR 0004)
    assert engine.registered == []


def test_bind不需引擎_範本清單由app給(tmp_path):
    def never():
        raise AssertionError("bind 不應建構引擎")
    hub = enginehub.EngineHub(engine_factory=never)
    lib = hub.bind({"按鈕": str(tmp_path / "按鈕.png")}, {"scale_range": [0.6, 1.5]},
                   tmp_path / "reg")
    assert hub.library is lib
    assert list(lib.templates) == ["按鈕"]
    assert lib.templates["按鈕"].capture_paths == [tmp_path / "按鈕.png"]
    assert lib.config == {"scale_range": [0.6, 1.5]}
    assert lib.artifacts_dir == tmp_path / "reg"
    assert hub.state == enginehub.LOADING   # 不觸碰生命週期狀態


def _bound_with_artifacts(tmp_path, cfg):
    hub = enginehub.EngineHub(engine_factory=FakeEngine)
    hub.bind({n: str(tmp_path / f"{n}.png") for n in "abc"}, cfg, tmp_path / "reg")
    for n, t in hub.library.templates.items():
        t.artifacts = "ART-" + n
    return hub


def test_bind只換有變的範本_其他沿用記憶體裡的登錄產物(tmp_path):
    hub = _bound_with_artifacts(tmp_path, {"k": 1})
    moved = {n: str(tmp_path / "templates" / f"{n}.png") for n in "abd"}
    lib = hub.bind(moved, {"k": 1}, tmp_path / "reg", changed={"b"})
    arts = {n: t.artifacts for n, t in lib.templates.items()}
    assert arts == {"a": "ART-a", "b": None, "d": None},         "圖只是搬位置的照用; 有變的與新的要重新登錄"


def test_bind整份換掉或引擎參數變了_登錄產物全部失效(tmp_path):
    hub = _bound_with_artifacts(tmp_path, {"k": 1})
    imgs = {n: str(tmp_path / f"{n}.png") for n in "abc"}
    lib = hub.bind(imgs, {"k": 1}, tmp_path / "reg")
    assert all(t.artifacts is None for t in lib.templates.values())
    hub = _bound_with_artifacts(tmp_path, {"k": 1})
    lib = hub.bind(imgs, {"k": 2}, tmp_path / "reg", changed=set())
    assert all(t.artifacts is None for t in lib.templates.values())


def test_load寫入引擎載入起訖日誌(tmp_path, monkeypatch):
    import applog
    log = tmp_path / "log.log"
    monkeypatch.setattr(applog, "_path", str(log))
    hub = enginehub.EngineHub(engine_factory=FakeEngine)
    hub.load()
    text = log.read_text(encoding="utf-8")
    assert "engine.load.start" in text
    assert "engine.load.done" in text
    assert "secs=" in text


def test_load失敗也寫日誌(tmp_path, monkeypatch):
    import applog
    log = tmp_path / "log.log"
    monkeypatch.setattr(applog, "_path", str(log))

    def factory():
        raise RuntimeError("no torch")
    hub = enginehub.EngineHub(engine_factory=factory)
    hub.load()
    text = log.read_text(encoding="utf-8")
    assert "engine.load.failed" in text


def test_引擎警告只留subject_detection來源(tmp_path):
    def factory():
        warnings.warn("outside noise")  # filename 是本測試檔 → 應被濾掉
        return FakeEngine()
    hub = enginehub.EngineHub(engine_factory=factory)
    hub.load()
    assert hub.state == enginehub.READY
    assert hub.warnings == []
