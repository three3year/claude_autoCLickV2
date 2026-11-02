"""`外部步驟`的約定 (介面正本 docs/external-step-api.md, ADR 0018) 與`外部工具登錄`.

登錄檔的讀檔驗證在 flowfile (`flowfile.read_tools`); 這裡只拿驗證過的結果查工具在哪。
"""
import math
import os

QUERY_FLAG = "--expected-time"
TAIL_LINES = 5
HWND = "{hwnd}"


class ToolRegistry:
    """一份流程的`外部工具登錄`: 工具名 → {dir, exe}.

    problem 是登錄檔本身的格式錯 (讀流程不因它失敗, 用到工具時才說)。
    """

    def __init__(self, tools=None, problem=None):
        self.tools = {n: dict(v) for n, v in (tools or {}).items()}
        self.problem = problem

    def __eq__(self, other):
        return (isinstance(other, ToolRegistry) and self.tools == other.tools
                and self.problem == other.problem)

    def __repr__(self):
        return f"ToolRegistry({self.tools!r}, problem={self.problem!r})"

    def names(self):
        return sorted(self.tools)

    def locate(self, name):
        """工具的 (入口檔路徑, 工作目錄); 找不到丟 LookupError, 訊息說明缺什麼."""
        if self.problem:
            raise LookupError(f"外部工具登錄（external_tools.yaml）格式錯：{self.problem}")
        entry = self.tools.get(name)
        if entry is None:
            raise LookupError(f"外部工具「{name}」沒有登錄（流程資料夾的 external_tools.yaml）")
        folder = entry["dir"]
        if not os.path.isdir(folder):
            raise LookupError(f"外部工具「{name}」登錄的資料夾不存在：{folder}")
        exe = os.path.join(folder, entry["exe"])
        if not os.path.isfile(exe):
            raise LookupError(f"外部工具「{name}」的入口檔不存在：{exe}")
        return exe, folder


def parse_expected(lines):
    """詢問的輸出 → 預期時間 (正數秒); 不是正數丟 ValueError, 訊息給人看."""
    text = next((ln.strip() for ln in reversed(lines) if ln.strip()), "")
    try:
        secs = float(text)
    except ValueError:
        raise ValueError(f"印出的不是數字：「{text}」" if text else "沒有印出預期時間") from None
    if not math.isfinite(secs) or secs <= 0:
        raise ValueError(f"預期時間要是正數，收到「{text}」")
    return secs
