# app/ — AutoClick 自動化應用層

Windows 桌面按鍵精靈：找圖點擊＋步驟序列自動執行；辨識全走主體偵測引擎（`src/subject_detection/`）。
與使用者對話一律用繁體中文。詞彙以 [app/CONTEXT.md](CONTEXT.md) 為準（範本、流程尺度、座標基準點、
清場、辨識中…），flow.yaml 的欄位與執行語意正本是 [docs/flow-format.md](../docs/flow-format.md)。

## 架構地圖

- `app.py` 主視窗（步驟清單、範本面板、紀錄區、執行與迷你視窗）
- `enginehub.py` 引擎生命週期（載入中／就緒／失敗）＋範本清單綁定＋query／預載／單張登錄；也是 runner 的偵測接縫實作
- `recognition.py` 背景辨識入口（`辨識中`）：編輯器的辨識都在背景執行緒做
- `flowfile.py` 流程資料夾讀寫與本流程範本（`FlowTemplates`）的唯一入口
- `calibration.py` 校準與畫面倍率的全部純邏輯
- `apppaths.py` 流程存放區、本機狀態資料夾、上次開的流程（佈局寫在它的 docstring）
- `applog.py` 檔案日誌（本機狀態資料夾的 `autoclick.log`，超過 1MB 輪替一份）
- `ui_dialogs.py` 步驟編輯與各對話框、拾取入口；`ui_overlay.py` 全螢幕截圖選取層與清場；
  `ui_theme.py` 深色主題；`window_coord.py` modal 堆疊＋清場還原清單的純狀態機；`ui_grab.py` 堆疊的 Tk 執行層
- `automation/`（舊名 engine，改名避免與主體偵測「引擎」混淆）：`runner.py` 步驟執行緒；
  `findtarget.py` 找圖目標的存取、限定範圍／挑選規則／位置是否仍有匹配的唯一實作（執行器、編輯器比對測試、
  影片轉流程三處共用）；`flowcheck.py` 執行前的結構檢查；`flowdefaults.py` 步驟與流程的「沒寫＝」表；
  `flowfmt.py` 存檔座標⇄螢幕座標；`pickcheck.py` 拾取檢查；`capture.py` mss 截圖；`win.py` ctypes 滑鼠／DPI／視窗；
  `hotkey.py` F12 急停；`imgio.py` 中文路徑圖片讀寫
- 測試在 `app/tests/`，隨根目錄 pytest 一起跑；檢查指令 `tools/flow_check` 與影片轉流程 `tools/video_to_flow`
  只呼叫 app 既有的函式

## 契約（改動前先確認沒破）

**辨識單一路徑**（ADR 0002）：runner 建構時注入偵測器（`query(範本名, 搜尋區域影像, color_check, expected_scale)`
回 `QueryResult`，`matches` 是所有匹配，範本不存在丟 KeyError）。每個找圖點都經 `findtarget.find`，判定結束寫一筆
`find.target` 到 `autoclick.log`（實跑回報點錯先查它）。不要再加第二條比對路徑。

**啟動契約與 gate**（ADR 0004）：視窗先開、引擎在背景執行緒 `hub.load()`（載入失敗降級僅粗篩並 modal 警告），
「視窗可操作」≠「`引擎就緒`」。就緒前所有辨識類操作必須過 `App.engine_gate()`（modal 提示並拒絕，含 F12）——
**新增任何辨識入口都要先過這道 gate**（唯一例外是拾取檢查，見下）。範本登錄不在啟動時做：讀取流程就在背景
`範本預載`（`App.start_preload` → `hub.start_preload`，引擎沒就緒就等），按執行時 `Runner._preload` 再走一次
（已載的沿用、正在載的等它，登錄產物寫入共用 hub 的一把鎖），比對測試／即時找圖用 `hub.ensure_template()`
單張隨用。範本清單由 app 組（`App.rebind_templates` → `hub.bind`，毫秒級、不需引擎）：換流程整份換
（`hub.generation` 加一，背景預載作廢），新增／改名只丟那幾張的登錄產物。存圖後的重新綁定延後到視窗還原後
（`App._schedule_reregister`）；任何引擎查詢前先 `App.ensure_registered()`，少了這步新範本仍會 KeyError。
引擎載入起訖寫日誌（engine.load.*），啟動變慢先看它。

**開窗關鍵路徑不得 import 重量級套件**（cv2／mss／numpy／torch）：capture、imgio、ui_dialogs、ui_overlay 都是函式內
延後 import，`subject_detection` 套件頂層是 PEP 562 惰性再匯出；`app/tests/test_import_slim.py` 的子程序探針會擋。

**引擎參數**：內建預設（`default_config.yaml`）＋流程 `engine:` 段覆蓋，由 `App.engine_config` 合併（ADR 0015；
沒有編輯 UI，讀進來原樣寫回）。步驟層級沒有門檻。

