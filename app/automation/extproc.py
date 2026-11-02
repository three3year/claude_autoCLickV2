"""啟動`外部工具`: runner 只透過這裡碰行程 (地位同 capture、win; 測試 harness 換掉 `start`).

標準輸入接一條一直開著的管線; 標準輸出與錯誤合併成一條、以 UTF-8 解讀, 背景執行緒
一行一行收下 (只留最後 KEEP 行)。不開主控台視窗, 工作目錄由呼叫端給 (登錄的資料夾)。
"""
import collections
import subprocess
import threading

KEEP = 200
_READER_GRACE = 2.0
_KILL_WAIT = 10.0


def start(exe, args, cwd):
    """啟動 `exe args…` (工作目錄 cwd), 回傳 Process; 啟動不了丟 OSError."""
    return Process(subprocess.Popen(
        [exe, *args], cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW))


class Process:
    def __init__(self, popen):
        self._p = popen
        self._lines = collections.deque(maxlen=KEEP)
        self._lock = threading.Lock()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        self._closed = False

    def _read(self):
        for raw in iter(self._p.stdout.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            with self._lock:
                self._lines.append(line)
        self._p.stdout.close()

    def poll(self):
        """結束碼; 還沒結束回 None. 結束後先把還在管線裡的輸出收完."""
        code = self._p.poll()
        if code is not None and not self._closed:
            self._closed = True
            self._reader.join(_READER_GRACE)
            try:
                self._p.stdin.close()
            except OSError:
                pass
        return code

    def send_line(self, text):
        """寫一行到標準輸入; 程序已結束、管線已關就算了."""
        try:
            self._p.stdin.write((text + "\n").encode("utf-8"))
            self._p.stdin.flush()
        except (OSError, ValueError):
            pass

    def kill_tree(self):
        """強制結束這個程序和它開的所有子孫程序 (taskkill /T), 等它真的結束才回來."""
        if self._p.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self._p.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW,
                           timeout=_KILL_WAIT)
        try:
            self._p.wait(_KILL_WAIT)
        except subprocess.TimeoutExpired:
            self._p.kill()
            self._p.wait(_KILL_WAIT)
        self.poll()

    def tail(self, n):
        """合併輸出的最後 n 行 (不含換行)."""
        with self._lock:
            return list(self._lines)[-n:] if n > 0 else []
