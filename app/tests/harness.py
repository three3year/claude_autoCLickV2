"""無頭測試用的假畫面／假輸入, 讓執行器可以跑完整份流程而不碰真實螢幕與滑鼠.

用法::

    def test_something(harness):
        harness.vision.plan("a.png", [None, (500, 400)])  # 第一次沒找到, 第二次起找到
        harness.run([{"type": "find_click", "template": "a.png"}])
        assert harness.clicks() == [(500, 400)]

設計要點:

- 所有作業系統邊界 (螢幕擷取、範本比對、滑鼠鍵盤) 都以模組屬性替換,
  沿用專案既有手法 (見 app/CLAUDE.md「測 runner 點擊邏輯時 monkeypatch
  automation.runner.win.click」)。
- 時間用虛擬時鐘, `等待` 不真的睡, 整份測試在數秒內跑完。
- 斷言對象是「事件序列」——誰在什麼順序做了什麼——不是內部欄位。
"""
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automation import runner as runner_mod  # noqa: E402
from automation import stage as stage_mod  # noqa: E402

TEMPLATES_DIR = os.path.join("C:", os.sep, "fake-templates")


# ---------- 步驟建構器 ----------

def wait(ms):
    return {"type": "wait", "ms": ms}


def click(x, y, **kw):
    return dict({"type": "click", "x": x, "y": y}, **kw)


def drag(x1, y1, x2, y2, **kw):
    return dict({"type": "drag", "x1": x1, "y1": y1, "x2": x2, "y2": y2}, **kw)


def find(template, **kw):
    return dict({"type": "find_click", "template": template}, **kw)


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


class Template:
    """假範本: 只帶著正式名稱 (相對路徑), 供假的比對器查腳本."""

    def __init__(self, name):
        self.name = name


class Screen:
    """假畫面: 只帶著這次擷取的原點, 供假的比對器換算絕對座標."""

    def __init__(self, origin):
        self.origin = origin


class Vision:
    """假的螢幕擷取與範本比對.

    每個`範本`名稱可安排一串逐次結果, 一次比對消耗一項, 最後一項無限重複:

        plan("a.png", [None, None, (500, 400)])  # 前兩次沒找到, 第三次起找到

    None = 沒找到; (x, y) = 在該絕對座標找到。
    未安排的`範本`一律在 default 座標找到。
    """

    def __init__(self, default=(1000, 500), size=(40, 20)):
        self.default = default
        self.size = size
        self._plans = {}
        self._calls = {}
        self._missing = set()
        self._lock = threading.Lock()
        self.grabs = []      # 每次擷取用的搜尋範圍
        self.lookups = []    # 每次比對的範本名稱

    def plan(self, name, results):
        self._plans[name] = list(results)
        self._calls[name] = 0

    def missing(self, name):
        """讓這個`範本`讀不到檔案 (模擬範本遺失)."""
        self._missing.add(name)

    # ---- 被替換進 automation.runner 的三個函式 ----
    def imread(self, path):
        name = _rel_name(path)
        if name in self._missing:
            return None
        return Template(name)

    def grab(self, region=None):
        with self._lock:
            self.grabs.append(tuple(region) if region else None)
        origin = (int(region[0]), int(region[1])) if region else (0, 0)
        return Screen(origin), origin

    def find_template(self, screen, tmpl, threshold=0.85):
        name = tmpl.name
        with self._lock:
            self.lookups.append(name)
            hit = self._next(name)
        w, h = self.size
        if hit is None:
            return {"found": False, "score": 0.0, "x": 0, "y": 0,
                    "w": w, "h": h, "cx": 0, "cy": 0}
        ox, oy = screen.origin
        return {"found": True, "score": 0.99,
                "x": hit[0] - ox - w // 2, "y": hit[1] - oy - h // 2,
                "w": w, "h": h,
                "cx": hit[0] - ox, "cy": hit[1] - oy}

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


class Harness:
    def __init__(self, monkeypatch):
        self.clock = Clock()
        self.vision = Vision()
        self.events = []
        self.lock = threading.Lock()
        self.input = Input(self.events, self.lock)
        monkeypatch.setattr(runner_mod, "time", self.clock)
        monkeypatch.setattr(runner_mod.capture, "grab", self.vision.grab)
        monkeypatch.setattr(runner_mod.matcher, "find_template",
                            self.vision.find_template)
        monkeypatch.setattr(runner_mod.imgio, "imread", self.vision.imread)
        for name in ("click", "drag", "press_keys", "move", "cursor_pos",
                     "virtual_screen"):
            monkeypatch.setattr(runner_mod.win, name, getattr(self.input, name))

    def make_stage(self, acquire_returns=None, block=False):
        self.stage = FakeStage(self.events, acquire_returns, block)
        return self.stage

    def make_runner(self, stage=None):
        return runner_mod.Runner(TEMPLATES_DIR, stage=stage)

    def run(self, steps, timeout=10.0, stage=None, **kw):
        """跑完一份流程並回傳執行器 (已結束).

        start_delay 預設 0; `搜尋範圍`預設原點 (0,0)，這樣`絕對座標`的數字
        就等於螢幕座標，測試好讀 (絕對座標＝相對範圍左上角的偏移)。
        """
        r = self.make_runner(stage)
        kw.setdefault("start_delay", 0)
        kw.setdefault("scan_region", [0, 0, 1920, 1080])
        r.start(steps, **kw)
        r._thread.join(timeout)
        assert not r._thread.is_alive(), "執行緒逾時未結束"
        self.runner = r
        return r

    # ---- 事件查詢 ----
    def clicks(self):
        return [(e[1], e[2]) for e in self.events if e[0] == "click"]

    def kinds(self):
        return [e[0] for e in self.events]

    def logs(self, runner=None):
        r = runner or self.runner
        return [e["msg"] for e in r.logs_since(0)]

    def log_text(self, runner=None):
        return "\n".join(self.logs(runner))


def _rel_name(path):
    """從假的完整路徑取回`範本`的正式名稱 (相對路徑)."""
    rel = os.path.relpath(path, TEMPLATES_DIR)
    return rel.replace(os.sep, "/")
