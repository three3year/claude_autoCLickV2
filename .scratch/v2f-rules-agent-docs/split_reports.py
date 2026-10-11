"""一次性: 四份在用流程的 `交付報告.md` 拆成 `交付報告/` (v2f-rules-agent-docs 票 10).

    .venv/Scripts/python .scratch/v2f-rules-agent-docs/split_reports.py [流程名 ...] [--apply]

區段切法與檔名用工具的 `report.sections` (跟影片轉流程產出的同一個函式); 每段「這段做什麼」由
現在的 flow.yaml 產 (report.outline), 「為什麼這樣做／已知風險／待確認」是讀舊報告後手寫的現況
(下面的 TEXT)。舊 `交付報告.md` 原樣搬成 `交付報告/舊紀錄.md`。flow.yaml 與 templates/ 寫前寫後
逐位元比對, 不一樣就還原並報錯。不加 --apply 只印出會寫什麼。
"""
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "app", ROOT / "src", ROOT / "tools"):
    sys.path.insert(0, str(p))

import flowfile  # noqa: E402
from flow_check import check  # noqa: E402
from video_to_flow import report  # noqa: E402

FLOWS = Path(os.environ["USERPROFILE"]) / "AutoClick"

# ---------------------------------------------------------------- 共用段落

POPUP_RISK = ("開頭載入異常久時，關掉簽到後忙碌檢查 1 秒內沒看到忙碌指示就放行，接著彈窗全部逾時、"
              "基建入口找不到而停止（10/08 08:44 實跑）。當時另加的「先等忙碌指示消失」那步用了出現等候上限，"
              "格式轉換時已退場；現在只靠關閉步驟的忙碌檢查。實跑若又在開頭提早結束，回報。")
