from automation import win

TC = r"C:\Program Files\GRYPHLINK\games\Arknights_TC\Arknights.exe"
CN = r"C:\Program Files\Arknights bilibili\games\Arknights Game\Arknights.exe"
LAUNCHER = r"C:\Program Files\Arknights bilibili\Games.exe"


def window(hwnd, path, size, minimized=False, title="明日方舟"):
    return win.Window(hwnd=hwnd, pid=hwnd * 10, title=title, size=size, path=path,
                      minimized=minimized)


def test_同一路徑取還原後面積最大的_最小化的不吃虧():
    windows = [window(1, CN, (1600, 900)),
               window(2, TC, (1280, 720), minimized=True),
               window(3, TC, (400, 300)),
               window(4, LAUNCHER, (1920, 1080))]
    assert win.pick_window(windows, TC).hwnd == 2


def test_路徑比對不分大小寫與斜線():
    windows = [window(1, CN, (1600, 900)), window(2, TC, (1280, 720))]
    got = win.pick_window(windows, "c:/program files/gryphlink/GAMES/arknights_tc/ARKNIGHTS.EXE")
    assert got.hwnd == 2
    assert win.same_program(TC, TC.lower().replace("\\", "/"))
    assert not win.same_program(TC, CN)


def test_沒有符合的就回報找不到_讀不到路徑的不算():
    windows = [window(1, CN, (1600, 900)), window(2, None, (1280, 720))]
    assert win.pick_window(windows, TC) is None
    assert win.pick_window([], TC) is None
    assert not win.same_program(None, None)
