ROOT = "<root>"


class WindowCoordinator:
    def __init__(self, max_retries=4):
        self.max_retries = max_retries
        self._stack = []
        self._clearing = False
        self._restore = []
        self._pending = {}

    def modal_opened(self, wid):
        if wid in self._stack:
            self._stack.remove(wid)
        self._stack.append(wid)

    def modal_closed(self, wid):
        if wid in self._stack:
            self._stack.remove(wid)

    def grab_target(self):
        if self._clearing:
            return None
        return self._stack[-1] if self._stack else ROOT

    def stack_depth(self):
        return len(self._stack)

    @property
    def clearing(self):
        return self._clearing

    def clear_entered(self, hidden):
        self._clearing = True
        self._restore = list(hidden)
        self._pending = {wid: 0 for wid, _z in hidden}

    def restore_plan(self):
        return list(self._restore)

    def window_destroyed(self, wid):
        self._restore = [(w, z) for w, z in self._restore if w != wid]
        self._pending.pop(wid, None)
        self.modal_closed(wid)

    def confirm_restored(self, wid):
        self._pending.pop(wid, None)

    def restore_timed_out(self, wid):
        n = self._pending.get(wid)
        if n is None or n >= self.max_retries:
            self._pending.pop(wid, None)
            return False
        self._pending[wid] = n + 1
        return True

    def all_restored(self):
        return not self._pending

    def clear_finished(self):
        self._clearing = False
        self._restore = []
        self._pending = {}
        return self.grab_target()
