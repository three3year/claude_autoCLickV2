"""步驟編輯對話框與比對測試預覽視窗.

辨識一律走 app 的引擎接縫 (app.detector.query); 匹配門檻屬 profile config,
對話框不再有每步門檻欄位 (ADR 0002)。

座標 (ADR 0012): 存檔裡的座標都相對`座標基準點`、`流程尺度`。每次`拾取`都經
`measured_pick`: 清場後先在這次的截圖上`校準`, 得到當下的基準點與`畫面倍率`, 拾取到
的螢幕座標再換算 (flowfmt.from_screen) 後才存; 量不到＝這次不存、提示重框搜尋範圍。
"""
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import calibration
import ui_grab
import ui_overlay
import ui_theme
from automation import capture, findtarget, flowdefaults, flowfmt, pickcheck, win
from automation.runner import BUSY_CHECK_KEY, sends_input
from ui_theme import C, FONT

STEP_TITLES = {
    "click": "座標點擊",
    "find_click": "找圖點擊",
    "find": "找圖點擊",
    "wait_gone": "找圖點擊",
    "drag": "滑鼠拖曳",
    "wait": "等待",
    "repeat_start": "重複開始",
    "repeat_end": "重複結束",
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
    if img is None:
        # 純底色佔位圖不動用 cv2/numpy——啟動時就會走到這裡, 重量級
        # 套件必須留在開窗關鍵路徑之外 (ADR 0004, 票 06)
        data = f"P6 {bw} {bh} 255 ".encode() + bytes((15, 23, 42)) * (bw * bh)
        return tk.PhotoImage(master=master, data=data)
    import cv2
    import numpy as np
    bg = np.zeros((bh, bw, 3), np.uint8)
    bg[:] = (42, 23, 15)  # C["bg"] #0F172A 的 BGR
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


def pick_cal_pair(app, fallback=False):
    """選擇`校準對` (fallback＝`備用校準對`): 從本流程的範本挑兩個. 取消回傳 None.

    兩張圖必須在執行開頭的畫面上同時看得到 (作為這份流程的比例尺); 選好後由
    呼叫端立刻量一次距離 (見 App.designate_pair / designate_fallback_pair)。
    """
    root = app.root
    names = app.list_template_names()
    title = "設定備用校準對" if fallback else "設定校準對"
    if len(names) < 2:
        messagebox.showinfo(title,
                            "至少需要兩個範本才能作為比例尺，"
                            "請先用「截圖框選」建立範本", parent=root)
        return None

    dlg = tk.Toplevel(root)
    dlg.title(title)
    dlg.configure(bg=C["panel"])
    dlg.resizable(False, False)
    dlg.transient(root)

    body = ttk.Frame(dlg, style="Panel.TFrame", padding=16)
    body.pack(fill="both", expand=True)
    cur = app.flow_cal
    if fallback:
        intro = ("從本流程選兩個「任何畫面都看得到」的範本當備用校準對\n"
                 "（例：遊戲視窗標題列的圖示與關閉鈕）；主校準對被彈窗蓋住、不在主畫面時"
                 "執行會改用它。\n按確定時主對與備用對都要在畫面上，才量得出備用對對"
                 "座標基準點的偏移。")
    else:
        how = ("已有校準對：會先用原本那一對量出目前的倍率，再換算新那一對的基準距離"
               "（流程尺度不變）。" if cur else
               "這份流程還沒有校準對：目前的畫面大小就是這份流程的尺度，"
               "量到的距離就是基準距離。")
        intro = ("從本流程選兩個「執行開頭一定同時出現在畫面上」、在遊戲畫面內相距夠遠的"
                 "固定圖當比例尺\n（標題列圖示＋關閉鈕量到的倍率會偏小，留給備用校準對）；"
                 "按確定後立刻量一次。\n" + how)
    ttk.Label(body, text=intro, style="Muted.TLabel", justify="left",
              wraplength=460).pack(anchor="w", pady=(0, 10))
    vars_ = []
    for label in ("範本一", "範本二"):
        fr = ttk.Frame(body, style="Panel.TFrame")
        fr.pack(anchor="w", pady=3)
        ttk.Label(fr, text=label, style="Muted.TLabel").pack(
            side="left", padx=(0, 10))
        var = tk.StringVar()
        ttk.Combobox(fr, textvariable=var, values=names, width=28,
                     state="readonly").pack(side="left")
        vars_.append(var)

    result = [None]

    def on_ok():
        a, b = vars_[0].get(), vars_[1].get()
        if not a or not b:
            messagebox.showwarning(title, "請選滿兩個範本", parent=dlg)
            return
        if a == b:
            messagebox.showwarning(title, "兩個範本不能相同", parent=dlg)
            return
        result[0] = (a, b)
        dlg.destroy()

    foot = ttk.Frame(dlg, style="Panel.TFrame", padding=(16, 0, 16, 14))
    foot.pack(fill="x")
    ttk.Button(foot, text="取消", command=dlg.destroy).pack(side="right",
                                                           padx=(8, 0))
    ttk.Button(foot, text="確定並量測", style="Run.TButton",
               command=on_ok).pack(side="right")
    dlg.bind("<Return>", lambda e: on_ok())
    dlg.bind("<Escape>", lambda e: dlg.destroy())

    _center(dlg, root)
    make_modal(dlg)
    dlg.focus_force()
    root.wait_window(dlg)
    return result[0]


CUR_FLOW_LABEL = "本流程"
NEW_LABEL = "新加入（按確定才複製進本流程）"

TREE_THUMB = 32   # 樹狀清單每列的縮圖邊長


class _Source:
    """選範本對話框裡的一個來源: 有名字、列得出範本、取得出某一張的圖.

    三種來源 (新加入的暫存圖 / 本流程 / profile 內另一份存檔) 只在這三件事上
    不同, 其餘流程 (展開、預覽、按確定複製) 完全一樣——把差異收在這裡, 對話框
    本體就不必到處分辨「這個 source 字串是哪一種」。
    """

    #: 按確定時要不要把圖複製進本流程 (本流程自己的那張不必複製)
    copies = True

    def __init__(self, key, label):
        self.key = key
        self.label = label

    def names(self):
        raise NotImplementedError

    def blob(self, name):
        """該範本的圖檔位元組; 讀不到回 None."""
        raise NotImplementedError

    def pos(self, name):
        """拍攝位置 (截圖當下的中心, 相對`座標基準點`); 沒有就 None (跨流程複製與上傳的都沒有)."""
        return None

    def check(self, name):
        """拾取當下的 (截圖, 基準點, 倍率), 供`拾取檢查`的縮放餘裕; 沒有＝None."""
        return None


class _Staged(_Source):
    """還沒落地的新圖 (現場截圖 / 從磁碟挑的): 取消就整批丟掉."""

    def __init__(self, pending):
        super().__init__(NEW_LABEL, NEW_LABEL)
        self._pending = pending

    def names(self):
        return sorted(self._pending)

    def blob(self, name):
        item = self._pending.get(name)
        return item["blob"] if item else None

    def pos(self, name):
        item = self._pending.get(name)
        return item["pos"] if item else None

    def check(self, name):
        item = self._pending.get(name)
        return item.get("check") if item else None


class _CurrentFlow(_Source):
    """本流程已經有的範本 (工作區裡的圖): 選它不必複製."""

    copies = False

    def __init__(self, app):
        super().__init__(CUR_FLOW_LABEL, CUR_FLOW_LABEL)
        self._app = app

    def names(self):
        return self._app.list_template_names()

    def blob(self, name):
        return self._app.template_bytes(name)


class _OtherFlow(_Source):
    """profile 內另一份流程存檔: 只讀 zip 索引列名稱, 要哪張才讀哪張."""

    def __init__(self, path):
        super().__init__(path, os.path.basename(path))
        self._path = path

    def names(self):
        import flowfile
        try:
            return flowfile.template_names(self._path)
        except Exception:
            return []   # 壞掉的存檔不該讓整個對話框開不起來

    def blob(self, name):
        import flowfile
        try:
            return flowfile.template_bytes(self._path, name)
        except Exception:
            return None


def _tmpl_sources(app, pending):
    """對話框左側的所有來源 (依顯示順序)."""
    import flowfile
    sources = []
    if pending:
        sources.append(_Staged(pending))
    sources.append(_CurrentFlow(app))
    current = os.path.abspath(app.current_flow_path() or "")
    for path in flowfile.list_flows(app.profile_dir):
        if os.path.abspath(path) == current:
            continue   # 就是本流程那一份存檔, 已經以「本流程」列在上面
        sources.append(_OtherFlow(path))
    return sources


def pick_template(app, title="選擇範本", initial=None):
    """選範本對話框: 本流程、profile 內其他流程存檔、磁碟上的 PNG、現場截圖.

    **按確定的那一刻才把選中的圖複製進本流程**; 按取消時檔案系統完全沒有
    變化 (包括在對話框裡現場拍的截圖, 取消即丟棄)。撞名自動加序號並改寫
    步驟引用, 所以複製進來永遠不會蓋掉本流程已有的圖。

    左側樹狀每一列都帶縮圖, 展開某個來源時才去讀它的圖 (一次一張, 不整包
    解壓)。回傳本流程裡最終的範本名, 取消回傳 None。引擎未就緒時照樣可以
    開、可以挑圖 (挑圖不需要辨識)。
    """
    import flowfile
    from automation import imgio

    root = app.root
    dlg = tk.Toplevel(root)
    dlg.title(title)
    dlg.configure(bg=C["panel"])
    dlg.transient(root)

    pending = {}      # 尚未落地的新圖: 名稱 → {blob, pos}
    sources = {}      # 樹狀節點 id → _Source
    entries = {}      # 樹狀節點 id → (來源, 範本名)
    loaded = set()    # 已經真的把內容讀進來的來源節點 (其餘只有佔位子節點)
    thumbs = {}       # 保住 PhotoImage 參照 (Tk 不持有, 被回收就變空白)
    result = [None]

    body = ttk.Frame(dlg, style="Panel.TFrame", padding=16)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="從本流程或其他流程存檔挑一張範本；也可以從磁碟挑 PNG "
                        "或現場截圖。\n按「確定」才會把選中的圖複製進本流程。",
              style="Muted.TLabel", justify="left").grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

    tree = ttk.Treeview(body, style="Flat.Treeview", show="tree",
                        selectmode="browse", height=9)
    tree.grid(row=1, column=0, sticky="nsew")
    sb = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    sb.grid(row=1, column=1, sticky="ns")

    pv = ttk.Frame(body, style="Panel.TFrame")
    pv.grid(row=1, column=2, sticky="nsew", padx=(12, 0))
    thumb = tk.Label(pv, bg=C["bg"], bd=0, highlightthickness=1,
                     highlightbackground=C["border"])
    thumb.pack()
    info = ttk.Label(pv, text="", style="Muted.TLabel", justify="left")
    info.pack(anchor="w", pady=(6, 0))
    body.columnconfigure(0, weight=1)
    body.rowconfigure(1, weight=1)

    def thumb_image(src, name):
        """該範本的小縮圖 (樹狀列用); 讀不到就給佔位圖."""
        key = (src.key, name)
        if key not in thumbs:
            thumbs[key] = _thumb_photo(dlg, imgio.imdecode(src.blob(name)),
                                       bw=TREE_THUMB, bh=TREE_THUMB)
        return thumbs[key]

    def fill(node, src):
        """把某個來源的範本列進樹裡 (展開時才呼叫, 才不會一開就讀所有圖)."""
        tree.delete(*tree.get_children(node))   # 連佔位子節點一起換掉
        loaded.add(node)
        for name in src.names():
            child = tree.insert(node, "end", text=" " + name,
                                image=thumb_image(src, name))
            entries[child] = (src, name)

    def render(select=None):
        """重建樹; `select` 是要選回來的 (來源 key, 範本名)."""
        opened = {sources[n].key for n in tree.get_children("")
                  if tree.item(n, "open")}
        tree.delete(*tree.get_children(""))
        sources.clear()
        entries.clear()
        loaded.clear()
        target = None
        for src in _tmpl_sources(app, pending):
            node = tree.insert("", "end", text=f" {src.label}", open=False)
            sources[node] = src
            # 「本流程」與剛加入的預設展開; 其餘沿用使用者展開過的狀態
            if src.key in opened or src.key in (CUR_FLOW_LABEL, NEW_LABEL):
                tree.item(node, open=True)
                fill(node, src)
                if select:
                    for child, (s, n) in entries.items():
                        if (s.key, n) == select:
                            target = child
            else:
                # 佔位子節點: 沒有子節點就不會畫出展開箭頭, 使用者也就
                # 展不開 (真正的內容等 <<TreeviewOpen>> 才讀)
                tree.insert(node, "end", text="…")
        if target:
            tree.selection_set(target)
            tree.focus(target)     # selected() 看的是 focus, 不能只設 selection
            tree.see(target)
        show()

    def on_open(_e=None):
        """展開某個來源時才去讀它的範本 (只有佔位子節點的才需要讀)."""
        node = tree.focus()
        if node in sources and node not in loaded:
            fill(node, sources[node])

    def selected():
        node = tree.focus()
        if node not in entries:
            picked = tree.selection()   # 鍵盤/程式選取時 focus 可能還沒跟上
            node = picked[0] if picked else None
        return entries.get(node)

    def show():
        sel = selected()
        img = imgio.imdecode(sel[0].blob(sel[1])) if sel else None
        ph = _thumb_photo(dlg, img)
        thumb.configure(image=ph)
        thumb._photo = ph
        if sel:
            size = (f"{img.shape[1]}×{img.shape[0]}px" if img is not None
                    else "讀不到圖")
            info.configure(text=f"名稱：{sel[1]}\n尺寸：{size}\n"
                                f"來源：{sel[0].label}")
        else:
            info.configure(text="")

    tree.bind("<<TreeviewSelect>>", lambda e: show())
    tree.bind("<<TreeviewOpen>>", on_open)

    def _stage(name, blob, pos=None, check=None):
        """把一張新圖暫存起來 (還沒落地); 名稱在暫存區內不重複."""
        final = flowfile.free_name(flowfile.clean_name(name) or "template",
                                   pending)
        pending[final] = {"blob": blob, "pos": pos, "check": check}
        render(select=(NEW_LABEL, final))
        return final

    def from_disk():
        paths = filedialog.askopenfilenames(
            parent=dlg, title="從磁碟挑圖片",
            filetypes=[("圖片檔", "*.png *.webp *.jpg *.jpeg *.bmp *.gif "
                                 "*.tif *.tiff"), ("所有檔案", "*.*")])
        for p in paths:
            img = imgio.imread(p)   # 一律重新編碼成 PNG
            if img is None:
                continue
            _stage(os.path.splitext(os.path.basename(p))[0],
                   imgio.encode_png(img))

    def shoot():
        # 走既有的清場入口 (絕不自行 withdraw/deiconify); 截下來的圖只暫存,
        # 按取消就一起丟掉。截圖當下量基準點與倍率: 圖除以倍率換回流程尺度,
        # 拍攝位置存成相對基準點 (沒有校準對＝不記位置)
        got = app.pick_region_measured(hide=(dlg,), parent=dlg)
        if not got or got[0] is None:
            return
        r, anchor, k = got
        _stage(app.next_template_name(taken=pending),
               imgio.encode_png(imgio.to_flow_scale(r["img"], k)),
               pos=template_pos_from_shot(r, anchor, k),
               check=(r.get("frame"), anchor, k))

    tools = ttk.Frame(body, style="Panel.TFrame")
    tools.grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))
    ttk.Button(tools, text="截圖新增", style="Accent.TButton",
               command=shoot).pack(side="left")
    ttk.Button(tools, text="從磁碟挑圖…", style="Small.TButton",
               command=from_disk).pack(side="left", padx=(6, 0))

    def on_ok():
        sel = selected()
        if sel is None:
            messagebox.showwarning(title, "請先選一張範本", parent=dlg)
            return
        src, name = sel
        if not src.copies:
            result[0] = name          # 已經是本流程的範本, 不必複製
            dlg.destroy()
            return
        blob = src.blob(name)
        if blob is None:
            messagebox.showwarning(title, f"讀不到「{name}」的圖", parent=dlg)
            return
        # 確定的這一刻才複製進本流程 (獨立副本, 來源日後改圖不影響本流程)
        final = app.add_template_image(name, blob, pos=src.pos(name))
        if final != name:
            app.log_ui(f"範本「{name}」與本流程已有的同名，"
                       f"已自動改名為「{final}」", "warn")
        app.refresh_templates()
        app.log_ui(f"已把範本「{final}」加入本流程"
                   "；建議跑一次「比對測試」確認畫面上找得到", "ok")
        result[0] = final
        dlg.destroy()
        chk = src.check(name)
        if chk is not None:   # 現場截圖: 登錄完成後跑縮放餘裕 (拾取當下的整張截圖)
            app.check_template_scale(final, *chk)

    foot = ttk.Frame(dlg, style="Panel.TFrame", padding=(16, 0, 16, 14))
    foot.pack(fill="x")
    ttk.Button(foot, text="取消", command=dlg.destroy).pack(side="right",
                                                           padx=(8, 0))
    ttk.Button(foot, text="確定", style="Run.TButton",
               command=on_ok).pack(side="right")
    dlg.bind("<Escape>", lambda e: dlg.destroy())

    render(select=(CUR_FLOW_LABEL, initial) if initial else None)
    _center(dlg, root)
    ui_theme.disable_transitions(dlg)   # 截圖前隱藏對話框需立即生效
    make_modal(dlg)
    dlg.focus_force()
    root.wait_window(dlg)
    return result[0]


