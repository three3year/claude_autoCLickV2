# 01 — 檔案日誌基礎

**What to build:** 應用有一個輕量檔案日誌:固定位置(exe／repo 旁)、大小上限或輪替從簡。未攔截例外(`report_callback_exception`)除了寫進主視窗紀錄面板外一併落地到日誌檔——主視窗隱藏時錯誤不再無聲消失。後續票(清場、堆疊、保險絲)的事件都寫進同一份日誌。

**Blocked by:** None — can start immediately

**Status:** resolved

- [x] 日誌模組可供各處呼叫,寫入帶時間戳的單行紀錄
- [x] 未攔截例外同時出現在紀錄面板與日誌檔
- [x] 日誌檔位置固定可預期,大小有上限(輪替或截斷從簡即可)
- [x] 打包版(frozen)與原始碼執行都寫得到日誌

## Comments
