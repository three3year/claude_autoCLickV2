"""步驟編輯對話框與比對測試預覽視窗.

辨識一律走 app 的引擎接縫 (app.detector.query); 匹配門檻屬 profile config,
對話框不再有每步門檻欄位 (ADR 0002)。
"""
import time
import tkinter as tk
from tkinter import messagebox, ttk

import cv2

import ui_grab
import ui_overlay
import ui_theme
from automation import capture, win
from ui_theme import C, FONT

BTN_NAMES = [("left", "左鍵"), ("right", "右鍵"), ("middle", "中鍵")]
BTN_ZH2KEY = {n: k for k, n in BTN_NAMES}
STEP_TITLES = {
    "click": "座標點擊",
    "find_click": "找圖點擊",
    "drag": "滑鼠拖曳",
    "wait": "等待",
    "key": "按鍵",
    "loop_start": "重複開始",
    "loop_end": "重複結束",
    "branch_end": "分岔結束",
}


def _center(dlg, parent):
    """置中於 parent 上方 1/3 處, 夾在 parent 所在螢幕的工作區內.

    多螢幕虛擬桌面原點可為負, 不能用 max(0, x) 夾座標,
    否則主視窗在負座標螢幕時子視窗會被推到主螢幕.
    """
    dlg.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - dlg.winfo_width()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - dlg.winfo_height()) // 3
    mx1, my1, mx2, my2 = win.monitor_work_area(parent.winfo_id())
    x = max(mx1, min(x, mx2 - dlg.winfo_width()))
    y = max(my1, min(y, my2 - dlg.winfo_height()))
    dlg.geometry(f"+{x}+{y}")


def _flash(dlg, times=2):
    """閃爍對話框透明度, 提示使用者需先處理此視窗 (幅度輕微以免傷眼)."""
    def pulse(i):
        try:
            dlg.attributes("-alpha", 0.85 if i % 2 == 0 else 1.0)
        except tk.TclError:
            return
        if i + 1 < times * 2:
            dlg.after(70, lambda: pulse(i + 1))
    dlg.lift()
    dlg.focus_force()
    pulse(0)


def make_modal(dlg):
    """讓 dlg 獨占互動; 點擊應用程式其他視窗時閃爍 dlg 提示.

    入堆/出堆與 grab 歸屬由 ui_grab 的 modal 堆疊統一管理: grab 永遠在
    堆頂, 關閉 (含中途關閉非堆頂) 後自動回到下一層——疊開的巢狀視窗
    不再需要 prev 交接參數, 也沒有輪詢逾時放棄。
    """
    ui_grab.register_modal(dlg)

    def on_press(e):
        # grab 生效時, 點在其他視窗的事件會轉送到本視窗, 座標會落在視窗範圍外
        if (e.x_root < dlg.winfo_rootx()
                or e.x_root >= dlg.winfo_rootx() + dlg.winfo_width()
                or e.y_root < dlg.winfo_rooty()
                or e.y_root >= dlg.winfo_rooty() + dlg.winfo_height()):
            _flash(dlg)

    dlg.bind("<ButtonPress>", on_press, add=True)


THUMB_W, THUMB_H = 176, 120


def _thumb_photo(master, img, bw=THUMB_W, bh=THUMB_H):
    """把 BGR/BGRA 影像縮放置中到「固定尺寸」底圖, 回傳 PhotoImage.

    固定尺寸讓預覽框不會隨範本大小忽大忽小; 透明區以洋紅色顯示;
    img=None 回傳純底色佔位圖.
    """
    import numpy as np
    bg = np.zeros((bh, bw, 3), np.uint8)
    bg[:] = (42, 23, 15)  # C["bg"] #0F172A 的 BGR
    if img is not None:
        if img.ndim == 3 and img.shape[2] == 4:
            alpha = img[:, :, 3:4].astype(np.float32) / 255.0
            mag = np.zeros_like(img[:, :, :3])
            mag[:] = (255, 0, 255)
            img = (img[:, :, :3].astype(np.float32) * alpha
                   + mag.astype(np.float32) * (1 - alpha)).astype(np.uint8)
        h, w = img.shape[:2]
        s = min(bw / w, bh / h, 1.0)
        nw, nh = max(1, int(w * s)), max(1, int(h * s))
        img2 = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
        y0, x0 = (bh - nh) // 2, (bw - nw) // 2
        bg[y0:y0 + nh, x0:x0 + nw] = img2
    rgb = cv2.cvtColor(bg, cv2.COLOR_BGR2RGB)
    return tk.PhotoImage(master=master,
                         data=f"P6 {bw} {bh} 255 ".encode() + rgb.tobytes())


def _check(parent, text, var, bg=None):
    """深色主題勾選框 (Label ☑/☐ 實作): ttk clam 的勾選記號長得像叉叉."""
    lbl = tk.Label(parent, bg=bg or C["panel"], fg=C["text"], font=FONT,
                   cursor="hand2")

    def sync(*_):
        lbl.configure(text=("☑ " if var.get() else "☐ ") + text)

    lbl.bind("<Button-1>", lambda e: var.set(not var.get()))
    var.trace_add("write", sync)
    sync()
    return lbl


