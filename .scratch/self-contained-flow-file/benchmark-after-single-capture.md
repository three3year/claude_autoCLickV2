# 基準測試集 — 一範本一張圖之後（票 02 對照）

量測日期：2026-08-18
profile：`profiles/arknights`（case 已改為自帶模板圖，`benchmark/<case>/template.png`）
執行方式：`python -m subject_detection.bench profiles/arknights`
引擎組態與基準線完全相同（`match_threshold 0.6`／`verify_threshold 0.8`／
`mask_strategy multi_capture`／`scale_range [0.6, 1.5]`／`aspect_jitter 0.1`，DINOv2 已載入）。
每個 case 的模板圖＝原範本的`登錄基準張`（排序後第一張），與 app 實際執行時看到的
那一張完全相同，所以這份成績就代表使用者的真實體驗。

## 結論：**沒有退步**

| 指標 | 轉換前（票 01 基準線） | 一範本一張圖 |
|---|---|---|
| cases | 38 | 38 |
| correct | 38/38（100.0%） | **38/38（100.0%）** |
| 漏抓 misses | 0 | **0** |
| 誤判 false_alarms | 0 | **0** |
| present case 分數平均 | 0.971 | 0.972 |
| present case 分數最低 | 0.884 | 0.896 |
| absent case 最佳候選分數最高 | 0.444 | 0.438 |
| 平均單次查詢 | 722 ms | **270 ms** |

`一範本一張圖`的代價**沒有在 benchmark 上顯現**：判定一格都沒掉，present case 的
分數平均甚至微幅上升，absent case 的最佳候選分數微幅下降（也就是負例更乾淨一點）。

查詢變快到約 1/2.7，是降級的副作用：單張的梯度啟發式遮罩比雙截圖的
「不一致區排除」遮罩更寬，過`匹配門檻`的粗篩候選變少，送進驗證階段批次的
crop 數也跟著變少。

## 曝險面實際表現

票 01 點名的四類「最可能退步」的對象逐一對照：

- **f0/f1 計數文字**（`解鎖線索計數`，全套最脆弱的一格）：`f1_counter_5of7`
  0.933 → **0.908**，是全套跌幅最大的一格（-0.025），但離 `verify_threshold 0.8`
  仍有 0.108 的餘裕。`f0` 反而微升。**雙截圖對計數文字的遮罩貢獻，在這組資料上
  沒有大到跨過門檻的程度。**
- **e00–e11 半透明線索卡**：`線索1` 兩格微升（+0.004／+0.007）、`線索5` 兩格
  微降（-0.013）。互有高低，沒有系統性退步。
- **g0/g1 細粒度混淆**：0.416 → 0.415、0.255 → 0.263，基本不動。遮罩變寬鬆
  **沒有**讓混淆變嚴重。
- **b0–b7 跨組**：整體微升（`b1_crossset_基建鈴鐺` +0.042 最明顯），只有
  `b4_crossset_會客室線索` -0.011。降成純跨尺度比對後表現反而更穩。

## 這份成績的邊界（不要過度外推）

benchmark 的 38 個 case 是既有失敗案例＋補充案例，覆蓋的是`可變區`、跨組尺度、
色偏、混淆這幾類。它**沒有**覆蓋「同一元素在遊戲不同狀態下差異更大」的長尾情形——
雙截圖原本就是為那種情形準備的。所以合理的結論是：

> 已知的驗收集合上，一範本一張圖沒有可量測的代價；但把 40 個雙截圖降為單張，
> 等於放棄了對「未進 benchmark 的狀態差異」的一層保險。日後若出現特定範本
> 在某些畫面狀態下抓不到，這是第一個該懷疑的地方（引擎的 `multi_capture`
> 登錄能力保留著，並沒有移除）。

## 逐 case 對照

（present case 的分數是驗證階段相似度；absent case 是最佳候選的粗篩分數。
兩者不同尺度，只在同一 case 的前後比較才有意義。）

