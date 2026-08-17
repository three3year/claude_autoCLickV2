# 01 — 量測`基準測試集`現況成績（轉換前基準線）

**What to build:** 在動任何東西之前,把`基準測試集`在**現況**(範本仍是多截圖、仍住在 profile 範本庫)下的完整成績量出來並記錄在案,作為日後判斷「一範本一張圖」代價的唯一對照組。

票 02 會把 benchmark case 改成各自帶一張模板圖,那一刻起現況成績就只能從 git 歷史撈回來重跑。所以這張票必須排第一。

**Blocked by:** 無 — 可立即開始。

**Status:** resolved

- [x] 以現況程式碼與現況 profile 跑完整`基準測試集`,取得總體成績與`漏抓`／`誤判`細項
- [x] 成績記錄進本 feature 的 `.scratch` 目錄(含量測日期、commit、profile 名稱、每個 case 的判定與分數)
- [x] 記錄裡註明哪些 case 用到的範本是多截圖(共 40 個範本為雙截圖),這些是降級後最可能退步的對象
- [x] 不修改任何程式碼與任何 profile 資料

## Comments

- 基準線記錄於 `.scratch/self-contained-flow-file/benchmark-baseline.md`：38/38（100%），0 漏抓、0 誤判，平均 722ms/查詢。34/38 個 case 引用雙截圖範本，曝險面幾乎是整套。
