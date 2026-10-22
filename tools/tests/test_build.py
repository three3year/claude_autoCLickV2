"""打包工具: 餵一組環境事實, 斷言排出來的步驟清單 (哪幾步、順序、argv 關鍵片段、失敗處置).

不真的建 venv、下載或打包; 唯一接縫是純函式 `build.plan`。另一條靜態防線: `app\\build.bat`
全為 ASCII (cmd 用錯 codepage 解析 UTF-8 批次檔會把行當指令跑掉)。
"""
import os
import sys

import pytest

import build
from vtf_synth import ROOT

VENV_PY = os.path.join(str(ROOT), ".venv", "Scripts", "python.exe")


def facts(**over):
    base = dict(root=str(ROOT), venv_python=None, system_python=("py", "-3"),
                system_version=(3, 12), has_nvidia=False, hub_cache=False, dist_exists=False)
    base.update(over)
    return build.Facts(**base)


def whats(steps):
    return [s.what for s in steps]


def argv_text(step):
    return " ".join(" ".join(c) for c in step.commands)


def step(steps, key):
    [s] = [s for s in steps if key in s.what]
    return s


# ---------- 乾淨機器 ----------

def test_乾淨機器六步全有且順序固定():
    steps = build.plan(facts())
    assert whats(steps) == [build.WHAT_VENV, build.WHAT_DEPS, build.WHAT_TORCH,
                            build.WHAT_WEIGHTS, build.WHAT_PACK, build.WHAT_CONFIRM]


def test_建_venv_用找到的系統_Python():
    s = step(build.plan(facts()), build.WHAT_VENV)
    assert s.commands[0][:4] == ("py", "-3", "-m", "venv")
    assert s.commands[0][-1] == ".venv"
    assert s.cwd == str(ROOT)
    assert s.on_fail == build.STOP


def test_venv_裡的套件一律經_venv_的_Python_執行():
    steps = build.plan(facts())
    for s in steps[1:]:
        for argv in s.commands:
            assert argv[0] == VENV_PY, s.what


def test_裝依賴含_build_extra_且失敗警告繼續():
    s = step(build.plan(facts()), build.WHAT_DEPS)
    assert ".[app,dev,build]" in argv_text(s)
    assert "--upgrade pip" in argv_text(s)
    assert s.on_fail == build.WARN


def test_無_GPU_torch_走_cpu_index():
    s = step(build.plan(facts(has_nvidia=False)), build.WHAT_TORCH)
    assert build.TORCH_INDEX_CPU in argv_text(s)
    assert build.TORCH_INDEX_CUDA not in argv_text(s)
    assert s.on_fail == build.WARN


def test_有_GPU_torch_走_cu126_index():
    s = step(build.plan(facts(has_nvidia=True)), build.WHAT_TORCH)
    assert build.TORCH_INDEX_CUDA in argv_text(s)
    assert build.TORCH_INDEX_CUDA.endswith("/cu126")


def test_下載權重走引擎驗證器且失敗停止():
    s = step(build.plan(facts()), build.WHAT_WEIGHTS)
    assert "subject_detection.verification import Verifier" in argv_text(s)
    assert "Verifier()" in argv_text(s)
    assert s.cwd == str(ROOT)
    assert s.on_fail == build.STOP


def test_打包用_PyInstaller_覆蓋且在_app_目錄():
    s = step(build.plan(facts()), build.WHAT_PACK)
    assert s.commands[0][1:] == ("-m", "PyInstaller", "--noconfirm", "AutoClick.spec")
    assert s.cwd == os.path.join(str(ROOT), "app")
    assert s.on_fail == build.STOP


def test_確認交付物看_exe_存在且失敗停止():
    s = step(build.plan(facts()), build.WHAT_CONFIRM)
    assert "AutoClick.exe" in argv_text(s)
    assert s.on_fail == build.STOP


# ---------- venv 與快取都在 ----------

def test_venv_與快取都在_跳過建_venv_與下載_pip_仍每次跑():
    steps = build.plan(facts(venv_python=VENV_PY, hub_cache=True, dist_exists=True))
    assert whats(steps) == [build.WHAT_DEPS, build.WHAT_TORCH, build.WHAT_PACK, build.WHAT_CONFIRM]


def test_venv_在時不需要系統_Python():
    steps = build.plan(facts(venv_python=VENV_PY, system_python=None, system_version=None))
    assert isinstance(steps, list)
    assert whats(steps)[0] == build.WHAT_DEPS


