# 04 — modal 堆疊接管 grab

**What to build:** 多個子視窗疊開(編輯對話框、比對測試結果、預覽框…)時,grab 永遠在最上層視窗手上;關掉上層後確實回到下層。`make_modal` 改走狀態機的 modal 堆疊:開窗入堆、`<Destroy>` 出堆(含中途關閉非堆頂),grab 歸堆頂,堆頂變更或堆頂視窗 `<Map>` 時奪回;「100ms×15 次逾時放棄」輪詢與 `takeover` 白名單協商廢除;`show_match_test` 的 prev 交接由堆疊語意取代;清場離場的 grab 交還改為交給堆頂。grab 轉移寫入日誌。

**Blocked by:** 02(狀態機)、03(清場離場交接點)

**Status:** resolved

- [x] 編輯對話框+比對測試結果疊開/關閉,每層都點得到該點的東西,grab 不遺失、不逾時放棄
- [x] 中途關閉非堆頂視窗,堆序與 grab 歸屬仍正確
- [x] Combobox 下拉(popdown 過客 grab)開關後 grab 回到堆頂,不誤入堆
- [x] 清場結束後 grab 歸堆頂(而非快照持有者)
- [x] 舊輪詢/takeover 機制移除,無殘留呼叫
- [x] grab/modal 行為以真實輸入(SendInput)做少量冒煙驗證——合成事件繞過 grab 路由,不算數
- [x] 既有 pytest 回歸網全綠

## Comments

2026-08-16:真實輸入冒煙以原始碼版完成(SendInput 拖曳/Esc;21 項 PASS,
含疊開/關閉/清場後 grab 歸屬)——打包版互動輪被使用者在用機器擋下,
紀錄見 issues/08。
