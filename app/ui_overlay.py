"""全螢幕截圖選取覆蓋層.

- 直接在螢幕截圖上框選區域或點選座標 (座標 1:1).
- 游標指到視窗/控制項時, 顯示該元素邊界的預設框; 直接點擊即選取該框,
  或按住拖曳自訂範圍.
- 所有模式都會把高亮區域以外的畫面壓黑; 粗藍吸附框只在 region 模式顯示.
"""
import contextlib
import ctypes
import time
import tkinter as tk
from ctypes import wintypes

import cv2

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


# ---------- 視窗/元素矩形列舉 (供游標吸附預設框) ----------

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
    """列舉可見頂層視窗 (依 Z 順序由上到下) 及其子控制項矩形 (實體像素).

    回傳 [{"rect": (x1,y1,x2,y2), "children": [rects...]}, ...].
    vs: 虛擬螢幕範圍 dict, 用來剔除螢幕外的視窗.
    """
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
            # 子控制項依面積由小到大, 供最小含點矩形吸附
            kids = sorted(children_buf,
                          key=lambda c: (c[2] - c[0]) * (c[3] - c[1]))
            tops.append({"rect": r, "children": kids, "hwnd": hwnd})
        return True

    # EnumWindows 依 Z 順序由最上層往下回報
    user32.EnumWindows(enum_top, 0)
    return tops


def _snap_rect(tops, sx, sy):
    """依 Z 順序找出游標所在的最上層視窗, 再吸附其內含點的最小子控制項.

    被其他視窗覆蓋的部分不會被吸附到 (以最上層含點視窗為準).
    回傳矩形 (實體像素) 或 None.
    """
    for t in tops:  # Z 順序: 最上層優先
        x1, y1, x2, y2 = t["rect"]
        if not (x1 <= sx < x2 and y1 <= sy < y2):
            continue
        for c in t["children"]:  # 面積小→大
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

_MAP_TIMEOUT_MS = 500  # 每次 deiconify 後等 map 確認的逾時


def _unbind(w, seq, funcid):
    """只移除指定 funcid 的綁定: tkinter 的 unbind(seq, funcid) 會把同
    事件的「所有」綁定整段清掉 (CPython gh-75666), root 的 <Map> 還掛著
    預覽框顯隱等綁定, 不能整段清."""
    try:
        scripts = w.bind(seq).split("\n")
        w.tk.call("bind", w._w, seq,
                  "\n".join(s for s in scripts if funcid not in s))
        w.deletecommand(funcid)
    except tk.TclError:
        pass


def _wait_mapped(w, timeout_ms=_MAP_TIMEOUT_MS):
    """等待 w 真的畫出來 (map): <Map> 事件驅動 + 逾時, 回傳是否可見.

    deiconify 只是把 map 請求排進佇列, 不等於視窗已畫出來——
    這裡跑事件迴圈直到收到 <Map> 或逾時, 與進場的 update+等待對稱。
    """
    try:
        if w.winfo_viewable():
            return True
        var = tk.IntVar(master=w, value=0)
        funcid = w.bind("<Map>", lambda e: var.set(1), add=True)
        after_id = w.after(timeout_ms, lambda: var.set(2))
        w.wait_variable(var)
        try:
            w.after_cancel(after_id)
        except tk.TclError:
            pass
        _unbind(w, "<Map>", funcid)
        return bool(w.winfo_viewable())
    except tk.TclError:
        return False


def _restore_verified(w, zoomed):
    """驗證式還原單一視窗: deiconify → 等 map 確認, 逾時依狀態機重試.

    回傳是否確認可見; 重試與放棄都寫入日誌 (偶發問題事後可查證)。
    """
    coord = ui_grab.coord
    name = ui_grab.wname(w)
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
        if _wait_mapped(w):
            coord.confirm_restored(w)
            return True
        if not coord.restore_timed_out(w):
            applog.log("clear.restore_fail", win=name,
                       retries=coord.max_retries)
            return False
        applog.log("clear.restore_retry", win=name)


