"""深色 ttk 主題設定."""
import ctypes
from tkinter import ttk


def safe_grab_current(w):
    """`grab_current()` 但容忍純 Tcl widget 持有 grab 的情形.

    ttk Combobox 下拉開啟時, 其 popdown 視窗會取得 grab; popdown 不在
    Python 的 widget 樹 → 標準庫 `nametowidget` 會 `KeyError: 'popdown'`.
    這種情況視為「grab 暫時被下拉選單持有」, 回傳 None (呼叫端本就處理 None).
    """
    try:
        return w.grab_current()
    except KeyError:
        return None


def disable_transitions(wnd):
    """停用視窗的 DWM 顯示/隱藏過場動畫, 讓 withdraw 立即從畫面消失.

    截圖前需要隱藏主視窗/對話框, 淡出動畫會殘留在截圖裡.
    """
    try:
        wnd.update_idletasks()
        hwnd = ctypes.windll.user32.GetAncestor(wnd.winfo_id(), 2)  # GA_ROOT
        val = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 3, ctypes.byref(val), 4)  # DWMWA_TRANSITIONS_FORCEDISABLED
    except Exception:
        pass

C = {
    "bg": "#0F172A",
    "panel": "#1E293B",
    "panel2": "#263449",
    "border": "#334155",
    "text": "#F0F4F8",
    "muted": "#94A3B8",
    "accent": "#22C55E",
    "accent_dark": "#15803D",
    "danger": "#EF4444",
    "warn": "#F59E0B",
    "info": "#38BDF8",
    "sel": "#2E4057",
    "tip": "#0B1220",   # ⓘ 說明提示框的底色 (比背景再深一點, 浮在面板上看得出邊界)
}

FONT = ("Microsoft JhengHei UI", 10)
FONT_BOLD = ("Microsoft JhengHei UI", 10, "bold")
FONT_MONO = ("Consolas", 9)


HOVER = "#31405A"  # 所有互動元件統一的 hover 反白色


