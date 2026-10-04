"""引擎生命週期: 狀態 (載入中/就緒/失敗) + 範本清單綁定 + 查詢/預載接縫.

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
        self.profile = None
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

    def load(self, root, config_dir=None, extra=None):
        """引擎＋範本探索一氣呵成 (背景執行緒用): 全部成功才轉 READY,
        中途任何失敗＝FAILED——外界不會觀察到「就緒但沒有範本清單」。

        不做整庫登錄: 登錄產物由`範本預載`/單張載入在使用當下載入
        (ADR 0004), 引擎就緒時間只含模型載入。起訖與耗時落地檔案日誌,
        供啟動驗收與日後回歸對照 (票 07)。
        """
        import time

        import applog
        t0 = time.perf_counter()
        applog.log("engine.load.start")
        try:
            self._build_engine()
            library = self.discover(root, config_dir, extra)
            if self.profile is None:
                # 背景載入期間 refresh() 可能已放入更新的快照 (切換
                # profile/增刪範本), 不能拿這份較舊的探索結果覆蓋
                self.profile = library
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

    def discover(self, root, config_dir=None, extra=None):
        """輕量探索範本 (不需引擎、不讀登錄產物, 只掃目錄與設定).

        `root` 是放著 `templates/` 與 `registered/` 的目錄——app 交的是當前
        流程的**工作區**; `config_dir` 是引擎參數設定所在的 profile 目錄
        (省略＝同 root); `extra` 是要一併交給引擎、但不住在 root 裡的
        `範本清單` (app 用它帶入 profile 自存的`校準對`圖)。掃出來的清單組成
        引擎的模板庫, 引擎自己不掃目錄 (ADR 0006)。

        回傳模板庫供 UI 立即使用, 不觸碰生命週期狀態與 hub.profile
        (背景載入中的 load() 才擁有它們)。
        """
        import os

        import flowfile
        from subject_detection.library import load_config, make_library
        templates_dir = os.path.join(str(root), "templates")
        if not os.path.isdir(templates_dir):
            raise FileNotFoundError(f"沒有範本目錄可掃: {templates_dir}")
        templates = flowfile.scan_templates(templates_dir)
        templates.update(extra or {})
        return make_library(templates,
                            load_config(config_dir if config_dir is not None
                                        else root),
                            os.path.join(str(root), "registered"))

    def refresh(self, root, config_dir=None, extra=None):
        """重新探索並綁定範本清單 (失效標記的落實): 範本增刪改後呼叫,
        清單立即反映、所有登錄產物失效 (artifacts 歸零), 下次
        `範本預載`/單張載入時重載。不需引擎, 任何狀態都可呼叫。"""
        self.profile = self.discover(root, config_dir, extra)
        return self.profile

    # ---------- 查詢 / 載入 (runner 偵測接縫的超集) ----------

    def query(self, name, search_region, color_check=False):
        """查詢所有匹配; color_check＝這次查詢要不要`比色` (ADR 0007)."""
        return self._engine.query(self.profile, name, search_region,
                                  color_check=color_check)

    def preload(self, names):
        """`範本預載`: 一次載入這些範本的登錄產物 (缺名丟 KeyError)."""
        for name in names:
            self.ensure_template(name)

    def ensure_template(self, name):
        """單一範本的登錄產物就位 (已載入的直接沿用).

        缺名丟 KeyError(範本名)——args[0] 是乾淨的範本名, 呼叫端組錯誤
        訊息用 (引擎 query 的 KeyError 是給人看的字串, 兩者用途不同)。
        """
        if name not in self.profile.templates:
            raise KeyError(name)
        self._engine.register(self.profile, name)
