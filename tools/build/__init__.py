"""打包工具: 把「準備環境 → 打包」做成一條路, 第一次 clone 直接跑就能從零打出交付物.

    python tools/build [--dry-run]
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple, Union

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MIN_VERSION = (3, 11)
EXTRAS = ".[app,dev,build]"
TORCH_INDEX_CPU = "https://download.pytorch.org/whl/cpu"
TORCH_INDEX_CUDA = "https://download.pytorch.org/whl/cu126"

STOP, WARN = "stop", "warn"

WHAT_VENV = "建 .venv"
WHAT_DEPS = "裝依賴 (pip install " + EXTRAS + ")"
WHAT_TORCH = "裝 torch"
WHAT_WEIGHTS = "下載 DINOv2 權重 (無頭建一次引擎驗證器)"
WHAT_PACK = "打包 (PyInstaller, 覆蓋 app\\dist\\AutoClick)"
WHAT_CONFIRM = "確認交付物"

DIST_EXE = os.path.join("app", "dist", "AutoClick", "AutoClick.exe")

_WEIGHTS_SCRIPT = ("import sys; sys.path.insert(0, 'src'); "
                   "from subject_detection.verification import Verifier; Verifier()")

_CONFIRM_SCRIPT = r"""
import os, sys
exe = sys.argv[1]
if not os.path.isfile(exe):
    print("找不到 " + exe + ": 打包沒有產出 exe, 請看上方 PyInstaller 的訊息")
    sys.exit(1)
folder = os.path.dirname(exe)
total = 0
for d, _, files in os.walk(folder):
    for f in files:
        total += os.path.getsize(os.path.join(d, f))
print("交付物: " + os.path.abspath(folder))
print("大小: %.0f MB (整個資料夾)" % (total / 1e6))
try:
    import torch
    cuda = torch.version.cuda
except Exception:
    cuda = None
if cuda:
    print("venv 裝的是 CUDA 版 torch (cu" + cuda.replace(".", "") + "), CUDA DLL 隨 torch 進了 _internal,"
          " 所以交付物約 4.5 GB (CPU 版約 700 MB); 在有 NVIDIA 的目標機自動用 GPU, 沒有的照常跑 CPU。")