def apply(root):
    root.configure(bg=C["bg"])
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=C["bg"], foreground=C["text"],
                    fieldbackground=C["panel"], bordercolor=C["border"],
                    lightcolor=C["panel"], darkcolor=C["panel"],
                    troughcolor=C["panel"], font=FONT)

    style.configure("TFrame", background=C["bg"])
    style.configure("Panel.TFrame", background=C["panel"])
    style.configure("TLabel", background=C["bg"], foreground=C["text"])
    style.configure("Panel.TLabel", background=C["panel"], foreground=C["text"])
    style.configure("Muted.TLabel", background=C["panel"], foreground=C["muted"])
    style.configure("Title.TLabel", background=C["panel"], foreground=C["muted"],
                    font=("Microsoft JhengHei UI", 10, "bold"))
    style.configure("Status.TLabel", background=C["bg"], foreground=C["muted"],
                    font=FONT_BOLD)

    # focuscolor 一律等於按鈕自身背景色 (含各狀態):
    # clam 的焦點環是虛線, 點擊後按鈕保有焦點, 焦點環有色會殘留一圈虛線框
    style.configure("TButton", background=C["panel2"], foreground=C["text"],
                    bordercolor=C["border"], focuscolor=C["panel2"], padding=(10, 4))
    style.map("TButton",
              background=[("active", HOVER), ("disabled", C["panel"])],
              focuscolor=[("active", HOVER), ("disabled", C["panel"])],
              foreground=[("disabled", "#5B6B80")])

    style.configure("Run.TButton", background=C["accent"], foreground="#06240F",
                    focuscolor=C["accent"], font=FONT_BOLD, padding=(14, 5))
    style.map("Run.TButton",
              background=[("active", "#16A34A"), ("disabled", "#1C3A28")],
              focuscolor=[("active", "#16A34A"), ("disabled", "#1C3A28")],
              foreground=[("disabled", "#4A6B55")])

    style.configure("Stop.TButton", background=C["danger"], foreground="#FFFFFF",
                    focuscolor=C["danger"], font=FONT_BOLD, padding=(14, 5))
    style.map("Stop.TButton",
              background=[("active", "#DC2626"), ("disabled", "#3A2430")],
              focuscolor=[("active", "#DC2626"), ("disabled", "#3A2430")],
              foreground=[("disabled", "#7A5560")])

    style.configure("Accent.TButton", background="#173D2A", foreground=C["accent"],
                    bordercolor=C["accent_dark"], focuscolor="#173D2A")
    style.map("Accent.TButton",
              background=[("active", "#1C4F35")],
              focuscolor=[("active", "#1C4F35")])

    # 小型按鈕 (存檔/讀檔/清除等次要操作): 縮小內距與字級, 省空間
    # width=0 覆蓋 clam 預設的 -11 最小寬度, 讓按鈕貼合文字不佔空間
    style.configure("Small.TButton", background=C["panel2"], foreground=C["muted"],
                    bordercolor=C["border"], focuscolor=C["panel2"],
                    padding=(5, 2), width=0, font=("Microsoft JhengHei UI", 9))
    style.map("Small.TButton",
              background=[("active", HOVER), ("disabled", C["panel"])],
              focuscolor=[("active", HOVER), ("disabled", C["panel"])],
              foreground=[("active", C["text"]), ("disabled", "#5B6B80")])

    # Menubutton (新增步驟下拉鈕) — 未設定時 clam 預設 hover 會反白成淺灰
    style.configure("TMenubutton", background=C["panel2"], foreground=C["text"],
                    bordercolor=C["border"], arrowcolor=C["muted"], padding=(10, 4))
    style.map("TMenubutton",
              background=[("active", HOVER), ("disabled", C["panel"])],
              foreground=[("active", C["text"]), ("disabled", "#5B6B80")],
              arrowcolor=[("active", C["text"])])

    style.configure("TCombobox", fieldbackground=C["panel"], background=C["panel2"],
                    foreground=C["text"], arrowcolor=C["muted"], padding=(6, 3))
    style.map("TCombobox",
              # active 需列在 readonly 之前, hover 才有反白 (先匹配者優先)
              fieldbackground=[("active", HOVER), ("readonly", C["panel"])],
              foreground=[("readonly", C["text"])],
              background=[("active", HOVER)],
              arrowcolor=[("active", C["text"])])
    style.configure("TSpinbox", fieldbackground=C["panel"], background=C["panel2"],
                    foreground=C["text"], arrowcolor=C["muted"], padding=(6, 3))
    style.map("TSpinbox",
              background=[("active", HOVER)],
              arrowcolor=[("active", C["text"])])
    style.configure("TEntry", fieldbackground=C["panel"], foreground=C["text"],
                    padding=(6, 3), insertcolor=C["text"])
    style.configure("TCheckbutton", background=C["panel"], foreground=C["text"],
                    focuscolor=C["panel"])
    style.map("TCheckbutton", background=[("active", C["panel"])])
    style.configure("Horizontal.TScale", background=C["panel2"], troughcolor=C["bg"])
    style.map("Horizontal.TScale", background=[("active", HOVER)])
    style.configure("TPanedwindow", background=C["bg"])
    style.configure("Vertical.TScrollbar", background=C["panel2"],
                    troughcolor=C["bg"], bordercolor=C["border"],
                    arrowcolor=C["muted"])
    style.map("Vertical.TScrollbar",
              background=[("active", HOVER)],
              arrowcolor=[("active", C["text"])])

    # 樹狀清單 (選範本對話框: 來源可展開、每列帶縮圖)
    style.configure("Treeview", background=C["bg"], fieldbackground=C["bg"],
                    foreground=C["text"], bordercolor=C["border"],
                    rowheight=40, borderwidth=0)
    style.map("Treeview",
              background=[("selected", C["sel"])],
              foreground=[("selected", C["text"])])
    style.configure("Treeview.Heading", background=C["panel2"],
                    foreground=C["muted"], relief="flat")
    style.layout("Flat.Treeview",  # 不要欄位標題列
                 [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure("Flat.Treeview", background=C["bg"],
                    fieldbackground=C["bg"], foreground=C["text"],
                    rowheight=40, borderwidth=0)
    style.map("Flat.Treeview",
              background=[("selected", C["sel"])],
              foreground=[("selected", C["text"])])

    # Combobox 下拉清單顏色
    root.option_add("*TCombobox*Listbox.background", C["panel"])
    root.option_add("*TCombobox*Listbox.foreground", C["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["sel"])
    root.option_add("*TCombobox*Listbox.selectForeground", C["text"])
    root.option_add("*TCombobox*Listbox.font", FONT)