TODO = {
    "why": ["待辦的三項（收穫、訂單交付、幹員信賴）同時找、有就點、點到它消失；點掉一個其他的會往左移，所以每輪重找。",
            "重複 3 次、分岔結尾 `on_break: break`：一輪三項都沒有（3 秒）就整段結束。",
            "收穫、幹員信賴勾忙碌檢查（收取送伺服器，連收時下一個要等上一個完成）。"],
    "risks": [],
    "confirm": ["訂單交付沒勾忙碌檢查：遇到忙碌時它的確認可能逾時；實跑看到再補勾。"],
}
SHIFT = {
    "why": ["每一站：先找類別標題（`标题_X`／`標題_X`），固定矩形是期望位置的窄帶、挑由上到下第 1 個 → "
            "以它為原點用相對座標點 ⇌；同站其他列用固定列距。找不到標題（分岔的條件逾時）就跳過那一站，不停流程。",
            "為什麼不找列名：引擎分不出只差數字的列名（製造站 1／2…），進駐總覽裡也沒有畫面上唯一的參考點；"
            "所以靠「窄帶＋第 1 個」限定（2026-10-09 換班段重建，列名範本與比色退場）。",
            "⇌ 與捲動拖曳都勾忙碌檢查：換班送伺服器，忙碌時列名還看得到，不等就會點掉下一個 ⇌、拖曳被吃掉。"
            "拖曳相對標題、`confirm: gone`（原點的圖離開＝有捲動）。"],
    "risks": ["捲動少了超過約 100px 會挑到前一類的列；新蓋設施改變排列會點錯列。",
              "窄帶 10/11 左右各加寬 24px（最大化時畫面左偏幾 px 會切到標題左側黃條，挑到第 1 列列名、補拖捲過頭）；"
              "日後重建換班段，窄帶左右各留範本寬 20%。"],
    "confirm": [],
}
CLUE_CHECK = {
    "why": ["開線索面板後逐號點 1–7 號篩選鈕（相對面板標記、不更新原點，點到「選中N」出現），每號找清單第一張卡的"
            "「來自」標籤；7 號都有才關面板、按快速置入。某號沒有或判不出來就停在那號、關面板、不按——只少按、不誤按。",
            "取代 10/07 的「交流中就不按」：交流中判斷會錯、沒在交流時也不一定湊齊 1–7 號（2026-10-09，影片 add3）。"],
    "risks": ["卡片標籤用「來自」：沒看過所有種類的卡片，萬一某種卡沒有這個標籤，那一號會被當成沒有（只少按）。",
              "確認選中後馬上看卡片：影片裡篩選鈕和清單同一幀換好；實機若清單比較晚換，空號可能被誤判成有——"
              "缺號卻按了快速置入時查那號卡片標籤的 `find.target`。"],
    "confirm": ["選中5／選中1 在 ×0.85 的重放裡驗證分數 0.72–0.78 偏弱；縮放大的模式下若某號一直沒選中，回報。"],
}
CREDIT = {
    "why": ["收取信用點到「獲得物資」出現（3 秒，沒出現就補做；還是沒有→跳出分岔、直接採購）→ 等獲得物資 → 點空白關掉。",
            "2026-10-08：商店頁還沒載好時第一下會被吃掉，以前沒有生效確認不補做，信用點沒領到、後面買不起。"],
    "risks": ["「今天已經收過」時按鈕長什麼樣子沒有證據；不論消失、變灰或照樣可點，都只會跳過或跳出、接著採購。",
              "頁面載入比 3 秒久還是會跳出（信用沒領到，只少買幾樣）。"],
    "confirm": [],
}
SHOP = {
    "why": ["重複 10 次（一頁 10 張卡）包一個 23 分支的分岔：每輪看畫面上有哪些白名單商品，買優先順序最高的那件"
            "（同種好幾格先買由上到下第 1 個），點到購買物品出現 → 購買 → 等獲得物資 → 點空白關。",
            "優先順序：加急許可、招聘許可、技巧概要·卷2、卷1、赤金、龍門幣、固源岩、糖、聚酸酯、異鐵、裝置、酮凝集、"
            "源岩、代糖、酯原料、異鐵碎片、破損裝置、雙酮、初級作戰記錄、基礎作戰記錄、碳素組、碳素、碳。",
            "商品都開比色（初級／基礎作戰記錄只差顏色；售罄的不算）；分岔結尾 `on_break: break`：畫面上沒有白名單商品、"
            "買不起（購買物品不出現）、獲得物資等不到，就結束整個採購。"],
    "risks": ["買不起就結束：排前面的買不起時，後面便宜的也不會買（使用者接受）。",
              "獲得物資彈窗還在時，剛買商品的範本會比到彈窗中央的獎勵圖示；每輪都等獲得物資消失才找下一件，邊際約 1 格。",
              "第一輪若商店頁還沒載好就截圖，會直接判定沒商品、結束購買。",
              "傢俱零件和其他沒有範本的商品不買。"],
    "confirm": [],
}


def popup(names, extra_why=()):
    return {"why": [f"登入後的彈窗（{names}）哪個出現關哪個；重複 6 輪、分岔結尾 `on_break: break`："
                    "一輪全部沒出現（5 秒）就整段結束。",
                    "關閉都勾忙碌檢查：關簽到會領獎、送伺服器，下一個彈窗要等它回應才出現。", *extra_why],
            "risks": [POPUP_RISK], "confirm": []}


def evening_open(close):
    return {"why": [f"開頭關公告：找「{close}」點到消失，2 秒沒有就跳過（2026-10-07 晚加；公告蓋住基建入口時原本會等 30 秒後停止）。",
                    "基建入口逾時 30 秒（登入載入）；待辦鈴鐺點到左下「待辦事項」出現（15 秒沒有就跳過）。"],
            "risks": ["只處理公告：先跳出的是簽到或活動彈窗時，公告約 4 秒後才出來，這一步會漏關，流程在基建入口那步 30 秒後停止"
                      "（早班清彈窗的迴圈沒搬，實跑遇到再處理）。"],
            "confirm": []}


