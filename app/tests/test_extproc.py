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