def ask_string(root, title, prompt, initialvalue=""):
    """深色主題版 askstring (modal + 點外閃爍). 取消回傳 None."""
    dlg = tk.Toplevel(root)
    dlg.title(title)
    dlg.configure(bg=C["panel"])
    dlg.resizable(False, False)
    dlg.transient(root)

    body = ttk.Frame(dlg, style="Panel.TFrame", padding=16)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text=prompt, style="Panel.TLabel").pack(anchor="w")
    var = tk.StringVar(value=initialvalue)
    ent = ttk.Entry(body, textvariable=var, width=32)
    ent.pack(pady=(8, 0), fill="x")

    result = [None]

    def on_ok():
        result[0] = var.get()
        dlg.destroy()

    foot = ttk.Frame(dlg, style="Panel.TFrame", padding=(16, 0, 16, 14))
    foot.pack(fill="x")
    ttk.Button(foot, text="取消", command=dlg.destroy).pack(side="right", padx=(8, 0))
    ttk.Button(foot, text="確定", style="Run.TButton", command=on_ok).pack(side="right")
    dlg.bind("<Return>", lambda e: on_ok())
    dlg.bind("<Escape>", lambda e: dlg.destroy())

    _center(dlg, root)
    make_modal(dlg)
    dlg.focus_force()
    ent.focus_set()
    ent.select_range(0, "end")
    root.wait_window(dlg)
    return result[0]


def _region_origin(app, parent):
    """`絕對座標`的基準＝`搜尋範圍`左上角; 沒設範圍就擋下並說明.

    座標存的是相對範圍的偏移, 沒有範圍就沒有基準可言。
    必須在進入清場「之前」呼叫: 清場期間 parent 已被隱藏, 以它為 parent
    彈 messagebox 會整個看不見卻在等確認, 體感就是卡死。
    """
    region = getattr(app, "scan_region", None)
    if not region:
        messagebox.showwarning(
            "拾取座標",
            "絕對座標是以「搜尋範圍」左上角為基準的，請先在主視窗框選搜尋範圍。\n\n"
            "（這樣視窗換位置時，座標會自動跟著搬過去，不必重新拾取）",
            parent=parent)
        return None
    return int(region[0]), int(region[1])


def _find_template_now(app, dlg, prev):
    """隱藏視窗後在框選範圍內即時查一次 prev 的範本, 回傳中心座標或 None."""
    name = prev.get("template", "")
    if not app.hub.ready:
        # `引擎就緒`前提示並拒絕 (清場中不得彈 modal——會隱形卡死);
        # 回 None 走「截圖當下位置」備援, 拾取流程不中斷
        if not ui_grab.coord.clearing:
            app.engine_gate(parent=dlg)
        return None
    app.ensure_registered()  # 剛存的範本可能還在延後重登錄佇列中
    if name not in app.profile.templates:
        return None
    with ui_overlay.screen_clear(app.root, extra=(dlg,)):
        app.root.update()
        time.sleep(0.12)
        screen, org = capture.grab(getattr(app, "scan_region", None))
    r = app.detector.query(name, screen)
    if r.found:
        x, y, w, h = r.box
        return org[0] + x + w // 2, org[1] + y + h // 2
    return None


def _resolve_prev_origin(app, step, dlg):
    """推算相對座標拾取的預設原點 (螢幕座標), 無法推算回傳 None.

    從本步驟往上找「有座標的動作」(跳過等待/按鍵):
    - 絕對座標點擊 → 其點擊位置
    - 相對座標點擊 → 累積偏移, 繼續往上找基準
    - 滑鼠拖曳 → 其終點位置 (相對拖曳 → 累積終點偏移, 繼續往上找)
    - 找圖點擊 → 只有它就是「直接前一個原點步驟」(途中沒經過相對步驟)
      才在畫面上即時找一次 (找不到用截圖當下位置備援); 途中隔了相對
      點擊/拖曳時, 畫面通常已被那次點擊切換, 即時找到的殘留同圖不可信,
      一律用「截圖當下位置」重現使用者剛剛拾取的位置
    """
    idx = step.get("_index", 0)
    dx = dy = 0  # 途中經過的相對點擊累積偏移
    via_rel = False  # 途中是否經過相對步驟 (影響找圖的推算方式, 見 docstring)
    i = min(idx, len(app.steps)) - 1
    while i >= 0:
        prev = app.steps[i]
        t = prev["type"]
        if t == "click" and prev.get("updateOrigin", True):
            if prev.get("mode", "abs") == "abs":
                return int(prev["x"]) + dx, int(prev["y"]) + dy
            dx += int(prev["x"])
            dy += int(prev["y"])
            via_rel = True
        elif t == "drag":
            if prev.get("mode", "abs") == "abs":
                return int(prev["x2"]) + dx, int(prev["y2"]) + dy
            dx += int(prev["x2"])
            dy += int(prev["y2"])
            via_rel = True
        elif t == "find_click" and prev.get("updateOrigin", True):
            off = (int(prev.get("offsetX", 0)), int(prev.get("offsetY", 0)))
            if via_rel:
                pos = app.template_pos(prev.get("template", ""))
            else:
                pos = _find_template_now(app, dlg, prev) or app.template_pos(
                    prev.get("template", ""))
            if pos:
                return pos[0] + off[0] + dx, pos[1] + off[1] + dy
            return None  # 找圖位置無法推算, 中斷
        i -= 1  # 等待 / 按鍵 / 不更新原點的找圖 → 往上繼續找
    return None


