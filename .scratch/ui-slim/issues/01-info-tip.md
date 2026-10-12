# 01 — ⓘ 說明提示元件

**What to build:** 主視窗「搜尋範圍」旁出現一個 ⓘ，滑鼠移上去才顯示說明；原本那行常駐的「（所有找圖步驟與比對測試都只在此範圍內找圖）」消失。ⓘ 是共用元件，後面的流程設定、步驟編輯器、其他對話框都用它（先做好，讓後面的票好做）。

見 spec「說明文字規則」。原型做法見 `prototype/main-layout` 分支的 `info_tip`（標籤＋懸停時開一個無邊框置頂的提示框，移開關掉）。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 共用 ⓘ 元件放在 UI 共用模組，背景色可配合所在面板；提示文字自動換行、不超出螢幕
- [x] 滑鼠移入顯示、移出消失；提示框所在的視窗關閉時跟著消失，不留孤兒視窗；不搶焦點、不打斷 modal 堆疊的 grab
- [x] 主視窗搜尋範圍那行常駐說明換成 ⓘ（說明文字精簡成使用時才需要的資料）
- [x] 測試（App 接縫）：ⓘ 存在、懸停事件後提示可見、離開後消失；常駐說明那行不存在
- [x] 新色票鍵或樣式名稱通過 `test_ui_palette` 的掃描

## Comments

- 2026-10-13 agent：ui_dialogs.info_tip（底色 C["tip"]）；測試 app/tests/test_main_window.py。commit 4f45f3d。
