# app/ — AutoClick 自動化應用層

Windows 桌面版按鍵精靈：在畫面中找圖並點擊 + 步驟序列自動執行。
由外部專案 claude_autoClick 整包移植而來（見 ADR 0002）；本檔整併舊專案的踩坑紀錄與慣例。
與使用者對話一律用繁體中文。

## 架構

- `app.py` 主視窗；`enginehub.py`（引擎生命週期：載入中/就緒/失敗＋`範本清單`
  綁定＋query/預載/單張登錄的單一接縫，也是 runner 的偵測接縫實作）；
  `ui_theme.py` 深色主題；`ui_overlay.py` 全螢幕截圖選取層；`ui_dialogs.py` 步驟編輯對話框；
  `window_coord.py`(modal 堆疊＋清場還原清單的純狀態機)；`ui_grab.py`(堆疊的 Tk 執行層)；
  `applog.py`(檔案日誌)；`apppaths.py`(流程預設位置、本機狀態資料夾、上次開的流程)；
  `flowfile.py`(**流程資料夾讀寫與本流程範本的唯一入口**，見下)；
  `calibration.py`(校準與畫面倍率的全部純邏輯，見下)
- `automation/`（舊名 engine，改名避免與主體偵測「引擎」混淆）：
  `capture.py`(mss 截圖)、`win.py`(ctypes 滑鼠/DPI/視窗資訊)、`runner.py`(步驟執行緒)、
  `hotkey.py`(F12 急停)、`imgio.py`(中文路徑圖片讀寫)、
  `flowfmt.py`(存檔座標⇄螢幕座標的換算與換校準對時的平移)、
  `flowdefaults.py`(**一張「沒寫＝」表**：步驟與流程的預設值只在這裡)、
  `findtarget.py`(`找圖目標`：步驟上找圖目標的存取函式，與限定範圍/挑選規則/位置是否仍有
  匹配的唯一實作——執行器、編輯器比對測試、影片轉流程自我驗證三處共用，行為一致由此保證)
- **辨識單一路徑走主體偵測引擎**（ADR 0002）：runner 建構時注入偵測器
  （`query(範本名, 搜尋區域影像, color_check, expected_scale) → QueryResult`，`matches`
  是所有匹配，範本不存在丟 KeyError；ADR 0007）。每個找圖點都經 `findtarget.find` 執行一個找圖目標，
  判定結束時寫一筆 `find.target` 到 `autoclick.log`（實跑回報點錯時先查它）。
  舊 matcher 已移除，**不要再加備援比對路徑**
- **啟動契約（ADR 0004，取代舊的「啟動建 Engine＋整庫登錄」）**：視窗先開、
  引擎於背景執行緒 `hub.load()` 載入（驗證模型常駐；載入失敗降級
  coarse-only 並 modal 警告），「視窗可操作」≠「`引擎就緒`」。就緒前
  所有辨識類操作必須過 `App.engine_gate()`（modal 提示並拒絕，含 F12）；
  **新增任何辨識入口都要先過這道 gate**。範本登錄不在啟動時做：讀取流程就在背景
  `範本預載`（`App.start_preload` → `hub.start_preload`，引擎沒就緒就等就緒；ADR 0004 後記），
  按執行時 runner `_preload` 再走一次（已載的沿用、正在載的等它——登錄產物的寫入共用
  hub 的一把鎖），比對測試/即時找圖用 `hub.ensure_template()` 單張隨用。`範本清單`由 app
  組（`App.rebind_templates` → `hub.bind(本流程的範本, 引擎參數, 登錄產物位置, changed)`，
  毫秒級、不需引擎）：換流程整份換（`hub.generation` 加一，背景預載作廢），新增／改名只丟那幾張的
  登錄產物。引擎載入起訖寫檔案日誌（engine.load.*）
- **開窗關鍵路徑不得 import 重量級套件**（cv2/mss/numpy/torch）：capture/
  imgio/ui_dialogs/ui_overlay 都是函式內延後 import，`subject_detection`
  套件頂層是 PEP 562 惰性再匯出——新程式碼別把這些改回頂層 import
  （`app/tests/test_import_slim.py` 的子程序探針會擋下）
- **匹配門檻是引擎參數**（match/verify 兩關）：引擎內建預設（`default_config.yaml`）＋流程
  `engine:` 段的覆蓋，由 `App.engine_config` 合併（ADR 0015；app 不提供編輯 UI，讀進來原樣寫回）。
  步驟層級沒有 threshold
