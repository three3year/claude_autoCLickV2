import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from subject_detection.engine import Match, QueryResult  # noqa: E402

import enginehub  # noqa: E402
from automation import flowdefaults  # noqa: E402
from automation import runner as runner_mod  # noqa: E402


CAL_PAIR = ("cal_left", "cal_right")
CAL_BASELINE = 100.0


def cal(pair=CAL_PAIR, baseline=CAL_BASELINE):
    return {"pair": list(pair), "baseline": float(baseline)}


_full = flowdefaults.complete

def wait(secs):
    return _full({"type": "wait", "wait": secs})


def click(x, y, **kw):
    return _full(dict({"type": "click", "click": [x, y]}, **kw))


def drag(x1, y1, x2, y2, **kw):
    return _full(dict({"type": "drag", "drag": [x1, y1], "to": [x2, y2]}, **kw))


def tgt(template, **attrs):
    return dict({"template": template}, **attrs)


def find(template, target=None, **kw):
    return _full(dict({"type": "find_click",
                       "target": tgt(template, **(target or {}))}, **kw))


HERE = "here"


def here(**kw):
    return find(HERE, type="find", **kw)


def repeat(n):
    return _full({"type": "repeat_start", "repeat": n})


def repeat_end(**kw):
    return _full(dict({"type": "repeat_end"}, **kw))


def branch_start():
    return _full({"type": "branch_start"})


def branch_or():
    return _full({"type": "branch_or"})


def branch_end(**kw):
    return _full(dict({"type": "branch_end"}, **kw))


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = 0
        self.on_sleep = None

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
    def __init__(self, origin, size=(1920, 1080)):
        self.origin = origin
        self.size = size

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

    def copy(self):
        return self

    def resized(self, s):
        return Screen((round(self.origin[0] * s), round(self.origin[1] * s)),
                      (max(1, round(self.size[0] * s)), max(1, round(self.size[1] * s))))


COLOR_THRESHOLD = 0.95


class Miss:
    def __init__(self, stage, score):
        self.stage, self.score = stage, float(score)


def miss(stage, score):
    return Miss(stage, score)


class Vision:
    def __init__(self, default=(1000, 500), size=(40, 20), clock=None):
        self.default = default
        self.size = size
        self._plans = {HERE: [(0, 0)]}
        self._calls = {HERE: 0}
        self._missing = set()
        self._lock = threading.Lock()
        self.grabs = []
        self.lookups = []
        self.color_checks = []
        self.expected_scales = []
        self.regions = []
        self.state = enginehub.READY
        self.preloads = []
        self.ensured = []
        self.preload_error = None
        self.preload_cost = 0.0
        self.after_each_load = None
        self.clock = clock
        self.grab_times = []

    @property
    def ready(self):
        return self.state == enginehub.READY

    def preload(self, names, on_loaded=None):
        names = list(names)
        self.preloads.append(names)
        if self.preload_error is not None:
            raise self.preload_error
        for n in names:
            if n in self._missing:
                raise KeyError(n)
            if self.preload_cost and self.clock is not None:
                self.clock.t += self.preload_cost
            if on_loaded is not None:
                on_loaded()
            if self.after_each_load is not None:
                self.after_each_load()

    def ensure_template(self, name):
        if name in self._missing:
            raise KeyError(name)
        self.ensured.append(name)

    def plan(self, name, results):
        self._plans[name] = list(results)
        self._calls[name] = 0

    def missing(self, name):
        self._missing.add(name)

    def grab(self, region=None):
        with self._lock:
            self.grabs.append(tuple(region) if region else None)
            if self.clock is not None:
                self.grab_times.append(self.clock.t)
        if region:
            origin = (int(region[0]), int(region[1]))
            return Screen(origin, (int(region[2]), int(region[3]))), origin
        return Screen((0, 0)), (0, 0)

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
        ox, oy = search_region.origin
        sw, sh = search_region.size
        with self._lock:
            self.regions.append((name, (ox, oy, sw, sh)))
        if isinstance(hit, Miss):
            return QueryResult(found=False, box=None, score=hit.score,
                               failed=hit.stage)
        hits = [] if hit is None else (
            [hit] if isinstance(hit[0], (int, float)) else list(hit))
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
            if rejected:
                return QueryResult(found=False, box=None,
                                   score=rejected[0].score, failed="color",
                                   rejected=rejected)
            return QueryResult(found=False, box=None, score=0.0,
                               failed="match")
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


PARK_DEFAULT = (0, 1079)


