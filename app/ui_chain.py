import os
import tkinter as tk
from tkinter import messagebox, ttk

import apppaths
import flowfile
import ui_dialogs
import ui_theme
from ui_theme import C

TITLE = "串接編輯"
ADD_TITLE = "加入流程"
NO_PROGRAM = "未設目標程式"
UNREADABLE = "讀不到流程"
NOT_IN_STORE = "流程不在存放區"
RUN_MAX = 99999
COLUMNS = (("flow", "流程", 200), ("run", "輪數", 60), ("warn", "提示", 200))


def flow_warning(root, name):
    folder = os.path.join(root, name)
    if not os.path.isfile(os.path.join(folder, flowfile.FLOW_YAML)):
        return NOT_IN_STORE
    try:
        flow = flowfile.read_flow(folder)
    except flowfile.FlowError:
        return UNREADABLE
    return None if flow.get("program") else NO_PROGRAM


def _warn_text(warning):
    return f"⚠ {warning}" if warning else ""


def _tree(parent, columns, height):
    tree = ttk.Treeview(parent, columns=[c for c, _h, _w in columns], show="headings",
                        selectmode="browse", height=height)
    for col, head, width in columns:
        tree.heading(col, text=head, anchor="w")
        tree.column(col, width=width, anchor="w", stretch=col != "run")
    tree.tag_configure("warn", foreground=C["warn"])
    bar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=bar.set)
    return tree, bar


def edit_chains(app, initial=None):
    """開串接編輯對話框 (modal, 關掉才回來); initial: 一開始選中的串接名."""
    _ChainEditor(app, initial).run()


