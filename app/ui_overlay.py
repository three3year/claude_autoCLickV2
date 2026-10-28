import contextlib
import ctypes
import time
import tkinter as tk
from ctypes import wintypes

import applog
import ui_grab
import ui_theme
from automation import capture, win

user32 = ctypes.windll.user32
try:
    dwmapi = ctypes.windll.dwmapi
except OSError:
    dwmapi = None

DWMWA_CLOAKED = 14


def _rect(hwnd):
    r = wintypes.RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return (r.left, r.top, r.right, r.bottom)
    return None


def _is_cloaked(hwnd):
    """UWP/虛擬桌面的隱形視窗 (IsWindowVisible 仍為真) 需剔除."""
    if dwmapi is None:
        return False
    val = ctypes.c_int(0)
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED,
                                    ctypes.byref(val), 4) == 0:
        return bool(val.value)
    return False


def _enum_element_rects(vs):
    vx1, vy1 = vs["x"], vs["y"]
    vx2, vy2 = vs["x"] + vs["w"], vs["y"] + vs["h"]
    tops = []

    def valid_rect(hwnd, allow_fullscreen):
        if not user32.IsWindowVisible(hwnd):
            return None
        r = _rect(hwnd)
        if not r:
            return None
        x1, y1, x2, y2 = r
        w, h = x2 - x1, y2 - y1
        if w < 8 or h < 8:
            return None
        if x2 <= vx1 or x1 >= vx2 or y2 <= vy1 or y1 >= vy2:
            return None
        # 頂層剔除幾乎占滿整個虛擬桌面的 (桌面 Progman/WorkerW)
        if not allow_fullscreen and w >= vs["w"] - 4 and h >= vs["h"] - 4:
            return None
        return r

    children_buf = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def enum_child(hwnd, lp):
        r = valid_rect(hwnd, allow_fullscreen=True)
        if r:
            children_buf.append(r)
        return True

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def enum_top(hwnd, lp):
        r = valid_rect(hwnd, allow_fullscreen=False)
        if r and not _is_cloaked(hwnd):
            children_buf.clear()
            user32.EnumChildWindows(hwnd, enum_child, 0)
            kids = sorted(children_buf,
                          key=lambda c: (c[2] - c[0]) * (c[3] - c[1]))
            tops.append({"rect": r, "children": kids, "hwnd": hwnd})
        return True

    # EnumWindows 依 Z 順序由最上層往下回報
    user32.EnumWindows(enum_top, 0)
    return tops


def _snap_rect(tops, sx, sy):
    for t in tops:
        x1, y1, x2, y2 = t["rect"]
        if not (x1 <= sx < x2 and y1 <= sy < y2):
            continue
        for c in t["children"]:
            cx1, cy1, cx2, cy2 = c
            if cx1 <= sx < cx2 and cy1 <= sy < cy2:
                return c
        return t["rect"]
    return None


def _walk_toplevels(wnd, out):
    for c in wnd.winfo_children():
        if isinstance(c, tk.Toplevel):
            out.append(c)
        _walk_toplevels(c, out)


_hide_state = {"depth": 0, "saved": [], "stale_tops": []}

_MAP_TIMEOUT_MS = 500


def _unbind(w, seq, funcid):
    try:
        scripts = w.bind(seq).split("\n")
        w.tk.call("bind", w._w, seq,
                  "\n".join(s for s in scripts if funcid not in s))
        w.deletecommand(funcid)
    except tk.TclError:
        pass


def _wait_mapped(root, w, timeout_ms=_MAP_TIMEOUT_MS):
    """deiconify 只是把 map 請求排進佇列, 不等於視窗已畫出來."""
    try:
        if w.winfo_viewable():
            return True
        var = tk.IntVar(master=root, value=0)
        funcid = w.bind("<Map>", lambda e: var.set(1), add=True)
        after_id = root.after(timeout_ms, lambda: var.set(2))
        root.wait_variable(var)
        try:
            root.after_cancel(after_id)
        except tk.TclError:
            pass
        _unbind(w, "<Map>", funcid)
        return bool(w.winfo_viewable())
    except tk.TclError:
        return False


