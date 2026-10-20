# app 測試手法（無頭環境驗證 GUI）

寫或改 `app/tests` 的測試、跑 app 全套測試、寫一次性 GUI 冒煙腳本前讀這份。
要驗執行器行為先加測試，不要再寫一次性腳本。

## 假件與夾具

- 假畫面／假輸入／虛擬時鐘都在 `tests/harness.py`：假件形狀＝`enginehub` 生命週期介面（`query` 回 `QueryResult`＋
  state／preload／ensure_template）——這是全 repo 唯一假件點。`vision.plan(範本名, [None, (x,y), [(x,y), (x,y,分數,比色分數)]])`
  安排「第幾次查詢才找到」，`win` 的點擊／拖曳全被換成只記事件，`等待` 走虛擬時鐘不真的睡。斷言的是事件序列
  （誰在什麼順序做了什麼），不是內部欄位。
- **背景辨識在測試裡預設當場做完**（conftest `inline_recognition` 換上 `harness.Inline`），斷言照舊緊接在操作後面；
  要看`辨識中`當下的樣子換 `app.recognition.executor = harness.Held()`，操作→斷言反灰／「辨識中…」→`release()`→
  斷言結果。「清場中查詢 0 次」用 `test_recognition.ClearProbe`（清場樁＋查詢紀錄）配 `Held`：Inline 會在清場裡
  當場做背景那段，量不出這件事。
- 流程資料夾讀寫與本流程的範本是純檔案邏輯，用暫存目錄真測不 mock（`test_flowfolder.py`、`test_flowfile.py`、
  `test_flow_open_save.py`）；斷言資料夾與快取的檔案狀態、讀回來的流程。conftest 把本機狀態資料夾與流程存放區
  換到暫存目錄（`local_paths`），測試不碰 repo 的 `.local/` 與使用者的流程。
- 測 runner 點擊邏輯時 monkeypatch `automation.runner.win.click`，不要真的動使用者滑鼠。
- 真的主視窗用 conftest 的 `main_app`（引擎不載入、不掛 F12 與視窗鉤子、不跑輪詢）。測試裡會被 `after` 排程的東西
  不要換成 lambda：Tkinter 以「id＋函式名」當 Tcl 命令名，視窗關掉後名字釋出、被下一個視窗的 lambda 重用，留著的
  after 一到就呼叫錯的函式（2026-10-13 真 App 測試偶發多一步、卡在步驟對話框）。`main_app` 用具名空函式，收尾
  取消所有未到期的 after。
- 文件對照（`test_doc_refs.py`）與格式規範對照（`test_flow_format_doc.py`）是靜態防線：改路徑、函式名、flowfile 的鍵
  時它們會紅，照訊息修文件。

## 跑測試

- 全套：根目錄 `.venv/Scripts/python -m pytest`（引擎、app、tools 三個 testpaths）。app 的 `*_ui.py`、
  `test_screen_clear_gui.py`、`test_import_slim.py` 等會開真的 Tk 視窗，全套約 90 秒。
- **會開視窗的測試在隱藏桌面跑**，不要直接在使用者桌面跑（使用者常在玩遊戲，視窗跳出來、搶焦點都算打擾，卡住還要
  他動手）：用 ctypes `CreateDesktopW("autoclick-tests", …, GENERIC_ALL)`，再 `CreateProcessW` 且
  `STARTUPINFOW.lpDesktop` 設成這個名字（Python 的 `subprocess.STARTUPINFO` 沒有 lpDesktop，要自己定義結構）。
  在那個桌面上直接跑 python，`cmd /c` 會卡死。pytest 輸出由小包裝腳本寫進檔案（`sys.stdout = sys.stderr = open(…)`
  再 `pytest.main`），外層包 timeout，跑完 `CloseDesktop`。腳本放 scratchpad，不進 repo。打包版冒煙（noUAC exe）
  也用同一招啟動。
- 沒改 app 程式碼時不必跑全套；單檔測試可以直接跑（不開視窗的那些）。
- 指令或測試超出預期 2–3 倍時間＝卡在 modal／提示／鎖，去查輸出、查程序視窗、結束它，不要空等。

## 一次性 GUI 腳本

- **開頭必須先呼叫 `tests/nodialogs.py` 的 `stub_dialogs()`**（pytest 由 conftest 自動套用）：messagebox／filedialog 是
  原生 modal，驅動時序不對觸發了驗證警告就會整個卡死等使用者來按掉；跑完印出它回傳的紀錄。會建真的 `App`
  的路徑也一樣（`test_import_slim` 的子程序探針）：啟動期的提示排在 `after(0)`、不在 `__init__` 裡擋。
- 先確認使用者在不在（idle 與前景視窗），真實輸入前驗證 `GetForegroundWindow()` 是目標視窗。
- 靶視窗子程序要自己 `SetProcessDpiAwareness`，否則它回報的 geometry 是邏輯座標，跟 mss／SetCursorPos 對不起來；
  Windows 把新視窗開在前景視窗那一台螢幕，靶視窗置頂時先關掉再啟動 app。
- 要靠子程序開靶視窗時**不能用 pid 找它的視窗**——venv 的 python.exe 啟動子程序時 pid 會轉手，`Popen.pid` 跟實際
  擁有視窗的程序不同 → 用視窗標題辨識。

## 模擬互動的限制

- GUI 畫面驗證用 PrintWindow 擷取視窗，不能只做語法檢查；**只拍靜態畫面驗證不了「互動才會執行到」的路徑**
  （勾選／選取時才跑的 callback），必須再用 `event_generate` 真的走一遍；`C["..."]` 色票鍵與 `style="..."` 樣式名的
  錯字只有執行到那一行才會炸，靠 `tests/test_ui_palette.py` 的掃描測試當靜態防線（新增色票鍵或樣式時不必改它）。
- overlay／對話框互動：`event_generate` 模擬，事件要發到綁定的 **Canvas** 而非 Toplevel。
- **虛擬事件（`<<ListboxSelect>>` 等）在未映射的視窗上不會派送**：驗互動路徑的測試要先 `deiconify()` + `update()`
  （並斷言 `winfo_viewable()`），否則 event_generate 靜靜沒事發生、退化成只驗靜態畫面（見 `test_template_panel.py`）。
- `event_generate` 模擬雙擊要連發兩次 `ButtonPress`（直接發 `<Double-Button-1>` 會報錯）；連擊計數會累積，三、四擊也
  匹配 Double 綁定，各組點擊間要等超過系統雙擊時間或換座標打斷。
- `event_generate` 合成事件**繞過 grab 路由**，驗證 grab／modal 相關行為必須用真實輸入（`win.click`／`win.drag`
  SendInput 注入）；合成事件測不出「點擊被 grab 導走」的卡死。
- modal 對話框 `grab_set` 會卡住呼叫端：操作排進 `root.after()`，用視窗標題找到那個 Toplevel、再按類別／文字找元件
  （見 `test_template_picker.py` 的 `_Driver`）；不要在生產程式碼裡留測試用的後門屬性。
- 驗證文字顏色不能用像素找色：ClearType 次像素渲染會在白字邊緣產生橙／藍彩邊造成誤判，改用 `tk.Text.bbox` 量
  字元位置、或放大截圖目視。
