"""AutoClick — 按鍵精靈 (本機桌面版)

核心: 找圖點擊 + 步驟序列自動執行, F12 急停.
辨識走主體偵測引擎 (兩階段: 粗篩＋深度驗證); 匹配門檻由 profile config
統一管理 (match_threshold / verify_threshold), 步驟層級沒有門檻 (ADR 0002)。

**一份`流程`＝一個自包自足的存檔** (ADR 0006): 步驟與它引用的每一張範本圖都在
同一個檔案裡, 複製檔案就搬完整份流程。本機沒有範本庫; 編輯與執行時 app 把存檔
解到 profile 底下的**工作區**給引擎讀 (格式與工作區規則全在 flowfile)。
"""
import json
import os
import re
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

import profile_store

if getattr(sys, "frozen", False):
    # 打包版: DINOv2 hub 程式碼與權重隨包 (_internal/torch_home), 目標機
    # 免網路免下載; 須在引擎載入驗證模型之前設定
    os.environ.setdefault("TORCH_HOME", os.path.join(sys._MEIPASS, "torch_home"))
else:
    # 原始碼執行時引擎在 repo 的 src/ 下 (未安裝進環境也能啟動)
    sys.path.insert(0, os.path.join(profile_store.data_root(), "src"))

import applog
import calibration
import enginehub
import flowfile
import ui_dialogs
import ui_grab
import ui_overlay
import ui_theme
from automation import capture, findtarget, flowfmt, hotkey, imgio, win
from automation.runner import (Runner, branch_layout, confirm_next_connected,
                               origin_source, uses_confirm_next,
                               uses_origin_leaves)
from ui_theme import C, FONT, FONT_MONO

PROFILES_DIR = profile_store.profiles_root()
DEFAULT_PROFILE = "arknights"

STEP_LABELS = {
    "find_click": "找圖點擊",
    "click": "座標點擊",
    "drag": "滑鼠拖曳",
    "wait": "等待",
    "key": "按鍵",
    "loop_start": "重複開始",
    "loop_end": "重複結束",
    "branch_start": "分岔開始",
    "branch_or": "分岔（或）",
    "branch_end": "分岔結束",
}
# 新增時直接加入清單的標記步驟 (無需開對話框)
MARKER_TYPES = {"loop_end", "branch_start", "branch_or", "branch_end"}
# 標記步驟中仍可編輯屬性的 (區段結尾: 設定「找不到跳出到此」的後續動作)
EDITABLE_MARKERS = {"loop_end", "branch_end"}
BTN_ZH = {"left": "左鍵", "right": "右鍵", "middle": "中鍵"}
# 步驟清單 │ 連線顏色: 依隸屬區塊 (重複=warn, 分岔=info)
GUIDE_COLORS = {"loop_start": C["warn"], "branch_start": C["info"]}
# 動作標籤［…］的顏色: 一眼區分步驟類型 (重複/分岔標記沿用整列顏色)
LABEL_COLORS = {
    "find_click": C["info"],
    "click": C["accent"],
    "drag": "#A78BFA",
    "wait": C["muted"],
    "key": "#F472B6",
}
# 執行紀錄各等級的文字色 (執行紀錄面板與迷你狀態視窗共用)
LOG_COLORS = {"info": "#CBD5E1", "ok": C["accent"],
              "warn": C["warn"], "error": C["danger"]}

# 全域保險絲: 每 FUSE_INTERVAL_MS 檢查一次, 連續 FUSE_TRIP 次
# 「grab 持有者不可見」(且不在清場中) 即自動救回
FUSE_INTERVAL_MS = 1000
FUSE_TRIP = 3


def _pointer_confirm_desc(s):
    """座標點擊/拖曳的`生效確認`摘要 (沒設＝空字串)."""
    mode = s.get("confirm", "none")
    what = {"appear": f"確認圖「{findtarget.confirm_template(s) or '?'}」"
                      f"{findtarget.tag_text(findtarget.confirm_target(s))}出現",
            "next": "下一步的圖出現",
            "gone": "原點的圖離開"}.get(mode)
    if what is None:
        return ""
    nf = {"skip": "跳過", "break": "跳出"}.get(s.get("onNotFound"), "停止")
    return f"，做到{what}（逾時{float(s.get('timeout', 10)):g}s→{nf}）"


def step_desc(s):
    t = s["type"]
    if t == "click":
        if s.get("mode", "abs") == "prev":
            pos = f"上一步點擊 ({int(s['x']):+d}, {int(s['y']):+d})"
        else:
            pos = f"範圍內 ({s['x']}, {s['y']})"
        uo = "，不更新原點" if not s.get("updateOrigin", True) else ""
        return (f"{pos} {BTN_ZH.get(s.get('button', 'left'))}×{s.get('clicks', 1)}"
                f"{uo}{_pointer_confirm_desc(s)}")
    if t == "find_click":
        act = {"click": "點擊", "none": "僅等待出現",
               "wait_gone": "等待消失"}.get(s.get("action", "click"), "點擊")
        nf = {"stop": "停止", "break": "跳出"}.get(s.get("onNotFound"), "跳過")
        cfm = {"gone": "，點到消失", "appear": "，點到確認圖出現",
               "next": "，點到下一步的圖出現"}.get(s.get("confirm"), "")
        if s.get("confirm") == "appear":
            cfm += findtarget.tag_text(findtarget.confirm_target(s))
        if s.get("action") == "wait_gone" and s.get("appearLimitMs"):
            act += f"（出現等候上限 {int(s['appearLimitMs'])}ms）"
        ox, oy = int(s.get("offsetX", 0)), int(s.get("offsetY", 0))
        off = f"，偏移({ox:+d}, {oy:+d})" if ox or oy else ""
        uo = "，不更新原點" if not s.get("updateOrigin", True) else ""
        return (f"{findtarget.template(s) or '?'}"
                f"{findtarget.tag_text(findtarget.target(s))} → {act}{off}{cfm}{uo}"
                f"（逾時{s.get('timeout', 10)}s→{nf}）")
    if t == "drag":
        if s.get("mode", "abs") == "prev":
            pos = (f"上一步 ({int(s['x1']):+d}, {int(s['y1']):+d}) → "
                   f"({int(s['x2']):+d}, {int(s['y2']):+d})")
        else:
            pos = f"({s['x1']}, {s['y1']}) → ({s['x2']}, {s['y2']})"
        hd = f" 停{s.get('holdMs')}ms" if s.get("holdMs") else ""
        return (f"{pos} {BTN_ZH.get(s.get('button', 'left'))} {s.get('ms', 300)}ms"
                f"{hd}{_pointer_confirm_desc(s)}")
    if t == "wait":
        return f"{s.get('ms', 0)} ms"
    if t == "key":
        return s.get("keys", "")
    if t == "loop_start":
        return f"×{s.get('count', 1)} 次"
    if t == "branch_start":
        return "每個分支以找圖開頭，先找到誰就走誰"
    if t == "branch_or":
        return "── 或 ──"
    if t in ("loop_end", "branch_end"):
        if s.get("onBreak") == "break":
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