def _destroy_stale_tops():
    """銷毀先前拾取段留下的覆蓋層 (截新圖前必須移除, 否則拍到舊畫面)."""
    tops, _hide_state["stale_tops"] = _hide_state["stale_tops"], []
    for t in tops:
        try:
            if t.winfo_exists():
                t.destroy()
        except tk.TclError:
            pass


@contextlib.contextmanager
def screen_clear(root, extra=()):
    """讓出整個螢幕: 隱藏本 App 的視窗, 離開時驗證式還原. 可巢狀.

    歷來卡死競態的根源都是「還原 → 立刻再隱藏」: 視窗映射是非同步的,
    兩段讓出之間的 viewable 狀態不可靠, 漏記的視窗結束後不會被還原,
    隱形視窗握著焦點/grab 就是整個 App 卡死. 因此讓出螢幕一律走本機制:
    - 巢狀時只有最外層真正隱藏/還原, 中間沒有還原再隱藏的空窗
    - 視窗自動列舉 (root + 所有 Toplevel 子孫 + extra), 呼叫端不會漏傳
    - 進場記錄「本次 withdraw 的清單」(含 zoomed 快照), 離場照清單全數
      還原——不再以 wm state 猜測, 一次失手不會讓之後每次清場都跳過它;
      不在清單上的視窗一律不碰 (執行流程迷你視窗的刻意顯隱自然隔離)
    - 離場逐窗 deiconify 並以 <Map> 事件確認真的畫出來 (逾時重試),
      全部確認可見、grab 交還堆頂之後, 才輪到 pick() 銷毀覆蓋層
    - grab 歸屬由 modal 堆疊決定 (ui_grab); 清場期間堆疊暫停奪 grab
    """
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
                    continue  # 覆蓋框/迷你視窗自行依 root <Map>/<Unmap> 顯隱
                state = w.state()
                if state not in ("normal", "zoomed"):
                    continue  # withdrawn/iconic = 刻意隱藏的視窗, 尊重之
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
            # 還原全程發生在覆蓋層後面 (pick 的覆蓋層延後銷毀), 使用者只會
            # 看到「覆蓋層消失 → 完整畫面」一次揭示; 不做 topmost 脈衝
            # (會把視窗瞬間抬到覆蓋層上, 看起來閃來閃去)
            st["saved"] = []
            plan = ui_grab.coord.restore_plan()
            for w, z in plan:
                _restore_verified(w, z)
            # 依清單順序 lift (root 先、對話框後), 維持 Z 序
            for w, _z in plan:
                try:
                    if w.winfo_exists() and w.winfo_viewable():
                        w.lift()
                except tk.TclError:
                    pass
            ui_grab.coord.clear_finished()
            applog.log("clear.exit", windows=len(plan))
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
            # 交接完成後才銷毀巢狀拾取暫存的覆蓋層 (一次揭示)
            _destroy_stale_tops()


