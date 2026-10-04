"""流程執行器: 在背景執行緒依序執行步驟, 支援停止、回圈、即時紀錄.

找圖相關步驟 (find_click / wait_gone / confirm / branch) 的辨識走建構時注入
的偵測器 (detector): `query(範本名, 搜尋區域影像) → QueryResult`——與主體
偵測引擎的 `Engine.query` 同形狀 (found / box / score; box 為搜尋區域內
座標), 範本不存在時丟 KeyError。門檻由引擎的 profile config 決定,
步驟層級沒有 threshold (見 ADR 0002)。
"""
import threading
import time

from . import capture, findtarget, flowfmt, win


class StopRequested(Exception):
    pass


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


def uses_confirm_next(step):
    """步驟是否用了「點到下一步的圖出現」(只有動作為點擊的找圖有意義)."""
    return (step.get("type") == "find_click"
            and step.get("action", "click") == "click"
            and step.get("confirm") == "next")


def flow_templates(steps):
    """`範本預載`名單: 流程引用的全部範本名, 依出現順序去重.

    找圖步驟的範本 + 確認圖 (confirm: "appear", 只有動作為點擊時有意義)。
    「點到下一步的圖出現」引用的是下一步 (必為找圖) 的範本、分岔條件是
    分支開頭的找圖步驟——都已涵蓋在「所有找圖步驟」之中。
    """
    seen = []
    for s in steps:
        if s.get("type") != "find_click":
            continue
        names = [findtarget.template(s)]
        if findtarget.uses_confirm_target(s):
            names.append(findtarget.confirm_template(s))
        for n in names:
            if n and n not in seen:
                seen.append(n)
    return seen


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
    def __init__(self, detector, stage=None):
        self.detector = detector  # 偵測查詢接縫 (見模組 docstring)
        self.stage = stage  # 並行執行時注入; None = 單流程, 完全走原本的路徑
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
        self._last_click = None
        self._step = (0, 0)  # (目前步驟序號, 總步驟數); 0 = 尚未進入步驟
        self._preparing = False  # `範本預載`進行中 (UI 顯示「準備範本中…」)
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
            "preparing": self._preparing,  # `範本預載`中 (round 仍為 0)
            "round": self.round,
            "totalRounds": self.total_rounds,
            "step": self._step[0],
            "stepTotal": self._step[1],
            "loops": list(self._loops),  # 巢狀重複區段進度: [(目前, 總數), ...]
        }

    # ---------- 控制 ----------
    def start(self, steps, run_mode="count", run_count=1, start_delay=3,
              scan_region=None, avoid_hover=False, scale=1.0):
        if self.running:
            raise RuntimeError("已在執行中")
        self._stop.clear()
        self.running = True
        self.round = 0
        self.total_rounds = 0 if run_mode == "infinite" else max(1, int(run_count))
        self.scan_region = scan_region  # 全域搜尋範圍 [x,y,w,h]; 步驟未自設範圍時套用
        self.avoid_hover = avoid_hover  # 找圖截圖前先把滑鼠移開, 避免 hover 反白干擾
        # `畫面倍率`: 步驟偏移換算落點時乘上它 (由校準模組算出, runner 不讀檔);
        # 1 (含未校準代入值) = 恆等換算, 與原路徑等價
        self.scale = float(scale)
        self._last_click = None  # 上一次點擊的螢幕座標, 供相對座標步驟使用
        self._step = (0, 0)
        self._preparing = False
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
            self._preload(steps)  # `範本預載`: 開跑前一次載齊, 失敗不開跑
            if start_delay > 0:
                self.log(f"{start_delay} 秒後開始執行 (按 F12 可隨時停止)")
                self._sleep(start_delay)

            self._take_stage()  # 第一個動作之前先上台
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
            self.running = False

    # ---------- `範本預載` ----------
    def _preload(self, steps):
        """執行前一次載入流程引用的全部範本 (ADR 0004).

        缺圖/登錄產物損壞在這裡就報明錯誤、流程不開跑——不讓問題拖到
        跑到一半才炸。每次執行都重掃 (登錄快取有效性由引擎那層把關)。
        """
        names = flow_templates(steps)
        if not names:
            return
        self._preparing = True
        self.log(f"準備範本中…（{len(names)} 張）")
        try:
            self.detector.preload(names)
        except KeyError as e:
            raise RuntimeError(f"範本預載失敗: 找不到範本圖片: {e.args[0]}"
                               " → 停止執行") from None
        except Exception as e:
            raise RuntimeError(f"範本預載失敗: {e} → 停止執行") from e
        finally:
            self._preparing = False
        self.log("範本就緒", "ok")

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
        if t == "click":
            mode = step.get("mode", "abs")
            x, y = self._sc(step["x"]), self._sc(step["y"])
            desc = ""
            if mode == "prev":
                if self._last_click is None:
                    self.log(f"[{no}] 相對座標: 尚無上一個點擊位置 → 跳過", "warn")
                    return
                x, y = self._last_click[0] + x, self._last_click[1] + y
                desc = f"（上一步 {int(step['x']):+d},{int(step['y']):+d}）"
            else:
                ox, oy = self._abs_origin()
                x, y = ox + x, oy + y
                desc = f"（範圍內 {int(step['x'])},{int(step['y'])}）"
            button = step.get("button", "left")
            clicks = int(step.get("clicks", 1))
            win.click(x, y, button, clicks)
            if step.get("updateOrigin", True):
                self._last_click = (x, y)
            self.log(f"[{no}] 點擊 ({x}, {y}){desc} {_btn_name(button)}×{clicks}")

        elif t == "drag":
            x1, y1 = self._sc(step["x1"]), self._sc(step["y1"])
            x2, y2 = self._sc(step["x2"]), self._sc(step["y2"])
            desc = ""
            if step.get("mode", "abs") == "prev":
                if self._last_click is None:
                    self.log(f"[{no}] 相對座標: 尚無上一個點擊位置 → 跳過", "warn")
                    return
                bx, by = self._last_click
                desc = f"（上一步 {x1:+d},{y1:+d} → {x2:+d},{y2:+d}）"
                x1, y1, x2, y2 = bx + x1, by + y1, bx + x2, by + y2
            else:
                ox, oy = self._abs_origin()
                desc = f"（範圍內 {x1},{y1} → {x2},{y2}）"
                x1, y1, x2, y2 = ox + x1, oy + y1, ox + x2, oy + y2
            button = step.get("button", "left")
            ms = int(step.get("ms", 300))
            hold = int(step.get("holdMs", 0))
            win.drag(x1, y1, x2, y2, button, ms, hold)
            self._last_click = (x2, y2)  # 拖曳終點可當相對座標原點
            hd = f" 停頓{hold}ms放開" if hold else ""
            self.log(f"[{no}] 拖曳 ({x1}, {y1}) → ({x2}, {y2}){desc} {_btn_name(button)} {ms}ms{hd}")

        elif t == "wait":
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
            win.press_keys(keys)
            self.log(f"[{no}] 按鍵 {keys}")

        else:
            self.log(f"[{no}] 未知步驟類型: {t}", "warn")

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

    def _query(self, no, name, screen, kind="範本"):
        """經偵測接縫查詢一次; 範本不存在 (KeyError) 轉成可讀的執行錯誤."""
        try:
            return self.detector.query(name, screen)
        except KeyError:
            raise RuntimeError(f"[{no}] 找不到{kind}圖片: {name}") from None

    @staticmethod
    def _box_center(result):
        """QueryResult.box (搜尋區域內座標) 的中心點."""
        x, y, w, h = result.box
        return x + w // 2, y + h // 2

    def _exec_branch(self, idx, steps):
        """分岔: 輪詢各分支開頭找圖步驟的條件圖, 先找到誰就走誰.

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
        names = " | ".join(findtarget.template(c) or "?" for c in conds)
        self.log(f"[{idx + 1}] 分岔: 等待任一張圖出現（{names}）")
        deadline = time.monotonic() + timeout
        while True:
            self._check_stop()
            if self.avoid_hover:
                self._avoid_cursor(region)
            screen, _ = capture.grab(region)
            for k, c in enumerate(conds):
                r = self._query(idx + 1, findtarget.template(c), screen)
                if r.found:
                    self.log(f"[{idx + 1}] 分岔 → 走分支 {k + 1}（{findtarget.template(c)}）", "ok")
                    return segs[k]  # 主迴圈接著執行該找圖步驟 (立即命中)
            if time.monotonic() >= deadline:
                break
            self._sleep(interval)
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
        name = findtarget.template(step)
        timeout = float(step.get("timeout", 10))
        interval = float(step.get("interval", 0.5))
        region = getattr(self, "scan_region", None)  # 全域搜尋範圍 [x,y,w,h] 或 None
        action = step.get("action", "click")
        do_click = action == "click"
        on_nf = step.get("onNotFound", "skip")
        off = (self._sc(step.get("offsetX", 0)), self._sc(step.get("offsetY", 0)))
        button = step.get("button", "left")
        clicks = int(step.get("clicks", 1))

        # ---- 等待消失: 必須先看到圖至少一次, 之後消失才算通過 ----
        # (從未出現不能判定成功: 可能畫面根本沒進到預期狀態)
        if action == "wait_gone":
            deadline = time.monotonic() + timeout
            seen = False
            while True:
                self._check_stop()
                if self.avoid_hover:
                    self._avoid_cursor(region)
                screen, org = capture.grab(region)
                r = self._query(no, name, screen)
                if r.found:
                    seen = True
                    if step.get("updateOrigin", True):
                        # 記錄最後看到的位置 (不點擊也算相對座標原點)
                        cx, cy = self._box_center(r)
                        self._last_click = (org[0] + cx + off[0],
                                            org[1] + cy + off[1])
                elif seen:
                    self.log(f"[{no}] 「{name}」已消失", "ok")
                    return
                if time.monotonic() >= deadline:
                    break
                self._sleep(interval)
            if seen:
                msg = f"[{no}] 逾時 {timeout}s 內「{name}」仍未消失"
            else:
                msg = f"[{no}] 逾時 {timeout}s 內「{name}」從未出現"
            return self._on_not_found(no, msg, on_nf)

        # ---- 找圖階段 (等待出現) ----
        deadline = time.monotonic() + timeout
        best = 0.0
        pos = score = None
        while True:
            self._check_stop()
            if self.avoid_hover:
                self._avoid_cursor(region)
            screen, origin = capture.grab(region)
            r = self._query(no, name, screen)
            best = max(best, r.score)
            if r.found:
                cx, cy = self._box_center(r)
                pos = (origin[0] + cx + off[0], origin[1] + cy + off[1])
                score = r.score
                break
            if time.monotonic() >= deadline:
                break
            self._sleep(interval)

        if pos is None:
            msg = f"[{no}] 逾時 {timeout}s 未找到「{name}」(最高相似度 {best:.3f})"
            return self._on_not_found(no, msg, on_nf)

        sx, sy = pos
        if not do_click:
            if step.get("updateOrigin", True):
                # 不點擊也記錄找到的位置 (含偏移), 供相對座標步驟當原點
                self._last_click = (sx, sy)
            self.log(f"[{no}] 找到「{name}」(相似度 {score:.3f}) 位置 ({sx}, {sy})", "ok")
            return

        win.click(sx, sy, button, clicks)
        if step.get("updateOrigin", True):
            self._last_click = (sx, sy)
        confirm = step.get("confirm", "none")
        if confirm == "next" and not confirm_next_connected(steps, idx):
            # 執行期防禦線: 理論上已被存檔與執行前檢查擋下, 退化成「不確認」
            self.log(f"[{no}] 「點到下一步的圖出現」但下一步不是找圖步驟"
                     "→ 以「不確認」執行（點一次就走）", "warn")
            confirm = "none"
        if confirm == "none":
            self.log(f"[{no}] 找到「{name}」(相似度 {score:.3f}) → 點擊 ({sx}, {sy})", "ok")
            return
        # ---- 點擊後確認生效階段 ----
        return self._confirm_click(steps, idx, confirm, name, region,
                                   off, button, clicks, timeout, interval, on_nf)

    def _confirm_click(self, steps, idx, mode, name, region,
                       off, button, clicks, timeout, interval, on_nf):
        """點擊後重試直到「確認生效」: 目標圖消失(gone)、確認圖出現(appear)
        或下一步的圖出現(next)。

        沒生效 (目標圖還在) 就再點一次; 逾時仍未生效 → 依 onNotFound 處置。
        專治「圖找到也點了, 但畫面還在轉場/載入而吃不到點擊」的失效。
        next 的確認對象依執行清單位置現算 (下一步的範本圖, 不記名)。
        """
        step = steps[idx]
        no = idx + 1
        # 各模式的措辭一次算齊 (等待中/已生效/逾時); 不用字串替換組完成語,
        # 範本名本身含「出現」等字時會被改壞
        fail = f"[{no}] 點擊「{name}」後 {timeout}s 內未確認生效"
        if mode == "next":
            cname = findtarget.template(steps[idx + 1])
            label = f"下一步的圖「{cname}」出現"
            done = f"下一步的圖「{cname}」已出現"
            kind = "下一步的"
            fail = f"[{no}] 點擊「{name}」後 {timeout}s 內未見下一步的圖「{cname}」"
        elif mode == "gone":
            cname, kind = "", "範本"
            label, done = f"「{name}」消失", f"「{name}」已消失"
        else:  # appear
            cname = findtarget.confirm_template(step)
            kind = "確認"
            label, done = f"確認圖「{cname}」出現", f"確認圖「{cname}」已出現"
        self.log(f"[{no}] 已點擊「{name}」→ 等待生效（直到{label}）")
        deadline = time.monotonic() + timeout
        while True:
            self._sleep(interval)  # 先給應用程式反應時間
            self._check_stop()
            if self.avoid_hover:
                self._avoid_cursor(region)
            screen, origin = capture.grab(region)
            rt = self._query(no, name, screen)
            if mode == "gone":
                if not rt.found:
                    self.log(f"[{no}] 點擊已生效（{done}）", "ok")
                    return
            elif self._query(no, cname, screen, kind=kind).found:  # appear / next
                self.log(f"[{no}] 點擊已生效（{done}）", "ok")
                return
            # 尚未生效 → 目標圖還在就補點一次 (位置以最新一次查詢為準)
            if rt.found:
                cx, cy = self._box_center(rt)
                sx = origin[0] + cx + off[0]
                sy = origin[1] + cy + off[1]
                win.click(sx, sy, button, clicks)
                if step.get("updateOrigin", True):
                    self._last_click = (sx, sy)
            if time.monotonic() >= deadline:
                break
        return self._on_not_found(no, fail, on_nf)


def _btn_name(b):
    return {"left": "左鍵", "right": "右鍵", "middle": "中鍵"}.get(b, b)
