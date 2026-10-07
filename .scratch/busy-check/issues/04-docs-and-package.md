# 04 — 文件與打包

**What to build:** 使用者照平常方式開打包版就有忙碌檢查,忙碌暫停已經沒有;給 agent 讀的 app 文件跟著改成忙碌檢查。

規格:`.scratch/busy-check/spec.md`(文件、打包);ADR 0011。

**Blocked by:** 01、02、03

**Status:** ready-for-agent

- [ ] `app/CLAUDE.md`:找圖語意、生效確認、檔案日誌欄位裡講忙碌暫停的段落改成忙碌檢查;「不要再用忙碌指示 → 等待消失」那句改指向忙碌檢查;日誌欄位改成 `busy.check`、拿掉 `busy_pause`。
- [ ] 打包前把使用者的 profiles 移出 dist,打包後放回;確認 profiles 內容與打包前相同。
- [ ] 直接跑 PyInstaller(不經 build.bat),再手動補 arknights profile 的放置步驟。
- [ ] 打包版冒煙:開得起來、步驟對話框看得到勾選、主視窗有忙碌出現等候欄位(先確認使用者不在用電腦,見 memory 的冒煙注意事項)。