def factory(cn, evening):
    why = ["離開待辦模式：找左上「返回」當原點、點空白處（右上會被收取提示蓋住），等 0.5 秒讓進駐總覽出現。",
           "製造站加速：以「進駐總覽」為原點點第三排中間那張製造站（點到下一步的圖出現）→ 生產面板 → 無人機加速 → "
           "最多 → 確定（勾忙碌檢查：加速送伺服器）→ 收取（3 秒沒有就跳過）。",
           "返回 ×2：第二下點到下一步的圖出現，第一下被吃掉時不會少退一層。"]
    risks = ["製造站卡是座標點擊：基建地圖的縮放會變（影片裡 1.0–1.24 倍），縮放差很多時相對進駐總覽可能點到別張；"
             "點錯就改用找圖點卡片。"]
    if evening:
        why.append("接著進駐總覽 → 非工作區定位 → 換班第一站（製造站）：相對非工作區點 ⇌、"
                   "再以類別標題窄帶定位拖曳捲動（同換班各段的做法）。")
        risks += SHIFT["risks"]
    elif cn:
        why.append("返回後地圖停在左邊、看不到會客室：以進駐總覽為原點往左拖地圖 → 會客室（點到線索鈕出現）→ 線索板。")
        risks.append("拖地圖找會客室的距離沿用繁中版（往左 950px），沒有單獨實跑驗證；找不到會客室會在那一步停止。")
    else:
        why.append("返回後往左拖地圖 → 會客室（點到線索面板出現）→ 線索面板。")
    return {"why": why, "risks": risks, "confirm": []}


