"""流程執行器: 在背景執行緒依序執行步驟, 支援停止、回圈、即時紀錄.

找圖相關步驟 (find_click / wait_gone / confirm / branch) 的辨識走建構時注入
的偵測器 (detector): `query(範本名, 搜尋區域影像) → QueryResult`——與主體
偵測引擎的 `Engine.query` 同形狀 (matches: 所有匹配, 框為搜尋區域內座標),
範本不存在時丟 KeyError。門檻由引擎的 profile config 決定, 步驟層級沒有
threshold (見 ADR 0002)。每個找圖點 (找圖三態、點擊後確認、分支條件) 都是
執行一個`找圖目標` (automation/findtarget.py): 多個匹配時由挑選規則決定
點哪一個, 「消失」只看先前挑中的那個位置 (ADR 0007)。

每次執行開頭先`校準` (ADR 0009): 流程自帶`校準對`與`基準距離`, 執行器在畫面上
找到兩張圖、以中心距離 ÷ 基準距離得出這次的`畫面倍率`——座標乘上它, 每次找圖
把它當`預期尺度`交給偵測器。量不到 (或流程沒有校準對) 就一個輸入都不送。

`生效確認`還沒通過時的`補做` (重送同一個輸入) 有兩道門 (ADR 0008): 距上一次
輸入已過`補做間隔`, 且畫面上沒有`忙碌指示` (流程有設才查; 只在補做判斷時查)。
所有實際送出的輸入都經過 `_input`, 它記下「上一次輸入」的時間。
"""
import threading
import time

import calibration as calib

from . import capture, findtarget, flowfmt, win


class StopRequested(Exception):
    pass


