# 基準測試集 — 轉換前基準線（票 01）

量測日期：2026-08-17
commit：`edcdfcef305116ff9abd4139e974852e83a114b5`（docs: 專案改名為 claude_autoClickV2）
profile：`profiles/arknights`（repo 開發用資料；範本仍住在 profile 範本庫、仍是多截圖）
執行方式：`python -m subject_detection.bench profiles/arknights`
引擎組態：`match_threshold 0.6`、`verify_threshold 0.8`、`mask_strategy multi_capture`、
`scale_range [0.6, 1.5]`、`aspect_jitter 0.1`；驗證模型 DINOv2 已載入（torch 2.13.0+cpu，
非 coarse-only）。

## 總體成績

| 指標 | 值 |
|---|---|
| cases | 38 |
| correct | 38/38（100.0%） |
| 漏抓 misses | 0 |
| 誤判 false_alarms | 0 |
| 平均單次查詢 | 722 ms |
| 最慢單次查詢 | 2036 ms（`e01_cluebg_線索1`） |

**滿分。** 這是唯一的對照組：票 02 把 case 改成自帶單張模板圖之後，任何一格從
correct 掉出來，都是「一範本一張圖」的直接代價。

## 多截圖範本的曝險面

profile 範本庫共 87 個範本，其中 **40 個是雙截圖**（與 spec 記載的數字一致）。
**34/38** 個 case 引用的是雙截圖範本 —— 降級後幾乎整套 benchmark 都在曝險面上。

雙截圖範本清單（登錄基準張＝排序後第一張；降級後保留它、丟棄另一張）：