def edit_step(app, step):
    """開啟步驟編輯對話框. 回傳修改後的 step dict, 取消回傳 None."""
    root = app.root
    dlg = tk.Toplevel(root)
    dlg.title(("編輯：" if step.get("_edit") else "新增：") + STEP_TITLES[step["type"]])
    dlg.configure(bg=C["panel"])
    dlg.resizable(False, False)
    dlg.transient(root)

    body = ttk.Frame(dlg, style="Panel.TFrame", padding=16)
    body.pack(fill="both", expand=True)
    row_i = [0]

    def add_row(label):
        """建立一列, 回傳可放置元件的 frame (元件須以此 frame 為父)."""
        ttk.Label(body, text=label, style="Muted.TLabel").grid(
            row=row_i[0], column=0, sticky="w", pady=3, padx=(0, 12))
        fr = ttk.Frame(body, style="Panel.TFrame")
        fr.grid(row=row_i[0], column=1, sticky="w", pady=3)
        row_i[0] += 1
        return fr

    def add_note(text):
        # wraplength 放寬讓說明少換行——找圖對話框列數多, 高度要壓在工作區內
        w = ttk.Label(body, text=text, style="Muted.TLabel",
                      font=("Microsoft JhengHei UI", 9), wraplength=470,
                      justify="left")
        w.grid(row=row_i[0], column=1, sticky="w", pady=(0, 4))
        row_i[0] += 1
        return w

    def lbl(parent, text):
        w = ttk.Label(parent, text=text, style="Muted.TLabel")
        w.pack(side="left", padx=(0, 4))
        return w

    def mouse_row(v):
        fr = add_row("滑鼠按鍵")
        cb = ttk.Combobox(fr, width=6, state="readonly",
                          values=[n for _, n in BTN_NAMES])
        cb.set(dict(BTN_NAMES)[v["button"].get()])
        cb.bind("<<ComboboxSelected>>",
                lambda e: v["button"].set(BTN_ZH2KEY[cb.get()]))
        cb.pack(side="left", padx=(0, 8))
        lbl(fr, "連點")
        ttk.Spinbox(fr, textvariable=v["clicks"], from_=1, to=10, width=4).pack(
            side="left", padx=(0, 4))
        lbl(fr, "次")

    result = [None]
    t = step["type"]
    v = {}

    if t == "click":
        MODE_ZH = {"abs": "絕對座標（搜尋範圍內）", "prev": "相對上一步點擊位置"}
        MODE_KEY = {n: k for k, n in MODE_ZH.items()}
        MODE_NOTE = {
            "abs": "以螢幕左上角為原點的絕對座標；「截圖拾取」在畫面上點一下即填入該點座標",
            "prev": "以前一個點擊位置為原點的偏移量（找圖步驟選「不點擊」時，"
                    "找到的位置也算）；勾選「預設原點」時截圖拾取會自動標出原點，"
                    "點一下目標即完成；取消勾選則拖線：起點＝基準、終點＝目標",
        }
        v["x"] = tk.IntVar(value=step.get("x", 500))
        v["y"] = tk.IntVar(value=step.get("y", 400))
        # 新增預設「相對上一步」; 編輯時缺 mode 鍵必須維持絕對 (執行期預設 abs)
        v["mode"] = tk.StringVar(
            value=MODE_ZH.get(step.get("mode",
                                       "abs" if step.get("_edit") else "prev"),
                              MODE_ZH["abs"]))
        v["button"] = tk.StringVar(value=step.get("button", "left"))
        v["clicks"] = tk.IntVar(value=step.get("clicks", 1))

        fr = add_row("座標基準")
        mode_cb = ttk.Combobox(fr, textvariable=v["mode"], width=20,
                               state="readonly", values=list(MODE_ZH.values()))
        mode_cb.pack(side="left")

        note_lbl = add_note(MODE_NOTE[MODE_KEY[v["mode"].get()]])
        mode_cb.bind("<<ComboboxSelected>>",
                     lambda e: note_lbl.configure(
                         text=MODE_NOTE[MODE_KEY[v["mode"].get()]]))

        fr = add_row("座標")
        lbl(fr, "X")
        ttk.Entry(fr, textvariable=v["x"], width=7).pack(side="left", padx=(0, 8))
        lbl(fr, "Y")
        ttk.Entry(fr, textvariable=v["y"], width=7).pack(side="left", padx=(0, 8))

        v["use_base"] = tk.BooleanVar(value=True)

        def pick_pos():
            # 整段包進同一個 screen_clear: 找圖預查與拾取之間視窗保持隱藏,
            # 沒有「還原→再隱藏」的空窗 (歷來卡死競態的根源)
            mode = MODE_KEY[v["mode"].get()]
            if mode != "prev":
                # 基準檢查在清場「前」做: 清場中彈 messagebox 會隱形 (票 07)
                org = _region_origin(app, dlg)
                if org is None:
                    return
            with ui_overlay.screen_clear(root, extra=(dlg,)):
                if mode == "prev":
                    base = _resolve_prev_origin(app, step, dlg) if v["use_base"].get() else None
                    if base is not None:
                        r = ui_overlay.pick(root, "line", "點一下要點擊的位置（原點＝上一步位置）",
                                            hide=(dlg,), base=base)
                    else:
                        r = ui_overlay.pick(
                            root, "line",
                            "拖曳一條線：起點＝上一步點擊位置（基準），終點＝要點擊的位置",
                            hide=(dlg,))
                    if r:
                        v["x"].set(r["dx"])
                        v["y"].set(r["dy"])
                else:
                    r = ui_overlay.pick(root, "point", "在畫面上點一下，選取要點擊的位置",
                                        hide=(dlg,))
                    if r:
                        v["x"].set(r["screenX"] - org[0])
                        v["y"].set(r["screenY"] - org[1])

        ttk.Button(fr, text="截圖拾取", style="Accent.TButton",
                   command=pick_pos).pack(side="left")
        base_chk = _check(fr, "預設原點", v["use_base"])

        def sync_base_chk():
            # 只有「相對上一步點擊」模式才有預設原點可用
            if MODE_KEY[v["mode"].get()] == "prev":
                base_chk.pack(side="left", padx=(8, 0))
            else:
                base_chk.pack_forget()

        sync_base_chk()
        mode_cb.bind("<<ComboboxSelected>>", lambda e: sync_base_chk(), add=True)
        mouse_row(v)
        v["updateOrigin"] = tk.BooleanVar(value=step.get("updateOrigin", True))
        fr = add_row("相對座標")
        _check(fr, "把點擊位置更新為相對座標原點", v["updateOrigin"]).pack(
            side="left")

    elif t == "drag":
        MODE_ZH = {"abs": "絕對座標（搜尋範圍內）", "prev": "相對上一步點擊位置"}
        MODE_KEY = {n: k for k, n in MODE_ZH.items()}
        MODE_NOTE = {
            "abs": "以螢幕左上角為原點的絕對座標；「截圖拾取」在畫面上拖一條線，"
                   "起點與終點會一併填入",
            "prev": "起點與終點都是以前一個點擊位置為原點的偏移量（找圖步驟不點擊時"
                    "找到的位置、拖曳終點也算）；勾選「預設原點」時截圖拾取會標出原點◎，"
                    "直接拖出拖曳路徑即可；取消勾選則先點一下原點，再拖出拖曳路徑",
        }
        v["x1"] = tk.IntVar(value=step.get("x1", 400))
        v["y1"] = tk.IntVar(value=step.get("y1", 300))
        v["x2"] = tk.IntVar(value=step.get("x2", 600))
        v["y2"] = tk.IntVar(value=step.get("y2", 400))
        v["mode"] = tk.StringVar(
            value=MODE_ZH.get(step.get("mode", "abs"), MODE_ZH["abs"]))
        v["button"] = tk.StringVar(value=step.get("button", "left"))
        v["ms"] = tk.IntVar(value=step.get("ms", 500))
        v["holdMs"] = tk.IntVar(value=step.get("holdMs", 0))

        fr = add_row("座標基準")
        mode_cb = ttk.Combobox(fr, textvariable=v["mode"], width=20,
                               state="readonly", values=list(MODE_ZH.values()))
        mode_cb.pack(side="left")

        note_lbl = add_note(MODE_NOTE[MODE_KEY[v["mode"].get()]])
        mode_cb.bind("<<ComboboxSelected>>",
                     lambda e: note_lbl.configure(
                         text=MODE_NOTE[MODE_KEY[v["mode"].get()]]))

        fr = add_row("起點")
        lbl(fr, "X")
        ttk.Entry(fr, textvariable=v["x1"], width=7).pack(side="left", padx=(0, 8))
        lbl(fr, "Y")
        ttk.Entry(fr, textvariable=v["y1"], width=7).pack(side="left", padx=(0, 8))

        v["use_base"] = tk.BooleanVar(value=True)

        def pick_drag():
            # 整段包進同一個 screen_clear: 預查/兩段拾取之間視窗保持隱藏,
            # 沒有「還原→再隱藏」的空窗 (歷來卡死競態的根源)
            if MODE_KEY[v["mode"].get()] != "prev":
                # 基準檢查在清場「前」做: 清場中彈 messagebox 會隱形 (票 07)
                org = _region_origin(app, dlg)
                if org is None:
                    return
            with ui_overlay.screen_clear(root, extra=(dlg,)):
                if MODE_KEY[v["mode"].get()] == "prev":
                    base = _resolve_prev_origin(app, step, dlg) if v["use_base"].get() else None
                    if base is None:
                        p = ui_overlay.pick(
                            root, "point",
                            "先點一下原點（上一步點擊位置），接著再拖出拖曳路徑",
                            hide=(dlg,))
                        if not p:
                            return
                        base = (p["screenX"], p["screenY"])
                    r = ui_overlay.pick(root, "line",
                                        "拖曳一條線：起點＝按下位置，終點＝放開位置",
                                        hide=(dlg,), mark=base)
                    if r:
                        v["x1"].set(r["startX"] - base[0])
                        v["y1"].set(r["startY"] - base[1])
                        v["x2"].set(r["endX"] - base[0])
                        v["y2"].set(r["endY"] - base[1])
                else:
                    r = ui_overlay.pick(root, "line",
                                        "拖曳一條線：起點＝按下位置，終點＝放開位置",
                                        hide=(dlg,))
                    if r:
                        v["x1"].set(r["startX"] - org[0])
                        v["y1"].set(r["startY"] - org[1])
                        v["x2"].set(r["endX"] - org[0])
                        v["y2"].set(r["endY"] - org[1])

        ttk.Button(fr, text="截圖拾取", style="Accent.TButton",
                   command=pick_drag).pack(side="left")
        base_chk = _check(fr, "預設原點", v["use_base"])

        def sync_base_chk():
            # 只有「相對上一步點擊」模式才有預設原點可用
            if MODE_KEY[v["mode"].get()] == "prev":
                base_chk.pack(side="left", padx=(8, 0))
            else:
                base_chk.pack_forget()

        sync_base_chk()
        mode_cb.bind("<<ComboboxSelected>>", lambda e: sync_base_chk(), add=True)

        fr = add_row("終點")
        lbl(fr, "X")
        ttk.Entry(fr, textvariable=v["x2"], width=7).pack(side="left", padx=(0, 8))
        lbl(fr, "Y")
        ttk.Entry(fr, textvariable=v["y2"], width=7).pack(side="left", padx=(0, 8))

        fr = add_row("滑鼠按鍵")
        cb = ttk.Combobox(fr, width=6, state="readonly",
                          values=[n for _, n in BTN_NAMES])
        cb.set(dict(BTN_NAMES)[v["button"].get()])
        cb.bind("<<ComboboxSelected>>",
                lambda e: v["button"].set(BTN_ZH2KEY[cb.get()]))
        cb.pack(side="left", padx=(0, 8))
        lbl(fr, "拖曳時間")
        ttk.Spinbox(fr, textvariable=v["ms"], from_=50, to=10000,
                    increment=50, width=7).pack(side="left", padx=(0, 4))
        lbl(fr, "毫秒")

        fr = add_row("放開前停頓")
        ttk.Spinbox(fr, textvariable=v["holdMs"], from_=0, to=5000,
                    increment=100, width=7).pack(side="left", padx=(0, 4))
        lbl(fr, "毫秒")
        add_note("到達終點後按住停頓再放開；捲動類介面直接放開會慣性滾過頭，"
                 "建議 500 毫秒左右；0＝直接放開")

    elif t == "wait":
        v["ms"] = tk.IntVar(value=step.get("ms", 1000))
        fr = add_row("等待時間")
        ttk.Spinbox(fr, textvariable=v["ms"], from_=10, to=3600000,
                    increment=100, width=10).pack(side="left", padx=(0, 4))
        lbl(fr, "毫秒")

    elif t == "loop_start":
        v["count"] = tk.IntVar(value=step.get("count", 3))
        fr = add_row("重複次數")
        ttk.Spinbox(fr, textvariable=v["count"], from_=1, to=99999,
                    width=7).pack(side="left", padx=(0, 4))
        lbl(fr, "次")
        add_note("把要重複的步驟放在「重複開始」與「重複結束」之間"
                 "（可用 ≡ 把手拖曳排列）；區段可以巢狀")

    elif t in ("loop_end", "branch_end"):
        BRK_ZH = {"continue": "繼續往下執行", "break": "再往外跳出一層區段"}
        seg = "重複" if t == "loop_end" else "分岔"
        v["onBreak"] = tk.StringVar(
            value=BRK_ZH.get(step.get("onBreak", "continue"), BRK_ZH["continue"]))
        fr = add_row("找不到跳出到此時")
        ttk.Combobox(fr, textvariable=v["onBreak"], width=20, state="readonly",
                     values=list(BRK_ZH.values())).pack(side="left")
        add_note(f"當內層步驟因「找不到 → 跳出目前區段」跳到這個{seg}結尾時的動作。"
                 "選「再往外跳出一層區段」可讓外層區段也一起跳出——"
                 "例如重複(FOR)內的分岔(IF)找不到時，直接跳出整個重複區段。"
                 "（正常執行流程到達此處不受影響）")

    elif t == "key":
        v["keys"] = tk.StringVar(value=step.get("keys", "enter"))
        fr = add_row("按鍵")
        ttk.Entry(fr, textvariable=v["keys"], width=24).pack(side="left")
        add_note("單鍵如 enter、esc、f5、a；組合鍵用 + 連接，如 ctrl+v、alt+f4")

    elif t == "find_click":
        v["template"] = tk.StringVar(value=step.get("template", ""))
        v["timeout"] = tk.DoubleVar(value=step.get("timeout", 10))
        v["interval"] = tk.DoubleVar(value=step.get("interval", 0.5))
        ACT_ZH = {"click": "點擊該圖片",
                  "none": "不點擊（僅等待出現）",
                  "wait_gone": "不點擊（等待消失）"}
        ACT_KEY = {n: k for k, n in ACT_ZH.items()}
        v["action"] = tk.StringVar(
            value=ACT_ZH.get(step.get("action", "click"), ACT_ZH["click"]))
        v["button"] = tk.StringVar(value=step.get("button", "left"))
        v["clicks"] = tk.IntVar(value=step.get("clicks", 1))
        v["offsetX"] = tk.IntVar(value=step.get("offsetX", 0))
        v["offsetY"] = tk.IntVar(value=step.get("offsetY", 0))
        NF_ZH = {"skip": "跳過此步驟繼續", "break": "跳出目前區段",
                 "stop": "停止整個流程"}
        v["onNotFound"] = tk.StringVar(
            value=NF_ZH.get(step.get("onNotFound", "skip"), NF_ZH["skip"]))

        PENDING = "（新截圖，確定後加入範本）"
        pending = [None]  # 尚未存檔的截圖 (按確定才匯入範本)

        fr = add_row("範本圖片")
        tmpl_cb = ttk.Combobox(fr, textvariable=v["template"],
                               values=app.list_template_names(), width=24,
                               state="readonly")
        tmpl_cb.pack(side="left", padx=(0, 6))

        fr = add_row("預覽")
        pv_lbl = tk.Label(fr, bg=C["bg"], bd=0, highlightthickness=1,
                          highlightbackground=C["border"])
        pv_lbl.pack(side="left")
        PV_W, PV_H = 150, 84  # 比主視窗縮圖小: 這個對話框列數多, 高度優先

        def cur_tmpl_img():
            """目前選擇的範本影像 (暫存截圖或已登錄範本), 無則 None."""
            if v["template"].get() == PENDING:
                return pending[0]["img"] if pending[0] else None
            nm = v["template"].get()
            if nm:
                return app.template_image(nm)
            return None

        def update_preview(*_):
            ph = _thumb_photo(dlg, cur_tmpl_img(), bw=PV_W, bh=PV_H)
            pv_lbl.configure(image=ph)
            pv_lbl._photo = ph

        tmpl_cb.bind("<<ComboboxSelected>>", update_preview, add=True)
        update_preview()

        def new_tmpl():
            r = app.pick_region_raw(hide=(dlg,))
            if r:
                pending[0] = r
                v["template"].set(PENDING)
                update_preview()

        # 回到範本圖片列補上按鈕 (排版在 combobox 之後)
        ttk.Button(tmpl_cb.master, text="截圖新增", style="Accent.TButton",
                   command=new_tmpl).pack(side="left")

        fr = add_row("等待逾時")
        ttk.Spinbox(fr, textvariable=v["timeout"], from_=0, to=3600,
                    increment=1, width=7).pack(side="left", padx=(0, 4))
        lbl(fr, "秒，每")
        ttk.Spinbox(fr, textvariable=v["interval"], from_=0.1, to=60,
                    increment=0.1, width=6).pack(side="left", padx=(0, 4))
        lbl(fr, "秒重試")

        fr = add_row("找到之後")
        act_cb = ttk.Combobox(fr, textvariable=v["action"], width=20,
                              state="readonly", values=list(ACT_ZH.values()))
        act_cb.pack(side="left")
        mouse_row(v)

        fr = add_row("點擊偏移")
        lbl(fr, "X")
        ttk.Entry(fr, textvariable=v["offsetX"], width=6).pack(side="left", padx=(0, 8))
        lbl(fr, "Y")
        ttk.Entry(fr, textvariable=v["offsetY"], width=6).pack(side="left")
        add_note("預設點在找到圖片的中心；偏移可點在圖片周圍的相對位置")

        # 點擊後確認生效: 對付「圖找到也點了, 但畫面轉場中吃不到點擊」(只有點擊時才有意義)
        CFM_ZH = {"none": "不確認（點一次）",
                  "gone": "點到目標圖消失為止",
                  "appear": "點到確認圖出現為止",
                  "next": "點到下一步的圖出現"}
        CFM_KEY = {n: k for k, n in CFM_ZH.items()}
        v["confirm"] = tk.StringVar(
            value=CFM_ZH.get(step.get("confirm", "none"), CFM_ZH["none"]))
        v["confirmTemplate"] = tk.StringVar(value=step.get("confirmTemplate", ""))

        # 「點擊後確認」整列自建 label 方便隨「不點擊」整列隱藏
        cfm_mode_lbl = ttk.Label(body, text="點擊後確認", style="Muted.TLabel")
        cfm_mode_lbl.grid(row=row_i[0], column=0, sticky="w", pady=5, padx=(0, 12))
        cfm_mode_fr = ttk.Frame(body, style="Panel.TFrame")
        cfm_mode_fr.grid(row=row_i[0], column=1, sticky="w", pady=5)
        row_i[0] += 1
        cfm_cb = ttk.Combobox(cfm_mode_fr, textvariable=v["confirm"], width=20,
                              state="readonly", values=list(CFM_ZH.values()))
        cfm_cb.pack(side="left")
        cfm_main_note = add_note(
            "沒生效（目標圖還在）就自動再點，直到生效或逾時（用上面的逾時/重試秒數）；"
            "仍未生效則依「找不到時」處置。「點到下一步的圖出現」以緊接的下一個"
            "找圖步驟要找的圖為生效條件（依清單位置跟隨，不必另選確認圖；"
            "下一步還不是找圖時可先存檔，該列會顯示 ⚠，執行前需排相連）")

        # 確認圖 (僅「點到確認圖出現」需要): 自建 label 方便整列顯示/隱藏
        cfm_lbl = ttk.Label(body, text="確認圖", style="Muted.TLabel")
        cfm_lbl.grid(row=row_i[0], column=0, sticky="w", pady=5, padx=(0, 12))
        cfm_row = ttk.Frame(body, style="Panel.TFrame")
        cfm_row.grid(row=row_i[0], column=1, sticky="w", pady=5)
        row_i[0] += 1
        cfm_tmpl_cb = ttk.Combobox(cfm_row, textvariable=v["confirmTemplate"],
                                   values=app.list_template_names(), width=24,
                                   state="readonly")
        cfm_tmpl_cb.pack(side="left", padx=(0, 6))

        def new_cfm_tmpl():
            r = app.pick_region_raw(hide=(dlg,))
            if r:
                nm = app.save_captured(r)  # 確認圖即時存檔 (不走主範本的 pending)
                cfm_tmpl_cb.configure(values=app.list_template_names())
                v["confirmTemplate"].set(nm)

        ttk.Button(cfm_row, text="截圖新增", style="Accent.TButton",
                   command=new_cfm_tmpl).pack(side="left")
        cfm_tmpl_note = add_note("截「點成功後才會出現」的下一畫面圖案（如結算畫面、下一關按鈕）")

        # 是否把找到 (點擊) 的位置更新為相對座標原點
        v["updateOrigin"] = tk.BooleanVar(value=step.get("updateOrigin", True))
        fr = add_row("相對座標")
        _check(fr, "把此步驟的位置更新為相對座標原點", v["updateOrigin"]).pack(
            side="left")
        add_note("取消勾選＝此步驟不影響「相對上一步」的原點，"
                 "後面的相對座標步驟沿用更早的位置")

        def sync_click_opts(*_):
            # 「不點擊」時整個「點擊後確認」都無意義 → 隱藏; 確認圖再依 appear 決定
            is_click = ACT_KEY[v["action"].get()] == "click"
            for w in (cfm_mode_lbl, cfm_mode_fr, cfm_main_note):
                w.grid() if is_click else w.grid_remove()
            appear = is_click and CFM_KEY[v["confirm"].get()] == "appear"
            for w in (cfm_lbl, cfm_row, cfm_tmpl_note):
                w.grid() if appear else w.grid_remove()

        sync_click_opts()
        act_cb.bind("<<ComboboxSelected>>", sync_click_opts, add=True)
        cfm_cb.bind("<<ComboboxSelected>>", sync_click_opts, add=True)

        fr = add_row("找不到時")
        ttk.Combobox(fr, textvariable=v["onNotFound"], width=18, state="readonly",
                     values=list(NF_ZH.values())).pack(side="left")
        add_note("找不到圖、或點了確認不生效時的處置。跳出目前區段＝跳到此步驟所在的"
                 "重複/分岔區段結尾之後（重複區段放棄剩餘次數）；不在任何區段內時等同停止")

        fr = add_row("測試")

        def test_now():
            name = v["template"].get()
            if not name:
                messagebox.showwarning("測試", "請先選擇範本圖片", parent=dlg)
                return
            if name == PENDING:
                if pending[0] is None:
                    messagebox.showwarning("測試", "請先選擇範本圖片", parent=dlg)
                    return
                # 引擎只查得到已登錄的範本 → 先存檔登錄再測
                # (與確認圖同慣例: 即時存檔, 之後取消對話框範本仍會留下)
                name = app.save_captured(pending[0])
                pending[0] = None
                v["template"].set(name)
                tmpl_cb.configure(values=app.list_template_names())
            show_match_test(app, name, hide=(dlg,))

        ttk.Button(fr, text="立即比對測試", style="Accent.TButton",
                   command=test_now).pack(side="left")

    # ---- 確定 / 取消 ----
    foot = ttk.Frame(dlg, style="Panel.TFrame", padding=(16, 0, 16, 14))
    foot.pack(fill="x")

    def on_ok():
        s = dict(step)
        s.pop("_edit", None)
        s.pop("_index", None)
        try:
            if t == "click":
                s.update(x=v["x"].get(), y=v["y"].get(),
                         mode={"絕對座標（搜尋範圍內）": "abs",
                               "相對上一步點擊位置": "prev"}[v["mode"].get()],
                         button=v["button"].get(), clicks=v["clicks"].get(),
                         updateOrigin=v["updateOrigin"].get())
            elif t == "drag":
                s.update(x1=v["x1"].get(), y1=v["y1"].get(),
                         x2=v["x2"].get(), y2=v["y2"].get(),
                         mode={"絕對座標（搜尋範圍內）": "abs",
                               "相對上一步點擊位置": "prev"}[v["mode"].get()],
                         button=v["button"].get(), ms=max(50, v["ms"].get()),
                         holdMs=max(0, v["holdMs"].get()))
            elif t == "loop_start":
                s.update(count=max(1, v["count"].get()))
            elif t in ("loop_end", "branch_end"):
                s.update(onBreak={"繼續往下執行": "continue",
                                  "再往外跳出一層區段": "break"}[v["onBreak"].get()])
            elif t == "wait":
                s.update(ms=max(10, v["ms"].get()))
            elif t == "key":
                keys = v["keys"].get().strip()
                if not keys:
                    raise ValueError("請輸入按鍵")
                s.update(keys=keys)
            elif t == "find_click":
                if not v["template"].get():
                    raise ValueError("請選擇範本圖片")
                if v["template"].get() == PENDING:
                    if pending[0] is None:
                        raise ValueError("請選擇範本圖片")
                    v["template"].set(app.save_captured(pending[0]))  # 確定才匯入
                action = ACT_KEY[v["action"].get()]
                confirm = CFM_KEY[v["confirm"].get()] if action == "click" else "none"
                if confirm == "appear" and not v["confirmTemplate"].get():
                    raise ValueError("「點到確認圖出現」需選擇確認圖")
                # confirm == "next" 而下一步不是找圖時不在此擋下 (拍板
                # 2026-08-16 修訂): 允許先存, 由步驟清單的 ⚠ 標記提示、
                # 執行前檢查攔下——作者常先建這步再補下一步
                s.update(
                    template=v["template"].get(),
                    timeout=v["timeout"].get(),
                    interval=max(0.1, v["interval"].get()),
                    action=action,
                    button=v["button"].get(), clicks=v["clicks"].get(),
                    offsetX=v["offsetX"].get(), offsetY=v["offsetY"].get(),
                    onNotFound={n: k for k, n in NF_ZH.items()}[v["onNotFound"].get()],
                    confirm=confirm,
                    confirmTemplate=v["confirmTemplate"].get() if confirm == "appear" else "",
                    updateOrigin=v["updateOrigin"].get(),
                )
                s.pop("region", None)
                s.pop("rotate", None)  # 舊版執行期旋轉比對已移除
        except (tk.TclError, ValueError) as e:
            msg = str(e) if isinstance(e, ValueError) else "請確認數值欄位皆已正確填寫"
            messagebox.showwarning("輸入錯誤", msg, parent=dlg)
            return
        result[0] = s
        dlg.destroy()

    ttk.Button(foot, text="取消", command=dlg.destroy).pack(side="right", padx=(8, 0))
    ttk.Button(foot, text="確定", style="Run.TButton", command=on_ok).pack(side="right")
    dlg.bind("<Return>", lambda e: on_ok())
    dlg.bind("<Escape>", lambda e: dlg.destroy())

    _center(dlg, root)
    ui_theme.disable_transitions(dlg)  # 截圖前隱藏對話框需立即生效
    make_modal(dlg)
    dlg.focus_force()
    root.wait_window(dlg)
    return result[0]


