# app/ — AutoClick 自動化應用層

Windows 桌面版按鍵精靈：在畫面中找圖並點擊 + 步驟序列自動執行。
由外部專案 claude_autoClick 整包移植而來（見 ADR 0002）；本檔整併舊專案的踩坑紀錄與慣例。
與使用者對話一律用繁體中文。

## 架構

- `app.py` 主視窗；`enginehub.py`（引擎生命週期：載入中/就緒/失敗＋profile
  綁定＋query/預載/單張登錄的單一接縫，也是 runner 的偵測接縫實作）；
  `ui_theme.py` 深色主題；`ui_overlay.py` 全螢幕截圖選取層；`ui_dialogs.py` 步驟編輯對話框；
  `window_coord.py`(modal 堆疊＋清場還原清單的純狀態機)；`ui_grab.py`(堆疊的 Tk 執行層)；
  `applog.py`(檔案日誌)；
  `profile_store.py`(profile 列舉/建立/應用狀態)；`flowpack.py`(舊 flow/pack 匯入、新 pack 匯出)
- `automation/`（舊名 engine，改名避免與主體偵測「引擎」混淆）：
  `capture.py`(mss 截圖)、`win.py`(ctypes 滑鼠/DPI/視窗資訊)、`runner.py`(步驟執行緒)、
  `hotkey.py`(F12 急停)、`imgio.py`(中文路徑圖片讀寫)、
  `stage.py`(舞台介面，並行執行未移植、接縫保留)、`flowfmt.py`(存檔格式版本與遷移)
- **辨識單一路徑走主體偵測引擎**（ADR 0002）：runner 建構時注入偵測器
  （`query(範本名, 搜尋區域影像) → QueryResult`，範本不存在丟 KeyError）。
  舊 matcher 已移除，**不要再加備援比對路徑**
- **啟動契約（ADR 0004，取代舊的「啟動建 Engine＋整庫登錄」）**：視窗先開、
  引擎於背景執行緒 `hub.load()` 載入（驗證模型常駐；載入失敗降級
  coarse-only 並 modal 警告），「視窗可操作」≠「`引擎就緒`」。就緒前
  所有辨識類操作必須過 `App.engine_gate()`（modal 提示並拒絕，含 F12）；
  **新增任何辨識入口都要先過這道 gate**。範本登錄不在啟動時做：執行流程
  前由 runner `_preload`（`範本預載`）一次載齊該流程引用的範本，比對測試/
  即時找圖用 `hub.ensure_template()` 單張隨用；範本增刪改後呼叫
  `App.reload_profile()`＝`hub.refresh()` 輕量重探索（毫秒級、不需引擎），
  登錄產物於下次使用時重載。引擎載入起訖寫檔案日誌（engine.load.*）
- **開窗關鍵路徑不得 import 重量級套件**（cv2/mss/numpy/torch）：capture/
  imgio/ui_dialogs/ui_overlay 都是函式內延後 import，`subject_detection`
  套件頂層是 PEP 562 惰性再匯出——新程式碼別把這些改回頂層 import
  （`app/tests/test_import_slim.py` 的子程序探針會擋下）
- **匹配門檻在 profile `config.yaml`**（match/verify 兩關），步驟層級沒有 threshold；
  讀舊檔時 `flowpack.migrate_flow()` 會把每步 threshold 安靜丟棄、範本引用去 .png
- **範本名＝相對路徑不含副檔名**（如 `zh/X`），與引擎範本名一致。app 建立的範本
  一律目錄形式（`<name>/<name>.png`）——資料夾內「只有影像檔」會被引擎當成
  一個多截圖範本，目錄形式避開歧義；使用者把更多截圖丟進同一目錄＝自動重登錄成多截圖範本
- 流程存檔有 `coordSpace` 標記：**沒有這個鍵＝舊格式**（絕對座標是螢幕座標），載入時由
  `flowpack.migrate_flow()`（內含 `flowfmt.to_region_space()`）換算成範圍座標。
  任何讀存檔的新路徑都要記得先過這一關，否則舊檔的座標會被當成新格式而整批偏掉
- `Runner` 可注入舞台；**不注入時完全走原本的單流程路徑**，改 runner 時務必保住這條回歸線
- profile `templates/_meta.json` 只有 `pos` 鍵：各範本截圖當下的中心螢幕座標
  （相對座標預設原點的備援；上傳的範本沒有記錄；鍵＝範本名不含副檔名）。
  舊專案的 `rot` 鍵與 `_orig/` 旋轉原圖機制已隨旋轉功能移除，讀舊 meta 時安靜丟棄
- 本輪已移除（不要加回去）：並行執行 UI 與 ParallelRun、旋轉比對與旋轉範本工具、
  flood-fill 去背工具、翻新解析度工具、`_orig` 範本鏡像、舊 matcher、每步 threshold

## 建置與部署