def test_只缺快取():
    steps = build.plan(facts(venv_python=VENV_PY, hub_cache=False))
    assert whats(steps) == [build.WHAT_DEPS, build.WHAT_TORCH, build.WHAT_WEIGHTS,
                            build.WHAT_PACK, build.WHAT_CONFIRM]


# ---------- 拒絕 ----------

def test_找不到_Python_拒絕並有訊息():
    got = build.plan(facts(system_python=None, system_version=None))
    assert isinstance(got, build.Refusal)
    assert "Python" in got.message and "3.11" in got.message


def test_版本_3_10_拒絕():
    got = build.plan(facts(system_version=(3, 10)))
    assert isinstance(got, build.Refusal)
    assert "3.10" in got.message and "3.11" in got.message


def test_版本_3_11_可以():
    assert isinstance(build.plan(facts(system_version=(3, 11))), list)


# ---------- build.bat 靜態防線 ----------

def test_build_bat_全為_ASCII():
    data = (ROOT / "app" / "build.bat").read_bytes()
    bad = [(i + 1, line) for i, line in enumerate(data.splitlines()) if any(b > 127 for b in line)]
    assert bad == [], bad


def test_build_bat_轉交給工具():
    lines = (ROOT / "app" / "build.bat").read_text(encoding="ascii").splitlines()
    code = "\n".join(l for l in lines if not l.strip().lower().startswith("rem"))
    assert "tools\\build" in code
    assert "pause" in code
    assert "PyInstaller" not in code and ".venv" not in code


# ---------- 執行器 (用假步驟, 不碰環境) ----------

def test_執行器照清單跑_警告繼續_停止就停(capsys, tmp_path):
    py = sys.executable
    ok = build.Step("一", ((py, "-c", "print('hi')"),), str(tmp_path), build.STOP)
    warn = build.Step("二", ((py, "-c", "raise SystemExit(3)"),), str(tmp_path), build.WARN)
    stop = build.Step("三", ((py, "-c", "raise SystemExit(4)"),), str(tmp_path), build.STOP)
    never = build.Step("四", ((py, "-c", "open(r'%s', 'w')" % (tmp_path / "touched")),),
                       str(tmp_path), build.STOP)
    code = build.run([ok, warn, stop, never])
    out = capsys.readouterr().out
    assert code == 1
    assert "一" in out and "二" in out and "三" in out and "四" not in out
    assert "警告" in out
    assert not (tmp_path / "touched").exists()


def test_執行器全綠回_0(capsys, tmp_path):
    py = sys.executable
    code = build.run([build.Step("一", ((py, "-c", "pass"),), str(tmp_path), build.STOP)])
    assert code == 0


def test_拒絕時_main_印訊息回_1(capsys, monkeypatch):
    monkeypatch.setattr(build, "detect", lambda: facts(system_python=None, system_version=None))
    assert build.main([]) == 1
    assert "3.11" in capsys.readouterr().out


def test_不認得的參數回_2_help_回_0(capsys, monkeypatch):
    monkeypatch.setattr(build, "detect", lambda: facts())
    assert build.main(["--bogus"]) == 2
    assert build.main(["--help"]) == 0
    assert "--dry-run" in capsys.readouterr().out


def test_警告步驟每條指令都跑(capsys, tmp_path):
    cmds = ((sys.executable, "-c", "raise SystemExit(3)"),
            (sys.executable, "-c", "open(r'%s', 'w')" % (tmp_path / "second")))
    assert build.run([build.Step("一", cmds, str(tmp_path), build.WARN)]) == 0
    assert (tmp_path / "second").exists()


def test_dry_run_只印清單不執行(capsys, monkeypatch):
    monkeypatch.setattr(build, "detect", lambda: facts())
    assert build.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert build.WHAT_VENV in out and build.WHAT_PACK in out
    assert build.TORCH_INDEX_CPU in out


def test_打包失敗且_exe_被鎖住時提示先關_AutoClick(capsys, tmp_path, monkeypatch):
    exe = tmp_path / "app" / "dist" / "AutoClick" / "AutoClick.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"x")
    monkeypatch.setattr(build, "_locked", lambda path: path == str(exe))
    py = sys.executable
    pack = build.Step(build.WHAT_PACK, ((py, "-c", "raise SystemExit(1)"),), str(tmp_path),
                      build.STOP)
    assert build.run([pack], root=str(tmp_path)) == 1
    assert "關掉" in capsys.readouterr().out


@pytest.mark.parametrize("what", [build.WHAT_DEPS, build.WHAT_TORCH])
def test_離線時_pip_失敗只警告(what):
    s = step(build.plan(facts()), what)
    assert s.on_fail == build.WARN