def _unscale(v, k):
    """拾取到的螢幕像素差反除當下的`畫面倍率`, 換回`流程尺度` (ADR 0009); 倍率 1 原值照存."""
    return flowfmt.scale_px(v, 1.0 / k)


def template_pos_from_shot(r, anchor, k):
    """截範本的拾取結果 → 拍攝位置 (截圖中心相對`座標基準點`, 流程尺度); 沒有基準點＝不記."""
    if anchor is None:
        return None
    center = (r["screenX"] + r["w"] // 2, r["screenY"] + r["h"] // 2)
    return list(flowfmt.from_screen(center, anchor, k))


NO_PAIR_MSG = ("這份流程還沒有校準對，就沒有座標基準點可以當基準。\n"
               "請先在主視窗「設定校準對」（例：遊戲視窗標題列的圖示與關閉鈕）")


def measured_pick(app, parent, body, need_anchor=False, hide=(), title="拾取",
                  quiet=False):
    """一次`拾取`的共同骨架 (ADR 0012): 清場前檢查 → 清場 → 先在這次的截圖上`校準` →
    body(anchor, k, frame) 做實際的拾取 → 清場後提示.

    回傳 (body 的結果, 座標基準點, 畫面倍率); 被擋下或量不到時回 None (已提示, 這次
    什麼都不存)。frame＝校準用的那張搜尋範圍截圖 (影像, 左上角螢幕座標), 比對測試
    直接拿它當畫面; 沒有校準對時為 None。
    - 流程沒有校準對: need_anchor 的拾取 (固定矩形) 擋下並提示先設校準對;
      只依原點的拾取照常, anchor＝None、k＝1 (新流程還沒有尺度, 當下畫面就是)。
    - 有校準對: 量不到 (範圍內找不到、兩張重疊) ＝不存、提示重框搜尋範圍。
    所有提示都在清場「之外」彈 (清場中彈 modal 會隱形卡死)。quiet＝只是檢查 (拾取檢查):
    引擎沒就緒、校準圖載不起來、量不到都不彈 modal, 寫一行紀錄區就回 None。
    """
    cal = app.flow_cal
    if cal is None:
        if need_anchor:
            messagebox.showwarning(title, NO_PAIR_MSG, parent=parent)
            return None
        with ui_overlay.screen_clear(app.root, extra=hide):
            return body(None, 1.0, None), None, 1.0
    if quiet:
        # 主對找不到時 calibrate() 會改量備用對: 備用對的範本也要先載得起來
        fb = calibration.fallback_pair(cal)
        names = [*cal["pair"], *(fb["pair"] if fb else ())]
        if not all(app.template_ready(n) for n in names):
            return None
    elif not app.calibration_ready(title, parent=parent):
        return None
    r = None
    with ui_overlay.screen_clear(app.root, extra=hide):
        c, frame = app.calibrate_frame()
        if c.ok:
            r = body(c.anchor, c.scale, frame)
    if c.ok and c.used == "fallback":
        app.log_ui(f"{title}：主校準對找不到（缺「{'」「'.join(c.main.missing)}」），"
                   "改用備用校準對量座標基準點與倍率", "warn")
    if not c.ok:
        if quiet:
            app.log_ui(f"{title}略過：{c.describe()}", "warn")
            return None
        messagebox.showwarning(
            title, f"拾取當下{c.describe()}。\n這次沒有存下任何座標；"
            "請重新框選搜尋範圍（要框住校準對兩張圖，例如遊戲視窗的標題列）後再試",
            parent=parent)
        return None
    return r, c.anchor, c.scale


def _template_screen_pos(app, name, anchor, k):
    """範本的拍攝位置換到螢幕上 (當下的基準點與倍率); 沒記位置或沒有基準點＝None."""
    pos = app.template_pos(name)
    if pos is None or anchor is None:
        return None
    return flowfmt.to_screen(pos, anchor, k)


def _find_template_now(app, dlg, prev, origin=None, k=1.0, anchor=None):
    """隱藏視窗後在搜尋範圍內即時找一次 prev 的找圖目標, 回傳挑中的中心或 None.

    origin: prev 判定時的原點 (它的找圖目標以原點為基準時才需要); k、anchor: 當下
    的`畫面倍率`與`座標基準點` (找圖目標的像素設定照它們換算, k 也是預期尺度——同執行器)。
    """
    return _find_target_now(app, dlg, findtarget.target(prev), origin, k, anchor)


def _find_target_now(app, dlg, tgt, origin=None, k=1.0, anchor=None):
    """隱藏視窗後即時執行一次`找圖目標` (與執行器同一個模組), 回傳挑中的
    匹配中心 (螢幕座標) 或 None."""
    name = tgt.get("template", "")
    if not app.hub.ready:
        # `引擎就緒`前提示並拒絕 (清場中不得彈 modal——會隱形卡死);
        # 回 None 走「截圖當下位置」備援, 拾取流程不中斷
        if not ui_grab.coord.clearing:
            app.engine_gate(parent=dlg)
        return None
    app.ensure_registered()  # 剛存的範本可能還在延後重登錄佇列中
    if name not in app.profile.templates:
        return None
    try:
        app.hub.ensure_template(name)  # 單張隨用載入 (票 05)
    except Exception:
        return None  # 載入失敗走「截圖當下位置」備援, 拾取流程不中斷
    with ui_overlay.screen_clear(app.root, extra=(dlg,)):
        screen, org = app.grab_frame()
    f = findtarget.find(tgt, app.detector, screen, org, origin=origin, scale=k,
                        anchor=anchor)
    return f.picked.center if f.picked is not None else None


def _resolve_prev_origin(app, step, dlg, k=1.0, anchor=None):
    """推算相對座標拾取的預設原點 (螢幕座標), 無法推算回傳 None.

    步驟裡存的都是流程尺度的偏移量, 換算成螢幕座標時一律乘上當下的`畫面倍率` k;
    範本拍攝位置相對當下的`座標基準點` anchor (與 runner 執行期同一套換算,
    ADR 0009、0012)。

    從本步驟往上找「有座標的動作」(跳過等待):
    - 座標點擊 → 累積偏移×k, 繼續往上找基準
    - 滑鼠拖曳 → 累積終點偏移×k, 繼續往上找
    - 找圖點擊 → 只有它就是「直接前一個原點步驟」(途中沒經過相對步驟)
      才在畫面上即時找一次 (找不到退用拍攝位置, 依當下基準點換到螢幕); 途中隔了
      相對點擊/拖曳時, 畫面通常已被那次點擊切換, 即時找到的殘留同圖不可信,
      一律用拍攝位置重現使用者剛剛拾取的位置
    """
    idx = step.get("_index", 0)
    dx = dy = 0  # 途中經過的相對點擊累積偏移 (已乘倍率的螢幕像素)
    via_rel = False  # 途中是否經過相對步驟 (影響找圖的推算方式, 見 docstring)
    i = min(idx, len(app.steps)) - 1
    while i >= 0:
        prev = app.steps[i]
        t = prev["type"]
        if t == "click" and prev["update_origin"]:
            dx += flowfmt.scale_px(prev["click"][0], k)
            dy += flowfmt.scale_px(prev["click"][1], k)
            via_rel = True
        elif t == "drag":
            dx += flowfmt.scale_px(prev["to"][0], k)
            dy += flowfmt.scale_px(prev["to"][1], k)
            via_rel = True
        elif t in findtarget.FIND_TYPES and prev["update_origin"]:
            off = tuple(flowfmt.scale_px(v, k) for v in prev["offset"])
            name = findtarget.template(prev)
            if via_rel:
                pos = _template_screen_pos(app, name, anchor, k)
            else:
                # 前一步的找圖目標以原點為基準時, 先推算它自己的原點 (再往上找)
                before = (_resolve_prev_origin(app, {"_index": i}, dlg, k, anchor)
                          if findtarget.needs_origin(findtarget.target(prev))
                          else None)
                pos = (_find_template_now(app, dlg, prev, before, k, anchor)
                       or _template_screen_pos(app, name, anchor, k))
            if pos:
                return pos[0] + off[0] + dx, pos[1] + off[1] + dy
            return None  # 找圖位置無法推算, 中斷
        i -= 1  # 等待 / 不更新原點的找圖 → 往上繼續找
    return None


# ================= `找圖目標`的設定 (限定範圍/挑選規則/比色) =================

LIMIT_ZH = {"none": "不限定（整個搜尋範圍）", "rect": "固定矩形"}
PICK_ZH = {"score": "分數最高", "top": "由上到下第 N 個",
           "left": "由左到右第 N 個", "near": "最接近指定點"}


def _key_of(table, text):
    return {v: k for k, v in table.items()}[text]


def _target_opts(tgt):
    """找圖目標 → 表單值 (findtarget.make_target 的參數)."""
    return {"within": tgt.get("within"), "pick": tgt.get("pick"),
            "color": bool(tgt.get("color"))}


def pick_check_now(app, tgt, hide=(), origin_fn=None,
                   kinds=(pickcheck.SCALE, pickcheck.UNIQUE)):
    """找圖目標設好之後的`拾取檢查`: 清場 → 截一張當下的搜尋範圍 (有校準對就在上面量) →
    照目標的限定範圍跑唯一 (與縮放餘裕) → 警告寫紀錄區並標記範本. 回傳警告清單.

    只是檢查, 不擋確定: 引擎沒就緒、範本不在清單、校準量不到都安靜略過 (量不到寫一行)。
    origin_fn(anchor, k): 這個找圖目標判定時的預設原點 (以原點為基準的設定才需要;
    推算不出來就略過, 不請使用者點)。
    """
    name = tgt.get("template", "")
    if not app.template_ready(name):
        return []

    def body(anchor, k, frame):
        if frame is None:   # 沒有校準對: 這裡才截圖 (有的話用量校準的那張)
            frame = app.grab_frame()
        origin = None
        if origin_fn is not None and findtarget.needs_origin(tgt):
            origin = origin_fn(anchor, k)
        return frame, origin

    got = measured_pick(app, app.root, body, hide=hide, title="拾取檢查", quiet=True)
    if not got or got[0] is None:
        return []
    (frame, origin), anchor, k = got
    screen, org = frame
    warns = pickcheck.check(app.detector, screen, org, tgt, anchor, k,
                            origin=origin, kinds=kinds)
    app.note_pick_warnings(name, warns)
    return warns


def _origin_or_click(root, origin_fn, anchor, k, hide):
    """預設原點 (螢幕座標); 推算不出來就請使用者點一下原點, 取消回 None.

    必須在清場「之內」呼叫 (推算可能要即時找圖, 拾取要讓出螢幕)。
    """
    base = origin_fn(anchor, k) if origin_fn is not None else None
    if base is None:
        p = ui_overlay.pick(root, "point",
                            "推算不出原點：先點一下原點（前一個原點步驟的位置）",
                            hide=hide)
        if p:
            base = (p["screenX"], p["screenY"])
    return base


def edit_target_opts(app, parent, tgt, title, origin_fn=None, test_fn=None):
    """`找圖目標`的設定子對話框: 限定範圍、挑選規則、比色.

    找圖步驟與`確認圖`共用。回傳表單值 {"within", "pick", "color"} (交給
    `findtarget.make_target` 組回找圖目標), 取消回 None。

    origin_fn(anchor, k): 這個找圖目標判定時的預設原點 (螢幕座標) 或 None——點選
    指定點時預先標出 (◎); test_fn(表單值, 子對話框): 以這組設定比對測試 (提示以
    子對話框為 parent, 才不會被壓在它後面)。
    所有拾取都在拾取當下量`座標基準點`與`畫面倍率` (measured_pick): 指定點相對原點、
    `固定矩形`相對基準點, 一律反除倍率換回流程尺度。
    """
    root = app.root
    sub = tk.Toplevel(root)
    sub.title(title)
    sub.configure(bg=C["panel"])
    sub.resizable(False, False)
    sub.transient(parent)
    body = ttk.Frame(sub, style="Panel.TFrame", padding=16)
    body.pack(fill="both", expand=True)
    row_i = [0]

    def add_row(label):
        ttk.Label(body, text=label, style="Muted.TLabel").grid(
            row=row_i[0], column=0, sticky="nw", pady=4, padx=(0, 12))
        fr = ttk.Frame(body, style="Panel.TFrame")
        fr.grid(row=row_i[0], column=1, sticky="w", pady=4)
        row_i[0] += 1
        return fr

    def add_note(text):
        w = ttk.Label(body, text=text, style="Muted.TLabel", wraplength=430,
                      font=("Microsoft JhengHei UI", 9), justify="left")
        w.grid(row=row_i[0], column=1, sticky="w", pady=(0, 6))
        row_i[0] += 1
        return w

    def entry(parent_, var, label):
        ttk.Label(parent_, text=label, style="Muted.TLabel").pack(
            side="left", padx=(0, 4))
        ttk.Entry(parent_, textvariable=var, width=6).pack(side="left",
                                                          padx=(0, 8))

    lim = tgt.get("within")
    pick_kind, pick_value = findtarget.pick_rule(tgt)
    v_lim = tk.StringVar(value=LIMIT_ZH["rect" if lim is not None else "none"])
    # `固定矩形`: 框選結果 [x, y, w, h] (相對座標基準點); None＝還沒框過
    fixed = [list(lim) if lim is not None else None]
    v_pick = tk.StringVar(value=PICK_ZH[pick_kind])
    v_n = tk.IntVar(value=int(pick_value) if pick_kind in ("top", "left") else 1)
    near = pick_value if pick_kind == "near" else (0, 0)
    v_px = tk.IntVar(value=int(near[0]))
    v_py = tk.IntVar(value=int(near[1]))
    v_color = tk.BooleanVar(value=bool(tgt.get("color")))

    # ---- 限定範圍 ----
    fr = add_row("限定範圍")
    lim_cb = ttk.Combobox(fr, textvariable=v_lim, width=22, state="readonly",
                          values=list(LIMIT_ZH.values()))
    lim_cb.pack(side="left")
    fixed_fr = add_row("")
    has_pair = app.flow_cal is not None

    def template_size():
        """這個找圖目標的範本大小 (流程尺度 w, h); 還沒選範本＝None (矩形餘裕跳過)."""
        name = tgt.get("template", "")
        img = app.template_image(name) if name else None
        return (img.shape[1], img.shape[0]) if img is not None else None

    def show_fixed():
        fixed_lbl.configure(text=findtarget.limit_text(fixed[0]) if fixed[0]
                            else "（還沒框選）")
        # `拾取檢查`的矩形餘裕: 框完立刻對照範本大小 (只警告, 確定照存; ADR 0013)
        warns = (pickcheck.rect_margin(
            findtarget.make_target(tgt.get("template", ""), within=fixed[0]),
            template_size()) if fixed[0] else [])
        fixed_warn.configure(text="\n".join(f"⚠ {w.text}" for w in warns))
        fixed_warn.grid() if warns else fixed_warn.grid_remove()

    def pick_fixed():
        def body(anchor, k, _frame):
            return ui_overlay.pick(root, "region",
                                   "框出只在這一塊找圖的範圍（存成相對座標基準點的位置）",
                                   hide=(sub,))

        got = measured_pick(app, sub, body, need_anchor=True, hide=(sub,),
                            title="固定矩形")
        if got and got[0]:
            r, anchor, k = got
            fixed[0] = findtarget.fixed_rect_from_screen(
                (r["screenX"], r["screenY"], r["w"], r["h"]), anchor, k)
            show_fixed()

    fixed_btn = ttk.Button(fixed_fr, text="在畫面上框選", style="Accent.TButton",
                           command=pick_fixed)
    fixed_btn.pack(side="left")
    fixed_lbl = ttk.Label(fixed_fr, style="Muted.TLabel")
    fixed_lbl.pack(side="left", padx=(8, 0))
    fixed_warn = add_note("")
    fixed_warn.configure(foreground=C["warn"])
    show_fixed()
    if not has_pair:
        fixed_btn.state(["disabled"])
    fixed_note = add_note(
        "在畫面上拖一個框，存成相對座標基準點（校準對第一張圖的中心）的位置，"
        "視窗挪位置、搜尋範圍重框都不用重設；用在位置固定的圖，會捲動的清單把框"
        "沿捲動方向拉長；框要比範本每邊多 20%（餘裕不足會在上面警告，但照樣可存）"
        if has_pair else
        "要先在主視窗設定校準對才能框選（固定矩形相對座標基準點）")

    # ---- 挑選規則 ----
    fr = add_row("挑選規則")
    pick_cb = ttk.Combobox(fr, textvariable=v_pick, width=22, state="readonly",
                           values=list(PICK_ZH.values()))
    pick_cb.pack(side="left")
    n_fr = add_row("")
    ttk.Label(n_fr, text="第", style="Muted.TLabel").pack(side="left")
    ttk.Spinbox(n_fr, textvariable=v_n, from_=1, to=99, width=5).pack(
        side="left", padx=4)
    ttk.Label(n_fr, text="個（中心高度差不到半個框高視為同一列）",
              style="Muted.TLabel").pack(side="left")
    near_fr = add_row("")
    ttk.Label(near_fr, text="相對原點", style="Muted.TLabel").pack(side="left",
                                                                 padx=(0, 4))
    entry(near_fr, v_px, "X")
    entry(near_fr, v_py, "Y")

    def pick_point():
        def body(anchor, k, _frame):
            base = _origin_or_click(root, origin_fn, anchor, k, (sub,))
            if base is None:
                return None
            r = ui_overlay.pick(root, "point",
                                "點一下指定點（畫面上有好幾個時挑最接近它的）",
                                hide=(sub,), mark=base)
            return (r, base) if r else None

        got = measured_pick(app, sub, body, hide=(sub,), title="指定點")
        if got and got[0]:
            (r, base), _anchor, k = got
            x, y = findtarget.offset_from_screen((r["screenX"], r["screenY"]),
                                                 base, k)
            v_px.set(x)
            v_py.set(y)

    ttk.Button(near_fr, text="點選", style="Accent.TButton",
               command=pick_point).pack(side="left")
    pick_note = add_note("畫面上有好幾個符合時點哪一個；指定點＝原點加偏移"
                         "（偏移 0,0＝最接近原點），沒有原點的步驟無法執行。"
                         "數不到第 N 個＝還沒找到，繼續等到逾時（絕不退而點別個）")

    # ---- 比色 ----
    fr = add_row("比色")
    _check(fr, "找到後再以顏色確認，顏色不符就不算找到", v_color).pack(side="left")
    add_note("用來分開形狀相同、只差顏色的圖（可按的橘色按鈕 vs 停用的灰色按鈕）。"
             "範本要框乾淨，不能含會變的數字或透出的背景")

    def sync(*_):
        lk = _key_of(LIMIT_ZH, v_lim.get())
        for w in (fixed_fr, fixed_note):
            w.grid() if lk == "rect" else w.grid_remove()
        if lk == "rect" and fixed_warn.cget("text"):
            fixed_warn.grid()
        else:
            fixed_warn.grid_remove()
        pk = _key_of(PICK_ZH, v_pick.get())
        n_fr.grid() if pk in ("top", "left") else n_fr.grid_remove()
        near_fr.grid() if pk == "near" else near_fr.grid_remove()

    sync()
    lim_cb.bind("<<ComboboxSelected>>", sync, add=True)
    pick_cb.bind("<<ComboboxSelected>>", sync, add=True)

    result = [None]

    def current():
        """表單 → {"within", "pick", "color"}; 數值不合法丟 ValueError/TclError."""
        lk = _key_of(LIMIT_ZH, v_lim.get())
        limit = None
        if lk == "rect":
            if fixed[0] is None:
                raise ValueError("固定矩形還沒框選：請按「在畫面上框選」拖一個框")
            limit = list(fixed[0])
        pk = _key_of(PICK_ZH, v_pick.get())
        pick_ = None
        if pk in ("top", "left"):
            n = int(v_n.get())
            if n < 1:
                raise ValueError("第 N 個的 N 要從 1 起算")
            pick_ = {pk: n}
        elif pk == "near":
            pick_ = {"near": [int(v_px.get()), int(v_py.get())]}
        return {"within": limit, "pick": pick_, "color": bool(v_color.get())}

    def checked():
        try:
            return current()
        except (tk.TclError, ValueError) as e:
            msg = str(e) if isinstance(e, ValueError) else "請確認數值欄位皆已正確填寫"
            messagebox.showwarning("找圖設定", msg, parent=sub)
            return None

    def on_test():
        opts = checked()
        if opts is not None and test_fn is not None:
            test_fn(opts, sub)

    def on_ok():
        opts = checked()
        if opts is not None:
            result[0] = opts
            # 找圖目標設好了: 照它的限定範圍查唯一 (與縮放餘裕), 只警告不擋
            pick_check_now(app, findtarget.make_target(tgt.get("template", ""),
                                                       **opts),
                           hide=(sub,), origin_fn=origin_fn)
            sub.destroy()

    foot = ttk.Frame(sub, style="Panel.TFrame", padding=(16, 0, 16, 14))
    foot.pack(fill="x")
    if test_fn is not None:
        ttk.Button(foot, text="以這組設定比對測試", style="Accent.TButton",
                   command=on_test).pack(side="left")
    ttk.Button(foot, text="取消", command=sub.destroy).pack(side="right",
                                                          padx=(8, 0))
    ttk.Button(foot, text="確定", style="Run.TButton",
               command=on_ok).pack(side="right")
    sub.bind("<Return>", lambda e: on_ok())
    sub.bind("<Escape>", lambda e: sub.destroy())

    _center(sub, parent)
    ui_theme.disable_transitions(sub)   # 拾取前隱藏對話框需立即生效
    make_modal(sub)
    sub.focus_force()
    root.wait_window(sub)
    return result[0]


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

    result = [None]
    t = step["type"]
    v = {}

    def busy_row():
        """`忙碌檢查`勾選列 (ADR 0011; 送出輸入的步驟才有); 回傳整列元件供顯示/隱藏."""
        v["busy_check"] = tk.BooleanVar(value=step[BUSY_CHECK_KEY])
        fr = add_row("忙碌檢查")
        _check(fr, BUSY_CHECK_TEXT, v["busy_check"]).pack(side="left")
        lab = body.grid_slaves(row=int(fr.grid_info()["row"]), column=0)
        return (*lab, fr)

    # 這次開對話框期間新加進本流程的範本: 關閉時把「最後沒被這一步引用到的」
    # 收回去——「在找圖對話框現場截圖後按取消＝丟棄該圖」(舊的`確認圖`
    # 「截圖即時存檔、取消對話框圖仍留下」語意已經改掉)
    added = []

    if t == "click":
        cx, cy = step["click"]
        v["x"] = tk.IntVar(value=cx)
        v["y"] = tk.IntVar(value=cy)
        add_note(PREV_NOTE)

        fr = add_row("座標")
        lbl(fr, "X")
        ttk.Entry(fr, textvariable=v["x"], width=7).pack(side="left", padx=(0, 8))
        lbl(fr, "Y")
        ttk.Entry(fr, textvariable=v["y"], width=7).pack(side="left", padx=(0, 8))

        v["use_base"] = tk.BooleanVar(value=True)

        def pick_pos():
            # 整段 (量校準、找圖預查、拾取) 包進同一個 screen_clear: 視窗保持隱藏,
            # 沒有「還原→再隱藏」的空窗 (歷來卡死競態的根源)
            def body(anchor, k, _frame):
                base = (_resolve_prev_origin(app, step, dlg, k, anchor)
                        if v["use_base"].get() else None)
                if base is not None:
                    return ui_overlay.pick(root, "line", "點一下要點擊的位置（原點＝上一步位置）",
                                           hide=(dlg,), base=base)
                return ui_overlay.pick(
                    root, "line",
                    "拖曳一條線：起點＝上一步點擊位置（基準），終點＝要點擊的位置",
                    hide=(dlg,))

            # 相對座標只要倍率 (不需要座標基準點)
            got = measured_pick(app, dlg, body, hide=(dlg,), title="拾取座標")
            if not got or not got[0]:
                return
            r, _anchor, k = got
            v["x"].set(_unscale(r["dx"], k))
            v["y"].set(_unscale(r["dy"], k))

        ttk.Button(fr, text="截圖拾取", style="Accent.TButton",
                   command=pick_pos).pack(side="left")
        _check(fr, "預設原點", v["use_base"]).pack(side="left", padx=(8, 0))
        v["update_origin"] = tk.BooleanVar(value=step["update_origin"])
        fr = add_row("相對座標")
        _check(fr, "把點擊位置更新為相對座標原點", v["update_origin"]).pack(
            side="left")
        busy_row()

    elif t == "drag":
        (x1, y1), (x2, y2) = step["drag"], step["to"]
        v["x1"] = tk.IntVar(value=x1)
        v["y1"] = tk.IntVar(value=y1)
        v["x2"] = tk.IntVar(value=x2)
        v["y2"] = tk.IntVar(value=y2)
        v["duration"] = tk.DoubleVar(value=step["duration"])
        v["hold"] = tk.DoubleVar(value=step["hold"])
        add_note(DRAG_NOTE)

        fr = add_row("起點")
        lbl(fr, "X")
        ttk.Entry(fr, textvariable=v["x1"], width=7).pack(side="left", padx=(0, 8))
        lbl(fr, "Y")
        ttk.Entry(fr, textvariable=v["y1"], width=7).pack(side="left", padx=(0, 8))

        v["use_base"] = tk.BooleanVar(value=True)

        def pick_drag():
            # 整段 (量校準、預查、兩段拾取) 包進同一個 screen_clear: 視窗保持隱藏,
            # 沒有「還原→再隱藏」的空窗 (歷來卡死競態的根源)
            def body(anchor, k, _frame):
                base = (_resolve_prev_origin(app, step, dlg, k, anchor)
                        if v["use_base"].get() else None)
                if base is None:
                    p = ui_overlay.pick(
                        root, "point",
                        "先點一下原點（上一步點擊位置），接著再拖出拖曳路徑",
                        hide=(dlg,))
                    if not p:
                        return None
                    base = (p["screenX"], p["screenY"])
                r = ui_overlay.pick(root, "line",
                                    "拖曳一條線：起點＝按下位置，終點＝放開位置",
                                    hide=(dlg,), mark=base)
                return (r, base) if r else None

            got = measured_pick(app, dlg, body, hide=(dlg,), title="拾取座標")
            if not got or not got[0]:
                return
            (r, base), _anchor, k = got
            # 兩端點都相對同一個原點
            x1, y1 = flowfmt.from_screen((r["startX"], r["startY"]), base, k)
            x2, y2 = flowfmt.from_screen((r["endX"], r["endY"]), base, k)
            v["x1"].set(x1)
            v["y1"].set(y1)
            v["x2"].set(x2)
            v["y2"].set(y2)

        ttk.Button(fr, text="截圖拾取", style="Accent.TButton",
                   command=pick_drag).pack(side="left")
        _check(fr, "預設原點", v["use_base"]).pack(side="left", padx=(8, 0))

        fr = add_row("終點")
        lbl(fr, "X")
        ttk.Entry(fr, textvariable=v["x2"], width=7).pack(side="left", padx=(0, 8))
        lbl(fr, "Y")
        ttk.Entry(fr, textvariable=v["y2"], width=7).pack(side="left", padx=(0, 8))

        fr = add_row("拖曳時間")
        ttk.Spinbox(fr, textvariable=v["duration"], from_=0.05, to=10,
                    increment=0.05, width=7).pack(side="left", padx=(0, 4))
        lbl(fr, "秒")

        fr = add_row("放開前停頓")
        ttk.Spinbox(fr, textvariable=v["hold"], from_=0, to=5,
                    increment=0.1, width=7).pack(side="left", padx=(0, 4))
        lbl(fr, "秒")
        add_note("到達終點後按住停頓再放開；捲動類介面直接放開會慣性滾過頭，"
                 "建議 0.5 秒左右；0＝直接放開")
        busy_row()

    elif t == "wait":
        v["wait"] = tk.DoubleVar(value=step["wait"])
        fr = add_row("等待時間")
        ttk.Spinbox(fr, textvariable=v["wait"], from_=0.01, to=3600,
                    increment=0.1, width=10).pack(side="left", padx=(0, 4))
        lbl(fr, "秒")

    elif t == "repeat_start":
        v["repeat"] = tk.IntVar(value=step["repeat"])
        fr = add_row("重複次數")
        ttk.Spinbox(fr, textvariable=v["repeat"], from_=1, to=99999,
                    width=7).pack(side="left", padx=(0, 4))
        lbl(fr, "次")
        add_note("把要重複的步驟放在「重複開始」與「重複結束」之間"
                 "（可用 ≡ 把手拖曳排列）；區段可以巢狀")

    elif t in ("repeat_end", "branch_end"):
        BRK_ZH = {"continue": "繼續往下執行", "break": "再往外跳出一層區段"}
        seg = "重複" if t == "repeat_end" else "分岔"
        v["on_break"] = tk.StringVar(
            value=BRK_ZH[step["on_break"]])
        fr = add_row("找不到跳出到此時")
        ttk.Combobox(fr, textvariable=v["on_break"], width=20, state="readonly",
                     values=list(BRK_ZH.values())).pack(side="left")
        add_note(f"當內層步驟因「找不到 → 跳出目前區段」跳到這個{seg}結尾時的動作。"
                 "選「再往外跳出一層區段」可讓外層區段也一起跳出——"
                 "例如重複(FOR)內的分岔(IF)找不到時，直接跳出整個重複區段。"
                 "（正常執行流程到達此處不受影響）")

    elif t in findtarget.FIND_TYPES:
        v["template"] = tk.StringVar(value=findtarget.template(step))
        v["timeout"] = tk.DoubleVar(value=step["timeout"])
        v["interval"] = tk.DoubleVar(value=step["interval"])
        # `找圖三態`就是步驟的 type
        ACT_ZH = {"find_click": "點擊該圖片",
                  "find": "不點擊（僅等待出現）",
                  "wait_gone": "不點擊（等待消失）"}
        ACT_KEY = {n: k for k, n in ACT_ZH.items()}
        v["type"] = tk.StringVar(value=ACT_ZH[t])
        ox, oy = step["offset"]
        v["offset_x"] = tk.IntVar(value=ox)
        v["offset_y"] = tk.IntVar(value=oy)
        v["on_fail"] = tk.StringVar(
            value=NF_ZH[step["on_fail"]])

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

        def update_preview(*_):
            nm = v["template"].get()
            ph = _thumb_photo(dlg, app.template_image(nm) if nm else None,
                              bw=PV_W, bh=PV_H)
            pv_lbl.configure(image=ph)
            pv_lbl._photo = ph

        tmpl_cb.bind("<<ComboboxSelected>>", update_preview, add=True)
        update_preview()

        # `找圖目標`的其餘屬性 (限定範圍/挑選規則/比色): 找圖步驟與確認圖
        # 共用同一個設定子對話框, 這裡只顯示摘要
        opts = {"main": _target_opts(findtarget.target(step)),
                "cfm": _target_opts(findtarget.confirm_target(step))}
        tmpl_var = {"main": v["template"]}

        def target_of(key):
            return findtarget.make_target(tmpl_var[key].get(), **opts[key])

        def main_origin(anchor, k):
            """本步驟判定時的原點＝本步驟之前的原點 (與執行器同一套推算)."""
            return _resolve_prev_origin(app, step, dlg, k, anchor)

        def cfm_origin(anchor, k):
            """確認圖判定時的原點＝點擊後的原點: 本步驟更新原點時是點擊落點
            (即時找本步驟的找圖目標 + 偏移), 否則沿用本步驟之前的原點."""
            if not v["update_origin"].get():
                return main_origin(anchor, k)
            tgt = target_of("main")
            before = main_origin(anchor, k) if findtarget.needs_origin(tgt) else None
            pos = (_find_target_now(app, dlg, tgt, before, k, anchor)
                   or _template_screen_pos(app, tgt["template"], anchor, k))
            if pos is None:
                return None
            try:
                ox, oy = int(v["offset_x"].get()), int(v["offset_y"].get())
            except (tk.TclError, ValueError):
                ox = oy = 0
            return (pos[0] + flowfmt.scale_px(ox, k),
                    pos[1] + flowfmt.scale_px(oy, k))

        origin_of = {"main": main_origin, "cfm": cfm_origin}
        summary_lbl = {}

        def refresh_summary():
            for key, lbl_ in summary_lbl.items():
                lbl_.configure(text="　" + findtarget.summary(target_of(key)))

        def set_opts(key, title):
            def test(o, parent):
                if not tmpl_var[key].get():
                    messagebox.showwarning("測試", "請先選擇範本圖片",
                                           parent=parent)
                    return
                show_match_test(app, findtarget.make_target(
                    tmpl_var[key].get(), **o), hide=(dlg,),
                    origin_fn=origin_of[key])
            got = edit_target_opts(app, dlg, target_of(key), title,
                                   origin_of[key], test)
            if got is not None:
                opts[key] = got
                refresh_summary()

        fr = add_row("找圖設定")
        ttk.Button(fr, text="設定…", style="Small.TButton",
                   command=lambda: set_opts("main", "找圖設定")).pack(side="left")
        summary_lbl["main"] = ttk.Label(fr, style="Muted.TLabel")
        summary_lbl["main"].pack(side="left")
        add_note("限定範圍＝只在這一塊找；挑選規則＝畫面上有好幾個時點哪一個；"
                 "比色＝顏色不符就不算找到")

        def choose_tmpl():
            """選範本對話框: 跨存檔瀏覽、從磁碟挑圖、現場截圖 (確定才複製)."""
            before = set(app.list_template_names())
            name = pick_template(app, "選擇範本圖片",
                                 initial=v["template"].get() or None)
            added.extend(n for n in app.list_template_names()
                         if n not in before)
            if name:
                v["template"].set(name)
                tmpl_cb.configure(values=app.list_template_names())
                update_preview()

        # 回到範本圖片列補上按鈕 (排版在 combobox 之後)
        ttk.Button(tmpl_cb.master, text="選擇範本…", style="Accent.TButton",
                   command=choose_tmpl).pack(side="left")

        fr = add_row("等待逾時")
        ttk.Spinbox(fr, textvariable=v["timeout"], from_=0, to=3600,
                    increment=1, width=7).pack(side="left", padx=(0, 4))
        lbl(fr, "秒，每")
        ttk.Spinbox(fr, textvariable=v["interval"], from_=0.1, to=60,
                    increment=0.1, width=6).pack(side="left", padx=(0, 4))
        lbl(fr, "秒重試")

        fr = add_row("找到之後")
        act_cb = ttk.Combobox(fr, textvariable=v["type"], width=20,
                              state="readonly", values=list(ACT_ZH.values()))
        act_cb.pack(side="left")

        fr = add_row("點擊偏移")
        lbl(fr, "X")
        ttk.Entry(fr, textvariable=v["offset_x"], width=6).pack(side="left", padx=(0, 8))
        lbl(fr, "Y")
        ttk.Entry(fr, textvariable=v["offset_y"], width=6).pack(side="left")
        add_note("預設點在找到圖片的中心；偏移可點在圖片周圍的相對位置")

        # `生效確認`: 對付「圖找到也點了, 但遊戲還不接受輸入」(只有點擊時才有意義)
        CFM_ZH = {"none": "不確認（點一次）",
                  "gone": "點到目標圖消失為止",
                  "appear": "點到確認圖出現為止",
                  "next": "點到下一步的圖出現"}
        CFM_KEY = {n: k for k, n in CFM_ZH.items()}
        v["confirm"] = tk.StringVar(
            value=CFM_ZH[step.get("confirm", "none")])   # 不點擊的找圖沒有確認
        v["confirm_template"] = tk.StringVar(value=findtarget.confirm_template(step))

        # 「生效確認」整列自建 label 方便隨「不點擊」整列隱藏
        cfm_mode_lbl = ttk.Label(body, text="生效確認", style="Muted.TLabel")
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
        cfm_tmpl_cb = ttk.Combobox(cfm_row, textvariable=v["confirm_template"],
                                   values=app.list_template_names(), width=24,
                                   state="readonly")
        cfm_tmpl_cb.pack(side="left", padx=(0, 6))

        def choose_cfm_tmpl():
            # 確認圖走與主範本**同一個**選範本對話框: 現場截圖後按取消
            # 一律丟棄 (舊的「截圖即時存檔」語意已改掉)
            before = set(app.list_template_names())
            nm = pick_template(app, "選擇確認圖",
                               initial=v["confirm_template"].get() or None)
            added.extend(n for n in app.list_template_names()
                         if n not in before)
            if nm:
                cfm_tmpl_cb.configure(values=app.list_template_names())
                v["confirm_template"].set(nm)

        ttk.Button(cfm_row, text="選擇範本…", style="Accent.TButton",
                   command=choose_cfm_tmpl).pack(side="left")
        tmpl_var["cfm"] = v["confirm_template"]
        ttk.Button(cfm_row, text="設定…", style="Small.TButton",
                   command=lambda: set_opts("cfm", "確認圖的找圖設定")).pack(
            side="left", padx=(6, 0))
        cfm_tmpl_note = add_note("截「點成功後才會出現」的下一畫面圖案（如結算畫面、下一關按鈕）")
        summary_lbl["cfm"] = add_note("")
        refresh_summary()
        busy_widgets = busy_row()   # 只有點擊時才有 (隨「不點擊」整列隱藏)

        # 是否把找到 (點擊) 的位置更新為相對座標原點
        v["update_origin"] = tk.BooleanVar(value=step["update_origin"])
        fr = add_row("相對座標")
        _check(fr, "把此步驟的位置更新為相對座標原點", v["update_origin"]).pack(
            side="left")
        add_note("取消勾選＝此步驟不影響「相對上一步」的原點，"
                 "後面的相對座標步驟沿用更早的位置")

        def sync_click_opts(*_):
            # 「不點擊」時整個「生效確認」都無意義 → 隱藏; 確認圖再依 appear 決定
            is_click = ACT_KEY[v["type"].get()] == "find_click"
            for w in (cfm_mode_lbl, cfm_mode_fr, cfm_main_note, *busy_widgets):
                w.grid() if is_click else w.grid_remove()
            appear = is_click and CFM_KEY[v["confirm"].get()] == "appear"
            for w in (cfm_lbl, cfm_row, cfm_tmpl_note, summary_lbl["cfm"]):
                w.grid() if appear else w.grid_remove()

        sync_click_opts()
        act_cb.bind("<<ComboboxSelected>>", sync_click_opts, add=True)
        cfm_cb.bind("<<ComboboxSelected>>", sync_click_opts, add=True)

        fr = add_row("找不到時")
        ttk.Combobox(fr, textvariable=v["on_fail"], width=18, state="readonly",
                     values=list(NF_ZH.values())).pack(side="left")
        add_note("找不到圖、或點了確認不生效時的處置。跳出目前區段＝跳到此步驟所在的"
                 "重複/分岔區段結尾之後（重複區段放棄剩餘次數）；不在任何區段內時等同停止")

        fr = add_row("測試")

        def test_now():
            name = v["template"].get()
            if not name:
                messagebox.showwarning("測試", "請先選擇範本圖片", parent=dlg)
                return
            # 範本一定已經在本流程裡了 (選範本對話框按確定的那一刻就複製進來),
            # 所以這裡直接照找圖目標完整測一次 (限定範圍/挑選規則/比色)
            show_match_test(app, target_of("main"), hide=(dlg,),
                            origin_fn=main_origin)

        ttk.Button(fr, text="立即比對測試", style="Accent.TButton",
                   command=test_now).pack(side="left")

    # ---- 座標點擊 / 拖曳的`生效確認` (ADR 0008) ----
    pointer_confirm = None
    if t in findtarget.POINTER_TYPES:
        pointer_confirm = _pointer_confirm_block(
            app, dlg, body, step, v, added, add_row, add_note, lbl)

    # ---- 確定 / 取消 ----
    foot = ttk.Frame(dlg, style="Panel.TFrame", padding=(16, 0, 16, 14))
    foot.pack(fill="x")

    def on_ok():
        s = dict(step)
        s.pop("_edit", None)
        s.pop("_index", None)
        try:
            for k in RETIRED_KEYS:
                s.pop(k, None)
            if t == "click":
                s.update(click=[v["x"].get(), v["y"].get()],
                         update_origin=v["update_origin"].get())
                pointer_confirm(s)
            elif t == "drag":
                s.update(drag=[v["x1"].get(), v["y1"].get()],
                         to=[v["x2"].get(), v["y2"].get()],
                         duration=max(0.05, v["duration"].get()),
                         hold=max(0.0, v["hold"].get()))
                pointer_confirm(s)
            elif t == "repeat_start":
                s.update(repeat=max(1, v["repeat"].get()))
            elif t in ("repeat_end", "branch_end"):
                s.update(on_break={"繼續往下執行": "continue",
                                   "再往外跳出一層區段": "break"}[v["on_break"].get()])
            elif t == "wait":
                s.update(wait=max(0.01, v["wait"].get()))
            elif t in findtarget.FIND_TYPES:
                if not v["template"].get():
                    raise ValueError("請選擇範本圖片")
                kind = ACT_KEY[v["type"].get()]
                confirm = (CFM_KEY[v["confirm"].get()] if kind == "find_click"
                           else "none")
                if confirm == "appear" and not v["confirm_template"].get():
                    raise ValueError("「點到確認圖出現」需選擇確認圖")
                # confirm == "next" 而下一步不是找圖時不在此擋下 (拍板
                # 2026-08-16 修訂): 允許先存, 由步驟清單的 ⚠ 標記提示、
                # 執行前檢查攔下——作者常先建這步再補下一步
                s[findtarget.TARGET] = target_of("main")
                if confirm == "appear":
                    s[findtarget.CONFIRM_TARGET] = target_of("cfm")
                else:
                    s.pop(findtarget.CONFIRM_TARGET, None)
                s.update(
                    type=kind,
                    timeout=v["timeout"].get(),
                    interval=max(0.1, v["interval"].get()),
                    offset=[v["offset_x"].get(), v["offset_y"].get()],
                    on_fail={n: k for k, n in NF_ZH.items()}[v["on_fail"].get()],
                    confirm=confirm,
                    update_origin=v["update_origin"].get(),
                )
                s.pop("region", None)  # 舊版步驟範圍 (已廢除; 限定範圍在找圖目標裡)
                s.pop("rotate", None)  # 舊版執行期旋轉比對已移除
            # `忙碌檢查`: 只在勾了 (且是送出輸入的步驟) 時寫鍵; 找圖選「不點擊」
            # 「等待消失」時整列已隱藏, 存為沒勾
            if sends_input(s) and v["busy_check"].get():
                s[BUSY_CHECK_KEY] = True
            else:
                s.pop(BUSY_CHECK_KEY, None)
        except (tk.TclError, ValueError) as e:
            msg = str(e) if isinstance(e, ValueError) else "請確認數值欄位皆已正確填寫"
            messagebox.showwarning("輸入錯誤", msg, parent=dlg)
            return
        # 換了找圖三態時只留新種類用得到的欄位, 缺的照「沒寫＝」表補齊
        keys = flowdefaults.KEYS[s["type"]]
        result[0] = flowdefaults.complete({k: v_ for k, v_ in s.items() if k in keys})
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
    discard_unused(app, added, result[0])
    return result[0]


BUSY_CHECK_TEXT = "送出後等忙碌指示消失再往下（會讓遊戲忙的操作才勾）"
# 座標點擊/拖曳一律相對`原點` (絕對座標已退場, ADR 0014)
PREV_NOTE = ("以前一個點擊位置為原點的偏移量（找圖步驟選「不點擊」時，"
             "找到的位置也算）；勾選「預設原點」時截圖拾取會自動標出原點，"
             "點一下目標即完成；取消勾選則拖線：起點＝基準、終點＝目標")
DRAG_NOTE = ("起點與終點都是以前一個點擊位置為原點的偏移量（找圖步驟不點擊時"
             "找到的位置、拖曳終點也算）；勾選「預設原點」時截圖拾取會標出原點◎，"
             "直接拖出拖曳路徑即可；取消勾選則先點一下原點，再拖出拖曳路徑")
# 已退場的步驟欄位 (ADR 0014): 舊存檔帶著也照常開, 編輯後存回時拿掉
RETIRED_KEYS = ("mode", "button", "clicks", "appearLimitMs")
POINTER_CFM_ZH = {"none": "不確認（送一次就走）",
                  "gone": "做到原點的圖離開",
                  "appear": "做到確認圖出現為止",
                  "next": "做到下一步的圖出現"}
NF_ZH = {"skip": "跳過此步驟繼續", "break": "跳出目前區段",
         "stop": "停止整個流程"}


def _pointer_confirm_block(app, dlg, body, step, v, added, add_row, add_note,
                           lbl):
    """座標點擊／拖曳對話框的`生效確認`區塊; 回傳 apply(s): 把表單寫回步驟.

    方式、確認圖 (同一個選範本對話框＋找圖設定)、逾時/輪詢、`找不到時` (預設停止:
    拖曳沒生效還往下走, 後面的相對點擊會點錯列)。沒有確認時不寫任何確認欄位。
    """
    key_of = {n: k for k, n in POINTER_CFM_ZH.items()}
    v["confirm"] = tk.StringVar(value=POINTER_CFM_ZH.get(
        step["confirm"], POINTER_CFM_ZH["none"]))
    v["cfm_tmpl"] = tk.StringVar(value=findtarget.confirm_template(step))
    # 沒設確認的步驟沒有等待欄位: 顯示預設表的值 (選了確認才寫進步驟)
    wait = dict(flowdefaults.WAIT, **{k: step[k] for k in flowdefaults.WAIT if k in step})
    v["cfm_timeout"] = tk.DoubleVar(value=wait["timeout"])
    v["cfm_interval"] = tk.DoubleVar(value=wait["interval"])
    v["cfm_nf"] = tk.StringVar(value=NF_ZH.get(wait["on_fail"],
                                               NF_ZH["stop"]))
    opts = _target_opts(findtarget.confirm_target(step))

    fr = add_row("生效確認")
    cfm_cb = ttk.Combobox(fr, textvariable=v["confirm"], width=20,
                          state="readonly", values=list(POINTER_CFM_ZH.values()))
    cfm_cb.pack(side="left")
    add_note("網路慢時遊戲畫好了卻還不接受輸入, 輸入會被吃掉: 設了就檢查有沒有生效, "
             "沒生效在補做間隔後重送同一個輸入（畫面上有忙碌指示時先不送）。"
             "「原點的圖離開」看產生原點的那個找圖：它挑中的位置不再有匹配＝生效"
             "（例：找 1 列 → 拖曳捲動），原點要來自找圖；"
             "「下一步的圖出現」看緊接的找圖步驟。不成立時該列顯示 ⚠")

    rows = []

    def row(label):
        fr_ = add_row(label)
        lab = body.grid_slaves(row=int(fr_.grid_info()["row"]), column=0)
        rows.append((lab, fr_))
        return fr_

    fr = row("確認圖")
    tmpl_cb = ttk.Combobox(fr, textvariable=v["cfm_tmpl"],
                           values=app.list_template_names(), width=22,
                           state="readonly")
    tmpl_cb.pack(side="left", padx=(0, 6))

    def choose():
        before = set(app.list_template_names())
        nm = pick_template(app, "選擇確認圖",
                           initial=v["cfm_tmpl"].get() or None)
        added.extend(n for n in app.list_template_names() if n not in before)
        if nm:
            tmpl_cb.configure(values=app.list_template_names())
            v["cfm_tmpl"].set(nm)

    def set_opts():
        got = edit_target_opts(app, dlg, findtarget.make_target(
            v["cfm_tmpl"].get(), **opts), "確認圖的找圖設定")
        if got is not None:
            opts.update(got)
            summary.configure(text="　" + findtarget.summary(
                findtarget.make_target(v["cfm_tmpl"].get(), **opts)))

    ttk.Button(fr, text="選擇範本…", style="Accent.TButton",
               command=choose).pack(side="left")
    ttk.Button(fr, text="設定…", style="Small.TButton",
               command=set_opts).pack(side="left", padx=(6, 0))
    summary = ttk.Label(fr, style="Muted.TLabel", text="　" + findtarget.summary(
        findtarget.make_target(v["cfm_tmpl"].get(), **opts)))
    summary.pack(side="left")

    fr = row("確認逾時")
    ttk.Spinbox(fr, textvariable=v["cfm_timeout"], from_=0, to=3600,
                increment=1, width=7).pack(side="left", padx=(0, 4))
    lbl(fr, "秒，每")
    ttk.Spinbox(fr, textvariable=v["cfm_interval"], from_=0.1, to=60,
                increment=0.1, width=6).pack(side="left", padx=(0, 4))
    lbl(fr, "秒檢查")
    fr = row("找不到時")
    ttk.Combobox(fr, textvariable=v["cfm_nf"], width=18, state="readonly",
                 values=list(NF_ZH.values())).pack(side="left")

    def sync(*_):
        mode = key_of[v["confirm"].get()]
        for i, (lab, fr_) in enumerate(rows):
            show = mode != "none" and (i != 0 or mode == "appear")
            for w in (*lab, fr_):
                w.grid() if show else w.grid_remove()

    sync()
    cfm_cb.bind("<<ComboboxSelected>>", sync, add=True)

    def apply(s):
        mode = key_of[v["confirm"].get()]
        for k in ("confirm", findtarget.CONFIRM_TARGET, "timeout", "interval",
                  "on_fail"):
            s.pop(k, None)
        if mode == "none":
            return
        if mode == "appear":
            if not v["cfm_tmpl"].get():
                raise ValueError("「做到確認圖出現為止」需選擇確認圖")
            s[findtarget.CONFIRM_TARGET] = findtarget.make_target(
                v["cfm_tmpl"].get(), **opts)
        s.update(confirm=mode, timeout=v["cfm_timeout"].get(),
                 interval=max(0.1, v["cfm_interval"].get()),
                 on_fail={n: k for k, n in NF_ZH.items()}[v["cfm_nf"].get()])

    return apply


def discard_unused(app, added, step):
    """把這次對話框加進來、最後卻沒被用到的範本收回去.

    取消整個對話框＝這次加的圖全部丟棄; 按確定則只留這一步真的引用到的
    (中途換過幾張的那幾張同樣不留)。已被**其他步驟**或流程層級設定 (校準對)
    引用的絕不動。
    """
    if not added:
        return
    keep = set()
    if step:
        keep = {findtarget.template(step),
                findtarget.confirm_template(step)} - {None, ""}
    others = set(app.referenced_templates())
    dropped = [n for n in dict.fromkeys(added)
               if n not in keep and n not in others]
    if not dropped:
        return
    for n in dropped:
        app.drop_template(n)
    app.reload_profile()
    app.refresh_templates()
    app.log_ui("已丟棄未使用的新範本：" + "、".join(dropped), "info")


_BLUE, _GREEN, _RED, _YELLOW = (240, 128, 32), (0, 200, 60), (40, 40, 230), \
    (0, 215, 255)


def _annotate_find(screen_bgr, org, f, origin=None, anchor=None):
    """在截圖上畫出一次找圖目標判定 (螢幕座標換回截圖座標), 回傳新影像.

    藍＝限定範圍、綠＝匹配 (分數、比色分數)、紅＝比色不符的、黃粗框＝挑選規則
    挑中的那個、◎＝原點、⊕＝座標基準點。完全沒有匹配時以細紅框標出最接近的
    粗篩候選 (除錯線索)。
    """
    import cv2
    img = screen_bgr.copy()
    ox, oy = org

    def box(b, color, width, text=None):
        x, y, w, h = b[0] - ox, b[1] - oy, b[2], b[3]
        cv2.rectangle(img, (x, y), (x + w, y + h), color, width)
        if text:
            cv2.putText(img, text, (x, max(16, y - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, color, 2, cv2.LINE_AA)

    if f.limit is not None:
        box(f.limit, _BLUE, 2)
    for m in f.rejected:
        box(m.box, _RED, 2, f"c{m.color:.2f}")
    for m in f.matches:
        text = f"{m.score:.2f}" + ("" if m.color is None else f" c{m.color:.2f}")
        box(m.box, _GREEN, 2, text)
    if f.picked is not None:
        box(f.picked.box, _YELLOW, 4)
    if not f.matches and not f.rejected and f.query is not None:
        cands = f.query.debug.get("candidates") or []
        if cands:
            # 候選框是查詢影像 (限定範圍裁切後) 內的座標
            bx, by = (f.limit[0], f.limit[1]) if f.limit else (ox, oy)
            x, y, w, h = cands[0]["box"]
            box((bx + x, by + y, w, h), _RED, 1, f"{f.query.score:.2f}")
    if origin is not None:
        cx, cy = origin[0] - ox, origin[1] - oy
        cv2.circle(img, (cx, cy), 9, _BLUE, 2)
        cv2.circle(img, (cx, cy), 3, _BLUE, -1)
    if anchor is not None:
        # ⊕＝座標基準點 (固定矩形的基準)
        ax, ay = anchor[0] - ox, anchor[1] - oy
        cv2.circle(img, (ax, ay), 9, _YELLOW, 2)
        cv2.line(img, (ax - 12, ay), (ax + 12, ay), _YELLOW, 2)
        cv2.line(img, (ax, ay - 12), (ax, ay + 12), _YELLOW, 2)
    return img


_WHY = {"none": "沒有任何匹配", "count": "匹配數不到挑選規則的第 N 個",
        "origin": "以原點為基準但沒有原點", "anchor": "固定矩形但沒有座標基準點"}


def show_match_test(app, target, hide=(), origin_fn=None):
    """隱藏視窗 → 在搜尋範圍的截圖上`校準` → 照`找圖目標`完整執行一次 → 標註預覽.

    target: 找圖目標 (或範本名＝只有範本、其餘預設的找圖目標)。與執行器走
    同一個模組 (`findtarget`): 限定範圍 (固定矩形以這張截圖量到的`座標基準點`
    換算)、比色、挑選規則都照設定, 倍率同時當預期尺度, 畫面上黃粗框的那個就是
    執行時會點的。origin_fn(anchor, k): 這個找圖目標判定時的預設原點; 設定以
    原點為基準卻推算不出時, 請使用者點一下原點。找到時補記範本的拍攝位置
    (相對基準點; 沒有校準對就不記)。
    """
    import cv2
    if isinstance(target, str):
        target = {"template": target}
    template_name = target.get("template", "")
    root = app.root
    if not app.engine_gate():  # `引擎就緒`前提示並拒絕 (ADR 0004)
        return
    app.ensure_registered()  # 剛存的範本可能還在延後重登錄佇列中 (票 05)
    if template_name not in app.profile.templates:
        messagebox.showerror("測試", f"範本不存在: {template_name}")
        return
    try:
        app.hub.ensure_template(template_name)  # 單張隨用載入 (票 05)
    except Exception as e:
        messagebox.showerror("測試", f"範本載入失敗: {e}", parent=root)
        return

    scan = getattr(app, "scan_region", None)

    def body(anchor, k, frame):
        origin = None
        if findtarget.needs_origin(target):
            origin = _origin_or_click(root, origin_fn, anchor, k, hide)
            if origin is None:
                return None   # 使用者取消點選原點
        if frame is None:   # 沒有校準對: 這裡才截圖 (有的話就用量校準的那張)
            frame = app.grab_frame()
        return origin, frame

    got = measured_pick(app, root, body, need_anchor=findtarget.needs_anchor(target),
                        hide=hide, title="比對測試")
    if not got or got[0] is None:
        return
    (origin, (screen, org)), anchor, k = got
    f = findtarget.find(target, app.detector, screen, org, origin=origin,
                        scale=k, anchor=anchor)
    annotated = _annotate_find(screen, org, f, origin, anchor)
    # `拾取檢查`: 同一張截圖再跑縮放餘裕與唯一, 結果與比對測試一起顯示 (ADR 0013)
    warns = pickcheck.check(app.detector, screen, org, target, anchor, k,
                            origin=origin, kinds=(pickcheck.SCALE, pickcheck.UNIQUE))
    app.note_pick_warnings(template_name, warns)

    win_ = tk.Toplevel(root)
    win_.title("比對測試結果")
    win_.configure(bg=C["panel"])
    win_.transient(root)

    cfg = app.profile.config
    many = f"　匹配 {len(f.matches)} 個" if f.matches else ""
    if f.picked is not None:
        cx, cy = f.picked.center
        c = "" if f.picked.color is None else f"　比色 {f.picked.color:.3f}"
        info = f"✔ 挑中 ({cx}, {cy})　分數 {f.picked.score:.3f}{c}{many}"
        fg = C["accent"]
        # 上傳/複製進來的範本原本沒有拍攝位置 → 用這次測到的位置補上 (相對
        # 當下的座標基準點), 供相對座標當備援原點
        if anchor is not None and app.template_pos(template_name) is None:
            rel = flowfmt.from_screen((cx, cy), anchor, k)
            app.record_template_pos(template_name, list(rel))
            app.log_ui(f"已記錄「{template_name}」拍攝位置 ({cx}, {cy})"
                       f"（相對基準點 {rel[0]:+d},{rel[1]:+d}），可作相對座標原點", "ok")
    else:
        why = _WHY.get(f.reason, "沒有任何匹配")
        if f.reason == "none" and f.query is not None and f.query.failed == "color":
            why = "形狀符合但比色不符（紅框）"
        info = f"✘ 沒挑到：{why}{many}"
        fg = C["danger"]
    # 各關的分數與門檻 (coarse-only 時沒有驗證分數)
    stages = ""
    d = f.query.debug if f.query is not None else {}
    if f.query is not None:
        stages = f"　粗篩 {d.get('match_score', 0):.3f}/{cfg['match_threshold']}"
        if "verify_score" in d:
            stages += f"　驗證 {d['verify_score']:.3f}/{cfg['verify_threshold']}"
        elif app.hub.coarse_only:
            stages += "（coarse-only：驗證未啟用）"
        if target.get("color"):
            stages += f"　比色門檻 {cfg.get('color_threshold', 0.95)}"
    scope = f"　搜尋範圍：{tuple(scan)}" if scan else "　搜尋範圍：全螢幕"
    if anchor is not None:
        scope += f"　基準點 {tuple(anchor)}　倍率 ×{k:.3f}"
    tk.Label(win_, text=info + stages, bg=C["panel"], fg=fg,
             font=FONT).pack(padx=12, pady=(12, 2))
    tk.Label(win_, text=f"找圖設定：{findtarget.summary(target)}{scope}",
             bg=C["panel"], fg=C["muted"], font=FONT).pack(padx=12, pady=(0, 2))
    tk.Label(win_, text=("拾取檢查：" + ("通過（縮放餘裕、唯一）" if not warns else
                                     "\n".join(f"⚠ {w}" for w in warns))),
             bg=C["panel"], fg=C["accent"] if not warns else C["warn"],
             font=FONT, justify="left", wraplength=1200).pack(padx=12, pady=(0, 2))
    tk.Label(win_, text="藍框＝限定範圍　綠框＝匹配（分數 c比色）　黃粗框＝挑中、"
                        "執行時會點的　紅框＝比色不符／最接近的候選　◎＝原點　⊕＝座標基準點",
             bg=C["panel"], fg=C["muted"],
             font=("Microsoft JhengHei UI", 9)).pack(padx=12, pady=(0, 6))

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
