# 基準集重製方法

Type: grilling
Status: resolved
Blocked by: 07

## Question

依 07 的盤點，決定新基準集怎麼做（ADR 0016）：
- 案例來源與答案：影格＋範本框由工具自動配對、人工審核；審核的介面是什麼（一張標了框的圖讓使用者看）。
- 案例類型配額：同款多個（pick）、比色（可按／灰）、忙碌指示在場、負樣本（圖不在）、縮放兩端（影格縮放合成？
  還是只用拾取檢查的縮放餘裕當替代）、兩個客戶端各半。
- 案例格式：沿用現在 `benchmark/<case>/`（scene、template、expected、config）還是簡化；單張範本。
- 通過標準：全部命中＋零誤判；與現在 52/52 怎麼比（不同集合不可直接比，以「新集 100%」為基線）。
- 建構工具：`tools/build_arknights_benchmark.py` 改寫成「從流程資料夾＋影片產案例」；舊 `_assets` 刪除時機。
- 引擎刪 multi_capture 要在新基準集通過之後才動（順序）。

Answer：方法＋配額＋格式＋通過標準；進 E 階段 spec。

## Answer

（2026-10-20 grilling。詞彙已更新：`CONTEXT.md`「基準測試集」補預期尺度與通過標準、新增「已知失敗」。ADR 0016 不修訂，細節以本票為準。）

### 案例來源與審核
- 工具拿四份流程**現在**的範本到**順序讀**的影格上量位置；人工判定過的資料優先（quick-place `frames_{cn,tw}.json`、
  商店 `annotations.json`／`credit-store-switch` 預期挑選、repo 內 `.scratch/v2f-rules-agent-docs/acceptance/demo2_plan.json`、
  `add5_plan.json`、`.scratch/shared-rect/acceptance/demo2_shop_plan.json`）。
- 票 07 提到暫存目錄的 4 份舊計畫已於 10/18 被清空（只剩空資料夾），不能用；其他流程靠工具重量。
- 審核：agent 逐張先審、有疑問的排前面；產生**本機 HTML 卡片頁**（範本小圖＋影格畫紅框；負樣本不畫框、標「應該沒有」），
  使用者全部看過、把錯的卡片編號回報。圖不上傳。

### 規模與配額
- 約 100 個，照類型配額每類 6–12：一般正例、同款多個（`centers`）、比色、忙碌指示、線索背景、混淆（列名互相像、灰鈕、同形卡）、
  縮放、負樣本、跨影片；簡中／繁中各半，四份流程都分到。
- **縮放**：真實影格 `resize` 合成到 ×0.85、×1.15（支援倍率範圍兩端），答案照比例換算，`expected_scale` 寫該倍率。
- **忙碌指示**：範本＝流程的忙碌指示本身；在場的幀（含疊字、淡入淡出）要找到、剛消失的幀要找不到。
- **負樣本**：只挑容易誤判的（同畫面的前後狀態、長得像的東西；例：公告關掉後找關閉鈕、售罄格找未售罄、列名 A 在只有列名 B 的畫面）。
- **跨影片**：6–8 個，同一張範本在別天錄的影片找（例：demo6 取材找 demo5 影格），兩個客戶端平分。
- **色偏不做**（同一台電腦同一螢幕；彈窗調暗背景的真實影格照收）。

### 影格規則
- 游標碰到答案框的幀一律不收（用 `quick-place-clue-check/frames.py` 的游標偵測），換一幀。
- 轉場、模糊、半透明蓋住的幀不收，除非它就是要當困難負樣本。
- 幀號只用順序讀得到的（demo4、demo6 跳轉不準）。

### 案例格式
- 沿用 `benchmark/<case>/`：`screenshot.png`＋`template.png`＋`expect.yaml`，一律單張範本。
- `expect.yaml` 新增：來源（流程、範本名、影片、幀號、案例類型；只給人看、引擎不讀）、`expected_scale`（沒寫＝1.0，
  bench 照 app 的查法傳給 `query`）、`known_failure: <原因>`。
- 引擎參數只用內建預設，`benchmark/` 不放設定檔。

### 通過標準
- 第一次跑不過的逐個判：影格不乾淨 → 換幀或刪；真的是引擎弱點 → 標 `known_failure`。
- 基線＝除已知失敗外 100% 命中＋零誤判；報表把已知失敗分開列，已知失敗變通過時提示拿掉標記。之後不得退步。
- 跟舊集 52/52 不直接比。

### 建構工具與快照
- 一次性腳本放基準集階段的 `.scratch`，不進 `tools/`；產出的案例 commit。之後加案例＝丟檔案，不重跑工具。
- 新集是快照：流程以後換範本不必跟著換，靠來源欄位查得到受影響的案例。

### 順序
1. 建新集、審核、跑到基線。
2. 同一階段內一次刪：引擎 `multi_capture`／跨拍攝對齊／`mask_strategy`、舊 `profiles/`（整個，含舊基準集與 `_assets`、`config.yaml`）、
   `tools/build_arknights_benchmark.py`、`tests/test_arknights_profile.py`；bench CLI 改指 `benchmark/`。
3. 刪完再用新集跑一次，確認沒退步。

### 何時跑
- 維持手動指令，不接進 pytest；引擎文件寫明「改引擎（門檻、模型、刪路徑）前後必跑」。
