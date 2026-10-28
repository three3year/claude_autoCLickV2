"""不准彈出真的 modal 對話框——pytest 與一次性 GUI 冒煙腳本共用的擋板.

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
