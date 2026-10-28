import threading
import time
import tkinter as tk

import applog

BUSY_TEXT = "辨識中…"
WATCH_MS = 20


class _Step:
    def __init__(self, work):
        self.work = work
        self.result = None
        self.error = None
        self.finished = False

    def run(self):
        try:
            self.result = self.work()
        except BaseException as e:
            self.error = e
        finally:
            self.finished = True


class Job:
    def __init__(self, rec, title, origin):
        self.rec, self.title, self.origin = rec, title, origin
        self.step = None
        self.done = None
        self.cancelled = False
        self.ended = False
        self.t0 = time.monotonic()

    def peek(self):
        s = self.step
        if s is None or not s.finished:
            return False, None, None
        return True, s.result, s.error

    def then(self, done):
        self.done = done
        self.rec._pump()
        return self

    def chain(self, work, done):
        self.rec._launch(self, work)
        return self.then(done)

    def cancel(self):
        self.cancelled = True
        self.rec._pump()


class Threaded:
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
    def __init__(self, app, executor=None):
        self.app = app
        self.executor = executor or DEFAULT_EXECUTOR()
        self.job = None
        self._wants = {}
        self._dialogs = {}
        self._restore = []
        self._watching = False

    @property
    def busy(self):
        return self.job is not None

    def register(self, *widgets):
        for w in widgets:
            self._wants[w] = not _disabled(w)
            if self.busy:
                _enable(w, False)

    def want(self, w, on):
        self._wants[w] = bool(on)
        if not self.busy:
            _enable(w, on)

    def register_window(self, win, status, closers=()):
        self._dialogs = {w: v for w, v in self._dialogs.items() if _alive(w)}
        self._dialogs[win] = (status, list(closers))

    def holds(self, win):
        return self.job is not None and self.job.origin is win

    def start(self, title, work, origin=None):
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

    def _launch(self, job, work):
        job.step = _Step(work)
        self.executor.launch(self, job.step)

    def _watch(self):
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
            self._end(job, "discarded")
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
