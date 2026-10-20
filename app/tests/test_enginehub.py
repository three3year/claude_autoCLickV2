"""引擎生命週期介面 (startup-speed 票 01): 狀態、委派、預載/單張載入.

假引擎經 engine_factory 注入——不碰 torch、不開執行緒, 測試直接把狀態
撥成任意值。介面形狀＝runner 偵測接縫 (query) 的超集, 與 harness 假件一致。
"""
import time
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
    assert lib.templates["按鈕"].image_path == tmp_path / "按鈕.png"
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


# ---------- 背景`範本預載` (flow-folder-format 11) ----------

class RegEngine:
    """登錄會真的把登錄產物掛上去的假引擎; gate＝登錄卡在那裡等放行; bad＝壞圖."""

    coarse_only = False

    def __init__(self, gate=None, bad=()):
        self.gate = gate
        self.bad = set(bad)
        self.registered = []

    def register(self, library, name):
        t = library.templates[name]
        if t.artifacts is None:
            if self.gate is not None:
                self.gate.wait(5)
            if name in self.bad:
                raise ValueError("讀不了這張圖")
            self.registered.append(name)
            t.artifacts = "ART-" + name


def _bound_hub(tmp_path, engine, names=("a", "b", "c"), load=True):
    hub = enginehub.EngineHub(engine_factory=lambda: engine)
    hub.bind({n: str(tmp_path / f"{n}.png") for n in names}, {"k": 1}, tmp_path / "reg")
    if load:
        hub.load()
    return hub


def _collect():
    got = []
    return got, lambda gen, event, data: got.append((gen, event, data))


def test_背景預載_載入全部並回報開始與就緒(tmp_path):
    engine = RegEngine()
    hub = _bound_hub(tmp_path, engine)
    got, report = _collect()
    hub.start_preload(["a", "b", "c"], report).join(5)
    assert engine.registered == ["a", "b", "c"]
    assert [e for _, e, _ in got] == ["start", "done"]
    assert got[0][2] == 3


def test_背景預載_引擎還沒就緒就等就緒後開始(tmp_path):
    import threading
    engine = RegEngine()
    hub = _bound_hub(tmp_path, engine, load=False)
    got, report = _collect()
    t = hub.start_preload(["a"], report)
    t.join(0.3)
    assert t.is_alive() and got == [] and engine.registered == []
    threading.Thread(target=hub.load).start()
    t.join(5)
    assert engine.registered == ["a"]
    assert [e for _, e, _ in got] == ["start", "done"]


def test_背景預載_引擎載入失敗就不做(tmp_path):
    def factory():
        raise RuntimeError("no torch")
    hub = enginehub.EngineHub(engine_factory=factory)
    hub.bind({"a": str(tmp_path / "a.png")}, {}, tmp_path / "reg")
    got, report = _collect()
    t = hub.start_preload(["a"], report)
    hub.load()
    t.join(5)
    assert got == []


def test_背景預載中換流程_舊的停下不回報就緒(tmp_path):
    import threading
    gate = threading.Event()
    engine = RegEngine(gate=gate)
    hub = _bound_hub(tmp_path, engine)
    got, report = _collect()
    t = hub.start_preload(["a", "b", "c"], report)
    time.sleep(0.1)                       # 卡在第一張
    swap = threading.Thread(target=lambda: hub.bind(
        {"x": str(tmp_path / "x.png")}, {"k": 1}, tmp_path / "reg"))
    gen0 = hub.generation
    swap.start()                          # 換流程 (等那一張登錄完才接手)
    while hub.generation == gen0:
        time.sleep(0.01)
    gate.set()
    swap.join(5)
    t.join(5)
    assert engine.registered == ["a"], "換流程後舊清單其餘的不載"
    assert [e for _, e, _ in got] == ["start"], "舊的不回報就緒"
    assert list(hub.library.templates) == ["x"]


def test_背景預載遇到壞圖_回報警告_其他照載(tmp_path):
    engine = RegEngine(bad={"b"})
    hub = _bound_hub(tmp_path, engine)
    got, report = _collect()
    hub.start_preload(["a", "b", "c"], report).join(5)
    assert engine.registered == ["a", "c"]
    events = [(e, d) for _, e, d in got]
    assert events[1][0] == "bad" and events[1][1][0] == "b"
    assert events[-1][0] == "done"
    with pytest.raises(ValueError):   # 按執行時照舊擋下
        hub.preload(["a", "b"])


def test_背景預載中按執行_等同一份_同一張不載兩次(tmp_path):
    import threading
    gate = threading.Event()
    engine = RegEngine(gate=gate)
    hub = _bound_hub(tmp_path, engine)
    got, report = _collect()
    bg = hub.start_preload(["a", "b", "c"], report)
    time.sleep(0.1)
    run = threading.Thread(target=lambda: hub.preload(["a", "b", "c"]))
    run.start()                           # 執行器的預載接著等
    time.sleep(0.1)
    assert run.is_alive(), "還沒載完就等"
    gate.set()
    run.join(5)
    bg.join(5)
    assert sorted(engine.registered) == ["a", "b", "c"], "每張只登錄一次"


def test_搬檔期間背景預載停在原地_換好清單後讀新路徑(tmp_path):
    engine = RegEngine()
    hub = _bound_hub(tmp_path, engine, names=("a",))
    got, report = _collect()
    with hub.files_locked():
        t = hub.start_preload(["a"], report)
        t.join(0.3)
        assert engine.registered == [], "搬檔的人持有鎖時不登錄"
        hub.bind({"a": str(tmp_path / "templates" / "a.png")}, {"k": 1}, tmp_path / "reg",
                 changed=set())   # 同一段裡換清單 (可重入)
    t.join(5)
    assert engine.registered == ["a"]
    assert hub.library.templates["a"].image_path == tmp_path / "templates" / "a.png"
