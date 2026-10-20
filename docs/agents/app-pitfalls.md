# app 踩過的坑（不要再犯）

改 Tk 視窗、覆蓋層、grab／modal、Windows API 或截圖、執行器輸入時序的程式碼前讀這份；
改哪一塊只讀那一組。契約與架構在 `app/CLAUDE.md`。

## Tk、grab、覆蓋層

- 讓出螢幕截圖一律用 `ui_overlay.screen_clear`（可巢狀：只有最外層真正隱藏／還原、自動列舉視窗、進場記錄
  「本次隱藏的清單＋zoomed 快照」、離場照清單逐窗驗證式還原——deiconify 後等 `<Map>` 確認真的畫出來、逾時重試，
  全部可見後 grab 交還 modal 堆疊堆頂，ADR 0003）。絕不要自行 withdraw／deiconify 做截圖；多段拾取流程
  （預查＋拾取、兩段拖曳拾取）要整段包在同一個 session 裡，避免「還原→再隱藏」空窗的映射競態（歷來卡死的根源）。
- grab 歸屬由 `window_coord`（純狀態機）＋`ui_grab`（Tk 執行層）的 modal 堆疊統一管理：堆頂變更或堆頂 `<Map>` 時
  事件驅動奪回。建立會打掉 grab 的 Toplevel（如預覽框）後呼叫 `ui_grab.apply_grab()` 交還堆頂即可。
- 清場期間不得以已隱藏的視窗為 parent 彈 messagebox（會隱形卡死等確認）——檢查類提示一律在進入清場前做。
- 在清場裡校準、找圖、`hub.ensure_template` 就是「視窗不見」，還原後在介面執行緒做就是「全白」：辨識只能在背景
  （契約「清場中不做任何辨識」）。
- 隱藏視窗去截圖前，視窗必須已用 `ui_theme.disable_transitions()` 停用 DWM 淡出動畫，否則截圖有半透明殘影。
- 覆蓋層生命週期：point／預設原點 line 拾取必須在「放開」才完成（按下就結束會把 release 事件漏給底下的應用程式）；
  完成時不能立刻銷毀覆蓋層（等待用 `wait_variable` 非 `wait_window`）——它是本程序的前景視窗，先銷毀會把前景讓給
  剛被自動點擊的遊戲，`focus_force` 被 Windows 拒絕、還原視窗被壓住看似消失。還原全程在覆蓋層後面完成
  （不做 topmost 脈衝、最大化直接 `state("zoomed")` 映射），最後才銷毀＝一次揭示，靠 focus_force 帶起整個擁有鏈蓋過遊戲。
- `__init__` 期間 root 可能已 `winfo_viewable`，置頂子視窗（預覽框等）必須等 root 首次 `<Map>` 後才能建立，
  否則主視窗首次顯示會被干擾。
- Combobox 下拉開啟時 popdown 視窗持有 grab，此時 `grab_current()` 會 `KeyError: 'popdown'`（popdown 不在 Python
  widget 樹）→ 一律用 `ui_theme.safe_grab_current()`。
- ttk clam 主題 `style.map` 是先匹配者優先：`("active", ...)` 要排在 `("readonly", ...)` 之前，否則 hover 不反白；
  元件沒設 map 時 clam 預設 hover 是亮灰色。clam 按鈕焦點環是虛線且點擊後殘留，`focuscolor` 要與各狀態背景同色
  才會隱形。clam 的 `TButton` 有預設 `width -11`（最小 11 字元寬），緊湊小按鈕的樣式要設 `width=0`。
- 對話框元件必須以 `_Rows.add()` 回傳那列的 `.frame` 為 parent，建在 body 上再 pack 進去會被 frame 蓋住。
- 大截圖餵 `tk.PhotoImage` 要用 PPM P6 bytes（`f"P6 {w} {h} 255 ".encode() + rgb.tobytes()`），PNG＋base64 慢 6 倍以上。
- `SegListbox` 大量列重建要用 `load()` 批次（單次 state 切換），不要逐列 `append`；拖曳排序中 `render_steps` 會跳過
  圖示列定位（`RowIcons.refresh` 依 `drag_guard` 早退），放開時補一次——拖曳效能問題先查「每次 motion 做了什麼重活」
  （磁碟寫入／強制版面同步），不是先改演算法。
- 清場／還原／grab 轉移／保險絲／未攔截例外都寫進 `autoclick.log`——偶發 UI 問題先看日誌再推測；
  「保險絲觸發」紀錄＝機制有洞的證據，要修洞而不是靠保險絲。

## Windows API 與截圖

- `cv2.imread`／`imwrite` 在 Windows 讀寫不了中文路徑 → 一律用 `automation/imgio.py`。
- `scan_region=None` 在 `Runner`／`capture.grab` 的語意是**全螢幕**，所以任何算出搜尋範圍的程式碼，「算不出範圍」
  都不能用 `None` 表達——會讓限制範圍的防護在最壞情況下變成完全不設限。
- `user32` 中回傳視窗代號的函式（`GetAncestor`…）一定要宣告 `restype = wintypes.HWND`，預設的 `c_int` 會截斷／
  符號延伸，代號比對就會失準。
- `SetWinEventHook` 不能掛在 Tk 主執行緒（會與 pynput 鉤子執行緒衝突造成 GIL 崩潰）→ 用 `win.watch_window_changes()`：
  專屬執行緒自帶 GetMessage 迴圈，callback 用 `root.after` 轉回 UI 執行緒。
- mss 截圖座標 == GetWindowRect == SetCursorPos 座標（都是實體像素）；截螢幕會截到蓋在上面的視窗，要截自家視窗的
  內容用 PrintWindow（`PW_RENDERFULLCONTENT`）。
- 使用者的主要目標（明日方舟）跑在 Google Play Games 裡：程序名 client.exe、視窗標題就是「Google Play Games」。
  簡中／繁中兩個客戶端的 exe 與標題**完全相同**，任何「靠標題或程序名自動找出是哪個視窗」的設計都分不出誰是誰
  → 目標視窗只能由使用者手動指定（搜尋範圍）。

## 執行器與輸入

- 點擊沒反應的排查順序（不是座標問題，落點已有 e2e 驗證 0px 誤差）：(1) 目標程式有防作弊（明日方舟 PC 版的 ACE
  核心驅動）或以更高權限執行時，注入的滑鼠事件被無聲丟棄（UIPI）；(2) `SetCursorPos` 瞬移不產生輸入事件、hover
  未生效——`win.click` 已內建補送 hover 事件＋保險停留，移開游標用 `win.park`（補事件，遊戲才知道游標走了）。
  調整點擊時序一律改 `win.click` 參數，不要在 runner 加 sleep。
- 固定等待是最後手段：執行器的等法都是輪詢（找圖、生效確認、忙碌檢查），新機制也用輪詢，不要加固定秒數。
- 校準對主對該選**遊戲畫面內**兩張固定圖；標題列圖示＋關閉鈕量到的倍率偏小 0.4%，只當備用（CONTEXT「校準對」）。