def _applog(event, **fields):
    """預設的檔案日誌: app 旁的 autoclick.log (延後匯入, 測試可另行注入)."""
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
    區段標記或其他步驟類型＝不相連; 測試選取片段恰結束在該步驟時,
    傳入的清單就是片段本身, 自然判為不相連。
    """
    return idx + 1 < len(steps) and steps[idx + 1].get("type") == "find_click"


POINTER_TYPES = findtarget.POINTER_TYPES   # 座標點擊與拖曳: 也有`生效確認` (ADR 0008)


def effect_confirm(step):
    """步驟實際生效的`生效確認`方式: none / gone / appear / next.

    找圖只有動作為點擊時有意義; 座標點擊與拖曳一律可設; 其他步驟沒有。
    """
    t = step.get("type")
    if t == "find_click" and step.get("action", "click") != "click":
        return "none"
    if t != "find_click" and t not in POINTER_TYPES:
        return "none"
    return step.get("confirm", "none")


def origin_source(steps, idx):
    """`原點`在 steps[idx] 執行前來自哪種步驟 (靜態推算): "find" / "pointer" / None.

    與編輯器的「預設原點推算」同一套走法: 往上找最近一個會更新原點的步驟
    (找圖三態、座標點擊勾著更新原點、拖曳), 等待/按鍵/區段標記略過。
    「原點的圖離開」只在原點來自找圖時才判斷得了。
    """
    for s in reversed(steps[:idx]):
        t = s.get("type")
        if t == "drag":
            return "pointer"
        if t == "click" and s.get("updateOrigin", True):
            return "pointer"
        if t == "find_click" and s.get("updateOrigin", True):
            return "find"
    return None


def uses_origin_leaves(step):
    """座標點擊/拖曳是否用了`原點的圖離開` (存成 confirm: "gone")."""
    return step.get("type") in POINTER_TYPES and effect_confirm(step) == "gone"


def uses_confirm_next(step):
    """步驟是否用了「點到下一步的圖出現」."""
    return effect_confirm(step) == "next"


def flow_templates(steps, extra=()):
    """`範本預載`名單 (見 findtarget.referenced_templates, 唯一的定義)."""
    return findtarget.referenced_templates(steps, extra)


def _matching_branch_end(steps, i):
    """從 branch_or 位置往後找所屬的 branch_end 索引 (深度感知)."""
    depth = 0
    for j in range(i + 1, len(steps)):
        t = steps[j].get("type")
        if t == "branch_start":
            depth += 1
        elif t == "branch_end":
            if depth == 0:
                return j
            depth -= 1
    return len(steps)


class Runner:
    def __init__(self, detector, stage=None, filelog=None):
        self.detector = detector  # 偵測查詢接縫 (見模組 docstring)
        self.stage = stage  # 並行執行時注入; None = 單流程, 完全走原本的路徑
        # 檔案日誌 (applog.log 的形狀): 每個找圖目標的判定結束寫一筆
        self.filelog = filelog or _applog
        self.ended = None   # 結束原因: done / error / stopped
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._logs = []          # {seq, t, level, msg}
        self._seq = 0
        self.running = False
        self.round = 0
        self.total_rounds = 0    # 0 = 無限
        self.scan_region = None
        self.avoid_hover = False
        self.scale = 1.0
        self._set_origin(None)
        self._step = (0, 0)  # (目前步驟序號, 總步驟數); 0 = 尚未進入步驟
        # 開跑前階段: "countdown"＝`開始延遲`未到期 / "templates"＝已到期仍在
        # `範本預載` / None＝已開跑 (UI 據此顯示「倒數啟動中…」/「等待準備範本完成…」)
        self._prerun = None
        self._due = 0.0  # `開始延遲`到期時刻 (monotonic): 按下執行＋延遲秒數
        self._prev_type = None  # 上一個執行過的步驟型別 (供拖曳後讓出的標註)
        self._loops = []     # 進行中重複區段的 (目前次數, 總次數), 由外到內
        self._loop_stack = []  # 進行中重複區段: [起始索引, 剩餘次數, 總次數]

    # ---------- 紀錄 ----------
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
            "prerun": self._prerun,  # 開跑前階段 (round 仍為 0 時才有值)
            "round": self.round,
            "totalRounds": self.total_rounds,
            "step": self._step[0],
            "stepTotal": self._step[1],
            "loops": list(self._loops),  # 巢狀重複區段進度: [(目前, 總數), ...]
        }

    # ---------- 控制 ----------
    def start(self, steps, run_mode="count", run_count=1, start_delay=3,
              scan_region=None, avoid_hover=False, calibration=None,
              retry_interval=1.0, busy=None, pressed_at=None):
        """pressed_at: 按下「執行」的時間 (monotonic); `開始延遲`從這時起算,
        沒給＝現在。"""
        if self.running:
            raise RuntimeError("已在執行中")
        self._stop.clear()
        self.running = True
        self.round = 0
        self.total_rounds = 0 if run_mode == "infinite" else max(1, int(run_count))
        self.scan_region = scan_region  # 全域搜尋範圍 [x,y,w,h]; 步驟未自設範圍時套用
        self.avoid_hover = avoid_hover  # 找圖截圖前先把滑鼠移開, 避免 hover 反白干擾
        # 流程的校準資料 {pair, baseline} (不成形＝None); `畫面倍率`由開頭校準得出
        self.calibration = calibration if calib.valid(calibration) else None
        self.scale = 1.0
        # `補做間隔` (秒) 與`忙碌指示` (找圖目標或 None): 流程層級設定
        self.retry_interval = max(0.0, float(retry_interval))
        self.busy = busy if busy and busy.get("template") else None
        self._last_input = None   # 上一次送出輸入的時間 (monotonic)
        self._last_click = None  # 上一次點擊的螢幕座標, 供相對座標步驟使用
        self._origin_src = None  # 原點來自找圖時: {target, box, origin}
        self._step = (0, 0)
        # `開始延遲`是時間下限: 到期前`範本預載`同時進行
        now = time.monotonic()
        self._due = (now if pressed_at is None else pressed_at) + max(0, start_delay)
        # 啟動當下就已到期 (延遲「無」) → 一開始就是「等待範本」, 不閃倒數
        self._prerun = "countdown" if self._due > now else "templates"
        self._prev_type = None
        self._loops = []
        self._thread = threading.Thread(
            target=self._run, args=(steps, start_delay), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self.stage is not None:
            # 可能正卡在 acquire 排隊; 沒人喚醒就連 leave 都執行不到
            self.stage.cancel()

    def _check_stop(self):
        if self._stop.is_set():
            raise StopRequested()

    def _sleep(self, seconds):
        """可中斷的等待"""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self._check_stop()
            time.sleep(min(0.05, max(0.0, end - time.monotonic())))

    # ---------- 舞台 (並行執行) ----------
    def _take_stage(self):
        """取得舞台 (會阻塞排隊); 拿不到就收工."""
        if self.stage is None:
            return
        if not self.stage.acquire():
            self._check_stop()  # 自己被停 → 用一般的中斷訊息
            # 為什麼取不到 (視窗不見了/整場結束/切換失敗) 由舞台那邊記錄
            raise StopRequested("無法取得舞台 → 收工")
        self._check_stop()

    def _wait_yielding(self, seconds):
        """`等待`期間讓出舞台——這是唯一的`讓出點` (見 ADR-0004).

        被停止時不再回頭搶舞台, 直接讓例外往上拋 (交還由 _run 的 leave 負責)。
        """
        if self.stage is None:
            self._sleep(seconds)
            return
        self.stage.release()
        self._sleep(seconds)
        self._take_stage()

    # ---------- 主迴圈 ----------
    def _run(self, steps, start_delay):
        try:
            if start_delay > 0:
                self.log(f"{start_delay} 秒後開始執行 (按 F12 可隨時停止)")
            # `範本預載`在倒數中進行: 開跑前一次載齊, 失敗立刻不開跑
            self._preload(steps)
            # 預載途中按的 F12 在這裡生效 (預載超過延遲時底下沒有剩餘等待)
            self._check_stop()
            self._sleep(self._due - time.monotonic())  # 等到`開始延遲`到期
            self._prerun = None

            self._take_stage()  # 第一個動作之前先上台
            self._calibrate()   # 量不到就拋錯: 一個輸入都不送
            i = 0
            while not self._stop.is_set():
                i += 1
                self.round = i
                if self.total_rounds:
                    self.log(f"── 第 {i}/{self.total_rounds} 輪 ──")
                else:
                    self.log(f"── 第 {i} 輪 (無限模式) ──")
                idx = 0
                self._loop_stack = []  # 進行中的重複區段: [起始索引, 剩餘次數, 總次數]
                while idx < len(steps):
                    self._check_stop()
                    # 巢狀重複區段目前次數 (供狀態顯示分辨階段); 只含重複區段
                    self._loops = [(e[2] - e[1] + 1, e[2]) for e in self._loop_stack]
                    step = steps[idx]
                    t = step.get("type")
                    if t == "loop_start":
                        total = max(1, int(step.get("count", 1)))
                        self._loop_stack.append([idx, total, total])
                        self.log(f"[{idx + 1}] 重複區段開始（共 {total} 次）")
                        idx += 1
                        continue
                    if t == "branch_start":
                        idx = self._exec_branch(idx, steps)
                        continue
                    if t == "branch_or":
                        # 走完一個分支 → 跳到分岔結束
                        idx = _matching_branch_end(steps, idx)
                        continue
                    if t == "branch_end":
                        idx += 1
                        continue
                    if t == "loop_end":
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
            # 任何退出路徑都必須交還舞台, 否則其他流程會永久卡住
            if self.stage is not None:
                self.stage.leave()
            self._prerun = None
            self.running = False

    # ---------- `範本預載` ----------
    def _preload(self, steps):
        """執行前一次載入流程引用的全部範本 (ADR 0004).

        缺圖/登錄產物損壞在這裡就報明錯誤、流程不開跑——不讓問題拖到
        跑到一半才炸。每次執行都重掃 (登錄快取有效性由引擎那層把關)。
        """
        extra = list(self.calibration["pair"]) if self.calibration else []
        if self.busy:
            extra.append(self.busy["template"])
        # 流程層級設定 (開頭校準、補做判斷要查) 引用的也是被引用的範本
        names = flow_templates(steps, extra)
        if not names:
            return
        self.log(f"準備範本中…（{len(names)} 張）")
        if self._prerun == "templates":   # 啟動當下就已到期
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
        """預載途中檢查`開始延遲`: 第一次發現已到期就記一行並切到「等待範本」."""
        if self._prerun == "countdown" and time.monotonic() >= self._due:
            self._prerun = "templates"
            self.log("等待準備範本完成")

    # ---------- 開頭`校準` ----------
    def _calibrate(self):
        """用流程的`校準對`量這次的`畫面倍率` (ADR 0009).

        依搜尋範圍截一張圖, 兩張校準圖用**全範圍**查 (不帶預期尺度——倍率差很多
        也量得到); 中心距離 ÷ 基準距離＝倍率, 是這次執行唯一的倍率。沒有校準
        資料、任一張找不到、兩張重疊＝拋錯 (流程一個輸入都不送), 都寫一筆
        `calibrate` 檔案日誌。
        """
        cal = self.calibration
        if cal is None:
            self._log_calibrate(result="no_pair")
            raise RuntimeError("這份流程沒有校準對（舊格式或尚未設定）→ 不執行；"
                               "請先在編輯器設定校準對")
        region = getattr(self, "scan_region", None)
        screen, org = self._grab(region)
        m = calib.measure(self.detector.query, screen, cal["pair"])
        if m.missing:
            self._log_calibrate(
                result="missing", pair=",".join(cal["pair"]),
                missing=",".join(m.missing),
                best=",".join(f"{m.scores[n]:.3f}" for n in m.missing))
            names = "、".join(f"「{n}」（最高分數 {m.scores[n]:.3f}）"
                             for n in m.missing)
            raise RuntimeError(f"開頭校準失敗：畫面上找不到校準圖{names}"
                               " → 不執行；請確認遊戲畫面上看得到校準對")
        centers = ";".join(f"({x + org[0]},{y + org[1]})"
                           for x, y in (m.centers[n] for n in cal["pair"]))
        if m.too_close:
            self._log_calibrate(result="too_close", pair=",".join(cal["pair"]),
                                centers=centers)
            raise RuntimeError("開頭校準失敗：兩張校準圖重疊在同一處，"
                               "不能當比例尺 → 不執行")
        self.scale = m.scale(cal["baseline"])
        self._log_calibrate(result="ok", pair=",".join(cal["pair"]),
                            centers=centers, distance=f"{m.distance:.1f}",
                            baseline=f"{float(cal['baseline']):.1f}",
                            scale=f"{self.scale:.3f}")
        self.log(f"開頭校準：畫面倍率 ×{self.scale:.3f}（距離 {m.distance:.1f}px"
                 f" ÷ 基準 {float(cal['baseline']):.1f}px）", "ok")

    def _log_calibrate(self, **fields):
        self._log_file("calibrate", **fields)

    def _log_file(self, event, **fields):
        """寫一筆檔案日誌 (所有事件共用); 日誌絕不能反過來影響執行."""
        try:
            self.filelog(event, **fields)
        except Exception:
            pass

    # ---------- 原點 ----------
    def _set_origin(self, xy, target=None, box=None, origin=None):
        """更新`原點`並記下它的來源.

        來自找圖時記下找圖目標、它挑中的框、查詢它時用的原點 (限定範圍換算用),
        供`原點的圖離開`重查; 來自座標點擊或拖曳時來源記為 None (非找圖)。
        """
        self._last_click = xy
        self._origin_src = (None if target is None else
                            {"target": target, "box": box, "origin": origin})

    # ---------- 輸入與`補做` ----------
    def _input(self, kind, *args):
        """送出一個輸入 (win.click / drag / press_keys) 並記下時間.

        執行器所有實際送出輸入的地方都經過這裡: 補做間隔從上一次輸入算起。
        """
        getattr(win, kind)(*args)
        self._last_input = time.monotonic()

    def _retry_ready(self, no, screen, org, gate):
        """`補做`的兩道門: 已過`補做間隔`、且畫面上沒有`忙碌指示`.

        忙碌指示只在這裡查 (間隔已滿才查, 一般輸入前不查), 用的是這一輪
        確認輪詢的同一張截圖, 不另外截圖也不讓出舞台。gate 記錄因忙碌延後
        的累計秒數 (busy_since: 這次開始延後的時間; delay: 已結算的總和)。
        """
        now = time.monotonic()
        if (self._last_input is not None
                and now - self._last_input < self.retry_interval - 1e-6):
            return False
        if self.busy is not None:
            f = self._find(no, self.busy, screen, org, self._last_click,
                           kind="忙碌指示")
            if f.picked is not None:
                if gate["busy_since"] is None:
                    gate["busy_since"] = now
                return False
        self._settle_busy(gate, now)
        return True

    @staticmethod
    def _settle_busy(gate, now):
        """把進行中的忙碌延後結算進總和."""
        if gate["busy_since"] is not None:
            gate["delay"] += now - gate["busy_since"]
            gate["busy_since"] = None

    # ---------- 步驟 ----------
    def _abs_origin(self):
        """`絕對座標`的基準＝目前`搜尋範圍`的左上角.

        座標存的是相對範圍的偏移, 所以重新框範圍 (或並行時綁到位置不同的視窗)
        時, 所有絕對座標會自動跟著搬過去, 不必重新拾取。
        """
        if not self.scan_region:
            raise RuntimeError("絕對座標需要「搜尋範圍」當基準，請先框選搜尋範圍")
        return int(self.scan_region[0]), int(self.scan_region[1])

    def _sc(self, v):
        """步驟偏移 ×`畫面倍率`四捨五入為整數像素 (倍率 1 = 恆等).

        只換算偏移量 (找圖偏移、相對/絕對座標、拖曳兩端點); 搜尋範圍與
        原點等執行期螢幕座標本來就是本機量測值, 不換算。
        """
        return flowfmt.scale_px(v, self.scale)

    def _exec_step(self, steps, idx):
        """執行 steps[idx]; 帶入清單與索引讓找圖步驟能現算「下一步」."""
        step = steps[idx]
        no = idx + 1  # 執行紀錄用的 1-based 步驟序號
        t = step.get("type")
        prev, self._prev_type = self._prev_type, t
        if t in POINTER_TYPES:
            return self._exec_pointer(steps, idx)

        if t == "wait":
            ms = int(step.get("ms", 1000))
            self.log(f"[{no}] 等待 {ms} ms")
            if self.stage is not None and prev == "drag":
                # 已知的高風險組合: 拖曳後讓出舞台, 滑鼠離開、視窗失焦,
                # 捲動中的列表回來時可能已位移, 後面的相對座標就會點空
                self.log(f"[{no}] 讓出舞台（上一步是拖曳，畫面可能已位移）", "warn")
            self._wait_yielding(ms / 1000.0)

        elif t == "find_click":
            return self._exec_find(steps, idx)

        elif t == "key":
            keys = step.get("keys", "")
            self._input("press_keys", keys)
            self.log(f"[{no}] 按鍵 {keys}")

        else:
            self.log(f"[{no}] 未知步驟類型: {t}", "warn")

    def _exec_pointer(self, steps, idx):
        """座標點擊 / 拖曳: 換算落點 → 送出 → (有設的話) `生效確認`.

        原點: 沒有確認時送出就更新 (同舊行為); 有確認時**生效後才更新**——補做
        送出的輸入以第一次輸入前的原點計算, 與第一次完全相同。
        """
        step = steps[idx]
        no = idx + 1
        t = step["type"]
        rel = step.get("mode", "abs") == "prev"
        if rel and self._last_click is None:
            self.log(f"[{no}] 相對座標: 尚無原點 → 跳過", "warn")
            return None
        base = self._last_click if rel else self._abs_origin()
        button = step.get("button", "left")
        if t == "click":
            x = base[0] + self._sc(step["x"])
            y = base[1] + self._sc(step["y"])
            clicks = int(step.get("clicks", 1))
            args = (x, y, button, clicks)
            after = (x, y)
            updates = step.get("updateOrigin", True)
            where = (f"（上一步 {int(step['x']):+d},{int(step['y']):+d}）" if rel
                     else f"（範圍內 {int(step['x'])},{int(step['y'])}）")
            text = f"點擊 ({x}, {y}){where} {_btn_name(button)}×{clicks}"
            fields = {"at": f"({x},{y})"}
        else:
            x1, y1 = self._sc(step["x1"]), self._sc(step["y1"])
            x2, y2 = self._sc(step["x2"]), self._sc(step["y2"])
            where = (f"（上一步 {x1:+d},{y1:+d} → {x2:+d},{y2:+d}）" if rel
                     else f"（範圍內 {x1},{y1} → {x2},{y2}）")
            x1, y1, x2, y2 = (base[0] + x1, base[1] + y1,
                              base[0] + x2, base[1] + y2)
            ms = int(step.get("ms", 300))
            hold = int(step.get("holdMs", 0))
            args = (x1, y1, x2, y2, button, ms, hold)
            after = (x2, y2)
            updates = True   # 拖曳終點一律是新原點
            hd = f" 停頓{hold}ms放開" if hold else ""
            text = (f"拖曳 ({x1}, {y1}) → ({x2}, {y2}){where} "
                    f"{_btn_name(button)} {ms}ms{hd}")
            fields = {"from": f"({x1},{y1})", "to": f"({x2},{y2})"}
        before, src = self._last_click, self._origin_src
        mode = effect_confirm(step)
        if mode == "gone" and src is None:
            # `原點的圖離開`判斷不了: 輸入先不送 (送了也確認不了生效與否)
            self.log(f"[{no}] 「原點的圖離開」但原點不是來自找圖（或沒有原點）"
                     "→ 無法執行", "warn")
            self._log_file("input.confirm", step=no, kind=t, mode=mode,
                            result="cannot_run", **fields)
            return self._on_not_found(no, f"[{no}] 原點不是來自找圖，無法確認生效",
                                      step.get("onNotFound", "stop"))
        self._input(t, *args)
        self.log(f"[{no}] {text}")
        if mode == "next" and not confirm_next_connected(steps, idx):
            # 執行期防禦線: 理論上已被執行前檢查擋下, 退化成「不確認」
            self.log(f"[{no}] 「下一步的圖出現」但下一步不是找圖步驟"
                     "→ 以「不確認」執行", "warn")
            mode = "none"
        if mode == "none":
            if updates:
                self._set_origin(after)
            self._log_file("input", step=no, kind=t, **fields)
            return None
        rec = dict(step=no, kind=t, mode=mode, **fields)
        if mode == "gone":
            # `原點的圖離開`: 重查產生原點的找圖目標 (限定範圍以它查詢時的原點換算、
            # 比色照開), 它挑中的框不再有匹配＝生效 (同等待消失的同位置判定)
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
            origin = after if updates else before   # 確認以操作後的原點為準
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
                return f.picked is not None, f
            waiting, done, fail = f"{what}出現", f"{what}已出現", f"未見{what}"
        timeout = float(step.get("timeout", 10))
        self.log(f"[{no}] 等待生效（直到{waiting}）")
        ok, f, polls, inputs, delay = self._await_effect(
            no, timeout, float(step.get("interval", 0.5)), check,
            lambda screen, org: True, lambda: self._input(t, *args))
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
        self._log_file("input.confirm", result="timeout", **rec)
        return self._on_not_found(
            no, f"[{no}] {'點擊' if t == 'click' else '拖曳'}後 {timeout}s 內"
                f"{fail}（送了 {inputs} 次）", step.get("onNotFound", "stop"))

    def _await_effect(self, no, timeout, interval, check, may_retry, resend):
        """`生效確認`的共同迴圈 (找圖點擊、座標點擊、拖曳共用).

        每個輪詢間隔截一張圖, check(screen, org) → (生效與否, 紀錄用的結果);
        沒生效時 may_retry(screen, org) 為真、且過了`補做`的兩道門 (補做間隔、
        忙碌指示) 才 resend() 重送同一個輸入。整段不讓出舞台。
        回傳 (生效與否, 最後一次 check 的結果, 輪詢數, 輸入數, 因忙碌延後秒數)。
        """
        region = getattr(self, "scan_region", None)
        deadline = time.monotonic() + timeout
        inputs, polls = 1, 0
        gate = {"busy_since": None, "delay": 0.0}
        while True:
            self._sleep(interval)   # 先給應用程式反應時間
            self._check_stop()
            screen, org = self._grab(region)
            polls += 1
            ok, last = check(screen, org)
            if ok:
                break
            if may_retry(screen, org) and self._retry_ready(no, screen, org,
                                                            gate):
                resend()
                inputs += 1
            if time.monotonic() >= deadline:
                break
        self._settle_busy(gate, time.monotonic())
        return ok, last, polls, inputs, gate["delay"]

    def _enclosing_end(self, steps, pos):
        """pos 之後第一個未配對的結束標記索引 (= 所屬最內層區段結尾); 無則 None."""
        depth = 0
        for j in range(pos + 1, len(steps)):
            t = steps[j].get("type")
            if t in ("loop_start", "branch_start"):
                depth += 1
            elif t in ("loop_end", "branch_end"):
                if depth > 0:
                    depth -= 1
                    continue
                return j
        return None

    def _break_out(self, pos, steps):
        """從 pos 往外跳出區段, 回傳落腳的步驟索引.

        跳出最內層所屬區段 (區段必定完整巢狀); 跳出重複區段=放棄剩餘次數。
        每個區段結尾可設 `onBreak`：預設 "continue" 停在該區段結尾之後繼續；
        設 "break" 則連外層區段也一起跳出 (例如讓 FOR 內的 IF 找不到時直接
        跳出整個 FOR)。往外跳到不在任何區段時 → 停止流程。
        """
        while True:
            end = self._enclosing_end(steps, pos)
            if end is None:
                raise RuntimeError(f"[{pos + 1}] 跳出後已不在任何區段內 → 停止執行")
            if steps[end].get("type") == "loop_end":
                if self._loop_stack:
                    self._loop_stack.pop()  # 正位於此重複區段內, 棧頂必為它
                self.log(f"[{end + 1}] 跳出重複區段（放棄剩餘次數）", "warn")
            else:
                self.log(f"[{end + 1}] 跳出分岔區段", "warn")
            if steps[end].get("onBreak", "continue") == "break":
                pos = end  # 再往外跳出一層
                continue
            return end + 1

    def _avoid_cursor(self, region):
        """找圖前把滑鼠移到離搜尋範圍最遠的虛擬桌面角落, 消除 hover 反白.

        截圖本身不含游標 (GDI), 但游標停留會讓底下 UI 反白, 干擾比對.
        """
        vs = win.virtual_screen()
        corners = [(vs["x"] + 2, vs["y"] + 2),
                   (vs["x"] + vs["w"] - 3, vs["y"] + 2),
                   (vs["x"] + 2, vs["y"] + vs["h"] - 3),
                   (vs["x"] + vs["w"] - 3, vs["y"] + vs["h"] - 3)]
        if region:
            cx, cy = region[0] + region[2] / 2.0, region[1] + region[3] / 2.0
        else:
            cx, cy = vs["x"] + vs["w"] / 2.0, vs["y"] + vs["h"] / 2.0
        x, y = max(corners, key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)
        if win.cursor_pos() == (x, y):
            return  # 已在角落, 不必再等
        win.move(x, y)
        self._sleep(0.08)  # 等 hover 反白消退與重繪

    def _grab(self, region):
        """找圖用的截圖 (需要時先把游標移開); 回傳 (影像, 左上角螢幕座標)."""
        if self.avoid_hover:
            self._avoid_cursor(region)
        return capture.grab(region)

    def _find(self, no, tgt, screen, org, origin, kind="範本"):
        """執行一個`找圖目標` (經偵測接縫); 範本不存在轉成可讀的執行錯誤."""
        try:
            return findtarget.find(tgt, self.detector, screen, org,
                                   origin=origin, scale=self.scale)
        except KeyError:
            raise RuntimeError(
                f"[{no}] 找不到{kind}圖片: {tgt.get('template', '')}") from None

    def _record(self, no, role, f, result, **extra):
        """一個`找圖目標`的判定結束 → 檔案日誌一筆 `find.target`.

        不逐次輪詢地寫: 呼叫端只在判定結束 (找到、逾時、無法執行) 時呼叫,
        f 是最後一次的結果。實跑回報點錯後, 靠它分辨「點錯哪個」與「沒找到」。
        """
        tgt = f.target
        fields = {
            "step": no, "role": role, "template": tgt.get("template", ""),
            "result": result,
            "limit": findtarget.fmt_box(f.limit) if f.limit else "all",
            "pick": findtarget.pick_text(tgt),
            "color": "on" if tgt.get("colorCheck") else "off",
            "matches": "[" + "; ".join(map(findtarget.fmt_match,
                                           f.matches)) + "]",
        }
        if f.rejected:
            fields["rejected"] = "[" + "; ".join(
                map(findtarget.fmt_match, f.rejected)) + "]"
        if f.picked is not None:
            fields["picked"] = findtarget.fmt_box(f.picked.box)
        if result in ("timeout", "cannot_run"):
            fields["best"] = (f"{f.query.score:.3f}" if f.query is not None
                              else "-")
            fields["failed"] = f.failed
        fields.update(extra)
        self._log_file("find.target", **fields)

    def _exec_branch(self, idx, steps):
        """分岔: 輪詢各分支開頭找圖步驟的找圖目標, 先挑到誰就走誰.

        回傳下一個要執行的步驟索引 (選中分支的開頭, 或分岔結束之後).
        """
        lay = branch_layout(steps, idx)
        if lay is None:
            self.log(f"[{idx + 1}] 分岔標記不成對 → 跳過", "warn")
            return idx + 1
        segs, end = lay
        conds = []
        for s in segs:
            if s >= end or steps[s].get("type") != "find_click":
                self.log(f"[{idx + 1}] 分岔的每個分支開頭必須是找圖步驟 → 跳過分岔", "warn")
                return end + 1
            conds.append(steps[s])

        timeout = max(float(c.get("timeout", 10)) for c in conds)
        interval = min(float(c.get("interval", 0.5)) for c in conds)
        region = getattr(self, "scan_region", None)
        tgts = [findtarget.target(c) for c in conds]
        names = " | ".join(t.get("template") or "?" for t in tgts)
        self.log(f"[{idx + 1}] 分岔: 等待任一張圖出現（{names}）")
        origin = self._last_click
        for k, t in enumerate(tgts):
            if origin is None and findtarget.needs_origin(t):
                self.log(f"[{segs[k] + 1}] 分支條件以原點為基準: 尚無原點 → "
                         "這個分支不成立", "warn")
        deadline = time.monotonic() + timeout
        polls = 0
        last = [findtarget.Found(t, reason="origin") for t in tgts]
        while True:
            self._check_stop()
            screen, org = self._grab(region)
            polls += 1
            for k, t in enumerate(tgts):
                f = last[k] = self._find(segs[k] + 1, t, screen, org, origin)
                if f.picked is not None:
                    self.log(f"[{idx + 1}] 分岔 → 走分支 {k + 1}（{f.template}）", "ok")
                    self._record(segs[k] + 1, "branch", f, "found", polls=polls)
                    return segs[k]  # 主迴圈接著執行該找圖步驟 (立即命中)
            if time.monotonic() >= deadline:
                break
            self._sleep(interval)
        for k, f in enumerate(last):
            self._record(segs[k] + 1, "branch", f,
                         "cannot_run" if f.reason == "origin" else "timeout",
                         polls=polls)
        if any(c.get("onNotFound") == "stop" for c in conds):
            raise RuntimeError(
                f"[{idx + 1}] 分岔逾時 {timeout}s, 沒有任何分支條件成立 → 停止執行")
        self.log(f"[{idx + 1}] 分岔逾時 {timeout}s, 沒有任何分支成立 → 跳過", "warn")
        # 分岔結束設「再往外跳出一層」時, 全逾時跳過也連外層區段一起跳出
        if steps[end].get("onBreak", "continue") == "break":
            return self._break_out(end, steps)
        return end + 1

    def _on_not_found(self, no, msg, on_nf):
        """找圖失敗/點擊未生效的共同處置: 依 onNotFound 停止/跳出/跳過."""
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
        timeout = float(step.get("timeout", 10))
        interval = float(step.get("interval", 0.5))
        region = getattr(self, "scan_region", None)  # 全域搜尋範圍 [x,y,w,h] 或 None
        action = step.get("action", "click")
        do_click = action == "click"
        on_nf = step.get("onNotFound", "skip")
        off = (self._sc(step.get("offsetX", 0)), self._sc(step.get("offsetY", 0)))
        button = step.get("button", "left")
        clicks = int(step.get("clicks", 1))
        # 這一步判定所依據的原點 (本步驟執行前的): 點擊/補做更新原點後, 本步
        # 自己的找圖目標仍以它為準
        origin = self._last_click
        if origin is None and findtarget.needs_origin(tgt):
            # 與`相對座標`同處理: 無法執行 → 跳過 (不走找不到時)
            self.log(f"[{no}] 找圖目標以原點為基準: 尚無原點 → 跳過", "warn")
            self._record(no, "wait_gone" if action == "wait_gone" else "find",
                         findtarget.Found(tgt, reason="origin"), "cannot_run")
            return None

        # ---- 等待消失: 必須先看到圖至少一次, 之後消失才算通過 ----
        # (從未出現不能判定成功: 可能畫面根本沒進到預期狀態)
        # 「消失」＝先前挑中的那個位置不再有匹配; 別處的同款圖不影響
        # `出現等候上限` (appearLimitMs, 預設不設): 這段時間內一次都沒看到＝通過
        # ——等「可能出現、也可能根本不出現」的圖 (忙碌指示), 取代固定等待
        if action == "wait_gone":
            start = time.monotonic()
            deadline = start + timeout
            limit_ms = step.get("appearLimitMs")
            appear_by = start + float(limit_ms) / 1000.0 if limit_ms else None
            tracked = None
            polls = 0
            while True:
                self._check_stop()
                screen, org = self._grab(region)
                polls += 1
                f = self._find(no, tgt, screen, org, origin)
                hit = (f.picked if tracked is None
                       else findtarget.still_there(tracked, f.matches))
                if hit is not None:
                    tracked = hit.box
                    if step.get("updateOrigin", True):
                        # 記錄最後看到的位置 (不點擊也算相對座標原點)
                        cx, cy = hit.center
                        self._set_origin((cx + off[0], cy + off[1]), tgt,
                                         hit.box, origin)
                elif tracked is not None:
                    self.log(f"[{no}] 「{name}」已消失", "ok")
                    self._record(no, "wait_gone", f, "gone", polls=polls,
                                 picked=findtarget.fmt_box(tracked))
                    return None
                elif appear_by is not None and time.monotonic() >= appear_by:
                    self.log(f"[{no}] 「{name}」在出現等候上限 {int(limit_ms)}ms "
                             "內沒出現 → 通過", "ok")
                    self._record(no, "wait_gone", f, "not_appeared", polls=polls)
                    return None
                if time.monotonic() >= deadline:
                    break
                self._sleep(interval)
            if tracked is not None:
                msg = f"[{no}] 逾時 {timeout}s 內「{name}」仍未消失"
                self._record(no, "wait_gone", f, "not_gone", polls=polls,
                             picked=findtarget.fmt_box(tracked))
            else:
                msg = f"[{no}] 逾時 {timeout}s 內「{name}」從未出現"
                self._record(no, "wait_gone", f, "timeout", polls=polls)
            return self._on_not_found(no, msg, on_nf)

        # ---- 找圖階段 (等待出現) ----
        deadline = time.monotonic() + timeout
        best = 0.0
        polls = 0
        while True:
            self._check_stop()
            screen, org = self._grab(region)
            polls += 1
            f = self._find(no, tgt, screen, org, origin)
            if f.query is not None:
                best = max(best, f.query.score)
            if f.picked is not None:
                break
            if time.monotonic() >= deadline:
                break
            self._sleep(interval)

        hit = f.picked
        if hit is None:
            msg = f"[{no}] 逾時 {timeout}s 未找到「{name}」(最高相似度 {best:.3f})"
            if f.reason == "count":
                msg += f"（找到 {len(f.matches)} 個，挑選規則挑不到）"
            self._record(no, "find", f, "timeout", polls=polls)
            return self._on_not_found(no, msg, on_nf)

        cx, cy = hit.center
        sx, sy = cx + off[0], cy + off[1]
        many = f"，共 {len(f.matches)} 個匹配" if len(f.matches) > 1 else ""
        self._record(no, "find", f, "found", polls=polls,
                     **({"click": f"({sx},{sy})"} if do_click else {}))
        if not do_click:
            if step.get("updateOrigin", True):
                # 不點擊也記錄找到的位置 (含偏移), 供相對座標步驟當原點
                self._set_origin((sx, sy), tgt, hit.box, origin)
            self.log(f"[{no}] 找到「{name}」(相似度 {hit.score:.3f}{many}) "
                     f"位置 ({sx}, {sy})", "ok")
            return None

        self._input("click", sx, sy, button, clicks)
        if step.get("updateOrigin", True):
            self._set_origin((sx, sy), tgt, hit.box, origin)
        confirm = step.get("confirm", "none")
        if confirm == "next" and not confirm_next_connected(steps, idx):
            # 執行期防禦線: 理論上已被存檔與執行前檢查擋下, 退化成「不確認」
            self.log(f"[{no}] 「點到下一步的圖出現」但下一步不是找圖步驟"
                     "→ 以「不確認」執行（點一次就走）", "warn")
            confirm = "none"
        if confirm == "none":
            self.log(f"[{no}] 找到「{name}」(相似度 {hit.score:.3f}{many}) → "
                     f"點擊 ({sx}, {sy})", "ok")
            return None
        # ---- 點擊後確認生效階段 ----
        return self._confirm_click(steps, idx, confirm, tgt, origin, hit.box,
                                   off, button, clicks, timeout, interval,
                                   on_nf)

    def _confirm_click(self, steps, idx, mode, tgt, origin, box,
                       off, button, clicks, timeout, interval, on_nf):
        """點擊後重試直到「確認生效」: 目標圖消失(gone)、確認圖出現(appear)
        或下一步的圖出現(next)。

        「目標圖消失」只看被點的那個位置 (box) 還有沒有匹配——畫面別處的同款
        圖不算; 沒生效 (那個位置還在) 就再點它一次; 逾時仍未生效 → 依
        onNotFound 處置。專治「圖找到也點了, 但畫面還在轉場/載入而吃不到點擊」
        的失效。確認圖與下一步各照自己的`找圖目標`判定, 原點用點擊後的;
        next 的確認對象依執行清單位置現算 (下一步的找圖目標, 不記名)。
        origin: 本步驟判定所依據的原點 (點擊前), 重查本步的找圖目標時沿用。
        """
        step = steps[idx]
        no = idx + 1
        name = tgt.get("template", "")
        # 各模式的措辭一次算齊 (等待中/已生效/逾時); 不用字串替換組完成語,
        # 範本名本身含「出現」等字時會被改壞
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
        else:  # appear
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
        # 被點的那個位置 (每輪以最新一次查詢更新); 目標已離開原位＝不補做
        cur = {"box": box, "still": None, "fm": None}

        def check(screen, org):
            fm = cur["fm"] = self._find(no, tgt, screen, org, origin)
            cur["still"] = findtarget.still_there(cur["box"], fm.matches)
            if cur["still"] is not None:
                cur["box"] = cur["still"].box
            if mode == "gone":
                return cur["still"] is None, fm
            fc = self._find(no, ctgt, screen, org, self._last_click, kind=kind)
            return fc.picked is not None, fc

        def resend():
            cx, cy = cur["still"].center
            sx, sy = cx + off[0], cy + off[1]
            self._input("click", sx, sy, button, clicks)
            if step.get("updateOrigin", True):
                self._set_origin((sx, sy), tgt, cur["box"], origin)

        ok, f, polls, n_clicks, delay = self._await_effect(
            no, timeout, interval, check,
            lambda screen, org: cur["still"] is not None, resend)
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
        return self._on_not_found(no, fail, on_nf)


def _btn_name(b):
    return {"left": "左鍵", "right": "右鍵", "middle": "中鍵"}.get(b, b)
