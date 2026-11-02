"""接縫 ②: 啟動外部工具的模組＋真的假工具 (會真的開程序, 每個案例限幾秒)."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automation import extproc  # noqa: E402

FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_tool.py")


def run_to_end(args, cwd, limit=10.0):
    p = extproc.start(sys.executable, [FAKE, *args], cwd)
    end = time.monotonic() + limit
    while (code := p.poll()) is None:
        assert time.monotonic() < end, "假工具沒有在時限內結束"
        time.sleep(0.05)
    return p, code


def test_結束碼與合併輸出的最後N行_中文正確(tmp_path):
    lines = [f"say=第{i}行：招募中" for i in range(1, 8)]
    p, code = run_to_end([*lines, "exit=3"], str(tmp_path))
    assert code == 3
    assert p.tail(5) == [f"第{i}行：招募中" for i in range(3, 8)]
    assert p.tail(100)[0] == "第1行：招募中"


def test_詢問預期時間的輸出(tmp_path):
    p, code = run_to_end(["expect=12.5", "--expected-time"], str(tmp_path))
    assert (code, p.tail(5)) == (0, ["12.5"])


def test_工作目錄是給的資料夾(tmp_path):
    d = tmp_path / "工具資料夾"
    d.mkdir()
    p, code = run_to_end(["print-cwd"], str(d))
    assert code == 0
    assert os.path.normcase(p.tail(1)[0]) == os.path.normcase(str(d))


PROBE = """
import sys, time
sys.path.insert(0, {app!r})
from automation import extproc
p = extproc.start(sys.executable, [{fake!r}, "print-console"], {cwd!r})
while p.poll() is None:
    time.sleep(0.05)
open({out!r}, "w", encoding="utf-8").write(p.tail(1)[0])
"""


def test_從沒有主控台的程式啟動_也不開主控台視窗(tmp_path):
    # 打包版是視窗程式 (沒有主控台): 沒擋的話, 主控台程式的工具會自己開一個新的主控台視窗
    import subprocess
    out = tmp_path / "out.txt"
    app = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = PROBE.format(app=app, fake=FAKE, cwd=str(tmp_path), out=str(out))
    subprocess.run([sys.executable, "-c", code], timeout=20,
                   creationflags=subprocess.DETACHED_PROCESS)
    assert out.read_text(encoding="utf-8") == "console=0"


def wait_end(p, limit=5.0):
    end = time.monotonic() + limit
    while (code := p.poll()) is None:
        assert time.monotonic() < end, "假工具沒有在時限內結束"
        time.sleep(0.05)
    return code


def wait_first_line(p, limit=5.0):
    end = time.monotonic() + limit
    while not p.tail(1):
        assert time.monotonic() < end, "假工具沒有在時限內印出第一行"
        time.sleep(0.05)
    return p.tail(1)[0]


def alive(pid):
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        k32.GetExitCodeProcess(h, ctypes.byref(code))
        return code.value == 259  # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


def test_寫一行stop_工具收到後以非0結束(tmp_path):
    p = extproc.start(sys.executable, [FAKE, "listen"], str(tmp_path))
    assert wait_first_line(p) == "等待中"
    p.send_line("stop")
    assert wait_end(p) != 0
    assert p.tail(1) == ["收到停止"]


DYING = """
import os, sys, time
sys.path.insert(0, {app!r})
from automation import extproc
p = extproc.start(sys.executable, [{fake!r}, "print-pid", "listen"], {cwd!r})
end = time.monotonic() + 5
while len(p.tail(2)) < 2 and time.monotonic() < end:
    time.sleep(0.05)
open({out!r}, "w", encoding="utf-8").write(p.tail(2)[0])
os._exit(0)
"""


def test_啟動它的程式不在了_標準輸入關閉_工具自己結束(tmp_path):
    # AutoClick 掛掉時管線的寫入端跟著關掉, 工具讀到 EOF 要當作 stop
    import subprocess
    out = tmp_path / "pid.txt"
    app = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = DYING.format(app=app, fake=FAKE, cwd=str(tmp_path), out=str(out))
    subprocess.run([sys.executable, "-c", code], timeout=20,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    pid = int(out.read_text(encoding="utf-8").removeprefix("pid="))
    end = time.monotonic() + 5
    while alive(pid):
        assert time.monotonic() < end, "標準輸入關閉後工具沒有結束"
        time.sleep(0.05)


def test_結束行程樹_工具和它開的孫程序都不在了(tmp_path):
    p = extproc.start(sys.executable, [FAKE, "grandchild"], str(tmp_path))
    grandchild = int(wait_first_line(p).removeprefix("grandchild="))
    assert alive(grandchild)
    p.kill_tree()
    assert p.poll() is not None
    assert not alive(grandchild)