class HScrollStrip(ttk.Frame):
    """單列橫向捲動容器: 內容超出寬度時可用滑鼠滾輪橫向捲動.

    子元件加到 `.inner`. 用於工具列在窄視窗時容納次要按鈕: 該列會縮小,
    捲動即可找到被擠出去的按鈕, 不必放大視窗.
    """

    def __init__(self, master, height=26, **kw):
        super().__init__(master, **kw)
        self._wheel_bound = set()  # 已綁滾輪的 widget, 避免重複累加
        self.canvas = tk.Canvas(self, height=height, bg=C["panel"],
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas, style="Panel.TFrame")
        self._win = self.canvas.create_window(0, 0, anchor="nw", window=self.inner)
        self.inner.bind("<Configure>", lambda e: (
            self.canvas.configure(scrollregion=self.canvas.bbox("all")),
            self._bind_wheel(self.inner)))  # 新加的子元件也要能觸發滾輪
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._win, height=e.height))
        self._bind_wheel(self.canvas)

    def _bind_wheel(self, widget):
        """把橫向滾輪綁到 widget 及其所有子孫 (直接綁, 不動全域 bind_all).

        直接綁在按鈕上, 游標停在按鈕上滾動也有效; 也不會影響步驟清單的垂直捲動.
        """
        if str(widget) not in self._wheel_bound:
            widget.bind("<MouseWheel>", self._on_wheel, add=True)
            self._wheel_bound.add(str(widget))
        for c in widget.winfo_children():
            self._bind_wheel(c)

    def _on_wheel(self, e):
        # 內容比視窗窄就不必捲動 (bbox 寬度 <= 視窗寬度)
        bbox = self.canvas.bbox("all")
        if bbox and bbox[2] > self.canvas.winfo_width():
            self.canvas.xview_scroll(-1 if e.delta > 0 else 1, "units")
        return "break"


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
    # 目前流程的`校準對`與`基準距離` {pair, baseline}; None＝沒有 (不能執行)
    flow_cal = None
    # 編輯器的`畫面倍率`: 開流程/切換流程時為 1, 按「校準」才更新
    editor_scale = 1.0
    # 流程層級的`補做間隔` (毫秒) 與`忙碌指示` (找圖目標或 None), ADR 0008
    retry_interval_ms = flowfile.RETRY_DEFAULT_MS
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

        # ---- profile: 上次選用的 (無記錄用 arknights, 再無則建立) ----
        state = profile_store.load_state(PROFILES_DIR)
        names = profile_store.list_profiles(PROFILES_DIR)
        name = state.get("profile")
        if name not in names:
            name = DEFAULT_PROFILE if DEFAULT_PROFILE in names else (
                names[0] if names else None)
        if name is None:
            profile_store.create_profile(PROFILES_DIR, DEFAULT_PROFILE)
            name = DEFAULT_PROFILE
        self.profile_name = name
        self.profile_dir = os.path.join(PROFILES_DIR, name)
        # 工作區＝當前流程的可重建快取 (解出來的範本圖 + 引擎登錄產物)
        self.ws = flowfile.Workspace(self.profile_dir)
        self.ws.ensure()
        self._pending_templates = set()  # 已落地、重探索延後中的新範本名
        self._rereg_after = None         # 延後重探索的 after id
        # 輕量探索先行 (不需引擎): 範本面板/清單立即可用;
        # 引擎在背景載入, 完成/失敗由 _poll 觀察 hub 狀態
        self.profile = self.hub.discover(*self._engine_source())
        self._engine_state_seen = enginehub.LOADING
        threading.Thread(target=lambda: self.hub.load(*self._engine_source()),
                         daemon=True).start()

        root.title("AutoClick — 按鍵精靈")
        root.geometry("1120x700")
        root.minsize(900, 560)
        ui_theme.apply(root)

        self._build_menu()
        self._build_toolbar()
        self._build_main()

        self.log_ui("引擎載入中…（就緒前，執行／比對測試等辨識功能暫不可用）")

        self._load_autosave()
        self.refresh_templates()
        self.render_steps()
        self._update_cal_ui()
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
            # 以「當下的工作區」重新探索: 背景載入期間使用者可能已切換
            # profile/流程或增刪範本, 不能拿背景那份舊快照直接覆蓋
            self.profile = self.hub.refresh(*self._engine_source())
            for msg in self.hub.warnings:
                self.log_ui(f"引擎警告: {msg}", "warn")
            if self.hub.coarse_only:
                self.log_ui("驗證模型未載入 → 降級為 coarse-only"
                            "（僅粗篩，精度較低）", "warn")
                messagebox.showwarning(
                    "引擎降級", "驗證模型載入失敗，找圖只跑粗篩（coarse-only），"
                    "精度較低。\n請檢查 torch 與模型權重是否完整。",
                    parent=self.root)
            self.log_ui(f"引擎就緒　profile: {self.profile_name}"
                        f"（本流程 {len(self.ws.names())} 個範本）", "ok")
            self.refresh_templates()
        elif state == enginehub.FAILED:
            # 檔案日誌由 hub.load() 落 (engine.load.failed), 這裡只做 UI
            self.log_ui(f"引擎載入失敗: {self.hub.error}", "error")
            messagebox.showerror(
                "引擎載入失敗",
                f"引擎載入失敗，辨識功能無法使用：\n{self.hub.error}",
                parent=self.root)

    # ================= profile =================

    @property
    def flows_dir(self):
        return flowfile.flows_dir(self.profile_dir)

    def _engine_source(self):
        """交給引擎的範本來源: (工作區, 引擎參數所在的 profile).

        引擎看得到的就是本流程的範本 (校準對也是本流程的範本, ADR 0009)。
        """
        self.ws.ensure()   # 工作區只是快取, 被刪掉就重建
        return (self.ws.root, self.profile_dir)

    def reload_profile(self):
        """重新探索當前工作區 (輕量, 不讀登錄產物): 新增/修改範本後呼叫.

        清單立即反映、既有登錄產物失效; 產物由`範本預載`/單張載入在
        使用當下重載 (ADR 0004), 這裡不做任何登錄、不需引擎。
        """
        self.profile = self.hub.refresh(*self._engine_source())

    def switch_profile(self, name):
        """切換 profile: 流程草稿、範本面板、引擎查詢對象一致跟隨.

        每個 profile 有自己的工作區, 所以切回來時該 profile 上次編到一半的
        流程 (草稿＋工作區的圖) 還在。
        """
        if name == self.profile_name:
            return
        if self.runner.status()["running"]:
            messagebox.showwarning("切換 profile", "流程執行中，請先停止再切換",
                                   parent=self.root)
            self.profile_cb.set(self.profile_name)
            return
        self._autosave()  # 先把目前流程的草稿存回原 profile
        # 舊 profile 延後中的重探索作廢: 圖已落地, 下次載入該 profile 會探索
        self._cancel_reregister()
        self._pending_templates.clear()
        prev = (self.profile_name, self.profile_dir, self.ws, self.profile)
        self.profile_name = name
        self.profile_dir = os.path.join(PROFILES_DIR, name)
        self.ws = flowfile.Workspace(self.profile_dir)
        try:
            self.reload_profile()
        except Exception as e:
            # 載入失敗就整組還原, 也不記錄狀態——否則面板/查詢對象指向
            # 新 profile 的殘破狀態, 下次啟動還會直接踩同一個雷
            self.profile_name, self.profile_dir, self.ws, self.profile = prev
            self.hub.profile = self.profile
            self.profile_cb.set(self.profile_name)
            messagebox.showerror("切換 profile",
                                 f"載入失敗，維持原 profile：{e}",
                                 parent=self.root)
            return
        profile_store.save_state(PROFILES_DIR, {"profile": name})
        self.profile_cb.set(name)
        self._collapsed.clear()
        self._apply_flow({"steps": [], flowfmt.COORD_SPACE: flowfmt.REGION})
        self._load_autosave()  # 該 profile 的流程草稿隨 profile 走
        self.refresh_templates()
        self.render_steps()
        self.log_ui(f"已切換 profile →「{name}」"
                    f"（本流程 {len(self.ws.names())} 個範本）", "ok")

    def refresh_profile_ui(self):
        """重新掃工作區並讓登錄產物失效: 工作區被外力動過之後按這顆, 不必重啟."""
        try:
            self.reload_profile()
        except Exception as e:
            messagebox.showerror("重新整理", f"重新探索失敗: {e}", parent=self.root)
            return
        self.refresh_templates()
        self.render_steps()
        self.log_ui(f"已重新整理本流程的範本（{len(self.ws.names())} 個；"
                    "登錄產物將於使用時載入）", "ok")

    def create_profile_ui(self):
        name = ui_dialogs.ask_string(self.root, "建立新 profile",
                                     "輸入新 profile 名稱（一個遊戲一個）：")
        if name is None:
            return
        try:
            profile_store.create_profile(PROFILES_DIR, name.strip())
        except ValueError as e:
            messagebox.showwarning("建立 profile", str(e), parent=self.root)
            return
        self.profile_cb.configure(
            values=profile_store.list_profiles(PROFILES_DIR))
        self.switch_profile(name.strip())
        self.log_ui(f"已建立 profile「{name.strip()}」（預設 config 已帶入）", "ok")

    # ================= 校準 (`校準對` / `畫面倍率`, ADR 0009) =================
    # 校準對與基準距離住在流程存檔裡 (self.flow_cal)。編輯器的倍率只屬於「這次
    # 編輯這份流程」: 開流程/切換流程時回到 1, 使用者按「校準」才更新——拾取的
    # 座標與截下的範本都除以它換回`流程尺度`。量測的純邏輯在 calibration 模組。

    def _update_cal_ui(self):
        """校準按鈕常駐顯示目前的編輯器倍率; 旁邊寫出這份流程的校準對."""
        if getattr(self, "cal_btn", None) is None:
            return
        self.cal_btn.configure(text=f"校準　×{self.editor_scale:.2f}")
        cal = self.flow_cal
        if cal:
            text = (f"校準對：{cal['pair'][0]} × {cal['pair'][1]}"
                    f"（{float(cal['baseline']):.0f}px）")
        else:
            text = "這份流程還沒有校準對（不能執行）"
        self.cal_info.configure(text=text)

    def _calibration_screen(self, names, title):
        """校準量測用的截圖: 範本就位 → 清場 → 依搜尋範圍截圖.

        範本是本流程的範本 (校準對就是流程的範本); 有不在本流程裡的就提示並
        回傳 None。量測前的提示都在清場「之前」彈 (清場中彈窗會隱形卡死)。
        """
        self.ensure_registered()
        for name in dict.fromkeys(names):
            if name not in self.profile.templates:
                messagebox.showwarning(
                    title, f"找不到校準圖：{name}\n（這張範本已不在本流程裡）",
                    parent=self.root)
                return None
            try:
                self.hub.ensure_template(name)
            except Exception as e:
                messagebox.showwarning(title, f"校準圖載入失敗：{name}（{e}）",
                                       parent=self.root)
                return None
        with ui_overlay.screen_clear(self.root):
            self.root.update()
            time.sleep(0.12)
            screen, _ = capture.grab(self.scan_region)
        return screen

    def _pair_distance(self, screen, pair, title):
        """在截圖上量一對圖的中心距離; 量不到或重疊時提示並回傳 None.

        查詢不帶預期尺度 (`calibration.measure`): 倍率差很多也量得到。
        """
        m = calibration.measure(self.detector.query, screen, pair)
        if m.missing:
            messagebox.showwarning(
                title, "畫面上找不到：" + "、".join(m.missing) +
                "\n請切換到兩張圖同時出現的畫面後重試（原本的設定維持不動）",
                parent=self.root)
            return None
        if m.too_close:
            messagebox.showwarning(
                title, "兩張圖的位置重疊，無法作為比例尺，"
                "請改用一對距離較遠的範本", parent=self.root)
            return None
        return m.distance

    def designate_pair(self):
        """設定 (或更換) 這份流程的`校準對`.

        還沒有校準對: 當下的畫面就是`流程尺度` (倍率 1), 量到的距離＝基準距離。
        已有校準對: 先用舊的那對量出倍率, 新的基準距離＝新距離 ÷ 倍率——換對
        不改變流程尺度; 舊對量不到就拒絕 (寫進錯的基準距離, 整份流程就點偏)。
        兩對在同一張截圖上量。任何一步失敗都不改動原本的校準資料。
        """
        if not self.engine_gate():
            return
        pair = ui_dialogs.pick_cal_pair(self)
        if not pair:
            return
        title = "設定校準對"
        old = self.flow_cal
        screen = self._calibration_screen(
            [*pair, *(old["pair"] if old else ())], title)
        if screen is None:
            return
        k = 1.0
        if old:
            d_old = self._pair_distance(screen, old["pair"], "設定校準對"
                                        "（先用原本的校準對量倍率）")
            if d_old is None:
                return
            k = calibration.snap_identity(d_old / float(old["baseline"]))
        dist = self._pair_distance(screen, list(pair), title)
        if dist is None:
            return
        self.flow_cal = calibration.make(pair, dist / k)
        self.editor_scale = k
        self._autosave()
        self._update_cal_ui()
        self.log_ui(f"已設定校準對「{pair[0]}」×「{pair[1]}」，"
                    f"基準距離 {dist / k:.1f}px（目前畫面倍率 ×{k:.3f}）", "ok")

    def calibrate_now(self):
        """`校準`: 用這份流程的校準對量一次, 更新編輯器倍率.

        失敗時保留原本的倍率 (切到兩張圖都看得到的畫面重試即可)。
        """
        cal = self.flow_cal
        if cal is None:
            messagebox.showinfo("校準", "這份流程還沒有校準對，"
                                "請先按「設定校準對」", parent=self.root)
            return
        if not self.engine_gate():
            return
        screen = self._calibration_screen(cal["pair"], "校準")
        if screen is None:
            return
        dist = self._pair_distance(screen, cal["pair"], "校準")
        if dist is None:
            return
        self.editor_scale = calibration.snap_identity(
            dist / float(cal["baseline"]))
        self._update_cal_ui()
        self.log_ui(f"校準完成：畫面倍率 ×{self.editor_scale:.3f}"
                    f"（目前距離 {dist:.1f}px ÷ 基準 {float(cal['baseline']):.1f}px）"
                    "；拾取的座標與截下的範本會換回流程尺度", "ok")

    # ================= `補做`設定 (補做間隔 / 忙碌指示, ADR 0008) =================

    def _update_retry_ui(self):
        """流程設定區顯示目前的補做間隔與忙碌指示."""
        if getattr(self, "busy_lbl", None) is None:
            return
        if self.retry_var.get() != str(self.retry_interval_ms):
            self.retry_var.set(str(self.retry_interval_ms))
        tgt = self.busy_target
        # 第三列空間有限: 只寫範本名 (細節在「忙碌指示…」裡看)
        self.busy_lbl.configure(text=tgt["template"] if tgt else "（不設）")

    def _on_retry_change(self):
        """補做間隔欄位改了 → 流程設定跟著改 (不合法的輸入先不理)."""
        try:
            ms = int(self.retry_var.get())
        except ValueError:
            return
        if ms >= 0 and ms != self.retry_interval_ms:
            self.retry_interval_ms = ms
            self._autosave()

    def edit_busy_indicator(self):
        """設定/清除`忙碌指示`: 選範本 (同一個選範本對話框) → 找圖設定.

        已設定時先問要不要清除 (否＝重新設定); 新設定時預設限定在搜尋範圍
        九宮格的下中格 (指示字樣在畫面底部中央)。這次加進來最後沒用到的圖收回。
        """
        cur = self.busy_target
        if cur and messagebox.askyesno(
                "忙碌指示", f"目前的忙碌指示是「{cur['template']}」。\n"
                "要清除嗎？（否＝重新設定）", parent=self.root):
            self.busy_target = None
            self._update_retry_ui()
            self._autosave()
            self.log_ui("已清除忙碌指示（補做只看補做間隔）", "ok")
            return
        before = set(self.list_template_names())
        name = ui_dialogs.pick_template(
            self, "選擇忙碌指示", initial=(cur or {}).get("template"))
        added = [n for n in self.list_template_names() if n not in before]
        if name:
            base = (cur if cur and cur["template"] == name
                    else {"template": name,
                          "limit": {"kind": "grid", "cells": [8]}})

            def test(o, parent):
                ui_dialogs.show_match_test(
                    self, findtarget.make_target(name, **o), hide=(parent,))

            opts = ui_dialogs.edit_target_opts(
                self, self.root, base, "忙碌指示的找圖設定", test_fn=test)
            tgt = findtarget.make_target(name, **opts) if opts else None
            if tgt is not None and findtarget.needs_origin(tgt):
                # 補做前才查、那時的原點不固定: 只能以搜尋範圍為基準
                messagebox.showwarning(
                    "忙碌指示", "忙碌指示的限定範圍與指定點不能以原點為基準，"
                    "請改用九宮格或搜尋範圍", parent=self.root)
            elif tgt is not None:
                self.busy_target = tgt
                self._autosave()
                self.log_ui(f"已設定忙碌指示「{name}」：補做前畫面上有它就先不補",
                            "ok")
        ui_dialogs.discard_unused(self, added, None)
        self._update_retry_ui()

    # ================= UI 建構 =================

    def _build_menu(self):
        kw = dict(bg=C["panel"], fg=C["text"], activebackground=C["sel"],
                  activeforeground=C["text"], bd=0, font=FONT)
        # 工作列直接放指令 (不用下拉選單); 存檔/讀檔走步驟面板按鈕
        menubar = tk.Menu(self.root, **kw)
        menubar.add_command(label="開啟資料夾",
                            command=lambda: os.startfile(self.profile_dir))
        self.root.configure(menu=menubar)
        self.root.bind("<Control-s>", lambda e: self.save_flow())
        self.root.bind("<Control-o>", lambda e: self.open_flow())

    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(12, 8))
        bar.pack(fill="x")

        ttk.Label(bar, text="模式").pack(side="left")
        self.run_mode = ttk.Combobox(bar, width=8, state="readonly",
                                     values=["執行次數", "直到停止"])
        self.run_mode.set("執行次數")
        self.run_mode.pack(side="left", padx=(4, 10))
        self.run_mode.bind("<<ComboboxSelected>>", lambda e: self._mode_ui())

        self.count_lbl = ttk.Label(bar, text="次數")
        self.count_lbl.pack(side="left")
        self.run_count = ttk.Spinbox(bar, from_=1, to=99999, width=6)
        self.run_count.set(1)
        self.run_count.pack(side="left", padx=(4, 10))

        ttk.Label(bar, text="啟動延遲").pack(side="left")
        self.start_delay = ttk.Combobox(bar, width=5, state="readonly",
                                        values=["無", "3 秒", "5 秒", "10 秒"])
        self.start_delay.set("3 秒")
        self.start_delay.pack(side="left", padx=(4, 14))

        self.btn_run = ttk.Button(bar, text="▶ 開始執行", style="Run.TButton",
                                  command=self.start_run)
        self.btn_run.pack(side="left", padx=(0, 6))
        self.btn_stop = ttk.Button(bar, text="■ 停止", style="Stop.TButton",
                                   command=self.stop_all, state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 14))

        self.status_lbl = ttk.Label(bar, text="待機", style="Status.TLabel")
        self.status_lbl.pack(side="left")

        ttk.Label(bar, text="F12 = 急停", foreground=C["muted"]).pack(side="right")

        # 第二列: 全域搜尋範圍 + game profile 切換
        bar2 = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        bar2.pack(fill="x")
        ttk.Label(bar2, text="搜尋範圍").pack(side="left")
        self.scan_lbl = ttk.Label(bar2, text="全螢幕", foreground=C["muted"])
        self.scan_lbl.pack(side="left", padx=(6, 8))
        ttk.Button(bar2, text="框選範圍", style="Accent.TButton",
                   command=self.pick_scan_region).pack(side="left", padx=(0, 6))
        ttk.Button(bar2, text="清除", command=self.clear_scan_region).pack(side="left")
        ttk.Label(bar2, text="（所有找圖步驟與比對測試都只在此範圍內找圖）",
                  foreground=C["muted"]).pack(side="left", padx=(12, 0))

        # 第三列: `校準`常駐按鈕區。前兩列在預設視窗寬度下已無剩餘空間
        # (塞進去會被裁掉), 校準自成一列才保得住「常駐顯示」
        bar3 = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        bar3.pack(fill="x")
        ttk.Label(bar3, text="畫面校準").pack(side="left")
        ttk.Button(bar3, text="設定校準對", style="Small.TButton",
                   takefocus=False,
                   command=self.designate_pair).pack(side="left", padx=(8, 6))
        # 校準按鈕常駐顯示目前的編輯器倍率 (執行時開頭會自動再量一次)
        self.cal_btn = ttk.Button(bar3, text="校準", style="Small.TButton",
                                  takefocus=False, command=self.calibrate_now)
        self.cal_btn.pack(side="left")
        self.cal_info = ttk.Label(bar3, text="", foreground=C["muted"])
        self.cal_info.pack(side="left", padx=(12, 0))
        # 流程層級的`補做`設定 (ADR 0008): 補做間隔 + 忙碌指示 (步驟面板太窄放不下)
        self.busy_lbl = ttk.Label(bar3, text="", foreground=C["muted"])
        self.busy_lbl.pack(side="right", padx=(6, 0))
        ttk.Button(bar3, text="忙碌指示…", style="Small.TButton",
                   takefocus=False,
                   command=self.edit_busy_indicator).pack(side="right")
        ttk.Label(bar3, text="ms").pack(side="right", padx=(2, 12))
        self.retry_var = tk.StringVar(value=str(self.retry_interval_ms))
        ttk.Spinbox(bar3, from_=0, to=10000, increment=100, width=6,
                    textvariable=self.retry_var).pack(side="right")
        ttk.Label(bar3, text="補做間隔").pack(side="right", padx=(16, 4))
        self.retry_var.trace_add("write", lambda *_: self._on_retry_change())

        ttk.Button(bar2, text="＋建立", style="Small.TButton", takefocus=False,
                   command=self.create_profile_ui).pack(side="right")
        self.profile_cb = ttk.Combobox(
            bar2, width=14, state="readonly",
            values=profile_store.list_profiles(PROFILES_DIR))
        self.profile_cb.set(self.profile_name)
        self.profile_cb.bind("<<ComboboxSelected>>",
                             lambda e: self.switch_profile(self.profile_cb.get()))
        self.profile_cb.pack(side="right", padx=(6, 6))
        ttk.Label(bar2, text="Profile").pack(side="right")

    def _mode_ui(self):
        state = "normal" if self.run_mode.get() == "執行次數" else "disabled"
        self.run_count.configure(state=state)

    def pick_scan_region(self):
        r = ui_overlay.pick(self.root, "region", "拖曳框選搜尋範圍（執行時只在此範圍內找圖）")
        if r:
            self.set_scan_region([r["screenX"], r["screenY"], r["w"], r["h"]])
        else:
            self._update_region_preview()

    def clear_scan_region(self):
        self.set_scan_region(None)

    def set_scan_region(self, region):
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
        main = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=5)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=1)

        # ---- 左: 步驟 ----
        left = ttk.Frame(main, style="Panel.TFrame", padding=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.rowconfigure(2, weight=1)
        left.columnconfigure(0, weight=1)

        head = ttk.Frame(left, style="Panel.TFrame")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(head, text="執行步驟", style="Title.TLabel").pack(side="left")

        # 「新增步驟」最高優先: 先 pack 到最右, 窄視窗時保留可見
        add_btn = ttk.Menubutton(head, text="＋ 新增步驟")
        add_menu = tk.Menu(add_btn, tearoff=0, bg=C["panel"], fg=C["text"],
                           activebackground=C["sel"], activeforeground=C["text"],
                           bd=0, font=FONT)
        for t in ("find_click", "click", "drag", "wait", "key"):
            add_menu.add_command(label=STEP_LABELS[t],
                                 command=lambda t=t: self.add_step(t))
        add_menu.add_separator()
        for t in ("loop_start", "loop_end"):
            add_menu.add_command(label=STEP_LABELS[t],
                                 command=lambda t=t: self.add_step(t))
        add_menu.add_separator()
        for t in ("branch_start", "branch_or", "branch_end"):
            add_menu.add_command(label=STEP_LABELS[t],
                                 command=lambda t=t: self.add_step(t))
        add_btn.configure(menu=add_menu)
        add_btn.pack(side="right")

        # 新流程/存檔/讀檔/清除: 小按鈕放進橫向捲動列, 窄視窗時縮小、滾輪捲動找到
        # (「匯出」已移除: 存檔本身就是可搬移的檔, 要給別人直接複製檔案)
        strip = HScrollStrip(head)
        strip.pack(side="left", fill="x", expand=True, padx=(8, 6))
        for text, cmd in (("新流程", self.new_flow),
                          ("存檔", self.save_flow), ("讀檔", self.open_flow),
                          ("清除", self.clear_steps),
                          ("測試選取", self.test_selected_steps)):
            ttk.Button(strip.inner, text=text, style="Small.TButton",
                       command=cmd, takefocus=False).pack(side="left", padx=(0, 4))

        opts = ttk.Frame(left, style="Panel.TFrame")
        opts.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.avoid_hover = tk.BooleanVar(value=False)
        ui_dialogs._check(opts, "找圖前移開滑鼠（避免 hover 干擾）",
                          self.avoid_hover).pack(side="left")
        self.step_list = SegListbox(
            left, bg=C["bg"], fg=C["text"], selectbackground=C["sel"],
            font=FONT, bd=0,
            highlightthickness=1, highlightbackground=C["border"],
            highlightcolor=C["accent"])  # 支援 Ctrl/Shift 多選
        self.step_list.drag_guard = (
            lambda: getattr(self, "_drag_idxs", None) is not None)
        self.step_list.press_keep = self._on_handle
        self.step_list.grid(row=2, column=0, sticky="nsew")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.step_list.yview)
        sb.grid(row=2, column=1, sticky="ns")
        self.step_list.configure(yscrollcommand=sb.set)
        self.step_list.bind("<Double-Button-1>", self._on_step_double)
        self.step_list.bind("<Delete>", lambda e: self.del_step())
        self.step_list.bind("<Control-c>", lambda e: (self.copy_steps(), "break")[1])
        self.step_list.bind("<Control-v>", lambda e: (self.paste_steps(), "break")[1])

        # 選取列顯示列內圖示操作; 左側 ≡ 把手可拖曳調整順序
        self._step_icons = RowIcons(self.step_list, [
            ("✎", "編輯", lambda i: self.edit_step()),
            ("⧉", "複製", lambda i: self.dup_step()),
            ("▲", "上移", lambda i: self.move_step(-1)),
            ("▼", "下移", lambda i: self.move_step(1)),
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

        # ---- 右 ----
        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=3)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        # 範本
        tp = ttk.Frame(right, style="Panel.TFrame", padding=10)
        tp.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        tp.rowconfigure(2, weight=1)
        tp.columnconfigure(0, weight=1)
        tp.columnconfigure(2, weight=1)

        thead = ttk.Frame(tp, style="Panel.TFrame")
        thead.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        # 面板列的是「本流程的範本」——一眼看得出這份流程帶了哪些圖 (ADR 0006)
        ttk.Label(thead, text="本流程的範本", style="Title.TLabel").pack(side="left")
        ttk.Button(thead, text="截圖框選", style="Accent.TButton",
                   command=lambda: self.capture_template()).pack(side="right")
        ttk.Button(thead, text="上傳圖片",
                   command=self.upload_template).pack(side="right", padx=(0, 6))

        self._tmpl_names = []     # 清單目前列出的範本名 (平面, 無資料夾層級)
        self.tmpl_list = tk.Listbox(
            tp, bg=C["bg"], fg=C["text"], selectbackground=C["sel"],
            selectforeground=C["text"], font=FONT_MONO, bd=0,
            highlightthickness=1, highlightbackground=C["border"],
            highlightcolor=C["accent"], activestyle="none", width=24)
        tsb = ttk.Scrollbar(tp, orient="vertical", command=self.tmpl_list.yview)
        self.tmpl_list.configure(yscrollcommand=tsb.set)
        self.tmpl_list.grid(row=2, column=0, sticky="nsew")
        tsb.grid(row=2, column=1, sticky="ns", padx=(0, 8))
        self.tmpl_list.bind("<<ListboxSelect>>", self._on_tmpl_select)
        self.tmpl_list.bind("<Double-Button-1>", lambda e: self.rename_template())
        self._tmpl_icons = RowIcons(self.tmpl_list, [
            ("✎", "重新命名", lambda i: self.rename_template()),
            ("✕", "刪除", lambda i: self.del_template()),
        ])

        pv = ttk.Frame(tp, style="Panel.TFrame")
        pv.grid(row=2, column=2, sticky="nsew")
        self.thumb_lbl = tk.Label(pv, bg=C["bg"], bd=0,
                                  highlightthickness=1,
                                  highlightbackground=C["border"])
        self.thumb_lbl.pack(fill="both", expand=True)
        self.thumb_info = ttk.Label(pv, text="", style="Muted.TLabel")
        self.thumb_info.pack(anchor="w", pady=(4, 0))

        # 按鈕重要性一致: 全放進橫向捲動列, 窄視窗時縮小、滾輪捲動找到
        tops = HScrollStrip(tp)
        tops.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        # (「＋資料夾」已移除: 一份流程的範本是平面清單, 不需要命名空間)
        for text, cmd in (("比對測試", self.test_template),
                          ("複製", self.copy_template),
                          ("重新整理", self.refresh_profile_ui)):
            ttk.Button(tops.inner, text=text, style="Small.TButton",
                       command=cmd, takefocus=False).pack(side="left", padx=(0, 4))

        # 紀錄
        lg = ttk.Frame(right, style="Panel.TFrame", padding=10)
        lg.grid(row=1, column=0, sticky="nsew")
        lg.rowconfigure(1, weight=1)
        lg.columnconfigure(0, weight=1)
        lhead = ttk.Frame(lg, style="Panel.TFrame")
        lhead.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(lhead, text="執行紀錄", style="Title.TLabel").pack(side="left")
        ttk.Button(lhead, text="清除",
                   command=lambda: self._clear_log()).pack(side="right")

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
            row_color = (C["warn"] if t in ("loop_start", "loop_end")
                         else C["info"] if t in ("branch_start", "branch_or",
                                                 "branch_end")
                         else C["text"])
            if t in ("loop_end", "branch_end"):
                if stack:
                    stack.pop()
                guides, tail = list(stack), "└ "
            elif t == "branch_or":
                guides, tail = list(stack[:-1]), "├ "
            elif t in ("loop_start", "branch_start"):
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
            if t in ("loop_start", "branch_start"):
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
        if self._drag_idxs is None:  # 拖曳中跳過 (磁碟寫入+版面同步太重),
            self._step_icons.refresh()  # 拖曳結束時補一次
            self._autosave()

    def _region_end(self, i):
        """start 標記 i 的對應結束索引 (通用巢狀); 不成對回傳 None."""
        depth = 0
        for j in range(i + 1, len(self.steps)):
            t = self.steps[j]["type"]
            if t in ("loop_start", "branch_start"):
                depth += 1
            elif t in ("loop_end", "branch_end"):
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
        if self.steps[i]["type"] in ("loop_start", "branch_start"):
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
        defaults = {
            "click": {"type": "click", "x": 500, "y": 400, "button": "left", "clicks": 1},
            "drag": {"type": "drag", "x1": 400, "y1": 300, "x2": 600, "y2": 400,
                     "button": "left", "ms": 500, "holdMs": 500},
            "find_click": {"type": "find_click", "target": {"template": ""},
                           "timeout": 10, "interval": 0.5, "action": "click",
                           "button": "left", "clicks": 1, "offsetX": 0, "offsetY": 0,
                           "onNotFound": "skip"},
            "wait": {"type": "wait", "ms": 1000},
            "key": {"type": "key", "keys": "enter"},
            "loop_start": {"type": "loop_start", "count": 3},
        }
        # 有選取列 → 插在選取列之後 (收合區段算整段); 沒有 → 接在最後
        idxs = self._expand_collapsed(self._sel_all())
        at = (idxs[-1] + 1) if idxs else len(self.steps)
        if t in MARKER_TYPES:  # 沒有可設定的欄位, 直接加入
            self.steps.insert(at, {"type": t})
            self.render_steps(keep=at)
            return
        s = defaults[t]
        s["_index"] = at  # 新步驟的插入位置, 供推算前一步
        s = ui_dialogs.edit_step(self, s)
        if s:
            self.steps.insert(at, s)
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
            if (s["type"] in ("loop_start", "branch_start")
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
        self.render_steps(keep=at + len(items) - 1)
        self.log_ui(f"已貼上 {len(items)} 個步驟", "ok")

    def dup_step(self):
        idxs = self._expand_collapsed(self._sel_all())
        if not idxs:
            return
        block = [json.loads(json.dumps(self.steps[i])) for i in idxs]
        at = idxs[-1] + 1
        self.steps[at:at] = block
        self.render_steps(keep=at + len(block) - 1)

    def del_step(self):
        idxs = self._expand_collapsed(self._sel_all())
        if not idxs:
            return
        for i in reversed(idxs):
            del self.steps[i]
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
        if moved:  # 拖曳中跳過的存檔與圖示刷新, 結束補一次
            self._step_icons.refresh()
            self._autosave()

    def clear_steps(self):
        if not self.steps:
            return
        if not messagebox.askyesno("清除步驟", f"清除全部 {len(self.steps)} 個步驟？",
                                   parent=self.root):
            return
        self.steps = []
        self.render_steps()
        self.log_ui("已清除全部步驟", "warn")

    def move_step(self, d):
        i = self._sel()
        if i is None:
            return
        j = i + d
        if not (0 <= j < len(self.steps)):
            return
        self.steps[i], self.steps[j] = self.steps[j], self.steps[i]
        self.render_steps(keep=j)

    # ================= 範本操作 (本流程的範本) =================
    # 範本名是**平面名稱**: 沒有資料夾層級, 在一份流程內唯一 (ADR 0006)。
    # **一範本一張圖**: 圖住在工作區, 存檔時進 zip; 多截圖範本已退場。

    def list_template_names(self):
        """本流程的範本名 (工作區已有的 + 延後重探索中的新範本)."""
        return sorted(set(self.ws.names()) | self._pending_templates)

    def template_image(self, name):
        """範本的參考影像 (登錄產物已載入時取它, 否則直接讀工作區的圖)."""
        t = self.profile.templates.get(name) if self.profile else None
        if t is not None and t.artifacts is not None:
            return t.artifacts.ref_bgr
        p = self.ws.path_of(name)
        return imgio.imread(p) if os.path.exists(p) else None

    def template_pos(self, name):
        """範本截圖時的中心螢幕座標 [x, y]; 沒有記錄回傳 None.

        只有本流程自己拍的圖有 pos——跨流程複製進來與從磁碟上傳的沒有
        (相對座標原點只能靠即時找圖或往前推)。
        """
        return self.ws.pos_of(name)

    def record_template_pos(self, name, xy):
        """補記範本的中心螢幕座標 (比對測試找到時, 供相對座標當備援原點)."""
        self.ws.set_pos(name, xy)

    def template_bytes(self, name):
        """本流程某個範本的圖檔位元組; 讀不到回 None."""
        try:
            with open(self.ws.path_of(name), "rb") as f:
                return f.read()
        except OSError:
            return None

    def current_flow_path(self):
        """目前這份流程對應的存檔路徑; 還沒存過的新流程回 None."""
        return self.ws.flow_path()

    def drop_template(self, name):
        """把範本從本流程收回去 (圖與登錄產物一起刪)."""
        self.ws.remove(name)

    def add_template_image(self, name, blob, pos=None):
        """把一張圖加進本流程 (bytes 或來源圖檔路徑); 回傳最終採用的範本名.

        撞名自動加序號, 所以本流程原有的圖絕對不會被蓋掉; 改名結果由呼叫端
        寫進執行紀錄 (不彈對話框)。
        """
        final = self.ws.add(name, blob, pos=pos)
        self._pending_templates.add(final)
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
        """本流程的範本清單 (平面, 沒有資料夾層級)."""
        names = self.list_template_names()
        sel = self._sel_template()
        self._tmpl_names = names
        self.tmpl_list.delete(0, "end")
        for n in names:
            self.tmpl_list.insert("end", f" 🖼 {n}")
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
            self.thumb_info.configure(
                text=f"{name}　{img.shape[1]}×{img.shape[0]}px")
        else:
            self.thumb_info.configure(text=name if name else "")

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

    def pick_region_raw(self, hide=()):
        """框選一個區域, 回傳原始截圖資料「不存檔」(供對話框確定後才儲存)."""
        return ui_overlay.pick(self.root, "region", "拖曳框選要辨識的圖片區域",
                               hide=hide)

    def flow_scale_image(self, img):
        """截下的範本圖換回`流程尺度`: 除以編輯器倍率 (倍率 1 原圖照存).

        上傳的圖不經這裡——不知道它的來源尺度, 照原樣存。
        """
        return imgio.to_flow_scale(img, self.editor_scale)

    def save_captured(self, r):
        """把 pick_region_raw 的結果存成本流程的新範本, 回傳範本名.

        圖落在工作區 (存檔時才進 zip), 先換回流程尺度; 記下`pos`＝截圖當下的
        中心螢幕座標 (螢幕座標, 不換算)。
        """
        name = self.ws.reserve(self.next_template_name())
        img = self.flow_scale_image(r["img"])
        imgio.imwrite(self.ws.path_of(name), img)
        self.ws.set_pos(name, [r["screenX"] + r["w"] // 2,
                               r["screenY"] + r["h"] // 2])
        # 重新探索卡主執行緒 → 延後到視窗還原、畫面喘口氣之後,
        # 「視窗消失」與「程式短暫卡住」兩種感受分開
        self._pending_templates.add(name)
        self._schedule_reregister()
        self.refresh_templates()
        self.log_ui(f"已新增範本「{name}」({img.shape[1]}×{img.shape[0]})"
                    "；建議跑一次「比對測試」確認畫面上找得到", "ok")
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
        """延後的重新探索立即補跑; 引擎查詢 (比對測試/執行流程) 前必須呼叫,
        否則延後期間的新範本還不在範本清單裡, 查詢會 KeyError。
        登錄產物本身由`範本預載`/單張載入在使用當下載入 (ADR 0004)."""
        if not self._pending_templates:
            return
        self._cancel_reregister()
        self.reload_profile()
        self._pending_templates.clear()
        self.refresh_templates()

    def capture_template(self, hide=()):
        """截圖框選 → 自動命名存入本流程的範本. 回傳範本名或 None."""
        r = self.pick_region_raw(hide=hide)
        if not r:
            return None
        return self.save_captured(r)

    def upload_template(self):
        """從硬碟上傳圖片存為本流程的範本 (可多選).

        一律重新編碼成 PNG; 上傳的範本沒有螢幕座標, 不記 `pos`
        (相對座標原點只能靠即時找圖或往前推)。引擎登錄時以遮罩決定
        有效區域, 不看 alpha (透明區照存, 只影響預覽)。
        """
        paths = filedialog.askopenfilenames(
            parent=self.root, title="上傳圖片範本",
            filetypes=[("圖片檔", "*.png *.webp *.jpg *.jpeg *.bmp *.gif *.tif *.tiff"),
                       ("所有檔案", "*.*")])
        added = []
        for p in paths:
            img = imgio.imread(p)  # IMREAD_UNCHANGED → 有 alpha 即 BGRA (imgio 已正規化)
            if img is None:
                self.log_ui(f"讀不到圖片：{os.path.basename(p)}", "warn")
                continue
            name = self.ws.reserve(self.next_template_name(taken=added))
            imgio.imwrite(self.ws.path_of(name), img)
            added.append(name)
        if not added:
            return
        self._pending_templates.update(added)
        self.reload_profile()
        self._pending_templates.clear()
        self.refresh_templates()
        self._select_tmpl_row(added[-1])  # 選取最後上傳的一張
        self.log_ui(f"已上傳 {len(added)} 張範本：{', '.join(added)}"
                    "；建議跑一次「比對測試」確認畫面上找得到", "ok")

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
        new = flowfile.clean_name(new)
        if not new or new == old:
            return
        final = self.ws.rename(old, new)
        if final is None:
            messagebox.showwarning("重新命名", f"找不到範本「{old}」的圖",
                                   parent=self.root)
            return
        changed = flowfile.rename_flow_refs(self._ref_data(), old, final)
        self.reload_profile()
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
        self.ws.remove(name)
        self._pending_templates.discard(name)
        self.reload_profile()
        self.refresh_templates()
        self.render_steps()

    def test_template(self):
        name = self._sel_template()
        if not name:
            messagebox.showinfo("比對測試", "請先在清單選擇一個範本", parent=self.root)
            return
        ui_dialogs.show_match_test(self, name)

    def copy_template(self):
        """複製選取的範本為新範本 (連同截圖位置記錄), 撞名自動加序號."""
        name = self._sel_template()
        if not name:
            messagebox.showinfo("複製", "請先在清單選擇一個範本", parent=self.root)
            return
        src = self.ws.path_of(name)
        if not os.path.exists(src):
            messagebox.showwarning("複製", f"找不到範本「{name}」的圖",
                                   parent=self.root)
            return
        new = self.add_template_image(name, src, pos=self.ws.pos_of(name))
        self.ensure_registered()
        self.refresh_templates()
        self._select_tmpl_row(new)  # 選取新複製的範本
        self.log_ui(f"已複製「{name}」→「{new}」", "ok")

    # ================= 流程存檔 =================

    def _ref_data(self):
        """引用範本的那部分流程資料: 步驟＋流程層級設定 (不讀介面元件).

        回傳的是同一批物件 (不是副本): `rename_flow_refs` 就地改它就改到本流程。
        """
        data = {"steps": self.steps}
        if self.flow_cal:
            data[calibration.FLOW_KEY] = self.flow_cal
        if self.busy_target:
            data[flowfile.BUSY_KEY] = self.busy_target
        return data

    def _flow_data(self):
        data = self._ref_data()
        data.update({
            "runMode": "count" if self.run_mode.get() == "執行次數" else "infinite",
            "runCount": self._run_count(),
            "scanRegion": self.scan_region,
            "avoidHover": self.avoid_hover.get(),
            flowfile.RETRY_KEY: self.retry_interval_ms,
            flowfmt.COORD_SPACE: flowfmt.REGION,
        })
        return data

    def referenced_templates(self):
        """本流程引用的全部範本名 (步驟 + 校準對 + 忙碌指示; 見 flowfile.flow_refs)."""
        return flowfile.flow_refs(self._ref_data())

    def _log_notes(self, notes):
        """把遷移提示寫進執行紀錄 (換算失敗的提示以警告等級顯示)."""
        for note in notes:
            self.log_ui(note, "warn" if "無法" in note else "info")

    def _apply_flow(self, data):
        # 舊存檔一律先遷移: 座標空間換算、範本名去副檔名、每步 threshold 丟棄
        self._log_notes(flowfile.migrate_flow(data))
        self.steps = data.get("steps", [])
        self.flow_cal = calibration.flow_pair(data)
        self.editor_scale = 1.0   # 編輯器倍率屬於「這次編輯這份流程」
        self._update_cal_ui()
        self.retry_interval_ms = flowfile.retry_interval_ms(data)
        self.busy_target = flowfile.busy_target(data)
        self._update_retry_ui()
        self.run_mode.set("直到停止" if data.get("runMode") == "infinite" else "執行次數")
        self.run_count.set(data.get("runCount", 1))
        self.scan_region = data.get("scanRegion")
        self.avoid_hover.set(bool(data.get("avoidHover", False)))
        if self.scan_region:
            self.scan_lbl.configure(text=f"限定 {tuple(self.scan_region)}",
                                    foreground=C["accent"])
        else:
            self.scan_lbl.configure(text="全螢幕", foreground=C["muted"])
        self._mode_ui()
        self.render_steps()
        self._update_region_preview()

    # ---- 流程存檔住在所屬 profile 的 flows/ 之下, 一份流程一個自包自足的檔 ----

    def new_flow(self):
        """開一份新流程: 步驟清空、**工作區整個清空** (圖與登錄產物都刪).

        磁碟上刻意不留任何非當前流程的圖 (ADR 0006); 代價是切回舊流程時
        該流程的範本要重新登錄。
        """
        if self.steps and not messagebox.askyesno(
                "新流程",
                f"開新流程會清掉目前的 {len(self.steps)} 個步驟與本流程的"
                f"{len(self.ws.names())} 個範本（未存檔的內容會消失）。\n"
                "確定要開新流程嗎？", parent=self.root):
            return
        self._switch_workspace(None)
        self._apply_flow({"steps": [], flowfmt.COORD_SPACE: flowfmt.REGION})
        self.log_ui("已開始一份新流程（工作區已清空）", "ok")

    def _switch_workspace(self, flow_path):
        """切流程的工作區交接: 清空 → (有存檔就) 解到工作區 → 重新探索.

        回傳 flowfile.read() 的結果 (flow_path 為 None 時回 None)。
        """
        self._cancel_reregister()
        self._pending_templates.clear()
        self._collapsed.clear()
        r = None
        if flow_path is None:
            self.ws.clear()
            self.ws.set_flow_path(None)
        else:
            r = self.ws.load_flow(flow_path)
        self.reload_profile()
        self.refresh_templates()
        return r

    def save_flow(self):
        """把目前流程存成一個自包自足的存檔 (步驟＋引用到的每一張範本圖)."""
        if not self.steps:
            messagebox.showinfo("儲存流程", "沒有步驟可儲存", parent=self.root)
            return
        os.makedirs(self.flows_dir, exist_ok=True)
        path = filedialog.asksaveasfilename(
            parent=self.root, title="儲存流程", initialdir=self.flows_dir,
            initialfile=os.path.basename(self.ws.flow_path() or ""),
            defaultextension=flowfile.EXT,
            filetypes=[("AutoClick 流程", "*" + flowfile.EXT)])
        if not path:
            return
        self.ensure_registered()  # 延後中的新範本先進清單, 圖才帶得齊
        try:
            missing = self.ws.put_flow(self._flow_data(), path=path)
        except OSError as e:
            messagebox.showerror("儲存流程", f"儲存失敗: {e}", parent=self.root)
            return
        names = self.referenced_templates()
        self.log_ui(f"已儲存流程 {os.path.basename(path)}"
                    f"（{len(self.steps)} 步、{len(names) - len(missing)} 個範本）",
                    "ok")
        if missing:
            self.log_ui("這些步驟引用的範本已不在本流程裡，存檔沒有帶到："
                        + "、".join(missing), "warn")

    def open_flow(self):
        """載入流程存檔; 舊格式與外來檔一律先落地成本 profile 的存檔再開.

        - 本 profile 內的存檔: 直接解到工作區
        - 不在本 profile 內的存檔: 原樣複製一份副本進來再開 (原始檔不被動到;
          不換算——流程自帶尺度與校準對)
        - 舊 autoClick flow JSON / 舊流程包: 單向轉換成新存檔後開啟
        """
        path = filedialog.askopenfilename(
            parent=self.root, title="載入流程", initialdir=self.flows_dir,
            filetypes=[("AutoClick 流程",
                        f"*{flowfile.EXT} *.json *.autoclick"),
                       ("所有檔案", "*.*")])
        if not path:
            return
        try:
            if flowfile.is_flow_file(path):
                if flowfile.is_inside_profile(path, self.profile_dir):
                    r = self._switch_workspace(path)
                    self._log_notes(r["notes"])
                    self.log_ui(f"已載入流程 {os.path.basename(path)}"
                                f"（{len(self.ws.names())} 個範本）", "ok")
                    self._apply_flow(r["data"])
                    return
                # 外來存檔: 原樣複製副本進 profile
                a = flowfile.adopt_foreign_flow(path, self.profile_dir)
                r = self._switch_workspace(a["flow_path"])
                self._log_notes(a["notes"])
                self.log_ui(
                    f"已把外來存檔 {os.path.basename(path)} 複製進本 profile → "
                    f"{os.path.basename(a['flow_path'])}（原始檔未被修改）", "ok")
                self._apply_flow(a["data"])
                return
            # 舊格式: 單向轉換 (ADR 0002)
            r = flowfile.import_legacy(path, self.profile_dir)
            self._switch_workspace(r["flow_path"])
            self._log_notes(r["notes"])
            msg = (f"已匯入舊格式流程 {os.path.basename(path)} → "
                   f"{os.path.basename(r['flow_path'])}"
                   f"（收進 {len(r['templates'])} 個範本）")
            self.log_ui(msg, "ok")
            self._log_conversion(r)
            self._apply_flow(r["data"])
        except Exception as e:
            messagebox.showerror("載入流程", f"載入失敗: {e}", parent=self.root)

    def _log_conversion(self, r):
        """舊格式轉換的副作用進執行紀錄 (改名/降級/缺圖都不彈對話框)."""
        if r.get("renamed"):
            self.log_ui("範本名已拉平，撞名自動加序號並同步改寫引用："
                        + "、".join(f"{k}→{v}" for k, v in
                                    sorted(r["renamed"].items())), "info")
        if r.get("downgraded"):
            self.log_ui("這些範本原本是多截圖，已取登錄基準張降為單張："
                        + "、".join(r["downgraded"]), "warn")
        if r.get("missing"):
            self.log_ui("找不到這些被引用的範本，沒有帶進存檔："
                        + "、".join(r["missing"]), "warn")

    def _autosave(self):
        """自動存檔**只寫步驟草稿**: 圖留在工作區, 不重壓整包 zip.

        拖曳排序一次動作就存一次, 重寫幾十張圖會卡頓; 當機重開時草稿與
        工作區裡的圖一起復原。
        """
        flowfile.write_draft(self.profile_dir, self._flow_data())

    def _load_autosave(self):
        data = flowfile.read_draft(self.profile_dir)
        if data is not None:
            self._apply_flow(data)

    # ================= 執行 =================

    def _run_count(self):
        try:
            return max(1, int(self.run_count.get()))
        except (ValueError, tk.TclError):
            return 1

    def _flow_error(self, steps=None):
        """執行前檢查流程結構, 回傳錯誤訊息或 None.

        堆疊掃描: 除了成對, 也擋交錯區段 (如 重複開始→分岔開始→
        重複結束→分岔結束), runner 的跳轉解譯無法正確執行交錯結構.
        """
        steps = self.steps if steps is None else steps
        zh = {"loop_start": "重複", "branch_start": "分岔"}
        stack = []  # 進行中區段的 (start type, 步驟序號)
        for i, s in enumerate(steps):
            t = s["type"]
            if t in ("loop_start", "branch_start"):
                if t == "branch_start":
                    lay = branch_layout(steps, i)
                    if lay is None:
                        return "分岔標記不成對（缺少「分岔結束」）"
                    segs, end = lay
                    for st in segs:
                        if st >= end or steps[st]["type"] != "find_click":
                            return "分岔的每個分支開頭必須是「找圖點擊」步驟"
                stack.append((t, i + 1))
            elif t in ("loop_end", "branch_end"):
                need = "loop_start" if t == "loop_end" else "branch_start"
                if not stack:
                    return f"步驟 {i + 1}「{STEP_LABELS[t]}」缺少對應的開始標記"
                if stack[-1][0] != need:
                    return (f"區段交錯：步驟 {i + 1}「{STEP_LABELS[t]}」之前，"
                            f"必須先結束步驟 {stack[-1][1]} 開始的"
                            f"「{zh[stack[-1][0]]}」區段（區段不可交錯）")
                stack.pop()
            elif t == "branch_or":
                if not stack or stack[-1][0] != "branch_start":
                    return "「分岔（或）」必須直接位於分岔區段內"
        if stack:
            return (f"步驟 {stack[-1][1]}「{STEP_LABELS[stack[-1][0]]}」"
                    f"缺少對應的結束標記")
        return None

    def start_run(self, steps=None, test=False):
        """執行流程; steps 給定時只跑該片段 (測試選取), 一律單次."""
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
            if (s["type"] == "find_click"
                    and findtarget.template(s) not in names):
                missing.append(findtarget.template(s) or "(未選擇)")
            if (findtarget.uses_confirm_target(s)
                    and findtarget.confirm_template(s) not in names):
                missing.append((findtarget.confirm_template(s) or "(未選擇)")
                               + "（確認圖）")
        if self.flow_cal is None:
            # 執行器開頭也會擋 (沒有校準對＝量不了倍率); 這裡先講清楚下一步
            messagebox.showwarning(
                "執行", "這份流程沒有校準對（舊格式或尚未設定），不能執行。\n"
                "請先在「畫面校準」設定校準對（例：遊戲視窗標題列的圖示與關閉鈕）",
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
        abs_no = [n for n, _ in flowfmt.abs_steps(steps)]
        if abs_no and not self.scan_region:
            messagebox.showwarning(
                "執行",
                "絕對座標是以「搜尋範圍」左上角為基準的，請先框選搜尋範圍。\n"
                f"用到絕對座標的步驟：{', '.join(map(str, abs_no))}",
                parent=self.root)
            return
        delay = {"無": 0, "3 秒": 3, "5 秒": 5, "10 秒": 10}[self.start_delay.get()]
        if test:
            mode, count = "count", 1
        else:
            mode = "count" if self.run_mode.get() == "執行次數" else "infinite"
            count = self._run_count()
        try:
            self.runner.start(steps, mode, count, delay,
                              scan_region=self.scan_region,
                              avoid_hover=self.avoid_hover.get(),
                              calibration=self.flow_cal,
                              retry_interval=self.retry_interval_ms / 1000.0,
                              busy=self.busy_target)
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
        return [i for i, s in enumerate(steps)
                if uses_confirm_next(s) and not confirm_next_connected(steps, i)]

    def _origin_leaves_bad(self, steps):
        """「原點的圖離開」但原點不是來自找圖的座標點擊/拖曳索引 (0-based).

        測試選取時傳入的是片段: 原點來源在片段外＝片段內沒有找圖來源, 一樣擋。
        """
        return [i for i, s in enumerate(steps)
                if uses_origin_leaves(s) and origin_source(steps, i) != "find"]

    def _fragment_origin_error(self, steps, base):
        """片段內「執行到時必然沒有原點」的相對座標步驟編號 (完整清單編號).

        原點來源: 絕對座標點擊/拖曳、找圖步驟; 相對步驟 (含以原點為基準的
        `找圖目標`) 在原點出現前執行只會被 runner 跳過, 測試片段時直接在
        執行前擋下.
        """
        have = False
        bad = []
        for k, s in enumerate(steps):
            t = s.get("type")
            if t in ("click", "drag"):
                if s.get("mode", "abs") == "prev" and not have:
                    bad.append(base + k + 1)
                elif t == "drag" or s.get("updateOrigin", True):
                    have = True
            elif t == "find_click":
                if not have and findtarget.needs_origin(findtarget.target(s)):
                    bad.append(base + k + 1)
                elif s.get("updateOrigin", True):
                    have = True
        return bad

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
                "以下以原點為基準的步驟（相對座標，或找圖的限定範圍／指定點"
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
        st = self.runner.status()
        running = st["running"]
        self.btn_run.configure(state="disabled" if running else "normal")
        self.btn_stop.configure(state="normal" if running else "disabled")
        if running:
            total = st["totalRounds"]
            if st["round"] == 0:
                text = ("準備範本中…" if st.get("preparing")
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
            if self.hub.state == enginehub.LOADING:
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
        self._autosave()
        self.root.destroy()


def main():
    win.set_dpi_aware()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
