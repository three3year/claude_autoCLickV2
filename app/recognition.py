"""背景辨識入口: App 唯一一個「辨識在背景做、做完回介面執行緒收尾」的地方 (`辨識中`).

`清場`只涵蓋截圖與覆蓋層上的操作; 校準、找圖、拾取檢查一律在使用者看得到東西的時候做——
清場中截好圖就派到這裡, 視窗還原後還沒做完就以`辨識中`等它, 介面照常重繪 (recognize-off-clear)。
這裡負責:

- 進入與解除`辨識中`; 同時只有一件 (會啟動辨識的入口辨識中都反灰, 不排隊)
- 反灰: 圖片類動作登記在這裡 (主視窗與對話框都登記), 反灰規則只有這一份;
  登記的元件平常要改可用與否也經 `want`, 辨識中改的值留到解除時才套用
- 發起的視窗顯示「辨識中…」(對話框在底列、主視窗在狀態列), 發起的對話框做完前關不掉
- 背景的結果回介面執行緒呼叫收尾; 工作丟例外也解除辨識中並寫紀錄區
- 檔案日誌每件一筆開始、一筆結束 (`recog.start` / `recog.end`, 含耗時與結果)

一件辨識 (`Job`) 可以有好幾段: 背景一段 → 介面收尾 → 收尾裡 `chain` 下一段背景 → …
最後一段收尾做完 (沒再接下一段) 才解除辨識中。背景段由 executor 執行: 平常是 `Threaded`
(daemon 執行緒, 關掉應用不等它, 結果丟棄); 測試換成扣住／放行或當場做完的版本。
"""
import threading
import time
import tkinter as tk

import applog

BUSY_TEXT = "辨識中…"
WATCH_MS = 20   # 背景段做完沒的輪詢間隔 (介面執行緒)


class _Step:
    """一段背景工作: 在 executor 給的執行緒上跑, 結果或例外留著給介面執行緒收."""

    def __init__(self, work):
        self.work = work
        self.result = None
        self.error = None
        self.finished = False

    def run(self):
        try:
            self.result = self.work()
        except BaseException as e:   # 背景的例外帶回介面執行緒報 (不讓執行緒靜靜死掉)
            self.error = e
        finally:
            self.finished = True


class Job:
    """一件背景辨識. 介面執行緒用 then / chain / cancel 接它的結果."""

    def __init__(self, rec, title, origin):
        self.rec, self.title, self.origin = rec, title, origin
        self.step = None
        self.done = None
        self.cancelled = False
        self.ended = False
        self.t0 = time.monotonic()

    def peek(self):
        """目前這段背景的 (做完沒, 結果, 例外); 只看不收 (覆蓋層看 ◎ 好了沒用)."""
        s = self.step
        if s is None or not s.finished:
            return False, None, None
        return True, s.result, s.error

    def then(self, done):
        """這段背景做完後在介面執行緒呼叫 done(結果); 已經做完就當場呼叫."""
        self.done = done
        self.rec._pump()
        return self

    def chain(self, work, done):
        """(在收尾裡) 接下一段背景: 同一件辨識, 辨識中不中斷."""
        self.rec._launch(self, work)
        return self.then(done)

    def cancel(self):
        """結果作廢 (覆蓋層按 Esc): 背景那段做完就解除辨識中, 什麼都不套用."""
        self.cancelled = True
        self.rec._pump()


class Threaded:
    """背景段在 daemon 執行緒上跑; 介面執行緒每 WATCH_MS 看一次做完沒."""

    def launch(self, rec, step):
        threading.Thread(target=step.run, name="recognize", daemon=True).start()
        rec._watch()


DEFAULT_EXECUTOR = Threaded


def _disabled(w):
    try:
        if hasattr(w, "instate"):
            return bool(w.instate(["disabled"]))
        return str(w.cget("state")) == "disabled"
    except tk.TclError:
        return False


def _enable(w, on):
    try:
        if hasattr(w, "instate"):
            w.state(["!disabled"] if on else ["disabled"])
        else:
            w.configure(state="normal" if on else "disabled")
    except tk.TclError:
        pass


def _alive(w):
    try:
        return bool(w.winfo_exists())
    except tk.TclError:
        return False


