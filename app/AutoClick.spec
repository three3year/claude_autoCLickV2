# -*- mode: python ; coding: utf-8 -*-
# AutoClick 打包 (onedir; 見 ticket 07 與 app/CLAUDE.md「建置與部署」)
#
# - torch CPU 與 DINOv2 隨包: 把本機 torch hub 快取 (repo 程式碼 + 權重)
#   整包塞進 _internal/torch_home/hub, 執行期 app.py 以 TORCH_HOME 指過去,
#   目標機免網路、免下載。打包前務必先從原始碼跑過一次 app (讓快取存在)。
# - 兩個 exe 共用同一份 _internal:
#     AutoClick.exe        正式版 (--uac-admin: UIPI 需要管理員權限)
#     AutoClick-noUAC.exe  冒煙測試用 (自動化啟動測試會被 UAC 擋住;
#                          對高權限視窗的點擊會被系統丟棄, 不作正式使用)
# - 使用者資料 (profiles/) 不進 _internal, 由 build.bat 放在 exe 旁。
import os

HUB = os.path.join(os.environ.get(
    "TORCH_HOME", os.path.join(os.path.expanduser("~"), ".cache", "torch")),
    "hub")
assert os.path.isdir(os.path.join(HUB, "checkpoints")), (
    f"torch hub 快取不存在 ({HUB}): 先從原始碼啟動一次 app 下載 DINOv2")

a = Analysis(
    ['app.py'],
    pathex=['../src'],  # 主體偵測引擎 (原始碼 layout)
    binaries=[],
    datas=[
        ('../src/subject_detection/default_config.yaml', 'subject_detection'),
        (HUB, 'torch_home/hub'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AutoClick',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 啟動速度優先: UPX 解壓成本吃掉冷啟動 (ADR 0004, 票 02)
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
)
exe_nouac = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AutoClick-noUAC',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 同上 (兩個 exe 共用取捨)
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
)
coll = COLLECT(
    exe,
    exe_nouac,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,  # 同上: DLL 群不壓縮, 免除每次載入的解壓成本
    upx_exclude=[],
    name='AutoClick',
)
