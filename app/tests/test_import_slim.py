"""開窗關鍵路徑瘦身 (startup-speed 票 06): 首次映射前不載重量級套件.

以子程序跑探針 (_slim_probe.py)——importlib 狀態乾淨, 直接斷言
cv2/mss/torch/numpy 都不在 sys.modules。
"""
import os
import subprocess
import sys


def test_主視窗首次映射前_不載入重量級套件():
    probe = os.path.join(os.path.dirname(__file__), "_slim_probe.py")
    out = subprocess.run([sys.executable, probe], capture_output=True,
                         text=True, timeout=120,
                         encoding="utf-8", errors="replace")
    assert out.returncode == 0, out.stderr
    assert "HEAVY=none" in out.stdout, (out.stdout or "") + (out.stderr or "")
