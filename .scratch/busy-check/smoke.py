from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DIST = os.path.join(ROOT, "app", "dist", "AutoClick")
EXE = os.path.join(DIST, "AutoClick-noUAC.exe")
RESULTS = os.path.join(HERE, "results")
TITLE = "AutoClick — 按鍵精靈"

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))   # per-monitor v2
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x20
PW_RENDERFULLCONTENT = 2
WM_CLOSE = 0x0010


def idle_seconds():
    class LII(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
    lii = LII(ctypes.sizeof(LII), 0)
    user32.GetLastInputInfo(ctypes.byref(lii))
    return (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0


def find_main():
    found = []
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value == TITLE and user32.IsWindowVisible(hwnd):
                ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                if not ex & WS_EX_TRANSPARENT:
                    found.append(hwnd)
        return True
    user32.EnumWindows(EnumProc(cb), 0)
    return found[0] if found else None


def print_window(hwnd, path):
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    hdc = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)

    class BMI(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]
    bmi = BMI(ctypes.sizeof(BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(0, hdc)
    import numpy as np
    sys.path.insert(0, os.path.join(ROOT, "app"))
    from automation import imgio
    img = np.frombuffer(buf, np.uint8).reshape(h, w, 4)[:, :, :3].copy()
    imgio.imwrite(path, img)
    return bool(ok), (w, h)


def main():
    os.makedirs(RESULTS, exist_ok=True)
    print(f"idle={idle_seconds():.0f}s (使用者活躍時只做啟動＋截圖, 不送輸入)")
    if find_main() is not None:
        raise SystemExit("AutoClick 已經開著, 不另外啟動")
    log = os.path.join(DIST, "autoclick.log")
    size0 = os.path.getsize(log) if os.path.isfile(log) else 0
    p = subprocess.Popen([EXE], cwd=DIST)
    t0 = time.time()
    hwnd = None
    while time.time() - t0 < 60:
        hwnd = find_main()
        if hwnd:
            break
        if p.poll() is not None:
            raise SystemExit(f"exe 提早結束, exit={p.returncode}")
        time.sleep(0.5)
    if not hwnd:
        p.kill()
        raise SystemExit("60 秒內沒看到主視窗")
    print(f"主視窗出現: {time.time() - t0:.1f}s, hwnd={hwnd}")
    time.sleep(3)
    out = os.path.join(RESULTS, "smoke_main.png")
    ok, size = print_window(hwnd, out)
    print(f"PrintWindow ok={ok} size={size} → {out}")
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    try:
        p.wait(15)
    except subprocess.TimeoutExpired:
        p.kill()
        print("關閉逾時, 已強制結束")
    print(f"exe 結束 exit={p.returncode}")
    if os.path.isfile(log):
        with open(log, encoding="utf-8", errors="replace") as f:
            f.seek(size0)
            tail = f.read()
        print("---- 這次啟動的 autoclick.log ----")
        print(tail[-3000:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