TEXT = {
    "早_簡中": {
        "videos": "`demo6.mp4`（簡中視窗 1696×912，主體）；`add1.mp4`（接收線索）、`add3.mp4`（查 1–7 號線索）、"
                  "`add5.mp4`（回收站換班）",
        "sections": {
            "重複-签到关闭": popup("簽到、活動、公告、今日配給、獲得物資",
                                ["今日配給／獲得物資用定位找圖＋相對點空白處關掉；獲得物資那下勾忙碌檢查（領取的結算）。"]),
            "步驟-基建入口": {"why": ["基建入口範本只框左邊不會變的基建圖樣（右上的通知數字與 BASE 字樣會被蓋住，"
                                    "舊範本因此找不到）；逾時 30 秒給登入載入。",
                                    "待辦鈴鐺點到左下「待辦事項」出現（15 秒沒有就跳過）。"],
                            "risks": [], "confirm": []},
            "重複-可收获": TODO,
            "步驟-返回": factory(True, False),
            "分岔-线索交流结果": {"why": ["進線索板時「線索交流結果」彈窗有才關（1.5 秒內沒有就跳過），關掉後等 0.8 秒。"],
                             "risks": [], "confirm": []},
            "步驟-每日线索": {"why": ["每日線索 → 領取（各 3 秒沒有就跳過；領取點到它消失）。"], "risks": [], "confirm": []},
            "分岔-接收线索": {"why": ["接收好友線索：接收線索 → 全部收取（點到「暂未收到新的线索」出現＝收完）→ 點面板外的空白處關掉"
                                   "（點到傳遞線索出現）。接收線索 5 秒沒有就跳出。",
                                   "2026-10-09 起排在查線索、快速置入之前：當天收到的當天就用得到。",
                                   "全部收取收完是暗藍色、比色仍 0.98，所以不比色，改用「暫未收到新的線索」判斷收完。"],
                           "risks": [],
                           "confirm": ["簡中「接收线索」範本在影片上引擎找不到、10/07 實機也逾時（最高 0.587），之後沒有新證據；"
                                       "實跑逾時就查這一步的 `find.target`，該重截。"]},
            "步驟-CONFIDENTIAL线索": {"why": ["點線索板右下 CONFIDENTIAL 線索鈕打開面板，點到面板標記「全部分页」出現（5 秒沒有就跳過）。"],
                                    "risks": [], "confirm": []},
            "分岔-全部分页": CLUE_CHECK,
            "分岔-全部分页_2": {"why": ["上一段因缺號跳出時面板還開著：面板標記 1 秒內看得到就點同一個空白處關掉，看不到就跳過。"],
                            "risks": [], "confirm": []},
            "分岔-解锁线索": {"why": ["解鎖線索開比色：7/7 才可按（灰色時比色 0.87–0.88 擋掉）；點了等 2 秒讓線索板自己關。"],
                           "risks": [], "confirm": []},
            "步驟-线索": {"why": ["重開線索板（2 秒沒有就跳過）。"], "risks": [], "confirm": []},
            "分岔-传递线索": {"why": ["傳遞線索 → 快捷傳遞重複線索 → 關閉；傳遞線索 3 秒內沒找到就整段跳過。",
                                   "傳遞線索勾忙碌檢查：前面剛收完、置入完線索，遊戲常還在提交。"],
                           "risks": [], "confirm": []},
            "步驟-返回_2": {"why": ["返回 ×2（第二下點到下一步的圖出現）→ 進駐總覽 → 非工作區定位（換班的起點）→ 等 0.5 秒。"],
                          "risks": [], "confirm": []},
            "分岔-标题_制造站": SHIFT, "步驟-标题_制造站": SHIFT, "分岔-标题_制造站_2": SHIFT,
            "步驟-标题_制造站_2": SHIFT, "分岔-标题_贸易站": SHIFT, "步驟-标题_贸易站": SHIFT,
            "分岔-标题_办公室": SHIFT,
            "分岔-标题_办公室_2": {"why": SHIFT["why"] + [
                "回收站：2026-10-10 照 `add5.mp4` 用一次性腳本插入——定位辦公室標題 → 拖曳 333px → 定位回收站標題 → 點 ⇌。"],
                "risks": SHIFT["risks"],
                "confirm": ["這段是 v2f-rules-agent-docs 驗收①的對照組：會在複本上刪掉、用 edit-flow＋add5 插回去比對。"]},
            "步驟-非工作区": {"why": ["點非工作區結束換班 → 幹員休整（3 秒沒有就跳過）→ 導航（點到下一步的圖出現）→ 好友 → "
                                   "好友列表（點到下一步的圖出現，逾時 30）→ 訪問基建（清單最上面那個：由上到下第 1 個，固定矩形是整欄高）。"],
                           "risks": [],
                           "confirm": ["好友列表 10/09 改成不比色＋只框那個分頁：旁邊同形的分頁若被點到，回報重截。"]},
            "重複-访问下位": {"why": ["訪問下位 ×10：點完等按鈕消失（轉場開始，5 秒），下一輪再等它出現；30 秒找不到就跳出。"],
                           "risks": [], "confirm": []},
            "步驟-导航（好友基建）": {"why": ["導航 → 採購中心 → 信用交易所（逾時 20）。"], "risks": [],
                                 "confirm": ["信用交易所 10/09 改成不比色：旁邊同形的分頁若被點到，回報重截。"]},
            "分岔-收取信用": CREDIT,
            "重複-採購_加急許可": dict(SHOP, why=SHOP["why"] + [
                "技巧概要·卷2 不開比色（demo6 上比色 0.94 差門檻一點）；卷1 範本在卷2 卡上粗篩只有 0.49，不會認錯。"],
                confirm=[
                "簡中沒在真畫面上驗證過的商品：源岩、代糖、酯原料、異鐵碎片、雙酮、酮凝集、破損裝置、碳、碳素組、龍門幣、技巧概要·卷1；"
                "碳素只在低位元率的 demo1 測過（失敗）。實跑留意這幾種有沒有漏買或點錯。"]),
            "步驟-导航（好友基建）_2": {"why": ["導航 → 公開招募。"], "risks": [], "confirm": []},
        },
        "stale": ["第 2 步「忙碌指示 → 等待消失（出現等候上限 3000ms）」：出現等候上限已退場，格式轉換時拿掉了。",
                  "「交流中」範本與「交流中就不按快速置入」的分岔（10/09 刪，改成查 1–7 號）。",
                  "換班的列名範本（製造站1列、貿易站1列、发电站1列、办公室列、各「首列」）與列名比色、「類別標題+首列」第二關"
                  "（10/09 換班段重建退場，改成類別標題窄帶）。",
                  "九宮格限定範圍（忙碌指示 [8, 9] 等；已全部換成固定矩形，九宮格已退場）。",
                  "忙碌暫停（ADR 0010；10/08 換成忙碌檢查）與換班後的「等待消失」步驟。",
                  "流程存檔路徑 `profiles/arknights/flows/*.autoclickpack`、草稿、工作區（現在是 `%USERPROFILE%\\AutoClick\\早_簡中\\` 資料夾）。",
                  "舊紀錄裡所有步驟編號（插入、刪除過很多次）。"],
    },
    "早_繁中": {
        "videos": "`demo2.mp4`（繁中最大化 1920×1024，主體）；部分範本另從 `demo3.mp4` 與後來的補充影片取材（細節見舊紀錄）",
        "sections": {
            "重複-圓形叉叉": popup("簽到、活動、公告都是圓形叉叉；獲得物資",
                                ["公告會在前一個彈窗關掉後約 4 秒自己跳出，所以每輪等 5 秒。"]),
            "步驟-基建BASE": {"why": ["基建入口（基建BASE，偏移 (0, +1)）逾時 30 秒給登入載入；鈴鐺點到左下「待辦事項」出現（15 秒沒有就跳過）。"],
                            "risks": [],
                            "confirm": ["基建BASE 10/09 重截換掉，還沒實跑驗過；找不到時看執行紀錄哪一關沒過（粗篩或驗證）。"]},
            "重複-可收穫": TODO,
            "步驟-返回": factory(False, False),
            "分岔-線索交流彈窗": {"why": ["進線索板時「線索交流」彈窗有才關（有才關，沒有就跳過）。"], "risks": [], "confirm": []},
            "步驟-每日線索": {"why": ["每日線索 → 領取（沒有就跳過）。"], "risks": [], "confirm": []},
            "分岔-接收線索": {"why": ["接收好友線索：接收線索 → 全部收取（點到「暫未收到新的線索」出現）→ 點面板外關掉。",
                                   "2026-10-09 起排在查線索、快速置入之前：當天收到的當天就用得到。"],
                           "risks": [], "confirm": []},
            "步驟-CONFIDENTIAL線索": {"why": ["點線索板右下 CONFIDENTIAL 線索鈕打開面板，點到面板標記「全部分頁」出現。"],
                                    "risks": [], "confirm": []},
            "分岔-全部分頁": CLUE_CHECK,
            "分岔-全部分頁_2": {"why": ["上一段因缺號跳出時面板還開著：面板標記看得到就點空白處關掉，看不到就跳過。"],
                            "risks": [], "confirm": []},
            "分岔-解鎖線索": {"why": ["解鎖線索開比色：只認可按的顏色；點了等 2 秒讓線索板自己關。"], "risks": [], "confirm": []},
            "步驟-線索面板": {"why": ["重開線索面板 → 傳遞線索（勾忙碌檢查：剛收完、置入完線索，遊戲常還在提交）→ 快速傳遞 → 關閉 → "
                                   "返回 ×2（第二下點到下一步的圖出現）→ 進駐總覽 → 非工作區定位（換班起點）。"],
                           "risks": [],
                           "confirm": ["快速傳遞在 ×0.883 的重放裡驗證 0.796 貼門檻；視窗模式找不到時回報重截。"]},
            "分岔-標題_製造站": SHIFT, "步驟-標題_製造站": SHIFT,
            "分岔-標題_貿易站": SHIFT, "步驟-標題_貿易站": dict(SHIFT, confirm=[
                "2026-10-10 第 3 個發電站換班改成一次拖曳（原本拖 391 → 重新定位 → 再拖 391，標題被拖到貼著列表頂端、"
                "實跑差幾像素就被蓋住）：合併後那一次拖曳還沒在實機走過；看點是那一步 `input.confirm kind=drag inputs=1`、"
                "接著辦公室標題在窄帶內找到。"]),
            "分岔-標題_辦公室": SHIFT,
            "步驟-非工作區": {"why": ["點非工作區結束換班 → 幹員休息（3 秒沒有就跳過）→ 導航 → 好友 → 好友列表 → "
                                   "訪問基建（清單最上面那個，固定矩形是整欄高）。"],
                           "risks": [],
                           "confirm": ["好友列表 10/09 改成不比色＋只框那個分頁：旁邊同形的分頁若被點到，回報重截。"]},
            "重複-訪問下位": {"why": ["訪問下位 ×10：點完等按鈕消失（轉場開始），下一輪再等它出現；實測約 2.3 秒一位。"],
                           "risks": [], "confirm": []},
            "步驟-導航": {"why": ["導航 → 採購中心 → 信用交易所。"], "risks": [],
                        "confirm": ["信用交易所 10/09 改成不比色：旁邊同形的分頁若被點到，回報重截。"]},
            "分岔-收取信用": CREDIT,
            "重複-採購_加急許可": dict(SHOP, confirm=[
                "10/10 實跑：龍門幣購買後「獲得物資」沒出現 → 跳到結尾，疑似信用點用完，待確認。"]),
            "步驟-導航_2": {"why": ["導航 → 公開招募。"], "risks": [], "confirm": []},
        },
        "stale": ["「使用前必做：在主畫面按一次校準」：流程自帶校準對，每次執行開頭自動量。",
                  "「交流中」範本與「交流中就不按快速置入」的分岔（10/09 刪，改成查 1–7 號）。",
                  "換班的列名範本（製造站1列、貿易站1列、發電站1列、辦公室列、各「首列」）、列名比色與「類別標題+首列」第二關；"
                  "「列名在畫面下 1/3 就跳過」的判斷（10/09 換班段重建退場）。",
                  "九宮格限定範圍、忙碌暫停（ADR 0010）、換班後的「等待消失」步驟、出現等候上限。",
                  "「座標尺度：基準尺度（demo2 實測倍率 0.91）」與搜尋範圍 [0, 0, 1920, 1024] 的舊說法（現在一份流程一個尺度，"
                  "見總覽的校準對）。",
                  "流程存檔路徑 `profiles/arknights/flows/*.autoclickpack`。",
                  "舊紀錄裡所有步驟編號（10/10 合併拖曳後第 108 步以後都往前移 2，舊紀錄沒跟著改）。"],
    },
    "晚_簡中": {
        "videos": "`demo4.mp4`（簡中視窗 1696×912，主體）；`demo5.mp4`（公告關閉的驗證）",
        "sections": {
            "步驟-公告关闭": evening_open("公告关闭"),
            "重複-可收获": TODO,
            "步驟-返回": factory(True, True),
            "分岔-标题_贸易站": SHIFT, "步驟-标题_贸易站": SHIFT, "分岔-标题_发电站": SHIFT,
            "步驟-标题_发电站": SHIFT, "分岔-标题_发电站_2": SHIFT,
            "步驟-非工作区": {"why": ["點非工作區結束換班 → 幹員休整（3 秒沒有就跳過）→ 導航（點到下一步的圖出現）→ 公開招募。"],
                           "risks": [], "confirm": []},
        },
        "stale": ["「使用前在主畫面按一次校準」「畫面倍率 0.806」：流程自帶校準對，每次執行開頭自動量。",
                  "換班「先找列名（比色）再確認類別標題」與列名範本（贸易站1列、发电站1列…，10/09 換班段重建退場）。",
                  "九宮格限定範圍、忙碌暫停（ADR 0010）、換班後的固定等待與「等待消失」、出現等候上限。",
                  "「口頭補充的按鍵」一節（報告已不寫；流程不支援按鍵）。",
                  "流程存檔路徑 `profiles/arknights/flows/*.autoclickpack`、舊紀錄裡所有步驟編號。"],
    },
    "晚_繁中": {
        "videos": "`demo3.mp4`（繁中最大化 1920×1024，主體）；`demo2.mp4`（離開待辦模式的位置、公告關閉的驗證）",
        "sections": {
            "步驟-圓形叉叉": evening_open("圓形叉叉"),
            "重複-可收穫": TODO,
            "步驟-返回": factory(False, True),
            "分岔-標題_貿易站": SHIFT, "步驟-標題_貿易站": SHIFT, "分岔-標題_發電站": SHIFT,
            "步驟-標題_發電站": SHIFT, "分岔-標題_發電站_2": SHIFT,
            "步驟-非工作區": {"why": ["點非工作區結束換班 → 幹員休息（3 秒沒有就跳過）→ 導航 → 公開招募。"],
                           "risks": [], "confirm": []},
        },
        "stale": ["「使用前在主畫面按一次校準」「畫面倍率 0.910」：流程自帶校準對，每次執行開頭自動量。",
                  "換班「先找列名（比色）再確認類別標題」與列名範本（貿易站1列、發電站1列…，10/09 換班段重建退場）。",
                  "九宮格限定範圍、忙碌暫停（ADR 0010）、換班後的固定等待與「等待消失」、出現等候上限。",
                  "「口頭補充的按鍵」一節（報告已不寫；流程不支援按鍵）。",
                  "流程存檔路徑 `profiles/arknights/flows/*.autoclickpack`、舊紀錄裡所有步驟編號。"],
    },
}

