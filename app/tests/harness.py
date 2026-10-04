"""無頭測試用的假畫面／假輸入, 讓執行器可以跑完整份流程而不碰真實螢幕與滑鼠.

用法::

    def test_something(harness):
        harness.vision.plan("a.png", [None, (500, 400)])  # 第一次沒找到, 第二次起找到
        harness.run([find("a.png")])
        assert harness.clicks() == [(500, 400)]

設計要點:

- 偵測查詢走 runner 的偵測接縫 (建構時注入的 detector), 假件形狀＝引擎的
  query(範本名, 搜尋區域) → QueryResult——這是全 repo 唯一的假件點。
- 其餘作業系統邊界 (螢幕擷取、滑鼠鍵盤) 以模組屬性替換, 沿用專案既有手法
  (見 app/CLAUDE.md「測 runner 點擊邏輯時 monkeypatch
  automation.runner.win.click」)。
- 時間用虛擬時鐘, `等待` 不真的睡, 整份測試在數秒內跑完。
- 每次執行開頭都會`校準` (ADR 0009): `run()` 預設交一對校準圖 (CAL_PAIR) 給
  執行器, 並在畫面上擺好讓量出來的`畫面倍率`剛好是 `scale` (預設 1)——
  不在意校準的測試照舊寫; 要測校準本身就自己給 `calibration=` 與 plan。
- 斷言對象是「事件序列」——誰在什麼順序做了什麼——不是內部欄位。
"""
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from subject_detection.engine import Match, QueryResult  # noqa: E402

import enginehub  # noqa: E402
from automation import runner as runner_mod  # noqa: E402
from automation import stage as stage_mod  # noqa: E402


# ---------- 校準 ----------

CAL_PAIR = ("cal_left", "cal_right")   # run() 預設交給執行器的`校準對`
CAL_BASELINE = 100.0                    # 它的`基準距離` (流程尺度)


def cal(pair=CAL_PAIR, baseline=CAL_BASELINE):
    """流程的校準資料 (校準對兩張範本名 + 基準距離)."""
    return {"pair": list(pair), "baseline": float(baseline)}


# ---------- 步驟建構器 ----------

def wait(ms):
    return {"type": "wait", "ms": ms}


def click(x, y, **kw):
    return dict({"type": "click", "x": x, "y": y}, **kw)


def drag(x1, y1, x2, y2, **kw):
    return dict({"type": "drag", "x1": x1, "y1": y1, "x2": x2, "y2": y2}, **kw)


def tgt(template, **attrs):
    """`找圖目標`: 範本 + 限定範圍/挑選規則/比色 (缺＝預設)."""
    return dict({"template": template}, **attrs)


def find(template, target=None, **kw):
    """找圖步驟; target 給`找圖目標`的其餘屬性 (limit/pick/colorCheck)."""
    return dict({"type": "find_click", "target": tgt(template, **(target or {}))},
                **kw)


def key(keys):
    return {"type": "key", "keys": keys}


def loop(count):
    return {"type": "loop_start", "count": count}


def loop_end(**kw):
    return dict({"type": "loop_end"}, **kw)


def branch_start():
    return {"type": "branch_start"}


def branch_or():
    return {"type": "branch_or"}


def branch_end(**kw):
    return dict({"type": "branch_end"}, **kw)


class Clock:
    """虛擬時鐘: sleep 直接推進時間, 不真的等待."""

    def __init__(self):
        self.t = 1000.0
        self.sleeps = 0
        self.on_sleep = None  # 每次 sleep 後呼叫, 用來模擬「等待中途的外力介入」

    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        self.t += max(0.0, seconds)
        self.sleeps += 1
        if self.on_sleep is not None:
            self.on_sleep(self.sleeps)

    def strftime(self, fmt):
        return "00:00:00"


