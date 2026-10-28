import threading
import time

import calibration as calib

from . import capture, findtarget, flowdefaults, flowfmt, win


class StopRequested(Exception):
    pass


def _applog(event, **fields):
    import applog
    applog.log(event, **fields)


def branch_layout(steps, start):
    """解析 start (branch_start 索引) 的分岔結構.

    回傳 (各分支起始索引 list, branch_end 索引); 標記不成對回傳 None.
    支援巢狀分岔 (內層標記以深度略過).
    """
    segs = [start + 1]
    depth = 0
    for i in range(start + 1, len(steps)):
        t = steps[i].get("type")
        if t == "branch_start":
            depth += 1
        elif t == "branch_end":
            if depth == 0:
                return segs, i
            depth -= 1
        elif t == "branch_or" and depth == 0:
            segs.append(i + 1)
    return None


def confirm_next_connected(steps, idx):
    """`找圖相連`檢查: steps[idx] 的緊接下一步是否為找圖步驟 (三態皆可).

    「點到下一步的圖出現」(confirm: "next") 的前提。最後一步、下一步是
    區段標記或其他步驟類型＝不相連。
    """
    return idx + 1 < len(steps) and findtarget.is_find(steps[idx + 1])


POINTER_TYPES = findtarget.POINTER_TYPES


def effect_confirm(step):
    """步驟實際生效的`生效確認`方式: none / gone / appear / next.

    找圖只有找到就點 (find_click) 時有意義; 座標點擊與拖曳一律可設; 其他步驟沒有。
    """
    if step.get("type") not in findtarget.CONFIRMABLE:
        return "none"
    return step["confirm"]


def origin_step(steps, idx):
    """`原點`在 steps[idx] 執行前由哪一步產生 (靜態推算): 那一步的索引, 沒有＝None.

    與編輯器的「預設原點推算」同一套走法: 往上找最近一個會更新原點的步驟
    (找圖三態、座標點擊勾著更新原點、拖曳), 等待/區段標記略過。
    """
    for j in range(idx - 1, -1, -1):
        s = steps[j]
        t = s.get("type")
        if t == "drag" or (t in ("click",) + findtarget.FIND_TYPES
                           and s["update_origin"]):
            return j
    return None


def origin_source(steps, idx):
    """`原點`在 steps[idx] 執行前來自哪種步驟 (靜態推算): "find" / "pointer" / None.

    「原點的圖離開」只在原點來自找圖時才判斷得了。
    """
    j = origin_step(steps, idx)
    if j is None:
        return None
    return "find" if steps[j].get("type") in findtarget.FIND_TYPES else "pointer"


def uses_origin_leaves(step):
    """座標點擊/拖曳是否用了`原點的圖離開` (存成 confirm: "gone")."""
    return step.get("type") in POINTER_TYPES and effect_confirm(step) == "gone"


def uses_confirm_next(step):
    """步驟是否用了「點到下一步的圖出現」."""
    return effect_confirm(step) == "next"


def flow_templates(steps, extra=()):
    return findtarget.referenced_templates(steps, extra)


def enclosing_end(steps, pos):
    """pos 之後第一個未配對的結束標記索引 (= pos 所屬最內層區段的結尾); 無則 None.

    pos 是區段開頭時就是它自己的結尾; 是「或」時是所屬分岔的結束。
    """
    depth = 0
    for j in range(pos + 1, len(steps)):
        t = steps[j].get("type")
        if t in ("repeat_start", "branch_start"):
            depth += 1
        elif t in ("repeat_end", "branch_end"):
            if depth == 0:
                return j
            depth -= 1
    return None


BUSY_GONE_CAP = 60.0
START_DELAY = 3.0
RETRY_INTERVAL = 1.0
BUSY_APPEAR = 1.0
BUSY_CHECK_KEY = "busy_check"
BUSY_CHECK_TYPES = ("click", "drag", "find_click")


def sends_input(step):
    """步驟會不會送出輸入: 座標點擊、拖曳、找到就點的找圖 (編輯器與執行器共用)."""
    return step.get("type") in BUSY_CHECK_TYPES


def has_busy_check(step):
    """步驟有沒有勾`忙碌檢查` (只有送出輸入的步驟算)."""
    return sends_input(step) and step[BUSY_CHECK_KEY]


GATE_ZH = findtarget.GATE_ZH