NOTE_ROW = re.compile(r"^\|\s*\d+\s*\|\s*find_click\s*\|\s*([^〔→|]+?)\s*(?:〔|→)")
CONFIRM_IMG = re.compile(r"確認圖「([^」]+)」")


def stale_templates(old_text, current):
    """舊報告步驟清單提到、現在 templates/ 沒有的範本名."""
    seen = []
    for line in old_text.splitlines():
        m = NOTE_ROW.match(line)
        names = [m.group(1)] if m else []
        names += CONFIRM_IMG.findall(line) if line.startswith("|") else []
        for n in names:
            n = n.strip()
            if n and n not in current and n not in seen:
                seen.append(n)
    return seen


def bullets(items, empty="無。"):
    return [f"- {x}" for x in items] or [empty]


def section_file(sec, steps, text):
    lines = [f"# {sec.name}", "", f"[← 總覽]({report.OVERVIEW})", "", "## 這段做什麼", ""]
    lines += report.outline(steps, sec.start, sec.end)
    lines += ["", "## 為什麼這樣做", ""] + bullets(text["why"])
    lines += ["", "## 已知風險", ""] + bullets(text["risks"], "無已知風險；實跑發現後補在這裡。")
    lines += ["", "## 待重拍", "", "無。", "", "## 待確認", ""] + bullets(text["confirm"])
    return "\n".join(lines) + "\n"


