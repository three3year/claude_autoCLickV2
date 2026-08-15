"""AutoClick — 按鍵精靈 (本機桌面版)

核心: 找圖點擊 + 步驟序列自動執行, F12 急停.
"""
import json
import os
import re
import shutil
import sys
import time
import zipfile
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

import ui_dialogs
import ui_overlay
import ui_theme
from automation import flowfmt, hotkey, imgio, win
from automation.runner import Runner, branch_layout
from ui_theme import C, FONT, FONT_MONO


def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE = base_dir()
TEMPLATES_DIR = os.path.join(BASE, "templates")
FLOWS_DIR = os.path.join(BASE, "flows")
AUTOSAVE = os.path.join(FLOWS_DIR, "_autosave.json")
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(FLOWS_DIR, exist_ok=True)

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


def clean_rel_name(name):
    """清理範本相對路徑: 分段去除非法字元、擋掉 ../空段, 保留資料夾分隔."""
    parts = []
    for p in name.replace("\\", "/").split("/"):
        p = re.sub(r'[:*?"<>|]', "_", p.strip())
        if p in ("", ".", ".."):
            continue
        parts.append(p)
    return "/".join(parts)


def step_desc(s):
    t = s["type"]
    if t == "click":
        if s.get("mode", "abs") == "prev":
            pos = f"上一步點擊 ({int(s['x']):+d}, {int(s['y']):+d})"
        else:
            pos = f"範圍內 ({s['x']}, {s['y']})"
        uo = "，不更新原點" if not s.get("updateOrigin", True) else ""
        return f"{pos} {BTN_ZH.get(s.get('button', 'left'))}×{s.get('clicks', 1)}{uo}"
    if t == "find_click":
        act = {"click": "點擊", "none": "僅等待出現",
               "wait_gone": "等待消失"}.get(s.get("action", "click"), "點擊")
        nf = {"stop": "停止", "break": "跳出"}.get(s.get("onNotFound"), "跳過")
        cfm = {"gone": "，點到消失", "appear": "，點到確認圖出現"}.get(s.get("confirm"), "")
        ox, oy = int(s.get("offsetX", 0)), int(s.get("offsetY", 0))
        off = f"，偏移({ox:+d}, {oy:+d})" if ox or oy else ""
        uo = "，不更新原點" if not s.get("updateOrigin", True) else ""
        return (f"{s.get('template', '?')} ≥{s.get('threshold', 0.85)} → {act}{off}{cfm}{uo}"
                f"（逾時{s.get('timeout', 10)}s→{nf}）")
    if t == "drag":
        if s.get("mode", "abs") == "prev":
            pos = (f"上一步 ({int(s['x1']):+d}, {int(s['y1']):+d}) → "
                   f"({int(s['x2']):+d}, {int(s['y2']):+d})")
        else:
            pos = f"({s['x1']}, {s['y1']}) → ({s['x2']}, {s['y2']})"
        hd = f" 停{s.get('holdMs')}ms" if s.get("holdMs") else ""
        return f"{pos} {BTN_ZH.get(s.get('button', 'left'))} {s.get('ms', 300)}ms{hd}"
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
    def __init__(self, root):
        self.root = root
        self.templates_dir = TEMPLATES_DIR
        self.flows_dir = FLOWS_DIR
        self.steps = []
        self.last_seq = 0
        self.scan_region = None  # 全域搜尋範圍 [x,y,w,h]; None = 全螢幕
        self._mini = None  # 執行中的迷你狀態視窗
        self._region_prev = None  # 搜尋範圍預覽框
        self._root_shown = False  # 主視窗是否已首次顯示 (Map 過)
        self._collapsed = set()  # 已收合的區段起點 (以 step dict 的 id 記錄)
        self._view = []  # 清單列 → steps 索引的映射 (收合時兩者不一致)
        self.runner = Runner(TEMPLATES_DIR)
        hotkey.start_stop_hotkey(self.stop_all)  # F12 = 全部停止

        root.title("AutoClick — 按鍵精靈")
        root.geometry("1120x700")
        root.minsize(900, 560)
        ui_theme.apply(root)

        self._build_menu()
        self._build_toolbar()
        self._build_main()

        self._load_autosave()
        self.refresh_templates()
        self.render_steps()
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

    # ================= UI 建構 =================

    def _build_menu(self):
        kw = dict(bg=C["panel"], fg=C["text"], activebackground=C["sel"],
                  activeforeground=C["text"], bd=0, font=FONT)
        # 工作列直接放指令 (不用下拉選單); 存檔/讀檔走步驟面板按鈕
        menubar = tk.Menu(self.root, **kw)
        menubar.add_command(label="開啟資料夾",
                            command=lambda: os.startfile(BASE))
        self.root.configure(menu=menubar)
        self.root.bind("<Control-s>", lambda e: self.export_pack())
        self.root.bind("<Control-o>", lambda e: self.import_pack())

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

        # 第二列: 全域搜尋範圍
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
        # 建立新 Toplevel 會把 modal 對話框既有的 grab 打掉, 建完要還回去
        grab_owner = ui_theme.safe_grab_current(self.root)
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
        if grab_owner is not None:
            try:
                grab_owner.grab_set()
            except tk.TclError:
                pass

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

        # 存檔/讀檔/清除: 小按鈕放進橫向捲動列, 窄視窗時縮小、滾輪捲動找到
        strip = HScrollStrip(head)
        strip.pack(side="left", fill="x", expand=True, padx=(8, 6))
        for text, cmd in (("存檔", self.export_pack), ("讀檔", self.import_pack),
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
        ttk.Label(thead, text="圖片範本", style="Title.TLabel").pack(side="left")
        ttk.Button(thead, text="截圖框選", style="Accent.TButton",
                   command=lambda: self.capture_template()).pack(side="right")
        ttk.Button(thead, text="上傳圖片",
                   command=self.upload_template).pack(side="right", padx=(0, 6))

        self._tmpl_open = set()  # 展開中的資料夾 (檔案總管式清單)
        self._tmpl_rows = []     # 清單列 → (kind, 相對路徑); kind: dir | file
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
        for text, cmd in (("比對測試", self.test_template), ("複製", self.copy_template),
                          ("＋資料夾", self.new_template_folder)):
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
            "find_click": {"type": "find_click", "template": "", "threshold": 0.85,
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

    # ================= 範本操作 =================

    def list_template_names(self):
        """所有範本的相對名稱 (含子資料夾, 如 zh/X.png)."""
        out = []
        for base, dirs, files in os.walk(TEMPLATES_DIR):
            rel = os.path.relpath(base, TEMPLATES_DIR)
            for fn in files:
                if fn.lower().endswith(".png"):
                    out.append(fn if rel == "." else
                               f"{rel}/{fn}".replace(os.sep, "/"))
        return sorted(out)

    def template_folders(self):
        """templates 下的子資料夾相對路徑."""
        out = []
        for base, dirs, _files in os.walk(TEMPLATES_DIR):
            for d in dirs:
                p = os.path.relpath(os.path.join(base, d), TEMPLATES_DIR)
                out.append(p.replace(os.sep, "/"))
        return sorted(out)

    def current_folder(self):
        """新範本的目的資料夾: 依清單選取的資料夾/檔案決定, 無則根目錄."""
        r = self._sel_row()
        if not r:
            return ""
        if r[0] == "dir":
            return r[1]
        return r[1].rsplit("/", 1)[0] if "/" in r[1] else ""

    def new_template_folder(self):
        parent = self.current_folder()
        name = ui_dialogs.ask_string(self.root, "新增資料夾", "輸入資料夾名稱：")
        if name is None:
            return
        name = clean_rel_name(name)
        if not name:
            return
        path = f"{parent}/{name}" if parent else name
        os.makedirs(os.path.join(TEMPLATES_DIR, path), exist_ok=True)
        self._open_ancestors(path + "/x")  # 展開父層鏈 (借用檔案路徑形式)
        self.refresh_templates()
        self._select_tmpl_row(("dir", path))
        self.log_ui(f"已建立資料夾「{path}」", "ok")

    def _open_ancestors(self, name):
        """展開檔案相對路徑的所有上層資料夾."""
        parts = name.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            self._tmpl_open.add("/".join(parts[:i]))

    def _select_tmpl_row(self, row):
        rows = self._tmpl_rows
        if row in rows:
            i = rows.index(row)
            self.tmpl_list.selection_clear(0, "end")
            self.tmpl_list.selection_set(i)
            self.tmpl_list.see(i)
            self._show_thumb()

    def refresh_templates(self):
        """檔案總管式清單: 資料夾列可點選展開/收合, 內容縮排列在其下."""
        names = self.list_template_names()
        folders = self.template_folders()
        rows, lines = [], []

        def children(dirpath):
            if dirpath:
                pre = dirpath + "/"
                dirs = [d for d in folders
                        if d.startswith(pre) and "/" not in d[len(pre):]]
                files = [n for n in names
                         if n.startswith(pre) and "/" not in n[len(pre):]]
            else:
                dirs = [d for d in folders if "/" not in d]
                files = [n for n in names if "/" not in n]
            return sorted(dirs), sorted(files)

        def emit(dirpath, depth):
            ind = "　" * depth
            dirs, files = children(dirpath)
            for d in dirs:
                mark = "▾" if d in self._tmpl_open else "▸"
                lines.append(f" {ind}{mark} 📁 {d.rsplit('/', 1)[-1]}")
                rows.append(("dir", d))
                if d in self._tmpl_open:
                    emit(d, depth + 1)
            for n in files:
                lines.append(f" {ind}　🖼 {n.rsplit('/', 1)[-1]}")
                rows.append(("file", n))

        emit("", 0)
        sel = self._sel_row()
        self._tmpl_rows = rows
        self.tmpl_list.delete(0, "end")
        for t in lines:
            self.tmpl_list.insert("end", t)
        if sel in rows:
            i = rows.index(sel)
            self.tmpl_list.selection_set(i)
            self.tmpl_list.see(i)
        self._tmpl_icons.refresh()
        self._show_thumb()

    def _sel_row(self):
        s = self.tmpl_list.curselection()
        rows = getattr(self, "_tmpl_rows", [])
        if not s or s[0] >= len(rows):
            return None
        return rows[s[0]]

    def _sel_template(self):
        r = self._sel_row()
        return r[1] if r and r[0] == "file" else None

    def _on_tmpl_select(self, e=None):
        r = self._sel_row()
        if r and r[0] == "dir":  # 點資料夾列 = 展開/收合
            (self._tmpl_open.discard if r[1] in self._tmpl_open
             else self._tmpl_open.add)(r[1])
            self.refresh_templates()
            return
        self._show_thumb()

    def _show_thumb(self):
        name = self._sel_template()
        img = imgio.imread(os.path.join(TEMPLATES_DIR, name)) if name else None
        # 固定尺寸底圖: 預覽框不隨範本大小忽大忽小
        photo = ui_dialogs._thumb_photo(self.root, img)
        self.thumb_lbl.configure(image=photo, text="")
        self.thumb_lbl._photo = photo
        if img is not None:
            self.thumb_info.configure(text=f"{name}　{img.shape[1]}×{img.shape[0]}px")
        else:
            self.thumb_info.configure(text=name if name else "")

    # ---- 範本中繼資料 ----
    # pos: 截圖當下的中心螢幕座標 (相對座標預設原點備援)

    def _meta_path(self):
        return os.path.join(TEMPLATES_DIR, "_meta.json")

    def _load_meta(self):
        try:
            with open(self._meta_path(), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        if data and "pos" not in data and "rot" not in data:
            data = {"pos": data}  # 舊格式 (name→[x,y]) 遷移
        return {"pos": data.get("pos", {})}  # rot (旋轉沿革) 已廢除, 讀入即丟

    def _save_meta(self, meta):
        try:
            with open(self._meta_path(), "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False)
        except OSError:
            pass

    def template_pos(self, name):
        """範本截圖時的中心螢幕座標 [x, y]; 舊版建立的範本可能沒有, 回傳 None."""
        return self._load_meta()["pos"].get(name)

    def _next_template_name(self):
        used = set()
        for fn in self.list_template_names():
            m = re.fullmatch(r"tmpl_(\d+)\.png", fn.rsplit("/", 1)[-1])
            if m:
                used.add(int(m.group(1)))
        n = 1
        while n in used:
            n += 1
        return f"tmpl_{n:03d}.png"

    def pick_region_raw(self, hide=()):
        """框選一個區域, 回傳原始截圖資料「不存檔」(供對話框確定後才儲存)."""
        return ui_overlay.pick(self.root, "region", "拖曳框選要辨識的圖片區域",
                               hide=hide)

    def save_captured(self, r):
        """把 pick_region_raw 的結果存成新範本 (存進目前資料夾), 回傳檔名."""
        folder = self.current_folder()
        name = self._next_template_name()
        if folder:
            name = f"{folder}/{name}"
        dest = os.path.join(TEMPLATES_DIR, name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        imgio.imwrite(dest, r["img"])
        meta = self._load_meta()
        meta["pos"][name] = [r["screenX"] + r["w"] // 2, r["screenY"] + r["h"] // 2]
        self._save_meta(meta)
        self.refresh_templates()
        self.log_ui(f"已新增範本「{name}」({r['w']}×{r['h']})", "ok")
        return name

    def capture_template(self, hide=()):
        """截圖框選 → 自動命名存入範本. 回傳檔名或 None."""
        r = self.pick_region_raw(hide=hide)
        if not r:
            return None
        return self.save_captured(r)

    def upload_template(self):
        """從硬碟上傳圖片存為範本 (可多選); 有透明度 (alpha) 一律保留.

        一律重新編碼成 tmpl_NNN.png (PNG 保留 alpha); 上傳的範本沒有螢幕座標,
        不寫入 meta['pos'] (相對座標原點只能靠即時找圖或往前推). 帶 alpha 的
        範本比對時只算不透明區 (matcher 用 alpha 當遮罩)。
        """
        paths = filedialog.askopenfilenames(
            parent=self.root, title="上傳圖片範本",
            filetypes=[("圖片檔", "*.png *.webp *.jpg *.jpeg *.bmp *.gif *.tif *.tiff"),
                       ("所有檔案", "*.*")])
        added, alpha_cnt = [], 0
        for p in paths:
            img = imgio.imread(p)  # IMREAD_UNCHANGED → 有 alpha 即 BGRA (imgio 已正規化)
            if img is None:
                self.log_ui(f"讀不到圖片：{os.path.basename(p)}", "warn")
                continue
            name = self._next_template_name()  # 讀磁碟計算, 迴圈內即時唯一
            folder = self.current_folder()
            if folder:
                name = f"{folder}/{name}"
            dest = os.path.join(TEMPLATES_DIR, name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            imgio.imwrite(dest, img)
            added.append(name)
            if img.ndim == 3 and img.shape[2] == 4:
                alpha_cnt += 1
        if not added:
            return
        self._open_ancestors(added[-1])
        self.refresh_templates()
        self._select_tmpl_row(("file", added[-1]))  # 選取最後上傳的一張
        tail = f"（{alpha_cnt} 張含透明度）" if alpha_cnt else ""
        self.log_ui(f"已上傳 {len(added)} 張範本{tail}：{', '.join(added)}", "ok")

    def rename_template(self):
        old = self._sel_template()
        if not old:
            messagebox.showinfo("重新命名", "請先在清單選擇一個範本", parent=self.root)
            return
        new = ui_dialogs.ask_string(
            self.root, "重新命名", "輸入新名稱（可含資料夾，如 zh/按鈕）：",
            initialvalue=os.path.splitext(old)[0])
        if new is None:
            return
        new = clean_rel_name(new)
        if not new:
            return
        if not new.lower().endswith(".png"):
            new += ".png"
        if new == old:
            return
        if os.path.exists(os.path.join(TEMPLATES_DIR, new)):
            messagebox.showwarning("重新命名", f"「{new}」已存在", parent=self.root)
            return
        os.makedirs(os.path.dirname(os.path.join(TEMPLATES_DIR, new)),
                    exist_ok=True)
        os.rename(os.path.join(TEMPLATES_DIR, old),
                  os.path.join(TEMPLATES_DIR, new))
        meta = self._load_meta()
        if old in meta["pos"]:
            meta["pos"][new] = meta["pos"].pop(old)
        self._save_meta(meta)
        # 同步更新引用此範本的步驟 (含點擊後確認圖)
        changed = 0
        for s in self.steps:
            if s.get("template") == old:
                s["template"] = new
                changed += 1
            if s.get("confirmTemplate") == old:
                s["confirmTemplate"] = new
                changed += 1
        self.refresh_templates()
        self.render_steps()
        msg = f"已將「{old}」重新命名為「{new}」"
        if changed:
            msg += f"（已同步更新 {changed} 個步驟）"
        self.log_ui(msg, "ok")

    def del_template(self):
        name = self._sel_template()
        if not name:
            return
        used = [i + 1 for i, s in enumerate(self.steps)
                if s["type"] == "find_click" and s.get("template") == name]
        # 沒有步驟使用時直接刪除, 不打擾
        if used and not messagebox.askyesno(
                "刪除範本",
                f"刪除範本「{name}」？\n（步驟 {', '.join(map(str, used))} 正在使用它）",
                parent=self.root):
            return
        os.remove(os.path.join(TEMPLATES_DIR, name))
        meta = self._load_meta()
        meta["pos"].pop(name, None)
        self._save_meta(meta)
        self.refresh_templates()

    def test_template(self):
        name = self._sel_template()
        if not name:
            messagebox.showinfo("比對測試", "請先在清單選擇一個範本", parent=self.root)
            return
        ui_dialogs.show_match_test(self, name, 0.85)

    def copy_template(self):
        """複製選取的範本為新範本 (連同截圖位置記錄), 命名為原檔名_N."""
        name = self._sel_template()
        if not name:
            messagebox.showinfo("複製", "請先在清單選擇一個範本", parent=self.root)
            return
        new = self._free_name(name)
        shutil.copyfile(os.path.join(TEMPLATES_DIR, name),
                        os.path.join(TEMPLATES_DIR, new))
        meta = self._load_meta()
        if name in meta["pos"]:
            meta["pos"][new] = list(meta["pos"][name])
        self._save_meta(meta)
        self._open_ancestors(new)
        self.refresh_templates()
        self._select_tmpl_row(("file", new))  # 選取新複製的範本
        self.log_ui(f"已複製「{name}」→「{new}」", "ok")

    def _free_name(self, name):
        """以 name 為基底找未使用的檔名: 末端已是 _數字則遞增 (保留補零位數)."""
        base = os.path.splitext(name)[0]
        m = re.fullmatch(r"(.*)_(\d+)", base)
        if m:
            stem, width, n = m.group(1), len(m.group(2)), int(m.group(2)) + 1
        else:
            stem, width, n = base, 1, 1
        while os.path.exists(os.path.join(TEMPLATES_DIR, f"{stem}_{n:0{width}d}.png")):
            n += 1
        return f"{stem}_{n:0{width}d}.png"

    # ================= 流程存檔 =================

    def _flow_data(self):
        return {
            "steps": self.steps,
            "runMode": "count" if self.run_mode.get() == "執行次數" else "infinite",
            "runCount": self._run_count(),
            "scanRegion": self.scan_region,
            "avoidHover": self.avoid_hover.get(),
            flowfmt.COORD_SPACE: flowfmt.REGION,
        }

    def _apply_flow(self, data):
        # 舊存檔的絕對座標是螢幕座標, 讀進來要換算成範圍座標 (見 automation/flowfmt)
        note = flowfmt.to_region_space(data)
        if note:
            self.log_ui(note, "warn" if "無法" in note else "info")
        self.steps = data.get("steps", [])
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

    # ---- 流程包: 流程 + 用到的範本 (含中繼資料) 打包成單一檔, 供跨電腦搬遷 ----

    def _used_templates(self):
        """步驟引用的所有範本 (含「點擊後確認」的確認圖)."""
        used = set()
        for s in self.steps:
            if s.get("type") == "find_click" and s.get("template"):
                used.add(s["template"])
            if s.get("confirm") == "appear" and s.get("confirmTemplate"):
                used.add(s["confirmTemplate"])
        return sorted(used)

    def export_pack(self):
        """儲存流程 (唯一格式: 流程包 zip, 含引用的範本圖與中繼資料)."""
        if not self.steps:
            messagebox.showinfo("儲存流程", "沒有步驟可儲存", parent=self.root)
            return
        used = self._used_templates()
        missing = [n for n in used
                   if not os.path.exists(os.path.join(TEMPLATES_DIR, n))]
        if missing:
            messagebox.showwarning("儲存流程",
                                   "以下範本不存在，無法儲存：\n" + "\n".join(missing),
                                   parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, title="儲存流程（含範本）", initialdir=FLOWS_DIR,
            defaultextension=".autoclickpack",
            filetypes=[("AutoClick 流程包", "*.autoclickpack")])
        if not path:
            return
        meta = self._load_meta()
        pmeta = {"pos": {n: meta["pos"][n] for n in used if n in meta["pos"]}}
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("flow.json",
                       json.dumps(self._flow_data(), ensure_ascii=False, indent=2))
            z.writestr("templates/_meta.json",
                       json.dumps(pmeta, ensure_ascii=False))
            for n in used:
                z.write(os.path.join(TEMPLATES_DIR, n), f"templates/{n}")
        self.log_ui(f"已儲存流程 {os.path.basename(path)}（含 {len(used)} 個範本）", "ok")

    def import_pack(self):
        """載入流程: 流程包 (zip) 或舊版純 JSON 流程 (.autoclick/.json)."""
        path = filedialog.askopenfilename(
            parent=self.root, title="載入流程", initialdir=FLOWS_DIR,
            filetypes=[("AutoClick 流程", "*.autoclickpack *.autoclick *.json"),
                       ("所有檔案", "*.*")])
        if not path:
            return
        if not zipfile.is_zipfile(path):
            try:  # 舊版純 JSON 流程 (不含範本)
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                self._apply_flow(data)
                self.log_ui(f"已載入流程 {os.path.basename(path)}", "ok")
            except Exception as e:
                messagebox.showerror("載入流程", f"載入失敗: {e}", parent=self.root)
            return
        try:
            with zipfile.ZipFile(path) as z:
                data = json.loads(z.read("flow.json").decode("utf-8"))
                try:
                    pmeta = json.loads(z.read("templates/_meta.json").decode("utf-8"))
                except KeyError:
                    pmeta = {"pos": {}}
                names = [i.filename[len("templates/"):] for i in z.infolist()
                         if i.filename.startswith("templates/")
                         and not i.filename.startswith("templates/_orig/")
                         and i.filename.lower().endswith(".png")]
                rename = {}
                meta = self._load_meta()
                for n in names:
                    content = z.read(f"templates/{n}")
                    dest = os.path.join(TEMPLATES_DIR, n)
                    final = n
                    if os.path.exists(dest):
                        with open(dest, "rb") as f:
                            if f.read() == content:
                                final = n  # 內容相同 → 直接沿用既有範本
                            else:
                                final = self._free_name(n)  # 同名不同圖 → 改名匯入
                                rename[n] = final
                    if final != n or not os.path.exists(dest):
                        fp = os.path.join(TEMPLATES_DIR, final)
                        os.makedirs(os.path.dirname(fp), exist_ok=True)
                        with open(fp, "wb") as f:
                            f.write(content)
                    if n in pmeta.get("pos", {}):
                        meta["pos"][final] = pmeta["pos"][n]
                self._save_meta(meta)
                for s in data.get("steps", []):
                    for k in ("template", "confirmTemplate"):
                        if s.get(k) in rename:
                            s[k] = rename[s[k]]
            self._apply_flow(data)
            self.refresh_templates()
            msg = f"已載入流程 {os.path.basename(path)}（{len(names)} 個範本）"
            if rename:
                msg += "；同名改為：" + "、".join(
                    f"{k}→{v2}" for k, v2 in rename.items())
            self.log_ui(msg, "ok")
        except Exception as e:
            messagebox.showerror("載入流程", f"載入失敗: {e}", parent=self.root)

    def _autosave(self):
        try:
            with open(AUTOSAVE, "w", encoding="utf-8") as f:
                json.dump(self._flow_data(), f, ensure_ascii=False)
        except OSError:
            pass

    def _load_autosave(self):
        try:
            with open(AUTOSAVE, encoding="utf-8") as f:
                self._apply_flow(json.load(f))
        except (OSError, ValueError):
            pass

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
        steps = self.steps if steps is None else steps
        if not steps:
            messagebox.showinfo("執行", "請先新增步驟", parent=self.root)
            return
        names = set(self.list_template_names())
        missing = []
        for s in steps:
            if s["type"] != "find_click":
                continue
            if s.get("template") not in names:
                missing.append(s.get("template") or "(未選擇)")
            if (s.get("confirm") == "appear"
                    and s.get("confirmTemplate") not in names):
                missing.append((s.get("confirmTemplate") or "(未選擇)") + "（確認圖）")
        if missing:
            messagebox.showwarning("執行", "找圖步驟的範本不存在：\n" + "\n".join(missing),
                                   parent=self.root)
            return
        err = self._flow_error(steps)
        if err:
            messagebox.showwarning("執行", err, parent=self.root)
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
                              avoid_hover=self.avoid_hover.get())
        except RuntimeError as e:
            messagebox.showwarning("執行", str(e), parent=self.root)
            return
        self._run_steps = steps  # 迷你視窗步驟摘要要對照「實際在跑」的清單
        self._show_mini()  # 隱藏主視窗, 顯示迷你狀態視窗讓出畫面

    def stop_all(self):
        """F12 急停與停止鈕."""
        self.runner.stop()

    def _fragment_origin_error(self, steps, base):
        """片段內「執行到時必然沒有原點」的相對座標步驟編號 (完整清單編號).

        原點來源: 絕對座標點擊/拖曳、找圖步驟; 相對步驟在原點出現前執行
        只會被 runner 跳過, 測試片段時直接在執行前擋下.
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
                if s.get("updateOrigin", True):
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
                "以下相對座標步驟的原點不在選取範圍內，執行時會沒有基準：\n"
                f"步驟 {', '.join(map(str, bad))}\n"
                "請把作為原點的步驟（前面的點擊／拖曳／找圖）一起選進來",
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
        st = self.runner.status()
        running = st["running"]
        self.btn_run.configure(state="disabled" if running else "normal")
        self.btn_stop.configure(state="normal" if running else "disabled")
        if running:
            total = st["totalRounds"]
            if st["round"] == 0:
                text = "倒數啟動中…"
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

    def _on_callback_error(self, etype, value, tb):
        import traceback
        traceback.print_exception(etype, value, tb)  # 原始碼執行時仍印到主控台
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
