"""不准彈出真的 modal 對話框——pytest 與一次性 GUI 冒煙腳本共用的擋板.

真的 messagebox/filedialog 是原生 modal: 一彈出來, 呼叫它的 Tk 執行緒就停在
那裡等人按, 同一執行緒上的 after()/逾時保護全都跑不到——驅動腳本整個卡死,
還蓋在使用者畫面上。驗證規則 (例如「九宮格至少要勾一格」) 被時序不對的合成
點擊觸發時就會這樣。

全部換成記錄; 詢問類一律回「否」(最保守的那條路), 檔案對話框一律回「取消」。

一次性腳本 (不在 pytest 裡) 在 import app 模組前後都可以呼叫, 只要早於第一個
對話框::

    sys.path.insert(0, r"...\\app\\tests")
    from nodialogs import stub_dialogs
    seen = stub_dialogs()
    ...
    print(seen)   # 驅動過程中被擋下的對話框訊息
"""
from tkinter import filedialog, messagebox


def stub_dialogs(setattr=setattr):
    """把 messagebox/filedialog 換成不阻塞的樁, 回傳被擋下的訊息紀錄.

    setattr: 預設直接改模組屬性 (一次性腳本用); pytest 傳 monkeypatch.setattr
    讓測試結束時還原。回傳 {"warning": [...], "info": [...], "error": [...]}。
    """
    seen = {"warning": [], "info": [], "error": []}
    for kind in seen:
        setattr(messagebox, "show" + kind,
                lambda title, msg, _k=kind, **kw: seen[_k].append(msg))
    setattr(messagebox, "askyesno", lambda *a, **kw: False)
    setattr(messagebox, "askyesnocancel", lambda *a, **kw: None)
    setattr(messagebox, "askokcancel", lambda *a, **kw: False)
    for name in ("askopenfilename", "askopenfilenames",
                 "asksaveasfilename", "askdirectory"):
        setattr(filedialog, name, lambda *a, **kw: "")
    return seen