class _ChainEditor:
    def __init__(self, app, initial):
        self.app = app
        self.root = apppaths.flows_root()
        self.warnings = {}
        self.name = None
        self.items, self.saved = [], []
        self.problem = None
        self._syncing = False
        self._build()
        chains = flowfile.list_chains(self.root)
        self._load(initial if initial in chains else (chains[0] if chains else None))

    def _build(self):
        dlg = self.dlg = tk.Toplevel(self.app.root)
        dlg.title(TITLE)
        dlg.configure(bg=C["panel"])
        dlg.transient(self.app.root)

        top = ttk.Frame(dlg, style="Panel.TFrame", padding=(16, 14, 16, 8))
        top.pack(fill="x")
        ttk.Label(top, text="串接檔", style="Panel.TLabel").pack(side="left")
        self.combo = ttk.Combobox(top, state="readonly", width=24)
        self.combo.pack(side="left", padx=(8, 8))
        self.combo.bind("<<ComboboxSelected>>", lambda e: self._on_choose())
        self.btn_new = self._small(top, "新增…", self.new_chain)
        self.btn_rename = self._small(top, "改名…", self.rename_chain)
        self.btn_delete = self._small(top, "刪除", self.delete_chain)
        ui_dialogs.info_tip(top, "串接檔放在流程存放區，把多份流程依序串起來執行。這裡的 ⚠ 只是提醒，"
                                 "照樣能存檔；按「執行串接」時才會擋下有問題的串接。編輯串接不會改到流程").pack(
            side="left", padx=(8, 0))

        mid = ttk.Frame(dlg, style="Panel.TFrame", padding=(16, 0, 16, 8))
        mid.pack(fill="both", expand=True)
        self.tree, bar = _tree(mid, COLUMNS, 10)
        self.tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._sync_run())
        ops = ttk.Frame(mid, style="Panel.TFrame", padding=(10, 0, 0, 0))
        ops.pack(side="left", fill="y")
        self.btn_add = self._small(ops, "加入…", self.add_flow, side="top")
        self.btn_remove = self._small(ops, "移除", self.remove, side="top")
        self.btn_up = self._small(ops, "上移", lambda: self.move(-1), side="top")
        self.btn_down = self._small(ops, "下移", lambda: self.move(1), side="top")
        ttk.Label(ops, text="輪數", style="Panel.TLabel").pack(side="top", anchor="w",
                                                             pady=(12, 0))
        self.run_var = tk.StringVar(value="")
        self.run_box = ttk.Spinbox(ops, from_=1, to=RUN_MAX, width=6,
                                   textvariable=self.run_var)
        self.run_box.pack(side="top", anchor="w")
        self.run_var.trace_add("write", lambda *_a: self._on_run())

        foot = ttk.Frame(dlg, style="Panel.TFrame", padding=(16, 0, 16, 14))
        foot.pack(fill="x")
        self.msg = ttk.Label(foot, style="Panel.TLabel", foreground=C["danger"])
        self.msg.pack(side="left")
        ttk.Button(foot, text="關閉", command=self.close).pack(side="right", padx=(8, 0))
        self.btn_save = ttk.Button(foot, text="存檔", style="Run.TButton", command=self.save)
        self.btn_save.pack(side="right")
        self.dirty_lbl = ttk.Label(foot, style="Panel.TLabel", foreground=C["warn"])
        self.dirty_lbl.pack(side="right", padx=(0, 8))
        dlg.protocol("WM_DELETE_WINDOW", self.close)
        dlg.bind("<Escape>", lambda e: self.close())

    @staticmethod
    def _small(parent, text, cmd, side="left"):
        b = ttk.Button(parent, text=text, style="Small.TButton", takefocus=False, command=cmd)
        if side == "top":
            b.pack(side="top", fill="x", pady=(0, 4))
        else:
            b.pack(side="left", padx=(0, 4))
        return b

    def run(self):
        ui_dialogs._center(self.dlg, self.app.root)
        ui_theme.disable_transitions(self.dlg)
        ui_dialogs.make_modal(self.dlg)
        self.dlg.focus_force()
        self.app.root.wait_window(self.dlg)

    @property
    def dirty(self):
        return self.items != self.saved

    def _warning(self, flow):
        if flow not in self.warnings:
            self.warnings[flow] = flow_warning(self.root, flow)
        return self.warnings[flow]

    def _load(self, name):
        self.name, self.problem = name, None
        self.items = []
        if name is not None:
            try:
                self.items = flowfile.read_chain(self.root, name)
            except flowfile.FlowError as e:
                self.problem = str(e)
        self.saved = [dict(i) for i in self.items]
        self._render(select=0 if self.items else None)

    def _render(self, select=None):
        chains = flowfile.list_chains(self.root)
        self.combo.configure(values=chains)
        self.combo.set(self.name or "")
        t = self.tree
        t.delete(*t.get_children())
        for item in self.items:
            warning = self._warning(item["flow"])
            t.insert("", "end", values=(item["flow"], item["run"], _warn_text(warning)),
                     tags=("warn",) if warning else ())
        rows = t.get_children()
        if select is not None and rows:
            node = rows[max(0, min(select, len(rows) - 1))]
            t.selection_set(node)
            t.see(node)
        self._sync_run()
        self._refresh_state()

    def _selected(self):
        sel = self.tree.selection()
        return self.tree.index(sel[0]) if sel else None

    def _refresh_state(self):
        have = self.name is not None
        editable = have and self.problem is None
        i = self._selected()

        def enable(widget, on):
            widget.configure(state="normal" if on else "disabled")
        enable(self.btn_rename, have)
        enable(self.btn_delete, have)
        enable(self.btn_add, editable)
        enable(self.btn_remove, editable and i is not None)
        enable(self.btn_up, editable and i is not None and i > 0)
        enable(self.btn_down, editable and i is not None and i < len(self.items) - 1)
        enable(self.run_box, editable and i is not None)
        enable(self.btn_save, editable and self.dirty)
        self.dirty_lbl.configure(text="＊未存檔" if editable and self.dirty else "")
        if self.problem:
            self.msg.configure(text=f"讀不進來：{self.problem}")
        elif not have:
            self.msg.configure(text="還沒有串接檔，按「新增…」建立", foreground=C["muted"])
            return
        self.msg.configure(foreground=C["danger"])

    def _sync_run(self):
        i = self._selected()
        self._syncing = True
        try:
            self.run_var.set("" if i is None else str(self.items[i]["run"]))
        finally:
            self._syncing = False
        self.msg.configure(text="")
        self._refresh_state()

    def _on_run(self):
        if self._syncing:
            return
        i = self._selected()
        if i is None:
            return
        text = self.run_var.get().strip()
        if not (text.isdigit() and 1 <= int(text) <= RUN_MAX):
            self.msg.configure(text=f"輪數要是 1–{RUN_MAX} 的整數")
            return
        self.msg.configure(text="")
        self.items[i]["run"] = int(text)
        node = self.tree.get_children()[i]
        self.tree.set(node, "run", int(text))
        self._refresh_state()

    def add_flow(self):
        flow = _pick_flow(self.app.root, self.root, self._warning)
        if flow is None:
            return
        i = self._selected()
        at = len(self.items) if i is None else i + 1
        self.items.insert(at, {"flow": flow, "run": 1})
        self._render(select=at)

    def remove(self):
        i = self._selected()
        if i is None:
            return
        del self.items[i]
        self._render(select=i)

    def move(self, d):
        i = self._selected()
        if i is None or not 0 <= i + d < len(self.items):
            return
        self.items[i], self.items[i + d] = self.items[i + d], self.items[i]
        self._render(select=i + d)

    def save(self):
        if self.name is None or self.problem is not None:
            return True
        try:
            flowfile.write_chain(self.root, self.name, self.items)
        except (OSError, flowfile.FlowError) as e:
            messagebox.showwarning("存檔失敗", f"串接「{self.name}」存不進去：{e}",
                                   parent=self.dlg)
            return False
        self.saved = [dict(i) for i in self.items]
        self.app.log_ui(f"已存串接「{self.name}」（{len(self.items)} 份流程）", "ok")
        self._refresh_state()
        return True

    def confirm_discard(self, title):
        if self.name is None or self.problem is not None or not self.dirty:
            return True
        answer = messagebox.askyesnocancel(
            title, f"串接「{self.name}」有還沒存檔的改動，要先存檔嗎？\n\n"
            "是＝存檔　否＝不存（改動會消失）　取消＝回去繼續編輯", parent=self.dlg)
        if answer is None:
            return False
        return self.save() if answer else True

    def _on_choose(self):
        new = self.combo.get()
        if new == self.name:
            return
        if not self.confirm_discard("切換串接"):
            self.combo.set(self.name or "")
            return
        self._load(new)

    def _ask_name(self, title, initial="", renaming=None):
        name = ui_dialogs.ask_string(self.app.root, title, "串接名：", initial)
        if name is None:
            return None
        problem = flowfile.chain_name_problem(self.root, name, renaming=renaming)
        if problem:
            messagebox.showwarning(title, problem, parent=self.dlg)
            return None
        return name

    def new_chain(self):
        name = self._ask_name("新增串接")
        if name is None or not self.confirm_discard("新增串接"):
            return
        try:
            flowfile.create_chain(self.root, name)
        except (OSError, flowfile.FlowError) as e:
            messagebox.showwarning("新增串接", str(e), parent=self.dlg)
            return
        self._load(name)

    def rename_chain(self):
        if self.name is None:
            return
        name = self._ask_name("串接改名", self.name, renaming=self.name)
        if name is None or name == self.name:
            return
        try:
            flowfile.rename_chain(self.root, self.name, name)
        except (OSError, flowfile.FlowError) as e:
            messagebox.showwarning("串接改名", str(e), parent=self.dlg)
            return
        self.name = name
        self._render(select=self._selected())

    def delete_chain(self):
        if self.name is None:
            return
        if not messagebox.askyesno(
                "刪除串接", f"刪除串接「{self.name}」？\n\n只刪串接檔，裡面的流程不受影響。",
                parent=self.dlg):
            return
        try:
            flowfile.delete_chain(self.root, self.name)
        except OSError as e:
            messagebox.showwarning("刪除串接", f"刪不掉：{e}", parent=self.dlg)
            return
        chains = flowfile.list_chains(self.root)
        self._load(chains[0] if chains else None)

    def close(self):
        if self.confirm_discard("關閉串接編輯"):
            self.dlg.destroy()


