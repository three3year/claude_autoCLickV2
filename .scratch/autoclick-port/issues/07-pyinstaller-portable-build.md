# 07 — PyInstaller 打包與可攜驗證

**What to build:** onedir 打包(`--uac-admin` 照舊),torch CPU 版與 DINOv2 權重一併隨包,目標機免裝 Python、免網路:首次啟動自動完成模板登錄並可正常找圖。使用者資料(profiles 含 flows)在 exe 旁。這是收尾票:打包產物即「可攜到其他 Windows 機器」的交付物。

**Blocked by:** 05 — 舊 flow 匯入、06 — flow pack 匯出(新格式)

**Status:** done (2026-08-15) — UAC/UIPI 實機點擊留待使用者手動驗證

- [x] 打包產物在無 Python、無網路的環境可啟動(近似驗證:複製整個 dist 到
      暫存目錄、把本機 torch hub 快取改名讓開後啟動——15.3s 開窗、引擎就緒、
      無任何下載;真正斷網的乾淨機器驗證留給使用者部署時確認)
- [x] 首次啟動不需下載模型,驗證階段(非 coarse-only)正常生效
      (hub 程式碼+權重隨包於 `_internal/torch_home/hub`,frozen 時
      app.py 設 TORCH_HOME 指過去;冒煙無 coarse-only 警告)
- [ ] 以系統管理員權限啟動(UIPI),對高權限視窗點擊有效——exe 帶
      `--uac-admin` manifest;自動啟動測試被 UAC 擋住(見 app/CLAUDE.md),
      同包附 `AutoClick-noUAC.exe` 供自動化冒煙,實機點擊由使用者驗證
- [x] 全部測試綠 + 引擎 bench 38/38 收尾確認(141 passed;38/38 100%)
- [x] 打包/發佈步驟寫入文件(`app/build.bat` + `app/AutoClick.spec` 註解 +
      app/CLAUDE.md「建置與部署」+ README「AutoClick 應用」)

實作備註:
- 交付物 = `app\dist\AutoClick\` 整個資料夾(~700MB):兩個 exe 共用
  `_internal/`,`profiles/arknights`(templates + registered + config)在 exe 旁。
- 打包前置條件:本機 torch hub 快取需存在(spec 會 assert 並提示先從
  原始碼跑一次 app)。
- 部署到既有機器 = 只覆蓋 exe 與 `_internal\`,絕不動 `profiles\`。