**流程資料夾與唯一入口**（ADR 0014；佈局見格式規範與 `flowfile.py` 的 docstring）：yaml 的鍵、預設、排版、讀檔驗證
**全部只在 `flowfile.py`**（`flowfile.read_flow`／`write_flow`；讀檔是唯一的入口驗證），UI 與 runner 只呼叫它；
**改 `flowfile` 的讀檔或 `flowdefaults` 的預設表要同步格式規範的欄位表**（`app/tests/test_flow_format_doc.py` 會擋）。
記憶體步驟＝平面標記＋yaml 同名鍵（`type` 是開頭的鍵），讀檔與新增步驟時照 `flowdefaults` 補成完整步驟、存檔時
等於預設的不寫——執行器、編輯器不自帶預設。改動只在記憶體（`App.dirty`），按存檔才寫；關閉、開檔、新流程時
有未存檔改動問「存檔／不存／取消」（`App.confirm_discard`）。舊格式程式不讀（在用的四份已用
`.scratch/flow-folder-format/convert.py` 轉過），不要加回舊格式讀取或遷移。

**範本與引用**：本流程的範本＝`flowfile.FlowTemplates`（`App.store`）：`templates/` 的圖＋快取裡 `shots/` 的未存檔截圖
（`registered/` 是引擎的登錄產物，兩者都可重建）。
新增、重截、改名、刪除只動記憶體與快取；存檔（`store.save`）把被引用的截圖搬進 `templates/`、沒被引用的搬回
`shots/`，存完 `templates/` 正好是引用集合；重開或讀取流程時清掉 `shots/`，登錄產物留著。新流程還沒有資料夾：
截圖與登錄產物放本機狀態資料夾的「未存檔」快取，第一次存檔（選位置＋輸入流程名，同名資料夾拒絕）時搬進去。
範本名是平面名稱＝檔名，一份流程內唯一，新增與改名擋下不能當檔名的名字（`flowfile.template_name_problem`）；
**一範本一張圖**（ADR 0016，引擎給清單會報錯）。**「被引用的範本」只有 `findtarget.referenced_templates` 一份定義**
（找圖目標＋確認圖＋校準對、備用校準對、忙碌指示；`flowfile.template_refs` 包一層）：存檔、預載、收回未使用新圖、
改名都照它——新增流程層級的找圖設定時要納入，否則存檔一整理那張圖就不見。被引用卻缺圖：照樣開，彈窗加紀錄
列出缺哪幾張；執行時範本預載擋下。範本拍攝位置 `template_pos`（截圖當下的中心，相對座標基準點、流程尺度）
只有本流程自己拍的圖才有，是預設原點的備援。

**一份流程一個尺度**（ADR 0009）：座標與範本圖都是`流程尺度`；校準對＋基準距離只在 `flow.yaml` 的 `calibration`
（`calibration.flow_pair`）。量測純邏輯在 `calibration.measure`（執行器、編輯器、影片轉流程共用）。
一個倍率兩個用途：座標 ×倍率（`flowfmt.scale_px` 統一捨入），找圖時同一個倍率經 `findtarget.find(scale=…)` 當
`預期尺度`交給引擎——新增找圖入口一律走 `findtarget.find`，倍率才不會只用到一半。執行器開頭自己校準
（`Runner.start(calibration=…)` → `Runner._calibrate`，開始延遲之後、第一個動作之前）：`calibration.calibrate`
一次得出`畫面倍率`與`座標基準點`（`Runner.anchor`＝校準對第一張中心，ADR 0012），校準查詢不帶預期尺度、只在
搜尋範圍內截圖；量不到、沒有校準對、或倍率在`支援倍率範圍`外（`Calibrated.in_range`，兩端常數
`calibration.SCALE_LOW`、`SCALE_HIGH`）都零輸入結束並寫 `calibrate` 日誌；執行中不重量。編輯器量到區間外只警告、
照常拾取（ADR 0013）。改倍率相關測試時倍率要取區間內的值。
`備用校準對`（ADR 0013，`calibration.fallback_pair`／`make_fallback`）：`calibration.calibrate` 主對缺一張才量備用，
`Calibrated.used` 說用的是哪組，用備用時基準點＝備用第一張中心＋偏移×倍率，存下的座標永遠相對同一個基準點；
執行器、編輯器拾取、影片轉流程三處都只走這個入口。換校準對（`App.designate_pair`）：同一張截圖先用舊對量倍率
與舊基準點，新基準距離＝新距離 ÷ 倍率，再依新舊基準點的差平移所有存下的座標（`flowfmt.shift_flow`＋
`FlowTemplates.shift_pos`），落點不變。

