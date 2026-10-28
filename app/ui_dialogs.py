import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import calibration
import ui_grab
import ui_overlay
import ui_theme
from automation import capture, findtarget, flowdefaults, flowfmt, pickcheck, win
from automation.runner import (BUSY_CHECK_KEY, confirm_next_connected, origin_source,
                               sends_input, uses_confirm_next, uses_origin_leaves)
from ui_theme import C, FONT, FONT_BOLD

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
    ui_grab.register_modal(dlg)

    def on_press(e):
        # grab 生效時, 點在其他視窗的事件會轉送到本視窗, 座標會落在視窗範圍外
        if (e.x_root < dlg.winfo_rootx()
                or e.x_root >= dlg.winfo_rootx() + dlg.winfo_width()
                or e.y_root < dlg.winfo_rooty()
                or e.y_root >= dlg.winfo_rooty() + dlg.winfo_height()):
            _flash(dlg)

    dlg.bind("<ButtonPress>", on_press, add=True)


def busy_foot(app, dlg, foot, closers=()):
    lbl = ttk.Label(foot, style="Panel.TLabel", foreground=C["warn"])
    lbl.pack(side="left", padx=(0, 8))
    app.recognition.register_window(dlg, lbl, closers)
    return lbl


def unless_busy(app, dlg, fn):
    def handler(_e=None):
        if not app.recognition.holds(dlg):
            fn()
    return handler


THUMB_W, THUMB_H = 176, 120


def _thumb_photo(master, img, bw=THUMB_W, bh=THUMB_H):
    if img is None:
        data = f"P6 {bw} {bh} 255 ".encode() + bytes((15, 23, 42)) * (bw * bh)
        return tk.PhotoImage(master=master, data=data)
    import cv2
    import numpy as np
    bg = np.zeros((bh, bw, 3), np.uint8)
    bg[:] = (42, 23, 15)
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


TIP_WRAP = 320


def info_tip(parent, text, bg=None):
    lbl = tk.Label(parent, text="ⓘ", bg=bg or C["panel"], fg=C["muted"],
                   cursor="question_arrow", font=(FONT[0], 10))
    tip = []

    def show(e):
        hide()
        t = tk.Toplevel(lbl)
        t.withdraw()
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        tk.Label(t, text=text, bg=C["tip"], fg=C["text"], font=FONT, justify="left",
                 wraplength=TIP_WRAP, padx=8, pady=6, highlightthickness=1,
                 highlightbackground=C["border"]).pack()
        t.update_idletasks()
        x1, y1, x2, y2 = win.monitor_work_area(lbl.winfo_id())
        w, h = t.winfo_reqwidth(), t.winfo_reqheight()
        if e.x_root or e.y_root:
            x, y = e.x_root + 12, e.y_root + 12
        else:
            x = lbl.winfo_rootx() + lbl.winfo_width()
            y = lbl.winfo_rooty() + lbl.winfo_height()
        x = max(x1, min(x, x2 - w))
        y = max(y1, min(y, y2 - h))
        t.geometry(f"+{x}+{y}")
        t.deiconify()
        tip.append(t)

    def hide(_e=None):
        while tip:
            t = tip.pop()
            try:
                t.destroy()
            except tk.TclError:
                pass

    lbl.bind("<Enter>", show)
    lbl.bind("<Leave>", hide)
    lbl.bind("<ButtonPress>", hide)
    lbl.winfo_toplevel().bind("<Unmap>", hide, add=True)
    return lbl


def ask_string(root, title, prompt, initialvalue=""):
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
    root = app.root
    names = app.list_template_names()
    title = "設定備用校準對" if fallback else "設定校準對"
    if len(names) < 2:
        messagebox.showinfo(title,
                            "至少需要兩個範本才能作為比例尺，"
                            "請先在範本面板「截圖新增」建立範本", parent=root)
        return None

    dlg = tk.Toplevel(root)
    dlg.title(title)
    dlg.configure(bg=C["panel"])
    dlg.resizable(False, False)
    dlg.transient(root)

    if fallback:
        tip = ("校準對被彈窗擋住時改用的兩張「任何畫面都看得到」的圖（例：標題列圖示與關閉鈕）。"
               "按確定時校準對與備用對都要在畫面上，才量得出備用對對座標基準點的偏移")
    elif app.flow_cal:
        tip = ("執行開頭一定同時出現、在遊戲畫面內相距夠遠的兩張固定圖。已有校準對：先用原本"
               "那一對量目前的倍率，再換算新那一對的基準距離（流程尺度不變）")
    else:
        tip = ("執行開頭一定同時出現、在遊戲畫面內相距夠遠的兩張固定圖（標題列圖示＋關閉鈕"
               "量到的倍率偏小，留給備用校準對）。目前的畫面大小就是這份流程的尺度")
    body = ttk.Frame(dlg, style="Panel.TFrame", padding=16)
    body.pack(fill="both", expand=True)
    rows = _Rows(body)
    vars_ = []
    for label, tip_ in (("範本一", tip), ("範本二", None)):
        var = tk.StringVar()
        ttk.Combobox(rows.add(label, tip_).frame, textvariable=var, values=names,
                     width=28, state="readonly").pack(side="left")
        vars_.append(var)

    result = [None]
    foot = ttk.Frame(dlg, style="Panel.TFrame", padding=(16, 0, 16, 14))
    foot.pack(fill="x")
    err = ttk.Label(foot, style="Panel.TLabel", foreground=C["danger"])

    def on_ok():
        a, b = vars_[0].get(), vars_[1].get()
        if not a or not b:
            err.configure(text="請選滿兩個範本")
            return
        if a == b:
            err.configure(text="兩個範本不能相同")
            return
        result[0] = (a, b)
        dlg.destroy()

    ttk.Button(foot, text="取消", command=dlg.destroy).pack(side="right",
                                                           padx=(8, 0))
    ttk.Button(foot, text="確定並量測", style="Run.TButton",
               command=on_ok).pack(side="right")
    err.pack(side="left")
    dlg.bind("<Return>", lambda e: on_ok())
    dlg.bind("<Escape>", lambda e: dlg.destroy())

    _center(dlg, root)
    make_modal(dlg)
    dlg.focus_force()
    root.wait_window(dlg)
    return result[0]


CUR_FLOW_LABEL = "本流程"
NEW_LABEL = "新加入（按確定才複製進本流程）"

TREE_THUMB = 32


class _Source:
    copies = True

    def __init__(self, key, label):
        self.key = key
        self.label = label

    def names(self):
        raise NotImplementedError

    def blob(self, name):
        raise NotImplementedError

    def pos(self, name):
        return None

    def check(self, name):
        return None


class _Staged(_Source):
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
    copies = False

    def __init__(self, app):
        super().__init__(CUR_FLOW_LABEL, CUR_FLOW_LABEL)
        self._app = app

    def names(self):
        return self._app.list_template_names()

    def blob(self, name):
        return self._app.template_bytes(name)


class _OtherFlow(_Source):
    def __init__(self, folder):
        super().__init__(folder, os.path.basename(folder))
        self._folder = folder

    def names(self):
        import flowfile
        return flowfile.folder_template_names(self._folder)

    def blob(self, name):
        import flowfile
        return flowfile.folder_template_bytes(self._folder, name)


def _tmpl_sources(app, pending):
    sources = []
    if pending:
        sources.append(_Staged(pending))
    sources.append(_CurrentFlow(app))
    sources += [_OtherFlow(folder) for folder in app.other_flow_folders()]
    return sources