- **一份流程＝一個資料夾（ADR 0014）**：`flow.yaml`＋`templates/<範本名>.png`＋`.cache/`
  （`registered/` 登錄產物、`shots/` 還沒存檔的截圖，都可重建）；影片轉流程產的另有
  `交付報告/`（app 不讀不寫）。yaml 的鍵、預設、排版、讀檔驗證**全部只在 `flowfile.py`**
  （`read_flow`／`write_flow`；讀檔是唯一的入口驗證，錯誤指出步驟編號與鍵），UI 與 runner 只呼叫它。
  記憶體步驟＝平面標記＋yaml 同名鍵（`type` 是 yaml 開頭的鍵），讀檔與新增步驟時照
  `flowdefaults` 補成完整步驟、存檔時等於預設的不寫——執行器、編輯器不自帶預設
  - **沒有 profile、工作區、步驟草稿、自動存檔**：改動只在記憶體（`App.dirty`），按存檔才寫；
    關閉、開檔、新流程時有未存檔改動問「存檔／不存／取消」（`App.confirm_discard`）
  - **本流程的範本＝`flowfile.FlowTemplates`**（`App.store`）：`templates/` 的圖＋`.cache/shots/`
    的未存檔截圖。新增、重截、改名、刪除只動記憶體與快取；存檔（`store.save`）把被引用的截圖搬進
    `templates/`、沒被引用的搬回 `shots/`，存完 `templates/` 正好是引用集合。重開或讀取流程時清掉
    `shots/`，登錄產物留著（過期自己重算）。新流程還沒有資料夾：截圖與登錄產物放本機狀態資料夾的
    「未存檔」快取，第一次存檔（選位置＋輸入流程名，已有同名資料夾就拒絕）時搬進去
  - **範本名是平面名稱＝檔名**（沒有資料夾層級），一份流程內唯一；新增與改名時擋下不能當檔名的
    名字（`flowfile.template_name_problem`）；**一範本一張圖**
    （多截圖範本已退場，引擎的 `multi_capture` 能力保留但 app 不再產生）
  - **「被引用的範本」只有 `findtarget.referenced_templates` 一份定義**（步驟的找圖目標＋確認圖＋
    流程層級的校準對、備用校準對、忙碌指示；`flowfile.template_refs` 包一層）：存檔、範本預載、對話框
    收回未使用新圖、改名（`rename_template_refs`）都照它。
    新增流程層級的找圖設定時要一併納入，否則存檔一整理那張圖就不見
  - 被引用卻缺圖：照樣開，彈窗加執行紀錄列出缺哪幾張；執行時範本預載擋下
- 舊格式（`.autoclickpack` zip、flow.json、步驟草稿）**程式不讀**：在用的四份已用一次性腳本
  轉成流程資料夾（`.scratch/flow-folder-format/convert.py`）。不要加回舊格式讀取或遷移
