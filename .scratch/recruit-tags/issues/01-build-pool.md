# 01 — 建池:抓資料表、建招募池快照

**What to build:** 使用者下一個 CLI 子命令,工具就把台服(arkntools tw-for-maa)或國服(Kengxxiao zh_CN)的 gacha_table 與 character_table 抓下來,整理成一份`招募池`快照存進工具自己的資料夾;快照裡有 29 個`招募標籤`(tagId、字面)、招募池每位幹員的稀有度與標籤集合、來源網址、上游最後提交時間、抓取時間。招募池裡有名字對不上幹員表時,建池失敗並把全部對不上的名字列出來,不產生快照。建池本身是入口函式(給兩份 JSON 與伺服器,回快照),抓取只在 CLI 裡。台服快照這張票就產出並進版控。

規格:`.scratch/recruit-tags/spec.md`「招募池快照」節與「位置與邊界」節。

**Blocked by:** None — can start immediately

**Status:** done (2026-10-10)

- [x] 新工具套件在 `tools/` 下成立(與影片轉流程並列),有 `__main__` 與 CLI;只用引擎公開 API 的紀律寫在套件說明裡。
- [x] 建池入口函式:輸入 gacha_table、character_table 的 JSON 與伺服器,輸出快照;標籤取自 `gachaTags`(29 個,含「元素」),成員取自 `recruitDetail`(去標記、按行、以「 / 」拆名),幹員標籤集合 = `tagList` + 職業標籤 + 位置標籤(英文列舉 → tagId 對照寫在工具裡),稀有度 `TIER_n` → n。
- [x] 名字對不上或欄位缺時失敗,錯誤訊息列出全部對不上的名字;grill 時台服 156 個名字有 1 個對不上,查明原因並在票的 Comments 記下。
- [x] CLI 子命令抓兩服資料表並寫快照;快照記來源網址、上游最後提交時間(GitHub API)、抓取時間、伺服器。
- [x] 台服快照產出並進版控;國服快照不在本票(等使用者給資料再說,但子命令要能抓)。
- [x] 測試(`tools/tests/`)以迷你 gacha_table/character_table 片段打建池入口:正常建池、名字對不上時失敗並列名、職業/位置轉標籤正確、快照帶來源與時間、兩服字面不同但 tagId 一致。

## Comments

**2026-10-10 實作完成**(`tools/recruit_tags/`:`pool.py` 建池、`fetch.py` 抓取、`cli.py` 的 `fetch-pool`)

- 台服快照 `tools/recruit_tags/data/pool_tw.json`:29 標籤、156 位幹員,上游更新 2026-10-08T08:12:56Z。
  國服 `fetch-pool --server cn` 實測可建(160 位),快照不進版控(等使用者給簡中資料)。
- **grill 時對不上的 1 個名字是「奧斯塔」**:台服 recruitDetail 寫「奧」(U+5967),character_table 寫「奥」
  (U+5965)——上游字面不一致。`pool.py` 的 `NAME_ALIASES` 記這筆對照;往後再有對不上的照樣失敗並列名。
- 實作時另外發現、規格沒寫到的三件事:
  1. 獅蠍、森蚺、異客在 character_table 另有同名的召喚物條目(`trap_…`)→ 只認 `char_` 開頭的條目。
  2. 5★/6★ 的 tagList 裡**沒有**資深/高資標籤 → 照 arkntools 依星數補(5★ 加 14、6★ 加 11),
     不補的話含高資/資深的組合永遠沒有候選。
  3. 國服 recruitDetail 用字面的 `\n` 與 `\r\n` 換行;gachaTags 另有 1012/1013(男性/女性干员),
     不是招募標籤 → 只收 tagId 1–29。
- 快照一個標籤 / 一位幹員一行,新幹員進池時 diff 好讀。
