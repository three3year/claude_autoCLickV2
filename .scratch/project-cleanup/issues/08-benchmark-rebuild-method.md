# 基準集重製方法

Type: grilling
Status: open
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