def pick(root, mode, hint, delay=0.0, hide=(), base=None, mark=None):
    """截圖後顯示全螢幕覆蓋層讓使用者選取.

    mode: 'region' 拖曳框選 / 'point' 點一下 / 'line' 拖曳一條線 (起點→終點).
    hide: 額外需要暫時隱藏的視窗 (例如對話框).
    base: line 模式的預設原點 (螢幕座標); 給定時原點已標示,
          使用者只需點一下目標位置即完成.
    mark: 純標示用的原點 (螢幕座標); 只畫記號不影響操作,
          供「相對位置拖曳」自由拖線時對照原點在哪.
    回傳:
      region → {"screenX","screenY","w","h","img"(裁切的 BGR)}
      point  → {"screenX","screenY"}
      line   → {"dx","dy","startX","startY","endX","endY"}
      取消   → None
    """
    try:
        with screen_clear(root, extra=hide):
            # 前一段拾取暫存的覆蓋層顯示著舊截圖, 截新圖前必須先移除
            _destroy_stale_tops()
            try:
                return _pick_impl(root, mode, hint, delay, base, mark)
            finally:
                # 出錯時先釋放 grab, 讓還原流程能把 grab 交回對話框;
                # 覆蓋層本體留到還原後才銷毀 (保住前景擁有權, 見 finish 註解)
                top = getattr(root, "_pick_top", None)
                if top is not None:
                    top._closing = True
                    try:
                        if top.winfo_exists():
                            top.grab_release()
                    except tk.TclError:
                        pass
    finally:
        # 視窗還原、前景/grab 交接完成後才銷毀覆蓋層.
        # 無論成功或出錯最終都必須銷毀: 殘留的全螢幕覆蓋層蓋住一切,
        # 看起來就是整台電腦卡死且無法關閉程式
        top = getattr(root, "_pick_top", None)
        root._pick_top = None
        if top is not None:
            if _hide_state["depth"] > 0:
                # 巢狀 (對話框把多段拾取包在同一次清場裡): 覆蓋層留給
                # 最外層離場「還原完成、前景交接後」銷毀——還原全程在
                # 覆蓋層後面完成, 一次揭示, 且覆蓋層保住本程序的前景權
                _hide_state["stale_tops"].append(top)
            else:
                try:
                    if top.winfo_exists():
                        top.destroy()
                except tk.TclError:
                    pass


