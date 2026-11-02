"""照外部步驟介面 (docs/external-step-api.md) 寫的假外部工具, 用參數演出各種情況.

參數 (可混用, 順序不拘):
    expect=N          詢問 (--expected-time) 時印出的內容, 沒寫＝5
    expect-exit=N     詢問時的結束碼, 沒寫＝0
    query-hang        詢問時卡住不回答
    say=文字          正式執行時印一行 (可寫多次, 依序印)
    exit=N            正式執行的結束碼, 沒寫＝0
    print-cwd         正式執行時印出工作目錄
    print-console     正式執行時印出 console=<主控台視窗 handle> (0＝沒有視窗)
    print-pid         正式執行一開始印出 pid=<自己的 pid>
    listen            印「等待中」後卡住讀標準輸入: 收到 stop 印「收到停止」以 2 結束,
                      標準輸入被關掉 (EOF) 印「標準輸入關閉」以 3 結束
    hang              印「卡住」後卡住, 不理 stop 也不理 EOF
    grandchild        開一個卡住的孫程序, 印 grandchild=<孫程序 pid>, 然後跟 hang 一樣卡住

卡住最多 HANG_CAP 秒就自己以 9 結束, 測試出錯時也不會留下永遠不走的程序。
"""
import os
import subprocess
import sys
import time

HANG_CAP = 30


def hang():
    time.sleep(HANG_CAP)
    return 9


def say(text):
    print(text, flush=True)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    opts = {"expect": "5", "expect-exit": "0", "exit": "0"}
    says = []
    flags = set()
    for a in argv:
        if a.startswith("say="):
            says.append(a[4:])
        elif "=" in a:
            k, v = a.split("=", 1)
            opts[k] = v
        else:
            flags.add(a)
    if "--expected-time" in flags:
        if "query-hang" in flags:
            return hang()
        print(opts["expect"])
        return int(opts["expect-exit"])
    if "print-pid" in flags:
        say(f"pid={os.getpid()}")
    if "print-cwd" in flags:
        print(os.getcwd())
    if "print-console" in flags:
        import ctypes
        print(f"console={ctypes.windll.kernel32.GetConsoleWindow() or 0}")
    for s in says:
        print(s)
    if "listen" in flags:
        say("等待中")
        for line in sys.stdin:
            if line.strip() == "stop":
                say("收到停止")
                return 2
        say("標準輸入關閉")
        return 3
    if "grandchild" in flags:
        child = subprocess.Popen([sys.executable, os.path.abspath(__file__), "hang"],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        say(f"grandchild={child.pid}")
        return hang()
    if "hang" in flags:
        say("卡住")
        return hang()
    return int(opts["exit"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
