from dataclasses import dataclass
from typing import Optional

from automation import win


@dataclass(frozen=True)
class Entry:
    """串接裡的一項: 流程名 (流程存放區的資料夾名)、串接檔給的輪數、它的`目標程式`路徑 (沒設＝None).
    read_error: 讀不進這份流程時的原因 (有它就只報這一條, 不再查目標程式)."""
    flow: str
    run: int = 1
    program: Optional[str] = None
    read_error: Optional[str] = None


@dataclass(frozen=True)
class Blocker:
    """準備檢查擋下的一組問題; flow 是 None＝整條串接的問題 (例: 空串接)."""
    flow: Optional[str]
    problems: tuple


EMPTY = "串接裡沒有流程"
UNREADABLE = "讀不到流程"
NO_PROGRAM = "未設目標程式"
NOT_RUNNING = "目標程式沒在執行"


def blockers(entries, problems, running):
    """開始前擋下串接的問題, 依流程分組 (空清單＝可以開始); 同一份流程出現兩次只列一次.

    entries: [Entry]; problems: {流程名: [單獨執行會擋的問題文字]};
    running: 執行中的程式路徑。
    """
    if not entries:
        return [Blocker(None, (EMPTY,))]
    out, seen = [], set()
    for e in entries:
        if e.flow in seen:
            continue
        seen.add(e.flow)
        found = _entry_problems(e, problems.get(e.flow, ()), running)
        if found:
            out.append(Blocker(e.flow, tuple(found)))
    return out


def _entry_problems(e, checks, running):
    if e.read_error is not None:
        return [f"{UNREADABLE}：{e.read_error}"]
    found = list(checks)
    if not e.program:
        found.append(NO_PROGRAM)
    elif not any(win.same_program(e.program, p) for p in running):
        found.append(f"{NOT_RUNNING}：{e.program}")
    return found


@dataclass(frozen=True)
class Outcome:
    """呼叫端回報的一份結果: kind 是 "done"／"stopped"／"failed"; failed 附原因."""
    kind: str
    reason: Optional[str] = None


DONE = Outcome("done")
STOPPED = Outcome("stopped")


def failed(reason):
    return Outcome("failed", reason)


def outcome(ended, error_reason):
    if ended == "done":
        return DONE
    if ended == "stopped":
        return STOPPED
    return failed(error_reason)


@dataclass(frozen=True)
class Turn:
    """交給呼叫端的一份: 第 no 份 (從 1 起)、共 total 份."""
    no: int
    total: int
    entry: Entry


DONE_TEXT = "完成"
INTERRUPTED_TEXT = "中斷（急停）"
NOT_RUN_STOP_TEXT = "未執行（急停）"


class Chain:
    """一條已通過準備檢查的串接, 從開始到結束的進行狀態.

    呼叫端反覆: next() 拿下一份 → 執行 → report(結果); next() 回 None＝整條結束。
    急停隨時可以 stop() (任何執行緒: 只記下來), 下一次 next() 就結束整條。
    """

    def __init__(self, entries):
        self.entries = list(entries)
        self.total = len(self.entries)
        self._results = [None] * self.total
        self._current = None
        self._last = None
        self.finished = False
        self.stopped = False

    def stop(self):
        """急停: 交出去還沒回報的那份記中斷、還沒判定的記未執行 (已跳過的維持), 不再交出.
        只設旗標 (F12 從鍵盤監聽的執行緒呼叫), 標記在呼叫端執行緒的下一次 next() 做."""
        self.stopped = True

    def next(self):
        if self.stopped and not self.finished:
            if self._current is not None:
                self._results[self._current.no - 1] = INTERRUPTED_TEXT
                self._current = None
            self._end(NOT_RUN_STOP_TEXT)
        if self.finished or self._current is not None:
            return self._current
        for i, res in enumerate(self._results):
            if res is None:
                self._current = self._last = Turn(i + 1, self.total, self.entries[i])
                return self._current
        self.finished = True
        return None

    @property
    def current(self):
        """交出去、還沒回報結果的那份 (Turn); 沒有是 None."""
        return self._current

    def progress(self):
        t = self._current or self._last
        return f"串接 {t.no}/{t.total}：{t.entry.flow}" if t else ""

    def report(self, outcome):
        """回報剛交出的那份的結果. 急停＝這份記中斷並結束整條;
        失敗＝之後同一個目標程式的都跳過 (不再交出), 其他目標程式的照常交出."""
        t = self._current
        self._current = None
        if outcome.kind == "done":
            self._results[t.no - 1] = DONE_TEXT
        elif outcome.kind == "stopped":
            self._results[t.no - 1] = INTERRUPTED_TEXT
            self.stopped = True
        else:
            self._results[t.no - 1] = f"失敗（{outcome.reason}）"
            skip = f"跳過（因為第 {t.no} 份「{t.entry.flow}」失敗）"
            for i, e in enumerate(self.entries):
                if (self._results[i] is None
                        and win.same_program(e.program, t.entry.program)):
                    self._results[i] = skip

    def _end(self, rest):
        self._results = [rest if r is None else r for r in self._results]
        self.finished = True

    @property
    def last_ran(self):
        return self._last

    def summary(self):
        return [f"{i}. {e.flow}：{res}"
                for i, (e, res) in enumerate(zip(self.entries, self._results), 1)]


def blocker_text(found):
    parts = []
    for b in found:
        if b.flow is None:
            parts.append("\n".join(b.problems))
        else:
            parts.append("\n".join([f"「{b.flow}」"]
                                   + ["・" + p.replace("\n", "\n　") for p in b.problems]))
    return "\n\n".join(parts)
