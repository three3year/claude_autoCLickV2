# 02 — 視窗協調狀態機(modal 堆疊+還原清單純邏輯)

**What to build:** 「modal 堆疊+清場還原清單」共用的純狀態機——本規格唯一新增的測試接縫。決策邏輯與 Tk 呼叫完全分離:給定事件序列(開 modal/關 modal/中途關閉非堆頂/清場進場/逐窗 map 確認/驗證逾時/清場離場),回答「此刻誰該持有 grab、該還原誰、以什麼順序、驗證失敗是否重試」。附完整 pytest,只測外部行為不驗內部呼叫順序。

**Blocked by:** None — can start immediately

**Status:** resolved

- [x] modal 堆疊語意:入堆/出堆/中途移除,grab 歸屬永遠是堆頂;堆空時歸主視窗
- [x] 還原清單語意:清場記錄「本次隱藏的視窗+wm state 快照」,離場照清單全數還原(含 zoomed),已銷毀的跳過;不在清單上的視窗一律不碰
- [x] 驗證式還原語意:逐窗「還原→等 map 確認」,逾時重試,全部可見後才進入「交還 grab、揭示」階段
- [x] 清場期間堆疊暫停奪 grab(overlay 持有),離場後 grab 歸堆頂
- [x] Combobox popdown 之類過客 grab 不入堆,消失後堆頂奪回
- [x] pytest 覆蓋上述所有情境,全綠;不依賴 GUI/Tk

## Comments