- **一份流程一個尺度（ADR 0009，取代 0005；詞彙見 app/CONTEXT.md「尺度與畫面倍率」）**：
  座標與範本圖都是`流程尺度`；`校準對`＋`基準距離`在 flow.yaml 的 `calibration`
  （`calibration.flow_pair`），別處不存任何校準資料。量測純邏輯在 `calibration.py`
  （`measure`，執行器、編輯器、影片轉流程共用）。慣例與坑：
  - **一個倍率兩個用途**：座標 ×倍率（`flowfmt.scale_px` 統一捨入），找圖時同一個倍率經
    `findtarget.find(scale=…)` 當`預期尺度`交給引擎（只掃它附近 5 格）。新增找圖入口一律走
    `findtarget.find`，倍率才不會只用到一半
  - 執行器開頭自己校準（`runner.start(calibration=…)` → `_calibrate`，延遲之後、第一個動作
    之前）：`calibration.calibrate` 一次得出`畫面倍率`與`座標基準點`（`Runner.anchor`，校準對
    第一張的中心，ADR 0012）；校準查詢**不帶**預期尺度、只在搜尋範圍內截圖；量不到或沒有
    校準對＝零輸入結束，寫 `calibrate` 日誌。抖動內貼齊 1（`snap_identity`）——倍率 1 時座標
    原樣、網格對準 1.0。執行中不重量。量到`支援倍率範圍`外（`Calibrated.in_range`，兩端常數只在
    `calibration.SCALE_LOW/HIGH`）也零輸入結束（`calibrate` 日誌 `result=out_of_range`）；編輯器
    （「校準」鈕、`measured_pick`）量到區間外只在紀錄區警告、照常拾取（ADR 0013 決策 1）。
    改倍率相關測試時倍率要取區間內的值，否則執行器不跑
  - **存下的座標一律相對座標基準點、流程尺度**：`固定矩形`（`within`，
    `findtarget.limit_rect(anchor=…)`）、範本拍攝位置 `template_pos`。換算只有 `flowfmt.to_screen`／
    `from_screen`（與 `rect_*` 版）一對純函式，執行器、編輯器、換算工具都用它
  - **編輯器沒有跨操作保存的倍率或基準點**（`App.editor_scale` 已移除）：每次拾取都走
    `ui_dialogs.measured_pick`——清場前檢查（`App.calibration_ready`）、清場中先
    `App.calibrate_frame()` 在這次的截圖上量基準點與倍率，再做拾取，清場後提示。拾取到的座標
    （`flowfmt.from_screen`／`_unscale`）、截下的範本（`imgio.to_flow_scale`）、拍攝位置
    （`ui_dialogs.template_pos_from_shot`）都用當下的值換回；量不到＝不存並提示重框搜尋範圍；
    沒有校準對＝需要基準點的拾取（固定矩形）擋下，只依原點的照常（倍率 1）。
    **新增拾取、截圖或比對測試入口一律走 `measured_pick`**。「校準」鈕只量測顯示，不存任何值
  - 換校準對（`App.designate_pair`）：同一張截圖先用舊對量倍率與舊基準點（量不到就拒絕），
    新基準距離＝新距離 ÷ 倍率，再依新舊基準點的差把所有存下的座標平移
    （`flowfmt.shift_flow`＋`FlowTemplates.shift_pos`），落點不變；有備用對時偏移跟著重算
  - **`備用校準對`（ADR 0013）**：校準資料可帶 `fallback {pair, baseline, offset}`
    （`calibration.fallback_pair`／`make_fallback`）。`calibration.calibrate` 先量主對、主對缺一張才量
    備用對，`Calibrated.used` 說用的是哪一組；用備用對時基準點＝備用第一張中心＋偏移×倍率
    （`fallback_anchor`／`fallback_offset` 互逆），存下的座標永遠相對同一個基準點。執行器、編輯器拾取、
    影片轉流程三處都只走這個入口；執行紀錄印一行警告照跑；主備皆無才不執行。主對該選**遊戲畫面內**兩張
    固定圖，標題列圖示＋關閉鈕量到的倍率偏小 0.4%，只當備用
  - **`拾取檢查`（`automation/pickcheck.py`，ADR 0013）**：只警告不擋存檔。截範本後跑縮放餘裕
    （`App.check_template_scale`，用拾取當下的整張截圖 `frame`，等 `ensure_registered` 後查）、找圖設定
    按確定與比對測試跑唯一＋縮放餘裕（`ui_dialogs.pick_check_now`，走 `measured_pick(quiet=True)`：
    只是檢查，引擎沒就緒／校準量不到都不彈 modal、不過 `engine_gate`，寫一行紀錄區就略過——這是
    「新增辨識入口要過 gate」的唯一例外）、固定矩形框完跑矩形餘裕。警告經
    `App.note_pick_warnings` 寫紀錄區並在範本面板標 ⚠（`pick_warnings()`，只活在這次編輯，不進存檔）。
    三個常數（粗篩 0.7、驗證 0.85、矩形 20%）住在模組，改它們要改 ADR 0013。影片轉流程的自我驗證
    （`tools/video_to_flow/verify.py`）呼叫同一個模組，不要另寫一套判斷
- 範本拍攝位置（flow.yaml 的 `template_pos`）：截圖當下的中心，**相對座標基準點、流程尺度**
  （相對座標預設原點的備援；◎ 退用它時以當下基準點換回螢幕）。編輯中住在 `FlowTemplates`，
  存檔只寫被引用的範本。
  **只有本流程自己拍的圖有 pos**——跨流程複製進來與從磁碟上傳的沒有（比對測試找到時補記）；
  沒有校準對時拍的圖也沒有（沒有基準點）
