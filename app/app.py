"""AutoClick — 按鍵精靈 (本機桌面版)

核心: 找圖點擊 + 步驟序列自動執行, F12 急停.
辨識走主體偵測引擎 (兩階段: 粗篩＋深度驗證); 匹配門檻是引擎參數 (內建預設＋流程的
`引擎參數覆蓋`, ADR 0015), 步驟層級沒有門檻 (ADR 0002)。

**一份`流程`＝一個資料夾** (ADR 0014): flow.yaml＋templates/＋可重建的 .cache/, 複製
資料夾就搬完整份流程。改動留在記憶體, 按存檔才寫回 (格式規則全在 flowfile)。
"""
import json
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

import apppaths

if getattr(sys, "frozen", False):
    # 打包版: DINOv2 hub 程式碼與權重隨包 (_internal/torch_home), 目標機
    # 免網路免下載; 須在引擎載入驗證模型之前設定
    os.environ.setdefault("TORCH_HOME", os.path.join(sys._MEIPASS, "torch_home"))
else:
    # 原始碼執行時引擎在 repo 的 src/ 下 (未安裝進環境也能啟動)
    sys.path.insert(0, os.path.join(apppaths.REPO_ROOT, "src"))

import applog
import calibration
import enginehub
import flowfile
import recognition
import ui_dialogs
import ui_grab
import ui_overlay
import ui_theme
from automation import (capture, findtarget, flowcheck, flowdefaults, flowfmt, hotkey,
                        imgio, pickcheck, win)
from automation.flowcheck import STEP_LABELS
from automation.runner import (Runner, has_busy_check, confirm_next_connected,
                               origin_source, uses_confirm_next, uses_origin_leaves)
from ui_theme import C, FONT, FONT_MONO

# 步驟標題列的新增鈕 (版面 D): 常用四種一排, 區段收在「區段 ▾」(None＝分隔線)
ADD_CHIPS = (("find_click", "找圖"), ("click", "點擊"), ("drag", "拖曳"), ("wait", "等待"))
SECTION_TYPES = ("repeat_start", "repeat_end", None,
                 "branch_start", "branch_or", "branch_end")
# 新增時直接加入清單的標記步驟 (無需開對話框)
MARKER_TYPES = {"repeat_end", "branch_start", "branch_or", "branch_end"}
# 標記步驟中仍可編輯屬性的 (區段結尾: 設定「找不到跳出到此」的後續動作)
EDITABLE_MARKERS = {"repeat_end", "branch_end"}
# 步驟清單 │ 連線顏色: 依隸屬區塊 (重複=warn, 分岔=info)
GUIDE_COLORS = {"repeat_start": C["warn"], "branch_start": C["info"]}
# 動作標籤［…］的顏色: 一眼區分步驟類型 (重複/分岔標記沿用整列顏色)
LABEL_COLORS = {
    "find_click": C["info"],
    "find": C["info"],
    "wait_gone": C["info"],
    "click": C["accent"],
    "drag": "#A78BFA",
    "wait": C["muted"],
}
# 執行紀錄各等級的文字色 (執行紀錄面板與迷你狀態視窗共用)
LOG_COLORS = {"info": "#CBD5E1", "ok": C["accent"],
              "warn": C["warn"], "error": C["danger"]}

# 主視窗 ⓘ 的說明 (說明文字規則: 只寫使用時才需要的資料)
SCAN_TIP = ("找圖步驟、比對測試、校準都只在這個範圍裡找；沒框＝全螢幕。"
            "框住遊戲視窗（含標題列），找圖較快也不會找到別的視窗")
CAL_TIP = ("執行開頭量畫面倍率與座標基準點的兩張圖：遊戲畫面內、相距夠遠、執行開頭一定"
           "看得到。沒有就不能執行。測試＝用目前畫面量一次，結果寫在執行紀錄")
FALLBACK_TIP = ("校準對被彈窗擋住時改用的兩張圖（例：標題列圖示與關閉鈕）。"
                "設定時校準對也要在畫面上；清除校準對時一起清除")
BUSY_TIP = ("畫面上有它＝遊戲忙碌中：先不補做；勾了忙碌檢查的步驟送出後等它消失。"
            "測試＝照它的找圖設定比對一次")
# 範本面板: 沒被任何步驟或流程設定引用的範本 (存檔時會離開 templates/)
UNREF_MARK = "（未引用）"

# 全域保險絲: 每 FUSE_INTERVAL_MS 檢查一次, 連續 FUSE_TRIP 次
# 「grab 持有者不可見」(且不在清場中) 即自動救回
FUSE_INTERVAL_MS = 1000
FUSE_TRIP = 3


def _pointer_confirm_desc(s):
    """座標點擊/拖曳的`生效確認`摘要 (沒設＝空字串)."""
    mode = s["confirm"]
    what = {"appear": f"確認圖「{findtarget.confirm_template(s) or '?'}」"
                      f"{findtarget.tag_text(findtarget.confirm_target(s))}出現",
            "next": "下一步的圖出現",
            "gone": "原點的圖離開"}.get(mode)
    if what is None:
        return ""
    nf = {"skip": "跳過", "break": "跳出", "stop": "停止"}[s["on_fail"]]
    return f"，做到{what}（逾時{float(s['timeout']):g}s→{nf}）"


def step_desc(s):
    """步驟清單的摘要; 勾了`忙碌檢查`的步驟尾端標〔忙碌檢查〕 (比照〔限定〕等標示)."""
    return _step_body(s) + ("〔忙碌檢查〕" if has_busy_check(s) else "")


def _step_body(s):
    t = s["type"]
    if t == "click":
        x, y = s["click"]
        pos = f"上一步點擊 ({int(x):+d}, {int(y):+d})"
        uo = "，不更新原點" if not s["update_origin"] else ""
        return f"{pos}{uo}{_pointer_confirm_desc(s)}"
    if t in findtarget.FIND_TYPES:
        act = {"find_click": "點擊", "find": "僅等待出現",
               "wait_gone": "等待消失"}[t]
        nf = {"stop": "停止", "break": "跳出", "skip": "跳過"}[s["on_fail"]]
        cfm = {"gone": "，點到消失", "appear": "，點到確認圖出現",
               "next": "，點到下一步的圖出現"}.get(s.get("confirm"), "")
        if s.get("confirm") == "appear":
            cfm += findtarget.tag_text(findtarget.confirm_target(s))
        ox, oy = (int(v) for v in s["offset"])
        off = f"，偏移({ox:+d}, {oy:+d})" if ox or oy else ""
        uo = "，不更新原點" if not s["update_origin"] else ""
        return (f"{findtarget.template(s) or '?'}"
                f"{findtarget.tag_text(findtarget.target(s))} → {act}{off}{cfm}{uo}"
                f"（逾時{float(s['timeout']):g}s→{nf}）")
    if t == "drag":
        (x1, y1), (x2, y2) = s["drag"], s["to"]
        pos = f"上一步 ({int(x1):+d}, {int(y1):+d}) → ({int(x2):+d}, {int(y2):+d})"
        hd = f" 停{float(s['hold']):g}s" if s["hold"] else ""
        return (f"{pos} {float(s['duration']):g}s{hd}"
                f"{_pointer_confirm_desc(s)}")
    if t == "wait":
        return f"{float(s['wait']):g} 秒"
    if t == "repeat_start":
        return f"×{s['repeat']} 次"
    if t == "branch_start":
        return "每個分支以找圖開頭，先找到誰就走誰"
    if t == "branch_or":
        return "── 或 ──"
    if t in ("repeat_end", "branch_end"):
        if s["on_break"] == "break":
            return "跳出到此 → 再往外跳一層"
        return "───────"
    return ""


class RowIcons:
    """Listbox 的列內操作圖示: 顯示在「選取列」右側, 貼齊列內不超出清單框."""

    def __init__(self, lb, icons):
        """icons: [(glyph, tooltip, callback), ...]; callback 收到選取列 index."""
        self.lb = lb
        self.bar = tk.Frame(lb, bg=C["sel"])  # 底色同選取列, 呈 inline 效果
        for glyph, tip, cb in icons:
            w = tk.Label(self.bar, text=glyph, bg=C["sel"], fg=C["muted"],
                         font=("Segoe UI Symbol", 9), cursor="hand2", padx=3, pady=0)
            w.pack(side="left", fill="y")
            w.bind("<Enter>", lambda e, w=w: w.configure(fg=C["text"], bg=ui_theme.HOVER))
            w.bind("<Leave>", lambda e, w=w: w.configure(fg=C["muted"], bg=C["sel"]))
            w.bind("<Button-1>", lambda e, cb=cb: self._run(cb))
            w._tip = tip
        lb.bind("<<ListboxSelect>>", lambda e: self.refresh(), add=True)
        lb.bind("<MouseWheel>", lambda e: lb.after(10, self.refresh), add=True)

    def refresh(self):
        """依目前選取列重新定位; 無選取或列不可見則隱藏. 清單重繪後需呼叫."""
        if getattr(self.lb, "drag_guard", lambda: False)():
            self.bar.place_forget()  # 拖曳排序中不定位 (bbox 強制版面同步會卡)
            return
        sel = self.lb.curselection()
        bb = self.lb.bbox(sel[0]) if sel else None
        if not bb:
            self.bar.place_forget()
            return
        # 以列高裁切, 貼齊該列不超框
        self.bar.place(relx=1.0, x=-3, y=bb[1], anchor="ne", height=bb[3])
        self.bar.lift()

    def _run(self, cb):
        sel = self.lb.curselection()
        if sel:
            cb(sel[0])


