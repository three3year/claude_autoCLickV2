"""照外部步驟介面 (docs/external-step-api.md) 寫的假外部工具, 用參數演出各種情況.

參數 (可混用, 順序不拘):
    expect=N          詢問 (--expected-time) 時印出的內容, 沒寫＝5
    expect-exit=N     詢問時的結束碼, 沒寫＝0
    say=文字          正式執行時印一行 (可寫多次, 依序印)
    exit=N            正式執行的結束碼, 沒寫＝0
    print-cwd         正式執行時印出工作目錄
    print-console     正式執行時印出 console=<主控台視窗 handle> (0＝沒有視窗)
"""
import os
import sys


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
        print(opts["expect"])
        return int(opts["expect-exit"])
    if "print-cwd" in flags:
        print(os.getcwd())
    if "print-console" in flags:
        import ctypes
        print(f"console={ctypes.windll.kernel32.GetConsoleWindow() or 0}")
    for s in says:
        print(s)
    return int(opts["exit"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