| 範本 | 兩張截圖 | 降級後保留 |
|---|---|---|
| `cn/V` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/X` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/信用購買` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/基建代辦` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/基建換班` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/基建換班非工作區` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/基建鈴鐺` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/天bar公開招募` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/天bar好友` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/天bar採購中心` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/天bar首頁` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/好友列表` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/好友基建` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/好友基建下一位` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/封面齒輪` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/快速置入` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/採購信用基準點` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/採購信用頁籤` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/採購信用領取` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/會客室交流結束` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/會客室等待交流` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/會客室線索` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/會客室飛機(取消用)` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/每日好友線索` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/每日好友線索領取` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/每日線索` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/每日線索領取` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/經驗圖` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/線索1` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/線索2` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/線索3` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/線索5` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/線索6` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/線索7` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/製造站加速` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/製造站加速確定` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/製造站收取` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/製造站數量最多` | `cn.png`, `翻新.png` | `cn.png` |
| `cn/返回` | `cn.png`, `翻新.png` | `cn.png` |
| `zh/解鎖線索計數` | `a.png`, `b.png` | `a.png` |

最可能退步的對象，是遮罩靠「截圖之間不一致」才算得出`可變區`的那幾類：

- **f0/f1 計數文字**（`zh/解鎖線索計數`，兩張 `a`/`b` 是 0/7 與 3/7 兩種計數）：雙截圖唯一的用途就是把數字
  位置標成可變區。降成單張後只剩單張梯度啟發式，`f1_counter_5of7` 是全套最脆弱的一格。
- **e00/e01/e10/e11 半透明線索卡**（`cn/線索1`、`cn/線索5`）：卡片透出的底色隨背景而變，
  兩張不同背景的截圖本來能把透出區排除。
- **g0/g1 細粒度混淆**（線索卡互相排除）：遮罩變寬鬆＝更容易把 2 號當 1 號，誤判風險。
- **b0–b7 跨組**：同一範本的 `cn` 與 `翻新` 兩張，降級後只剩 `cn`，查「貼上翻新截圖」的場景
  就變成純跨尺度比對。

## 逐 case 明細

| case | 範本 | 多截圖 | expected | verdict | score |
|---|---|---|---|---|---|
| a0_sameset_返回 | cn/返回 | yes | present | correct | 0.990 |
| a1_sameset_基建鈴鐺 | cn/基建鈴鐺 | yes | present | correct | 1.000 |
| a2_sameset_信用購買 | cn/信用購買 | yes | present | correct | 1.000 |
| a3_sameset_好友列表 | cn/好友列表 | yes | present | correct | 1.000 |
| a4_sameset_天bar首頁 | cn/天bar首頁 | yes | present | correct | 1.000 |
| a5_sameset_採購信用領取 | cn/採購信用領取 | yes | present | correct | 0.966 |
| b0_crossset_返回 | cn/返回 | yes | present | correct | 0.976 |
| b1_crossset_基建鈴鐺 | cn/基建鈴鐺 | yes | present | correct | 0.919 |
| b2_crossset_每日線索 | cn/每日線索 | yes | present | correct | 0.955 |
| b3_crossset_製造站加速 | cn/製造站加速 | yes | present | correct | 0.989 |
| b4_crossset_會客室線索 | cn/會客室線索 | yes | present | correct | 0.959 |
| b5_crossset_線索3 | cn/線索3 | yes | present | correct | 0.963 |
| b6_crossset_快速置入 | cn/快速置入 | yes | present | correct | 0.987 |
| b7_crossset_經驗圖 | cn/經驗圖 | yes | present | correct | 0.961 |
| c0_scale70_返回 | cn/返回 | yes | present | correct | 0.982 |
| c1_scale140_信用購買 | cn/信用購買 | yes | present | correct | 0.993 |
| c2_scale120_基建代辦 | cn/基建代辦 | yes | present | correct | 0.992 |
| d0_color_返回 | cn/返回 | yes | present | correct | 0.977 |
| d1_color_每日線索 | cn/每日線索 | yes | present | correct | 0.884 |
| d2_color_好友列表 | cn/好友列表 | yes | present | correct | 0.992 |
| e00_cluebg_線索1 | cn/線索1 | yes | present | correct | 0.953 |
| e01_cluebg_線索1 | cn/線索1 | yes | present | correct | 0.950 |
| e10_cluebg_線索5 | cn/線索5 | yes | present | correct | 0.969 |
| e11_cluebg_線索5 | cn/線索5 | yes | present | correct | 0.969 |
| f0_counter_0of7 | zh/解鎖線索計數 | yes | present | correct | 0.986 |
| f1_counter_5of7 | zh/解鎖線索計數 | yes | present | correct | 0.933 |
| g0_confuser_線索1_vs_2 | cn/線索1 | yes | absent | correct | 0.416 |
| g1_confuser_線索2_vs_3 | cn/線索2 | yes | absent | correct | 0.255 |
| g2_pick_線索1_among_2 | cn/線索1 | yes | present | correct | 0.950 |
| h0_neg_返回_board | cn/返回 | yes | absent | correct | 0.320 |
| h1_neg_基建鈴鐺_synth | cn/基建鈴鐺 | yes | absent | correct | 0.444 |
| h2_neg_採購信用頁籤_crop | zh/採購信用頁籤 | - | absent | correct | 0.379 |
| h3_neg_線索6_busy | cn/線索6 | yes | absent | correct | 0.305 |
| h4_neg_製造站收取_board | cn/製造站收取 | yes | absent | correct | 0.309 |
| i0_zh_返回 | zh/返回 | - | present | correct | 1.000 |
| i1_zh_V | zh/V | - | present | correct | 0.970 |
| i2_zh_X | zh/X | - | present | correct | 1.000 |
| j0_fullscreen_返回 | cn/返回 | yes | present | correct | 0.946 |

（`絕對分數`的意義：present case 是驗證階段相似度、absent case 是最佳候選的分數；
兩者都不是同一個尺度，只在同一 case 的前後比較才有意義。）

## 沒有動到的東西

程式碼與 profile 資料一行未改；`registered/` 的登錄產物沿用既有快取。