class Recognition:
    """App 的背景辨識入口 (見模組說明). app 要有 root 與 log_ui."""

    def __init__(self, app, executor=None):
        self.app = app
        self.executor = executor or DEFAULT_EXECUTOR()
        self.job = None
        self._wants = {}       # 登記的圖片類動作 → 不在辨識中時該不該可用
        self._dialogs = {}     # 視窗 → (顯示「辨識中…」的標籤, [關閉／確定／取消])
        self._restore = []     # 辨識中改掉、解除時要還原的 (callable)
        self._watching = False

    # ---------- 登記 ----------

    @property
    def busy(self):
        return self.job is not None

    def register(self, *widgets):
        """圖片類動作 (按了會辨識或改圖片的元件): 辨識中一律反灰."""
        for w in widgets:
            self._wants[w] = not _disabled(w)
            if self.busy:
                _enable(w, False)

    def want(self, w, on):
        """登記的元件平常要改可用與否走這裡: 辨識中先記著, 解除時才套用."""
        self._wants[w] = bool(on)
        if not self.busy:
            _enable(w, on)

    def register_window(self, win, status, closers=()):
        """win 發起辨識時「辨識中…」寫在 status 標籤; closers (關閉／確定／取消) 反灰、視窗 X 無效."""
        self._dialogs = {w: v for w, v in self._dialogs.items() if _alive(w)}
        self._dialogs[win] = (status, list(closers))

    def holds(self, win):
        """win 是不是正在等自己發起的辨識 (做完前關不掉, 狀態列顯示「辨識中…」)."""
        return self.job is not None and self.job.origin is win

    # ---------- 進入與解除`辨識中` ----------

    def start(self, title, work, origin=None):
        """進入辨識中並在背景跑 work(); 回傳 Job (接著用 then 收結果或 cancel)."""
        if self.job is not None:
            raise RuntimeError(f"背景辨識「{self.job.title}」還沒做完")
        job = self.job = Job(self, title, origin if origin is not None else self.app.root)
        self._enter(job)
        self._launch(job, work)
        return job

    def _enter(self, job):
        self._wants = {w: on for w, on in self._wants.items() if _alive(w)}
        for w in self._wants:
            self._wants[w] = not _disabled(w)
            _enable(w, False)
        self._restore = []
        status, closers = self._dialogs.get(job.origin, (None, ()))
        if status is not None and _alive(status):
            text = status.cget("text")
            status.configure(text=BUSY_TEXT)
            self._restore.append(lambda: status.configure(text=text))
        for w in closers:
            if _alive(w) and not _disabled(w):
                _enable(w, False)
                self._restore.append(lambda w=w: _enable(w, True))
        win = job.origin
        if win is not self.app.root and _alive(win):
            # 視窗 X 無效; 解除時換回原本的處理 (空字串＝Tk 預設的關閉)
            prev = win.tk.call("wm", "protocol", win._w, "WM_DELETE_WINDOW")
            win.protocol("WM_DELETE_WINDOW", lambda: None)
            self._restore.append(lambda: win.tk.call(
                "wm", "protocol", win._w, "WM_DELETE_WINDOW", prev))
        applog.log("recog.start", title=job.title, origin=_name(win))

    def _end(self, job, result):
        if job.ended:
            return
        job.ended = True
        if self.job is job:
            self.job = None
        for undo in self._restore:
            try:
                undo()
            except tk.TclError:
                pass
        self._restore = []
        for w, on in list(self._wants.items()):
            if _alive(w):
                _enable(w, on)
            else:
                del self._wants[w]
        applog.log("recog.end", title=job.title, result=result,
                   seconds=f"{time.monotonic() - job.t0:.2f}")

    # ---------- 背景段與收尾 ----------

    def _launch(self, job, work):
        job.step = _Step(work)
        self.executor.launch(self, job.step)

    def _watch(self):
        """(介面執行緒) 每 WATCH_MS 看一次背景段做完沒 (只排一個計時器)."""
        if self._watching:
            return
        self._watching = True
        try:
            self.app.root.after(WATCH_MS, self._tick)
        except tk.TclError:
            self._watching = False

    def _tick(self):
        self._watching = False
        job = self.job
        if job is None:
            return
        self._pump()
        if self.job is job and job.step is not None and not job.step.finished:
            self._watch()

    def _pump(self):
        """(介面執行緒) 背景段做完、收尾也接上了就收尾; 收尾沒再接下一段＝解除辨識中."""
        job = self.job
        if job is None or job.ended:
            return
        step = job.step
        if step is None or not step.finished:
            return
        if job.cancelled:
            self._end(job, "cancelled")
            return
        if not _alive(self.app.root):
            self._end(job, "discarded")   # 應用關掉了: 結果丟棄
            return
        if step.error is not None:
            e = step.error
            applog.exception("recog.error", type(e), e, e.__traceback__)
            self._end(job, "error")
            self.app.log_ui(f"{job.title}失敗：{type(e).__name__}: {e}", "error")
            return
        if job.done is None:
            return
        done, job.done, job.step = job.done, None, None
        try:
            done(step.result)
        except BaseException:
            self._end(job, "error")
            raise
        if job.step is None:
            self._end(job, "ok")


def _name(w):
    try:
        return w.title() or str(w)
    except Exception:
        return str(w)