class Screen:
    """假畫面: 只帶著這次擷取的原點與大小, 供假的偵測器換算絕對座標.

    支援影像式的裁切 `screen[y0:y1, x0:x1]` (裁出的子畫面原點跟著位移),
    找圖目標的`限定範圍`就是這樣裁圖再查詢。
    """

    def __init__(self, origin, size=(1920, 1080)):
        self.origin = origin
        self.size = size   # (w, h)

    @property
    def shape(self):
        return (self.size[1], self.size[0], 3)

    def __getitem__(self, key):
        ys, xs = key[0], key[1]
        w, h = self.size
        x0, x1, _ = xs.indices(w)
        y0, y1, _ = ys.indices(h)
        return Screen((self.origin[0] + x0, self.origin[1] + y0),
                      (max(0, x1 - x0), max(0, y1 - y0)))


COLOR_THRESHOLD = 0.95   # 假偵測器的比色門檻 (同明日方舟 profile)


class Vision:
    """假的螢幕擷取與偵測查詢 (形狀＝引擎的 query, 回 QueryResult).

    每個`範本`名稱可安排一串逐次結果, 一次查詢消耗一項, 最後一項無限重複:

        plan("a.png", [None, None, (500, 400)])  # 前兩次沒找到, 第三次起找到
        plan("card", [[(100, 50), (300, 50, 0.95)]])  # 一次查詢兩個匹配

    None = 沒找到; (x, y) = 在該絕對座標 (框中心) 找到; 一串位置 = 畫面上同時
    有這幾個匹配 (可帶第三個值當分數, 預設 0.99; 第四個值當比色分數, 預設
    0.99——要求比色時低於 COLOR_THRESHOLD 的不算匹配, 同引擎)。只有中心落在這次查詢的
    畫面 (含`限定範圍`裁切) 內的匹配才會被回報。未安排的`範本`一律在 default
    座標找到。
    """

    def __init__(self, default=(1000, 500), size=(40, 20)):
        self.default = default
        self.size = size
        self._plans = {}
        self._calls = {}
        self._missing = set()
        self._lock = threading.Lock()
        self.grabs = []      # 每次擷取用的搜尋範圍
        self.lookups = []    # 每次查詢的範本名稱
        self.color_checks = []   # 每次查詢的 (範本名稱, 是否要求比色)
        self.expected_scales = []   # 每次查詢的 (範本名稱, 收到的`預期尺度`)
        # ---- 生命週期假件 (enginehub.EngineHub 的形狀, 票 01) ----
        self.state = enginehub.READY   # 測試可撥成 LOADING / FAILED
        self.preloads = []         # 每次`範本預載`收到的名單
        self.ensured = []          # 單張載入 (ensure_template) 的範本名
        self.preload_error = None  # 預載時要拋的例外 (模擬缺圖/損壞)

    @property
    def ready(self):
        return self.state == enginehub.READY

    def preload(self, names):
        """`範本預載`假件: 記錄名單; 名單中有 missing 的範本丟
        KeyError(範本名) (同 enginehub.ensure_template)."""
        names = list(names)
        self.preloads.append(names)
        if self.preload_error is not None:
            raise self.preload_error
        for n in names:
            if n in self._missing:
                raise KeyError(n)

    def ensure_template(self, name):
        if name in self._missing:
            raise KeyError(name)
        self.ensured.append(name)

    def plan(self, name, results):
        self._plans[name] = list(results)
        self._calls[name] = 0

    def missing(self, name):
        """讓這個`範本`不存在於 profile (查詢丟 KeyError, 同引擎)."""
        self._missing.add(name)

    # ---- 被替換進 automation.runner 的擷取函式 ----
    def grab(self, region=None):
        with self._lock:
            self.grabs.append(tuple(region) if region else None)
        if region:
            origin = (int(region[0]), int(region[1]))
            return Screen(origin, (int(region[2]), int(region[3]))), origin
        return Screen((0, 0)), (0, 0)

    # ---- runner 的偵測查詢接縫 (同 Engine.query 的形狀) ----
    def query(self, name, search_region, color_check=False,
              expected_scale=None):
        if name in self._missing:
            raise KeyError(f"unknown template: {name!r}")
        with self._lock:
            self.lookups.append(name)
            self.color_checks.append((name, bool(color_check)))
            self.expected_scales.append((name, expected_scale))
            hit = self._next(name)
        w, h = self.size
        hits = [] if hit is None else (
            [hit] if isinstance(hit[0], (int, float)) else list(hit))
        ox, oy = search_region.origin
        sw, sh = search_region.size
        matches, rejected = [], []
        for p in hits:
            box = (int(p[0]) - ox - w // 2, int(p[1]) - oy - h // 2, w, h)
            cx, cy = int(p[0]) - ox, int(p[1]) - oy
            if not (0 <= cx < sw and 0 <= cy < sh):
                continue
            m = Match(box, float(p[2]) if len(p) > 2 else 0.99)
            if color_check:
                m.color = float(p[3]) if len(p) > 3 else 0.99
                if m.color < COLOR_THRESHOLD:
                    rejected.append(m)
                    continue
            matches.append(m)
        matches.sort(key=lambda m: m.score, reverse=True)
        if not matches:
            failed = "color" if rejected else "match"
            return QueryResult(found=False, box=None, score=0.0,
                               failed=failed, rejected=rejected)
        return QueryResult(found=True, box=matches[0].box,
                           score=matches[0].score, matches=matches,
                           rejected=rejected)

    def _next(self, name):
        if name not in self._plans:
            return self.default
        plan = self._plans[name]
        i = self._calls[name]
        self._calls[name] = i + 1
        return plan[min(i, len(plan) - 1)]


class Input:
    """假的滑鼠鍵盤: 只記錄事件, 不送出任何真實輸入."""

    def __init__(self, events, lock=None):
        self.events = events
        self._lock = lock or threading.Lock()
        self._cursor = (0, 0)

    def _rec(self, ev):
        with self._lock:
            self.events.append(ev)

    def click(self, x, y, button="left", clicks=1, **kw):
        self._rec(("click", int(x), int(y), button, int(clicks)))
        self._cursor = (int(x), int(y))

    def drag(self, x1, y1, x2, y2, button="left", duration_ms=300, hold_ms=0):
        self._rec(("drag", int(x1), int(y1), int(x2), int(y2), button))
        self._cursor = (int(x2), int(y2))

    def press_keys(self, combo):
        self._rec(("keys", combo))

    def move(self, x, y):
        self._rec(("move", int(x), int(y)))
        self._cursor = (int(x), int(y))

    def cursor_pos(self):
        return self._cursor

    def virtual_screen(self):
        return {"x": 0, "y": 0, "w": 1920, "h": 1080}


class FakeStage(stage_mod.Stage):
    """假舞台: 把取得/讓出/退出記進同一條事件序列, 方便斷言交錯順序.

    acquire_returns 可安排逐次回傳值 (False = 整場執行已結束)。
    block=True 時 acquire 會真的阻塞 (模擬`排隊`), 直到 cancel() 被呼叫。
    """

    def __init__(self, events, acquire_returns=None, block=False):
        self.events = events
        self._returns = list(acquire_returns or [])
        self._n = 0
        self.left = 0
        self._block = block
        self.blocked = threading.Event()   # acquire 已經卡住了
        self._cancelled = threading.Event()

    def acquire(self):
        self.events.append(("acquire",))
        i = self._n
        self._n += 1
        if self._block:
            self.blocked.set()
            self._cancelled.wait(5)
            return False  # 被喚醒 = 輪不到你了
        return self._returns[i] if i < len(self._returns) else True

    def release(self):
        self.events.append(("release",))

    def cancel(self):
        self._cancelled.set()

    def leave(self):
        self.left += 1
        self.events.append(("leave",))


class FileLog:
    """假的檔案日誌 (`applog.log` 的形狀): 記下每一筆 (事件, 欄位)."""

    def __init__(self):
        self.records = []

    def __call__(self, event, **fields):
        self.records.append((event, fields))

    def of(self, event):
        return [f for e, f in self.records if e == event]


class Harness:
    def __init__(self, monkeypatch):
        self.clock = Clock()
        self.filelog = FileLog()
        self.vision = Vision()
        self.events = []
        self.lock = threading.Lock()
        self.input = Input(self.events, self.lock)
        monkeypatch.setattr(runner_mod, "time", self.clock)
        monkeypatch.setattr(runner_mod.capture, "grab", self.vision.grab)
        for name in ("click", "drag", "press_keys", "move", "cursor_pos",
                     "virtual_screen"):
            monkeypatch.setattr(runner_mod.win, name, getattr(self.input, name))

    def make_stage(self, acquire_returns=None, block=False):
        self.stage = FakeStage(self.events, acquire_returns, block)
        return self.stage

    def make_runner(self, stage=None):
        return runner_mod.Runner(self.vision, stage=stage,
                                 filelog=self.filelog)

    def place_calibration(self, scale, region):
        """在搜尋範圍左上附近擺好 CAL_PAIR, 中心距離＝基準距離×scale."""
        x, y = int(region[0]) + 10, int(region[1]) + 10
        self.vision.plan(CAL_PAIR[0], [(x, y)])
        self.vision.plan(CAL_PAIR[1], [(x + round(CAL_BASELINE * scale), y)])

    def start(self, runner, steps, scale=1.0, **kw):
        """以測試預設值啟動執行器 (不等它結束).

        start_delay 預設 0; `搜尋範圍`預設原點 (0,0)，這樣`絕對座標`的數字
        就等於螢幕座標，測試好讀 (絕對座標＝相對範圍左上角的偏移)。
        沒給 `calibration` 時交 CAL_PAIR, 開頭量出來的倍率＝scale。
        """
        kw.setdefault("start_delay", 0)
        kw.setdefault("scan_region", [0, 0, 1920, 1080])
        if "calibration" not in kw:
            kw["calibration"] = cal()
            self.place_calibration(scale, kw["scan_region"] or (0, 0))
        self.runner = runner
        runner.start(steps, **kw)

    def run(self, steps, timeout=10.0, stage=None, **kw):
        """跑完一份流程並回傳執行器 (已結束); 預設值見 `start`."""
        r = self.make_runner(stage)
        self.start(r, steps, **kw)
        r._thread.join(timeout)
        assert not r._thread.is_alive(), "執行緒逾時未結束"
        self.runner = r
        return r

    # ---- 事件查詢 ----
    def clicks(self):
        return [(e[1], e[2]) for e in self.events if e[0] == "click"]

    def kinds(self):
        return [e[0] for e in self.events]

    def _cal_names(self):
        cal = getattr(getattr(self, "runner", None), "calibration", None)
        return set(cal["pair"]) if cal else set()

    def lookups(self):
        """步驟的查詢 (範本名序列), 不含開頭校準查校準對的那兩次."""
        skip = self._cal_names()
        return [n for n in self.vision.lookups if n not in skip]

    def grabs(self):
        """步驟的擷取 (搜尋範圍序列), 不含開頭校準的那一次."""
        return self.vision.grabs[1:] if self._cal_names() else self.vision.grabs

    def expected_scales(self):
        """步驟查詢收到的`預期尺度`, 不含開頭校準 (那兩次不帶預期尺度)."""
        skip = self._cal_names()
        return [(n, s) for n, s in self.vision.expected_scales if n not in skip]

    def logs(self, runner=None):
        r = runner or self.runner
        return [e["msg"] for e in r.logs_since(0)]

    def log_text(self, runner=None):
        return "\n".join(self.logs(runner))