class GateBest:
    """輪詢期間各關的最高分 (執行紀錄「哪一關沒過」用).

    每輪沒挑到時 `see(f)` 記下那一關的分數; 比色那一關記比色分數與它的圖形分數
    (本尊比色沒過時使用者要同時看到兩個數字才知道該調範本還是比色)。
    """

    def __init__(self):
        self.best = {}

    def see(self, f):
        if f is None or f.picked is not None or f.query is None:
            return
        gate = f.query.failed
        if gate == "color" and f.rejected:
            m = max(f.rejected, key=lambda m: m.color)
            score, graphic = m.color, m.score
        elif gate in GATE_ZH:
            score, graphic = f.query.score, None
        else:
            return
        if gate not in self.best or score > self.best[gate][0]:
            self.best[gate] = (score, graphic)

    def text(self, f):
        """沒挑到的那一關與該關分數的一句話 (沒有＝空字串)."""
        if f is None:
            return ""
        failed = f.failed
        if failed == "count":
            return f"找到 {len(f.matches)} 個，挑選規則挑不到"
        if failed in GATE_ZH:
            score, graphic = self.best.get(failed, (None, None))
            if score is None and f.query is not None:
                score = f.query.score
            if score is None:
                return f"{GATE_ZH[failed]}沒過"
            text = f"{GATE_ZH[failed]}最高 {score:.3f}"
            if graphic is not None:
                text += f"（圖形 {graphic:.3f}）"
            return text
        return {"limit": "限定範圍落在搜尋範圍外", "origin": "沒有原點",
                "anchor": "沒有座標基準點"}.get(failed, "")


def gate_fields(f):
    """檔案紀錄的「最高分」與「沒過的那一關」兩欄 (找圖與生效確認共用的欄位名).

    沒挑到: 最後一次查詢的最高分與未過的關卡; 挑到了但該離開的沒離開 (原點的圖離開、
    目標圖消失): 分數是仍在原位那個匹配的, 關卡寫 still_there。
    """
    if f is None:
        return {"best": "-", "failed": "-"}
    if f.picked is not None:
        return {"best": f"{f.picked.score:.3f}", "failed": "still_there"}
    return {"best": f"{f.query.score:.3f}" if f.query is not None else "-",
            "failed": f.failed}


class WaitClock:
    """找圖等待共用的等待時鐘: 截止時間、輪詢間隔、逾時判定.

    分岔的輪詢、一般找圖、生效確認、忙碌檢查 (另有`忙碌出現等候`) 都用它
    判斷逾時。逾時照常計時, 不因忙碌指示延後 (ADR 0011)。start: 起算時間
    (monotonic), 沒給＝現在 (忙碌檢查從送出輸入的時間起算)。
    """

    def __init__(self, timeout, interval, appear_limit=None, start=None):
        now = time.monotonic() if start is None else start
        self.timeout = timeout
        self.interval = interval
        self._deadline = now + timeout
        self._appear_by = None if appear_limit is None else now + appear_limit

    def expired(self):
        return time.monotonic() >= self._deadline

    def appear_expired(self):
        """`忙碌出現等候`到了沒 (沒設＝永遠沒到)."""
        return (self._appear_by is not None
                and time.monotonic() >= self._appear_by)

    def nap(self, appear=False):
        """下一輪前該睡多久: 輪詢間隔, 但不超過截止時間 (appear＝忙碌出現等候)."""
        by = self._appear_by if appear and self._appear_by is not None else self._deadline
        return max(0.0, min(self.interval, by - time.monotonic()))