**存檔座標一律是偏移量**（ADR 0012）：`相對座標`相對原點；`固定矩形`（`findtarget.limit_rect(anchor=…)`）、
`template_pos` 相對`座標基準點`，都是流程尺度。存檔裡唯一的螢幕座標是搜尋範圍本身；其他螢幕座標只在執行期或
拾取當下存在（基準點、原點、送進 `win.click` 的落點）。換算只有 `flowfmt.to_screen`／`from_screen`（與 `rect_*` 版）
一對純函式。程序啟動即 `win.set_dpi_aware()`，全程實體像素；多螢幕虛擬桌面原點可為負、配置會變，用
`win.virtual_screen()` 查當下配置，不要混入未設 DPI-aware 程序的座標。改座標相關程式碼前先確認自己在哪個座標系。

**清場中不做任何辨識；新增辨識入口一律走背景辨識**（詞彙見 CONTEXT「清場」「辨識中」）：清場只截圖與讓使用者在
覆蓋層上操作，辨識交 `App.recognition`（`recognition.Recognition`）在背景執行緒做。拾取類一律走
`ui_dialogs.measured_pick`：清場前檢查（`App.calibration_ready`）→ 清場中只截一張整個虛擬桌面的圖（`App.grab_shot`）、
派背景辨識（裁出搜尋範圍 `App.scan_frame` 量校準、推算 ◎）、叫覆蓋層（`ui_overlay.pick(shot=, pending=)`）→ 還原 →
背景沒做完就`辨識中`等它 → 收尾在介面執行緒。拾取到的座標、截下的範本（`imgio.to_flow_scale`）、拍攝位置
（`ui_dialogs.template_pos_from_shot`）都用當下的倍率與基準點換回；量不到＝不存並提示重框搜尋範圍；沒有校準對＝
需要基準點的拾取（固定矩形）擋下。◎ 可以晚到（覆蓋層 `late=`），推不出且還沒點＝改走「先點原點」或拖線
（同一次清場，不還原再隱藏）；叫覆蓋層一律經 `ui_dialogs.overlay_pick`。只量不框的（流程設定的測試與設定）清場
只截圖再 `App.recognize(title, work, done, origin)`。介面執行緒只做 `ensure_registered`、就緒檢查、modal、寫紀錄區、
填欄位、改流程資料；背景不碰 Tk（表單值、步驟清單在派工前讀好）。圖片類動作登記在 `Recognition.register`，
辨識中一律反灰——反灰規則只有那一份；登記的元件平常改可用與否走 `Recognition.want`。發起辨識的對話框用
`ui_dialogs.busy_foot` 登記底列與關閉類按鈕，做完前關不掉。**新增拾取、截圖或比對測試入口一律走 `measured_pick`**。

**拾取檢查**（`automation/pickcheck.py`，ADR 0013）：只警告不擋存檔。截範本後跑縮放餘裕（`App.check_template_scale`），
找圖設定按確定與比對測試跑唯一＋縮放餘裕（`ui_dialogs.pick_check_now`，走 `measured_pick(quiet=True)`：清場只截
搜尋範圍、檢查在主視窗以辨識中進行），固定矩形框完跑矩形餘裕。只是檢查：引擎沒就緒／量不到都不彈 modal、
不過 gate，寫一行紀錄就略過。警告經 `App.note_pick_warnings` 寫紀錄區並在範本面板標 ⚠，只活在這次編輯。
三個常數（粗篩 0.7、驗證 0.85、矩形 20%）住在模組，改它們要改 ADR 0013；影片轉流程的自我驗證
（`tools/video_to_flow/verify.py`）呼叫同一個模組。

**執行語意：哪個函式負責**（語意本身寫在格式規範）：區段在記憶體是平面標記、yaml 巢狀，`flowfile` 讀寫時轉換，
runner 用堆疊與跳轉解譯（`Runner._exec_branch`、`_break_out`、`runner.enclosing_end`）。**執行前的結構檢查只有
`automation/flowcheck.py` 一份**（`flow_errors` 一次跑完整份）：App 與 `tools/flow_check` 都只呼叫它，新增執行前會擋
的條件加在這裡。找圖 `Runner._exec_find`（三態）；原點執行期 `Runner._set_origin`（記找圖目標＋挑中的框，
`原點的圖離開`靠它），編輯器與檢查用 `runner.origin_source` 靜態推算；生效確認三種步驟同一個迴圈
`Runner._await_effect`，所有輸入都經 `Runner._input`（新增送輸入的地方也要走它）；忙碌檢查 `Runner._busy_check`。
檔案日誌：找圖確認寫 `find.target`，座標點擊／拖曳寫 `input.confirm`（沒開確認寫 `input`），勾了忙碌檢查的步驟
另寫 `busy.check`——實跑回報輸入被吃掉或步驟變慢先查這幾筆。

## 建置與部署