def pick_template(app, title="選擇範本", initial=None):
    import flowfile
    from automation import imgio

    root = app.root
    dlg = tk.Toplevel(root)
    dlg.title(title)
    dlg.configure(bg=C["panel"])
    dlg.transient(root)

    pending = {}
    sources = {}
    entries = {}
    loaded = set()
    thumbs = {}       # 保住 PhotoImage 參照 (Tk 不持有, 被回收就變空白)
    result = [None]

    body = ttk.Frame(dlg, style="Panel.TFrame", padding=16)
    body.pack(fill="both", expand=True)
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
        key = (src.key, name)
        if key not in thumbs:
            thumbs[key] = _thumb_photo(dlg, imgio.imdecode(src.blob(name)),
                                       bw=TREE_THUMB, bh=TREE_THUMB)
        return thumbs[key]

    def fill(node, src):
        tree.delete(*tree.get_children(node))
        loaded.add(node)
        for name in src.names():
            child = tree.insert(node, "end", text=" " + name,
                                image=thumb_image(src, name))
            entries[child] = (src, name)

    def render(select=None):
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
            tree.focus(target)
            tree.see(target)
        show()

    def on_open(_e=None):
        node = tree.focus()
        if node in sources and node not in loaded:
            fill(node, sources[node])

    def selected():
        node = tree.focus()
        if node not in entries:
            picked = tree.selection()
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
            img = imgio.imread(p)
            if img is None:
                continue
            _stage(os.path.splitext(os.path.basename(p))[0],
                   imgio.encode_png(img))

    def shoot():
        def done(r, m):
            _stage(app.next_template_name(taken=pending),
                   imgio.encode_png(imgio.to_flow_scale(r["img"], m.k)),
                   pos=template_pos_from_shot(r, m.anchor, m.k),
                   check=m)
        app.pick_region_measured(done, hide=(dlg,), parent=dlg)

    tools = ttk.Frame(body, style="Panel.TFrame")
    tools.grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))
    shoot_btn = ttk.Button(tools, text="截圖新增", style="Accent.TButton", command=shoot)
    shoot_btn.pack(side="left")
    app.recognition.register(shoot_btn)
    ttk.Button(tools, text="從磁碟挑圖…", style="Small.TButton",
               command=from_disk).pack(side="left", padx=(6, 0))
    info_tip(tools, "從本流程或流程存放區底下的其他流程挑一張；也可以從磁碟挑圖或"
                    "現場截圖。按「確定」才把選中的圖複製進本流程，取消什麼都不留").pack(
        side="left", padx=(8, 0))
    foot = ttk.Frame(dlg, style="Panel.TFrame", padding=(16, 0, 16, 14))
    err = ttk.Label(foot, style="Panel.TLabel", foreground=C["danger"])
    tree.bind("<<TreeviewSelect>>", lambda e: err.configure(text=""), add=True)

    def on_ok():
        sel = selected()
        if sel is None:
            err.configure(text="請先選一張範本")
            return
        src, name = sel
        if not src.copies:
            result[0] = name
            dlg.destroy()
            return
        blob = src.blob(name)
        if blob is None:
            err.configure(text=f"讀不到「{name}」的圖")
            return
        final = app.add_template_image(name, blob, pos=src.pos(name))
        if final != name:
            app.log_ui(f"範本「{name}」與本流程已有的同名，"
                       f"已自動改名為「{final}」", "warn")
        app.refresh_templates()
        app.log_ui(f"已把範本「{final}」加入本流程"
                   "；建議按「立即比對測試」確認畫面上找得到", "ok")
        result[0] = final
        dlg.destroy()
        chk = src.check(name)
        if chk is not None:
            app.check_template_scale(final, chk)

    foot.pack(fill="x")
    cancel = ttk.Button(foot, text="取消", command=dlg.destroy)
    cancel.pack(side="right", padx=(8, 0))
    ok = ttk.Button(foot, text="確定", style="Run.TButton", command=on_ok)
    ok.pack(side="right")
    busy_foot(app, dlg, foot, (ok, cancel))
    err.pack(side="left")
    dlg.bind("<Escape>", unless_busy(app, dlg, dlg.destroy))

    render(select=(CUR_FLOW_LABEL, initial) if initial else None)
    _center(dlg, root)
    ui_theme.disable_transitions(dlg)
    make_modal(dlg)
    dlg.focus_force()
    root.wait_window(dlg)
    return result[0]


def _unscale(v, k):
    return flowfmt.scale_px(v, 1.0 / k)