class Runner:
    def __init__(self, detector, filelog=None):
        self.detector = detector
        self.filelog = filelog or _applog
        self.ended = None
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._logs = []
        self._seq = 0
        self.running = False
        self.round = 0
        self.total_rounds = 0
        self.scan_region = None
        self.scale = 1.0
        self.anchor = None
        self._set_origin(None)
        self._step = (0, 0)
        self._prerun = None
        self._due = 0.0
        self._loops = []
        self._loop_stack = []

    def log(self, msg, level="info"):
        with self._lock:
            self._seq += 1
            self._logs.append({
                "seq": self._seq,
                "t": time.strftime("%H:%M:%S"),
                "level": level,
                "msg": msg,
            })
            if len(self._logs) > 500:
                self._logs = self._logs[-400:]

    def logs_since(self, since):
        with self._lock:
            return [e for e in self._logs if e["seq"] > since]

    def status(self):
        return {
            "running": self.running,
            "prerun": self._prerun,
            "round": self.round,
            "totalRounds": self.total_rounds,
            "step": self._step[0],
            "stepTotal": self._step[1],
            "loops": list(self._loops),
        }

    def start(self, steps, run_mode="count", run_count=1, scan_region=None,
              calibration=None, busy=None, pressed_at=None,
              start_delay=START_DELAY, retry_interval=RETRY_INTERVAL,
              busy_appear=BUSY_APPEAR):
        """pressed_at: 按下「執行」的時間 (monotonic); `開始延遲`從這時起算,
        沒給＝現在。start_delay / retry_interval / busy_appear 是固定行為
        (START_DELAY、RETRY_INTERVAL、BUSY_APPEAR), app 不傳; 參數只留給測試
        縮短虛擬時間。"""
        if self.running:
            raise RuntimeError("已在執行中")
        self._stop.clear()
        self.running = True
        self.round = 0
        self.total_rounds = 0 if run_mode == "infinite" else max(1, int(run_count))
        self.scan_region = scan_region
        self.calibration = calibration if calib.valid(calibration) else None
        self.scale = 1.0
        self.anchor = None
        self.retry_interval = max(0.0, float(retry_interval))
        self.busy = busy if busy and busy.get("template") else None
        self.busy_appear = max(0.0, float(busy_appear))
        self._last_input = None
        self._last_click = None
        self._origin_src = None
        self._step = (0, 0)
        now = time.monotonic()
        self._due = (now if pressed_at is None else pressed_at) + max(0, start_delay)
        self._prerun = "countdown" if self._due > now else "templates"
        self._loops = []
        self._thread = threading.Thread(
            target=self._run, args=(steps, start_delay), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _check_stop(self):
        if self._stop.is_set():
            raise StopRequested()

    def _sleep(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self._check_stop()
            time.sleep(min(0.05, max(0.0, end - time.monotonic())))

    def _run(self, steps, start_delay):
        try:
            if self._prerun == "countdown":
                self.log(f"{start_delay:g} 秒後開始執行 (按 F12 可隨時停止)")
            self._preload(steps)
            self._check_stop()
            self._sleep(self._due - time.monotonic())
            self._prerun = None

            self._calibrate()
            i = 0
            while not self._stop.is_set():
                i += 1
                self.round = i
                if self.total_rounds:
                    self.log(f"── 第 {i}/{self.total_rounds} 輪 ──")
                else:
                    self.log(f"── 第 {i} 輪 (無限模式) ──")
                idx = 0
                self._loop_stack = []
                while idx < len(steps):
                    self._check_stop()
                    self._loops = [(e[2] - e[1] + 1, e[2]) for e in self._loop_stack]
                    step = steps[idx]
                    t = step.get("type")
                    if t == "repeat_start":
                        total = max(1, int(step["repeat"]))
                        self._loop_stack.append([idx, total, total])
                        self.log(f"[{idx + 1}] 重複區段開始（共 {total} 次）")
                        idx += 1
                        continue
                    if t == "branch_start":
                        idx = self._exec_branch(idx, steps)
                        continue
                    if t == "branch_or":
                        end = enclosing_end(steps, idx)
                        idx = len(steps) if end is None else end
                        continue
                    if t == "branch_end":
                        idx += 1
                        continue
                    if t == "repeat_end":
                        if self._loop_stack:
                            ent = self._loop_stack[-1]
                            ent[1] -= 1
                            done = ent[2] - ent[1]
                            if ent[1] > 0:
                                self.log(f"[{idx + 1}] 重複區段 第 {done}/{ent[2]} 次完成 → 返回")
                                idx = ent[0] + 1
                                continue
                            self.log(f"[{idx + 1}] 重複區段完成（{ent[2]} 次）")
                            self._loop_stack.pop()
                        idx += 1
                        continue
                    self._step = (idx + 1, len(steps))
                    sig = self._exec_step(steps, idx)
                    if sig == "break":
                        idx = self._break_out(idx, steps)
                        continue
                    idx += 1
                if self.total_rounds and i >= self.total_rounds:
                    break
            self.log("執行完成", "ok")
            self.ended = "done"
        except StopRequested as e:
            self.log(str(e) or "已停止 (使用者中斷)", "warn")
            self.ended = "stopped"
        except Exception as e:
            self.log(f"執行錯誤: {e}", "error")
            self.ended = "error"
        finally:
            self._prerun = None
            self.running = False

    def _preload(self, steps):
        extra = list(self.calibration["pair"]) if self.calibration else []
        fb = calib.fallback_pair(self.calibration)
        if fb:
            extra += fb["pair"]
        if self.busy:
            extra.append(self.busy["template"])
        names = flow_templates(steps, extra)
        if not names:
            return
        self.log(f"準備範本中…（{len(names)} 張）")
        if self._prerun == "templates":
            self.log("等待準備範本完成")
        self._check_due()
        try:
            self.detector.preload(names, on_loaded=self._check_due)
        except KeyError as e:
            raise RuntimeError(f"範本預載失敗: 找不到範本圖片: {e.args[0]}"
                               " → 停止執行") from None
        except Exception as e:
            raise RuntimeError(f"範本預載失敗: {e} → 停止執行") from e
        self.log("範本就緒", "ok")

    def _check_due(self):
        if self._prerun == "countdown" and time.monotonic() >= self._due:
            self._prerun = "templates"
            self.log("等待準備範本完成")

    def _calibrate(self):
        cal = self.calibration
        if cal is None:
            self._log_calibrate(result="no_pair")
            raise RuntimeError("這份流程沒有校準對（舊格式或尚未設定）→ 不執行；"
                               "請先在編輯器設定校準對")
        region = getattr(self, "scan_region", None)
        screen, org = self._grab(region)
        c = calib.calibrate(self.detector.query, screen, org, cal)
        m = c.measurement
        used = ({"used": "fallback", "main_missing": ",".join(c.main.missing)}
                if c.used == "fallback" else {})
        if c.problem == "missing":
            fields = dict(result="missing", pair=",".join(cal["pair"]),
                          missing=",".join(c.main.missing),
                          best=",".join(f"{c.main.scores[n]:.3f}"
                                        for n in c.main.missing))
            if c.fallback is not None:
                fields.update(fallback_pair=",".join(c.pair),
                              fallback_missing=",".join(m.missing))
            self._log_calibrate(**fields)
            raise RuntimeError(f"開頭校準失敗：{c.describe()} → 不執行；"
                               "請確認搜尋範圍框住了遊戲畫面、畫面上看得到校準對")
        centers = ";".join(f"({x},{y})" for x, y in (m.centers[n] for n in c.pair))
        if c.problem == "too_close":
            self._log_calibrate(result="too_close", pair=",".join(c.pair),
                                centers=centers, **used)
            raise RuntimeError(f"開頭校準失敗：{c.describe()} → 不執行")
        measured = dict(pair=",".join(c.pair), centers=centers,
                        distance=f"{m.distance:.1f}", baseline=f"{c.baseline:.1f}",
                        scale=f"{c.scale:.3f}", **used)
        if not c.in_range:
            self._log_calibrate(result="out_of_range", **measured)
            raise RuntimeError(f"開頭校準：{calib.out_of_range_text(c.scale)} → 不執行")
        self.scale, self.anchor = c.scale, c.anchor
        self._log_calibrate(result="ok", **measured)
        if c.used == "fallback":
            self.log(f"主校準對找不到（缺「{'」「'.join(c.main.missing)}」），"
                     f"改用備用校準對「{c.pair[0]}」×「{c.pair[1]}」，座標誤差略大",
                     "warn")
        self.log(f"開頭校準：畫面倍率 ×{self.scale:.3f}（距離 {m.distance:.1f}px"
                 f" ÷ 基準 {c.baseline:.1f}px）", "ok")
        where = (f"校準對第一張「{c.pair[0]}」的中心" if c.used == "main" else
                 f"備用校準對第一張「{c.pair[0]}」的中心加上設定時量好的偏移")
        self.log(f"座標基準點 ({self.anchor[0]}, {self.anchor[1]})"
                 f"（{where}；固定矩形以它為原點）", "ok")

    def _log_calibrate(self, **fields):
        self._log_file("calibrate", **fields)

    def _log_file(self, event, **fields):
        try:
            self.filelog(event, **fields)
        except Exception:
            pass

    def _set_origin(self, xy, target=None, box=None, origin=None):
        self._last_click = xy
        self._origin_src = (None if target is None else
                            {"target": target, "box": box, "origin": origin})

    def _input(self, kind, *args, **kw):
        getattr(win, kind)(*args, **kw)
        self._last_input = time.monotonic()

    def _busy_seen(self, no, screen, org):
        if self.busy is None:
            return False
        f = self._find(no, self.busy, screen, org, self._last_click,
                       kind="忙碌指示")
        return f.picked is not None

    def _busy_check(self, no, step):
        if not has_busy_check(step):
            return
        if self.busy is None:
            self.log(f"[{no}] 勾了忙碌檢查但流程沒設忙碌指示 → 不等", "warn")
            return
        sent = self._last_input
        region = getattr(self, "scan_region", None)
        interval = step.get("interval", flowdefaults.WAIT["interval"])
        clock = WaitClock(BUSY_GONE_CAP, max(0.1, float(interval)),
                          appear_limit=self.busy_appear, start=sent)
        box = None
        polls = 0
        while True:
            self._check_stop()
            screen, org = self._grab(region)
            polls += 1
            f = self._find(no, self.busy, screen, org, self._last_click,
                           kind="忙碌指示")
            if box is None:
                if f.picked is not None:
                    box = f.picked.box
                    self.log(f"[{no}] 看到忙碌指示 → 等它消失")
                elif clock.appear_expired():
                    result = "not_appeared"
                    break
            else:
                hit = findtarget.still_there(box, f.matches)
                if hit is None:
                    result = "gone"
                    break
                box = hit.box
                if clock.expired():
                    result = "timeout"
                    break
            self._sleep(clock.nap(appear=box is None))
        waited = time.monotonic() - sent
        rec = dict(step=no, result=result, waited=f"{waited:.2f}", polls=polls)
        if box is not None:
            rec["picked"] = findtarget.fmt_box(box)
        self._log_file("busy.check", **rec)
        if result == "gone":
            self.log(f"[{no}] 忙碌指示已消失（等了 {waited:.1f}s）", "ok")
        elif result == "timeout":
            msg = (f"[{no}] 忙碌指示 {int(BUSY_GONE_CAP)} 秒沒消失"
                   "（可能斷線或畫面卡住）")
            self.log(msg + " → 停止執行", "warn")
            raise RuntimeError(msg + " → 停止執行")

    def _retry_ready(self, busy_seen, gate):
        now = time.monotonic()
        if (self._last_input is not None
                and now - self._last_input < self.retry_interval - 1e-6):
            return False
        if busy_seen:
            if gate["busy_since"] is None:
                gate["busy_since"] = now
            return False
        self._settle_busy(gate, now)
        return True

    @staticmethod
    def _settle_busy(gate, now):
        if gate["busy_since"] is not None:
            gate["delay"] += now - gate["busy_since"]
            gate["busy_since"] = None

    def _sc(self, v):
        return flowfmt.scale_px(v, self.scale)

    def _exec_step(self, steps, idx):
        step = steps[idx]
        no = idx + 1
        t = step.get("type")
        if t in POINTER_TYPES:
            return self._exec_pointer(steps, idx)

        if t == "wait":
            secs = float(step["wait"])
            self.log(f"[{no}] 等待 {secs:g} 秒")
            self._sleep(secs)

        elif t in findtarget.FIND_TYPES:
            return self._exec_find(steps, idx)

        else:
            self.log(f"[{no}] 未知步驟類型: {t}", "warn")

    def _exec_pointer(self, steps, idx):
        step = steps[idx]
        no = idx + 1
        t = step["type"]
        if self._last_click is None:
            self.log(f"[{no}] 相對座標: 尚無原點 → 跳過", "warn")
            return None
        base = self._last_click
        if t == "click":
            dx, dy = step["click"]
            x = base[0] + self._sc(dx)
            y = base[1] + self._sc(dy)
            args, kw = (x, y), {}
            after = (x, y)
            updates = step["update_origin"]
            text = f"點擊 ({x}, {y})（上一步 {int(dx):+d},{int(dy):+d}）"
            fields = {"at": f"({x},{y})"}
        else:
            x1, y1 = (self._sc(v) for v in step["drag"])
            x2, y2 = (self._sc(v) for v in step["to"])
            where = f"（上一步 {x1:+d},{y1:+d} → {x2:+d},{y2:+d}）"
            x1, y1, x2, y2 = (base[0] + x1, base[1] + y1,
                              base[0] + x2, base[1] + y2)
            duration = float(step["duration"])
            hold = float(step["hold"])
            args = (x1, y1, x2, y2)
            kw = {"duration_ms": int(round(duration * 1000)),
                  "hold_ms": int(round(hold * 1000))}
            after = (x2, y2)
            updates = True
            hd = f" 停頓{hold:g}s放開" if hold else ""
            text = f"拖曳 ({x1}, {y1}) → ({x2}, {y2}){where} {duration:g}s{hd}"
            fields = {"from": f"({x1},{y1})", "to": f"({x2},{y2})"}
        before, src = self._last_click, self._origin_src
        mode = effect_confirm(step)
        if mode == "gone" and src is None:
            self.log(f"[{no}] 「原點的圖離開」但原點不是來自找圖（或沒有原點）"
                     "→ 無法執行", "warn")
            self._log_file("input.confirm", step=no, kind=t, mode=mode,
                            result="cannot_run", **fields)
            return self._on_not_found(no, f"[{no}] 原點不是來自找圖，無法確認生效",
                                      step["on_fail"])
        self._input(t, *args, **kw)
        self.log(f"[{no}] {text}")
        if mode == "next" and not confirm_next_connected(steps, idx):
            self.log(f"[{no}] 「下一步的圖出現」但下一步不是找圖步驟"
                     "→ 以「不確認」執行", "warn")
            mode = "none"
        if mode == "none":
            self._log_file("input", step=no, kind=t, **fields)
        self._busy_check(no, step)
        if mode == "none":
            if updates:
                self._set_origin(after)
            return None
        rec = dict(step=no, kind=t, mode=mode, **fields)
        gates = GateBest()
        if mode == "gone":
            tgt, box = src["target"], src["box"]
            what = f"原點的圖「{tgt.get('template', '')}」"
            rec.update(template=tgt.get("template", ""),
                       picked=findtarget.fmt_box(box))

            def check(screen, org):
                f = self._find(no, tgt, screen, org, src["origin"])
                return findtarget.still_there(box, f.matches) is None, f
            waiting, done, fail = (f"{what}離開原位", f"{what}已離開原位",
                                   f"{what}仍在原位")
        else:
            origin = after if updates else before
            ctgt = (findtarget.target(steps[idx + 1]) if mode == "next"
                    else findtarget.confirm_target(step))
            what = (("下一步的圖" if mode == "next" else "確認圖")
                    + f"「{ctgt.get('template', '')}」")
            rec["template"] = ctgt.get("template", "")
            if origin is None and findtarget.needs_origin(ctgt):
                self.log(f"[{no}] {what}出現的判定以原點為基準: 尚無原點 → "
                         "以「不確認」執行", "warn")
                self._log_file("input.confirm", result="cannot_run", **rec)
                return None

            def check(screen, org):
                f = self._find(no, ctgt, screen, org, origin, kind="確認")
                gates.see(f)
                return f.picked is not None, f
            waiting, done, fail = f"{what}出現", f"{what}已出現", f"未見{what}"
        timeout = float(step["timeout"])
        self.log(f"[{no}] 等待生效（直到{waiting}）")

        def stopped(last, polls, inputs):
            self._log_file("input.confirm", result="stopped",
                           **dict(rec, polls=polls, inputs=inputs,
                                  **gate_fields(last)))
        ok, f, polls, inputs, delay = self._await_effect(
            no, timeout, float(step["interval"]), check,
            lambda screen, org: True, lambda: self._input(t, *args, **kw),
            on_stop=stopped)
        rec.update(inputs=inputs, polls=polls, busy_delay=f"{delay:.2f}")
        if ok:
            if updates:
                self._set_origin(after)
            self.log(f"[{no}] 已生效（{done}）", "ok")
            if mode == "gone":
                self._log_file("input.confirm", result="gone", **rec)
            else:
                self._log_file("input.confirm", result="found",
                               **dict(rec, picked=findtarget.fmt_box(f.picked.box)))
            return None
        self._log_file("input.confirm", result="timeout",
                       **dict(rec, **gate_fields(f)))
        why = "" if mode == "gone" else gates.text(f)
        why = f"，{why}" if why else ""
        return self._on_not_found(
            no, f"[{no}] {'點擊' if t == 'click' else '拖曳'}後 {timeout}s 內"
                f"{fail}（送了 {inputs} 次{why}）", step["on_fail"])

    def _await_effect(self, no, timeout, interval, check, may_retry, resend,
                      on_stop=None):
        region = getattr(self, "scan_region", None)
        clock = WaitClock(timeout, interval)
        inputs, polls = 1, 0
        gate = {"busy_since": None, "delay": 0.0}
        last = None
        try:
            while True:
                self._sleep(clock.interval)
                self._check_stop()
                screen, org = self._grab(region)
                polls += 1
                ok, last = check(screen, org)
                if ok:
                    break
                busy = self._busy_seen(no, screen, org)
                if may_retry(screen, org) and self._retry_ready(busy, gate):
                    resend()
                    inputs += 1
                if clock.expired():
                    break
        except StopRequested:
            if on_stop is not None and last is not None:
                on_stop(last, polls, inputs)
            raise
        self._settle_busy(gate, time.monotonic())
        return ok, last, polls, inputs, gate["delay"]

    def _break_out(self, pos, steps):
        while True:
            end = enclosing_end(steps, pos)
            if end is None:
                raise RuntimeError(f"[{pos + 1}] 跳出後已不在任何區段內 → 停止執行")
            if steps[end].get("type") == "repeat_end":
                if self._loop_stack:
                    self._loop_stack.pop()
                self.log(f"[{end + 1}] 跳出重複區段（放棄剩餘次數）", "warn")
            else:
                self.log(f"[{end + 1}] 跳出分岔區段", "warn")
            if steps[end]["on_break"] == "break":
                pos = end
                continue
            return end + 1

    def _avoid_cursor(self, region):
        """截圖本身不含游標 (GDI), 但游標停留會讓底下 UI 反白, 干擾比對.

        多螢幕大小不一時虛擬桌面的角落可能根本不在螢幕上, SetCursorPos 到不了。
        """
        if region:
            x, y = region[0] - 2, region[1] + region[3] + 1
            cx, cy = region[0] + region[2] / 2.0, region[1] + region[3] / 2.0
        else:
            vs = win.virtual_screen()
            cx, cy = vs["x"] + vs["w"] / 2.0, vs["y"] + vs["h"] / 2.0
            x, y = vs["x"], vs["y"] + vs["h"]
        x1, y1, x2, y2 = win.monitor_rect_at(cx, cy)
        x, y = min(max(x, x1), x2 - 1), min(max(y, y1), y2 - 1)
        if win.cursor_pos() == (x, y):
            return
        win.park(x, y)
        self._sleep(0.08)

    def _grab(self, region):
        self._avoid_cursor(region)
        return capture.grab(region)

    def _find(self, no, tgt, screen, org, origin, kind="範本"):
        try:
            return findtarget.find(tgt, self.detector, screen, org,
                                   origin=origin, scale=self.scale,
                                   anchor=self.anchor)
        except KeyError:
            raise RuntimeError(
                f"[{no}] 找不到{kind}圖片: {tgt.get('template', '')}") from None

    def _record(self, no, role, f, result, **extra):
        tgt = f.target
        fields = {
            "step": no, "role": role, "template": tgt.get("template", ""),
            "result": result,
            "limit": findtarget.fmt_box(f.limit) if f.limit else "all",
            "pick": findtarget.pick_text(tgt),
            "color": "on" if tgt.get("color") else "off",
            "matches": "[" + "; ".join(map(findtarget.fmt_match,
                                           f.matches)) + "]",
        }
        if f.rejected:
            fields["rejected"] = "[" + "; ".join(
                map(findtarget.fmt_match, f.rejected)) + "]"
        if f.picked is not None:
            fields["picked"] = findtarget.fmt_box(f.picked.box)
        if result in ("timeout", "cannot_run", "not_appeared", "stopped", "not_gone"):
            fields.update(gate_fields(f))
        fields.update(extra)
        self._log_file("find.target", **fields)

    def _exec_branch(self, idx, steps):
        lay = branch_layout(steps, idx)
        if lay is None:
            self.log(f"[{idx + 1}] 分岔標記不成對 → 跳過", "warn")
            return idx + 1
        segs, end = lay
        conds = []
        for s in segs:
            if s >= end or not findtarget.is_find(steps[s]):
                self.log(f"[{idx + 1}] 分岔的每個分支開頭必須是找圖步驟 → 跳過分岔", "warn")
                return end + 1
            conds.append(steps[s])

        timeout = max(float(c["timeout"]) for c in conds)
        interval = min(float(c["interval"]) for c in conds)
        region = getattr(self, "scan_region", None)
        tgts = [findtarget.target(c) for c in conds]
        names = " | ".join(t.get("template") or "?" for t in tgts)
        self.log(f"[{idx + 1}] 分岔: 等待任一張圖出現（{names}）")
        origin = self._last_click
        for k, t in enumerate(tgts):
            if origin is None and findtarget.needs_origin(t):
                self.log(f"[{segs[k] + 1}] 分支條件以原點為基準: 尚無原點 → "
                         "這個分支不成立", "warn")
        clock = WaitClock(timeout, interval)
        polls = 0
        last = [findtarget.Found(t, reason="origin") for t in tgts]
        try:
            while True:
                self._check_stop()
                screen, org = self._grab(region)
                polls += 1
                for k, t in enumerate(tgts):
                    f = last[k] = self._find(segs[k] + 1, t, screen, org, origin)
                    if f.picked is not None:
                        self.log(f"[{idx + 1}] 分岔 → 走分支 {k + 1}（{f.template}）", "ok")
                        self._record(segs[k] + 1, "branch", f, "found", polls=polls)
                        return segs[k]
                if clock.expired():
                    break
                self._sleep(clock.interval)
        except StopRequested:
            if polls:
                for k, f in enumerate(last):
                    self._record(segs[k] + 1, "branch", f, "stopped", polls=polls)
            raise
        for k, f in enumerate(last):
            self._record(segs[k] + 1, "branch", f,
                         "cannot_run" if f.reason == "origin" else "timeout",
                         polls=polls)
        if any(c["on_fail"] == "stop" for c in conds):
            raise RuntimeError(
                f"[{idx + 1}] 分岔逾時 {timeout}s, 沒有任何分支條件成立 → 停止執行")
        self.log(f"[{idx + 1}] 分岔逾時 {timeout}s, 沒有任何分支成立 → 跳過", "warn")
        if steps[end]["on_break"] == "break":
            return self._break_out(end, steps)
        return end + 1

    def _on_not_found(self, no, msg, on_nf):
        if on_nf == "stop":
            raise RuntimeError(msg + " → 停止執行")
        if on_nf == "break":
            self.log(msg + " → 跳出目前區段", "warn")
            return "break"
        self.log(msg + " → 跳過", "warn")
        return None

    def _exec_find(self, steps, idx):
        step = steps[idx]
        no = idx + 1
        tgt = findtarget.target(step)
        name = tgt.get("template", "")
        timeout = float(step["timeout"])
        interval = float(step["interval"])
        region = getattr(self, "scan_region", None)
        kind = step["type"]
        do_click = kind == "find_click"
        on_nf = step["on_fail"]
        off = tuple(self._sc(v) for v in step["offset"])
        origin = self._last_click
        if origin is None and findtarget.needs_origin(tgt):
            self.log(f"[{no}] 找圖目標以原點為基準: 尚無原點 → 跳過", "warn")
            self._record(no, "wait_gone" if kind == "wait_gone" else "find",
                         findtarget.Found(tgt, reason="origin"), "cannot_run")
            return None

        if kind == "wait_gone":
            clock = WaitClock(timeout, interval)
            tracked = None
            polls = 0
            gates = GateBest()
            f = None
            try:
                while True:
                    self._check_stop()
                    screen, org = self._grab(region)
                    polls += 1
                    f = self._find(no, tgt, screen, org, origin)
                    gates.see(f)
                    hit = (f.picked if tracked is None
                           else findtarget.still_there(tracked, f.matches))
                    if hit is not None:
                        tracked = hit.box
                        if step["update_origin"]:
                            cx, cy = hit.center
                            self._set_origin((cx + off[0], cy + off[1]), tgt,
                                             hit.box, origin)
                    elif tracked is not None:
                        self.log(f"[{no}] 「{name}」已消失", "ok")
                        self._record(no, "wait_gone", f, "gone", polls=polls,
                                     picked=findtarget.fmt_box(tracked))
                        return None
                    if clock.expired():
                        break
                    self._sleep(clock.interval)
            except StopRequested:
                if f is not None:
                    extra = ({"picked": findtarget.fmt_box(tracked)}
                             if tracked is not None else {})
                    self._record(no, "wait_gone", f, "stopped", polls=polls,
                                 **extra)
                raise
            if tracked is not None:
                msg = f"[{no}] 逾時 {timeout}s 內「{name}」仍未消失"
                self._record(no, "wait_gone", f, "not_gone", polls=polls,
                             picked=findtarget.fmt_box(tracked))
            else:
                why = gates.text(f)
                msg = (f"[{no}] 逾時 {timeout}s 內「{name}」從未出現"
                       + (f"（{why}）" if why else ""))
                self._record(no, "wait_gone", f, "timeout", polls=polls)
            return self._on_not_found(no, msg, on_nf)

        clock = WaitClock(timeout, interval)
        gates = GateBest()
        polls = 0
        f = None
        try:
            while True:
                self._check_stop()
                screen, org = self._grab(region)
                polls += 1
                f = self._find(no, tgt, screen, org, origin)
                gates.see(f)
                if f.picked is not None:
                    break
                if clock.expired():
                    break
                self._sleep(clock.interval)
        except StopRequested:
            if f is not None:
                self._record(no, "find", f, "stopped", polls=polls)
            raise

        hit = f.picked
        if hit is None:
            why = gates.text(f)
            msg = (f"[{no}] 逾時 {timeout}s 未找到「{name}」"
                   + (f"（{why}）" if why else ""))
            self._record(no, "find", f, "timeout", polls=polls)
            return self._on_not_found(no, msg, on_nf)

        cx, cy = hit.center
        sx, sy = cx + off[0], cy + off[1]
        many = f"，共 {len(f.matches)} 個匹配" if len(f.matches) > 1 else ""
        self._record(no, "find", f, "found", polls=polls,
                     **({"click": f"({sx},{sy})"} if do_click else {}))
        if not do_click:
            if step["update_origin"]:
                self._set_origin((sx, sy), tgt, hit.box, origin)
            self.log(f"[{no}] 找到「{name}」(相似度 {hit.score:.3f}{many}) "
                     f"位置 ({sx}, {sy})", "ok")
            return None

        self._input("click", sx, sy)
        if step["update_origin"]:
            self._set_origin((sx, sy), tgt, hit.box, origin)
        self._busy_check(no, step)
        confirm = step["confirm"]
        if confirm == "next" and not confirm_next_connected(steps, idx):
            self.log(f"[{no}] 「點到下一步的圖出現」但下一步不是找圖步驟"
                     "→ 以「不確認」執行（點一次就走）", "warn")
            confirm = "none"
        if confirm == "none":
            self.log(f"[{no}] 找到「{name}」(相似度 {hit.score:.3f}{many}) → "
                     f"點擊 ({sx}, {sy})", "ok")
            return None
        return self._confirm_click(steps, idx, confirm, tgt, origin, hit.box,
                                   off, timeout, interval, on_nf)

    def _confirm_click(self, steps, idx, mode, tgt, origin, box,
                       off, timeout, interval, on_nf):
        step = steps[idx]
        no = idx + 1
        name = tgt.get("template", "")
        fail = f"[{no}] 點擊「{name}」後 {timeout}s 內未確認生效"
        ctgt = None
        if mode == "next":
            ctgt = findtarget.target(steps[idx + 1])
            cname = ctgt.get("template", "")
            label = f"下一步的圖「{cname}」出現"
            done = f"下一步的圖「{cname}」已出現"
            kind = "下一步的"
            fail = f"[{no}] 點擊「{name}」後 {timeout}s 內未見下一步的圖「{cname}」"
        elif mode == "gone":
            kind = "範本"
            label, done = f"「{name}」消失", f"「{name}」已消失"
        else:
            ctgt = findtarget.confirm_target(step)
            cname = ctgt.get("template", "")
            kind = "確認"
            label, done = f"確認圖「{cname}」出現", f"確認圖「{cname}」已出現"
        role = "confirm_" + mode
        if (ctgt is not None and self._last_click is None
                and findtarget.needs_origin(ctgt)):
            self.log(f"[{no}] {label}的判定以原點為基準: 尚無原點 → "
                     "以「不確認」執行（點一次就走）", "warn")
            self._record(no, role, findtarget.Found(ctgt, reason="origin"),
                         "cannot_run")
            return None
        self.log(f"[{no}] 已點擊「{name}」→ 等待生效（直到{label}）")
        cur = {"box": box, "still": None, "fm": None}
        gates = GateBest()

        def check(screen, org):
            fm = cur["fm"] = self._find(no, tgt, screen, org, origin)
            cur["still"] = findtarget.still_there(cur["box"], fm.matches)
            if cur["still"] is not None:
                cur["box"] = cur["still"].box
            if mode == "gone":
                return cur["still"] is None, fm
            fc = self._find(no, ctgt, screen, org, self._last_click, kind=kind)
            gates.see(fc)
            return fc.picked is not None, fc

        def stopped(last, polls, n_clicks):
            extra = {"polls": polls, "clicks": n_clicks}
            if mode == "gone":
                extra["picked"] = findtarget.fmt_box(cur["box"])
            self._record(no, role, last, "stopped", **extra)

        def resend():
            cx, cy = cur["still"].center
            sx, sy = cx + off[0], cy + off[1]
            self._input("click", sx, sy)
            if step["update_origin"]:
                self._set_origin((sx, sy), tgt, cur["box"], origin)

        ok, f, polls, n_clicks, delay = self._await_effect(
            no, timeout, interval, check,
            lambda screen, org: cur["still"] is not None, resend,
            on_stop=stopped)
        extra = {"polls": polls, "clicks": n_clicks,
                 "busy_delay": f"{delay:.2f}"}
        if mode == "gone":
            extra["picked"] = findtarget.fmt_box(cur["box"])
        if ok:
            self.log(f"[{no}] 點擊已生效（{done}）", "ok")
            self._record(no, role, f, "gone" if mode == "gone" else "found",
                         **extra)
            return None
        self._record(no, role, f, "not_gone" if mode == "gone" else "timeout",
                     **extra)
        why = "" if mode == "gone" else gates.text(f)
        return self._on_not_found(no, fail + (f"（{why}）" if why else ""), on_nf)

