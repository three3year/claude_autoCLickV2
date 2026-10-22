# 01 — tools/build 工具：探測環境、排步驟、執行到打出交付物

Spec: `.scratch/build-bootstrap/spec.md`

**What to build:** 一支新的 Python 工具 `tools/build`（與 `tools/flow_check` 同一種套件佈局，只用標準庫啟動），跑一次就把環境補齊並打包：探測環境事實（venv 在不在、找到哪個系統 Python 與版本、`nvidia-smi` 跑不跑得動、torch hub 快取在不在、舊 dist 在不在）→ 一個純函式把事實排成有序步驟清單（或拒絕：找不到 Python／版本低於 3.11，附訊息）→ 執行器逐步跑 subprocess，每步前印說明、後印結果，結束碼 0／1。步驟順序與失敗處置照 spec：建 venv（缺才做）→ pip 升級與 install `.[app,dev,build]`（一律；失敗警告繼續）→ pip install torch 到 cu126 或 cpu index（一律；失敗警告繼續）→ 無頭建一次引擎驗證器下載權重（缺快取才做；失敗停止）→ PyInstaller `--noconfirm` 打 `AutoClick.spec` 覆蓋 dist（失敗停止；exe 被鎖時提示先關 AutoClick）→ 確認 exe 存在、印位置與資料夾大小（裝了 CUDA 版時附一句變大的原因）。pyproject 新增 `build` extra 含 pyinstaller。`AutoClick.spec` 不改。

**Blocked by:** None — can start immediately

**Status:** done (2026-10-22)

- [x] 在現有 `.venv` 下執行 `python tools/build`：跳過建 venv 與下載、pip 兩步仍跑、PyInstaller 覆蓋 `app\dist\AutoClick`，結束印出交付物位置與大小，結束碼 0
- [x] pyproject 的 optional-dependencies 有 `build = ["pyinstaller"]`，工具裝的是 `.[app,dev,build]`
- [x] 「事實 → 步驟清單」是純函式；`tools/tests` 的測試覆蓋：乾淨機器（缺 venv、缺快取、無 GPU）六步全有且 torch 走 cpu index；有 GPU 走 cu126；venv 與快取都在時跳過建 venv 與下載、pip 仍每次跑；找不到 Python 拒絕並有訊息；版本 3.10 拒絕；pip 步驟標「警告繼續」、下載與打包標「停止」
- [x] 測試不真的建 venv、下載或打包；全套 pytest 綠
- [x] 探測是唯一碰環境的讀取；步驟裡 venv 的套件一律經 venv 的 Python 子程序執行，工具本身可在任何 ≥3.11 的系統 Python 下啟動
- [x] 輸出 UTF-8；AutoClick 開著時打包失敗的訊息提到先關掉它