- **每次改完 app/ 或引擎的程式碼，收尾都要重新打包**——使用者平常用的是打包版，dist 沒跟上＝修正沒送達。
  使用者回報 UI 問題先確認是打包版還是原始碼版。
- **打包只有一條路**：`tools/build`（使用者雙擊 `app\build.bat` 也只是轉交給它；bat 只含 ASCII，有測試擋）。agent 直接跑：

  ```bash
  python tools/build            # 探測環境 → 補缺的 (.venv、依賴、torch、DINOv2 權重) → PyInstaller 覆蓋 app\dist\AutoClick
  python tools/build --dry-run  # 只印步驟清單, 不執行
  ```

  約 3–5 分鐘（第一次 clone 再加下載時間）。工具只用標準庫、用系統 Python 啟動，venv 裡的套件一律經 venv 的 Python
  子程序跑；每次都跑 pip install，靠 pip 略過已裝的。直接覆蓋舊 dist（`--noconfirm`，不保留舊版），打包前確認沒有
  AutoClick 程序在跑（exe 被鎖住時工具會提示先關掉）。有 NVIDIA 的機器裝 cu126 版 torch、交付物約 3 GB；沒有的
  CPU 版約 700 MB。改偵測或步驟順序時 `tools/tests/test_build.py` 會擋（餵事實、斷言步驟清單，不真的建 venv 或打包）。
- spec 在 `app\AutoClick.spec`：必須 onedir（onefile 啟動 4.6s 對 1.4s）；`upx=False` 明確關閉（ADR 0004——本機從未裝過
  upx，別去「補上」）。torch 與 DINOv2 隨包：spec 把本機 torch hub 快取塞進 _internal，frozen 時 app.py 以 TORCH_HOME
  指過去；spec 會 assert 快取存在，工具的下載那步（無頭建一次引擎的 Verifier）保證它成立。
- 交付物與部署方式見 README「打包與部署」。exe 以系統管理員執行（`uac_admin`）的原因：不以管理員執行時，
  對高權限視窗注入的滑鼠事件被 UIPI 無聲丟棄。
- **打包後冒煙**：UAC 會擋自動啟動，用同包的 AutoClick-noUAC.exe（共用 _internal；對高權限視窗的點擊會被丟棄，
  不作正式使用）。使用者常在玩遊戲：先查 idle（GetLastInputInfo）與前景視窗，在隱藏桌面啟動（做法見測試手法），
  開一份在用流程，看日誌有 engine.load.done 與紀錄區出現「範本就緒」。打包版的本機狀態在 `%LOCALAPPDATA%\AutoClick\`
  ——冒煙開過的流程會變成使用者下次自動開的那份，開他平常用的那份或冒煙完改回。截自家視窗用 PrintWindow；
  同標題會有兩個 Tk 頂層視窗（另一個是可點穿的覆蓋層），要挑 ex style 沒有 WS_EX_TRANSPARENT 的那個。
- 使用者資料位置的正本是 `apppaths.py` 的 docstring；原始碼執行與打包版的位置分開，agent 從原始碼冒煙
  不影響打包版。

## 已移除（不要加回去，也不用反引號寫它們）

並行執行 UI 與 ParallelRun、旋轉比對與旋轉範本工具、flood-fill 去背工具、翻新解析度工具、orig 範本鏡像、
舊 matcher、每步 threshold、profile 與整個 profiles 目錄、範本庫、工作區、步驟草稿與自動存檔、zip 流程存檔
（autoclickpack）、flow.json、多截圖範本、匯出流程包、範本資料夾層級、舊格式遷移與匯入、九宮格限定範圍、
以搜尋範圍為基準的指定點、編輯器倍率（editor_scale）、舞台接縫、按鍵步驟、絕對座標、滑鼠鍵與連點、原點矩形、
出現等候上限、補做間隔／忙碌出現等候／開始延遲／避開游標的設定（後四者是固定行為）、引擎的多張圖登錄與
mask_strategy、regrab 輪詢守護與 takeover 白名單、config.yaml 遊戲設定檔。

## 只有部分改動才需要的參考

- 改 Tk 視窗、覆蓋層、grab／modal、Windows API 或截圖、執行器輸入時序的程式碼前，讀
  [docs/agents/app-pitfalls.md](../docs/agents/app-pitfalls.md)（踩過的坑，依主題分組）。
- 寫或改 `app/tests` 的測試、跑 app 全套測試、寫一次性 GUI 冒煙腳本前，讀
  [docs/agents/app-testing.md](../docs/agents/app-testing.md)（假件點、隱藏桌面、擋對話框、模擬互動的限制）。
- 改版面、樣式、色票、對話框或清單的互動前，讀
  [docs/agents/app-ui-conventions.md](../docs/agents/app-ui-conventions.md)（已拍板的 UI 決策，不要改回去）。