def overview(name, flow, folder, secs, info, stale_names):
    cal = flow["calibration"]
    fb = cal.get("fallback")
    busy = flow.get("busy")
    tpl = flowfile.folder_template_names(folder)
    lines = [f"# 交付報告：{name}", "",
             "總覽；每個頂層區段另有一份，改哪段只讀那一份。步驟用內容指稱（範本名＋動作），不寫步驟編號——"
             "編號以 flow.yaml 行尾的 `# N` 為準。", "",
             "## 概要", "",
             f"- 示範影片：{info['videos']}（都在 oCam Video 資料夾）",
             f"- 校準對：{cal['pair'][0]} × {cal['pair'][1]}，基準距離 {cal['baseline']:.1f}"
             + (f"；備用校準對：{fb['pair'][0]} × {fb['pair'][1]}，基準距離 {fb['baseline']:.1f}，"
                f"偏移 ({fb['offset'][0]:+d},{fb['offset'][1]:+d})" if fb else "；沒有備用校準對"),
             f"- 搜尋範圍：{flow['scan_region'] or '不寫（全螢幕）'}",
             f"- 忙碌指示：「{busy['template']}」" + (f"，固定矩形 {busy['within']}" if busy.get('within') else "")
             if busy else "- 忙碌指示：沒有",
             f"- 步驟數：{len(flow['steps'])}；範本數：{len(tpl)}",
             f"- 引擎參數覆蓋：{flow.get('engine') or '沒有'}",
             "", "## 各段報告（依流程順序）", ""]
    lines += [f"- [{s.name}]({s.file})" for s in secs]
    lines += ["", "## 待重拍", "", "無——在用的範本都實跑或影格驗證過；個別段落的弱範本列在待確認。", "", "## 待確認", ""]
    pend = [(s, t) for s in secs for t in info["sections"][s.name]["confirm"]]
    seen = set()
    rows = []
    for s, t in pend:
        if t in seen:   # 換班各段共用的同一則只列一次
            continue
        seen.add(t)
        rows.append(f"{t}（[{s.name}]({s.file})）")
    lines += bullets(rows)
    lines += ["", "## 過期內容（舊紀錄裡已不成立的）", "",
              "舊紀錄是按日期累積的修改歷史；下面這些已經不是現況，讀舊紀錄時別照做。", ""]
    lines += bullets(info["stale"])
    if stale_names:
        lines.append(f"- 舊紀錄步驟清單提到、現在 `templates/` 沒有的範本：{'、'.join(stale_names)}。")
    lines += ["", "## 舊紀錄", "",
              f"[{report.OLD}]({report.OLD})：拆檔前的整份 `交付報告.md`，原樣保留（歷史，平常不必讀）。"
              "要查某個做法當初為什麼這樣定、比過哪些分數時才翻。"]
    return "\n".join(lines) + "\n"


