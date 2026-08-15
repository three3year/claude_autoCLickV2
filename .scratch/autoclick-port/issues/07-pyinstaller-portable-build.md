# 07 — PyInstaller 打包與可攜驗證

**What to build:** onedir 打包(`--uac-admin` 照舊),torch CPU 版與 DINOv2 權重一併隨包,目標機免裝 Python、免網路:首次啟動自動完成模板登錄並可正常找圖。使用者資料(profiles 含 flows)在 exe 旁。這是收尾票:打包產物即「可攜到其他 Windows 機器」的交付物。

**Blocked by:** 05 — 舊 flow 匯入、06 — flow pack 匯出(新格式)

**Status:** ready-for-agent

- [ ] 打包產物在無 Python、無網路的環境可啟動(以隔離環境或斷網驗證)
- [ ] 首次啟動不需下載模型,驗證階段(非 coarse-only)正常生效
- [ ] 以系統管理員權限啟動(UIPI),對高權限視窗點擊有效
- [ ] 全部測試綠 + 引擎 bench 38/38 收尾確認
- [ ] 打包/發佈步驟寫入文件(build 腳本或說明)