def _pick_flow(parent, root, warning_of):
    dlg = tk.Toplevel(parent)
    dlg.title(ADD_TITLE)
    dlg.configure(bg=C["panel"])
    dlg.transient(parent)
    result = [None]
    names = {}  # 列 → 流程資料夾名稱 (Treeview 的 values 會把「007」讀回成數字)

    body = ttk.Frame(dlg, style="Panel.TFrame", padding=16)
    body.pack(fill="both", expand=True)
    tree, bar = _tree(body, (COLUMNS[0], COLUMNS[2]), 12)
    tree.pack(side="left", fill="both", expand=True)
    bar.pack(side="left", fill="y")
    for folder in flowfile.list_flow_folders(root):
        name = os.path.basename(folder)
        warning = warning_of(name)
        iid = tree.insert("", "end", values=(name, _warn_text(warning)),
                          tags=("warn",) if warning else ())
        names[iid] = name

    def on_ok(_e=None):
        sel = tree.selection()
        if not sel:
            err.configure(text="請先選一份流程")
            return
        result[0] = names[sel[0]]
        dlg.destroy()

    foot = ttk.Frame(dlg, style="Panel.TFrame", padding=(16, 0, 16, 14))
    foot.pack(fill="x")
    err = ttk.Label(foot, style="Panel.TLabel", foreground=C["danger"])
    err.pack(side="left")
    if not tree.get_children():
        err.configure(text="流程存放區裡還沒有流程", foreground=C["muted"])
    ttk.Button(foot, text="取消", command=dlg.destroy).pack(side="right", padx=(8, 0))
    ttk.Button(foot, text="確定", style="Run.TButton", command=on_ok).pack(side="right")
    tree.bind("<Double-Button-1>", on_ok)
    dlg.bind("<Escape>", lambda e: dlg.destroy())

    ui_dialogs._center(dlg, parent)
    ui_theme.disable_transitions(dlg)
    ui_dialogs.make_modal(dlg)
    dlg.focus_force()
    parent.wait_window(dlg)
    return result[0]
