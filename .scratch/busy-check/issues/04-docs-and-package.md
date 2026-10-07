# 04 — 文件與打包

**What to build:** 使用者照平常方式開打包版就有忙碌檢查,忙碌暫停已經沒有;給 agent 讀的 app 文件跟著改成忙碌檢查。

規格:`.scratch/busy-check/spec.md`(文件、打包);ADR 0011。

**Blocked by:** 01、02、03

**Status:** done

- [x] `app/CLAUDE.md`:找圖語意、生效確認、檔案日誌欄位裡講忙碌暫停的段落改成忙碌檢查;「不要再用忙碌指示 → 等待消失」那句改指向忙碌檢查;日誌欄位改成 `busy.check`、拿掉 `busy_pause`。
- [x] 打包前把使用者的 profiles 移出 dist,打包後放回;確認 profiles 內容與打包前相同。
- [x] 直接跑 PyInstaller(不經 build.bat),再手動補 arknights profile 的放置步驟。
- [x] 打包版冒煙:開得起來、步驟對話框看得到勾選、主視窗有忙碌出現等候欄位(先確認使用者不在用電腦,見 memory 的冒煙注意事項)。

## Comments

**2026-10-08(實作)**

- `app/CLAUDE.md`:生效確認條目裡的忙碌暫停段落改成忙碌檢查(含執行前檢查、對話框隱藏規則),找圖三態的那句改指向忙碌檢查,日誌欄位改 `busy.check`、拿掉 `busy_pause`。
- 打包三次(第一次後發現第三列塞不下、第二次後依 code review 重構執行器),每次都:確認 AutoClick 沒在跑 → 把 `dist/AutoClick/profiles` 移到 `dist/profiles-live-tmp` → 直接跑 PyInstaller(不經 build.bat)→ 移回 → SHA256 比對 53 個檔案全部相同。arknights profile 本來就在,不必補放。
- 打包版冒煙(`smoke.py`,只啟動 noUAC 版 + PrintWindow 截主視窗 + WM_CLOSE;使用者當時在用電腦,不送真實輸入):第一版截圖看到第三列「忙碌出現等候」標籤被裁掉、欄位只剩半截(預設視窗寬度下右側設定擠不下)→ 把 bar3 右側流程設定改成先 pack(被裁的變成左側校準對說明文字),重新打包後截圖確認三個欄位都在(`results/smoke_main.png`)。
- 沒走到的互動項:步驟對話框的勾選沒在打包版裡實際打開(使用者活躍時不送輸入);對話框由 `test_busy_check_ui.py` 覆蓋,打包版跑的是同一份程式碼。
- 規格「日誌寫在 input / input.confirm 之後、確認那筆之前」字面上對有確認的座標點擊/拖曳是矛盾的(`input.confirm` 本身就是確認那筆):實作是輸入那筆(`input` / 點擊的 `find.target`)之後、確認那筆(`input.confirm` / 確認的 `find.target`)之前,與 `app/CLAUDE.md` 的寫法一致。
