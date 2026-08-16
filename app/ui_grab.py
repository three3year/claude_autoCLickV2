"""modal 堆疊的 Tk 執行層: 決策在 window_coord (純邏輯), 這裡只是薄執行層.

取代舊「_regrab 100ms×15 次輪詢逾時放棄 + takeover 白名單」協商:
全域一個堆疊, 開 modal 入堆、<Destroy> 出堆 (含中途關閉非堆頂),
grab 永遠歸堆頂; 事件驅動 (堆頂變更、堆頂視窗 <Map>) 奪回, 不再逾時放棄。
Combobox popdown 之類的過客 grab 不入堆——popdown 自己會把 grab 還回來。
"""
import tkinter as tk

import applog
import ui_theme
from window_coord import ROOT, WindowCoordinator

coord = WindowCoordinator()


def wname(w):
    """視窗在日誌中的名字: 標題優先, 退回 Tk 路徑."""
    try:
        return w.title() or str(w)
    except Exception:
        return str(w)


def top_window():
    """堆頂視窗 (無 modal 或清場中回傳 None)."""
    t = coord.grab_target()
    if t is None or t is ROOT:
        return None
    return t


def register_modal(dlg):
    """dlg 進 modal 堆疊; <Destroy> 自動出堆並把 grab 交回下一層."""
    coord.modal_opened(dlg)
    applog.log("modal.open", win=wname(dlg), depth=coord.stack_depth())

    def on_destroy(e):
        if e.widget is dlg:
            coord.modal_closed(dlg)
            applog.log("modal.close", win=wname(dlg), depth=coord.stack_depth())
            apply_grab("modal-close")

    dlg.bind("<Destroy>", on_destroy, add=True)
    # 清場還原或其他原因重新 map 時, 堆頂奪回 grab (事件驅動, 取代輪詢)
    dlg.bind("<Map>",
             lambda e: apply_grab("map") if e.widget is dlg else None,
             add=True)
    apply_grab("modal-open")


def apply_grab(reason=""):
    """把 grab 設到堆頂.

    清場中不動 (overlay 持有 grab 是拾取的必要條件); 堆空也不動
    (主視窗正常互動不需要 grab, 也不干涉 popdown 之類的過客持有者)。
    堆頂尚未 map 時先跳過——它的 <Map> 綁定屆時會再呼叫本函式。
    """
    target = coord.grab_target()
    if target is None or target is ROOT:
        return
    try:
        if not target.winfo_exists():
            # 沒收到 <Destroy> 就消失的殘留項: 清掉再找下一層
            coord.modal_closed(target)
            apply_grab(reason)
            return
        if not target.winfo_viewable():
            return
        if ui_theme.safe_grab_current(target) is not target:
            target.grab_set()
            applog.log("grab.set", win=wname(target), reason=reason)
    except tk.TclError:
        pass
