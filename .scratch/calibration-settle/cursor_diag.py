"""游標移開診斷: 以系統管理員身分跑. 記錄 SetCursorPos/SendInput 的回傳值與 GetCursorPos, 各點停 2 秒後截全螢幕.

用法: python cursor_diag.py <輸出資料夾> [倒數秒數]
"""
import ctypes, ctypes.wintypes as wt, os, sys, time

out = sys.argv[1]
delay = int(sys.argv[2]) if len(sys.argv) > 2 else 20
os.makedirs(out, exist_ok=True)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass
u = ctypes.windll.user32
log = open(os.path.join(out, "log.txt"), "w", encoding="utf-8")


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    log.write(s + "\n"); log.flush()


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def pos():
    p = wt.POINT(); u.GetCursorPos(ctypes.byref(p)); return (p.x, p.y)


def fg():
    b = ctypes.create_unicode_buffer(256); u.GetWindowTextW(u.GetForegroundWindow(), b, 256); return b.value


def hover():
    i = INPUT(); i.type = 0; i.mi = MOUSEINPUT(0, 0, 0, 0x0001, 0, 0)
    n = u.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))
    return n, ctypes.GetLastError()


def shot(name):
    import mss, mss.tools
    with mss.mss() as m:
        mon = m.monitors[1]
        img = m.grab(mon)
        mss.tools.to_png(img.rgb, img.size, output=os.path.join(out, name + ".png"))


say("admin:", bool(ctypes.windll.shell32.IsUserAnAdmin()))
for k in range(delay, 0, -1):
    print(f"{k} 秒後開始，請切到繁中主畫面、之後別碰滑鼠", flush=True); time.sleep(1)
home = pos()
say("前景:", fg(), " 原位:", home)
shot("0_home")
for label, (x, y) in [("A_停點(0,1035)", (0, 1035)), ("B_視窗內左下(5,1020)", (5, 1020))]:
    ok = u.SetCursorPos(x, y)
    err = ctypes.GetLastError()
    say(label, "SetCursorPos=", ok, "err=", err, "→", pos())
    say(label, "SendInput(hover)=", hover(), "→", pos())
    for t in range(8):
        time.sleep(0.25)
    say(label, "2 秒後:", pos(), " 前景:", fg())
    shot(label)
u.SetCursorPos(*home); hover()
say("移回:", pos())