class Input:
    def __init__(self, events, lock=None, clock=None):
        self.events = events
        self._lock = lock or threading.Lock()
        self._cursor = PARK_DEFAULT
        self.track_clicks = False
        self.clock = clock
        self.times = []

    def _rec(self, ev):
        with self._lock:
            self.events.append(ev)
            if self.clock is not None:
                self.times.append(self.clock.t)

    def click(self, x, y, button="left", clicks=1, **kw):
        self._rec(("click", int(x), int(y), button, int(clicks)))
        if self.track_clicks:
            self._cursor = (int(x), int(y))

    def drag(self, x1, y1, x2, y2, button="left", duration_ms=300, hold_ms=0):
        self._rec(("drag", int(x1), int(y1), int(x2), int(y2), button,
                   int(duration_ms), int(hold_ms)))
        if self.track_clicks:
            self._cursor = (int(x2), int(y2))

    def move(self, x, y):
        self._rec(("move", int(x), int(y)))
        self._cursor = (int(x), int(y))

    def park(self, x, y):
        self._rec(("park", int(x), int(y)))
        self._cursor = (int(x), int(y))

    def cursor_pos(self):
        return self._cursor

    def virtual_screen(self):
        return {"x": 0, "y": 0, "w": 1920, "h": 1080}

    def monitor_rect_at(self, x, y):
        return (0, 0, 1920, 1080)


class FileLog:
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
        self.vision = Vision(clock=self.clock)
        self.events = []
        self.lock = threading.Lock()
        self.input = Input(self.events, self.lock, self.clock)
        monkeypatch.setattr(runner_mod, "time", self.clock)
        monkeypatch.setattr(runner_mod.capture, "grab", self.vision.grab)
        for name in ("click", "drag", "move", "park", "cursor_pos",
                     "virtual_screen", "monitor_rect_at"):
            monkeypatch.setattr(runner_mod.win, name, getattr(self.input, name))

    def make_runner(self):
        return runner_mod.Runner(self.vision, filelog=self.filelog)

    def place_calibration(self, scale, anchor):
        x, y = int(anchor[0]), int(anchor[1])
        self.vision.plan(CAL_PAIR[0], [(x, y)])
        self.vision.plan(CAL_PAIR[1], [(x + round(CAL_BASELINE * scale), y)])

    def start(self, runner, steps, scale=1.0, anchor=None, **kw):
        kw.setdefault("start_delay", 0)
        kw.setdefault("scan_region", [0, 0, 1920, 1080])
        if "calibration" not in kw:
            kw["calibration"] = cal()
            region = kw["scan_region"] or (0, 0)
            self.place_calibration(scale, anchor or (region[0], region[1]))
        self.runner = runner
        runner.start(steps, **kw)

    def run(self, steps, timeout=10.0, **kw):
        r = self.make_runner()
        self.start(r, steps, **kw)
        r._thread.join(timeout)
        assert not r._thread.is_alive(), "執行緒逾時未結束"
        self.runner = r
        return r

    def clicks(self):
        return [(e[1], e[2]) for e in self.events if e[0] == "click"]

    def kinds(self):
        return [e[0] for e in self.events if e[0] not in ("park", "move")]

    def input_times(self):
        return [(e[0], t) for e, t in zip(self.events, self.input.times)
                if e[0] in ("click", "drag")]

    def _cal_names(self):
        import calibration
        cal = getattr(getattr(self, "runner", None), "calibration", None)
        fb = calibration.fallback_pair(cal)
        return (set(cal["pair"]) | set(fb["pair"] if fb else ())) if cal else set()

    def lookups(self):
        skip = self._cal_names() | {HERE}
        return [n for n in self.vision.lookups if n not in skip]

    def grabs(self):
        return self.vision.grabs[1:] if self._cal_names() else self.vision.grabs

    def expected_scales(self):
        skip = self._cal_names()
        return [(n, s) for n, s in self.vision.expected_scales if n not in skip]

    def query_regions(self):
        skip = self._cal_names()
        return [(n, r) for n, r in self.vision.regions if n not in skip]

    def logs(self, runner=None):
        r = runner or self.runner
        return [e["msg"] for e in r.logs_since(0)]

    def log_text(self, runner=None):
        return "\n".join(self.logs(runner))


class Inline:
    def launch(self, rec, step):
        step.run()
        rec._pump()


class Held:
    def __init__(self):
        self.held = []

    def launch(self, rec, step):
        self.held.append((rec, step))

    def release(self):
        while self.held:
            rec, step = self.held.pop(0)
            step.run()
            rec._pump()
