import ctypes
import os
import threading
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def set_dpi_aware():
    """讓本程序以實體像素運作, 使 mss 截圖座標與 SetCursorPos 座標一致"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def virtual_screen():
    """回傳虛擬桌面範圍 (多螢幕時 x/y 可能為負)"""
    return {
        "x": user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        "y": user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        "w": user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        "h": user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    }


MONITOR_DEFAULTTONEAREST = 2


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong),
                ("rcMonitor", ctypes.c_long * 4),
                ("rcWork", ctypes.c_long * 4),
                ("dwFlags", ctypes.c_ulong)]


def monitor_work_area(hwnd):
    """回傳 hwnd 所在螢幕的工作區 (x1, y1, x2, y2, 不含工作列); 失敗回傳虛擬桌面範圍"""
    mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    mi = _MONITORINFO()
    mi.cbSize = ctypes.sizeof(_MONITORINFO)
    if mon and user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
        return tuple(mi.rcWork)
    vs = virtual_screen()
    return (vs["x"], vs["y"], vs["x"] + vs["w"], vs["y"] + vs["h"])


def monitor_rect_at(x, y):
    """回傳離 (x, y) 最近的螢幕範圍 (x1, y1, x2, y2, 含工作列); 失敗回傳虛擬桌面範圍.

    多螢幕大小不一時, 虛擬桌面的角落可能不在任何螢幕上 (SetCursorPos 會被夾回),
    要停游標得用實際螢幕的範圍。
    """
    mon = user32.MonitorFromPoint(_POINT(int(x), int(y)), MONITOR_DEFAULTTONEAREST)
    mi = _MONITORINFO()
    mi.cbSize = ctypes.sizeof(_MONITORINFO)
    if mon and user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
        return tuple(mi.rcMonitor)
    vs = virtual_screen()
    return (vs["x"], vs["y"], vs["x"] + vs["w"], vs["y"] + vs["h"])


GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
GA_ROOT = 2


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


user32.WindowFromPoint.argtypes = [_POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.MonitorFromPoint.argtypes = [_POINT, ctypes.c_ulong]
user32.MonitorFromPoint.restype = wintypes.HMONITOR
# 回傳視窗代號的函式一律宣告 restype: 預設的 c_int 會把代號截斷/符號延伸,
# 比對就會失準
user32.GetAncestor.restype = wintypes.HWND


def is_window_covered(tk_winfo_id):
    """視窗是否被「其他程序」的視窗完全遮住 (取樣點檢查).

    本程序自己的視窗 (對話框、點擊穿透的預覽框) 不算遮蓋;
    WindowFromPoint 會自動跳過 WS_EX_TRANSPARENT 的視窗.
    """
    hwnd = user32.GetAncestor(tk_winfo_id, GA_ROOT) or tk_winfo_id
    if user32.IsIconic(hwnd):
        return True
    r = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return False
    our_pid = os.getpid()
    for fx in (0.08, 0.35, 0.65, 0.92):
        for fy in (0.08, 0.35, 0.65, 0.92):
            pt = _POINT(int(r.left + (r.right - r.left) * fx),
                        int(r.top + (r.bottom - r.top) * fy))
            h = user32.WindowFromPoint(pt)
            if not h:
                continue
            top = user32.GetAncestor(h, GA_ROOT)
            if top == hwnd:
                return False
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(top, ctypes.byref(pid))
            if pid.value == our_pid:
                return False
    return True


EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_SYSTEM_MINIMIZESTART = 0x0016
EVENT_SYSTEM_MINIMIZEEND = 0x0017
EVENT_OBJECT_SHOW = 0x8002
EVENT_OBJECT_HIDE = 0x8003
EVENT_OBJECT_LOCATIONCHANGE = 0x800B
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002
OBJID_WINDOW = 0

_WinEventProc = ctypes.WINFUNCTYPE(
    None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
    wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)


def watch_window_changes(callback, debounce=0.1):
    """其他程序的頂層視窗顯示/隱藏/移動/前景切換時呼叫 callback().

    在專屬背景執行緒安裝 SetWinEventHook 並自帶訊息迴圈
    (不能掛在 Tk 主執行緒: 會與 pynput 的鉤子執行緒衝突導致 GIL 崩潰).
    callback 在掛勾執行緒被呼叫且已去抖 (最多每 debounce 秒一次);
    呼叫端負責轉回 UI 執行緒 (root.after 可跨執行緒使用).
    """
    def run():
        last = [0.0]

        def proc(hook, event, hwnd, id_object, id_child, thread, ms):
            if id_object != OBJID_WINDOW:
                return
            now = time.monotonic()
            if now - last[0] < debounce:
                return
            last[0] = now
            try:
                callback()
            except Exception:
                pass

        cproc = _WinEventProc(proc)  # 存活於執行緒閉包, 不會被 GC
        flags = WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS
        for e1, e2 in ((EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND),
                       (EVENT_SYSTEM_MINIMIZESTART, EVENT_SYSTEM_MINIMIZEEND),
                       (EVENT_OBJECT_SHOW, EVENT_OBJECT_HIDE),
                       (EVENT_OBJECT_LOCATIONCHANGE, EVENT_OBJECT_LOCATIONCHANGE)):
            user32.SetWinEventHook(e1, e2, None, cproc, 0, 0, flags)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    t = threading.Thread(target=run, daemon=True, name="win-event-watch")
    t.start()
    return t


def make_click_through(tk_winfo_id):
    """讓視窗完全不接收滑鼠事件 (點擊穿透), 供純顯示用的覆蓋框.

    tk_winfo_id: Tk 元件的 winfo_id(); 會自動往上找 OS 頂層視窗.
    """
    hwnd = user32.GetAncestor(tk_winfo_id, GA_ROOT) or tk_winfo_id
    get_l = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    set_l = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    style = get_l(hwnd, GWL_EXSTYLE)
    set_l(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)


_BUTTON_FLAGS = {
    "left": (0x0002, 0x0004),
    "right": (0x0008, 0x0010),
    "middle": (0x0020, 0x0040),
}
MOUSEEVENTF_MOVE = 0x0001

INPUT_MOUSE = 0
_ULONG_PTR = ctypes.c_size_t


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", _ULONG_PTR)]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


user32.SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(_INPUT), ctypes.c_int)
user32.SendInput.restype = ctypes.c_uint


def _send_button(flag):
    inp = _INPUT()
    inp.type = INPUT_MOUSE
    inp.mi = _MOUSEINPUT(0, 0, 0, flag, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def _send_hover():
    """原地送一個相對移動 0,0 的真實移動事件.

    SetCursorPos 只是瞬移游標, 不會產生輸入事件; 靠 hover 狀態或讀輸入
    佇列的程式會以為滑鼠沒動過, 按下事件就可能被忽略. 補送一個
    SendInput 移動讓目標程式在目前位置收到 WM_MOUSEMOVE.
    """
    inp = _INPUT()
    inp.type = INPUT_MOUSE
    inp.mi = _MOUSEINPUT(0, 0, 0, MOUSEEVENTF_MOVE, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def move(x, y):
    """移動游標到實體像素座標並確認到位.

    SetCursorPos 用統一的虛擬桌面實體像素座標, 不受各螢幕不同 DPI 影響
    (絕對座標 SendInput 的 0..65535 線性映射在多螢幕混合 DPI 下會偏差數像素);
    極少數情況第一次未即時生效, 確認 GetCursorPos 後重試, 避免按鍵落在舊位置.
    """
    x, y = int(x), int(y)
    user32.SetCursorPos(x, y)
    for _ in range(3):
        cx, cy = cursor_pos()
        if abs(cx - x) <= 1 and abs(cy - y) <= 1:
            return
        user32.SetCursorPos(x, y)
        time.sleep(0.005)


def park(x, y):
    """把游標停到一點, 並讓目標程式也看到它移過去.

    光 move 只是瞬移: 自己畫游標、靠輸入事件追蹤游標的遊戲 (明日方舟主畫面
    會跟著游標偏移) 仍以為游標停在最後一次真實輸入的位置, 移開等於沒移。
    """
    move(x, y)
    _send_hover()


# 滑鼠按鍵「放開後」的預設保險停留秒數: 點擊事件送出後若立刻移動游標
# (下一個座標點擊的 move、找圖前的移開游標等), 目標程式或輸入防護層
# 可能還沒消化完點擊就看到位移, 把點擊當成滑動或直接丟棄。
POST_CLICK_DELAY = 0.4


def click(x, y, button="left", clicks=1, interval=0.06, settle=0.15,
          post=POST_CLICK_DELAY):
    """settle: 到位後的保險停留秒數, 讓目標程式先消化游標移動再按下.
    post: 放開後的保險停留秒數, 避免下一動作 (找圖移開游標等)
    來得太快, 目標程式還沒收到完整點擊."""
    down, up = _BUTTON_FLAGS.get(button, _BUTTON_FLAGS["left"])
    move(x, y)
    _send_hover()
    time.sleep(settle)
    for i in range(max(1, int(clicks))):
        _send_button(down)
        time.sleep(0.04)  # 按住時間比照真人點擊; 太短會被逐幀取樣的程式漏掉
        _send_button(up)
        if i < clicks - 1:
            time.sleep(interval)
    time.sleep(max(0.0, post))


def drag(x1, y1, x2, y2, button="left", duration_ms=300, hold_ms=0,
         post=POST_CLICK_DELAY):
    """按住拖曳: 起點按下 → 平滑插值移動 → 終點放開.

    hold_ms: 到達終點後按住停頓再放開的毫秒數;
    捲動類介面直接放開會觸發慣性滾過頭, 停頓到滾動靜止再放開可避免.
    post: 放開後的保險停留秒數 (同 click), 避免下一動作立刻移動游標.
    """
    down, up = _BUTTON_FLAGS.get(button, _BUTTON_FLAGS["left"])
    move(x1, y1)
    _send_hover()
    time.sleep(0.15)
    _send_button(down)
    time.sleep(0.05)
    n = max(2, int(duration_ms / 15))
    for i in range(1, n + 1):
        move(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n)
        time.sleep(duration_ms / 1000.0 / n)
    time.sleep(0.05 + max(0, hold_ms) / 1000.0)
    _send_button(up)
    time.sleep(max(0.0, post))


def press_keys(combo):
    """按下組合鍵, 例如 'enter'、'ctrl+v'、'alt+f4'."""
    from pynput.keyboard import Controller, Key

    kb = Controller()
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    keys = []
    for p in parts:
        if len(p) == 1:
            keys.append(p)
        else:
            k = getattr(Key, p, None)
            if k is None:
                raise RuntimeError(f"不支援的按鍵名稱: {p}")
            keys.append(k)
    for k in keys:
        kb.press(k)
        time.sleep(0.02)
    for k in reversed(keys):
        kb.release(k)
        time.sleep(0.02)


def cursor_pos():
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y