def _restore_verified(root, w, zoomed):
    coord = ui_grab.coord
    name = ui_grab.wname(w)
    attempt = 0
    while True:
        try:
            if zoomed:
                w.state("zoomed")  # 直接以最大化映射, 免二次重繪
            else:
                w.deiconify()
        except tk.TclError:
            coord.window_destroyed(w)
            applog.log("clear.restore_gone", win=name)
            return False
        if _wait_mapped(root, w):
            coord.confirm_restored(w)
            applog.log("clear.restored", win=name, retries=attempt)
            return True
        if not coord.restore_timed_out(w):
            applog.log("clear.restore_fail", win=name,
                       retries=coord.max_retries)
            return False
        attempt += 1
        applog.log("clear.restore_retry", win=name, attempt=attempt,
                   timeout_ms=_MAP_TIMEOUT_MS)


def _destroy_stale_tops():
    tops, _hide_state["stale_tops"] = _hide_state["stale_tops"], []
    for t in tops:
        try:
            if t.winfo_exists():
                t.destroy()
        except tk.TclError:
            pass


@contextlib.contextmanager
def screen_clear(root, extra=()):
    # 視窗映射是非同步的: 還原後立刻再隱藏, 中間的 viewable 狀態不可靠, 所以巢狀時只有最外層隱藏/還原
    st = _hide_state
    if st["depth"] == 0:
        try:
            root.update()
        except tk.TclError:
            pass
        wnds = [root]
        _walk_toplevels(root, wnds)
        for w in extra:
            if w not in wnds:
                wnds.append(w)
        st["saved"] = []
        for w in wnds:
            try:
                if not w.winfo_exists() or w.overrideredirect():
                    continue
                state = w.state()
                if state not in ("normal", "zoomed"):
                    continue
                st["saved"].append((w, state == "zoomed"))
            except tk.TclError:
                pass
        ui_grab.coord.clear_entered(st["saved"])
        applog.log("clear.enter",
                   windows=";".join(ui_grab.wname(w) for w, _z in st["saved"]))
        for w, _z in st["saved"]:
            try:
                w.withdraw()
                w.grab_release()  # withdraw 不會自動釋放 grab! 隱形視窗
                # 握著 grab 會吃掉所有真實點擊, 看起來就是整個 App 卡死
            except tk.TclError:
                pass
    st["depth"] += 1
    try:
        yield
    finally:
        st["depth"] -= 1
        if st["depth"] == 0:
            st["saved"] = []
            plan = ui_grab.coord.restore_plan()
            for w, z in plan:
                _restore_verified(root, w, z)
            for w, _z in plan:
                try:
                    if w.winfo_exists() and w.winfo_viewable():
                        w.lift()
                except tk.TclError:
                    pass
            ui_grab.coord.clear_finished()
            applog.log("clear.exit", count=len(plan))
            ui_grab.apply_grab("clear-exit")
            # 前景交接: 此時覆蓋層仍是本程序的前景視窗, focus_force
            # (SetForegroundWindow) 必被允許, 且會把整個擁有鏈 (對話框+主視窗)
            # 一起帶到其他應用程式 (如遊戲) 之上
            try:
                root.lift()
                target = ui_grab.top_window()
                if target is None or not target.winfo_exists():
                    target = root
                target.focus_force()
            except tk.TclError:
                pass
            _destroy_stale_tops()


class _Signal:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


ABORT = _Signal("ABORT")
NO_MARK = _Signal("NO_MARK")

PENDING_MS = 30
BUSY_HINT = "辨識中…　"


def pick(root, mode, hint, delay=0.0, hide=(), base=None, mark=None,
         shot=None, pending=None, late=None):
    try:
        with screen_clear(root, extra=hide):
            _destroy_stale_tops()
            try:
                return _pick_impl(root, mode, hint, delay, base, mark,
                                  shot, pending, late)
            finally:
                top = getattr(root, "_pick_top", None)
                if top is not None:
                    top._closing = True
                    try:
                        if top.winfo_exists():
                            top.grab_release()
                    except tk.TclError:
                        pass
    finally:
        top = getattr(root, "_pick_top", None)
        root._pick_top = None
        if top is not None:
            if _hide_state["depth"] > 0:
                _hide_state["stale_tops"].append(top)
            else:
                try:
                    if top.winfo_exists():
                        top.destroy()
                except tk.TclError:
                    pass


