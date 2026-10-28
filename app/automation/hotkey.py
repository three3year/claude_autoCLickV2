import threading


def start_stop_hotkey(on_stop):
    """啟動背景監聽, 按下 F12 時呼叫 on_stop(). 回傳 listener."""
    from pynput import keyboard

    def on_press(key):
        if key == keyboard.Key.f12:
            try:
                on_stop()
            except Exception:
                pass

    listener = keyboard.Listener(on_press=on_press)
    t = threading.Thread(target=listener.start, daemon=True)
    t.start()
    return listener
