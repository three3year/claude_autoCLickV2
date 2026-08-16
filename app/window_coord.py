"""視窗協調狀態機: modal 堆疊 + 清場還原清單 (純邏輯, 無 Tk).

決策邏輯與 Tk 呼叫完全分離——本模組回答「此刻誰該持有 grab、該還原誰、
以什麼順序、驗證失敗是否重試」; Tk 側 (ui_grab / ui_overlay) 只是薄執行層。
視窗以不透明的可雜湊 id 表示 (執行層放 widget, 測試放字串)。
"""

ROOT = "<root>"  # 堆空時 grab 歸屬主視窗 (執行層解讀為「不設 grab」)


class WindowCoordinator:
    def __init__(self, max_retries=4):
        self.max_retries = max_retries
        self._stack = []      # modal 堆疊, 尾端 = 堆頂
        self._clearing = False
        self._restore = []    # 清場還原清單 [(wid, zoomed)], 依隱藏順序
        self._pending = {}    # 還原中尚未 map 確認的視窗 → 已用重試次數

    # ---------- modal 堆疊 ----------

    def modal_opened(self, wid):
        """開 modal 入堆; 已在堆中則移到堆頂."""
        if wid in self._stack:
            self._stack.remove(wid)
        self._stack.append(wid)

    def modal_closed(self, wid):
        """關 modal 出堆 (含中途關閉非堆頂); 不在堆中則無事."""
        if wid in self._stack:
            self._stack.remove(wid)

    def grab_target(self):
        """此刻誰該持有 grab: 清場中 None (overlay 持有, 堆疊暫停),
        否則堆頂; 堆空時 ROOT (主視窗, 執行層不設 grab)."""
        if self._clearing:
            return None
        return self._stack[-1] if self._stack else ROOT

    def stack_depth(self):
        return len(self._stack)

    # ---------- 清場 ----------

    @property
    def clearing(self):
        return self._clearing

    def clear_entered(self, hidden):
        """清場進場: 記錄本次隱藏的視窗與 zoomed 快照 (依隱藏順序)."""
        self._clearing = True
        self._restore = list(hidden)
        self._pending = {wid: 0 for wid, _z in hidden}

    def restore_plan(self):
        """離場該還原的視窗清單 [(wid, zoomed)], 照隱藏順序."""
        return list(self._restore)

    def window_destroyed(self, wid):
        """視窗已銷毀: 跳過還原、離開堆疊."""
        self._restore = [(w, z) for w, z in self._restore if w != wid]
        self._pending.pop(wid, None)
        self.modal_closed(wid)

    def confirm_restored(self, wid):
        """map 確認: 此視窗已真的畫出來."""
        self._pending.pop(wid, None)

    def restore_timed_out(self, wid):
        """還原逾時: 回傳是否該再試一次 (超過上限即放棄, 不再擋住離場)."""
        n = self._pending.get(wid)
        if n is None or n >= self.max_retries:
            self._pending.pop(wid, None)
            return False
        self._pending[wid] = n + 1
        return True

    def all_restored(self):
        return not self._pending

    def clear_finished(self):
        """清場離場完成: 清空還原狀態, 回傳 grab 該交還給誰 (堆頂/ROOT)."""
        self._clearing = False
        self._restore = []
        self._pending = {}
        return self.grab_target()