def _hint_text(hint, mode, base, mark):
    if mode == "region" and mark is not None:
        return hint + "　（◎＝原點，拖曳＝框出範圍，Esc 取消）"
    if mode == "region":
        return hint + "　（直接點選＝取用高亮框，拖曳＝自訂範圍，Esc 取消）"
    if mode == "line" and base is not None:
        return hint + "　（原點已標示，點一下目標位置即完成，Esc 取消）"
    if mode == "line" and mark is not None:
        return hint + "　（◎＝原點，拖出一條線＝拖曳路徑，Esc 取消）"
    if mode == "line":
        return hint + "　（拖曳：起點＝基準點，終點＝目標點，Esc 取消）"
    if mark is not None:
        return hint + "　（◎＝原點，Esc 取消）"
    return hint + "　（Esc 取消）"


def _pick_impl(root, mode, hint, delay, base, mark=None, shot=None, pending=None,
               late=None):
    import cv2
    if shot is None:
        root.update()
        if delay > 0:
            time.sleep(delay)
        time.sleep(0.1)  # 視窗已停用過場動畫, 短暫等待合成器刷新即可
        shot = capture.grab()
    img, origin = shot
    vs = {"x": origin[0], "y": origin[1], "w": img.shape[1], "h": img.shape[0]}
    rects = _enum_element_rects(vs)
    h, w = img.shape[:2]

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    dark = cv2.convertScaleAbs(rgb, alpha=0.45)
    ppm = f"P6 {w} {h} 255 ".encode() + dark.tobytes()

    top = tk.Toplevel(root)
    root._pick_top = top
    top.overrideredirect(True)
    top.geometry(f"{w}x{h}+{origin[0]}+{origin[1]}")
    top.attributes("-topmost", True)
    top.configure(bg="black", cursor="crosshair")

    photo = tk.PhotoImage(master=top, data=ppm)
    cv = tk.Canvas(top, width=w, height=h, highlightthickness=0,
                   bg="black", cursor="crosshair")
    cv.pack(fill="both", expand=True)
    cv.create_image(0, 0, anchor="nw", image=photo)
    cv._photo = photo
    hl_item = cv.create_image(0, 0, anchor="nw", state="hidden")

    INFO = "#2080F0"
    hint_x = max(20, -origin[0]) + 40
    click_line = mode == "line" and (base is not None or late == "base")
    hint_bg = cv.create_rectangle(0, 0, 0, 0, fill="#0F172A", outline=INFO, width=1)
    hint_item = cv.create_text(hint_x, 34, anchor="w", fill="#F0F4F8",
                               font=("Microsoft JhengHei UI", 11), text="")

    def set_hint(text):
        cv.itemconfigure(hint_item, text=text)
        cv.coords(hint_bg, hint_x - 14, 16, hint_x + len(text) * 15 + 20, 52)

    if pending is None:
        set_hint(_hint_text(hint, mode, base, mark))
    elif late == "origin":
        set_hint(BUSY_HINT + "原點還在算，算好就直接用；也可以先點一下原點（Esc 取消）")
    elif late is not None:
        set_hint(BUSY_HINT + hint + "　（◎ 原點還在算，可以先點目標；Esc 取消）")
    else:
        set_hint(BUSY_HINT + _hint_text(hint, mode, base, mark))

    snap_box = cv.create_rectangle(0, 0, 0, 0, outline=INFO, width=4)
    sel_rect = cv.create_rectangle(0, 0, 0, 0, outline=INFO, width=2, state="hidden")
    line_item = cv.create_line(0, 0, 0, 0, fill=INFO, width=3,
                               arrow=tk.LAST, state="hidden")
    line_dot = cv.create_oval(0, 0, 0, 0, fill=INFO, outline="", state="hidden")

    MAG_SRC_W, MAG_SRC_H, MAG_ZOOM = 46, 30, 4
    MAG_W, MAG_H = MAG_SRC_W * MAG_ZOOM, MAG_SRC_H * MAG_ZOOM
    INFO_BGR = (240, 128, 32)
    mag_img_item = cv.create_image(0, 0, anchor="nw")
    mag_border = cv.create_rectangle(0, 0, 0, 0, outline=INFO, width=2)
    mag_text_bg = cv.create_rectangle(0, 0, 0, 0, fill="#0F172A", outline=INFO)
    mag_text = cv.create_text(0, 0, fill="#F0F4F8", font=("Consolas", 10), text="")
    mag_photo = [None]  # 防止被回收

    def update_mag(e):
        x0 = min(max(e.x - MAG_SRC_W // 2, 0), max(0, w - MAG_SRC_W))
        y0 = min(max(e.y - MAG_SRC_H // 2, 0), max(0, h - MAG_SRC_H))
        crop = img[y0:y0 + MAG_SRC_H, x0:x0 + MAG_SRC_W]
        zoom = cv2.resize(crop, (MAG_W, MAG_H), interpolation=cv2.INTER_NEAREST)
        cx = (e.x - x0) * MAG_ZOOM + MAG_ZOOM // 2
        cy = (e.y - y0) * MAG_ZOOM + MAG_ZOOM // 2
        cv2.line(zoom, (cx, 0), (cx, MAG_H), INFO_BGR, 1)
        cv2.line(zoom, (0, cy), (MAG_W, cy), INFO_BGR, 1)
        rgb = cv2.cvtColor(zoom, cv2.COLOR_BGR2RGB)
        ph = tk.PhotoImage(master=top,
                           data=f"P6 {MAG_W} {MAG_H} 255 ".encode() + rgb.tobytes())
        mag_photo[0] = ph
        cv.itemconfigure(mag_img_item, image=ph)

        mx = e.x + 26
        if mx + MAG_W > w - 4:
            mx = e.x - 26 - MAG_W
        my = e.y + 26
        if my + MAG_H + 24 > h - 4:
            my = e.y - 26 - MAG_H - 24
        cv.coords(mag_img_item, mx, my)
        cv.coords(mag_border, mx - 1, my - 1, mx + MAG_W + 1, my + MAG_H + 1)
        cv.coords(mag_text_bg, mx - 1, my + MAG_H + 1, mx + MAG_W + 1, my + MAG_H + 23)
        sx, sy = to_screen(e.x, e.y)
        cv.coords(mag_text, mx + MAG_W // 2, my + MAG_H + 12)
        cv.itemconfigure(mag_text, text=f"({sx}, {sy})")

    st = {"start": None, "dragging": False, "snap": None, "down": False,
          "early": pending is not None and late is not None}
    result = [None]

    def show_base(b):
        x0, y0 = b[0] - origin[0], b[1] - origin[1]
        st["start"] = (x0, y0)
        cv.coords(line_dot, x0 - 2.5, y0 - 2.5, x0 + 2.5, y0 + 2.5)
        cv.itemconfigure(line_dot, state="normal")

    def show_mark(m):
        mx0, my0 = m[0] - origin[0], m[1] - origin[1]
        cv.create_oval(mx0 - 7, my0 - 7, mx0 + 7, my0 + 7, outline=INFO, width=2,
                       tags="mark")
        cv.create_oval(mx0 - 2, my0 - 2, mx0 + 2, my0 + 2, fill=INFO, outline="",
                       tags="mark")

    if mode == "line" and base is not None:
        show_base(base)
    if mark is not None and not (mode == "line" and base is not None):
        show_mark(mark)
    hl_photo = [None]  # 高亮裁切圖 (防止被回收)
    hl_box = [None]

    def set_highlight(x1, y1, x2, y2):
        x1 = max(0, min(int(x1), w)); x2 = max(0, min(int(x2), w))
        y1 = max(0, min(int(y1), h)); y2 = max(0, min(int(y2), h))
        if x2 - x1 < 1 or y2 - y1 < 1:
            clear_highlight()
            return
        if hl_box[0] == (x1, y1, x2, y2):
            return
        hl_box[0] = (x1, y1, x2, y2)
        crop = rgb[y1:y2, x1:x2]
        ph = tk.PhotoImage(
            master=top,
            data=f"P6 {x2 - x1} {y2 - y1} 255 ".encode() + crop.tobytes())
        hl_photo[0] = ph
        cv.coords(hl_item, x1, y1)
        cv.itemconfigure(hl_item, image=ph, state="normal")

    def clear_highlight():
        hl_box[0] = None
        cv.itemconfigure(hl_item, state="hidden")

    def finish():
        # 只「結束等待」不銷毀覆蓋層: 覆蓋層是本程序的前景視窗, 立刻銷毀
        # 會把前景讓給其他應用程式 (如剛被自動點擊過的遊戲), 之後還原視窗
        # 時 focus_force 會被 Windows 拒絕, 視窗被壓在遊戲下看似消失.
        # 銷毀延後到 pick() 還原+奪回前景之後.
        try:
            top.unbind_all("<Escape>")
        except tk.TclError:
            pass
        top._closing = True
        try:
            top.grab_release()
        except tk.TclError:
            pass
        try:
            top._done_var.set(1)
        except tk.TclError:
            pass

    def to_screen(x, y):
        return origin[0] + x, origin[1] + y

    def update_snap_highlight(sx, sy):
        snap = _snap_rect(rects, sx, sy)
        st["snap"] = snap
        if snap:
            x1 = snap[0] - origin[0]; y1 = snap[1] - origin[1]
            x2 = snap[2] - origin[0]; y2 = snap[3] - origin[1]
            set_highlight(x1, y1, x2, y2)
            if mode == "region":
                cv.coords(snap_box, x1, y1, x2, y2)
                cv.itemconfigure(snap_box, state="normal")
        else:
            clear_highlight()
            cv.itemconfigure(snap_box, state="hidden")

    def on_move(e):
        update_mag(e)
        sx, sy = to_screen(e.x, e.y)

        if mode == "line" and st["start"] is not None:
            x0, y0 = st["start"]
            cv.coords(line_item, x0, y0, e.x, e.y)
            cv.itemconfigure(line_item, state="normal")
            cv.coords(line_dot, x0 - 2.5, y0 - 2.5, x0 + 2.5, y0 + 2.5)
            cv.itemconfigure(line_dot, state="normal")
            cv.itemconfigure(mag_text, text=f"Δ({e.x - x0:+d}, {e.y - y0:+d})")
            update_snap_highlight(sx, sy)
            return

        if mode == "region" and st["start"] is not None:
            if abs(e.x - st["start"][0]) > 3 or abs(e.y - st["start"][1]) > 3:
                st["dragging"] = True
            if st["dragging"]:
                cv.itemconfigure(snap_box, state="hidden")
                cv.itemconfigure(sel_rect, state="normal")
                cv.coords(sel_rect, st["start"][0], st["start"][1], e.x, e.y)
                set_highlight(min(st["start"][0], e.x), min(st["start"][1], e.y),
                              max(st["start"][0], e.x), max(st["start"][1], e.y))
            return

        update_snap_highlight(sx, sy)

    def on_down(e):
        st["down"] = True
        if mode == "point" or click_line:
            # 放開時才完成: 按下就銷毀覆蓋層的話, 使用者手指放開的
            # release 事件會落到底下的應用程式 (等於把點擊漏出去)
            return
        st["start"] = (e.x, e.y)
        st["dragging"] = False

    def _commit_region(x1, y1, x2, y2):
        x1 = max(0, min(x1, w)); x2 = max(0, min(x2, w))
        y1 = max(0, min(y1, h)); y2 = max(0, min(y2, h))
        if x2 - x1 < 4 or y2 - y1 < 4:
            return False
        result[0] = {
            "screenX": origin[0] + x1, "screenY": origin[1] + y1,
            "w": x2 - x1, "h": y2 - y1,
            "img": img[y1:y2, x1:x2].copy(),
        }
        return True

    def on_up(e):
        st["down"] = False
        early = {"early": True} if st["early"] else {}
        if mode == "point":
            sx, sy = to_screen(e.x, e.y)
            result[0] = dict({"screenX": sx, "screenY": sy}, **early)
            finish()
            return
        if click_line:
            if st["start"] is None:
                result[0] = {"endX": origin[0] + e.x, "endY": origin[1] + e.y,
                             "early": True}
                finish()
                return
            x0, y0 = st["start"]
            result[0] = {
                "dx": e.x - x0, "dy": e.y - y0,
                "startX": origin[0] + x0, "startY": origin[1] + y0,
                "endX": origin[0] + e.x, "endY": origin[1] + e.y,
            }
            finish()
            return
        if mode == "line":
            if st["start"] is None:
                return
            x0, y0 = st["start"]
            if abs(e.x - x0) < 2 and abs(e.y - y0) < 2:
                st["start"] = None
                cv.itemconfigure(line_item, state="hidden")
                cv.itemconfigure(line_dot, state="hidden")
                return
            result[0] = dict({
                "dx": e.x - x0, "dy": e.y - y0,
                "startX": origin[0] + x0, "startY": origin[1] + y0,
                "endX": origin[0] + e.x, "endY": origin[1] + e.y,
            }, **early)
            finish()
            return
        if mode != "region" or st["start"] is None:
            return
        if st["dragging"]:
            x1, y1 = min(st["start"][0], e.x), min(st["start"][1], e.y)
            x2, y2 = max(st["start"][0], e.x), max(st["start"][1], e.y)
            st["start"] = None
            st["dragging"] = False
            if _commit_region(x1, y1, x2, y2):
                finish()
            else:
                cv.itemconfigure(sel_rect, state="hidden")
        else:
            st["start"] = None
            snap = st["snap"]
            if snap and _commit_region(snap[0] - origin[0], snap[1] - origin[1],
                                       snap[2] - origin[0], snap[3] - origin[1]):
                finish()

    cv.bind("<Motion>", on_move)
    cv.bind("<ButtonPress-1>", on_down)
    cv.bind("<ButtonRelease-1>", on_up)
    top.bind("<Escape>", lambda e: finish())
    top.bind_all("<Escape>", lambda e: finish())

    pt = wintypes.POINT()
    if user32.GetCursorPos(ctypes.byref(pt)):
        e0 = tk.Event()
        e0.x, e0.y = pt.x - origin[0], pt.y - origin[1]
        if 0 <= e0.x < w and 0 <= e0.y < h:
            on_move(e0)

    def _guard_grab():
        """整個 overlay 存活期間強制持有 grab.

        預覽框重建等 Toplevel 事件可能把 grab 打掉; 沒有 grab 時真實點擊
        會被導向看不見的視窗, 全螢幕覆蓋層又蓋住一切 → 整個 App 看起來
        卡死. 所以被搶走就奪回, 直到 overlay 關閉. (modal 堆疊在清場期間
        暫停奪 grab, 不會與本守護互搶——overlay 持有 grab 是拾取的必要條件)
        """
        try:
            if not top.winfo_exists() or getattr(top, "_closing", False):
                return
            if top.winfo_viewable() and ui_theme.safe_grab_current(top) is not top:
                top.grab_set()
        except tk.TclError:
            return
        top.after(100, _guard_grab)

    def watch_pending():
        try:
            if not top.winfo_exists() or getattr(top, "_closing", False):
                return
        except tk.TclError:
            return
        status = pending.status()
        if status == "pending":
            top.after(PENDING_MS, watch_pending)
            return
        st["early"] = False
        if status == "failed":
            result[0] = ABORT
            finish()
            return
        got = pending.mark if late is not None else None
        if late == "origin":
            if got is not None and not st["down"]:
                result[0] = {"screenX": got[0], "screenY": got[1], "auto": True}
                finish()
                return
            set_hint(_hint_text(hint, mode, None, None))
            return
        if late is not None and got is None:
            if st["start"] is None and not st["down"]:
                result[0] = NO_MARK
                finish()
                return
        elif late == "base":
            show_base(got)
        elif late == "mark":
            show_mark(got)
        set_hint(_hint_text(hint, mode, got if late == "base" else base,
                            got if late == "mark" else mark))

    top.focus_force()
    _guard_grab()
    if pending is not None:
        watch_pending()
    top._done_var = tk.IntVar(master=root, value=0)
    top.bind("<Destroy>",
             lambda e: top._done_var.set(1) if e.widget is top else None,
             add=True)
    root.wait_variable(top._done_var)
    return result[0]