| case | expected | 前 verdict | 後 verdict | 前 score | 後 score | 差 |
|---|---|---|---|---|---|---|
| a0_sameset_返回 | present | correct | correct | 0.990 | 0.989 | -0.001 |
| a1_sameset_基建鈴鐺 | present | correct | correct | 1.000 | 1.000 | +0.000 |
| a2_sameset_信用購買 | present | correct | correct | 1.000 | 1.000 | +0.000 |
| a3_sameset_好友列表 | present | correct | correct | 1.000 | 1.000 | +0.000 |
| a4_sameset_天bar首頁 | present | correct | correct | 1.000 | 1.000 | +0.000 |
| a5_sameset_採購信用領取 | present | correct | correct | 0.966 | 0.965 | -0.001 |
| b0_crossset_返回 | present | correct | correct | 0.976 | 0.977 | +0.002 |
| b1_crossset_基建鈴鐺 | present | correct | correct | 0.919 | 0.961 | +0.042 |
| b2_crossset_每日線索 | present | correct | correct | 0.955 | 0.971 | +0.015 |
| b3_crossset_製造站加速 | present | correct | correct | 0.989 | 0.992 | +0.004 |
| b4_crossset_會客室線索 | present | correct | correct | 0.959 | 0.948 | -0.011 |
| b5_crossset_線索3 | present | correct | correct | 0.963 | 0.959 | -0.004 |
| b6_crossset_快速置入 | present | correct | correct | 0.987 | 0.987 | +0.000 |
| b7_crossset_經驗圖 | present | correct | correct | 0.961 | 0.958 | -0.003 |
| c0_scale70_返回 | present | correct | correct | 0.982 | 0.982 | -0.001 |
| c1_scale140_信用購買 | present | correct | correct | 0.993 | 0.994 | +0.001 |
| c2_scale120_基建代辦 | present | correct | correct | 0.992 | 0.990 | -0.002 |
| d0_color_返回 | present | correct | correct | 0.977 | 0.975 | -0.002 |
| d1_color_每日線索 | present | correct | correct | 0.884 | 0.896 | +0.012 |
| d2_color_好友列表 | present | correct | correct | 0.992 | 0.992 | +0.000 |
| e00_cluebg_線索1 | present | correct | correct | 0.953 | 0.957 | +0.004 |
| e01_cluebg_線索1 | present | correct | correct | 0.950 | 0.957 | +0.007 |
| e10_cluebg_線索5 | present | correct | correct | 0.969 | 0.956 | -0.013 |
| e11_cluebg_線索5 | present | correct | correct | 0.969 | 0.956 | -0.013 |
| f0_counter_0of7 | present | correct | correct | 0.986 | 0.988 | +0.001 |
| f1_counter_5of7 | present | correct | correct | 0.933 | 0.908 | -0.025 |
| g0_confuser_線索1_vs_2 | absent | correct | correct | 0.416 | 0.415 | -0.002 |
| g1_confuser_線索2_vs_3 | absent | correct | correct | 0.255 | 0.263 | +0.008 |
| g2_pick_線索1_among_2 | present | correct | correct | 0.950 | 0.957 | +0.007 |
| h0_neg_返回_board | absent | correct | correct | 0.320 | 0.316 | -0.004 |
| h1_neg_基建鈴鐺_synth | absent | correct | correct | 0.444 | 0.438 | -0.005 |
| h2_neg_採購信用頁籤_crop | absent | correct | correct | 0.379 | 0.379 | +0.000 |
| h3_neg_線索6_busy | absent | correct | correct | 0.305 | 0.328 | +0.023 |
| h4_neg_製造站收取_board | absent | correct | correct | 0.309 | 0.299 | -0.010 |
| i0_zh_返回 | present | correct | correct | 1.000 | 1.000 | +0.000 |
| i1_zh_V | present | correct | correct | 0.970 | 0.972 | +0.003 |
| i2_zh_X | present | correct | correct | 1.000 | 1.000 | +0.000 |
| j0_fullscreen_返回 | present | correct | correct | 0.946 | 0.949 | +0.003 |
