# 06 — 實跑驗收

**What to build:** 使用者用打包版實跑四份流程,確認換班與彈窗不再在忙碌時操作。我監看 `autoclick.log`。

規格:`.scratch/busy-check/spec.md`(最終驗收)。

**Blocked by:** 05 — 四份流程勾忙碌檢查與交付報告

**Status:** ready-for-human

- [ ] 換班段每個 ⇄ 與拖曳都有 `busy.check`;簡中多數 `gone`;拖曳沒有 `inputs=2`。
- [ ] 開頭清彈窗沒有提早跳出。
- [ ] 傳遞線索、可收獲、幹員信賴、確定的確認沒有逾時。
- [ ] 繁中 `busy.check` 有 `gone`(新忙碌指示範本第一次實機確認);全是 `not_appeared` 就查範本。
- [ ] 沒有 `busy.check result=timeout` 誤停;有的話查當時是否真的斷線。
- [ ] 結果寫回本票 `## Comments`,有要放寬或補勾的步驟列出來。
