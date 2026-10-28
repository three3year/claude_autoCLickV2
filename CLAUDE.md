# claude_autoClickV2

## Agent skills

### Issue tracker

Issues 與規格以本地 markdown 存於 `.scratch/<feature>/`。See `docs/agents/issue-tracker.md`.

### Triage labels

使用預設五標籤(needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix)。See `docs/agents/triage-labels.md`.

### Domain docs

兩個 context(引擎/自動化應用),入口為根目錄 `GLOSSARY-MAP.md`;引擎詞彙在根目錄
`GLOSSARY.md`、應用詞彙在 `app/GLOSSARY.md`,ADR 共用 `docs/adr/`。See `docs/agents/domain.md`.`CONTEXT.md` 為舊名(v1.3.0 前的 skill),現僅轉址到 `GLOSSARY.md`。

## 引擎基準測試集

改引擎(`src/subject_detection/`:門檻、模型、粗篩、遮罩、刪路徑)**前後都要跑**
`.venv/Scripts/python -m subject_detection.bench`。改前先跑一次當基線,改後結果要跟基線一致:
結束碼 0,已知失敗可以變少、不能變多;已知失敗這次通過了就拿掉它的 `known_failure`。
新的失敗情境加一個案例資料夾進 `benchmark/`。案例格式、指令選項、收案標準見 README「基準測試集」。
