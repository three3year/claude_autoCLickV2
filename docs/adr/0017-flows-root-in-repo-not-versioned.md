# ADR 0017：流程存放區在專案的 flows/，不進版控

Status: accepted（2026-10-18）。取代 project-cleanup 票 09
（`.scratch/project-cleanup/issues/09-packaged-layout-and-flow-location.md`）裡「流程放
`%USERPROFILE%\AutoClick\`」那一條；票 09 其餘佈局（打包版資料夾裡沒有使用者資料、本機
狀態與日誌的位置）不變。ADR 0015 只說「開檔選任何位置的流程資料夾」，不受影響。

## 背景

`流程存放區`（`apppaths.flows_root()`，詞彙見 `app/GLOSSARY.md`）是開檔、新流程第一次存檔的
對話框起點，也是影片轉流程沒指定輸出位置時的預設。票 09 把它放在使用者資料夾底下的
`AutoClick`，跟專案分開。使用者想把日常在用的流程集中在專案裡（開專案就看得到），
但流程含範本圖、快取與個人調整，屬於使用資料，不該上傳到 git。

## 決策

1. **存放區＝repo 根目錄的 `flows/`，`.gitignore` 排除整個資料夾。** 流程資料夾仍可存在
   任何位置，存放區只是預設；不存在就建（沿用對話框原本的行為）。
2. **原始碼執行**：`<repo>/flows`，repo 根就是路徑模組所在的 `app/` 的上一層。
3. **打包版從 exe 所在資料夾逐層往上找 repo**：某層底下有 `app/apppaths.py`（本專案自己的
   原始檔）就認定是 repo 根，用它的 `flows/`。打包版在 `app\dist\AutoClick\`，打包時暫時的
   `dist-new` 也在 repo 裡，兩者都找得到；這台電腦上打包版與原始碼執行看到同一組流程。
4. **往上找到磁碟根都沒有 → 退回 `%USERPROFILE%\AutoClick\`**：整包拿到沒有 repo 的電腦照樣能用。
5. 影片轉流程工具不再自己寫死預設輸出，呼叫同一個 `flows_root()`；`--out` 與計畫的 `out` 優先。

## 取捨與已知代價

- 記號用專案原始檔而不是 `.git`：別的 git repo 不會誤認，沒有 `.git` 的專案複本也認得。
  代價是改名或搬走 `app/apppaths.py` 時要一起改記號。
- 流程在 repo 裡卻不進版控：看起來像「忘了 commit」，其實是刻意的（別把 `flows/` 從
  `.gitignore` 拿掉）。流程的備份不靠 git。
- 重新打包整個換掉 `dist\` 不會碰到流程，因為流程不在 dist 裡。

## 替代方案

- **只有原始碼執行搬進專案、打包版維持使用者資料夾。** 拒絕：兩邊各一組流程，平常用
  打包版等於沒搬。
- **打包版一律用 exe 旁的 `flows\`。** 拒絕：重新打包會整個換掉 dist，流程跟著被刪。
- **`.local/flows/` 或 `app/flows/`。** 拒絕：前者跟可丟的本機狀態混在一起，後者跟程式碼
  與 build、dist 混在一起。
- **晚_繁中當範例進 git。** 這次取消；之後要範例另開需求。