- 已移除（不要加回去）：並行執行 UI 與 ParallelRun、旋轉比對與旋轉範本工具、
  flood-fill 去背工具、翻新解析度工具、`_orig` 範本鏡像、舊 matcher、每步 threshold、
  **profile、範本庫、工作區、步驟草稿與自動存檔、zip 流程存檔、多截圖範本、匯出流程包、範本資料夾層級**、
  舊格式遷移與匯入、九宮格限定範圍、以搜尋範圍為基準的指定點、編輯器倍率、舞台接縫、
  按鍵步驟、絕對座標、滑鼠鍵與連點、原點矩形、出現等候上限、補做間隔／忙碌出現等候／開始延遲／
  避開游標的設定（後四者是固定行為）

## 建置與部署

- **每次改完 app/ 或引擎的程式碼，收尾都要重新打包**（跑 `app\build.bat`）——
  使用者平常用的是打包版，dist 沒跟上原始碼＝修正等於沒送達。
  PyInstaller `--noconfirm` 會整個重建 `dist\AutoClick\`；打包版資料夾裡沒有使用者資料，
  不必先搬東西出來
- 打包：`app\build.bat`（PyInstaller onedir，spec 在 `app\AutoClick.spec`），
  交付物＝整個 `app\dist\AutoClick\` 資料夾（目標機免 Python、免網路）。
  打包必須用 **onedir**，不要 onefile（onefile 啟動 4.6s，onedir 1.4s）；
  UPX 明確關閉（`upx=False`，ADR 0004——本機其實從未裝過 upx.exe，
  `upx=True` 一直是靜默 no-op，別因為看到設定就去裝 upx「補上」它）
- torch CPU 與 DINOv2 隨包：spec 把本機 torch hub 快取（repo 程式碼＋權重）塞進
  `_internal\torch_home\hub`，frozen 時 app.py 以 `TORCH_HOME` 指過去。
  **打包前先從原始碼跑過一次 app**（讓 hub 快取存在，spec 會 assert）
- exe 以系統管理員執行（`--uac-admin`，開啟時跳 UAC）——UIPI 限制：不以管理員執行時，
  對較高權限視窗注入的滑鼠事件會被系統無聲丟棄；部署後的自動啟動測試會被 UAC 擋住——
  自動化冒煙改用同包的 `AutoClick-noUAC.exe`（共用 `_internal`；點擊會被高權限視窗
  丟棄，不作正式使用）
- 使用者資料（`apppaths.py`）：流程資料夾預設在 `%USERPROFILE%\AutoClick\`（開檔與第一次存檔的
  對話框從這裡開）；本機狀態資料夾（`state.json` 只記上次開的流程、`autoclick.log`、「未存檔」快取）
  打包版在 `%LOCALAPPDATA%\AutoClick\`、原始碼執行在 repo 的 `.local\`（gitignore）——agent 冒煙開過的
  流程不會變成打包版下次自動開的那份。repo 的 `profiles/arknights/` 只剩引擎基準測試集
- 部署 = 整個 `AutoClick\` 資料夾換掉
- 使用者回報 UI 問題時，先確認截圖是部署的 exe 還是原始碼版——原始碼修正後要重新打包部署

## 座標系統（重要）

- 程序啟動即設 DPI-aware（`win.set_dpi_aware()`），全程使用**實體像素**
- 多螢幕虛擬桌面原點可為負；**螢幕配置會變動，不要寫死假設**，用 `win.virtual_screen()` 查當下配置
- mss 截圖座標 == GetWindowRect == SetCursorPos 座標，不要混入未設 DPI-aware 的程序取得的座標
- **存檔裡的座標一律是「偏移量」，沒有一個是螢幕座標**：`相對座標`相對原點、
  `固定矩形`、範本拍攝位置 `template_pos` 都相對`座標基準點`（ADR 0012）。螢幕座標只出現在兩個地方：
  搜尋範圍本身（存檔裡唯一的螢幕座標，要先有它才找得到基準點）、以及執行期或拾取當下才有的值
  （基準點、原點、送進 `win.click` 的最終落點）。改動座標相關程式碼前先確認自己在哪一個座標系
- 步驟偏移量是`流程尺度`（ADR 0009）：偏移量 → 螢幕像素要 ×`畫面倍率`再加基準點
  （`flowfmt.to_screen`，runner `_sc`、預設原點推算）；螢幕像素 → 偏移量要減基準點、反除倍率
  （`flowfmt.from_screen`、拾取 `_unscale`）。倍率 1、基準點 (0,0) 時兩者都是恆等

## 踩過的坑（不要再犯）

- `cv2.imread/imwrite` 在 Windows 讀寫不了中文路徑 → 一律用 `automation/imgio.py`
- `scan_region=None` 在 `Runner`／`capture.grab` 的語意是**全螢幕**，所以任何算出搜尋範圍的
  程式碼，「算不出範圍」都不能用 `None` 表達——會讓限制範圍的防護在最壞情況下變成完全不設限
- `user32` 中**回傳視窗代號的函式**（`GetAncestor`…）一定要宣告 `restype = wintypes.HWND`，
  預設的 `c_int` 會截斷／符號延伸，代號比對就會失準
- 使用者的主要目標（明日方舟）跑在 **Google Play Games** 裡：程序名 `client.exe`、視窗標題就是
  `Google Play Games`。cn／zh 兩個客戶端的 exe 與標題**完全相同**，任何「靠標題或程序名自動
  找出是哪個視窗」的設計都分不出誰是誰 → 目標視窗只能由使用者手動指定
- 點擊沒反應的排查順序（不是座標問題，落點已有 e2e 驗證 0px 誤差）：(1) 目標程式有防作弊
  （如明日方舟 PC 版的 ACE 核心驅動）或以更高權限執行時，注入的滑鼠事件會被無聲丟棄（UIPI）;
  (2) `SetCursorPos` 瞬移不產生輸入事件、hover 未生效——`win.click` 已內建補送 hover 事件＋保險停留，
  調整點擊時序一律改 `win.click` 參數，不要在 runner 加 sleep
- 大截圖餵 `tk.PhotoImage` 要用 **PPM P6 bytes**（`f"P6 {w} {h} 255 ".encode() + rgb.tobytes()`），
  PNG+base64 慢 6 倍以上
- 隱藏視窗去截圖前，視窗必須已用 `ui_theme.disable_transitions()` 停用 DWM 淡出動畫，
  否則截圖有半透明殘影
- ttk clam 主題 `style.map` 是先匹配者優先：`("active", ...)` 要排在 `("readonly", ...)` 之前，
  否則 hover 不反白；元件沒設 map 時 clam 預設 hover 是亮灰色
- clam 按鈕焦點環是虛線且點擊後殘留，`focuscolor` 要與各狀態背景同色才會隱形
- `SetWinEventHook` 不能掛在 Tk 主執行緒（會與 pynput 鉤子執行緒衝突造成 GIL 崩潰）→
  用 `win.watch_window_changes()`：專屬執行緒自帶 GetMessage 迴圈，callback 用 `root.after` 轉回 UI 執行緒
- `SegListbox` 大量列重建要用 `load()` 批次（單次 state 切換），不要逐列 `append`；
  拖曳排序中 `render_steps` 會跳過圖示列定位（`RowIcons.refresh` 依 `drag_guard` 早退），
  放開時補一次——拖曳效能問題先查「每次 motion 做了什麼重活」（磁碟寫入/強制版面同步），不是先改演算法
- 讓出螢幕截圖一律用 `ui_overlay.screen_clear`（可巢狀：只有最外層真正隱藏/還原、自動列舉視窗、
  進場記錄「本次隱藏的清單＋zoomed 快照」、離場照清單逐窗驗證式還原——deiconify 後等 `<Map>`
  確認真的畫出來、逾時重試，全部可見後 grab 交還 modal 堆疊堆頂，見 ADR 0003）——
  絕不要自行 withdraw/deiconify 做截圖；多段拾取流程（預查＋拾取、兩段拖曳拾取）要整段包在
  同一個 session 裡，避免「還原→再隱藏」空窗的映射競態（歷來卡死的根源）。
  grab 歸屬由 `window_coord`（純狀態機）＋`ui_grab`（Tk 執行層）的 modal 堆疊統一管理：
  堆頂變更或堆頂 `<Map>` 時事件驅動奪回，舊 `_regrab` 輪詢守護與 takeover 白名單已廢除；
  建立會打掉 grab 的 Toplevel（如預覽框）後呼叫 `ui_grab.apply_grab()` 交還堆頂即可。
  清場期間不得以已隱藏的視窗為 parent 彈 messagebox（會隱形卡死等確認）——檢查類提示
  一律在進入清場前做（見 `_region_origin`）
- 清場/還原/grab 轉移/保險絲/未攔截例外都會寫進檔案日誌 `applog`（本機狀態資料夾的
  `autoclick.log`，超過 1MB 輪替一份 .1）——偶發 UI 問題先看日誌再推測；
  「保險絲觸發」紀錄＝機制有洞的證據，要修洞而不是靠保險絲。
  引擎載入起訖（engine.load.start/done/failed 含耗時）也在日誌，啟動變慢先看這行。
  存圖後的重新綁定延後到視窗還原後才跑（`App._schedule_reregister`），任何引擎查詢
  （比對測試、執行流程、即時找圖）前必須先 `App.ensure_registered()`——它只把新範本交進
  範本清單，登錄產物由`範本預載`/`hub.ensure_template()` 於使用當下載入
  （ADR 0004），少了這步新範本仍會 KeyError
- 覆蓋層生命週期：point／預設原點 line 拾取必須在「放開」才完成（按下就結束會把 release 事件
  漏給底下的應用程式）；完成時不能立刻銷毀覆蓋層（等待用 `wait_variable` 非 `wait_window`）——
  它是本程序的前景視窗，先銷毀會把前景讓給剛被自動點擊的遊戲，`focus_force` 被 Windows 拒絕、
  還原視窗被壓住看似消失。還原全程在覆蓋層後面完成（不做 topmost 脈衝、最大化直接
  `state("zoomed")` 映射），最後才銷毀＝一次揭示，靠 focus_force 帶起整個擁有鏈蓋過遊戲
- 對話框元件必須以 `add_row()` 回傳的 frame 為 parent，建在 body 上再 pack 進去會被 frame 蓋住
- `__init__` 期間 root 可能已 `winfo_viewable`，置頂子視窗（預覽框等）必須等 root 首次 `<Map>`
  後才能建立，否則主視窗首次顯示會被干擾
- ttk clam 的 `TButton` 有預設 `width -11`（最小 11 字元寬），做緊湊小按鈕時樣式要設 `width=0`
- Combobox 下拉開啟時，其 popdown 視窗持有 grab，此時呼叫 `grab_current()` 會
  `KeyError: 'popdown'`（popdown 不在 Python widget 樹）→ 一律用 `ui_theme.safe_grab_current()`

## 測試手法（無頭環境驗證 GUI）

- 執行器邏輯有 pytest 回歸網（`app/tests/`，隨根目錄 `pytest` 一起跑）。
  假畫面／假輸入／虛擬時鐘都在 `tests/harness.py`：假件形狀＝`enginehub`
  生命週期介面（`query` 回 `QueryResult`＋state/preload/ensure_template）——
  這是全 repo 唯一假件點；`vision.plan(範本名, [None, (x,y), [(x,y), (x,y,分數,比色分數)]])`
  安排「第幾次查詢才找到」，`win` 的點擊/拖曳全被換成只記事件，`等待` 走虛擬時鐘不真的睡。
  要驗執行器行為先加測試，不要再寫一次性腳本
- 流程資料夾讀寫與本流程的範本是純檔案邏輯，用暫存目錄真測不 mock
  （`test_flowfolder.py`、`test_flowfile.py`、`test_flow_open_save.py`）；
  斷言的是**資料夾與快取的檔案狀態、讀回來的流程**，不是內部欄位。conftest 把本機狀態資料夾與
  流程預設位置換到暫存目錄（`local_paths`），測試不碰 repo 的 `.local/` 與使用者的流程
- 測試要靠子程序開靶視窗時，**不能用 pid 找它的視窗**——venv 的 `python.exe` 啟動子程序時
  pid 會轉手，`Popen.pid` 跟實際擁有視窗的程序不同 → 用視窗標題辨識
- GUI 畫面驗證：用 PrintWindow 擷取視窗，不能只做語法檢查
- **只拍靜態畫面驗證不了「互動才會執行到」的路徑**（勾選/選取時才跑的 callback），必須再用
  `event_generate` 真的走一遍；`C["..."]` 色票鍵與 `style="..."` 樣式名稱的錯字只有執行到那一行
  才會炸，靠 `tests/test_ui_palette.py` 的掃描測試當靜態防線（新增色票鍵或樣式時不必改它）
- overlay/對話框互動：`event_generate` 模擬，注意事件要發到綁定的 **Canvas** 而非 Toplevel
- modal 對話框 `grab_set` 會卡住背景測試程序 → 截圖/關閉動作放在 thread 或 `after()` 裡
- **一次性 GUI 冒煙腳本開頭必須先呼叫 `tests/nodialogs.py` 的 `stub_dialogs()`**（pytest 由
  conftest 自動套用）：messagebox/filedialog 是原生 modal，驅動時序不對觸發了驗證警告
  （例如「固定矩形還沒框選」）就會整個卡死、等使用者來按掉；跑完印出它回傳的紀錄。
  **會建真的 `App` 的路徑也一樣**（`test_import_slim` 的子程序探針）：啟動期的提示
  （自動開上次流程時的缺圖警告）排在 `after(0)`、不在 `__init__` 裡擋
- 測 runner 點擊邏輯時 monkeypatch `automation.runner.win.click`，不要真的動使用者滑鼠
- 驗證文字顏色不能用像素找色：ClearType 次像素渲染會在白字邊緣產生橙/藍彩邊造成誤判，
  改用 `tk.Text.bbox` 量字元位置、或放大截圖目視
- `event_generate` 模擬雙擊要連發兩次 `ButtonPress`（直接發 `<Double-Button-1>` 會報錯）；
  連擊計數會累積，三、四擊也匹配 Double 綁定，各組點擊間要等超過系統雙擊時間或換座標打斷
- **虛擬事件（`<<ListboxSelect>>` 等）在未映射的視窗上不會派送**：驗互動路徑的測試
  要先 `deiconify()` + `update()`（並斷言 `winfo_viewable()`），否則 event_generate
  靜靜沒事發生、退化成只驗靜態畫面（見 `test_template_panel.py`）
- 驗 modal 對話框的互動：對話框會卡住呼叫端，所以把操作排進 `root.after()`，
  用視窗標題找到那個 Toplevel、再按類別/文字找元件（見 `test_template_picker.py`
  的 `_Driver`）；不要在生產程式碼裡留測試用的後門屬性
- `event_generate` 合成事件**繞過 grab 路由**，驗證 grab/modal 相關行為必須用真實輸入
  （`win.click`/`win.drag` SendInput 注入）；合成事件測不出「點擊被 grab 導走」的卡死

## UI 慣例（已拍板的決策，不要改回去）

- 色票：背景 #0F172A、面板 #1E293B、hover 統一 `ui_theme.HOVER`(#31405A)、執行綠 #22C55E；
  截圖選取層所有線條（吸附框/拖曳框/拉線/提示框）統一藍 #2080F0
- 步驟標籤［…］顏色：找圖=info、座標點擊=accent、拖曳=#A78BFA、等待=muted
  （`LABEL_COLORS`），重複/分岔標記沿用整列顏色
- 截圖選取層：游標吸附視窗/元件框（依 z-order、被遮蓋部分不吸附）、高亮區外壓黑
  （暗版底圖＋原亮度裁切圖蓋回）、有放大鏡、無十字準星；粗藍框只在 region 模式，
  point/line 拾取只有壓黑高亮
- 子視窗一律用 `ui_dialogs.make_modal()` 而非直接 `grab_set`（含點外閃爍提示）：
  它把視窗登進 modal 堆疊，grab 永遠在堆頂、關閉後自動回到下一層——
  巢狀視窗（編輯對話框＋比對測試結果）不需要也不要再手動交接 grab
- 常駐螢幕的覆蓋框（如搜尋範圍預覽）：框線畫在範圍外側（避免拍進截圖）、
  用 `win.make_click_through()` 點擊穿透、綁 root 的 `<Map>/<Unmap>` 自動顯隱
- 範本正式名稱＝**平面名稱＝檔名**（沒有資料夾層級）；截圖自動命名 `tmpl_NNN`（自動產生的名字
  經 `flowfile.clean_name` 清成能當檔名）；使用者改名輸入不能當檔名的字元＝擋下說明，不靜靜改寫。
  主視窗的範本面板列的是**本流程的範本**（平面清單，沒有資料夾），改名靠面板的重新命名
  （`flowfile.rename_template_refs` 同步改寫所有引用含`確認圖`、校準對、忙碌指示，撞名自動加序號）
- **選範本一律走 `ui_dialogs.pick_template`**：左側樹狀「新加入／本流程／流程預設位置底下的
  其他流程資料夾」（其他流程只列檔名，預覽才讀那一張）、可從磁碟挑 PNG、可現場
  截圖；**按確定才複製進本流程**，取消時檔案系統完全沒有變化。`確認圖`走同一個
  對話框（取消時這次加進來、最後沒被引用的圖一併丟棄）——舊的「截圖即時存檔、取消對話框圖仍留下」
  語意已經改掉，別再加回去
- 找圖搜尋範圍只有主視窗的全域設定，步驟不各自設範圍
- 拾取相對座標用拖線：起點=基準、終點=目標
- 找圖選「不點擊」「等待消失」時，生效確認與忙碌檢查的勾選列隨 `sync_click_opts` 隱藏、存為沒勾

## 執行語意（正本在 `docs/flow-format.md`）

區段、分岔怎麼選分支、`on_fail`／`on_break`、找圖三態、原點與 `update_origin`、生效確認與補做、
忙碌檢查的等法都寫在 [docs/flow-format.md](../docs/flow-format.md)（寫流程的 agent 讀那份），這裡只留
**哪個函式負責**。**改 `flowfile` 的讀檔或 `flowdefaults` 的預設表要同步格式規範的欄位表**
（`app/tests/test_flow_format_doc.py` 會擋）。

- 區段在記憶體是平面標記（repeat_start/end、branch_start/or/end），flow.yaml 是巢狀，`flowfile` 讀寫時轉換；
  runner 用堆疊與跳轉解譯（`_exec_branch`、`_break_out`、`_enclosing_end`）。
- **執行前的結構檢查只有 `automation/flowcheck.py` 一份**：`section_error`（成對、不交錯、分支開頭是找圖、
  「或」在分岔內）、`no_origin`、`origin_leaves_bad`、`confirm_next_bad`、`busy_check_bad`；`flow_errors` 一次跑完
  整份。App（`_flow_error`、`_fragment_origin_error`…）與檢查指令 `tools/flow_check` 都只呼叫它——新增執行前
  會擋的條件加在這裡，兩邊一起生效
- 找圖：`Runner._exec_find`（三態）、`_exec_branch`；每個找圖點都經 `findtarget.find`
- 原點：執行期 `Runner._set_origin`（找圖目標＋挑中的框＋查詢時的原點，`原點的圖離開`靠它）；編輯器與
  檢查用 `runner.origin_source` 靜態推算（拾取預設原點推算、測試選取片段檢查都遵守 `update_origin`）。拾取推算
  遇到找圖時：只有「直接前一個原點步驟就是找圖」才即時找畫面（備援截圖位置）；途中隔了相對點擊/拖曳＝
  畫面已被切換，一律用「截圖當下位置」
- 生效確認：三種步驟走同一個迴圈 `Runner._await_effect`（找圖點擊 `_confirm_click`）；所有輸入都經
  `Runner._input`（記上次輸入時間，補做間隔看它），新增送輸入的地方也要走它。座標點擊/拖曳的補做落點以
  第一次輸入前的原點計算，原點生效後才更新
- 忙碌檢查：`Runner._busy_check`（`BUSY_APPEAR`、`BUSY_GONE_CAP`）；找圖等待共用 `WaitClock`、逾時不看忙碌指示；
  補做的門在確認沒生效的那一輪用同一張截圖查（`_busy_seen`）
- 檔案日誌：找圖的確認寫 `find.target`（含 `busy_delay`＝補做被忙碌延後秒數），座標點擊/拖曳寫 `input.confirm`，
  沒開確認的寫一行 `input`（落點）；勾了忙碌檢查的步驟在輸入那筆之後、確認那筆之前寫一筆 `busy.check`
  （`result`＝not_appeared/gone/timeout、`waited`＝從送出起的秒數、`polls`、看到時的 `picked`）。
  實跑回報輸入被吃掉或步驟變慢時先查這幾筆

## UI 慣例（續）

- 窄視窗塞不下的按鈕列用 `HScrollStrip`（橫向捲動容器，滾輪橫向捲動）：步驟鈕列釘選
  「新增步驟」保證可見、其餘捲動；次要小按鈕用 `Small.TButton`（`width=0` 原因見 clam 坑）
- 步驟清單是 `SegListbox`（tk.Text 實作、相容 Listbox 介面，不是 Listbox）——拍板：
  選取只加背景不變文字色、│ 連線依隸屬區塊顏色（重複=warn、分岔=info）、
  號碼欄用 tab 定位點對齊（比例字型下位數不同會讓縮排右偏）
- 步驟多選拖曳：把手按在已選取列上＝整組拖曳（不連續選取會併攏成連續區塊、相對順序不變），
  按列內文仍縮成單選；新增步驟插在選取列（收合區段算整段）之後，無選取才接在最後
- 「測試選取」＝只執行清單選取片段（跳選補滿頭尾、收合算整段、一律單次），共用
  `start_run(steps=…, test=True)` 與 `_flow_error(steps)`；迷你視窗摘要對照 `_run_steps`
  （實際在跑的清單），不是 `self.steps`；片段內相對座標步驟若在任何原點來源之前，
  執行前即擋下（`_fragment_origin_error` → `flowcheck.no_origin`）
