# 06 — 建立基線

**What to build:** 用 01 的執行器跑 `benchmark/` 新集，沒過的逐個判：影格不乾淨（游標、轉場）就換一幀或刪，真的是引擎弱點就加 `known_failure` 寫明原因。到「除已知失敗外 100% 命中＋零誤判」為止。見 [spec](../spec.md)「Implementation Decisions」的建立基線。

**Blocked by:** 05 — 使用者審卡片、修正、案例進 benchmark/

**Status:** resolved

- [x] 第一次跑的結果（總數、漏抓、誤判、各案例分數）記在本票 Comments
- [x] 每個沒過的案例寫一行判定：換幀／刪除／已知失敗＋原因
- [x] 換過的幀做一小頁卡片頁給使用者確認後才 commit（沒換幀，不適用）
- [x] 指令結束碼成功：除已知失敗外全部命中、零誤判
- [x] 基線結果（含已知失敗清單）記在本票，作為 07、08 的比對依據

## Comments

- 2026-10-21 agent：第一次跑 `python -m subject_detection.bench`：**其他案例 80/97、漏抓 9、誤判 8**，結束碼 1。各案例分數：

<details><summary>第一次跑的完整報表</summary>

```
[MISS ] busy04_cn_忙碌指示_demo6f1792                        score=0.648  207.1ms
  [MISS ] busy07_cn_忙碌指示_demo6f2655                        score=0.673  218.0ms
  [MISS ] busy10_tw_忙碌指示_demo2f2032                        score=0.199  134.7ms
  [MISS ] cluebg03_cn_来自_add3f285                          score=0.304  104.2ms
  [MISS ] cluebg08_tw_來自_add4f225                          score=0.331  108.9ms
  [FALSE] cluebg10_tw_選中3_add4f194                         score=0.880  211.4ms
  [FALSE] color02_cn_全部收取_demo6f1136                       score=0.968  239.4ms
  [FALSE] color08_tw_全部收取_add2f120                         score=0.980  263.9ms
  [FALSE] conf04_cn_标题_发电站_demo4f736                       score=0.981  252.6ms
  [FALSE] conf05_cn_标题_贸易站_demo4f608                       score=0.977  275.7ms
  [FALSE] conf06_tw_快速傳遞_demo2f1200                        score=0.966  385.1ms
  [FALSE] conf09_tw_選中1_demo2f2920                         score=0.883  179.6ms
  [FALSE] cross04_cn_最多_demo4f168                          score=0.963  259.1ms
  [MISS ] multi04_cn_来自_add3f56                            score=0.291  108.6ms
  [MISS ] multi05_cn_访问基建_demo6f1816                       score=1.000  531.9ms
  [MISS ] multi06_tw_來自_add4f80                            score=0.310  137.4ms
  [MISS ] multi08_tw_訪問基建_demo2f1824                       score=1.000  559.6ms
  [PASS ] busy01_cn_忙碌指示_demo6f283                         score=0.952  232.1ms
  [PASS ] busy02_cn_忙碌指示_demo6f296                         score=0.995  216.6ms
  [PASS ] busy03_cn_忙碌指示_demo6f308                         score=0.251  133.4ms
  [PASS ] busy05_cn_忙碌指示_demo6f1800                        score=0.976  225.3ms
  [PASS ] busy06_cn_忙碌指示_demo6f1810                        score=0.121  148.2ms
  [PASS ] busy08_tw_忙碌指示_demo2f1992                        score=0.996  228.9ms
  [PASS ] busy09_tw_忙碌指示_demo2f2009                        score=0.174  141.0ms
  [PASS ] busy11_tw_忙碌指示_demo2f2056                        score=0.999  226.0ms
  [PASS ] busy12_tw_忙碌指示_demo2f2067                        score=0.174  204.3ms
  [PASS ] cluebg01_cn_CONFIDENTIAL线索_demo6f800             score=0.996  250.6ms
  [PASS ] cluebg02_cn_来自_add3f162                          score=0.304  112.5ms
  [PASS ] cluebg04_cn_选中5_add3f191                         score=0.999  138.1ms
  [PASS ] cluebg05_cn_选中5_add3f264                         score=0.537  110.0ms
  [PASS ] cluebg06_tw_CONFIDENTIAL線索_demo2f968             score=1.000  288.5ms
  [PASS ] cluebg07_tw_來自_add4f64                           score=0.310  130.3ms
  [PASS ] cluebg09_tw_選中3_add4f93                          score=1.000  166.6ms
  [PASS ] color01_cn_全部收取_demo5f1096                       score=0.996  226.3ms
  [PASS ] color03_cn_採購_固源岩_demo6f3532                     score=0.311  133.1ms
  [PASS ] color04_cn_採購_聚酸酯_demo6f3532                     score=0.869  244.9ms
  [PASS ] color05_cn_解锁线索_demo5f1200                       score=1.000  352.6ms
  [PASS ] color06_cn_解锁线索_demo6f856                        score=0.930  334.6ms
  [PASS ] color07_tw_全部收取_add2f80                          score=1.000  278.0ms
  [PASS ] color09_tw_快速置入_demo2f968                        score=0.986  144.6ms
  [PASS ] color10_tw_採購_初級作戰記錄_demo2f3020                  score=0.975  277.6ms
  [PASS ] color11_tw_採購_招聘許可_demo2f3020                    score=0.387  191.0ms
  [PASS ] color12_tw_解鎖線索_demo2f968                        score=0.919  148.3ms
  [PASS ] conf01_cn_好友_demo5f4024                          score=0.973  380.9ms
  [PASS ] conf02_cn_线索交流结果_demo6f808                       score=0.954  394.2ms
  [PASS ] conf03_cn_选中3_demo5f432                          score=0.570   98.1ms
  [PASS ] conf07_tw_標題_貿易站_demo2f1528                      score=0.991  520.8ms
  [PASS ] conf08_tw_標題列圖示_demo2f1152                       score=0.981  216.4ms
  [PASS ] conf10_tw_標題列關閉鈕_demo3f192                       score=1.000  231.4ms
  [PASS ] conf11_tw_鈴鐺_demo3f376                           score=0.297  119.9ms
  [PASS ] cross01_cn_收取信用_demo6f3024                       score=0.955  133.9ms
  [PASS ] cross02_cn_进驻总览_demo5f920                        score=0.982  182.3ms
  [PASS ] cross03_cn_公开招募_demo5f1864                       score=0.978  147.1ms
  [PASS ] cross05_tw_傳遞線索_add2f160                         score=0.989  155.2ms
  [PASS ] cross06_tw_採購中心_demo3f792                        score=0.994  161.6ms
  [PASS ] cross07_tw_會客室_demo3f160                         score=0.995  213.4ms
  [PASS ] cross08_tw_每日線索_add4f264                         score=0.861  196.0ms
  [PASS ] multi01_cn_採購_聚酸酯_demo5f3300                     score=0.932  277.6ms
  [PASS ] multi02_cn_採購_聚酸酯_demo5f3540                     score=0.933  287.1ms
  [PASS ] multi03_cn_採購_聚酸酯_demo5f3820                     score=0.929  233.7ms
  [PASS ] multi07_tw_採購_初級作戰記錄_demo2f2880                  score=0.971  357.6ms
  [PASS ] neg01_cn_今日配给_demo5f24                           score=0.329  545.2ms
  [PASS ] neg02_cn_会客室_demo6f528                           score=0.345  100.4ms
  [PASS ] neg03_cn_传递关闭_demo5f760                          score=0.340   82.9ms
  [PASS ] neg04_cn_公告关闭_demo4f72                           score=0.336   68.7ms
  [PASS ] neg05_cn_确定_demo4f200                            score=0.423  351.9ms
  [PASS ] neg06_cn_订单交付_demo4f128                          score=0.312  128.6ms
  [PASS ] neg07_tw_主畫面設定鈕_add4f80                          score=0.272   92.9ms
  [PASS ] neg08_tw_接收線索_demo2f1104                         score=0.266   99.1ms
  [PASS ] neg09_tw_收取_demo2f736                            score=0.251   66.8ms
  [PASS ] neg10_tw_公開招募_demo3f0                            score=0.250  126.1ms
  [PASS ] neg11_tw_確定_demo3f400                            score=0.468   93.0ms
  [PASS ] neg12_tw_進駐總覽_demo3f488                          score=0.222  161.5ms
  [PASS ] pos01_cn_导航（好友基建）_demo5f3136                     score=1.000  131.6ms
  [PASS ] pos02_cn_待办铃铛_demo5f416                          score=0.993  303.3ms
  [PASS ] pos03_cn_线索_demo5f944                            score=0.999  285.8ms
  [PASS ] pos04_cn_制造中_demo4f320                           score=0.998  127.5ms
  [PASS ] pos05_cn_待辦事項_demo4f72                           score=1.000  190.6ms
  [PASS ] pos06_cn_无人机加速_demo4f208                         score=0.989  141.9ms
  [PASS ] pos07_tw_可收穫_demo2f495                           score=0.996  208.7ms
  [PASS ] pos08_tw_生產面板箭頭_demo2f705                        score=0.979  121.4ms
  [PASS ] pos09_tw_返回_demo2f620                            score=0.998  120.7ms
  [PASS ] pos10_tw_無人機加速_demo3f408                         score=0.992  170.5ms
  [PASS ] pos11_tw_訂單交付_demo3f200                          score=1.000  161.1ms
  [PASS ] pos12_tw_非工作區_demo3f504                          score=1.000  121.2ms
  [PASS ] scale01_cn_干员信赖_demo5f560_x0.85                  score=0.984  134.0ms
  [PASS ] scale02_cn_每日线索_demo6f1096_x0.85                 score=0.946  230.1ms
  [PASS ] scale03_cn_采购中心_demo6f3136_x1.15                 score=0.978  169.4ms
  [PASS ] scale04_cn_主画面设置钮_demo4f8_x1.15                  score=0.991  178.7ms
  [PASS ] scale05_cn_导航_demo4f400_x1.15                    score=0.995  171.0ms
  [PASS ] scale06_cn_干员休整_demo4f792_x0.85                  score=0.967  138.8ms
  [PASS ] scale07_tw_傳遞關閉_demo2f1199_x0.85                 score=0.985  126.2ms
  [PASS ] scale08_tw_導航_demo2f1628_x0.85                   score=0.983  139.9ms
  [PASS ] scale09_tw_線索交流彈窗_demo2f915_x1.15                score=0.988  167.1ms
  [PASS ] scale10_tw_幹員休息_demo3f728_x1.15                  score=0.987  180.0ms
  [PASS ] scale11_tw_幹員信賴_demo3f200_x1.15                  score=0.975  214.2ms
  [PASS ] scale12_tw_待辦事項_demo3f200_x0.85                  score=0.978  224.8ms

其他案例 80/97  misses: 9  false_alarms: 8  |  已知失敗 0/0  misses: 0  false_alarms: 0  |  FAIL
```