def _pick_impl(root, mode, hint, delay, base, mark=None):
    root.update()
    if delay > 0:
        time.sleep(delay)
    time.sleep(0.1)  # 視窗已停用過場動畫, 短暫等待合成器刷新即可

    img, origin = capture.grab()
    vs = {"x": origin[0], "y": origin[1], "w": img.shape[1], "h": img.shape[0]}
    rects = _enum_element_rects(vs)
    h, w = img.shape[:2]

    # PPM (P6) 位元組直接餵給 PhotoImage — 比 PNG 快數倍
    # 底圖用壓黑版, 高亮區域再以原亮度的裁切圖蓋回去
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    dark = cv2.convertScaleAbs(rgb, alpha=0.45)
    ppm = f"P6 {w} {h} 255 ".encode() + dark.tobytes()

    top = tk.Toplevel(root)
    root._pick_top = top  # 供 pick() 的 finally 清掉中途出錯殘留的覆蓋層
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
    hl_item = cv.create_image(0, 0, anchor="nw", state="hidden")  # 高亮亮圖

    INFO = "#2080F0"  # 選取層所有線條統一用藍
    hint_x = max(20, -origin[0]) + 40
    if mode == "region":
        full = hint + "　（直接點選＝取用高亮框，拖曳＝自訂範圍，Esc 取消）"
    elif mode == "line" and base is not None:
        full = hint + "　（原點已標示，點一下目標位置即完成，Esc 取消）"
    elif mode == "line" and mark is not None:
        full = hint + "　（◎＝原點，拖出一條線＝拖曳路徑，Esc 取消）"
    elif mode == "line":
        full = hint + "　（拖曳：起點＝基準點，終點＝目標點，Esc 取消）"
    else:
        full = hint + "　（Esc 取消）"
    cv.create_rectangle(hint_x - 14, 16, hint_x + len(full) * 15 + 20, 52,
                        fill="#0F172A", outline=INFO, width=1)
    cv.create_text(hint_x, 34, anchor="w", fill="#F0F4F8",
                   font=("Microsoft JhengHei UI", 11), text=full)

    snap_box = cv.create_rectangle(0, 0, 0, 0, outline=INFO, width=4)
    sel_rect = cv.create_rectangle(0, 0, 0, 0, outline=INFO, width=2, state="hidden")
    # line 模式: 起點圓點 + 帶箭頭的連線
    line_item = cv.create_line(0, 0, 0, 0, fill=INFO, width=3,
                               arrow=tk.LAST, state="hidden")
    line_dot = cv.create_oval(0, 0, 0, 0, fill=INFO, outline="", state="hidden")

    # ---- 放大鏡 (跟隨游標, 4 倍放大) ----
    MAG_SRC_W, MAG_SRC_H, MAG_ZOOM = 46, 30, 4
    MAG_W, MAG_H = MAG_SRC_W * MAG_ZOOM, MAG_SRC_H * MAG_ZOOM
    INFO_BGR = (240, 128, 32)  # #2080F0 的 BGR
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
        # 游標所在像素的十字定位線
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

    st = {"start": None, "dragging": False, "snap": None}
    result = [None]
    if mode == "line" and base is not None:
        # 預設原點: 直接標示, 之後點一下即為終點
        x0, y0 = base[0] - origin[0], base[1] - origin[1]
        st["start"] = (x0, y0)
        cv.coords(line_dot, x0 - 2.5, y0 - 2.5, x0 + 2.5, y0 + 2.5)
        cv.itemconfigure(line_dot, state="normal")
    if mode == "line" and mark is not None:
        # 純標示的原點記號 (◎): 不影響拖線操作
        mx0, my0 = mark[0] - origin[0], mark[1] - origin[1]
        cv.create_oval(mx0 - 7, my0 - 7, mx0 + 7, my0 + 7, outline=INFO, width=2)
        cv.create_oval(mx0 - 2, my0 - 2, mx0 + 2, my0 + 2, fill=INFO, outline="")
    hl_photo = [None]  # 高亮裁切圖 (防止被回收)
    hl_box = [None]    # 目前高亮範圍, 避免重複重建 PhotoImage

    def set_highlight(x1, y1, x2, y2):
        """指定區域以原亮度顯示, 其餘畫面維持壓黑底圖."""
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
            top.unbind_all("<Escape>")  # 移除逃生口的全域綁定
        except tk.TclError:
            pass
        top._closing = True  # 停止 _guard_grab, 讓 grab 可以交回對話框
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
        """游標吸附元素框 → 該範圍亮顯; 粗藍框只在 region 模式畫出."""
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
            # 判定是否已構成拖曳
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
        if mode == "point" or (mode == "line" and base is not None):
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
        if mode == "point":
            sx, sy = to_screen(e.x, e.y)
            result[0] = {"screenX": sx, "screenY": sy}
            finish()
            return
        if mode == "line" and base is not None:
            # 原點已預設 → 點一下 (放開) 即為終點
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
                # 沒有拖出線 → 重來
                st["start"] = None
                cv.itemconfigure(line_item, state="hidden")
                cv.itemconfigure(line_dot, state="hidden")
                return
            result[0] = {
                "dx": e.x - x0, "dy": e.y - y0,
                "startX": origin[0] + x0, "startY": origin[1] + y0,
                "endX": origin[0] + e.x, "endY": origin[1] + e.y,
            }
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
            # 單擊 → 取用吸附框
            st["start"] = None
            snap = st["snap"]
            if snap and _commit_region(snap[0] - origin[0], snap[1] - origin[1],
                                       snap[2] - origin[0], snap[3] - origin[1]):
                finish()

    cv.bind("<Motion>", on_move)
    cv.bind("<ButtonPress-1>", on_down)
    cv.bind("<ButtonRelease-1>", on_up)
    top.bind("<Escape>", lambda e: finish())
    # 逃生口: 就算焦點/grab 落在別的視窗, Esc 一律取消選取層
    top.bind_all("<Escape>", lambda e: finish())

    # 進場即依目前游標位置顯示高亮, 不必等第一次移動
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

    top.focus_force()
    _guard_grab()
    # 等待改用變數而非 wait_window: finish 不銷毀覆蓋層 (見 finish 註解),
    # 意外銷毀時也要能結束等待, 避免卡死
    top._done_var = tk.IntVar(master=root, value=0)
    top.bind("<Destroy>",
             lambda e: top._done_var.set(1) if e.widget is top else None,
             add=True)
    root.wait_variable(top._done_var)
    return result[0]