- **每次改完 app/ 或引擎的程式碼，收尾都要重新打包**（跑 `app\build.bat`）——
  使用者平常用的是打包版，dist 沒跟上原始碼＝修正等於沒送達。
  注意 PyInstaller `--noconfirm` 會整個重建 `dist\AutoClick\`（含裡面的
  profiles），build.bat 之後會重新放入 arknights profile；不要把測試資料
  留在 dist 裡指望它活過重建
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
- 使用者資料＝`profiles/`（每個 profile 自帶 templates/flows/config），位置依 `sys.frozen`：
  exe 用 exe 旁的 `profiles/`＝使用者正式資料；從原始碼跑用 repo 根目錄的 `profiles/`
  （arknights 範本庫進版控；`flows/`、`registered/`、`_meta.json`、`app_state.json` 已 gitignore）
- 部署 = 只覆蓋 exe 與 `_internal/`；**絕不能動使用者的 profiles/**
- 使用者回報 UI 問題時，先確認截圖是部署的 exe 還是原始碼版——原始碼修正後要重新打包部署

## 座標系統（重要）

- 程序啟動即設 DPI-aware（`win.set_dpi_aware()`），全程使用**實體像素**
- 多螢幕虛擬桌面原點可為負；**螢幕配置會變動，不要寫死假設**，用 `win.virtual_screen()` 查當下配置
- mss 截圖座標 == GetWindowRect == SetCursorPos 座標，不要混入未設 DPI-aware 的程序取得的座標
- **步驟裡的座標一律是「偏移量」，沒有一個是螢幕座標**：`相對座標`相對原點、`絕對座標`相對搜尋範圍左上角。
  螢幕座標只出現在三個地方：搜尋範圍本身、`templates/_meta.json` 的 `pos`、
  以及執行期換算後送進 `win.click` 的最終落點。改動座標相關程式碼前先確認自己在哪一個座標系

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
  拖曳排序中 `render_steps` 會跳過 `_autosave` 與圖示列定位（`RowIcons.refresh` 依 `drag_guard` 早退），
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
- 清場/還原/grab 轉移/保險絲/未攔截例外都會寫進檔案日誌 `applog`（exe／repo 旁
  `autoclick.log`，超過 1MB 輪替一份 .1）——偶發 UI 問題先看日誌再推測；
  「保險絲觸發」紀錄＝機制有洞的證據，要修洞而不是靠保險絲。
  引擎載入起訖（engine.load.start/done/failed 含耗時）也在日誌，啟動變慢先看這行。
  存圖後的重新探索延後到視窗還原後才跑（`App._schedule_reregister`），任何引擎查詢
  （比對測試、執行流程、即時找圖）前必須先 `App.ensure_registered()`——它只做輕量
  重探索讓新範本進清單，登錄產物由`範本預載`/`hub.ensure_template()` 於使用當下載入
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
  這是全 repo 唯一假件點；`vision.plan(範本名, [None, (x,y)])`
  安排「第幾次查詢才找到」，`win` 的點擊/拖曳/按鍵全被換成只記事件，`等待` 走虛擬時鐘不真的睡。
  要驗執行器行為先加測試，不要再寫一次性腳本
- profile 管理與匯入/匯出是純檔案邏輯，用暫存目錄真測不 mock
  （`test_profile_store.py`、`test_flowpack.py`）
- 測試要靠子程序開靶視窗時，**不能用 pid 找它的視窗**——venv 的 `python.exe` 啟動子程序時
  pid 會轉手，`Popen.pid` 跟實際擁有視窗的程序不同 → 用視窗標題辨識
- GUI 畫面驗證：用 PrintWindow 擷取視窗，不能只做語法檢查
- **只拍靜態畫面驗證不了「互動才會執行到」的路徑**（勾選/選取時才跑的 callback），必須再用
  `event_generate` 真的走一遍；`C["..."]` 色票鍵與 `style="..."` 樣式名稱的錯字只有執行到那一行
  才會炸，靠 `tests/test_ui_palette.py` 的掃描測試當靜態防線（新增色票鍵或樣式時不必改它）
- overlay/對話框互動：`event_generate` 模擬，注意事件要發到綁定的 **Canvas** 而非 Toplevel
- modal 對話框 `grab_set` 會卡住背景測試程序 → 截圖/關閉動作放在 thread 或 `after()` 裡
- 測 runner 點擊邏輯時 monkeypatch `automation.runner.win.click`，不要真的動使用者滑鼠
- 驗證文字顏色不能用像素找色：ClearType 次像素渲染會在白字邊緣產生橙/藍彩邊造成誤判，
  改用 `tk.Text.bbox` 量字元位置、或放大截圖目視
- `event_generate` 模擬雙擊要連發兩次 `ButtonPress`（直接發 `<Double-Button-1>` 會報錯）；
  連擊計數會累積，三、四擊也匹配 Double 綁定，各組點擊間要等超過系統雙擊時間或換座標打斷
- 測試會呼叫 `render_steps` 時先 monkeypatch `App._autosave`，避免覆寫使用者的 `flows/_autosave.json`
- `event_generate` 合成事件**繞過 grab 路由**，驗證 grab/modal 相關行為必須用真實輸入
  （`win.click`/`win.drag` SendInput 注入）；合成事件測不出「點擊被 grab 導走」的卡死

## UI 慣例（已拍板的決策，不要改回去）

- 色票：背景 #0F172A、面板 #1E293B、hover 統一 `ui_theme.HOVER`(#31405A)、執行綠 #22C55E；
  截圖選取層所有線條（吸附框/拖曳框/拉線/提示框）統一藍 #2080F0
- 步驟標籤［…］顏色：找圖=info、座標點擊=accent、拖曳=#A78BFA、等待=muted、按鍵=#F472B6
  （`LABEL_COLORS`），重複/分岔標記沿用整列顏色
- 截圖選取層：游標吸附視窗/元件框（依 z-order、被遮蓋部分不吸附）、高亮區外壓黑
  （暗版底圖＋原亮度裁切圖蓋回）、有放大鏡、無十字準星；粗藍框只在 region 模式，
  point/line 拾取只有壓黑高亮
- 子視窗一律用 `ui_dialogs.make_modal()` 而非直接 `grab_set`（含點外閃爍提示）：
  它把視窗登進 modal 堆疊，grab 永遠在堆頂、關閉後自動回到下一層——
  巢狀視窗（編輯對話框＋比對測試結果）不需要也不要再手動交接 grab
- 常駐螢幕的覆蓋框（如搜尋範圍預覽）：框線畫在範圍外側（避免拍進截圖）、
  用 `win.make_click_through()` 點擊穿透、綁 root 的 `<Map>/<Unmap>` 自動顯隱
- 範本正式名稱＝相對路徑不含副檔名（可含子資料夾如 `zh/X`，meta 鍵與流程引用一律用它）；
  截圖自動命名 `tmpl_NNN`、以目錄形式存進清單目前選取的資料夾
  （清單是檔案總管式：點資料夾列展開/收合；多截圖範本顯示張數）；
  改名靠範本面板的重新命名（同步更新引用步驟，輸入含 `/` 即搬移；`clean_rel_name` 防穿越）
- 找圖搜尋範圍只有主視窗的全域設定，步驟不各自設範圍
- 座標點擊基準只有兩種：絕對座標（基準＝搜尋範圍左上角，沒設範圍就不能拾取也不能執行）、
  相對上一步（原點語意見找圖三態條目；拾取用拖線：起點=基準、終點=目標）
- 重複/分岔區段都是平面標記步驟（loop_start/end、branch_start/or/end，非巢狀資料結構），
  runner 用堆疊與跳轉解譯；區段必須完整巢狀不可交錯，執行前由 `_flow_error` 堆疊掃描擋下
- 分岔的拍板語意：每個分支開頭必須是找圖步驟＝該分支條件，執行時輪詢先找到誰走誰；
  全部逾時依條件步驟的 onNotFound 決定跳過或停止
- 找圖「找不到時」有三種：跳過（skip）／跳出目前區段（break）／停止（stop）。
  break＝跳到最內層所屬重複/分岔區段結尾之後，重複區段放棄剩餘次數（break 語意非 continue）；
  不在任何區段內＝停止流程；作為分岔條件全逾時時等同跳過
- 區段結尾（loop_end/branch_end）可設 `onBreak`：預設 continue（跳出停在本層結尾之後繼續）／
  break（因找不到而跳出抵達此處時，連外層區段一起跳出，可連續往外傳播，跳出最外層則停止流程）。
  只在「因找不到跳出」時生效，正常執行流程走到區段結尾不受影響
- 找圖 `action` 三態：click（找到就點）／none（找出現、僅等待不點）／wait_gone（等待此圖消失）。
  wait_gone 必須先看到圖至少一次、之後消失才通過；從未出現＝逾時走 `onNotFound`
  （紀錄區分「從未出現」與「仍未消失」）。「不點擊也算相對座標原點」涵蓋三態
  （wait_gone 記錄「最後看到的位置」）
- 所有會產生原點的步驟（座標點擊、找圖三態）都可勾掉 `updateOrigin`（拖曳除外，一律更新）——
  執行期（含確認補點）、拾取預設原點推算、測試選取片段檢查都遵守同一設定。拾取推算遇到找圖時：
  只有「直接前一個原點步驟就是找圖」才即時找畫面（備援截圖位置）；途中隔了相對點擊/拖曳＝
  畫面已被切換，一律用「截圖當下位置」重現剛剛拾取的點，不可信任畫面殘留同圖
- 找圖點擊有「點擊後確認生效」`confirm`：none／gone（點到目標圖消失）／appear（點到確認圖
  `confirmTemplate` 出現）。沒生效會自動補點、用步驟的逾時/重試當預算，逾時仍未生效走
  `onNotFound`。appear 的確認圖採截圖即時存檔（不走主範本的 pending，取消對話框圖仍會留下）。
  **只有 click 才有意義**：選任一種「不點擊」時，整列用 `sync_click_opts` 自動隱藏、且存為 none
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
  執行前即擋下（`_fragment_origin_error`）