class SegListbox(tk.Text):
    """步驟清單: tk.Text 實作的 Listbox 替代品, 每列可分段上色.

    需求: 區塊 │ 連線依隸屬區塊顏色顯示 (Listbox 一列只能單色做不到);
    選取只加背景色, 文字顏色維持原樣.
    僅實作本程式用到的 Listbox 介面 (curselection/selection_set/see/
    nearest/bbox/size), 內容以 clear() + append(segs) 重建.
    """

    def __init__(self, master, **kw):
        super().__init__(master, wrap="none", exportselection=False,
                         state="disabled", cursor="", **kw)
        # 拿掉 Text 類別綁定 (文字游標/內建拖曳選取), 事件只走實例綁定
        self.bindtags((str(self), str(self.winfo_toplevel()), "all"))
        self._n = 0
        self._sel = set()
        self._anchor = 0
        self._color_tags = {}
        self.drag_guard = lambda: False  # 外部拖曳排序中 → 抑制拖曳選取
        self.press_keep = lambda e: False  # 按下時保留多選 (按在把手上整組拖曳)
        self.tag_configure("selbg", background=self.cget("selectbackground"))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        # 類別綁定移除後手動接滾輪 (不 break, RowIcons 的 refresh 也要收到)
        self.bind("<MouseWheel>",
                  lambda e: self.yview_scroll(-(e.delta // 120) * 3, "units"))

    # ---- 內容 ----

    def clear(self):
        self.configure(state="normal")
        tk.Text.delete(self, "1.0", "end")
        self.configure(state="disabled")
        self._n = 0
        self._sel.clear()

    def append(self, segs):
        """加入一列; segs: [(文字, 顏色 | None=預設), ...]."""
        self.configure(state="normal")
        if self._n:
            tk.Text.insert(self, "end", "\n")
        self._insert_segs(segs)
        self.configure(state="disabled")
        self._n += 1

    def load(self, rows):
        """一次重建全部列 (state 只切換一次; 逐列 append 在大量步驟時會卡)."""
        self.configure(state="normal")
        tk.Text.delete(self, "1.0", "end")
        for i, segs in enumerate(rows):
            if i:
                tk.Text.insert(self, "end", "\n")
            self._insert_segs(segs)
        self.configure(state="disabled")
        self._n = len(rows)
        self._sel.clear()

    def _insert_segs(self, segs):
        for text, color in segs:
            tags = ()
            if color:
                tag = self._color_tags.get(color)
                if tag is None:
                    tag = f"c{len(self._color_tags)}"
                    self.tag_configure(tag, foreground=color)
                    self._color_tags[color] = tag
                tags = (tag,)
            tk.Text.insert(self, "end", text, tags)

    # ---- Listbox 相容介面 ----

    def size(self):
        return self._n

    def curselection(self):
        return tuple(sorted(self._sel))

    def selection_set(self, i):
        if 0 <= i < self._n:
            self._sel = {i}
            self._anchor = i
            self._apply_sel()

    def selection_set_rows(self, rows):
        rows = {r for r in rows if 0 <= r < self._n}
        if rows:
            self._sel = rows
            self._anchor = min(rows)
            self._apply_sel()

    def selection_clear(self, *_args):
        self._sel.clear()
        self._apply_sel()

    def nearest(self, y):
        if not self._n:
            return -1
        i = int(self.index(f"@0,{y}").split(".")[0]) - 1
        return max(0, min(i, self._n - 1))

    def bbox(self, i):
        self.update_idletasks()  # dlineinfo 需版面已排定
        info = self.dlineinfo(f"{i + 1}.0")
        return tuple(info[:4]) if info else None

    def see(self, i):
        tk.Text.see(self, f"{i + 1}.0")

    # ---- 選取 ----

    def _apply_sel(self):
        self.tag_remove("selbg", "1.0", "end")
        for i in self._sel:
            # 蓋到換行符, 背景才會延伸到整列寬度
            self.tag_add("selbg", f"{i + 1}.0", f"{i + 2}.0")
        self.event_generate("<<ListboxSelect>>")

    def _press(self, e):
        self.focus_set()  # Delete / Ctrl+C 快捷鍵需要焦點
        if not self._n:
            return
        i = self.nearest(e.y)
        if e.state & 0x0004:  # Ctrl: 切換單列
            (self._sel.discard if i in self._sel else self._sel.add)(i)
            self._anchor = i
        elif e.state & 0x0001:  # Shift: 錨點到點擊列的範圍
            a, b = sorted((self._anchor, i))
            self._sel = set(range(a, b + 1))
        elif i in self._sel and len(self._sel) > 1 and self.press_keep(e):
            self._anchor = i  # 按在已選取列的把手上: 保留多選, 供整組拖曳
        else:
            self._sel = {i}
            self._anchor = i
        self._apply_sel()

    def _motion(self, e):
        if self.drag_guard() or not self._n:
            return
        i = self.nearest(e.y)
        a, b = sorted((self._anchor, i))
        new = set(range(a, b + 1))
        if new != self._sel:
            self._sel = new
            self._apply_sel()


class App:
    # 目前流程的`校準對`與`基準距離` {pair, baseline}; None＝沒有 (不能執行,
    # 也沒有`座標基準點`——需要基準點的拾取會被擋下)
    flow_cal = None
    # 流程層級的`忙碌指示` (找圖目標或 None), ADR 0008; 補做間隔與忙碌出現等候是固定行為
    busy_target = None

    def __init__(self, root):
        self.root = root
        self.steps = []
        self.last_seq = 0
        self.scan_region = None  # 全域搜尋範圍 [x,y,w,h]; None = 全螢幕
        self._mini = None  # 執行中的迷你狀態視窗
        self._region_prev = None  # 搜尋範圍預覽框
        self._root_shown = False  # 主視窗是否已首次顯示 (Map 過)
        self._collapsed = set()  # 已收合的區段起點 (以 step dict 的 id 記錄)
        self._view = []  # 清單列 → steps 索引的映射 (收合時兩者不一致)

        # ---- 引擎: 視窗先開, 引擎於背景執行緒載入 (ADR 0004) ----
        # 「視窗可操作」與「`引擎就緒`」是兩個時間點; 就緒前辨識類操作由
        # engine_gate 提示並拒絕, 狀態轉變由 _poll 在 UI 執行緒觀察處理
        self.hub = enginehub.EngineHub()
        self.detector = self.hub  # runner 偵測查詢接縫 (query) ＝ hub
        self.runner = Runner(self.detector)
        hotkey.start_stop_hotkey(self._on_hotkey)  # F12 (pynput 執行緒)

        # ---- 流程: 本流程的範本 (templates/＋快取) 與 app 不改的流程設定 ----
        # 啟動先是空白新流程 (視窗開好後再讀上次開的流程)
        self.store = flowfile.FlowTemplates.new(apppaths.unsaved_dir())
        self.flow_engine = {}   # 流程的`引擎參數覆蓋` (engine: 段; 沒有編輯 UI, 原樣保留)
        self.dirty = False      # 有沒有還沒存檔的改動
        self._pending_templates = set()  # 已落地、還沒交給引擎的新範本名
        self._rereg_after = None         # 延後重新綁定的 after id
        # 範本清單先綁好 (不需引擎): 範本面板/清單立即可用;
        # 引擎在背景載入, 完成/失敗由 _poll 觀察 hub 狀態
        self.rebind_templates()
        self._engine_state_seen = enginehub.LOADING
        threading.Thread(target=self.hub.load, daemon=True).start()

        self._update_title()
        root.geometry("1120x700")
        root.minsize(900, 560)
        ui_theme.apply(root)

        self._build_menu()
        self._build_toolbar()
        self._build_main()

        self.log_ui("引擎載入中…（就緒前，執行／比對測試等辨識功能暫不可用）")

        self.refresh_templates()
        self.render_steps()
        self._open_last_flow()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        # windowed exe 沒有 stderr, callback 例外預設完全無聲 →
        # 顯示在執行紀錄面板, 出問題時才有線索
        root.report_callback_exception = self._on_callback_error
        ui_theme.disable_transitions(root)  # 截圖前隱藏視窗需立即生效
        # 主視窗隱藏 (截圖/執行) 時同步隱藏搜尋範圍預覽框, 還原/首次顯示時建立;
        # 不能在 __init__ 就建立: 主視窗尚未映射時先開置頂子視窗會干擾其首次顯示
        root.bind("<Unmap>", self._on_root_visibility, add=True)
        root.bind("<Map>", self._on_root_visibility, add=True)
        # 其他程式的視窗變動 (顯示/移動/前景) 時才重新判斷遮蓋, 免定時掃描
        self._cover_pending = False
        self._win_hook = win.watch_window_changes(self._schedule_cover_check)
        self._poll()
        # 全域保險絲: 低頻監控「grab 持有者不可見」, 超過門檻自動救回
        self._fuse_miss = 0
        self.root.after(FUSE_INTERVAL_MS, self._fuse_check)

    # ================= 引擎生命週期 =================

    def engine_gate(self, parent=None):
        """辨識類操作的就緒 gating: 未`引擎就緒`→ modal 提示並拒絕 (ADR 0004).

        回傳 True = 放行。拍板: 一律 modal 對話框, 不排隊、不置灰。
        """
        msg = enginehub.gating_message(self.hub.state)
        if msg is None:
            return True
        messagebox.showwarning("引擎尚未就緒", msg, parent=parent or self.root)
        return False

    # ================= 背景辨識 (`辨識中`, recognize-off-clear) =================
    # 清場只截圖; 校準、找圖、拾取檢查都派到背景辨識入口 (recognition), 視窗還原後在
    # 背景做, 介面照常重繪。圖片類動作 (存檔、開檔、執行、截圖、拾取、比對測試、校準對的
    # 設定與測試) 都登記在它那裡, 辨識中一律反灰。

    @property
    def recognition(self):
        """App 唯一的背景辨識入口 (第一次用到才建)."""
        r = self.__dict__.get("_recognition")
        if r is None:
            r = self.__dict__["_recognition"] = recognition.Recognition(self)
        return r

    def recognize(self, title, work, done, origin=None, job=None):
        """在背景跑 work(), 做完在介面執行緒呼叫 done(結果); origin＝發起的視窗.

        job: 收尾裡接著做的下一段 (同一件辨識, 辨識中不中斷)。已經有一件在辨識中
        (按確定觸發的檢查才可能碰到) 就寫一行略過。回傳 Job 或 None。
        """
        if job is not None:
            return job.chain(work, done)
        if self.recognition.busy:
            self.log_ui(f"{title}略過：上一件辨識還沒做完", "warn")
            return None
        return self.recognition.start(title, work, origin).then(done)

    def _on_hotkey(self):
        """F12 (pynput 執行緒). 急停不經 UI 執行緒 (UI 卡住也停得下);
        只有就緒前的「提示並拒絕」才轉回 UI 執行緒跳 modal."""
        if self.runner.status()["running"] or self.hub.ready:
            self.stop_all()
        else:
            self.root.after(0, self.engine_gate)

    def _on_engine_state(self, state):
        """背景載入結束 (由 _poll 在 UI 執行緒觀察到狀態轉變時呼叫)."""
        if state == enginehub.READY:
            for msg in self.hub.warnings:
                self.log_ui(f"引擎警告: {msg}", "warn")
            if self.hub.coarse_only:
                self.log_ui("驗證模型未載入 → 降級為 coarse-only"
                            "（僅粗篩，精度較低）", "warn")
                messagebox.showwarning(
                    "引擎降級", "驗證模型載入失敗，找圖只跑粗篩（coarse-only），"
                    "精度較低。\n請檢查 torch 與模型權重是否完整。",
                    parent=self.root)
            self.log_ui(f"引擎就緒（本流程 {len(self.store.names())} 個範本）", "ok")
            self.refresh_templates()
        elif state == enginehub.FAILED:
            # 檔案日誌由 hub.load() 落 (engine.load.failed), 這裡只做 UI
            self.log_ui(f"引擎載入失敗: {self.hub.error}", "error")
            messagebox.showerror(
                "引擎載入失敗",
                f"引擎載入失敗，辨識功能無法使用：\n{self.hub.error}",
                parent=self.root)

    # ================= 範本清單與引擎參數 =================

    def engine_config(self):
        """引擎參數＝引擎內建預設 (default_config.yaml)＋流程 engine: 段的覆蓋 (ADR 0015)."""
        from subject_detection.library import load_default_config
        cfg = load_default_config()
        cfg.update(self.flow_engine or {})
        return cfg

    def rebind_templates(self, changed=None):
        """把本流程的範本清單交給引擎 (`範本清單`由 app 組, ADR 0006; 輕量, 不需引擎).

        changed: None＝整份換掉 (換流程), 登錄產物全部失效; 名稱集合＝只有這幾張要
        重新登錄 (新增、重截、改名), 其他沿用記憶體裡的登錄產物 (ADR 0004)。
        """
        self.library = self.hub.bind(self.store.images(), self.engine_config(),
                                     self.store.registered_dir, changed)

    def start_preload(self):
        """讀取流程後在背景做`範本預載` (被引用、有圖的範本; 引擎沒就緒就等就緒).

        換流程時舊的那份由 hub 依世代作廢; 回報經佇列交回 UI 執行緒 (drain_preload)。
        """
        q = self.__dict__.setdefault("_preload_q", queue.Queue())
        names = [n for n in self.referenced_templates() if n in self.library.templates]
        if not names:
            return None
        self._preload_thread = self.hub.start_preload(
            names, lambda gen, event, data: q.put((gen, event, data)))
        return self._preload_thread

    def drain_preload(self):
        """背景預載的回報寫進執行紀錄 (UI 執行緒; 只認目前這份範本清單的)."""
        q = self.__dict__.get("_preload_q")
        while q is not None and not q.empty():
            gen, event, data = q.get_nowait()
            if gen != self.hub.generation:
                continue
            if event == "start":
                self.log_ui(f"開始準備範本（{data} 張）")
            elif event == "bad":
                name, err = data
                self.log_ui(f"範本「{name}」載入失敗：{err}（按執行時會停下並報錯）", "warn")
            elif event == "done":
                self.log_ui("範本就緒", "ok")

    def _mark_dirty(self):
        """有改動還沒存檔 (步驟、範本、校準對、忙碌指示、搜尋範圍、執行輪數)."""
        self._set_dirty(True)

    def _set_dirty(self, dirty):
        """未存檔標記的唯一入口: 改它同時改視窗標題 (`*` 跟著未存檔走)."""
        self.dirty = dirty
        self._update_title()

    def _update_title(self):
        """視窗標題 `[*]<流程名> — AutoClick` (流程名＝資料夾名, 新流程沒存過＝未命名)."""
        self.root.title(f"{'*' if self.dirty else ''}{self.flow_name()} — AutoClick")

    # ================= 流程設定 (校準對、備用校準對、忙碌指示; ui-slim 04) =================
    # 流程層級的設定收在「流程設定…」對話框: 每列＝名稱 ⓘ＋現狀＋設定…／清除／測試;
    # 主視窗第一列只留摘要。設定或清除之後, 對話框的現狀、主視窗摘要、範本面板的未引用
    # 標記一起重畫 (_settings_changed)。

    def _parent(self):
        """提示的 parent: modal 堆疊的堆頂 (例: 從流程設定對話框按的), 沒有就主視窗."""
        return ui_grab.top_window() or self.root

    def _cal_text(self):
        cal = self.flow_cal
        if not cal:
            return "沒有（不能執行）"
        return f"{cal['pair'][0]} × {cal['pair'][1]}（基準 {float(cal['baseline']):.0f} px）"

    def _fb_text(self):
        fb = calibration.fallback_pair(self.flow_cal)
        if not fb:
            return "沒有"
        return f"{fb['pair'][0]} × {fb['pair'][1]}（基準 {float(fb['baseline']):.0f} px）"

    def _busy_text(self):
        return self.busy_target["template"] if self.busy_target else "不設"

    def _settings_summary(self):
        """主視窗第一列的摘要: 這份流程能不能跑 (校準對) 與有沒有忙碌指示."""
        return (f"校準對 {'✓' if self.flow_cal else '✗'}　"
                f"忙碌指示 {'✓' if self.busy_target else '—'}")

    def _settings_changed(self):
        """流程設定改了: 主視窗摘要、開著的流程設定對話框、範本面板的未引用標記都重畫."""
        lbl = getattr(self, "settings_lbl", None)
        if lbl is not None:
            lbl.configure(text=self._settings_summary())
        refresh = getattr(self, "_settings_refresh", None)
        if refresh is not None:
            refresh()
        if getattr(self, "tmpl_list", None) is not None:
            self.refresh_templates()

    def open_flow_settings(self):
        """「流程設定…」: 校準對、備用校準對、忙碌指示三列 (modal); 底部只有「關閉」."""
        dlg = tk.Toplevel(self.root)
        dlg.title("流程設定")
        dlg.configure(bg=C["panel"])
        dlg.resizable(False, False)
        dlg.transient(self.root)
        body = ttk.Frame(dlg, style="Panel.TFrame", padding=16)
        body.pack(fill="both", expand=True)
        rows = (("校準對", CAL_TIP, self._cal_text,
                 self.designate_pair, self.clear_calibration, self.test_calibration),
                ("備用校準對", FALLBACK_TIP, self._fb_text,
                 self.designate_fallback_pair, self.clear_fallback,
                 self.test_fallback_calibration),
                ("忙碌指示", BUSY_TIP, self._busy_text,
                 self.set_busy_indicator, self.clear_busy_indicator,
                 self.test_busy_indicator))
        shown = []
        rec = self.recognition
        for r, (title, tip, text_of, set_fn, clear_fn, test_fn) in enumerate(rows):
            pad = (8 if r else 0, 0)
            cell = ttk.Frame(body, style="Panel.TFrame")
            cell.grid(row=r, column=0, sticky="w", pady=pad)
            ttk.Label(cell, text=title, style="Panel.TLabel").pack(side="left")
            ui_dialogs.info_tip(cell, tip).pack(side="left", padx=(2, 12))
            lbl = ttk.Label(body, style="Muted.TLabel")
            lbl.grid(row=r, column=1, sticky="w", padx=(8, 16), pady=pad)
            shown.append((lbl, text_of))
            for c, (text, fn) in enumerate((("設定…", set_fn), ("清除", clear_fn),
                                            ("測試", test_fn))):
                b = ttk.Button(body, text=text, style="Small.TButton", takefocus=False,
                               command=fn)
                b.grid(row=r, column=2 + c, padx=(0, 4), pady=pad)
                # 圖片類: 校準對兩列的設定與測試 (量測), 忙碌指示的測試 (比對測試)
                if text == "測試" or (text == "設定…" and r < 2):
                    rec.register(b)
        body.columnconfigure(1, minsize=260)

        def refresh():
            for lbl_, text_of_ in shown:
                lbl_.configure(text=text_of_())

        def on_destroy(e):
            if e.widget is dlg:
                self._settings_refresh = None

        refresh()
        self._settings_refresh = refresh
        dlg.bind("<Destroy>", on_destroy, add=True)
        foot = ttk.Frame(dlg, style="Panel.TFrame", padding=(16, 0, 16, 14))
        foot.pack(fill="x")
        close = ttk.Button(foot, text="關閉", command=dlg.destroy)
        close.pack(side="right")
        ui_dialogs.busy_foot(self, dlg, foot, (close,))
        dlg.bind("<Escape>", ui_dialogs.unless_busy(self, dlg, dlg.destroy))
        ui_dialogs._center(dlg, self.root)
        ui_theme.disable_transitions(dlg)   # 測試與設定要清場: 隱藏需立即生效
        ui_dialogs.make_modal(dlg)
        dlg.focus_force()
        self.root.wait_window(dlg)

    # ================= 校準 (`校準對` / `畫面倍率` / `座標基準點`, ADR 0009、0012) =================
    # 校準對與基準距離住在流程存檔裡 (self.flow_cal)。編輯器沒有跨操作保存的倍率或
    # 基準點: 每次拾取都在那張截圖上量 (ui_dialogs.measured_pick, 量測在背景辨識),
    # 拾取到的座標與截下的範本當場換回`流程尺度`、相對基準點。量測純邏輯在 calibration。

    def calibration_names(self, names=None):
        """校準要查的範本名 (預設＝這份流程的校準對, 含備用校準對——主對找不到時
        calibrate() 會改量備用對, 備用對的範本也要先載得起來)."""
        if names is None:
            fb = calibration.fallback_pair(self.flow_cal)
            names = [*self.flow_cal["pair"], *(fb["pair"] if fb else ())]
        return list(dict.fromkeys(names))

    def calibration_ready(self, title, names=None, parent=None):
        """校準量測前的檢查 (清場「之前」、介面執行緒, 清場中彈窗會隱形卡死):
        `引擎就緒`、校準對的範本都在本流程裡. 回傳是否可以量; 不行時已提示.

        登錄產物的載入 (可能要好幾秒) 不在這裡: 派到背景辨識後才做 (`load_problem`),
        載不起來在收尾時提示。
        """
        parent = parent or self._parent()
        if not self.engine_gate(parent):
            return False
        self.ensure_registered()
        for name in self.calibration_names(names):
            if name not in self.library.templates:
                messagebox.showwarning(
                    title, f"找不到校準圖：{name}\n（這張範本已不在本流程裡）",
                    parent=parent)
                return False
        return True

    def templates_known(self, names):
        """(介面執行緒) 這些範本能不能拿來查: 引擎就緒、已在範本清單; 不行就安靜略過
        (拾取檢查用, 不彈 modal、不過 engine_gate)."""
        if not all(names) or not self.hub.ready or self.library is None:
            return False
        self.ensure_registered()
        return all(n in self.library.templates for n in names)

    def load_problem(self, names):
        """(背景) 載入這些範本的登錄產物; 載不起來回傳 (範本名, 例外), 都好回 None."""
        for name in names:
            try:
                self.hub.ensure_template(name)
            except Exception as e:
                return name, e
        return None

    def grab_frame(self):
        """清場「之內」依搜尋範圍截一張圖: 回傳 (影像, 左上角螢幕座標)."""
        self.root.update()
        time.sleep(0.12)
        return capture.grab(self.scan_region)

    def grab_shot(self):
        """清場「之內」截整個虛擬桌面 (影像, 左上角): 覆蓋層直接顯示它, 背景校準裁出
        搜尋範圍那塊來量 (`scan_frame`)——拾取與校準用同一張 (ADR 0012)."""
        self.root.update()
        time.sleep(0.12)
        return capture.grab(None)

    def scan_frame(self, shot):
        """整張截圖裁出搜尋範圍那塊: (影像, 左上角螢幕座標); 沒框搜尋範圍＝整張."""
        img, (ox, oy) = shot
        if not self.scan_region:
            return shot
        x, y, w, h = (int(v) for v in self.scan_region)
        x0, y0 = max(x, ox), max(y, oy)
        x1 = min(x + w, ox + img.shape[1])
        y1 = min(y + h, oy + img.shape[0])
        if x1 <= x0 or y1 <= y0:
            return shot   # 搜尋範圍不在畫面上: 量整張 (量不到會照常提示)
        return img[y0 - oy:y1 - oy, x0 - ox:x1 - ox].copy(), (x0, y0)

    def _warn_measure(self, title, m):
        """量不到 (Measurement / Calibrated) 時的提示."""
        messagebox.showwarning(
            title, m.describe() + "\n請切換到兩張圖同時出現的畫面、搜尋範圍要框住"
            "它們，再重試（原本的設定維持不動）", parent=self._parent())

    def _warn_load(self, title, problem):
        name, e = problem
        messagebox.showwarning(title, f"校準圖載入失敗：{name}（{e}）",
                               parent=self._parent())

    def _grab_measure_work(self, names, measure):
        """流程設定的量測入口共同骨架: 清場只截搜尋範圍 (現在就截), 回傳背景要跑的 work——
        載入校準圖的登錄產物並 measure(畫面, 左上角), 結果＝(載入問題, 量測結果)."""
        with ui_overlay.screen_clear(self.root):
            screen, org = self.grab_frame()

        def work():
            problem = self.load_problem(names)
            return problem, (None if problem else measure(screen, org))
        return work

    def designate_pair(self):
        """設定 (或更換) 這份流程的`校準對` (ADR 0009、0012).

        還沒有校準對: 當下的畫面就是`流程尺度` (倍率 1), 量到的距離＝基準距離,
        第一張的中心就是座標基準點 (之後可以開始拾取)。
        已有校準對: 先用舊的那對量出倍率與舊基準點, 新的基準距離＝新距離 ÷ 倍率
        (換對不改變流程尺度); 所有存下的座標 (固定矩形、範本拍攝位置) 依
        新舊兩個基準點的差 (換回流程尺度) 一次平移, 每個落點都不變。舊對量不到就
        拒絕 (不知道差多少就換基準, 整份流程會點偏)。兩對在同一張截圖上量。
        任何一步失敗都不改動原本的校準資料與座標。清場只截圖, 量測在背景 (`辨識中`),
        改流程資料的部分在介面執行緒的收尾。
        """
        if self.recognition.busy or not self.engine_gate(self._parent()):
            return
        pair = ui_dialogs.pick_cal_pair(self)
        if not pair:
            return
        title = "設定校準對"
        old = self.flow_cal
        fb = calibration.fallback_pair(old)
        if fb and set(pair) == set(fb["pair"]):
            messagebox.showwarning(title, "新的校準對與備用校準對相同；"
                                   "請挑別的兩張，或先改備用對", parent=self._parent())
            return
        names = [*pair, *(old["pair"] if old else ())]
        if not self.calibration_ready(title, names):
            return
        query = self.detector.query

        def measure(screen, org):
            c = None
            if old:
                # 只用舊主對量 (不退備用對: 換對要知道舊基準點在哪)
                c = calibration.calibrate(query, screen, org,
                                          calibration.make(old["pair"], old["baseline"]))
                if not c.ok:
                    return c, None
            return c, calibration.measure(query, screen, list(pair), org)

        def done(res):
            problem, got = res
            if problem:
                self._warn_load(title, problem)
                return
            c, m = got
            if c is not None and not c.ok:
                self._warn_measure("設定校準對（先用原本的校準對量倍率與基準點）", c)
                return
            if not m.ok:
                self._warn_measure(title, m)
                return
            if self.flow_cal is not old:
                self.log_ui(f"{title}：量測中校準資料被改過，這次的結果不套用", "warn")
                return
            self._apply_pair(pair, old, fb, c, m)

        self.recognize(title, self._grab_measure_work(names, measure), done,
                       origin=self._parent())

    def _apply_pair(self, pair, old, fb, c, m):
        """設定校準對的收尾 (介面執行緒): 換校準資料、平移存下的座標、寫紀錄."""
        k, old_anchor = (c.scale, c.anchor) if c is not None else (1.0, None)
        self.flow_cal = calibration.make(pair, m.distance / k)
        moved = 0
        if old_anchor is not None:
            # 存下的座標全部改成相對新基準點 (每個落點照舊)
            moved = (flowfmt.shift_flow(self._ref_data(), old_anchor, m.anchor, k)
                     + self.store.shift_pos(old_anchor, m.anchor, k))
            if fb:
                # 備用對的偏移跟著重算: 備用第一張的中心不動, 指向新基準點
                fb_first = calibration.fallback_first(old_anchor, fb["offset"], k)
                self.flow_cal[calibration.FALLBACK_KEY] = calibration.make_fallback(
                    fb["pair"], fb["baseline"],
                    calibration.fallback_offset(m.anchor, fb_first, k))
        self._mark_dirty()
        self._settings_changed()
        self.render_steps()
        self.log_ui(f"已設定校準對「{pair[0]}」×「{pair[1]}」，"
                    f"基準距離 {m.distance / k:.1f}px（目前畫面倍率 ×{k:.3f}）；"
                    f"座標基準點 {tuple(m.anchor)}", "ok")
        if old_anchor is not None:
            self.log_ui(f"基準點從 {tuple(old_anchor)} 換到 {tuple(m.anchor)}，"
                        f"已換算 {moved} 個存下的座標（固定矩形、範本拍攝位置），"
                        "落點不變（捨入誤差內）"
                        + ("；備用校準對的偏移已跟著重算" if fb else ""), "ok")

    def designate_fallback_pair(self):
        """設定 (或更換) 這份流程的`備用校準對` (ADR 0013).

        要先有校準對 (主對)。沿用挑兩張的對話框; 按確定時在當下畫面同時量主對與備用對:
        主對找不到就拒絕 (沒有基準點可對齊); 量到的備用距離 ÷ 當下倍率＝它的基準距離,
        (主基準點 − 備用第一張中心) ÷ 倍率＝偏移 (流程尺度)。存進流程 (存檔時寫進 flow.yaml)。
        清場只截圖, 量測在背景。
        """
        if self.recognition.busy or not self.engine_gate(self._parent()):
            return
        title = "設定備用校準對"
        main = self.flow_cal
        if main is None:
            messagebox.showinfo(title, "請先設定校準對，"
                                "備用對才有可對齊的座標基準點", parent=self._parent())
            return
        pair = ui_dialogs.pick_cal_pair(self, fallback=True)
        if not pair:
            return
        if set(pair) == set(main["pair"]):
            messagebox.showwarning(title, "備用校準對不能與校準對相同；"
                                   "備用對是主對被擋住時用的另外兩張圖",
                                   parent=self._parent())
            return
        names = [*pair, *main["pair"]]
        if not self.calibration_ready(title, names):
            return
        query = self.detector.query

        def measure(screen, org):
            c = calibration.calibrate(query, screen, org,
                                      calibration.make(main["pair"], main["baseline"]))
            if not c.ok:
                return c, None
            return c, calibration.measure(query, screen, list(pair), org)

        def done(res):
            problem, got = res
            if problem:
                self._warn_load(title, problem)
                return
            c, m = got
            if not c.ok:
                self._warn_measure("設定備用校準對（先用校準對量倍率與基準點）", c)
                return
            if not m.ok:
                self._warn_measure(title, m)
                return
            if self.flow_cal is not main:
                self.log_ui(f"{title}：量測中校準資料被改過，這次的結果不套用", "warn")
                return
            k = c.scale
            fb = calibration.make_fallback(pair, m.distance / k,
                                           calibration.fallback_offset(c.anchor, m.anchor, k))
            self.flow_cal = dict(main, **{calibration.FALLBACK_KEY: fb})
            self._mark_dirty()
            self._settings_changed()
            self.log_ui(f"已設定備用校準對「{pair[0]}」×「{pair[1]}」，基準距離 "
                        f"{fb['baseline']:.1f}px，對座標基準點的偏移 "
                        f"({fb['offset'][0]:+d},{fb['offset'][1]:+d})（目前畫面倍率 ×{k:.3f}）；"
                        "主校準對找不到時執行會改用它", "ok")

        self.recognize(title, self._grab_measure_work(names, measure), done,
                       origin=self._parent())

    def clear_calibration(self):
        """清除校準對＝整份校準資料清空 (備用對依附主對的基準點, 一起清; 有備用時先確認)."""
        cal = self.flow_cal
        if cal is None:
            self.log_ui("校準對還沒設定，沒有可清除的", "info")
            return
        fb = calibration.fallback_pair(cal)
        stored = self._stored_coords()
        if (fb or stored) and not messagebox.askyesno("清除校準對", "\n".join(filter(None, (
                "備用校準對依附校準對的座標基準點，會一起清除。" if fb else "",
                f"已存的 {stored} 個座標（固定矩形、範本拍攝位置）相對現在的基準點；"
                "清除後再設定的校準對會從新的基準點與尺度起算，這些座標不會跟著換算"
                "（要換校準對請直接按「設定…」，座標會自動平移）。" if stored else "",
                "要清除嗎？"))), parent=self._parent()):
            return
        self.flow_cal = None
        self._mark_dirty()
        self._settings_changed()
        self.log_ui("已清除校準對" + ("與備用校準對" if fb else "")
                    + "（沒有校準對不能執行）", "warn")

    def _stored_coords(self):
        """相對座標基準點存下的座標數 (固定矩形＋範本拍攝位置; 清除校準對前提醒用)."""
        tgts = [t for s in self.steps for _key, t in findtarget.step_targets(s)]
        tgts += [self.busy_target] if self.busy_target else []
        return (sum(1 for t in tgts if t.get("within") is not None)
                + len(self.store.pos()))

    def clear_fallback(self):
        """清除備用校準對 (主校準對不動)."""
        cal = self.flow_cal
        if calibration.fallback_pair(cal) is None:
            self.log_ui("備用校準對還沒設定，沒有可清除的", "info")
            return
        self.flow_cal = {k: v for k, v in cal.items() if k != calibration.FALLBACK_KEY}
        self._mark_dirty()
        self._settings_changed()
        self.log_ui("已清除備用校準對（主校準對找不到時不再改量備用對）", "ok")

    def test_calibration(self):
        """校準對的「測試」: 用這份流程的校準對在目前畫面量一次, 結果寫進執行紀錄.

        只是顯示, 不影響任何存下的值——拾取與執行時各自重量 (ADR 0012); 量到`支援倍率
        範圍`外只警告 (ADR 0013 決策 1)。清場只截圖, 量測在背景 (`辨識中`)。
        """
        title = "測試校準對"
        if self.recognition.busy:
            return
        if self.flow_cal is None:
            self.log_ui(f"{title}：校準對還沒設定", "warn")
            return
        if not self.calibration_ready(title):
            return
        cal, query = self.flow_cal, self.detector.query

        def done(res):
            problem, c = res
            if problem:
                self._warn_load(title, problem)
                return
            if not c.ok:
                self.log_ui(f"{title}：{c.describe()}（搜尋範圍要框住校準對兩張圖）", "warn")
                return
            m = c.measurement
            which = ("用備用校準對量（主對缺「" + "」「".join(c.main.missing) + "」）"
                     if c.used == "fallback" else "用校準對量")
            self.log_ui(f"{title}：目前畫面倍率 ×{c.scale:.3f}"
                        f"（距離 {m.distance:.1f}px ÷ 基準 {c.baseline:.1f}px，{which}）、"
                        f"座標基準點 {tuple(c.anchor)}；只是顯示，拾取時會各自重量", "ok")
            if not c.in_range:   # 只警告不擋 (ADR 0013 決策 1)
                self.log_ui(f"{title}：{ui_dialogs.out_of_range_warning(c.scale)}", "warn")

        work = self._grab_measure_work(self.calibration_names(),
                                 lambda screen, org: calibration.calibrate(
                                     query, screen, org, cal))
        self.recognize(title, work, done, origin=self._parent())

    def test_fallback_calibration(self):
        """備用校準對的「測試」: 只用備用對量 (主對看得到時也一樣), 結果寫進執行紀錄."""
        title = "測試備用校準對"
        if self.recognition.busy:
            return
        fb = calibration.fallback_pair(self.flow_cal)
        if fb is None:
            self.log_ui(f"{title}：備用校準對還沒設定", "warn")
            return
        if not self.calibration_ready(title, fb["pair"]):
            return
        cal, query = self.flow_cal, self.detector.query

        def done(res):
            problem, got = res
            if problem:
                self._warn_load(title, problem)
                return
            m, k, anchor = got
            if not m.ok:
                self.log_ui(f"{title}：{m.describe()}", "warn")
                return
            self.log_ui(f"{title}：畫面倍率 ×{k:.3f}（距離 {m.distance:.1f}px ÷ 基準 "
                        f"{float(fb['baseline']):.1f}px）、座標基準點 {tuple(anchor)}；"
                        "只是顯示", "ok")
            if not calibration.in_supported_range(k):
                self.log_ui(f"{title}：{ui_dialogs.out_of_range_warning(k)}", "warn")

        work = self._grab_measure_work(list(fb["pair"]),
                                 lambda screen, org: calibration.measure_fallback(
                                     query, screen, org, cal))
        self.recognize(title, work, done, origin=self._parent())

    # ================= `忙碌指示` (ADR 0008、0011) =================

    def set_busy_indicator(self):
        """設定 (或重新設定)`忙碌指示`: 選範本 (同一個選範本對話框) → 找圖設定.

        限定範圍由作者在找圖設定裡框`固定矩形` (指示字樣在畫面底部中央)。清除是流程設定
        對話框裡另一顆鈕。這次加進來最後沒用到的圖收回。
        """
        cur = self.busy_target
        before = set(self.list_template_names())
        name = ui_dialogs.pick_template(
            self, "選擇忙碌指示", initial=(cur or {}).get("template"))
        added = [n for n in self.list_template_names() if n not in before]
        if name:
            base = (cur if cur and cur["template"] == name
                    else {"template": name})

            def test(o, parent):
                ui_dialogs.show_match_test(
                    self, findtarget.make_target(name, **o), hide=(parent,))

            opts = ui_dialogs.edit_target_opts(
                self, self._parent(), base, "忙碌指示的找圖設定", test_fn=test)
            tgt = findtarget.make_target(name, **opts) if opts else None
            if tgt is not None and findtarget.needs_origin(tgt):
                # 補做前才查、那時的原點不固定: 不能挑「最接近指定點」
                messagebox.showwarning(
                    "忙碌指示", "忙碌指示的指定點不能以原點為基準（補做前才查，"
                    "那時的原點不固定），請改用其他挑選規則", parent=self._parent())
            elif tgt is not None:
                self.busy_target = tgt
                self._mark_dirty()
                self.log_ui(f"已設定忙碌指示「{name}」：畫面上有它時先不補做，"
                            "勾了忙碌檢查的步驟送出後會等它消失", "ok")
        ui_dialogs.discard_unused(self, added, None)
        self._settings_changed()

    def clear_busy_indicator(self):
        """清除忙碌指示＝不設 (補做只看補做間隔)."""
        if self.busy_target is None:
            self.log_ui("忙碌指示還沒設定，沒有可清除的", "info")
            return
        self.busy_target = None
        self._mark_dirty()
        self._settings_changed()
        self.log_ui("已清除忙碌指示（補做只看補做間隔）", "ok")

    def test_busy_indicator(self):
        """忙碌指示的「測試」: 照它的找圖目標比對測試 (標註預覽＋拾取檢查)."""
        if self.busy_target is None:
            self.log_ui("測試忙碌指示：忙碌指示還沒設定", "warn")
            return
        ui_dialogs.show_match_test(self, self.busy_target)

    # ================= UI 建構 =================

    def _build_menu(self):
        # 存檔/開檔走步驟面板按鈕與快速鍵 (沒有選單列); 辨識中跟按鈕一樣不理
        self.root.bind("<Control-s>", lambda e: self.recognition.busy or self.save_flow())
        self.root.bind("<Control-o>", lambda e: self.recognition.busy or self.open_flow())

    def _build_toolbar(self):
        """兩列工具列 (版面 D, ui-slim): 第一列流程檔＋搜尋範圍 …… 流程設定摘要;
        第二列執行設定＋大字狀態＋開始/停止 …… F12. 沒有另外的狀態列."""
        bar = ttk.Frame(self.root, padding=(12, 8, 12, 4))
        bar.pack(fill="x")
        rec = self.recognition
        for text, cmd in (("新流程", self.new_flow), ("開檔", self.open_flow),
                          ("存檔", self.save_flow)):
            b = ttk.Button(bar, text=text, style="Small.TButton", takefocus=False,
                           command=cmd)
            b.pack(side="left", padx=(0, 4))
            rec.register(b)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Label(bar, text="搜尋範圍").pack(side="left")
        ui_dialogs.info_tip(bar, SCAN_TIP, bg=C["bg"]).pack(side="left", padx=(2, 0))
        self.scan_lbl = ttk.Label(bar, text="全螢幕", foreground=C["muted"])
        self.scan_lbl.pack(side="left", padx=(6, 8))
        b = ttk.Button(bar, text="框選", style="Small.TButton", takefocus=False,
                       command=self.pick_scan_region)
        b.pack(side="left", padx=(0, 4))
        rec.register(b)
        ttk.Button(bar, text="清除", style="Small.TButton", takefocus=False,
                   command=self.clear_scan_region).pack(side="left")
        # 流程層級的設定 (校準對、備用校準對、忙碌指示) 收在對話框, 這裡只放摘要
        ttk.Button(bar, text="流程設定…", style="Small.TButton", takefocus=False,
                   command=self.open_flow_settings).pack(side="right")
        self.settings_lbl = ttk.Label(bar, text=self._settings_summary(),
                                      foreground=C["muted"])
        self.settings_lbl.pack(side="right", padx=(0, 8))

        bar2 = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        bar2.pack(fill="x")
        ttk.Label(bar2, text="F12 = 急停", foreground=C["muted"]).pack(side="right")
        ttk.Label(bar2, text="模式").pack(side="left")
        self.run_mode = ttk.Combobox(bar2, width=8, state="readonly",
                                     values=["執行次數", "直到停止"])
        self.run_mode.set("執行次數")
        self.run_mode.pack(side="left", padx=(4, 10))
        self.run_mode.bind("<<ComboboxSelected>>", lambda e: self._on_run_setting())
        self.count_lbl = ttk.Label(bar2, text="次數")
        self.count_lbl.pack(side="left")
        self.run_count = ttk.Spinbox(bar2, from_=1, to=99999, width=6)
        self.run_count.set(1)
        self.run_count.pack(side="left", padx=(4, 14))
        self.run_count.configure(command=self._on_run_setting)
        self.run_count.bind("<KeyRelease>", lambda e: self._on_run_setting(), add=True)
        self._run_seen = self._run_value()   # 上次看到的執行輪數 (值變了才算改動)
        # 大字狀態: 遠遠瞄一眼就知道在做什麼 (文字由 _poll 更新)
        self.status_lbl = ttk.Label(bar2, text="待機", style="Status.TLabel",
                                    font=(FONT[0], 13, "bold"))
        self.status_lbl.pack(side="left", padx=(0, 14))
        self.btn_run = ttk.Button(bar2, text="▶ 開始執行", style="Run.TButton",
                                  command=self.start_run)
        self.btn_run.pack(side="left", padx=(0, 6))
        rec.register(self.btn_run)
        rec.register_window(self.root, self.status_lbl)   # 主視窗發起的: 狀態列顯示辨識中
        self.btn_stop = ttk.Button(bar2, text="■ 停止", style="Stop.TButton",
                                   command=self.stop_all, state="disabled")
        self.btn_stop.pack(side="left")

    def _mode_ui(self):
        state = "normal" if self.run_mode.get() == "執行次數" else "disabled"
        self.run_count.configure(state=state)

    def _on_run_setting(self):
        """執行輪數的元件動過 (模式下拉、次數欄的上下鈕/滾輪/打字).

        值真的變了才算改動: 次數欄有焦點時放開任何鍵 (Alt+Tab 的 Alt)、
        在 1 往下滾也會來到這裡, 值沒變不標成未存檔。
        """
        self._mode_ui()
        run = self._run_value()
        if run != self._run_seen:
            self._run_seen = run
            self._mark_dirty()

    def pick_scan_region(self):
        if self.recognition.busy:
            return
        r = ui_overlay.pick(self.root, "region", "拖曳框選搜尋範圍（執行時只在此範圍內找圖）")
        if r:
            self.set_scan_region([r["screenX"], r["screenY"], r["w"], r["h"]])
        else:
            self._update_region_preview()

    def clear_scan_region(self):
        self.set_scan_region(None)

    def set_scan_region(self, region):
        if region != self.scan_region:
            self._mark_dirty()
        self.scan_region = region
        if region:
            self.scan_lbl.configure(text=f"限定 {tuple(region)}",
                                    foreground=C["accent"])
        else:
            self.scan_lbl.configure(text="全螢幕", foreground=C["muted"])
        self._update_region_preview()

    # ---- 搜尋範圍預覽框: 未執行時在螢幕上標示目前框選範圍 ----

    def _on_root_visibility(self, e):
        if e.widget is self.root:
            self._root_shown = True
            self._update_region_preview()

    def _schedule_cover_check(self):
        """視窗事件的去抖: 短時間大量事件 (拖曳視窗) 只觸發一次檢查."""
        if self._cover_pending:
            return
        self._cover_pending = True

        def check():
            self._cover_pending = False
            self._update_region_preview()

        try:
            self.root.after(100, check)
        except tk.TclError:
            pass

    def _update_region_preview(self):
        # _root_shown: 預覽框只能在主視窗首次 Map 之後建立;
        # __init__ 過程中 winfo_viewable 可能已為真, 提前開置頂子視窗會干擾主視窗開啟
        show = (self.scan_region is not None
                and self._root_shown
                and self.root.winfo_viewable()
                and not self.runner.status()["running"]
                and not win.is_window_covered(self.root.winfo_id()))
        if show:
            self._show_region_preview()
        else:
            self._hide_region_preview()

    def _show_region_preview(self):
        if (self._region_prev is not None
                and getattr(self._region_prev, "_region", None) == self.scan_region):
            return  # 範圍沒變就不重建, 避免 Map 事件重複觸發造成閃爍
        # 建立新 Toplevel 會把 modal 對話框既有的 grab 打掉, 建完交還堆頂
        self._hide_region_preview()
        x, y, w, h = self.scan_region
        b = 3  # 框線畫在範圍外側, 才不會被拍進搜尋範圍的截圖
        p = tk.Toplevel(self.root)
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.configure(bg="#2080F0")
        hole = tk.Frame(p, bg="#010203")
        hole.place(x=b, y=b, width=w, height=h)
        p.geometry(f"{w + 2 * b}x{h + 2 * b}+{x - b}+{y - b}")
        p.attributes("-transparentcolor", "#010203")  # 內部鏤空
        ui_theme.disable_transitions(p)  # 截圖前隱藏需立即生效
        p.update_idletasks()
        win.make_click_through(p.winfo_id())  # 不擋滑鼠操作
        p._region = list(self.scan_region)
        self._region_prev = p
        ui_grab.apply_grab("region-preview")

    def _hide_region_preview(self):
        if self._region_prev is not None:
            try:
                self._region_prev.destroy()
            except tk.TclError:
                pass
            self._region_prev = None

    def _build_main(self):
        """主區兩欄 (版面 D): 左＝執行步驟; 右上＝本流程的範本, 右下＝執行紀錄."""
        main = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=5)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=3)
        main.rowconfigure(1, weight=2)
        self._build_steps(main)
        self._build_templates(main)
        self._build_log(main)

    def _popup_button(self, master, text, types):
        """按下彈出選單的小鈕 (選單是它的子元件); types 依序加入, None＝分隔線."""
        btn = ttk.Button(master, text=text, style="Small.TButton", takefocus=False)
        menu = tk.Menu(btn, tearoff=0, bg=C["panel"], fg=C["text"],
                       activebackground=C["sel"], activeforeground=C["text"],
                       bd=0, font=FONT)
        for t in types:
            if t is None:
                menu.add_separator()
            else:
                menu.add_command(label=STEP_LABELS[t],
                                 command=lambda t=t: self.add_step(t))
        btn.configure(command=lambda: menu.tk_popup(
            btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height()))
        return btn

    def _build_steps(self, main):
        left = ttk.Frame(main, style="Panel.TFrame", padding=10)
        left.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 10))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        head = ttk.Frame(left, style="Panel.TFrame")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(head, text="執行步驟", style="Title.TLabel").pack(side="left")
        b = ttk.Button(head, text="測試選取", style="Small.TButton", takefocus=False,
                       command=self.test_selected_steps)
        b.pack(side="left", padx=(10, 0))
        self.recognition.register(b)
        # 新增步驟: 寬度夠＝常用四種一排鈕＋「區段 ▾」; 不夠＝整排收成「＋ 新增 ▾」列出全部九項
        chips = ttk.Frame(head, style="Panel.TFrame")
        for t, text in ADD_CHIPS:
            ttk.Button(chips, text=text, style="Small.TButton", takefocus=False,
                       command=lambda t=t: self.add_step(t)).pack(side="left", padx=(0, 4))
        self._popup_button(chips, "區段 ▾", SECTION_TYPES).pack(side="left")
        compact = self._popup_button(head, "＋ 新增 ▾",
                                     [t for t, _ in ADD_CHIPS] + [None, *SECTION_TYPES])

        def pad(w):
            px = w.pack_info().get("padx", 0)
            return sum(map(int, px)) if isinstance(px, (tuple, list)) else 2 * int(px)

        def fit(_e=None):
            used = sum(w.winfo_reqwidth() + pad(w) for w in head.pack_slaves()
                       if w not in (chips, compact)) + 20
            want = (chips if head.winfo_width() - used >= chips.winfo_reqwidth()
                    else compact)
            other = compact if want is chips else chips
            if other.winfo_manager():
                other.pack_forget()
            if not want.winfo_manager():
                want.pack(side="right")
        head.bind("<Configure>", fit, add=True)

        self.step_list = SegListbox(
            left, bg=C["bg"], fg=C["text"], selectbackground=C["sel"],
            font=FONT, bd=0,
            highlightthickness=1, highlightbackground=C["border"],
            highlightcolor=C["accent"])  # 支援 Ctrl/Shift 多選
        self.step_list.drag_guard = (
            lambda: getattr(self, "_drag_idxs", None) is not None)
        self.step_list.press_keep = self._on_handle
        self.step_list.grid(row=1, column=0, sticky="nsew")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.step_list.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.step_list.configure(yscrollcommand=sb.set)
        self.step_list.bind("<Double-Button-1>", self._on_step_double)
        self.step_list.bind("<Delete>", lambda e: self.del_step())
        self.step_list.bind("<Control-c>", lambda e: (self.copy_steps(), "break")[1])
        self.step_list.bind("<Control-v>", lambda e: (self.paste_steps(), "break")[1])

        # 選取列只有 ✎ ✕ (排序靠 ☰ 把手拖曳、複製靠 Ctrl+C/V)
        self._step_icons = RowIcons(self.step_list, [
            ("✎", "編輯", lambda i: self.edit_step()),
            ("✕", "刪除", lambda i: self.del_step()),
        ])
        self._handle_w = tkfont.Font(font=FONT).measure(" ☰ ") + 6  # 把手區寬度
        # 號碼欄 tab 定位點 (含 3 位數餘裕), render_steps 以 \t 對齊 │ 縮排
        self.step_list.configure(
            tabs=(tkfont.Font(font=FONT).measure(" ☰ 999. "),))
        self._drag_idxs = None
        self._drag_scroll_dir = 0     # 邊緣自動捲動方向 (-1 上 / 1 下 / 0 停)
        self._drag_scroll_job = None  # 邊緣捲動 after 計時器
        self._drag_job = None         # 拖曳移動合併節流 after 計時器
        self._drag_y = 0
        self.step_list.bind("<Motion>", self._handle_cursor, add=True)
        self.step_list.bind("<ButtonPress-1>", self._drag_start, add=True)
        self.step_list.bind("<B1-Motion>", self._drag_motion, add=True)
        self.step_list.bind("<ButtonRelease-1>", self._drag_end, add=True)

    def _build_templates(self, main):
        """本流程的範本: 截圖新增; 清單 (沒被引用的灰字) ＋縮圖; 重截／重新命名／刪除."""
        tp = ttk.Frame(main, style="Panel.TFrame", padding=10)
        tp.grid(row=0, column=1, sticky="nsew", pady=(0, 10))
        tp.rowconfigure(1, weight=1)
        tp.columnconfigure(0, weight=1)
        tp.columnconfigure(2, weight=1)

        thead = ttk.Frame(tp, style="Panel.TFrame")
        thead.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        # 面板列的是「本流程的範本」——一眼看得出這份流程帶了哪些圖 (ADR 0006)
        ttk.Label(thead, text="本流程的範本", style="Title.TLabel").pack(side="left")
        b = ttk.Button(thead, text="截圖新增", style="Accent.TButton",
                       command=lambda: self.capture_template())
        b.pack(side="right")
        self.recognition.register(b)

        self._tmpl_names = []     # 清單目前列出的範本名 (平面, 無資料夾層級)
        self.tmpl_list = tk.Listbox(
            tp, bg=C["bg"], fg=C["text"], selectbackground=C["sel"],
            selectforeground=C["text"], font=FONT_MONO, bd=0,
            highlightthickness=1, highlightbackground=C["border"],
            highlightcolor=C["accent"], activestyle="none", width=24)
        tsb = ttk.Scrollbar(tp, orient="vertical", command=self.tmpl_list.yview)
        self.tmpl_list.configure(yscrollcommand=tsb.set)
        self.tmpl_list.grid(row=1, column=0, sticky="nsew")
        tsb.grid(row=1, column=1, sticky="ns", padx=(0, 8))
        self.tmpl_list.bind("<<ListboxSelect>>", self._on_tmpl_select)
        self.tmpl_list.bind("<Double-Button-1>", lambda e: self.rename_template())
        self._tmpl_icons = RowIcons(self.tmpl_list, [
            ("✎", "重新命名", lambda i: self.rename_template()),
            ("✕", "刪除", lambda i: self.del_template()),
        ])

        pv = ttk.Frame(tp, style="Panel.TFrame")
        pv.grid(row=1, column=2, sticky="nsew")
        self.thumb_lbl = tk.Label(pv, bg=C["bg"], bd=0,
                                  highlightthickness=1,
                                  highlightbackground=C["border"])
        self.thumb_lbl.pack(fill="both", expand=True)
        self.thumb_info = ttk.Label(pv, text="", style="Muted.TLabel")
        self.thumb_info.pack(anchor="w", pady=(4, 0))

        ops = ttk.Frame(tp, style="Panel.TFrame")
        ops.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        for text, cmd in (("重截", self.recapture_template),
                          ("重新命名", self.rename_template),
                          ("刪除", self.del_template)):
            b = ttk.Button(ops, text=text, style="Small.TButton", takefocus=False,
                           command=cmd)
            b.pack(side="left", padx=(0, 4))
            if text == "重截":
                self.recognition.register(b)

    def _build_log(self, main):
        lg = ttk.Frame(main, style="Panel.TFrame", padding=10)
        lg.grid(row=1, column=1, sticky="nsew")
        lg.rowconfigure(1, weight=1)
        lg.columnconfigure(0, weight=1)
        lhead = ttk.Frame(lg, style="Panel.TFrame")
        lhead.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(lhead, text="執行紀錄", style="Title.TLabel").pack(side="left")
        ttk.Button(lhead, text="清除", style="Small.TButton", takefocus=False,
                   command=self._clear_log).pack(side="right")

        self.log_text = tk.Text(
            lg, bg=C["bg"], fg="#CBD5E1", font=FONT_MONO, bd=0,
            highlightthickness=1, highlightbackground=C["border"],
            state="disabled", wrap="char", height=5)
        self.log_text.grid(row=1, column=0, sticky="nsew")
        for tag, color in (("info", "#CBD5E1"), ("ok", C["accent"]),
                           ("warn", C["warn"]), ("error", C["danger"]),
                           ("time", C["muted"])):
            self.log_text.tag_configure(tag, foreground=color)

    # ================= 步驟操作 =================

    def render_steps(self, keep=None):
        lb = self.step_list
        top = lb.yview()[0]  # 保留捲動位置: 重建會把 tk.Text 捲回頂端
        rows = []  # 先組好所有列, 最後一次 load (大量步驟時逐列 append 會卡)
        self._view = []
        stack = []  # 進行中區段類型, 供 │ 連線前綴 (顏色依隸屬區塊)
        i = 0
        while i < len(self.steps):
            s = self.steps[i]
            t = s["type"]
            collapsed = False
            end = None
            row_color = (C["warn"] if t in ("repeat_start", "repeat_end")
                         else C["info"] if t in ("branch_start", "branch_or",
                                                 "branch_end")
                         else C["text"])
            if t in ("repeat_end", "branch_end"):
                if stack:
                    stack.pop()
                guides, tail = list(stack), "└ "
            elif t == "branch_or":
                guides, tail = list(stack[:-1]), "├ "
            elif t in ("repeat_start", "branch_start"):
                end = self._region_end(i)
                collapsed = id(s) in self._collapsed and end is not None
                guides, tail = list(stack), ("▸ " if collapsed else "▾ ")
            else:
                guides, tail = list(stack), ""
            body = step_desc(s)
            if collapsed:
                body += f"（收合 {end - i - 1} 步，雙擊展開）"
            # 號碼後接 tab: 比例字型下位數不同寬度不一, 靠定位點讓 │ 對齊
            segs = [(f" ☰ {i + 1:>2}.\t", row_color)]
            segs += [("│ ", GUIDE_COLORS[g]) for g in guides]
            if tail:
                segs.append((tail, row_color))
            segs.append((f"［{STEP_LABELS[t]}］", LABEL_COLORS.get(t, row_color)))
            if ((uses_confirm_next(s)
                 and not confirm_next_connected(self.steps, i))
                    or (uses_origin_leaves(s)
                        and origin_source(self.steps, i) != "find")):
                # 「點到下一步的圖出現」不相連, 或「原點的圖離開」的原點不是
                # 來自找圖 (存檔後被移動/刪除/改掉前後步驟): 執行前會被擋下,
                # 平時只在列上提示、不彈窗
                segs.append(("⚠ ", C["warn"]))
            segs.append((body, row_color))
            rows.append(segs)
            self._view.append(i)
            if t in ("repeat_start", "branch_start"):
                if collapsed:
                    i = end + 1  # 跳過整個收合區段 (含結束標記)
                    continue
                stack.append(t)
            i += 1
        lb.load(rows)
        lb.yview_moveto(top)  # 先還原原本捲動位置 (拖曳時列數不變 → 精準)
        if keep is not None and self._view:
            vi = 0
            for k, si in enumerate(self._view):
                if si <= keep:
                    vi = k
            lb.selection_set(vi)
            lb.see(vi)  # 還原後才確保 keep 可見, 只在超出視窗時才微調
        if self._drag_idxs is None:  # 拖曳中跳過 (版面同步太重), 拖曳結束時補一次
            self._step_icons.refresh()
        # 步驟改了引用 (換範本、刪掉最後一個引用的步驟): 範本面板的未引用標記即時跟著變
        if (getattr(self, "tmpl_list", None) is not None
                and set(self.referenced_templates()) != getattr(self, "_refs_shown", None)):
            self.refresh_templates()

    def _region_end(self, i):
        """start 標記 i 的對應結束索引 (通用巢狀); 不成對回傳 None."""
        depth = 0
        for j in range(i + 1, len(self.steps)):
            t = self.steps[j]["type"]
            if t in ("repeat_start", "branch_start"):
                depth += 1
            elif t in ("repeat_end", "branch_end"):
                if depth == 0:
                    return j
                depth -= 1
        return None

    def _sel(self):
        """回傳選取列對應的 steps 索引 (收合時清單列 ≠ 步驟索引)."""
        s = self.step_list.curselection()
        if not s or s[0] >= len(self._view):
            return None
        return self._view[s[0]]

    def _on_step_double(self, e):
        i = self._sel()
        if i is None:
            return
        if self.steps[i]["type"] in ("repeat_start", "branch_start"):
            self._toggle_fold(i)  # 區段起點雙擊 = 收合/展開 (編輯用 ✎ 圖示)
        else:
            self.edit_step()

    def _toggle_fold(self, i):
        key = id(self.steps[i])
        if key in self._collapsed:
            self._collapsed.discard(key)
        else:
            if self._region_end(i) is None:
                return  # 沒有對應的結束標記, 無法收合
            self._collapsed.add(key)
        self.render_steps(keep=i)

    def add_step(self, t):
        # 有選取列 → 插在選取列之後 (收合區段算整段); 沒有 → 接在最後
        idxs = self._expand_collapsed(self._sel_all())
        at = (idxs[-1] + 1) if idxs else len(self.steps)
        if t in MARKER_TYPES:  # 沒有可設定的欄位, 直接加入
            self.steps.insert(at, flowdefaults.new_step(t))
            self._mark_dirty()
            self.render_steps(keep=at)
            return
        s = flowdefaults.new_step(t)   # 「沒寫＝」表補齊的完整步驟
        s["_index"] = at  # 新步驟的插入位置, 供推算前一步
        s = ui_dialogs.edit_step(self, s)
        if s:
            self.steps.insert(at, s)
            self._mark_dirty()
            self.render_steps(keep=at)

    def edit_step(self):
        i = self._sel()
        if i is None:
            return
        if (self.steps[i]["type"] in MARKER_TYPES
                and self.steps[i]["type"] not in EDITABLE_MARKERS):
            return  # 其餘標記步驟沒有可編輯的欄位
        s = dict(self.steps[i])
        s["_edit"] = True
        s["_index"] = i
        r = ui_dialogs.edit_step(self, s)
        if r:
            if r != self.steps[i]:
                self._mark_dirty()
            self.steps[i] = r
            self.render_steps(keep=i)

    def _sel_all(self):
        """所有選取列對應的 steps 索引 (已排序)."""
        return sorted(self._view[i] for i in self.step_list.curselection()
                      if i < len(self._view))

    def _expand_collapsed(self, idxs):
        """選取包含收合的區段起點時, 展開為整個區段的索引 (含結束標記)."""
        out = set()
        for i in idxs:
            out.add(i)
            s = self.steps[i]
            if (s["type"] in ("repeat_start", "branch_start")
                    and id(s) in self._collapsed):
                end = self._region_end(i)
                if end is not None:
                    out.update(range(i, end + 1))
        return sorted(out)

    def copy_steps(self):
        idxs = self._expand_collapsed(self._sel_all())
        if not idxs:
            return
        self._step_clip = [json.loads(json.dumps(self.steps[i])) for i in idxs]
        self.log_ui(f"已複製 {len(idxs)} 個步驟（Ctrl+V 貼上）")

    def paste_steps(self):
        clip = getattr(self, "_step_clip", None)
        if not clip:
            return
        idxs = self._sel_all()
        at = (idxs[-1] + 1) if idxs else len(self.steps)
        items = [json.loads(json.dumps(s)) for s in clip]
        self.steps[at:at] = items
        self._mark_dirty()
        self.render_steps(keep=at + len(items) - 1)
        self.log_ui(f"已貼上 {len(items)} 個步驟", "ok")

    def del_step(self):
        idxs = self._expand_collapsed(self._sel_all())
        if not idxs:
            return
        for i in reversed(idxs):
            del self.steps[i]
        self._mark_dirty()
        self.render_steps(keep=min(idxs[0], len(self.steps) - 1))

    def _on_handle(self, e):
        """游標是否在某列左側的 ☰ 把手區內."""
        lb = self.step_list
        if not lb.size() or e.x > self._handle_w:
            return False
        bb = lb.bbox(lb.nearest(e.y))
        return bool(bb and bb[1] - 1 <= e.y <= bb[1] + bb[3] + 2)

    def _handle_cursor(self, e):
        if self._drag_idxs is not None:
            return  # 拖曳中不做把手偵測 (bbox 會強制版面同步, 拖大量步驟會卡)
        self.step_list.configure(cursor="fleur" if self._on_handle(e) else "")

    def _drag_start(self, e):
        # 只有按在 ☰ 把手上才進入拖曳排序模式 (存 steps 索引, 非清單列)
        self._drag_idxs = None
        if self._on_handle(e):
            vi = self.step_list.nearest(e.y)
            if vi < len(self._view):
                i = self._view[vi]
                sel = self._expand_collapsed(self._sel_all())
                # 按在選取列上 → 整組一起拖; 否則只拖該列 (收合區段連內容)
                self._drag_idxs = sel if i in sel else self._expand_collapsed([i])

    def _drag_reorder_to(self, y):
        """把拖曳中的步驟移到清單 y 座標所在列的位置 (自動捲動時也用)."""
        idxs = self._drag_idxs
        if not idxs:
            return
        vi = self.step_list.nearest(y)
        if not (0 <= vi < len(self._view)):
            return
        j = self._view[vi]
        if j in idxs:
            return
        picked = set(idxs)
        block = [self.steps[i] for i in idxs]
        rest = [s for k, s in enumerate(self.steps) if k not in picked]
        down = j > idxs[0]
        at = j - sum(1 for i in idxs if i < j) + (1 if down else 0)
        self.steps = rest[:at] + block + rest[at:]
        self._drag_idxs = list(range(at, at + len(block)))
        # keep = 靠近游標那端, 邊緣自動捲動時 see() 才不會拉回另一端
        self.render_steps(keep=at + len(block) - 1 if down else at)
        self.step_list.selection_set_rows(
            [v for v, si in enumerate(self._view)
             if at <= si < at + len(block)])

    def _drag_motion(self, e):
        if self._drag_idxs is None:
            return  # 非把手拖曳 → 保留 Listbox 預設行為
        # 合併節流: 只記最新位置, 30ms 批次處理一次 (每個 motion 都全量
        # 重繪清單, 步驟多時會卡)
        self._drag_y = e.y
        if self._drag_job is None:
            self._drag_job = self.step_list.after(30, self._drag_apply)
        self._update_edge_scroll(e.y)
        return "break"  # 抑制 Listbox 預設的拖曳選取

    def _drag_apply(self):
        self._drag_job = None
        if self._drag_idxs is not None:
            self._drag_reorder_to(self._drag_y)

    def _update_edge_scroll(self, y):
        """游標拖到清單上/下緣感應區時, 啟動持續自動捲動 (超出視窗也能排序)."""
        lb = self.step_list
        zone = 22  # 邊緣感應區高度 (px)
        if y < zone:
            self._drag_scroll_dir = -1
        elif y > lb.winfo_height() - zone:
            self._drag_scroll_dir = 1
        else:
            self._drag_scroll_dir = 0
        if self._drag_scroll_dir and self._drag_scroll_job is None:
            self._drag_scroll_tick()

    def _drag_scroll_tick(self):
        """自動捲動計時: 每次捲一列並依目前游標重新定位插入點, 直到離開邊緣或放開."""
        self._drag_scroll_job = None
        if self._drag_idxs is None or not self._drag_scroll_dir:
            return
        lb = self.step_list
        lb.yview_scroll(self._drag_scroll_dir, "units")
        y = lb.winfo_pointery() - lb.winfo_rooty()  # 游標可能靜止在邊緣, 用實際位置
        self._drag_reorder_to(y)
        self._drag_scroll_job = lb.after(90, self._drag_scroll_tick)

    def _drag_end(self, e):
        moved = self._drag_idxs is not None
        self._drag_idxs = None
        self._drag_scroll_dir = 0
        if self._drag_scroll_job is not None:
            self.step_list.after_cancel(self._drag_scroll_job)
            self._drag_scroll_job = None
        if self._drag_job is not None:
            self.step_list.after_cancel(self._drag_job)
            self._drag_job = None
        if moved:  # 拖曳中跳過的圖示刷新, 結束補一次
            self._step_icons.refresh()
            self._mark_dirty()

    # ================= 範本操作 (本流程的範本) =================
    # 範本名是**平面名稱** (＝templates/ 裡的檔名), 在一份流程內唯一。**一範本一張圖**。
    # 新增、重截、改名、刪除只動記憶體與快取 (self.store), 存檔才寫回 templates/。

    def list_template_names(self):
        """本流程的範本名 (已存檔的＋還沒存檔的截圖)."""
        return self.store.names()

    def template_image(self, name):
        """範本的參考影像 (登錄產物已載入時取它, 否則直接讀圖)."""
        t = self.library.templates.get(name) if self.library else None
        if t is not None and t.artifacts is not None:
            return t.artifacts.ref_bgr
        p = self.store.path_of(name)
        return imgio.imread(p) if os.path.exists(p) else None

    def template_pos(self, name):
        """範本的拍攝位置 [x, y] (截圖當下的中心, 相對`座標基準點`、流程尺度);
        沒有記錄回傳 None.

        只有本流程自己拍的圖有——跨流程複製進來與從磁碟上傳的沒有
        (相對座標原點只能靠即時找圖或往前推)。
        """
        return self.store.pos_of(name)

    def record_template_pos(self, name, xy):
        """補記範本的拍攝位置 (相對座標基準點; 比對測試找到時, 供相對座標當備援原點)."""
        self.store.set_pos(name, xy)
        self._mark_dirty()

    def template_bytes(self, name):
        """本流程某個範本的圖檔位元組; 讀不到回 None."""
        try:
            with open(self.store.path_of(name), "rb") as f:
                return f.read()
        except OSError:
            return None

    def current_flow_path(self):
        """目前這份流程的資料夾; 還沒存過的新流程回 None."""
        return self.store.folder

    def other_flow_folders(self):
        """流程預設位置底下的其他流程資料夾 (選範本對話框的來源)."""
        cur = self.store.folder
        return [p for p in flowfile.list_flow_folders(apppaths.flows_root())
                if cur is None or os.path.normcase(os.path.abspath(p))
                != os.path.normcase(os.path.abspath(cur))]

    def drop_template(self, name):
        """把範本從本流程收回去 (快取的圖與登錄產物一起刪)."""
        with self.hub.files_locked():
            self.store.remove(name)
            self._pending_templates.discard(name)
            self.rebind_templates(changed=set())
        self._mark_dirty()

    def add_template_image(self, name, blob, pos=None):
        """把一張圖加進本流程 (bytes 或來源圖檔路徑); 回傳最終採用的範本名.

        撞名自動加序號, 所以本流程原有的圖絕對不會被蓋掉; 改名結果由呼叫端
        寫進執行紀錄 (不彈對話框)。
        """
        final = self.store.add(name, blob, pos=pos)
        self._pending_templates.add(final)
        self._mark_dirty()
        self._schedule_reregister()
        return final

    # ---- 清單 ----

    def _select_tmpl_row(self, name):
        rows = self._tmpl_names
        if name in rows:
            i = rows.index(name)
            self.tmpl_list.selection_clear(0, "end")
            self.tmpl_list.selection_set(i)
            self.tmpl_list.see(i)
            self._show_thumb()

    def refresh_templates(self):
        """本流程的範本清單 (平面, 沒有資料夾層級); 有`拾取檢查`警告的範本標 ⚠;
        沒被任何步驟或流程設定引用的灰字加「（未引用）」(存檔時會離開 templates/)."""
        names = self.list_template_names()
        sel = self._sel_template()
        self._tmpl_names = names
        flagged = self.pick_warnings()
        used = self._refs_shown = set(self.referenced_templates())
        self.tmpl_list.delete(0, "end")
        for n in names:
            if n in used:
                self.tmpl_list.insert("end", f" {'⚠' if n in flagged else '🖼'} {n}")
            else:
                self.tmpl_list.insert("end", f" {'⚠' if n in flagged else '○'} {n}"
                                             f"　{UNREF_MARK}")
                self.tmpl_list.itemconfig("end", fg=C["muted"])
        if sel in names:
            i = names.index(sel)
            self.tmpl_list.selection_set(i)
            self.tmpl_list.see(i)
        self._tmpl_icons.refresh()
        self._show_thumb()

    def _sel_template(self):
        s = self.tmpl_list.curselection()
        rows = getattr(self, "_tmpl_names", [])
        if not s or s[0] >= len(rows):
            return None
        return rows[s[0]]

    def _on_tmpl_select(self, e=None):
        self._show_thumb()

    def _show_thumb(self):
        name = self._sel_template()
        img = self.template_image(name) if name else None
        # 固定尺寸底圖: 預覽框不隨範本大小忽大忽小
        photo = ui_dialogs._thumb_photo(self.root, img)
        self.thumb_lbl.configure(image=photo, text="")
        self.thumb_lbl._photo = photo
        if img is not None:
            text = f"{name}　{img.shape[1]}×{img.shape[0]}px"
        else:
            text = name if name else ""
        if name and name in self.pick_warnings():
            text += "　⚠ 拾取檢查有警告（見執行紀錄）"
        self.thumb_info.configure(text=text)

    # ================= `拾取檢查` (ADR 0013) =================
    # 判斷在 automation/pickcheck.py (影片轉流程也用它); 這裡只接線: 截範本後的
    # 縮放餘裕、找圖設定確定與比對測試的唯一 (ui_dialogs), 警告寫紀錄區並在面板標記。
    # 標記不進存檔: 只活在這一次編輯 session, 下一次檢查通過時消失。

    def pick_warnings(self):
        """{範本名: [警告文字]}: 目前帶著拾取檢查警告的範本 (面板標 ⚠)."""
        return self.__dict__.setdefault("_tmpl_warnings", {})

    def note_pick_warnings(self, name, warns):
        """記下某範本這次拾取檢查的結果: 有警告→寫紀錄區、面板標記; 通過→清掉標記."""
        flagged = self.pick_warnings()
        if warns:
            flagged[name] = [str(w) for w in warns]
            for w in warns:
                self.log_ui(f"拾取檢查「{name}」{w}", "warn")
        elif flagged.pop(name, None) is not None:
            self.log_ui(f"拾取檢查「{name}」這次通過，標記已清除", "ok")
        self.refresh_templates()

    def check_template_scale(self, name, m, job=None):
        """截範本後的`縮放餘裕`: m＝拾取當下的量測 (ui_dialogs.Measured: 搜尋範圍那塊截圖
        frame、基準點 anchor、倍率 k; 沒有校準對時 anchor 是 None、倍率 1). 等該範本進了
        範本清單才查; 沒有截圖或引擎沒就緒就略過 (只是檢查, 不經 engine_gate 的 modal).

        登錄產物載入與查詢在背景 (job＝接在截圖那件辨識後面, 不給就自己開一件, 發起視窗是
        主視窗), 做完寫紀錄區、在範本面板標 ⚠。
        """
        if m.frame is None or not self.templates_known([name]):
            return
        (screen, org), anchor, k = m.frame, m.anchor, m.k

        def work():
            problem = self.load_problem([name])
            if problem:
                return problem, []
            return None, pickcheck.scale_margin(self.detector, screen, org,
                                                {"template": name}, anchor, k)

        def done(res):
            problem, warns = res
            if problem:
                self.log_ui(f"拾取檢查略過：範本「{name}」載入失敗（{problem[1]}）", "warn")
                return
            self.note_pick_warnings(name, warns)

        self.recognize("縮放餘裕", work, done, origin=self.root, job=job)

    # ---- 新增範本 ----

    def next_template_name(self, taken=()):
        """下一個未使用的自動命名; taken 補上本批次剛建立、尚未重載的名稱.

        公開: 選範本對話框現場截圖時也要照同一套命名 (別讓它自己編一套)。
        """
        used = set()
        for fn in [*self.list_template_names(), *taken]:
            m = re.fullmatch(r"tmpl_(\d+)", fn)
            if m:
                used.add(int(m.group(1)))
        n = 1
        while n in used:
            n += 1
        return f"tmpl_{n:03d}"

    def pick_region_measured(self, done, hide=(), parent=None):
        """框選一個區域並在那張畫面上`校準`; 做完在介面執行緒呼叫 done(拾取結果, 量測)
        (量測＝ui_dialogs.Measured: anchor 座標基準點、k 畫面倍率、frame 搜尋範圍那塊、job).

        截範本的共同入口 (範本面板「截圖新增」與「重截」、選範本對話框「截圖新增」): 圖要除以
        當下倍率、拍攝位置要相對當下基準點 (ADR 0012)。沒有校準對＝倍率 1、不記位置。
        覆蓋層立刻出現, 校準在背景同時做; 取消、量不到都不呼叫 done (量不到已提示)。
        frame 給`拾取檢查`的縮放餘裕用。
        """
        def overlay(shot, pending):
            return ui_dialogs.overlay_pick(self.root, "region", "拖曳框選要辨識的圖片區域",
                                           hide, shot, pending)
        return ui_dialogs.measured_pick(self, parent or self.root, "截圖框選", done,
                                        overlay=overlay, hide=hide)

    def save_captured(self, r, anchor=None, k=1.0):
        """把截圖框選的結果 (覆蓋層 region 拾取) 存成本流程的新範本, 回傳範本名.

        圖落在快取 (存檔時才進 templates/), 先除以當下的`畫面倍率` k 換回流程尺度
        (倍率 1 原圖照存; 上傳的圖不經這裡); 拍攝位置＝截圖中心相對當下的`座標基準點`
        anchor (沒有基準點就不記)。
        """
        name = self.store.reserve(self.next_template_name())
        img = imgio.to_flow_scale(r["img"], k)
        imgio.imwrite(self.store.path_of(name), img)
        pos = ui_dialogs.template_pos_from_shot(r, anchor, k)
        if pos is not None:
            self.store.set_pos(name, pos)
        self._mark_dirty()
        # 交給範本清單是毫秒級; 登錄產物在用到時 (縮放餘裕、比對測試) 於背景載入
        self._pending_templates.add(name)
        self._schedule_reregister()
        self.refresh_templates()
        self.log_ui(f"已新增範本「{name}」({img.shape[1]}×{img.shape[0]})", "ok")
        return name

    def _schedule_reregister(self):
        """把重新探索排入 after 佇列 (合併連續多次存圖, 只跑一次)."""
        if self._rereg_after is None:
            self._rereg_after = self.root.after(80, self._run_reregister)

    def _cancel_reregister(self):
        if self._rereg_after is not None:
            try:
                self.root.after_cancel(self._rereg_after)
            except tk.TclError:
                pass
            self._rereg_after = None

    def _run_reregister(self):
        self._rereg_after = None
        if ui_grab.coord.clearing:
            # 排程落在下一次清場的事件迴圈裡: 重新探索會在畫面隱藏時卡住,
            # 等清場結束再跑 (需要引擎的查詢路徑自會 ensure_registered)
            self._rereg_after = self.root.after(500, self._run_reregister)
            return
        self.ensure_registered()

    def ensure_registered(self):
        """延後的重新綁定立即補跑; 引擎查詢 (比對測試/執行流程) 前必須呼叫,
        否則延後期間的新範本還不在範本清單裡, 查詢會 KeyError。只有新範本要
        重新登錄, 其他的登錄產物照用 (ADR 0004)."""
        if not self._pending_templates:
            return
        self._cancel_reregister()
        self.rebind_templates(changed=set(self._pending_templates))
        self._pending_templates.clear()
        self.refresh_templates()

    def capture_template(self, hide=()):
        """截圖框選 → 拿到當下倍率與基準點後自動命名存入本流程的範本, 接著 (同一件背景辨識)
        跑縮放餘裕. 範本在校準做完才存; 回傳這件辨識 (Job) 或 None (被擋下)."""
        if self.recognition.busy:
            return None

        def done(r, m):
            name = self.save_captured(r, m.anchor, m.k)
            self.check_template_scale(name, m, job=m.job)
        return self.pick_region_measured(done, hide=hide)

    def recapture_template(self):
        """「重截」: 選中的範本框一張新圖取代它、名字不變 (引用它的步驟都不用改).

        走跟截圖新增同一條拾取路徑 (量倍率與基準點、圖換回流程尺度、記拍攝位置), 換完跑
        縮放餘裕的拾取檢查。新圖只住在快取, 存檔時才換掉 templates/ 裡的那張 (不存檔＝沒
        重截); 取消＝什麼都不變。
        """
        if self.recognition.busy:
            return
        name = self._sel_template()
        if not name:
            self.log_ui("重截：先在範本清單選一個範本", "warn")
            return

        def done(r, m):
            if name not in self.store.names():   # 辨識中被刪掉或改名了
                self.log_ui(f"重截：範本「{name}」已不在本流程，這次沒換", "warn")
                return
            img = imgio.to_flow_scale(r["img"], m.k)
            with self.hub.files_locked():
                self.store.replace(name, imgio.encode_png(img),
                                   pos=ui_dialogs.template_pos_from_shot(r, m.anchor, m.k))
                self.rebind_templates(changed={name})
            self.pick_warnings().pop(name, None)
            self._mark_dirty()
            self.refresh_templates()
            self.log_ui(f"已重截範本「{name}」({img.shape[1]}×{img.shape[0]})；"
                        "存檔時才換掉原本的圖", "ok")
            self.check_template_scale(name, m, job=m.job)
        self.pick_region_measured(done)

    # ---- 管理 ----

    def rename_template(self):
        """重新命名本流程的範本, 並同步改寫所有引用它的步驟 (含`確認圖`)."""
        old = self._sel_template()
        if not old:
            messagebox.showinfo("重新命名", "請先在清單選擇一個範本", parent=self.root)
            return
        new = ui_dialogs.ask_string(self.root, "重新命名", "輸入新名稱：",
                                    initialvalue=old)
        if new is None:
            return
        if new == old:
            return
        problem = flowfile.template_name_problem(new)
        if problem:   # 範本名＝檔名: 不靜靜改寫使用者輸入的名字, 擋下並說明
            messagebox.showwarning("重新命名", problem, parent=self.root)
            return
        with self.hub.files_locked():
            final = self.store.rename(old, new)
            if final is not None:
                self.rebind_templates(changed={final})
        if final is None:
            messagebox.showwarning("重新命名", f"找不到範本「{old}」的圖",
                                   parent=self.root)
            return
        changed = flowfile.rename_template_refs(self._ref_data(), old, final)
        flagged = self.pick_warnings()
        if old in flagged:
            flagged[final] = flagged.pop(old)
        self._mark_dirty()
        self.refresh_templates()
        self.render_steps()
        msg = f"已將「{old}」重新命名為「{final}」"
        if final != new:
            msg += "（原名稱已被占用，自動加序號）"
        if changed:
            msg += f"（已同步更新 {changed} 個步驟）"
        self.log_ui(msg, "ok")

    def del_template(self):
        """從本流程移除範本; 引用它的步驟以既有方式標示為有問題 (執行前擋下)."""
        name = self._sel_template()
        if not name:
            return
        used = [f"步驟 {i + 1}" for i, s in enumerate(self.steps)
                if name in flowfile.used_templates([s])]
        if self.flow_cal and name in self.flow_cal["pair"]:
            used.append("校準對")
        if self.busy_target and self.busy_target["template"] == name:
            used.append("忙碌指示")
        # 沒有人使用時直接刪除, 不打擾
        if used and not messagebox.askyesno(
                "刪除範本",
                f"刪除範本「{name}」？\n（{'、'.join(used)} 正在使用它）",
                parent=self.root):
            return
        with self.hub.files_locked():
            self.store.remove(name)
            self._pending_templates.discard(name)
            self.rebind_templates(changed=set())
        self.pick_warnings().pop(name, None)
        self._mark_dirty()
        self.refresh_templates()
        self.render_steps()

    # ================= 流程 (資料夾) =================

    def _ref_data(self):
        """引用範本的那部分流程資料: 步驟＋校準對＋忙碌指示 (不讀介面元件).

        回傳的是同一批物件 (不是副本): `rename_template_refs` 就地改它就改到本流程。
        """
        return {"steps": self.steps, "calibration": self.flow_cal,
                "busy": self.busy_target}

    def _flow_data(self):
        """目前的流程 (記憶體模型, flowfile 把它寫回資料夾)."""
        return {"run": self._run_value(), "scan_region": self.scan_region,
                "calibration": self.flow_cal, "busy": self.busy_target,
                "template_pos": self.store.pos(), "engine": dict(self.flow_engine),
                "steps": self.steps}

    def referenced_templates(self):
        """本流程引用的全部範本名 (步驟 + 校準對 + 忙碌指示; 見 flowfile.template_refs)."""
        return flowfile.template_refs(self._ref_data())

    def flow_name(self):
        """流程名 (＝資料夾名); 還沒存檔的新流程回「未命名」."""
        return os.path.basename(self.store.folder) if self.store.folder else "未命名"

    def _apply_flow(self, flow):
        """套用一份流程 (flowfile 讀進來、已驗證過的記憶體模型)."""
        self.steps = flow["steps"]
        self.flow_cal = flow["calibration"]
        self.busy_target = flow["busy"]
        self._settings_changed()
        self.flow_engine = dict(flow["engine"])
        forever = flow["run"] == "forever"
        self.run_mode.set("直到停止" if forever else "執行次數")
        self.run_count.set(1 if forever else flow["run"])
        self._run_seen = self._run_value()
        self.scan_region = flow["scan_region"]
        if self.scan_region:
            self.scan_lbl.configure(text=f"限定 {tuple(self.scan_region)}",
                                    foreground=C["accent"])
        else:
            self.scan_lbl.configure(text="全螢幕", foreground=C["muted"])
        self._mode_ui()
        self.render_steps()
        self._update_region_preview()

    def _switch_flow(self, folder, flow):
        """換成另一份流程: 本流程的範本換成那份資料夾的 (新流程＝空的未存檔快取),
        範本清單整份重新交給引擎; 記下它是上次開的流程."""
        unsaved = apppaths.unsaved_dir()
        self.store = (flowfile.FlowTemplates.open(folder, unsaved, flow["template_pos"])
                      if folder else flowfile.FlowTemplates.new(unsaved))
        self._cancel_reregister()
        self._pending_templates.clear()
        self.pick_warnings().clear()   # 標記只屬於這一次編輯, 不進存檔
        self._collapsed.clear()
        self._apply_flow(flow)
        self.rebind_templates()
        self.refresh_templates()
        self._set_dirty(False)
        if folder:
            apppaths.remember_last_flow(folder)
        self.start_preload()

    def confirm_discard(self, title):
        """有未存檔的改動時問「存檔／不存／取消」; 回傳是否繼續往下走.

        存檔＝先存 (新流程會跳第一次存檔的對話框), 存成才繼續; 不存＝丟掉改動繼續;
        取消＝什麼都不變。
        """
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(
            title, f"「{self.flow_name()}」有還沒存檔的改動，要先存檔嗎？\n\n"
            "是＝存檔　否＝不存（改動會消失）　取消＝回去繼續編輯", parent=self.root)
        if answer is None:
            return False
        if answer:
            return self.save_flow()
        return True

    def new_flow(self):
        """開一份新流程 (還沒有資料夾: 第一次存檔才選位置與名字)."""
        if not self.confirm_discard("新流程"):
            return
        self._switch_flow(None, flowfile.new_flow())
        self.log_ui("已開始一份新流程（第一次存檔時選位置與名字）", "ok")

    def open_flow(self):
        """開檔: 一般開檔視窗選 flow.yaml, 開它所在的流程資料夾."""
        if not self.confirm_discard("開啟流程"):
            return
        root = apppaths.flows_root()
        os.makedirs(root, exist_ok=True)
        path = filedialog.askopenfilename(
            parent=self.root, title="開啟流程（選流程資料夾裡的 flow.yaml）",
            initialdir=root,
            filetypes=[("AutoClick 流程", flowfile.FLOW_YAML), ("所有檔案", "*.*")])
        if not path:
            return
        self.open_flow_folder(os.path.dirname(path))

    def open_flow_folder(self, folder, startup=False):
        """讀一份流程資料夾並換成它; 讀不進來就說明原因、目前的流程不動. 回傳是否開成.

        被引用卻缺圖的照樣開, 彈窗加執行紀錄列出缺哪幾張 (執行時照範本預載的規則
        拒絕開跑; 可在 app 裡重截同名圖補回)。startup＝app 啟動時自動開的 (提示
        排到事件迴圈再彈, 不在 __init__ 裡擋)。
        """
        name = os.path.basename(os.path.abspath(folder))

        def warn(title, text):
            if startup:
                self.root.after(0, lambda: messagebox.showwarning(
                    title, text, parent=self.root))
            else:
                messagebox.showwarning(title, text, parent=self.root)

        try:
            flow = flowfile.read_flow(folder)
        except flowfile.FlowError as e:
            self.log_ui(f"無法開啟流程「{name}」：{e}", "warn")
            warn("開啟流程", f"無法開啟流程「{name}」：\n{e}")
            return False
        self._switch_flow(folder, flow)
        self.log_ui(f"已開啟流程「{name}」（{len(self.steps)} 步、"
                    f"{len(self.store.names())} 個範本）", "ok")
        missing = flowfile.missing_templates(folder, flow)
        if missing:
            self.log_ui("這些範本被引用卻不在 templates/（執行前要補回，可重截同名圖）："
                        + "、".join(missing), "warn")
            warn("開啟流程", f"流程「{name}」缺這些範本圖：\n" + "\n".join(missing)
                 + "\n\n執行前要補回（可在 app 裡重截同名範本）")
        return True

    def _open_last_flow(self):
        """app 啟動: 自動開上次開的流程; 它不在了就留在空白新流程並記一行."""
        last = apppaths.last_flow()
        if not last:
            return
        if os.path.isfile(os.path.join(last, flowfile.FLOW_YAML)):
            self.open_flow_folder(last, startup=True)
        else:
            self.log_ui(f"上次開的流程已經不在（{last}）→ 開了空白新流程", "warn")

    def _ask_new_flow_folder(self):
        """新流程第一次存檔: 選位置、輸入流程名 → <位置>/<流程名>/ (已有同名資料夾就拒絕).

        回傳要建的流程資料夾路徑; 取消或被拒絕回 None (什麼都沒寫)。
        """
        root = apppaths.flows_root()
        os.makedirs(root, exist_ok=True)
        path = filedialog.asksaveasfilename(
            parent=self.root, title="存成新流程（輸入流程名，會建同名資料夾）",
            initialdir=root, initialfile="新流程",
            filetypes=[("流程資料夾", "*")])
        if not path:
            return None
        folder = os.path.abspath(path)
        if folder.lower().endswith(".yaml"):
            folder = folder[:-5]
        name = os.path.basename(folder)
        if not name or name != name.strip() or name.endswith("."):
            messagebox.showwarning("存檔", f"流程名「{name}」不能當資料夾名，請換一個",
                                   parent=self.root)
            return None
        if os.path.exists(folder):
            messagebox.showwarning(
                "存檔", f"「{os.path.dirname(folder)}」裡已經有「{name}」了，"
                "請換一個流程名（什麼都沒寫）", parent=self.root)
            return None
        return folder

    def save_flow(self):
        """存檔: flow.yaml 整份重寫、截圖搬進 templates/、templates/ 只留被引用的範本.

        新流程第一次存檔才選位置與名字。回傳是否存成 (取消或失敗回 False)。
        """
        new_folder = None
        if self.store.folder is None:
            new_folder = self._ask_new_flow_folder()
            if new_folder is None:
                return False
        self.ensure_registered()  # 延後中的新範本先進清單
        try:
            with self.hub.files_locked():   # 背景預載不讀搬到一半的圖
                missing = self.store.save(self._flow_data(), new_folder)
                self.rebind_templates(changed=set())   # 圖只是搬了位置, 登錄產物照用
        except (OSError, flowfile.FlowError, ValueError) as e:
            messagebox.showerror("存檔", f"存檔失敗：{e}", parent=self.root)
            return False
        self._set_dirty(False)
        apppaths.remember_last_flow(self.store.folder)
        names = self.referenced_templates()
        self.log_ui(f"已存檔「{self.flow_name()}」（{len(self.steps)} 步、"
                    f"{len(names) - len(missing)} 個範本）", "ok")
        if missing:
            self.log_ui("這些範本被引用卻沒有圖，存檔沒有帶到："
                        + "、".join(missing), "warn")
        return True

    # ================= 執行 =================

    def _run_value(self):
        """執行輪數 (存檔的 run 鍵): "forever" 或次數."""
        return "forever" if self.run_mode.get() == "直到停止" else self._run_count()

    def _run_count(self):
        try:
            return max(1, int(self.run_count.get()))
        except (ValueError, tk.TclError):
            return 1

    def _flow_error(self, steps=None):
        """執行前檢查流程的區段結構, 回傳錯誤訊息或 None (`flowcheck.section_error`)."""
        return flowcheck.section_error(self.steps if steps is None else steps)

    def start_run(self, steps=None, test=False):
        """執行流程; steps 給定時只跑該片段 (測試選取), 一律單次."""
        pressed_at = time.monotonic()  # `開始延遲`從按下執行起算 (含底下的檢查)
        if self.recognition.busy:   # 辨識中執行鈕反灰; 這裡是第二道
            return
        if not self.engine_gate():  # `引擎就緒`前提示並拒絕 (ADR 0004)
            return
        self.ensure_registered()  # 剛存的範本先登錄, runner 查詢才查得到
        steps = self.steps if steps is None else steps
        if not steps:
            messagebox.showinfo("執行", "請先新增步驟", parent=self.root)
            return
        names = set(self.list_template_names())
        missing = []
        for s in steps:
            if (findtarget.is_find(s)
                    and findtarget.template(s) not in names):
                missing.append(findtarget.template(s) or "(未選擇)")
            if (findtarget.uses_confirm_target(s)
                    and findtarget.confirm_template(s) not in names):
                missing.append((findtarget.confirm_template(s) or "(未選擇)")
                               + "（確認圖）")
        if self.flow_cal is None:
            # 執行器開頭也會擋 (沒有校準對＝量不了倍率); 這裡先講清楚下一步
            messagebox.showwarning(
                "執行", "這份流程沒有校準對（尚未設定），不能執行。\n"
                "請先在「流程設定…」設定校準對（遊戲畫面內兩張相距夠遠的固定圖）",
                parent=self.root)
            return
        missing += [f"{n}（校準對）" for n in self.flow_cal["pair"]
                    if n not in names]
        if self.busy_target and self.busy_target["template"] not in names:
            missing.append(f"{self.busy_target['template']}（忙碌指示）")
        if missing:
            messagebox.showwarning("執行", "範本不存在：\n" + "\n".join(missing),
                                   parent=self.root)
            return
        checked = [i + 1 for i in flowcheck.busy_check_bad(steps, self.busy_target)]
        if checked:
            # 勾了忙碌檢查卻沒有忙碌指示可查: 擋下, 不讓人以為有在等
            messagebox.showwarning(
                "執行",
                "有步驟勾了「忙碌檢查」，但這份流程沒有設定忙碌指示：\n"
                f"步驟 {', '.join(map(str, checked))}\n"
                "請先在「流程設定…」設定忙碌指示，或取消這些步驟的勾選",
                parent=self.root)
            return
        err = self._flow_error(steps)
        if err:
            messagebox.showwarning("執行", err, parent=self.root)
            return
        # `找圖相連`檢查 (測試選取片段在 test_selected_steps 先以絕對編號擋下)
        bad = [i + 1 for i in self._origin_leaves_bad(steps)]
        if bad:
            messagebox.showwarning(
                "執行",
                "「原點的圖離開」需要原點來自找圖步驟：\n"
                f"步驟 {', '.join(map(str, bad))} 前面最近的原點來自點擊／拖曳"
                "（或沒有原點）。\n請在它前面放找圖步驟當原點，或改用確認圖",
                parent=self.root)
            return
        bad = [i + 1 for i in self._confirm_next_bad(steps)]
        if bad:
            messagebox.showwarning(
                "執行",
                "「點到下一步的圖出現」需要下一個步驟是找圖步驟：\n"
                f"步驟 {', '.join(map(str, bad))} 的下一步不是找圖"
                "（或已是最後一步）。\n請把下一個找圖步驟排在其後",
                parent=self.root)
            return
        if test:
            mode, count = "count", 1
        else:
            mode = "count" if self.run_mode.get() == "執行次數" else "infinite"
            count = self._run_count()
        try:
            self.runner.start(steps, mode, count,
                              scan_region=self.scan_region,
                              calibration=self.flow_cal,
                              busy=self.busy_target,
                              pressed_at=pressed_at)
        except RuntimeError as e:
            messagebox.showwarning("執行", str(e), parent=self.root)
            return
        self._run_steps = steps  # 迷你視窗步驟摘要要對照「實際在跑」的清單
        self._show_mini()  # 隱藏主視窗, 顯示迷你狀態視窗讓出畫面

    def stop_all(self):
        """F12 急停與停止鈕."""
        self.runner.stop()

    def _confirm_next_bad(self, steps):
        """`找圖相連`不成立的「點到下一步的圖出現」步驟索引 (0-based).

        片段恰結束在該步驟時, 片段清單就在此打住 → 自然判為不相連。
        """
        return flowcheck.confirm_next_bad(steps)

    def _origin_leaves_bad(self, steps):
        """「原點的圖離開」但原點不是來自找圖的座標點擊/拖曳索引 (0-based).

        測試選取時傳入的是片段: 原點來源在片段外＝片段內沒有找圖來源, 一樣擋。
        """
        return flowcheck.origin_leaves_bad(steps)

    def _fragment_origin_error(self, steps, base):
        """片段內「執行到時必然沒有原點」的相對座標步驟編號 (完整清單編號)."""
        return [base + k + 1 for k in flowcheck.no_origin(steps)]

    def test_selected_steps(self):
        """測試選取: 只執行清單中選取的連續步驟片段 (單次)."""
        idxs = self._expand_collapsed(self._sel_all())
        if not idxs:
            messagebox.showinfo("測試選取", "請先在步驟清單選取要測試的步驟",
                                parent=self.root)
            return
        lo, hi = idxs[0], idxs[-1]  # 取頭尾涵蓋整段 (跳選也補滿中間)
        bad = self._fragment_origin_error(self.steps[lo:hi + 1], lo)
        if bad:
            messagebox.showwarning(
                "測試選取",
                "以下以原點為基準的步驟（座標點擊、拖曳，或找圖的指定點"
                "以原點為基準）的原點不在選取範圍內，執行時會沒有基準：\n"
                f"步驟 {', '.join(map(str, bad))}\n"
                "請把作為原點的步驟（前面的點擊／拖曳／找圖）一起選進來",
                parent=self.root)
            return
        # `找圖相連`檢查以絕對編號提示 (與原點檢查同慣例); 片段結尾恰是
        # 「點到下一步的圖出現」步驟＝不相連, 要把下一步一起選進來
        bad = [lo + i + 1
               for i in self._origin_leaves_bad(self.steps[lo:hi + 1])]
        if bad:
            messagebox.showwarning(
                "測試選取",
                "「原點的圖離開」需要原點來自找圖步驟：\n"
                f"步驟 {', '.join(map(str, bad))} 的原點不是找圖，或不在選取範圍內。"
                "\n請把作為原點的找圖步驟一起選進來",
                parent=self.root)
            return
        bad = [lo + i + 1 for i in self._confirm_next_bad(self.steps[lo:hi + 1])]
        if bad:
            messagebox.showwarning(
                "測試選取",
                "「點到下一步的圖出現」需要下一個步驟是找圖步驟：\n"
                f"步驟 {', '.join(map(str, bad))} 的下一步不是找圖，"
                "或不在選取範圍內。\n請把緊接的下一個找圖步驟一起選進來",
                parent=self.root)
            return
        self.log_ui(f"測試執行步驟 {lo + 1}～{hi + 1}", "info")
        self.start_run(steps=self.steps[lo:hi + 1], test=True)

    def _show_mini(self):
        """執行中的迷你狀態視窗: 置頂、可拖曳, 讓使用者知道程式仍在運作."""
        mx1, my1, mx2, my2 = win.monitor_work_area(self.root.winfo_id())
        self._was_zoomed = self.root.state() == "zoomed"
        self.root.withdraw()
        m = tk.Toplevel(self.root)
        m.overrideredirect(True)
        m.attributes("-topmost", True)
        m.configure(bg=C["accent"])  # 外框 1px 綠邊
        inner = tk.Frame(m, bg=C["panel"])
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        row1 = tk.Frame(inner, bg=C["panel"])
        row1.pack(fill="x")

        tk.Label(row1, text="●", bg=C["panel"], fg=C["accent"], font=FONT).pack(
            side="left", padx=(10, 4), pady=(4, 0))
        # 固定寬度: 文字隨輪次變長時視窗才不會跟著變寬 (右下角定位會超出螢幕)
        self._mini_lbl = tk.Label(row1, text="執行中…", bg=C["panel"],
                                  fg=C["text"], font=FONT, width=21, anchor="w")
        self._mini_lbl.pack(side="left", pady=(4, 0))
        tk.Button(row1, text="■ 停止", command=self.stop_all,
                  bg=C["panel"], fg=C["danger"], activebackground=C["sel"],
                  activeforeground=C["danger"], bd=0, font=FONT,
                  cursor="hand2").pack(side="left", padx=(12, 4))
        tk.Label(row1, text="F12 急停", bg=C["panel"], fg=C["muted"],
                 font=("Microsoft JhengHei UI", 9)).pack(side="left", padx=(0, 10))

        # 第二行: 目前執行到哪一步 + 重複區段次數 (固定寬度, 過長截斷)
        self._mini_step = tk.Label(inner, text="", bg=C["panel"], fg=C["text"],
                                   font=("Microsoft JhengHei UI", 9),
                                   width=42, anchor="w")
        self._mini_step.pack(fill="x", padx=(28, 10), pady=(0, 2))

        # 第三行: 即時最新紀錄 (分岔走哪支、重複第幾次、找到與否…), 依等級上色
        self._mini_log = tk.Label(inner, text="", bg=C["panel"], fg=C["muted"],
                                  font=("Microsoft JhengHei UI", 9),
                                  width=42, anchor="w")
        self._mini_log.pack(fill="x", padx=(28, 10), pady=(0, 6))

        drag = {}

        def d_start(e):
            drag.update(x=e.x_root - m.winfo_x(), y=e.y_root - m.winfo_y())

        def d_move(e):
            m.geometry(f"+{e.x_root - drag['x']}+{e.y_root - drag['y']}")

        for wdg in (inner, row1, self._mini_lbl, self._mini_step, self._mini_log):
            wdg.bind("<ButtonPress-1>", d_start)
            wdg.bind("<B1-Motion>", d_move)

        # 預設放在主視窗所在螢幕的右下角 (工作區內, 不擋工作列)
        # 注意要用 reqwidth/reqheight: 映射前 winfo_width 還不是最終尺寸
        m.update_idletasks()
        m.geometry(f"+{mx2 - m.winfo_reqwidth() - 16}+{my2 - m.winfo_reqheight() - 16}")
        self._mini = m

    def _step_text(self, st):
        """迷你視窗第二行: 重複區段次數 + 目前步驟摘要, 過長截斷."""
        parts = []
        loops = st.get("loops", [])
        if loops:  # 巢狀重複由外到內, 讓使用者分辨跑到第幾輪重複
            parts.append("重複 " + "›".join(f"{c}/{t}" for c, t in loops))
        i = st.get("step", 0)
        run_steps = getattr(self, "_run_steps", None) or self.steps
        if 1 <= i <= len(run_steps):
            s = run_steps[i - 1]
            parts.append(f"步驟{i}/{st['stepTotal']}［{STEP_LABELS[s['type']]}］"
                         f"{step_desc(s)}")
        text = "　".join(parts)
        return text[:40] + "…" if len(text) > 41 else text

    def _close_mini(self):
        if self._mini is None:
            return
        try:
            self._mini.destroy()
        except tk.TclError:
            pass
        self._mini = None
        if getattr(self, "_was_zoomed", False):
            self.root.state("zoomed")  # 直接以最大化映射 (deiconify 會遺失且二次重繪)
        else:
            self.root.deiconify()
        self.root.lift()

    # ================= 紀錄 / 輪詢 =================

    def log_ui(self, msg, level="info"):
        self._append_log(time.strftime("%H:%M:%S"), level, msg)

    def _append_log(self, t, level, msg):
        txt = self.log_text
        txt.configure(state="normal")
        txt.insert("end", t + " ", ("time",))
        txt.insert("end", msg + "\n", (level,))
        if int(txt.index("end-1c").split(".")[0]) > 500:
            txt.delete("1.0", "100.0")
        txt.see("end")
        txt.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _poll(self):
        # 背景引擎載入的狀態轉變在這裡 (UI 執行緒) 觀察與處理
        if self.hub.state != self._engine_state_seen:
            self._engine_state_seen = self.hub.state
            self._on_engine_state(self.hub.state)
        self.drain_preload()
        st = self.runner.status()
        running = st["running"]
        self.recognition.want(self.btn_run, not running)   # 辨識中反灰由背景辨識入口管
        self.btn_stop.configure(state="normal" if running else "disabled")
        if running:
            total = st["totalRounds"]
            if st["round"] == 0:
                text = ("等待準備範本完成…" if st.get("prerun") == "templates"
                        else "倒數啟動中…")
            elif total:
                text = f"執行中　第 {st['round']}/{total} 輪"
            else:
                text = f"執行中　第 {st['round']} 輪"
            self.status_lbl.configure(text=text, foreground=C["accent"])
            if self._mini is not None:
                self._mini_lbl.configure(text=text)
                self._mini_step.configure(text=self._step_text(st))
        else:
            self._close_mini()
            if self.recognition.holds(self.root):
                self.status_lbl.configure(text=recognition.BUSY_TEXT,
                                          foreground=C["warn"])
            elif self.hub.state == enginehub.LOADING:
                self.status_lbl.configure(text="引擎載入中…",
                                          foreground=C["warn"])
            elif self.hub.state == enginehub.FAILED:
                self.status_lbl.configure(text="引擎載入失敗",
                                          foreground=C["danger"])
            else:
                self.status_lbl.configure(text="待機", foreground=C["muted"])

        latest = None
        for e in self.runner.logs_since(self.last_seq):
            self.last_seq = e["seq"]
            self._append_log(e["t"], e["level"], e["msg"])
            latest = e
        # 迷你視窗即時顯示最新一條紀錄 (階段轉換都在這裡冒出來)
        if latest is not None and self._mini is not None:
            msg = latest["msg"]
            self._mini_log.configure(
                text=(msg[:40] + "…") if len(msg) > 41 else msg,
                fg=LOG_COLORS.get(latest["level"], C["muted"]))

        self.root.after(300, self._poll)

    def _fuse_check(self):
        """全域保險絲: 「握有 grab 的視窗不可見」連續超過門檻 → 自動救回.

        正常運作時永不觸發——觸發紀錄即機制有洞的證據, 日誌是修洞的線索。
        清場 (拾取) 進行中不觸發; 秒級輪詢, 負載可忽略。
        """
        try:
            holder = ui_theme.safe_grab_current(self.root)
            if (holder is None or ui_grab.coord.clearing
                    or not holder.winfo_exists() or holder.winfo_viewable()):
                self._fuse_miss = 0
            else:
                self._fuse_miss += 1
                if self._fuse_miss >= FUSE_TRIP:
                    applog.log("fuse.trigger", win=ui_grab.wname(holder),
                               seconds=self._fuse_miss)
                    self.log_ui("偵測到隱形視窗持有輸入焦點，已自動救回"
                                "（詳見日誌檔）", "warn")
                    self._fuse_miss = 0
                    try:
                        holder.deiconify()
                        holder.lift()
                        holder.focus_force()
                    except tk.TclError:
                        pass
        except tk.TclError:
            self._fuse_miss = 0
        self.root.after(FUSE_INTERVAL_MS, self._fuse_check)

    def _on_callback_error(self, etype, value, tb):
        import traceback
        traceback.print_exception(etype, value, tb)  # 原始碼執行時仍印到主控台
        # 主視窗隱藏時紀錄面板看不到 → 一併落地到日誌檔, 事後可查
        applog.exception("callback.error", etype, value, tb)
        try:
            frame = traceback.extract_tb(tb)[-1]
            where = f"{os.path.basename(frame.filename)}:{frame.lineno}"
            self.log_ui(f"內部錯誤: {etype.__name__}: {value}（{where}）", "error")
        except Exception:
            pass

    def on_close(self):
        if self.runner.status()["running"]:
            if not messagebox.askyesno("離開", "流程執行中，確定停止並離開？",
                                       parent=self.root):
                return
            self.stop_all()
        if not self.confirm_discard("離開"):
            return
        self.root.destroy()


def main():
    win.set_dpi_aware()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
