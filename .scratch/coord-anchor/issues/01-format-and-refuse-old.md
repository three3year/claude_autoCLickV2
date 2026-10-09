# 01 — 存檔新格式、舊格式拒絕開啟

**What to build:** 流程存檔與步驟草稿蓋新的存檔版本與新的座標空間標記(座標相對`座標基準點`)。開啟舊格式的存檔、舊 JSON、舊流程包時 app 拒絕開啟並說明「這是舊格式,座標基準不同」;profile 的步驟草稿是舊格式時不復原、開空白並提示。既有的舊格式遷移(螢幕→搜尋範圍座標空間、範本收進找圖目標、範本名去副檔名、丟每步門檻)隨之退場。這張只定格式與拒絕;座標的新語意由 03–06 補上。

規格:`.scratch/coord-anchor/spec.md`(需要你決定的第一項、存檔格式、接縫三)。ADR 0012 第 7 點。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 新存檔與草稿寫入新版本與新座標空間標記,寫讀往返不變。
- [x] 舊格式存檔、舊 JSON、舊流程包一律拒絕開啟,提示原因;流程清單裡的舊檔點了也是同樣提示,不當機。
- [x] 舊格式的步驟草稿不復原,開空白並提示一次。
- [x] 舊格式遷移程式碼與其測試移除或改成斷言拒絕;存檔格式測試(接縫三)綠。
- [x] `app/CONTEXT.md` 裡「匯入舊 flow 時每步 threshold 安靜丟棄」等描述舊格式遷移的字句同步更新。
- [x] app 全套 pytest 綠(在隱藏桌面跑)。

## Comments

**2026-10-09(實作)**

- 存檔格式 5、`coordSpace: anchor`;`flowfile.check_format` 任一不符就丟 `OldFormatError`(訊息「這是舊格式,座標基準不同…」)。`read`、`read_draft`、`adopt_foreign_flow`、`is_flow_file` 都過這一關;非 zip、沒有 flow.json、舊 JSON 一律同一個拒絕。`write`/`write_draft` 一律蓋新標記,收到座標相對搜尋範圍的資料直接 raise(絕不把舊比例寫成新偏移)。
- 移除:`migrate_flow`、`_migrate_step`、`flowfmt.to_region_space`、`import_legacy`、`collect_flow_templates`、`flatten_name`、`baseline_capture`、`legacy_meta_pos`、`_pack_library`,以及只靠它們活著的 `tools/convert_to_flow_files.py`。`scan_templates` 留著(enginehub 掃工作區用)。
- app:`open_flow` 檔案類型只剩 `*.autoclickpack`,舊檔點了 → `showwarning` 說明、目前流程原封不動(`_switch_workspace` 先 `load_flow` 再動狀態);`_load_autosave` 舊草稿 → 開空白、提示排 `after(0)`(不在 `__init__` 擋住——`test_import_slim` 的探針會建真的 App,第一版直接彈在使用者桌面上卡住了,已修)。repo 的 `profiles/arknights/flows/_autosave.json` 是舊格式空草稿,已刪。
- 文件:`app/CONTEXT.md` 匹配門檻條目拿掉「匯入舊 flow 時 threshold 安靜丟棄」;`app/CLAUDE.md` 格式段重寫。
- 測試:`test_flowfile`(拒絕六種舊資料、舊 JSON、非 zip、舊草稿、`write` 擋舊座標空間)、`test_flow_open_save`(開舊檔不動現況、舊草稿開空白)。app 全套在隱藏桌面 548+ passed。