</details>

- 2026-10-21 agent：17 個沒過的逐個看過影格（範本、預期框、引擎找到的框）。**沒有一張是影格髒**（游標、轉場都沒碰到答案框），全部是引擎弱點 → 加 `known_failure`，沒換幀、沒刪案例，所以沒有換幀卡片頁要給使用者看。判定：
  - busy04／busy07／busy10 忙碌指示：淡入淡出最淡的幀，字幾乎透明，粗篩或驗證不到門檻 → 已知失敗。
  - cluebg03／cluebg08／multi04／multi06 来自／來自：粗篩先把 1920 寬畫面縮到 640 寬，小藥丸縮成約 22×11 px 被雜訊峰擠出前 20 名；同一張圖裁成答案附近小範圍就全部找到（粗篩 0.83–1.0）。app 在 114×78 小範圍找，實跑沒事 → 已知失敗。
  - multi05／multi08 訪問基建：範本連暗底一起截；好友自訂名片亮底／彩底的列驗證掉到 0.67–0.78 → 已知失敗。
  - color02／color08 全部收取、conf06 快速傳遞、cross04 最多：整顆按鈕變暗／變灰，比色（TM_CCOEFF_NORMED 扣平均除對比）分數 0.97–0.99 仍過 0.95 → 已知失敗（票 05 已預告）。
  - conf04 标题_发电站、conf05 标题_贸易站：類別標題配到左欄列名／別的類別標題，引擎分不出列名（app 靠期望位置窄帶擋）→ 已知失敗。
  - cluebg10 選中3：配到選中的 7 號圓鈕（0.88），只差中間數字 → 已知失敗。
  - conf09 選中1：配到商店底部問號鈕（0.88）→ 已知失敗。
- 2026-10-21 agent：順手修了執行器：輸出被導向（管線、檔案）時預設編碼是 cp950，簡中案例名印不出來直接崩潰（加了測試）。
- 2026-10-21 agent：**基線**（07、08 的比對依據）：
  - `其他案例 80/80  misses: 0  false_alarms: 0  |  已知失敗 0/17  misses: 9  false_alarms: 8  |  OK`，結束碼 0。
  - 已知失敗清單（17）：busy04、busy07、busy10、cluebg03、cluebg08、cluebg10、color02、color08、conf04、conf05、conf06、conf09、cross04、multi04、multi05、multi06、multi08。