def template_pos_from_shot(r, anchor, k):
    if anchor is None:
        return None
    center = (r["screenX"] + r["w"] // 2, r["screenY"] + r["h"] // 2)
    return list(flowfmt.from_screen(center, anchor, k))


NO_PAIR_MSG = ("這份流程還沒有校準對，就沒有座標基準點可以當基準。\n"
               "請先在主視窗「流程設定…」設定校準對")


def out_of_range_warning(scale):
    return (f"{calibration.out_of_range_text(scale)}"
            "（用這個大小執行會被擋，拾取的範本與座標不可靠）")


class Measured:
    def __init__(self, frame, shot=None):
        self.frame, self.shot = frame, shot
        self.c = None
        self.anchor, self.k = None, 1.0
        self.base = None
        self.problem = None
        self.extra = None
        self.job = None

    @property
    def failed(self):
        return self.problem is not None or (self.c is not None and not self.c.ok)


class _Pending:
    def __init__(self, job):
        self.job = job

    def status(self):
        done, m, err = self.job.peek()
        if not done:
            return "pending"
        return "failed" if err is not None or m.failed else "ready"

    @property
    def mark(self):
        _done, m, _err = self.job.peek()
        return m.base if m is not None else None


def _measure(app, cal, names, frame, shot, resolve, extra):
    m = Measured(frame, shot)
    if cal is not None:
        m.problem = app.load_problem(names)
        if m.problem is not None:
            return m
        screen, org = frame
        m.c = calibration.calibrate(app.detector.query, screen, org, cal)
        if not m.c.ok:
            return m
        m.anchor, m.k = m.c.anchor, m.c.scale
    if resolve is not None:
        m.base = resolve(frame, m.anchor, m.k)
    if extra is not None:
        m.extra = extra(m)
    return m


def measured_pick(app, parent, title, done, overlay=None, need_anchor=False, hide=(),
                  quiet=False, origin=None, extra=None, cleared=None):
    if app.recognition.busy:
        if quiet:
            app.log_ui(f"{title}略過：上一件辨識還沒做完", "warn")
        return None
    cal = app.flow_cal
    names = []
    if cal is None:
        if need_anchor:
            messagebox.showwarning(title, NO_PAIR_MSG, parent=parent)
            return None
    else:
        names = app.calibration_names()
        if quiet:
            if not app.templates_known(names):
                return None
        elif not app.calibration_ready(title, parent=parent):
            return None
    if app.hub.ready:
        app.ensure_registered()
    resolve = origin() if origin is not None else None
    job = None
    try:
        with ui_overlay.screen_clear(app.root, extra=hide):
            if quiet:
                shot, frame = None, app.grab_frame()
            else:
                shot = app.grab_shot()
                frame = app.scan_frame(shot)
            job = app.recognition.start(
                title, lambda: _measure(app, cal, names, frame, shot, resolve, extra),
                origin=parent)
            if cleared is not None:
                cleared()
            r = overlay(shot, _Pending(job)) if overlay is not None else True
    except BaseException:
        if job is not None:
            job.cancel()
        raise
    if r is None:
        job.cancel()
        return None

    def finish(m):
        m.job = job
        if m.failed:
            if m.problem is not None:
                why = f"校準圖載入失敗：{m.problem[0]}（{m.problem[1]}）"
            else:
                why = m.c.describe()
            if quiet:
                app.log_ui(f"{title}略過：{why}", "warn")
            elif m.problem is not None:
                messagebox.showwarning(title, why, parent=parent)
            else:
                messagebox.showwarning(
                    title, f"拾取當下{why}。\n這次沒有存下任何座標；"
                    "請重新框選搜尋範圍（要框住校準對兩張圖，例如遊戲視窗的標題列）後再試",
                    parent=parent)
            return
        c = m.c
        if c is not None and c.used == "fallback":
            app.log_ui(f"{title}：主校準對找不到（缺「{'」「'.join(c.main.missing)}」），"
                       "改用備用校準對量座標基準點與倍率", "warn")
        if c is not None and not c.in_range:
            app.log_ui(f"{title}：{out_of_range_warning(c.scale)}", "warn")
        if _not_picked(r):
            return
        done(r, m)
    return job.then(finish)


def _not_picked(r):
    return r is None or r is ui_overlay.ABORT or r is ui_overlay.NO_MARK


def _tagged(r, tag):
    return r if _not_picked(r) else (tag, r)


def overlay_pick(root, mode, hint, hide, shot, pending, late=None, **kw):
    status = pending.status() if pending is not None else "ready"
    if status == "failed":
        return ui_overlay.ABORT
    if status == "pending":
        return ui_overlay.pick(root, mode, hint, hide=hide, shot=shot, pending=pending,
                               late=late, **kw)
    mark = pending.mark if late is not None else None
    if late == "origin":
        if mark is not None:
            return {"screenX": mark[0], "screenY": mark[1], "auto": True}
    elif late is not None:
        if mark is None:
            return ui_overlay.NO_MARK
        kw["base" if late == "base" else "mark"] = mark
    return ui_overlay.pick(root, mode, hint, hide=hide, shot=shot, **kw)


def _click_origin(root, shot, pending, hide,
                  hint="推算不出原點：先點一下原點（前一個原點步驟的位置）"):
    p = overlay_pick(root, "point", hint, hide, shot, pending)
    return p if _not_picked(p) else (p["screenX"], p["screenY"])


def _pick_around_origin(root, mode, hint, hide, shot, pending, late,
                        click_hint="推算不出原點：先點一下原點（前一個原點步驟的位置）"):
    if late:
        r = overlay_pick(root, mode, hint, hide, shot, pending, late="mark")
        if r is not ui_overlay.NO_MARK:
            return _tagged(r, None)
    base = _click_origin(root, shot, pending, hide, click_hint)
    if _not_picked(base):
        return base
    return _tagged(overlay_pick(root, mode, hint, hide, shot, pending, mark=base), base)


NO_ORIGIN_MSG = ("推算不出原點，這次沒存；再拾取一次"
                 "（等 ◎ 出現，沒有 ◎ 會先請你點原點）")


def _late_base(app, parent, title, clicked, r, m):
    if clicked is not None:
        return clicked
    base = m.base
    if base is None:
        messagebox.showwarning(title, NO_ORIGIN_MSG, parent=parent)
        return None
    if r.get("early"):
        app.log_ui(f"{title}：原點 ◎ 在 ({base[0]}, {base[1]})"
                   "（點的時候 ◎ 還沒出現，請核對）", "info")
    return base


def _template_screen_pos(app, name, anchor, k):
    pos = app.template_pos(name)
    if pos is None or anchor is None:
        return None
    return flowfmt.to_screen(pos, anchor, k)


def _find_template_now(app, frame, prev, origin=None, k=1.0, anchor=None):
    return _find_target_now(app, frame, findtarget.target(prev), origin, k, anchor)


def _find_target_now(app, frame, tgt, origin=None, k=1.0, anchor=None):
    name = tgt.get("template", "")
    if frame is None or not app.hub.ready or name not in app.library.templates:
        return None
    try:
        app.hub.ensure_template(name)
    except Exception:
        return None
    screen, org = frame
    f = findtarget.find(tgt, app.detector, screen, org, origin=origin, scale=k,
                        anchor=anchor)
    return f.picked.center if f.picked is not None else None


def _resolve_prev_origin(app, step, frame, k=1.0, anchor=None, steps=None):
    steps = app.steps if steps is None else steps
    idx = step.get("_index", 0)
    dx = dy = 0
    via_rel = False
    i = min(idx, len(steps)) - 1
    while i >= 0:
        prev = steps[i]
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
                before = (_resolve_prev_origin(app, {"_index": i}, frame, k, anchor, steps)
                          if findtarget.needs_origin(findtarget.target(prev))
                          else None)
                pos = (_find_template_now(app, frame, prev, before, k, anchor)
                       or _template_screen_pos(app, name, anchor, k))
            if pos:
                return pos[0] + off[0] + dx, pos[1] + off[1] + dy
            return None
        i -= 1
    return None


LIMIT_ZH = {"none": "不限定", "rect": "固定矩形"}
PICK_ZH = {"score": "分數最高", "top": "由上到下第 N 個",
           "left": "由左到右第 N 個", "near": "最接近指定點"}


def pick_check_now(app, tgt, hide=(), origin_fn=None,
                   kinds=(pickcheck.SCALE, pickcheck.UNIQUE), cleared=None):
    name = tgt.get("template", "")
    if not app.templates_known([name]):
        return False

    def extra(m):
        problem = app.load_problem([name])
        if problem is not None:
            return problem, []
        screen, org = m.frame
        return None, pickcheck.check(app.detector, screen, org, tgt, m.anchor, m.k,
                                     origin=m.base, kinds=kinds)

    def done(_r, m):
        problem, warns = m.extra
        if problem is not None:
            app.log_ui(f"拾取檢查略過：範本「{name}」載入失敗（{problem[1]}）", "warn")
            return
        app.note_pick_warnings(name, warns)

    origin = origin_fn if origin_fn is not None and findtarget.needs_origin(tgt) else None
    return measured_pick(app, app.root, "拾取檢查", done, hide=hide, quiet=True,
                         origin=origin, extra=extra, cleared=cleared) is not None


TIP = {
    "tmpl": "要找的圖。「選擇…」可從其他流程、磁碟挑圖或現場截圖",
    "within": "固定矩形＝只在這一塊找（相對座標基準點，視窗挪位置不用重框）。"
              "框要比範本每邊多 20%；會捲動的清單沿捲動方向拉長",
    "pick": "畫面上有好幾個時挑哪一個（中心高度差不到半個框高算同一列）。數不到第 N 個＝"
            "還沒找到，繼續等到逾時。指定點＝原點加偏移，沒有原點的步驟無法執行",
    "color": "形狀相同、只差顏色時用（可按的橘色 vs 停用的灰色）。範本要框乾淨，"
             "不能含會變的數字或透出的背景",
    "act": "找到之後點它、只等它出現，或等它消失",
    "offset": "點在找到的圖片中心加這個偏移",
    "cfm": "送出後沒生效（輸入被吃掉）就再送，直到成立或逾時。下一步的圖＝緊接的找圖步驟"
           "要找的圖；原點的圖離開＝產生原點的找圖挑中的位置不再有匹配",
    "cfm_tmpl": "送出成功後才會出現的圖（例：結算畫面、下一關按鈕）。"
                "「設定…」＝它的限定範圍、挑選規則、比色",
    "busy": "送出後等忙碌指示消失再往下；會讓遊戲忙的操作才勾",
    "origin": "後面的相對座標步驟以這一步的位置為原點",
    "timeout": "最多等幾秒、每隔幾秒看一次；到了照「找不到時」處置",
    "nf": "跳出目前區段＝跳到所在重複／分岔的結尾之後（重複放棄剩下的次數）；"
          "不在區段內＝停止",
    "pos": "相對原點（前一個點擊、拖曳終點或找圖的位置）。勾「預設原點」時拾取會標出原點，"
           "點一下目標即可；不勾則拖一條線：起點＝原點、終點＝目標",
    "drag_pos": "起點、終點都相對原點。勾「預設原點」時拾取會標出原點，直接拖出路徑；"
                "不勾則先點一下原點再拖",
    "duration": "從起點拖到終點花的時間",
    "hold": "到終點後按住多久才放開；捲動類介面直接放開會慣性滾過頭，0.5 秒左右；0＝直接放開",
    "wait": "什麼都不做，等這麼久",
    "repeat": "「重複開始」到「重複結束」之間的步驟跑幾次；區段可以巢狀",
    "brk": "內層「找不到 → 跳出目前區段」跳到這裡時，要不要再往外跳一層"
           "（例：重複裡的分岔找不到，直接跳出整個重複）",
}


class _Row:
    def __init__(self, widgets, frame):
        self.widgets = widgets
        self.frame = frame

    def show(self, on):
        for w in self.widgets:
            w.grid() if on else w.grid_remove()


class _Rows:
    def __init__(self, parent, start=0):
        self.parent = parent
        self.i = start

    def add(self, label, tip=None):
        head = ttk.Frame(self.parent, style="Panel.TFrame")
        ttk.Label(head, text=label, style="Muted.TLabel").pack(side="left")
        if tip:
            info_tip(head, tip).pack(side="left", padx=(2, 0))
        head.grid(row=self.i, column=0, sticky="nw", pady=3, padx=(0, 10))
        fr = ttk.Frame(self.parent, style="Panel.TFrame")
        fr.grid(row=self.i, column=1, sticky="w", pady=3)
        self.i += 1
        return _Row((head, fr), fr)


def _combo(parent, var, table, width):
    shown = tk.StringVar(value=table[var.get()])
    cb = ttk.Combobox(parent, textvariable=shown, values=list(table.values()),
                      width=width, state="readonly")
    key_of = {v: k for k, v in table.items()}
    cb.bind("<<ComboboxSelected>>", lambda e: var.set(key_of[shown.get()]), add=True)
    return cb


def _text(parent, text):
    w = ttk.Label(parent, text=text, style="Muted.TLabel")
    w.pack(side="left", padx=(0, 4))
    return w


def _num(parent, var, lo, hi, inc, width=5):
    w = ttk.Spinbox(parent, textvariable=var, from_=lo, to=hi, increment=inc, width=width)
    w.pack(side="left", padx=(0, 4))
    return w


def _entry(parent, var, width=5):
    w = ttk.Entry(parent, textvariable=var, width=width)
    w.pack(side="left", padx=(0, 6))
    return w


def _xy(parent, x, y, prefix):
    _text(parent, prefix + "X")
    _entry(parent, x)
    _text(parent, "Y")
    _entry(parent, y)


def _template_size(app, name):
    img = app.template_image(name) if name else None
    return (img.shape[1], img.shape[0]) if img is not None else None


class _TargetFields:
    def __init__(self, app, dlg, rows, tgt, template_fn, origin_fn, on_change):
        self.app, self.dlg = app, dlg
        self.template_fn, self.origin_fn, self.on_change = template_fn, origin_fn, on_change
        lim = tgt.get("within")
        self.rect = list(lim) if lim is not None else None
        self.limit = tk.StringVar(value="rect" if lim is not None else "none")
        kind, value = findtarget.pick_rule(tgt)
        self.pick = tk.StringVar(value=kind)
        self.n = tk.IntVar(value=int(value) if kind in ("top", "left") else 1)
        near = value if kind == "near" else (0, 0)
        self.nx, self.ny = tk.IntVar(value=int(near[0])), tk.IntVar(value=int(near[1]))
        self.color = tk.BooleanVar(value=bool(tgt.get("color")))
        self.has_pair = app.flow_cal is not None

        fr = rows.add("限定範圍", TIP["within"]).frame
        top = ttk.Frame(fr, style="Panel.TFrame")
        top.pack(side="top", anchor="w")
        _combo(top, self.limit, LIMIT_ZH, 8).pack(side="left", padx=(0, 6))
        self.rect_btn = ttk.Button(top, text="框選", style="Small.TButton",
                                   command=self.pick_rect)
        self.rect_btn.pack(side="left")
        app.recognition.register(self.rect_btn)
        self.rect_lbl = ttk.Label(fr, style="Muted.TLabel")

        fr = rows.add("挑選規則", TIP["pick"]).frame
        line = ttk.Frame(fr, style="Panel.TFrame")
        line.pack(side="top", anchor="w")
        _combo(line, self.pick, PICK_ZH, 15).pack(side="left", padx=(0, 6))
        self.n_fr = ttk.Frame(line, style="Panel.TFrame")
        _text(self.n_fr, "第")
        _num(self.n_fr, self.n, 1, 99, 1, width=3)
        _text(self.n_fr, "個")
        self.near_fr = ttk.Frame(fr, style="Panel.TFrame")
        _xy(self.near_fr, self.nx, self.ny, "原點＋")
        pt = ttk.Button(self.near_fr, text="點選", style="Small.TButton",
                        command=self.pick_point)
        pt.pack(side="left")
        app.recognition.register(pt)

        fr = rows.add("比色", TIP["color"]).frame
        _check(fr, "顏色不符就不算找到", self.color).pack(side="left")
        for var in (self.limit, self.pick):
            var.trace_add("write", lambda *_: self.on_change())
        self.sync()

    def sync(self, show_all=False):
        fixed = self.limit.get() == "rect"
        self.app.recognition.want(self.rect_btn, fixed and self.has_pair)
        self.rect_lbl.configure(text=findtarget.limit_text(self.rect) if self.rect
                                else "（還沒框選）")
        pk = self.pick.get()
        for w, on, how in ((self.rect_lbl, fixed, dict(side="top", anchor="w", pady=(2, 0))),
                           (self.n_fr, pk in ("top", "left"), dict(side="left")),
                           (self.near_fr, pk == "near",
                            dict(side="top", anchor="w", pady=(2, 0)))):
            if on or show_all:
                if not w.winfo_manager():
                    w.pack(**how)
            elif w.winfo_manager():
                w.pack_forget()

    def warnings(self):
        if self.limit.get() != "rect":
            return []
        if not self.has_pair:
            return ["要先在「流程設定…」設定校準對才能框選固定矩形"]
        if self.rect is None:
            return ["還沒框選固定矩形"]
        name = self.template_fn()
        return [w.text for w in pickcheck.rect_margin(
            findtarget.make_target(name, within=self.rect), _template_size(self.app, name))]

    def pick_rect(self):
        app, dlg = self.app, self.dlg

        def overlay(shot, pending):
            return overlay_pick(app.root, "region",
                                 "框出只在這一塊找圖的範圍（存成相對座標基準點的位置）",
                                 (dlg,), shot, pending)

        def done(r, m):
            self.rect = findtarget.fixed_rect_from_screen(
                (r["screenX"], r["screenY"], r["w"], r["h"]), m.anchor, m.k)
            self.on_change()

        measured_pick(app, dlg, "固定矩形", done, overlay=overlay, need_anchor=True,
                      hide=(dlg,))

    def pick_point(self):
        app, dlg = self.app, self.dlg
        hint = "點一下指定點（畫面上有好幾個時挑最接近它的）"

        def overlay(shot, pending):
            return _pick_around_origin(app.root, "point", hint, (dlg,), shot, pending,
                                       late=self.origin_fn is not None)

        def done(got, m):
            clicked, r = got
            base = _late_base(app, dlg, "指定點", clicked, r, m)
            if base is None:
                return
            x, y = findtarget.offset_from_screen((r["screenX"], r["screenY"]), base, m.k)
            self.nx.set(x)
            self.ny.set(y)

        measured_pick(app, dlg, "指定點", done, overlay=overlay, hide=(dlg,),
                      origin=self.origin_fn)

    def current(self):
        limit = None
        if self.limit.get() == "rect":
            if self.rect is None:
                raise ValueError("固定矩形還沒框選：按「框選」拖一個框，或改選不限定")
            limit = list(self.rect)
        pk = self.pick.get()
        pick_ = None
        try:
            if pk in ("top", "left"):
                n = int(self.n.get())
                if n < 1:
                    raise ValueError("第 N 個的 N 要從 1 起算")
                pick_ = {pk: n}
            elif pk == "near":
                pick_ = {"near": [int(self.nx.get()), int(self.ny.get())]}
        except tk.TclError:
            raise ValueError("挑選規則的數值要填整數") from None
        return {"within": limit, "pick": pick_, "color": bool(self.color.get())}


def edit_target_opts(app, parent, tgt, title, origin_fn=None, test_fn=None):
    root = app.root
    sub = tk.Toplevel(root)
    sub.title(title)
    sub.configure(bg=C["panel"])
    sub.resizable(False, False)
    sub.transient(parent)
    foot = ttk.Frame(sub, style="Panel.TFrame", padding=(16, 0, 16, 14))
    foot.pack(side="bottom", fill="x")
    err = ttk.Label(foot, style="Panel.TLabel", foreground=C["danger"])
    body = ttk.Frame(sub, style="Panel.TFrame", padding=16)
    body.pack(side="top", fill="both", expand=True)
    rows = _Rows(body)
    warn = ttk.Label(body, style="Panel.TLabel", foreground=C["warn"])

    def changed():
        fields.sync()
        ws = fields.warnings()
        warn.configure(text="　".join(f"⚠ {w}" for w in ws))
        warn.grid() if ws else warn.grid_remove()
        err.configure(text="")

    fields = _TargetFields(app, sub, rows, tgt, lambda: tgt.get("template", ""),
                           origin_fn, changed)
    warn.grid(row=rows.i, column=0, columnspan=2, sticky="w", pady=(6, 0))
    changed()
    result = [None]

    def checked():
        try:
            return fields.current()
        except ValueError as e:
            err.configure(text=str(e))
            return None

    def on_test():
        opts = checked()
        if opts is not None and test_fn is not None:
            test_fn(opts, sub)

    def on_ok():
        opts = checked()
        if opts is not None:
            result[0] = opts
            if not pick_check_now(app, findtarget.make_target(tgt.get("template", ""), **opts),
                                  hide=(sub,), origin_fn=origin_fn, cleared=sub.destroy):
                sub.destroy()

    if test_fn is not None:
        test_btn = ttk.Button(foot, text="以這組設定比對測試", style="Accent.TButton",
                              command=on_test)
        test_btn.pack(side="left", padx=(0, 8))
        app.recognition.register(test_btn)
    err.pack(side="left")
    cancel = ttk.Button(foot, text="取消", command=sub.destroy)
    cancel.pack(side="right", padx=(8, 0))
    ok = ttk.Button(foot, text="確定", style="Run.TButton", command=on_ok)
    ok.pack(side="right")
    busy_foot(app, sub, foot, (ok, cancel))
    sub.bind("<Return>", unless_busy(app, sub, on_ok))
    sub.bind("<Escape>", unless_busy(app, sub, sub.destroy))

    _center(sub, parent)
    ui_theme.disable_transitions(sub)
    make_modal(sub)
    sub.focus_force()
    root.wait_window(sub)
    return result[0]


CARD_W = (436, 460)
CARD_GAP = 12
PV_W, PV_H = 230, 100
CFM_W = 18
ACT_ZH = {"find_click": "點擊該圖片", "find": "不點擊（僅等待出現）",
          "wait_gone": "不點擊（等待消失）"}
CFM_ZH = {"none": "不確認（點一次）", "gone": "點到目標圖消失為止",
          "appear": "點到確認圖出現為止", "next": "點到下一步的圖出現"}
BRK_ZH = {"continue": "繼續往下執行", "break": "再往外跳出一層區段"}


class _StepEditor:
    def __init__(self, app, step):
        self.app, self.step = app, step
        self.t = step["type"]
        self.v = {}
        self.syncs = []
        self.optional = []
        self.fields = None
        self.cols = None
        self.result = None
        self.added = []
        root = app.root
        d = self.dlg = tk.Toplevel(root)
        d.title(("編輯：" if step.get("_edit") else "新增：") + STEP_TITLES[self.t])
        d.configure(bg=C["panel"])
        d.resizable(False, False)
        d.transient(root)
        foot = ttk.Frame(d, style="Panel.TFrame", padding=(16, 0, 16, 14))
        foot.pack(side="bottom", fill="x")    # 先 pack: 內容再長也擠不掉確定鈕
        cancel = ttk.Button(foot, text="取消", command=d.destroy)
        cancel.pack(side="right", padx=(8, 0))
        ok = ttk.Button(foot, text="確定", style="Run.TButton", command=self.ok)
        ok.pack(side="right")
        busy_foot(app, d, foot, (ok, cancel))
        self.err = ttk.Label(foot, style="Panel.TLabel", foreground=C["danger"])
        self.err.pack(side="left")
        body = ttk.Frame(d, style="Panel.TFrame", padding=(16, 14, 16, 6))
        body.pack(side="top", fill="both", expand=True)
        if self.t in findtarget.FIND_TYPES:
            self._build_find(body)
        elif self.t in findtarget.POINTER_TYPES:
            self._build_pointer(body)
        else:
            self._build_simple(body)
        self.warn = ttk.Label(body, style="Panel.TLabel", foreground=C["warn"])
        for var in self.v.values():
            if isinstance(var, tk.Variable):
                var.trace_add("write", lambda *_: self.sync())
        d.bind("<Return>", unless_busy(app, d, self.ok))
        d.bind("<Escape>", unless_busy(app, d, d.destroy))

    def _cards(self, body, left_title, right_title):
        cols = self.cols = ttk.Frame(body, style="Panel.TFrame")
        cols.pack(side="top", fill="x")
        cards = []
        for col, title in enumerate((left_title, right_title)):
            card = tk.Frame(cols, bg=C["panel"], highlightthickness=1,
                            highlightbackground=C["border"], padx=12, pady=8)
            card.grid(row=0, column=col, sticky="nsew",
                      padx=(0, CARD_GAP) if col == 0 else 0)
            ttk.Label(card, text=title, style="Panel.TLabel", font=FONT_BOLD).grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
            cards.append(card)
        return cards

    def _optional(self, row, pred):
        self.optional.append(row)
        self.syncs.append(lambda: row.show(pred()))

    def _confirm_image_row(self, rows, origin_fn=None, test=False):
        app, v = self.app, self.v
        v["confirm_template"] = tk.StringVar(value=findtarget.confirm_template(self.step))
        self.cfm_opts = {"within": None, "pick": None, "color": False}
        ct = findtarget.confirm_target(self.step)
        self.cfm_opts.update(within=ct.get("within"), pick=ct.get("pick"),
                             color=bool(ct.get("color")))
        row = rows.add("確認圖", TIP["cfm_tmpl"])
        line = ttk.Frame(row.frame, style="Panel.TFrame")
        line.pack(side="top", anchor="w")
        self.cfm_cb = ttk.Combobox(line, textvariable=v["confirm_template"],
                                   values=app.list_template_names(), width=CFM_W,
                                   state="readonly")
        self.cfm_cb.pack(side="left", padx=(0, 4))
        ttk.Button(line, text="選擇…", style="Small.TButton",
                   command=self.choose_cfm).pack(side="left", padx=(0, 4))

        def set_opts():
            name = v["confirm_template"].get()
            if not name:
                self.err.configure(text="請先選確認圖")
                return

            def test_fn(o, parent):
                show_match_test(app, findtarget.make_target(name, **o), hide=(self.dlg,),
                                origin_fn=origin_fn)

            got = edit_target_opts(app, self.dlg,
                                   findtarget.make_target(name, **self.cfm_opts),
                                   "確認圖的找圖設定", origin_fn,
                                   test_fn if test else None)
            if got is not None:
                self.cfm_opts = got
                self.sync()

        ttk.Button(line, text="設定…", style="Small.TButton",
                   command=set_opts).pack(side="left")
        self.cfm_tags = ttk.Label(row.frame, style="Muted.TLabel")
        self.syncs.append(self._sync_cfm_tags)
        return row

    def _sync_cfm_tags(self):
        tags = findtarget.tag_text(findtarget.make_target("", **self.cfm_opts))
        self.cfm_tags.configure(text=tags)
        if tags and not self.cfm_tags.winfo_manager():
            self.cfm_tags.pack(side="top", anchor="w", pady=(2, 0))
        elif not tags and self.cfm_tags.winfo_manager():
            self.cfm_tags.pack_forget()

    def _busy_row(self, rows):
        self.v["busy_check"] = tk.BooleanVar(value=self.step.get(BUSY_CHECK_KEY, False))
        row = rows.add("忙碌檢查", TIP["busy"])
        _check(row.frame, BUSY_CHECK_TEXT, self.v["busy_check"]).pack(side="left")
        return row

    def _wait_rows(self, rows):
        v, step = self.v, self.step
        wait = dict(flowdefaults.WAIT, **{k: step[k] for k in flowdefaults.WAIT if k in step})
        v["timeout"] = tk.DoubleVar(value=wait["timeout"])
        v["interval"] = tk.DoubleVar(value=wait["interval"])
        v["on_fail"] = tk.StringVar(value=wait["on_fail"] if wait["on_fail"] in NF_ZH
                                    else "stop")
        r1 = rows.add("等待逾時", TIP["timeout"])
        _num(r1.frame, v["timeout"], 0, 3600, 1)
        _text(r1.frame, "秒，每")
        _num(r1.frame, v["interval"], 0.1, 60, 0.1, width=4)
        _text(r1.frame, "秒看一次")
        r2 = rows.add("找不到時", TIP["nf"])
        _combo(r2.frame, v["on_fail"], NF_ZH, 14).pack(side="left")
        return r1, r2

    def _build_find(self, body):
        app, v, step = self.app, self.v, self.step
        left, right = self._cards(body, "找什麼", "找到之後")
        v["template"] = tk.StringVar(value=findtarget.template(step))
        self.pv = tk.Label(left, bg=C["bg"], bd=0, highlightthickness=1,
                           highlightbackground=C["border"])
        self.pv.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.syncs.append(self._sync_preview)
        lrows = _Rows(left, 2)
        row = lrows.add("範本", TIP["tmpl"])
        self.tmpl_cb = ttk.Combobox(row.frame, textvariable=v["template"],
                                    values=app.list_template_names(), width=18,
                                    state="readonly")
        self.tmpl_cb.pack(side="left", padx=(0, 4))
        ttk.Button(row.frame, text="選擇…", style="Small.TButton",
                   command=self.choose_tmpl).pack(side="left")
        self.fields = _TargetFields(app, self.dlg, lrows, findtarget.target(step),
                                    v["template"].get, self.main_origin, self.sync)
        test_btn = ttk.Button(left, text="立即比對測試", style="Accent.TButton",
                              command=self.test_now)
        test_btn.grid(row=99, column=0, columnspan=2, sticky="w", pady=(8, 0))
        app.recognition.register(test_btn)

        rrows = _Rows(right, 1)
        v["type"] = tk.StringVar(value=self.t)
        _combo(rrows.add("動作", TIP["act"]).frame, v["type"], ACT_ZH, 18).pack(side="left")
        ox, oy = step["offset"]
        v["offset_x"], v["offset_y"] = tk.IntVar(value=ox), tk.IntVar(value=oy)
        row = rrows.add("點擊偏移", TIP["offset"])
        _xy(row.frame, v["offset_x"], v["offset_y"], "中心＋")
        clicks = lambda: v["type"].get() == "find_click"   # noqa: E731
        self._optional(row, clicks)
        v["confirm"] = tk.StringVar(value=step.get("confirm", "none"))
        row = rrows.add("生效確認", TIP["cfm"])
        _combo(row.frame, v["confirm"], CFM_ZH, 18).pack(side="left")
        self._optional(row, clicks)
        self._optional(self._confirm_image_row(rrows, self.cfm_origin, test=True),
                       lambda: clicks() and v["confirm"].get() == "appear")
        self._optional(self._busy_row(rrows), clicks)
        v["update_origin"] = tk.BooleanVar(value=step["update_origin"])
        _check(rrows.add("原點", TIP["origin"]).frame, "更新為這一步的位置",
               v["update_origin"]).pack(side="left")
        self._wait_rows(rrows)

    def _sync_preview(self):
        name = self.v["template"].get()
        ph = _thumb_photo(self.dlg, self.app.template_image(name) if name else None,
                          bw=PV_W, bh=PV_H)
        self.pv.configure(image=ph)
        self.pv._photo = ph

    def main_origin(self):
        app, step, steps = self.app, dict(self.step), list(self.app.steps)
        return lambda frame, anchor, k: _resolve_prev_origin(app, step, frame, k, anchor,
                                                             steps)

    def cfm_origin(self):
        v = self.v
        main = self.main_origin()
        if not v["update_origin"].get():
            return main
        try:
            tgt = findtarget.make_target(v["template"].get(), **self.fields.current())
        except ValueError:
            tgt = {"template": v["template"].get()}
        try:
            ox, oy = int(v["offset_x"].get()), int(v["offset_y"].get())
        except (tk.TclError, ValueError):
            ox = oy = 0
        app = self.app

        def resolve(frame, anchor, k):
            before = main(frame, anchor, k) if findtarget.needs_origin(tgt) else None
            pos = (_find_target_now(app, frame, tgt, before, k, anchor)
                   or _template_screen_pos(app, tgt["template"], anchor, k))
            if pos is None:
                return None
            return pos[0] + flowfmt.scale_px(ox, k), pos[1] + flowfmt.scale_px(oy, k)
        return resolve

    def _choose(self, var, title):
        app = self.app
        before = set(app.list_template_names())
        name = pick_template(app, title, initial=var.get() or None)
        self.added.extend(n for n in app.list_template_names() if n not in before)
        names = app.list_template_names()
        for cb in (getattr(self, "tmpl_cb", None), getattr(self, "cfm_cb", None)):
            if cb is not None:
                cb.configure(values=names)
        if name:
            var.set(name)

    def choose_tmpl(self):
        self._choose(self.v["template"], "選擇範本圖片")

    def choose_cfm(self):
        self._choose(self.v["confirm_template"], "選擇確認圖")

    def test_now(self):
        name = self.v["template"].get()
        if not name:
            self.err.configure(text="請先選擇範本圖片")
            return
        try:
            opts = self.fields.current()
        except ValueError as e:
            self.err.configure(text=str(e))
            return
        show_match_test(self.app, findtarget.make_target(name, **opts), hide=(self.dlg,),
                        origin_fn=self.main_origin)

    def _apply_find(self, s):
        v = self.v
        name = v["template"].get()
        if not name:
            raise ValueError("請選擇範本圖片")
        kind = v["type"].get()
        confirm = v["confirm"].get() if kind == "find_click" else "none"
        if confirm == "appear" and not v["confirm_template"].get():
            raise ValueError("「點到確認圖出現」需選擇確認圖")
        s[findtarget.TARGET] = findtarget.make_target(name, **self.fields.current())
        if confirm == "appear":
            s[findtarget.CONFIRM_TARGET] = findtarget.make_target(
                v["confirm_template"].get(), **self.cfm_opts)
        else:
            s.pop(findtarget.CONFIRM_TARGET, None)
        s.update(type=kind, timeout=v["timeout"].get(),
                 interval=max(0.1, v["interval"].get()),
                 offset=[v["offset_x"].get(), v["offset_y"].get()],
                 on_fail=v["on_fail"].get(), confirm=confirm,
                 update_origin=v["update_origin"].get())
        s.pop("region", None)
        s.pop("rotate", None)

    def _build_pointer(self, body):
        v, step = self.v, self.step
        left, right = self._cards(body, "位置", "送出之後")
        lrows = _Rows(left, 1)
        v["use_base"] = tk.BooleanVar(value=True)
        if self.t == "click":
            v["x"], v["y"] = (tk.IntVar(value=c) for c in step["click"])
            _xy(lrows.add("偏移", TIP["pos"]).frame, v["x"], v["y"], "原點＋")
        else:
            (x1, y1), (x2, y2) = step["drag"], step["to"]
            v["x1"], v["y1"] = tk.IntVar(value=x1), tk.IntVar(value=y1)
            v["x2"], v["y2"] = tk.IntVar(value=x2), tk.IntVar(value=y2)
            _xy(lrows.add("起點", TIP["drag_pos"]).frame, v["x1"], v["y1"], "原點＋")
            _xy(lrows.add("終點").frame, v["x2"], v["y2"], "原點＋")
        fr = lrows.add("").frame
        pick_btn = ttk.Button(fr, text="截圖拾取", style="Accent.TButton",
                              command=self.pick_pos if self.t == "click" else self.pick_drag)
        pick_btn.pack(side="left", padx=(0, 8))
        self.app.recognition.register(pick_btn)
        _check(fr, "預設原點", v["use_base"]).pack(side="left")
        if self.t == "drag":
            v["duration"] = tk.DoubleVar(value=step["duration"])
            v["hold"] = tk.DoubleVar(value=step["hold"])
            fr = lrows.add("拖曳時間", TIP["duration"]).frame
            _num(fr, v["duration"], 0.05, 10, 0.05)
            _text(fr, "秒")
            fr = lrows.add("放開前停頓", TIP["hold"]).frame
            _num(fr, v["hold"], 0, 5, 0.1)
            _text(fr, "秒")
        else:
            v["update_origin"] = tk.BooleanVar(value=step["update_origin"])
            _check(lrows.add("原點", TIP["origin"]).frame, "更新為這一步的位置",
                   v["update_origin"]).pack(side="left")

        rrows = _Rows(right, 1)
        v["confirm"] = tk.StringVar(value=step["confirm"] if step["confirm"] in POINTER_CFM_ZH
                                    else "none")
        _combo(rrows.add("生效確認", TIP["cfm"]).frame, v["confirm"], POINTER_CFM_ZH,
               18).pack(side="left")
        self._optional(self._confirm_image_row(rrows),
                       lambda: v["confirm"].get() == "appear")
        self._busy_row(rrows)
        for row in self._wait_rows(rrows):
            self._optional(row, lambda: v["confirm"].get() != "none")

    def pick_pos(self):
        app, v, dlg = self.app, self.v, self.dlg
        use_base = v["use_base"].get()

        def overlay(shot, pending):
            if use_base:
                r = overlay_pick(app.root, "line", "點一下要點擊的位置（原點＝上一步位置）",
                                  (dlg,), shot, pending, late="base")
                if r is not ui_overlay.NO_MARK:
                    return _tagged(r, "base")
            r = overlay_pick(app.root, "line",
                              "拖曳一條線：起點＝上一步點擊位置（基準），終點＝要點擊的位置",
                              (dlg,), shot, pending)
            return _tagged(r, "line")

        def done(got, m):
            how, r = got
            if how == "base" and "dx" not in r:
                base = _late_base(app, dlg, "拾取座標", None, r, m)
                if base is None:
                    return
                dx, dy = r["endX"] - base[0], r["endY"] - base[1]
            else:
                dx, dy = r["dx"], r["dy"]
            v["x"].set(_unscale(dx, m.k))
            v["y"].set(_unscale(dy, m.k))

        measured_pick(app, dlg, "拾取座標", done, overlay=overlay, hide=(dlg,),
                      origin=self.main_origin if use_base else None)

    def pick_drag(self):
        app, v, dlg = self.app, self.v, self.dlg
        use_base = v["use_base"].get()
        hint = "拖曳一條線：起點＝按下位置，終點＝放開位置"

        def overlay(shot, pending):
            return _pick_around_origin(app.root, "line", hint, (dlg,), shot, pending,
                                       late=use_base,
                                       click_hint="先點一下原點（上一步點擊位置），"
                                                  "接著再拖出拖曳路徑")

        def done(got, m):
            clicked, r = got
            base = _late_base(app, dlg, "拾取座標", clicked, r, m)
            if base is None:
                return
            x1, y1 = flowfmt.from_screen((r["startX"], r["startY"]), base, m.k)
            x2, y2 = flowfmt.from_screen((r["endX"], r["endY"]), base, m.k)
            for key, val in (("x1", x1), ("y1", y1), ("x2", x2), ("y2", y2)):
                v[key].set(val)

        measured_pick(app, dlg, "拾取座標", done, overlay=overlay, hide=(dlg,),
                      origin=self.main_origin if use_base else None)

    def _apply_pointer(self, s):
        v = self.v
        if self.t == "click":
            s.update(click=[v["x"].get(), v["y"].get()],
                     update_origin=v["update_origin"].get())
        else:
            s.update(drag=[v["x1"].get(), v["y1"].get()], to=[v["x2"].get(), v["y2"].get()],
                     duration=max(0.05, v["duration"].get()),
                     hold=max(0.0, v["hold"].get()))
        mode = v["confirm"].get()
        for k in ("confirm", findtarget.CONFIRM_TARGET, "timeout", "interval", "on_fail"):
            s.pop(k, None)
        if mode == "none":
            return
        if mode == "appear":
            if not v["confirm_template"].get():
                raise ValueError("「做到確認圖出現為止」需選擇確認圖")
            s[findtarget.CONFIRM_TARGET] = findtarget.make_target(
                v["confirm_template"].get(), **self.cfm_opts)
        s.update(confirm=mode, timeout=v["timeout"].get(),
                 interval=max(0.1, v["interval"].get()), on_fail=v["on_fail"].get())

    def _build_simple(self, body):
        v, step, t = self.v, self.step, self.t
        grid = ttk.Frame(body, style="Panel.TFrame")
        grid.pack(side="top", anchor="w")
        rows = _Rows(grid)
        if t == "wait":
            v["wait"] = tk.DoubleVar(value=step["wait"])
            fr = rows.add("等待時間", TIP["wait"]).frame
            _num(fr, v["wait"], 0.01, 3600, 0.1, width=8)
            _text(fr, "秒")
        elif t == "repeat_start":
            v["repeat"] = tk.IntVar(value=step["repeat"])
            fr = rows.add("重複次數", TIP["repeat"]).frame
            _num(fr, v["repeat"], 1, 99999, 1, width=8)
            _text(fr, "次")
        else:
            v["on_break"] = tk.StringVar(value=step["on_break"])
            _combo(rows.add("跳出到此時", TIP["brk"]).frame, v["on_break"], BRK_ZH,
                   18).pack(side="left")

    def _apply_simple(self, s):
        v, t = self.v, self.t
        if t == "wait":
            s.update(wait=max(0.01, v["wait"].get()))
        elif t == "repeat_start":
            s.update(repeat=max(1, v["repeat"].get()))
        else:
            s.update(on_break=v["on_break"].get())

    def _index(self):
        return self.step.get("_index", len(self.app.steps)), bool(self.step.get("_edit"))

    def warnings(self):
        out = list(self.fields.warnings()) if self.fields else []
        v = self.v
        kind = v["type"].get() if "type" in v else self.t
        mode = v["confirm"].get() if sends_input({"type": kind}) else "none"
        i, editing = self._index()
        steps = self.app.steps
        here = dict(self.step, type=kind, confirm=mode)
        hyp = steps[:i] + [here] + steps[i + (1 if editing else 0):]
        if uses_confirm_next(here) and not confirm_next_connected(hyp, i):
            out.append("下一步要是找圖步驟")
        if uses_origin_leaves(here) and origin_source(hyp, i) != "find":
            out.append("原點要來自找圖步驟（前面放一個找圖）")
        return out

    def sync(self, show_all=False):
        if not self.dlg.winfo_exists():
            return
        if self.fields is not None:
            self.fields.sync(show_all)
        for fn in self.syncs:
            fn()
        if show_all:
            for row in self.optional:
                row.show(True)
        ws = self.warnings() if self.cols is not None else []
        self.warn.configure(text="　".join(f"⚠ {w}" for w in ws))
        if ws and not self.warn.winfo_manager():
            self.warn.pack(side="top", anchor="w", pady=(6, 0))
        elif not ws and self.warn.winfo_manager():
            self.warn.pack_forget()
        self.err.configure(text="")

    def _fix_width(self):
        if self.cols is None:
            return
        self.sync(show_all=True)
        self.dlg.update_idletasks()
        for card in self.cols.grid_slaves(row=0):
            col = int(card.grid_info()["column"])
            need = card.winfo_reqwidth() + (CARD_GAP if col == 0 else 0)
            self.cols.grid_columnconfigure(col, minsize=max(CARD_W[col], need))
        self.sync()

    def _clamp_height(self):
        d = self.dlg
        d.update_idletasks()
        x1, y1, x2, y2 = win.monitor_work_area(self.app.root.winfo_id())
        limit = (y2 - y1) - 40
        if d.winfo_reqheight() > limit:
            d.geometry(f"{d.winfo_reqwidth()}x{limit}+{d.winfo_x()}+{y1}")

    def ok(self):
        s = dict(self.step)
        s.pop("_edit", None)
        s.pop("_index", None)
        try:
            for k in RETIRED_KEYS:
                s.pop(k, None)
            if self.t in findtarget.FIND_TYPES:
                self._apply_find(s)
            elif self.t in findtarget.POINTER_TYPES:
                self._apply_pointer(s)
            else:
                self._apply_simple(s)
            if sends_input(s) and self.v["busy_check"].get():
                s[BUSY_CHECK_KEY] = True
            else:
                s.pop(BUSY_CHECK_KEY, None)
        except (tk.TclError, ValueError) as e:
            self.err.configure(text=str(e) if isinstance(e, ValueError)
                               else "請確認數值欄位都填了數字")
            return
        keys = flowdefaults.KEYS[s["type"]]
        self.result = flowdefaults.complete({k: v_ for k, v_ in s.items() if k in keys})
        changed = findtarget.target(self.result) != findtarget.target(self.step)
        if findtarget.is_find(self.result) and (changed or not self.step.get("_edit")):
            if pick_check_now(self.app, findtarget.target(self.result), hide=(self.dlg,),
                              origin_fn=self.main_origin, cleared=self.dlg.destroy):
                return
        self.dlg.destroy()

    def run(self):
        app, d = self.app, self.dlg
        self.sync()
        self._fix_width()
        _center(d, app.root)
        self._clamp_height()
        ui_theme.disable_transitions(d)
        make_modal(d)
        d.focus_force()
        app.root.wait_window(d)
        discard_unused(app, self.added, self.result)
        return self.result


def edit_step(app, step):
    return _StepEditor(app, step).run()


BUSY_CHECK_TEXT = "送出後等忙碌指示消失"
RETIRED_KEYS = ("mode", "button", "clicks", "appearLimitMs")
POINTER_CFM_ZH = {"none": "不確認（送一次就走）",
                  "gone": "做到原點的圖離開",
                  "appear": "做到確認圖出現為止",
                  "next": "做到下一步的圖出現"}
NF_ZH = {"skip": "跳過此步驟繼續", "break": "跳出目前區段",
         "stop": "停止整個流程"}


def discard_unused(app, added, step):
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
    app.rebind_templates(changed=set())
    app.refresh_templates()
    app.log_ui("已丟棄未使用的新範本：" + "、".join(dropped), "info")


_BLUE, _GREEN, _RED, _YELLOW = (240, 128, 32), (0, 200, 60), (40, 40, 230), \
    (0, 215, 255)


def _annotate_find(screen_bgr, org, f, origin=None, anchor=None):
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
            bx, by = (f.limit[0], f.limit[1]) if f.limit else (ox, oy)
            x, y, w, h = cands[0]["box"]
            box((bx + x, by + y, w, h), _RED, 1, f"{f.query.score:.2f}")
    if origin is not None:
        cx, cy = origin[0] - ox, origin[1] - oy
        cv2.circle(img, (cx, cy), 9, _BLUE, 2)
        cv2.circle(img, (cx, cy), 3, _BLUE, -1)
    if anchor is not None:
        ax, ay = anchor[0] - ox, anchor[1] - oy
        cv2.circle(img, (ax, ay), 9, _YELLOW, 2)
        cv2.line(img, (ax - 12, ay), (ax + 12, ay), _YELLOW, 2)
        cv2.line(img, (ax, ay - 12), (ax, ay + 12), _YELLOW, 2)
    return img


_WHY = {"none": "沒有任何匹配", "count": "匹配數不到挑選規則的第 N 個",
        "origin": "以原點為基準但沒有原點", "anchor": "固定矩形但沒有座標基準點"}


def show_match_test(app, target, hide=(), origin_fn=None):
    if isinstance(target, str):
        target = {"template": target}
    template_name = target.get("template", "")
    root = app.root
    parent = ui_grab.top_window() or root
    if app.recognition.busy:
        return
    if not app.engine_gate(parent):
        return
    app.ensure_registered()
    if template_name not in app.library.templates:
        messagebox.showerror("測試", f"範本不存在: {template_name}", parent=parent)
        return
    needs = findtarget.needs_origin(target)

    def extra(m):
        problem = app.load_problem([template_name])
        if problem is not None:
            return "load", problem
        if needs and m.base is None:
            return None
        return "ok", _match(app, target, m, m.base)

    def overlay(shot, pending):
        return overlay_pick(root, "point", "推算不出原點：先點一下原點（前一個原點步驟的位置）",
                            hide, shot, pending, late="origin")

    def done(r, m):
        got = m.extra
        if (got is not None and got[0] == "load") or not needs or r.get("auto"):
            _show_match(app, target, m, got, parent)
            return
        origin = (r["screenX"], r["screenY"])
        m.job.chain(lambda: ("ok", _match(app, target, m, origin)),
                    lambda res: _show_match(app, target, m, res, parent))

    measured_pick(app, parent, "比對測試", done,
                  need_anchor=findtarget.needs_anchor(target), hide=hide,
                  overlay=overlay if needs else None,
                  origin=origin_fn if needs else None, extra=extra)


def _match(app, target, m, origin):
    screen, org = m.frame
    f = findtarget.find(target, app.detector, screen, org, origin=origin,
                        scale=m.k, anchor=m.anchor)
    annotated = _annotate_find(screen, org, f, origin, m.anchor)
    warns = pickcheck.check(app.detector, screen, org, target, m.anchor, m.k,
                            origin=origin, kinds=(pickcheck.SCALE, pickcheck.UNIQUE))
    return f, annotated, warns, origin


def _show_match(app, target, m, got, parent):
    import cv2
    kind, data = got
    if kind == "load":
        messagebox.showerror("測試", f"範本載入失敗: {data[1]}", parent=parent)
        return
    f, annotated, warns, origin = data
    root = app.root
    template_name = target.get("template", "")
    anchor, k = m.anchor, m.k
    scan = getattr(app, "scan_region", None)
    app.note_pick_warnings(template_name, warns)

    win_ = tk.Toplevel(root)
    win_.title("比對測試結果")
    win_.configure(bg=C["panel"])
    win_.transient(root)

    cfg = app.library.config
    many = f"　匹配 {len(f.matches)} 個" if f.matches else ""
    if f.picked is not None:
        cx, cy = f.picked.center
        c = "" if f.picked.color is None else f"　比色 {f.picked.color:.3f}"
        info = f"✔ 挑中 ({cx}, {cy})　分數 {f.picked.score:.3f}{c}{many}"
        fg = C["accent"]
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
    head = tk.Frame(win_, bg=C["panel"])
    head.pack(padx=12, pady=(12, 2))
    tk.Label(head, text=info + stages, bg=C["panel"], fg=fg, font=FONT).pack(side="left")
    info_tip(head, "藍框＝限定範圍　綠框＝匹配（分數 c比色）　黃粗框＝挑中、執行時會點的"
                   "　紅框＝比色不符／最接近的候選　◎＝原點　⊕＝座標基準點").pack(
        side="left", padx=(6, 0))
    tk.Label(win_, text=f"找圖設定：{findtarget.summary(target)}{scope}",
             bg=C["panel"], fg=C["muted"], font=FONT).pack(padx=12, pady=(0, 2))
    tk.Label(win_, text=("拾取檢查：" + ("通過（縮放餘裕、唯一）" if not warns else
                                     "\n".join(f"⚠ {w}" for w in warns))),
             bg=C["panel"], fg=C["accent"] if not warns else C["warn"],
             font=FONT, justify="left", wraplength=1200).pack(padx=12, pady=(0, 6))

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
    make_modal(win_)
    win_.focus_force()
