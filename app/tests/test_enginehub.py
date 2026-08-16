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
        self.loaded = None

    def load_profile(self, profile_dir, register=True):
        self.loaded = (str(profile_dir), register)
        return FakeProfile()

    def register(self, profile, name):
        self.registered.append(name)

    def query(self, profile, name, search_region):
        self.queries.append((profile, name, search_region))
        return "RESULT"


def _ready_hub(engine=None):
    engine = engine or FakeEngine()
    hub = enginehub.EngineHub(engine_factory=lambda: engine)
    hub.load_engine()
    return hub, engine


def test_初始為載入中_load_engine後就緒():
    engine = FakeEngine()
    hub = enginehub.EngineHub(engine_factory=lambda: engine)
    assert hub.state == enginehub.LOADING
    assert not hub.ready
    hub.load_engine()
    assert hub.state == enginehub.READY
    assert hub.ready


def test_引擎建構失敗_狀態failed且保留錯誤():
    boom = RuntimeError("no torch")
    def factory():
        raise boom
    hub = enginehub.EngineHub(engine_factory=factory)
    hub.load_engine()
    assert hub.state == enginehub.FAILED
    assert not hub.ready
    assert hub.error is boom


def test_query委派引擎與當前profile():
    hub, engine = _ready_hub()
    p = FakeProfile()
    hub.profile = p
    r = hub.query("a", "SCREEN")
    assert r == "RESULT"
    assert engine.queries == [(p, "a", "SCREEN")]


def test_preload逐一登錄():
    hub, engine = _ready_hub()
    hub.profile = FakeProfile()
    hub.preload(["a", "b"])
    assert engine.registered == ["a", "b"]


def test_preload未知範本丟KeyError():
    hub, engine = _ready_hub()
    hub.profile = FakeProfile()
    with pytest.raises(KeyError):
        hub.preload(["a", "nope"])
    assert engine.registered == ["a"]  # 錯在哪張就停在哪張


def test_ensure_template單張登錄():
    hub, engine = _ready_hub()
    hub.profile = FakeProfile()
    hub.ensure_template("b")
    assert engine.registered == ["b"]


def test_coarse_only跟隨引擎():
    hub, _ = _ready_hub(FakeEngine(coarse_only=True))
    assert hub.coarse_only
    hub2 = enginehub.EngineHub(engine_factory=FakeEngine)
    assert not hub2.coarse_only  # 尚未載入 = 尚未降級


def test_gating決策矩陣():
    assert enginehub.gating_message(enginehub.READY) is None
    assert "載入中" in enginehub.gating_message(enginehub.LOADING)
    assert "失敗" in enginehub.gating_message(enginehub.FAILED)


def _make_profile_dir(tmp_path):
    (tmp_path / "templates" / "zh" / "X").mkdir(parents=True)
    (tmp_path / "templates" / "zh" / "X" / "X.png").write_bytes(b"png")
    return tmp_path


def test_load一氣呵成_引擎加探索全成功才就緒(tmp_path):
    engine = FakeEngine()
    hub = enginehub.EngineHub(engine_factory=lambda: engine)
    hub.load(_make_profile_dir(tmp_path))
    assert hub.state == enginehub.READY
    assert "zh/X" in hub.profile.templates
    # 不整庫登錄: 登錄產物由`範本預載`/單張載入在使用當下載入 (ADR 0004)
    assert engine.loaded is None
    assert engine.registered == []


def test_load時profile探索失敗_整體視為failed(tmp_path):
    hub = enginehub.EngineHub(engine_factory=FakeEngine)
    hub.load(tmp_path / "not-a-profile")  # 沒有 templates/ 目錄
    assert hub.state == enginehub.FAILED
    assert isinstance(hub.error, FileNotFoundError)


def test_refresh重新探索並綁定profile(tmp_path):
    hub = enginehub.EngineHub(engine_factory=FakeEngine)
    p = hub.refresh(_make_profile_dir(tmp_path))
    assert hub.profile is p
    assert "zh/X" in p.templates
    assert hub.state == enginehub.LOADING  # 不觸碰生命週期狀態


def test_discover不需引擎_輕量探索範本清單(tmp_path):
    # 目錄形式範本 (app 落地慣例): zh/ 是命名空間, X/ 是一個範本
    (tmp_path / "templates" / "zh" / "X").mkdir(parents=True)
    (tmp_path / "templates" / "zh" / "X" / "X.png").write_bytes(b"png")

    def never():
        raise AssertionError("discover 不應建構引擎")
    hub = enginehub.EngineHub(engine_factory=never)
    p = hub.discover(tmp_path)
    assert "zh/X" in p.templates
    assert hub.state == enginehub.LOADING  # 探索不改變生命週期狀態
    assert hub.profile is None             # 也不搶佔背景載入的 profile


def test_引擎警告只留subject_detection來源():
    def factory():
        warnings.warn("outside noise")  # filename 是本測試檔 → 應被濾掉
        return FakeEngine()
    hub = enginehub.EngineHub(engine_factory=factory)
    hub.load_engine()
    assert hub.state == enginehub.READY
    assert hub.warnings == []
