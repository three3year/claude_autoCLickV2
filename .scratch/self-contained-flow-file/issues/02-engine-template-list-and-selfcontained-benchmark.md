# 02 — 引擎改收`範本清單`,benchmark case 自帶模板圖

**What to build:** 引擎不再假設有一個範本庫目錄可掃。改由呼叫端交付**範本清單**(範本名 → 圖檔路徑)與`登錄產物`的存放位置;舊的「掃目錄」入口整條移除,不保留兩條讀取路徑。

`基準測試集`同步脫鉤:每個 case 資料夾自己帶一張模板圖,不再以範本名引用外部範本庫。新增 case 仍然是「丟檔案就好、不改程式」。

app 這一側**使用者完全無感**:hub 內部把現有的 profile 範本庫掃成一份清單餵給引擎即可,UI 與執行期行為一個字不變。

**這張票會量出「一範本一張圖」的實際代價**——case 改成單張模板圖之後,與票 01 的基準線一對照就知道退步多少。這是整個 feature 最早能拿到這個答案的時間點;若退步到不可接受,回頭重議「一範本一張圖」的成本在此最低。

**Blocked by:** 01

**Status:** resolved

- [x] 引擎新增「收範本清單」的入口,並移除舊的掃目錄入口(引擎、bench、測試全數改走新入口,不留相容層)
- [x] 引擎參數設定的載入方式不變(仍讀 profile 設定檔覆蓋預設值)
- [x] `登錄產物`的存放位置由呼叫端指定,引擎不再自己決定要寫到 profile 的哪個子目錄
- [x] benchmark case 契約改為自帶模板圖;38 個既有 case 全數轉好,轉換取原範本的登錄基準張(排序後第一張)
- [x] bench 工具不再需要 profile 的範本庫就能跑完整套
- [x] 引擎既有測試(登錄產物重用、遮罩、多尺度、驗證)改走新入口後全綠,斷言不變
- [x] `enginehub` 對外形狀(生命週期狀態、`query`／`preload`／`ensure_template`)一個字不改;內部改成組清單餵引擎
- [x] app 端的執行器回歸網與 `enginehub` 測試**一行不改**即通過
- [x] 跑完整`基準測試集`,與票 01 的基準線逐項對照,把差異記錄進 `.scratch`;退步明顯時在票上留言請使用者確認是否續行

## Comments

- 引擎改收`範本清單`：`Engine.load_templates(templates, config, artifacts_dir)`＋`library.make_library`；`Profile`／`load_profile_dir`／`discover_templates` 整條移除，掃目錄改由呼叫端負責（app 走 `flowfile.scan_templates`，engine 測試走 `synth.template_list`）。
- benchmark case 契約改為自帶 `template.png`（38 個全轉好，`expect.yaml` 不再有 `template:` 引用）；登錄產物存 `benchmark/_registered/`。原範本庫搬到 `benchmark/_assets/templates/`（benchmark 自己擁有輸入，builder 工具照舊可重跑）。
- `enginehub` 對外形狀不變，`test_enginehub.py` 一行未改即通過；執行器回歸網全綠。
- 成績對照記錄於 `.scratch/self-contained-flow-file/benchmark-after-single-capture.md`：**38/38（100%）沒有退步**，present case 分數平均 0.971→0.972，查詢從 722ms 降到 270ms。跌幅最大的 `f1_counter_5of7`（0.933→0.908）離門檻仍有 0.108 餘裕 → 不需要回頭重議「一範本一張圖」。