def digest(folder):
    h = hashlib.sha256()
    for rel in ["flow.yaml"] + sorted(f"templates/{n}" for n in os.listdir(folder / "templates")):
        h.update(rel.encode())
        h.update((folder / rel).read_bytes())
    return h.hexdigest()


def split(name, apply):
    folder = FLOWS / name
    info = TEXT[name]
    old_path = folder / "交付報告.md"
    rdir = folder / report.DIR
    if rdir.exists():
        raise SystemExit(f"{name}：交付報告/ 已經存在，不重做")
    old = old_path.read_bytes()
    flow = flowfile.read_flow(folder)
    secs = report.sections(flow["steps"])
    missing = [s.name for s in secs if s.name not in info["sections"]]
    extra = [k for k in info["sections"] if k not in {s.name for s in secs}]
    if missing or extra:
        raise SystemExit(f"{name}：段落對不上 缺 {missing} 多 {extra}")
    stale_names = stale_templates(old.decode("utf-8"), set(flowfile.folder_template_names(folder)))
    files = {report.OVERVIEW: overview(name, flow, folder, secs, info, stale_names)}
    for s in secs:
        files[s.file] = section_file(s, flow["steps"], info["sections"][s.name])
    if not apply:
        print(f"== {name}：{len(files)} 份；過期範本 {stale_names}")
        print(files[report.OVERVIEW])
        return
    before = digest(folder)
    report.write(folder, files)
    os.replace(old_path, rdir / report.OLD)
    assert (rdir / report.OLD).read_bytes() == old, "舊紀錄要逐位元相同"
    assert digest(folder) == before, "flow.yaml 與 templates/ 不能變"
    res = check(folder)
    assert res.ok, res.errors
    print(f"{name}：寫好 {len(files)} 份＋舊紀錄；flow.yaml、templates/ 不變；檢查指令沒有錯誤")


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if a != "--apply"]
    for n in args or TEXT:
        split(n, "--apply" in sys.argv)
