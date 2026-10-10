"""引擎生命週期: 狀態 (載入中/就緒/失敗) + `範本清單`綁定 + 查詢/預載接縫.

「視窗可操作」與「`引擎就緒`」是兩個時間點 (ADR 0004; 詞彙見
app/CONTEXT.md「啟動與就緒」)。App 與 runner 都只透過這個介面使用
主體偵測引擎——它是 runner 偵測接縫 (query) 的超集, 測試假件
(tests/harness.py 的 Vision) 與它同形狀, 是全 repo 唯一的假件點。

重量級 import (torch/cv2) 全部發生在 load_engine() 內, 本模組保持輕量。
"""

LOADING = "loading"   # 引擎載入中: 辨識類操作一律提示並拒絕
READY = "ready"       # `引擎就緒`: 辨識可用 (可能已降級 coarse-only)
FAILED = "failed"     # 引擎載入本身炸掉: 辨識永久不可用 (非降級)


def _default_engine_factory():
    from subject_detection.engine import Engine
    return Engine()


def gating_message(state):
    """就緒 gating 純決策: 此狀態下辨識類操作被拒絕的原因; None = 放行."""
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
        self.state = LOADING
        self.error = None    # FAILED 時的例外
        self.warnings = []   # 引擎建構時發出的警告 (降級 coarse-only 等)

    # ---------- 生命週期 ----------

    @property
    def ready(self):
        return self.state == READY

    @property
    def coarse_only(self):
        """驗證模型未載入 (引擎降級粗篩)。尚未載入完成時視為未降級."""
        return self._engine is not None and self._engine.coarse_only

    def _build_engine(self):
        """建構引擎 (torch/DINOv2); 收集引擎自己發的警告, 失敗直接拋."""
        import warnings as _warnings
        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            engine = self._factory()
        # 只留引擎自己發的警告 (torch 載入時的雜音不進執行紀錄)
        self.warnings = [str(w.message) for w in caught
                         if "subject_detection" in (w.filename or "")]
        self._engine = engine

    def load(self):
        """建構引擎 (背景執行緒用): 成功轉 READY, 失敗＝FAILED.

        範本清單由 app 先 `bind` 好 (純資料, 不需引擎), 所以外界不會觀察到「就緒但
        沒有範本清單」。不做整庫登錄: 登錄產物由`範本預載`/單張載入在使用當下載入
        (ADR 0004), 引擎就緒時間只含模型載入。起訖與耗時落地檔案日誌。
        """
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

    # ---------- 範本清單 ----------

    def bind(self, templates, config, registered_dir, changed=None):
        """綁定`範本清單` (app 組的 {範本名: 圖檔路徑}; 引擎不掃目錄, ADR 0006).

        config: 引擎參數 (內建預設＋流程的覆蓋); registered_dir: 登錄產物放哪。
        changed: None＝整份換掉 (換流程、引擎參數變了), 所有登錄產物失效; 給名稱
        集合＝只有這幾張 (新增、重截、改名) 要重新登錄, 其他沿用已在記憶體的登錄產物
        (圖只是搬了位置也算沒變)。不需引擎, 任何狀態都可呼叫。
        """
        from subject_detection.library import make_library
        library = make_library(templates, config, registered_dir)
        old = self.library
        if changed is not None and old is not None and old.config == config:
            for name, t in library.templates.items():
                prev = old.templates.get(name)
                if prev is not None and name not in changed:
                    t.artifacts = prev.artifacts
        self.library = library
        return library

    # ---------- 查詢 / 載入 (runner 偵測接縫的超集) ----------

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
        """單一範本的登錄產物就位 (已載入的直接沿用).

        缺名丟 KeyError(範本名)——args[0] 是乾淨的範本名, 呼叫端組錯誤
        訊息用 (引擎 query 的 KeyError 是給人看的字串, 兩者用途不同)。
        """
        if name not in self.library.templates:
            raise KeyError(name)
        self._engine.register(self.library, name)
