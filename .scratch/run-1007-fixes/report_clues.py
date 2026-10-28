from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "busy-pause-fixed-rect"))

import common as bp  # noqa: E402
import report as r05  # noqa: E402

import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402

DATE = "2026-10-07"
HEADING = f"## {DATE} 晚：接收線索真的按「全部收取」"
STEPS_HEADING = f"## 步驟清單（{DATE} 接收線索後更新）"

COMMON = [
    "- **結構**（一個分岔，`接收線索` 找不到就整段跳過）：",
    "  1. 接收線索（線索板右上中間那顆）→ 點擊，點到確認圖「全部收取」出現（逾時 5s→跳出分岔）。",
    "  2. 全部收取 → 點擊，點到確認圖「暫未收到新的線索」出現（逾時 8s→跳過）。"
    "收完、或本來就沒有線索時，面板中間都會出現這行字；沒線索時按到的是暗掉的按鈕，沒有作用。",
    "  3. 座標點擊（相對全部收取，落在線索板左下的空白處）關掉面板，點到確認圖「傳遞線索」出現"
    "（逾時 5s→跳過）。面板開著時會蓋住右側那排圖示，傳遞線索重新出現＝面板關了。取代原本的固定等待 500ms。",
    "- **比色分不出能不能按**：全部收取收完後是暗藍色，比色仍有 0.98（門檻 0.95），所以不比色，"
    "改用「暫未收到新的線索」判斷收完沒。",
    "- **固定矩形**：新範本照票 08 的做法加框（影片上的位置外擴 40px）。",
    "- 腳本：`.scratch/run-1007-fixes/build_clues.py`（真引擎驗證、全過才寫回）、本報告 `report_clues.py`；"
    "備份 `app/dist/profiles-backup-2026-10-07-run-1007-fixes-02/`。",
]

SECTIONS = {
    "早_簡中": [
        HEADING, "",
        "使用者 10/07 錄了 `oCam Video/add1.mp4`（簡中，有好友線索：點接收线索 → 全部收取 → 點面板外關掉）。"
        "原本這段只開關面板、沒有按全部收取（demo6 當天沒線索）。第 64–69 步的分岔換成第 64–68 步。",
        "",
        *COMMON,
        "- **範本**：`全部收取` 換成 add1 第 100 格裁的可按藍色版 (1378,852,170,46)（原本那張是收完的暗色版）；"
        "新增 `暂未收到新的线索`（第 170 格 (1381,463,171,24)）。`接收线索` 沿用原範本與框。",
        "- **關面板的位置**沿用原本的 (-429,-184)：在 add1 上落在 6 號線索格右下的空白處，"
        "跟使用者在影片裡點的位置差不多。",
        "- **驗證**（真引擎、影格貼到實機搜尋範圍的畫布、套框）：26/26 符合——",
        "  接收线索 有 4/4（0.953–0.977，有沒有 NEW 都找得到）、面板開著時無 2/2；"
        "全部收取 有 4/4（藍色 0.996–1.000、暗色 0.975）、線索板上無 2/2；"
        "暂未收到新的线索 收完後有 3/3（1.000）、其他畫面無 4/4；传递线索 面板關著有 3/3、開著無 4/4。",
        "- **10/07 早上實機「接收线索」逾時（最高 0.587）**：當時第 54 步無條件按了快速置入，接著重開线索（第 59 步）"
        "也逾時，線索板狀態已經亂掉；同一張範本在 add1 正常的線索板上找得到，所以先不換範本。"
        "快速置入已在下午改成分岔（見下面「快速置入看線索板狀態」）。實跑若還是逾時，查日誌這一步的 `find.target`。",
        "",
    ],
    "早_繁中": [
        HEADING, "",
        "使用者 10/07 錄了 `oCam Video/add2.mp4`（繁中，有好友線索）。繁中原本沒有接收線索這段"
        "（demo2 當天沒點，見 `.scratch/run-1006-fixes/issues/03-reception-friend-clue-not-claimed.md`）；"
        "照簡中的位置插在「線索面板」（第 55 步）之後、「傳遞線索」之前，新的第 56–60 步。",
        "",
        *COMMON,
        "- **範本**（都從 add2 裁，與流程同尺度）：`接收線索` 第 160 格 (1790,350,58,58)——收完、沒有 NEW 標籤的那格，"
        "有 NEW 時也找得到（0.996）；`全部收取` 第 80 格 (1554,958,192,52)；`暫未收到新的線索` 第 125 格 (1557,518,194,27)。",
        "- **關面板的位置**：簡中的 (-429,-184) 照基準距離換算（1868/1650）成 (-486,-208)，在 add2 上落在線索板空白處。",
        "- **驗證**（同簡中的做法）：26/26 符合——",
        "  接收線索 有 4/4（0.996–1.000）、面板開著時無 2/2；全部收取 有 3/3（藍色 1.000、暗色 0.980）、線索板上無 2/2；"
        "暫未收到新的線索 收完後有 4/4（1.000）、其他畫面無 4/4；傳遞線索 面板關著有 3/3、開著無 4/4。",
        "- **忙碌指示**：add2 收取時出現的「正在提交反饋至神經……」，現在的忙碌指示範本（下午從 demo2 重截的那張）"
        "在 add2 上 0.93–0.99、框 [8,9] 內找得到。",
        "",
    ],
}

PROSE = {
    "早_簡中": [
        ("  接收线索（打開面板、點面板外關掉）→ 传递线索 → 返回 ×2。",
         "  接收线索 → 全部收取 → 點面板外關掉（10/07 晚改成真的收，見最上面那節）→ 传递线索 → 返回 ×2。"),
    ],
    "早_繁中": [
        ("   - 傳遞線索 → 快速傳遞 → 關閉 → 返回 ×2。",
         "   - 接收線索 → 全部收取 → 點面板外關掉（10/07 晚加，見最上面那節）。\n"
         "   - 傳遞線索 → 快速傳遞 → 關閉 → 返回 ×2。"),
    ],
}
CN_OLD_NOTE = re.compile(r"  - \*\*接收线索只開關、沒有按「全部收取」\*\*.*?(?=\n  - |\n- |\n\n|\n## )", re.S)
CN_NEW_NOTE = "  - 接收线索原本只開關、沒有按「全部收取」（demo6 當天沒有新線索）；10/07 晚照 add1 補上。"


def step_table(steps):
    lines = r05.step_table(steps)
    lines[0] = STEPS_HEADING
    return lines


def main():
    for name, sec in SECTIONS.items():
        md = os.path.join(bp.FLOWS, name + ".md")
        with open(md, encoding="utf-8") as f:
            text = f.read()
        text = r05.replace_section(text, re.escape(HEADING), sec, before_first_h2=True)
        for old, new in PROSE[name]:
            if new in text:
                continue
            if old in text:
                text = text.replace(old, new)
            else:
                raise SystemExit(f"{name}.md 找不到要換的句子: {old.strip()}")
        if name == "早_簡中":
            text = CN_OLD_NOTE.sub(CN_NEW_NOTE, text)
        steps = flowfile.read(bp.flow_path(name))["data"]["steps"]
        text = r05.replace_section(text, r"## 步驟清單", step_table(steps) + [""])
        with open(md, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"{name}.md: 已更新（步驟 {len(steps)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