"""


@dataclass(frozen=True)
class Facts:
    root: str
    venv_python: Optional[str]
    system_python: Optional[Tuple[str, ...]]
    system_version: Optional[Tuple[int, int]]
    has_nvidia: bool
    hub_cache: bool
    dist_exists: bool


@dataclass(frozen=True)
class Step:
    what: str
    commands: Tuple[Tuple[str, ...], ...]
    cwd: str
    on_fail: str


@dataclass(frozen=True)
class Refusal:
    message: str


Plan = Union[list, Refusal]


def _run_quiet(argv, cwd=None):
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace")
        return p.returncode, p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def _find_system_python():
    for argv in (("py", "-3"), ("python",)):
        code, out = _run_quiet(argv + ("-c", "import sys; print(sys.version_info[0], sys.version_info[1])"))
        parts = out.split()
        if code == 0 and len(parts) == 2 and all(p.isdigit() for p in parts):
            return argv, (int(parts[0]), int(parts[1]))
    return None, None


def venv_python_path(root):
    return os.path.join(root, ".venv", "Scripts", "python.exe")


def hub_dir():
    return os.path.join(os.environ.get(
        "TORCH_HOME", os.path.join(os.path.expanduser("~"), ".cache", "torch")), "hub")


def detect(root=ROOT) -> Facts:
    venv_py = venv_python_path(root)
    sys_py, version = _find_system_python()
    return Facts(
        root=root,
        venv_python=venv_py if os.path.isfile(venv_py) else None,
        system_python=sys_py,
        system_version=version,
        has_nvidia=_run_quiet(("nvidia-smi", "-L"))[0] == 0,
        hub_cache=os.path.isdir(os.path.join(hub_dir(), "checkpoints")),
        dist_exists=os.path.isfile(os.path.join(root, DIST_EXE)),
    )


def plan(facts: Facts) -> Plan:
    steps = []
    venv_py = facts.venv_python
    if venv_py is None:
        if facts.system_python is None:
            return Refusal("找不到 Python: 請安裝 Python %d.%d 以上 (python.org, 安裝時勾選 py launcher), "
                           "再雙擊一次 build.bat" % MIN_VERSION)
        if facts.system_version < MIN_VERSION:
            return Refusal("找到的 Python 是 %d.%d, 需要 %d.%d 以上: 請安裝新版 Python (python.org), "
                           "再雙擊一次 build.bat" % (facts.system_version + MIN_VERSION))
        venv_py = venv_python_path(facts.root)
        steps.append(Step(WHAT_VENV, (facts.system_python + ("-m", "venv", ".venv"),),
                          facts.root, STOP))
    pip = (venv_py, "-m", "pip", "install")
    steps.append(Step(WHAT_DEPS, (pip + ("--upgrade", "pip"), pip + ("-e", EXTRAS)),
                      facts.root, WARN))
    index = TORCH_INDEX_CUDA if facts.has_nvidia else TORCH_INDEX_CPU
    steps.append(Step(WHAT_TORCH, (pip + ("torch", "--index-url", index),), facts.root, WARN))
    if not facts.hub_cache:
        steps.append(Step(WHAT_WEIGHTS, ((venv_py, "-c", _WEIGHTS_SCRIPT),), facts.root, STOP))
    steps.append(Step(WHAT_PACK, ((venv_py, "-m", "PyInstaller", "--noconfirm", "AutoClick.spec"),),
                      os.path.join(facts.root, "app"), STOP))
    steps.append(Step(WHAT_CONFIRM, ((venv_py, "-c", _CONFIRM_SCRIPT, DIST_EXE),), facts.root, STOP))
    return steps


def _say(msg=""):
    print(msg, flush=True)


def _locked(path):
    """Windows 上正在跑的 exe 不能以寫入開啟."""
    try:
        with open(path, "ab"):
            return False
    except OSError:
        return True


def _run_command(argv, cwd):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    try:
        return subprocess.run(list(argv), cwd=cwd, env=env).returncode
    except OSError as e:
        _say("  無法啟動 %s: %s" % (argv[0], e))
        return 1


def run(steps: Sequence[Step], root=ROOT) -> int:
    total = len(steps)
    for i, step in enumerate(steps, 1):
        _say()
        _say("[%d/%d] %s" % (i, total, step.what))
        failed = None
        for argv in step.commands:
            _say("  > " + _show(argv))
            code = _run_command(argv, step.cwd)
            if code != 0 and failed is None:
                failed = code
        if failed is None:
            _say("  完成")
            continue
        if step.on_fail == WARN:
            _say("  警告: 這步失敗 (結束碼 %d), 繼續; 離線時只要 venv 裡依賴已齊全就不影響打包" % failed)
            continue
        _say("  失敗 (結束碼 %d), 停止" % failed)
        if step.what == WHAT_WEIGHTS:
            _say("  下載 DINOv2 權重需要網路 (torch.hub 從 GitHub 取); 若上一步裝 torch 有警告, 先把那個解決")
        if step.what == WHAT_PACK:
            exe = os.path.join(root, DIST_EXE)
            if os.path.isfile(exe) and _locked(exe):
                _say("  舊的 AutoClick.exe 被鎖住 (AutoClick 還開著): 先關掉 AutoClick 再打包一次")
        return 1
    _say()
    _say("全部完成")
    return 0


def _show(argv):
    return " ".join("<script>" if "\n" in a else a for a in argv)


def _print_plan(steps):
    for i, step in enumerate(steps, 1):
        _say("[%d/%d] %s  (失敗: %s)" % (i, len(steps), step.what, "停止" if step.on_fail == STOP else "警告繼續"))
        for argv in step.commands:
            _say("  > " + _show(argv))


USAGE = "用法: python tools/build [--dry-run]   (--dry-run 只印步驟清單不執行)"


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:] if argv is None else list(argv)
    if any(a in ("-h", "--help") for a in argv):
        _say(USAGE)
        return 0
    unknown = [a for a in argv if a != "--dry-run"]
    if unknown:
        _say("不認得的參數: %s\n%s" % (" ".join(unknown), USAGE))
        return 2
    dry = "--dry-run" in argv
    facts = detect()
    _say("repo: %s" % facts.root)
    _say("環境: venv %s; 系統 Python %s; NVIDIA %s; torch hub 快取 %s; 舊 dist %s" % (
        "在" if facts.venv_python else "缺",
        "%s %d.%d" % ((" ".join(facts.system_python),) + facts.system_version)
        if facts.system_python else "找不到",
        "有" if facts.has_nvidia else "無",
        "在" if facts.hub_cache else "缺",
        "在 (會覆蓋)" if facts.dist_exists else "無"))
    steps = plan(facts)
    if isinstance(steps, Refusal):
        _say(steps.message)
        return 1
    if dry:
        _print_plan(steps)
        return 0
    return run(steps, root=facts.root)
