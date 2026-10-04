# 06 — 文件更新、重寫四份流程、重新打包、實跑

**What to build:** 使用者的四份在用流程(基建換班_簡中/繁中、日常_簡中/繁中)不再因網路延遲失敗。app 的 agent 文件把「點擊後確認」改成「生效確認」並補上新規則。Claude 先備份正式 profile,再重寫四份流程:鈴鐺(基建換班 2、日常簡中 19、日常繁中 9)改為確認圖出現、確認圖用左下角「待辦事項」標籤(簡中 demo4、繁中 demo3 截);每個捲動拖曳設原點的圖離開;換班 ⇌ 後的固定 1500ms 改成等待消失(忙碌指示,出現等候上限 1000ms);其他不確認的找圖點擊與座標點擊能確認的補上,下一步已有確認的拿掉固定等待;簡中、繁中各設一張忙碌指示範本(文字那段)。步驟編號以重寫當時的流程為準(flow-scale 遷移後)。

規格:`.scratch/effect-confirm/spec.md`;ADR 0008;memory:flow-speed-over-fixed-waits、engine-cannot-tell-row-labels-apart。

**Blocked by:** 01、02、03、04、05、flow-scale/07

**Status:** ready-for-agent

- [ ] app 的 agent 文件改用「生效確認」並描述補做、忙碌指示、出現等候上限
- [ ] 正式 profile 已備份,位置記在本檔 Comments
- [ ] 四份流程依上述規則重寫,同步更新各自的人讀版 .md
- [ ] 用示範影片自我驗證:鈴鐺確認圖、忙碌指示範本、拖曳來源找圖都找得到
- [ ] 全部 pytest 通過,重新打包(注意 memory:build-bat-encoding、repackage-move-user-data-out、packaged-smoke-user-present)
- [ ] 使用者實跑四份流程;日誌裡座標點擊與拖曳的確認紀錄都是生效,換班段不再有固定 1500ms
