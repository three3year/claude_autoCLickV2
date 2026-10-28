import threading
import time

LOADING = "loading"
READY = "ready"
FAILED = "failed"


def _default_engine_factory():
    from subject_detection.engine import Engine
    return Engine()


def gating_message(state):
    if state == LOADING:
        return "引擎載入中，辨識功能尚未就緒，請稍後再試"
    if state == FAILED:
        return "引擎載入失敗，辨識功能無法使用（詳見執行紀錄／日誌檔）"
    return None


class EngineHub:
    def __init__(self, engine_factory=None):
        self._factory = engine_factory or _default_engine_factory
        self._engine = None
        self.library = None
        self.generation = 0
        self._reg_lock = threading.RLock()
        self.state = LOADING
        self.error = None
        self.warnings = []

    @property
    def ready(self):
        return self.state == READY

    @property
    def coarse_only(self):
        return self._engine is not None and self._engine.coarse_only

    def _build_engine(self):
        import warnings as _warnings
        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            engine = self._factory()
        self.warnings = [str(w.message) for w in caught
                         if "subject_detection" in (w.filename or "")]
        self._engine = engine

    def load(self):
        import time

        import applog
        t0 = time.perf_counter()
        applog.log("engine.load.start")
        try:
            self._build_engine()
        except Exception as exc:
            self.error = exc
            self.state = FAILED
            applog.log("engine.load.failed", error=repr(exc),
                       secs=round(time.perf_counter() - t0, 2))
            return
        self.state = READY
        applog.log("engine.load.done",
                   secs=round(time.perf_counter() - t0, 2),
                   coarse_only=self.coarse_only)

    def bind(self, templates, config, registered_dir, changed=None):
        from subject_detection.library import make_library
        library = make_library(templates, config, registered_dir)
        old = self.library
        keep = changed is not None and old is not None and old.config == config
        if not keep:
            self.generation += 1
        with self._reg_lock:
            if keep:
                for name, t in library.templates.items():
                    prev = old.templates.get(name)
                    if prev is not None and name not in changed:
                        t.artifacts = prev.artifacts
            self.library = library
        return library

    def query(self, name, search_region, color_check=False,
              expected_scale=None):
        """查詢所有匹配; color_check＝這次查詢要不要`比色` (ADR 0007);
        expected_scale＝引擎的`預期尺度` (None＝照引擎參數的尺度範圍全掃,
        ADR 0009)."""
        return self._engine.query(self.library, name, search_region,
                                  color_check=color_check,
                                  expected_scale=expected_scale)

    def preload(self, names, on_loaded=None):
        """`範本預載`: 一次載入這些範本的登錄產物 (缺名丟 KeyError).

        on_loaded: 每載完一張呼叫一次 (無參數)。
        """
        for name in names:
            self.ensure_template(name)
            if on_loaded is not None:
                on_loaded()

    def ensure_template(self, name):
        with self._reg_lock:
            library = self.library
            if name not in library.templates:
                raise KeyError(name)
            self._engine.register(library, name)

    def files_locked(self):
        return self._reg_lock

    def start_preload(self, names, report):
        gen = self.generation

        def work():
            while self.state == LOADING:
                time.sleep(0.05)
            if self.state != READY or gen != self.generation:
                return
            report(gen, "start", len(names))
            for name in names:
                if gen != self.generation:
                    return
                try:
                    self.ensure_template(name)
                except KeyError:
                    continue
                except Exception as e:
                    report(gen, "bad", (name, e))
            if gen == self.generation:
                report(gen, "done", None)

        t = threading.Thread(target=work, daemon=True, name="template-preload")
        t.start()
        return t
