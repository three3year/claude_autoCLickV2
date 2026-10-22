"""打包工具: 把「準備環境 → 打包」做成一條路, 第一次 clone 直接跑就能從零打出交付物.

    python tools/build [--dry-run]

人雙擊 `app\\build.bat` 與 agent 由程式呼叫走的都是這支。只用標準庫, 可在任何系統 Python 下啟動
(venv 裡的套件一律經 venv 的 Python 子程序跑); 打包版本身的佈局與行為不變 (spec 在
`app\\AutoClick.spec`, 交付物在 `app\\dist\\AutoClick\\`)。

三段, 接縫是中間那個純函式:

1. `detect()`: 探測環境事實 (`Facts`), 唯一碰環境的讀取——有沒有 `.venv`、找得到哪個系統 Python
   (`py -3` 優先, 再 `python`) 與版本、`nvidia-smi` 跑不跑得動、torch hub 快取在不在、舊 dist 在不在。
2. `plan(facts)`: 事實 → 有序步驟清單 (`Step`: 說明一句、要跑的指令、工作目錄、失敗處置 STOP／WARN),
   或 `Refusal` (找不到 Python、版本低於 3.11, 附給人看的訊息)。順序固定: 建 venv (缺才做) →
   pip 升級與 install `.[app,dev,build]` (一律; 失敗警告繼續) → pip install torch 到 cu126 或 cpu
   index (一律; 警告繼續) → 無頭建一次引擎驗證器下載 DINOv2 權重 (缺快取才做; 停止) →
   PyInstaller `--noconfirm` 覆蓋 dist (停止) → 確認 exe 存在、印位置與大小 (停止)。
3. `run(steps)`: 照清單跑 subprocess, 每步前印說明、後印結果; 結束碼 0／1。打包失敗且舊 dist 的
   exe 被鎖住時提示先關掉 AutoClick。
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple, Union

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MIN_VERSION = (3, 11)   # pyproject 的 requires-python
EXTRAS = ".[app,dev,build]"
TORCH_INDEX_CPU = "https://download.pytorch.org/whl/cpu"
TORCH_INDEX_CUDA = "https://download.pytorch.org/whl/cu126"  # 驅動 ≥560; 見 spec

STOP, WARN = "stop", "warn"

WHAT_VENV = "建 .venv"
WHAT_DEPS = "裝依賴 (pip install " + EXTRAS + ")"
WHAT_TORCH = "裝 torch"
WHAT_WEIGHTS = "下載 DINOv2 權重 (無頭建一次引擎驗證器)"
WHAT_PACK = "打包 (PyInstaller, 覆蓋 app\\dist\\AutoClick)"
WHAT_CONFIRM = "確認交付物"

DIST_EXE = os.path.join("app", "dist", "AutoClick", "AutoClick.exe")

# 下載權重: 走 app 載引擎的同一段 torch.hub.load, 不開視窗、不碰使用者資料;
# 引擎改模型時這裡自動跟著。sys.path 補 src/ 是為了 pip install 失敗 (離線) 時仍能匯入。
_WEIGHTS_SCRIPT = ("import sys; sys.path.insert(0, 'src'); "
                   "from subject_detection.verification import Verifier; Verifier()")

# 確認交付物: exe 存在、資料夾大小; 裝了 CUDA 版 torch 時說明變大的原因。
_CONFIRM_SCRIPT = r"""
import os, sys
exe = os.path.join("app", "dist", "AutoClick", "AutoClick.exe")
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
          " 所以交付物約 3 GB (CPU 版約 700 MB); 在有 NVIDIA 的目標機自動用 GPU, 沒有的照常跑 CPU。")
"""


@dataclass(frozen=True)
class Facts:
    root: str
    venv_python: Optional[str]               # .venv 的 python.exe; 沒有 venv 則 None
    system_python: Optional[Tuple[str, ...]]  # ("py", "-3") 或 ("python",); 找不到則 None
    system_version: Optional[Tuple[int, int]]
    has_nvidia: bool                         # nvidia-smi 跑得動
    hub_cache: bool                          # torch hub 快取 (hub/checkpoints) 在
    dist_exists: bool


@dataclass(frozen=True)
class Step:
    what: str
    commands: Tuple[Tuple[str, ...], ...]   # 依序跑; 任一失敗＝這步失敗
    cwd: str
    on_fail: str                            # STOP／WARN


@dataclass(frozen=True)
class Refusal:
    message: str


Plan = Union[list, Refusal]


# ================= 探測 =================

def _run_quiet(argv, cwd=None):
    """跑一個指令拿 (結束碼, stdout); 找不到程式視為失敗."""
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=60)
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
    """與 AutoClick.spec 同一個判斷: TORCH_HOME 或使用者資料夾 .cache\\torch."""
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


# ================= 排步驟 (純函式) =================

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
    steps.append(Step(WHAT_CONFIRM, ((venv_py, "-c", _CONFIRM_SCRIPT),), facts.root, STOP))
    return steps


# ================= 執行 =================

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
            _say("  > " + " ".join(_short(a) for a in argv))
            code = _run_command(argv, step.cwd)
            if code != 0:
                failed = code
                break
        if failed is None:
            _say("  完成")
            continue
        if step.on_fail == WARN:
            _say("  警告: 這步失敗 (結束碼 %d), 繼續; 離線時只要 venv 裡依賴已齊全就不影響打包" % failed)
            continue
        _say("  失敗 (結束碼 %d), 停止" % failed)
        if step.what == WHAT_PACK:
            exe = os.path.join(root, DIST_EXE)
            if os.path.isfile(exe) and _locked(exe):
                _say("  舊的 AutoClick.exe 被鎖住 (AutoClick 還開著): 先關掉 AutoClick 再打包一次")
        return 1
    _say()
    _say("全部完成")
    return 0


def _short(arg):
    return "<script>" if "\n" in arg else arg


def _print_plan(steps):
    for i, step in enumerate(steps, 1):
        _say("[%d/%d] %s  (失敗: %s)" % (i, len(steps), step.what, "停止" if step.on_fail == STOP else "警告繼續"))
        for argv in step.commands:
            _say("  > " + " ".join(_short(a) for a in argv))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    dry = "--dry-run" in argv
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
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
