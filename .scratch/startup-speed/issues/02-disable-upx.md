# 02 — 關閉 UPX(獨立快速改善)

**What to build:** 打包關閉 UPX 壓縮,消除每次啟動(尤其冷啟動)的 DLL
解壓成本。dist 體積由約 700MB 變大到約 900MB–1GB 屬預期取捨(ADR 0004)。
重新打包後量測冷/熱啟動開窗秒數,與基準(熱 3.1–4.4s、冷 15.3s 歷史紀錄)
對照留紀錄。

**Blocked by:** None — can start immediately

**Status:** done

- [x] spec 關閉 UPX,重新打包成功、打包版可正常啟動操作
- [x] 量測並記錄關 UPX 前後的開窗秒數對照(熱啟動至少兩次取值)
- [x] dist 體積變化記錄在 Comments
- [x] 部署慣例不變:只覆蓋 exe 與 _internal/,不動使用者 profiles/

## Comments

**2026-08-16 實測發現:UPX 從來沒有真正生效。** 本機沒有安裝 upx.exe
(`where upx` 找不到),PyInstaller 對 `upx=True` 的行為是靜默跳過——
所以「UPX 解壓吃掉啟動時間」的假說不成立,這張票沒有速度紅利可拿。
spec 仍改為明確 `upx=False`(三處:兩個 EXE 與 COLLECT):把 ADR 0004 的
取捨寫進設定,防止日後環境裝了 upx 之後打包「意外變慢」。

量測(舊程式碼快照、upx=False、乾淨 worktree 建置,AutoClick-noUAC):
- 第一次啟動(檔案快取冷):**11.4s** 開窗——與歷史紀錄 15.3s 同量級,
  確認冷啟動的成本來自檔案 IO/模型載入,與 UPX 無關
- 第二次(熱):**2.9s**,與既有 dist 的 3.1–4.4s 一致(無差異,符合預期)
- dist 體積:691MB vs 既有 700MB(相同量級,差異來自 profiles 內容)