def _annotate_query(screen_bgr, box, score, ok):
    """在畫面上框出引擎查詢的位置 (綠=通過, 紅=未達門檻), 回傳新影像."""
    img = screen_bgr.copy()
    if box is None:
        return img
    color = (0, 200, 60) if ok else (40, 40, 230)
    x, y, w, h = box
    cv2.rectangle(img, (x, y), (x + w, y + h), color, 3)
    cv2.putText(img, f"{score:.3f}", (x, max(20, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)
    return img


def show_match_test(app, template_name, region=None, hide=(), delay=0.0):
    """隱藏視窗 → 截取搜尋範圍 → 引擎查詢 → 顯示 box 與分數的標註預覽.

    region: 限定搜尋範圍 [x,y,w,h]; None 則用 app.scan_region, 再無則全螢幕.
    達標綠框 / 未達標紅框 (紅框為最接近的粗篩候選位置)。
    """
    root = app.root
    if not app.engine_gate():  # `引擎就緒`前提示並拒絕 (ADR 0004)
        return
    app.ensure_registered()  # 剛存的範本可能還在延後重登錄佇列中 (票 05)
    if template_name not in app.profile.templates:
        messagebox.showerror("測試", f"範本不存在: {template_name}")
        return

    scan = region or getattr(app, "scan_region", None)

    with ui_overlay.screen_clear(root, extra=hide):
        root.update()
        time.sleep(0.12 + delay)
        screen, origin = capture.grab(scan)

    r = app.detector.query(template_name, screen)
    box = r.box
    if box is None:  # 未達門檻: 用最接近的粗篩候選當紅框 (除錯線索)
        cands = r.debug.get("candidates") or []
        box = tuple(cands[0]["box"]) if cands else None
    annotated = _annotate_query(screen, box, r.score, r.found)

    win_ = tk.Toplevel(root)
    win_.title("比對測試結果")
    win_.configure(bg=C["panel"])
    win_.transient(root)

    cfg = app.profile.config
    if r.found:
        x, y, w, h = r.box
        cx, cy = origin[0] + x + w // 2, origin[1] + y + h // 2
        info = f"✔ 找到　分數 {r.score:.3f}　位置 ({cx}, {cy})"
        fg = C["accent"]
        # 上傳的範本原本沒有 pos → 用這次測到的位置補上, 供相對座標當備援原點
        if app.template_pos(template_name) is None:
            meta = app._load_meta()
            meta["pos"][template_name] = [cx, cy]
            app._save_meta(meta)
            app.log_ui(f"已記錄「{template_name}」位置 ({cx}, {cy})，可作相對座標原點", "ok")
    elif box is not None:
        info = f"✘ 未達門檻　分數 {r.score:.3f}（紅框為最接近的候選）"
        fg = C["danger"]
    else:
        info = f"✘ 沒有任何候選　分數 {r.score:.3f}"
        fg = C["danger"]
    # 兩階段各自的分數與門檻 (coarse-only 時沒有驗證分數)
    d = r.debug
    stages = f"　粗篩 {d.get('match_score', 0):.3f}/{cfg['match_threshold']}"
    if "verify_score" in d:
        stages += f"　驗證 {d['verify_score']:.3f}/{cfg['verify_threshold']}"
    elif app.hub.coarse_only:
        stages += "（coarse-only：驗證未啟用）"
    scope = f"　搜尋範圍：{tuple(scan)}" if scan else "　搜尋範圍：全螢幕"
    tk.Label(win_, text=info + stages + scope, bg=C["panel"], fg=fg,
             font=FONT).pack(padx=12, pady=(12, 6))

    h, w = annotated.shape[:2]
    scale = min(1.0, 1240.0 / w, 700.0 / h)
    if scale < 1.0:
        annotated = cv2.resize(annotated, (int(w * scale), int(h * scale)))
    rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
    ppm = f"P6 {rgb.shape[1]} {rgb.shape[0]} 255 ".encode() + rgb.tobytes()
    photo = tk.PhotoImage(master=win_, data=ppm)
    lbl = tk.Label(win_, image=photo, bg=C["panel"])
    lbl._photo = photo
    lbl.pack(padx=12, pady=(0, 12))

    win_.bind("<Escape>", lambda e: win_.destroy())
    _center(win_, root)
    # 從編輯對話框開啟時自然疊在它上面; 關閉後 grab 由堆疊交回下一層
    make_modal(win_)
    win_.focus_force()
