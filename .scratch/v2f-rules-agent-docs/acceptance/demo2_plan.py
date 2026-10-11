"""驗收②: demo2 (早_繁中, 繁中最大化 1920×1024) 的轉換計畫 (照 video-to-flow / video-measure 量的).

    .venv/Scripts/python .scratch/v2f-rules-agent-docs/acceptance/demo2_plan.py <輸出 plan.json>

位置與幀號都是在 demo2 上量的 (掃描候選、逐幀條帶、`demo2_locate.py` 用在用早_繁中的圖當參考找框);
範本由組裝從 demo2 影格重裁。影片裡的探索操作 (進駐總覽教學彈窗、來回切分頁、多按一次返回、
游標停在製造站 2 沒點) 不建步驟, 寫進報告。
"""
import json
import sys

VIDEO = "C:/Users/three/我的電腦/oCam Video/demo2.mp4"
ABSENT = [1730]          # 進基建→好友之間的載入畫面: 什麼都沒有

T = {   # 範本: (取材幀, 框)
    "主畫面設定鈕": (262, [30, 58, 60, 56]),
    "主畫面倉庫": (256, [1678, 834, 86, 100]),
    "標題列圖示": (256, [7, 3, 26, 31]),
    "標題列關閉鈕": (292, [1875, 6, 26, 26]),
    "圓形叉叉": (5, [1647, 149, 46, 46]),
    "基建BASE": (260, [1394, 803, 85, 95]),
    "鈴鐺": (433, [1804, 189, 40, 40]),
    "待辦事項": (500, [10, 962, 180, 42]),
    "可收穫": (495, [204, 964, 50, 40]),
    "訂單交付": (548, [212, 966, 47, 40]),
    "幹員信賴": (578, [350, 958, 40, 46]),
    "返回": (620, [42, 63, 30, 46]),
    "進駐總覽": (679, [206, 150, 72, 64]),
    "生產面板箭頭": (705, [596, 811, 33, 34]),
    "無人機加速": (716, [1824, 728, 48, 48]),
    "最多": (732, [1215, 470, 190, 62]),
    "確定": (753, [1384, 787, 75, 38]),
    "收取": (775, [1642, 850, 50, 58]),
    "會客室": (858, [855, 264, 145, 36]),
    "線索面板": (876, [336, 922, 66, 74]),
    "線索交流彈窗": (915, [40, 222, 52, 112]),
    "每日線索": (955, [1796, 232, 48, 54]),
    "領取": (986, [1133, 784, 63, 31]),
    "快速置入": (1000, [1710, 925, 40, 36]),
    "傳遞線索": (1140, [1790, 464, 58, 58]),
    "快速傳遞": (1156, [100, 942, 76, 78]),
    "傳遞關閉": (1199, [1852, 59, 48, 48]),
    "標題_製造站": (1460, [866, 626, 112, 44]),
    "標題_貿易站": (1526, [866, 464, 112, 44]),
    "非工作區": (1570, [1638, 56, 60, 56]),
    "幹員休息": (1596, [1652, 930, 84, 64]),
    "導航": (1628, [304, 60, 68, 46]),
    "好友": (1660, [1630, 58, 60, 50]),
    "離開基建確認": (1680, [1265, 672, 60, 56]),
    "好友列表": (1792, [46, 280, 58, 64]),
    "訪問基建": (1894, [1310, 232, 64, 38]),
    "訪問下位": (1952, [1712, 882, 190, 64]),   # 連字框 (只框圖示時 ×1.15 粗篩 0.64)
    "忙碌指示": (2000, [1069, 944, 272, 25]),
    "採購中心": (2690, [1612, 350, 74, 66]),
    "信用交易所": (2726, [1530, 150, 95, 42]),
    "收取信用": (2750, [1520, 62, 155, 48]),
    "獲得物資": (2778, [910, 90, 125, 112]),
    "購買物品": (2794, [1200, 780, 56, 46]),
    "採購_招聘許可": (2784, [736, 370, 98, 70]),   # 上排那張 (由上到下第 1 個挑的是它)
    "採購_裝置": (2869, [424, 684, 98, 70]),
    "採購_初級作戰記錄": (2900, [1048, 369, 98, 70]),   # 上排第 4 格 (第 5 格同款)
    "採購_破損裝置": (2980, [425, 371, 98, 70]),
    "採購_赤金": (3024, [1360, 683, 98, 70]),
    "公開招募": (3147, [1320, 363, 62, 58]),
}
NO_ABSENT = {"標題列圖示", "標題列關閉鈕"}    # 載入畫面也有標題列


def f(name, frame=None, head="find_click", **kw):
    return dict({head: name, "frame": T[name][0] if frame is None else frame}, **kw)


def popup(frame):
    return {"branch": [{"if": f("圓形叉叉", frame, confirm="gone", timeout=5, on_fail="skip",
                                busy_check=True)}]}


def buy(name):
    return {"if": f(name, pick={"top": 1}, color=True, scroll="horizontal",
                    confirm={"appear": "購買物品"}, timeout=1.5, on_fail="break"),
            "then": [f("購買物品", confirm={"appear": "獲得物資", "frame": 2814}, timeout=4,
                       on_fail="break", busy_check=True),
                     f("獲得物資", 2814, head="find", timeout=8, on_fail="break"),
                     {"click": [960, 877], "frame": 2862, "confirm": "gone"}]}


STEPS = [
    # 登入彈窗: 簽到、活動、公告 (影片三個都出現了; 每天不一定有 → 各包一個分支)
    popup(5), popup(61), popup(227),
    f("基建BASE", confirm="next", timeout=30),
    f("鈴鐺", confirm={"appear": "待辦事項"}, timeout=15, on_fail="skip"),
    # 待辦: 三項同時找, 有就收 (收穫、信賴送伺服器 → 忙碌檢查)
    {"repeat": 3, "on_break": "break", "steps": [{"branch": [
        {"if": f("可收穫", confirm="gone", timeout=3, on_fail="skip", busy_check=True)},
        {"if": f("訂單交付", confirm="gone", timeout=3, on_fail="skip")},
        {"if": f("幹員信賴", 600, confirm="gone", timeout=3, on_fail="skip",
                 busy_check=True)}]}]},
    # 離開待辦模式: 以返回箭頭為原點點空白處
    f("返回", head="find", timeout=5), {"click": [557, 283], "frame": 653}, {"wait": 0.5},
    # 製造站加速
    f("進駐總覽", head="find"), {"click": [549, 734], "frame": 683, "confirm": "next"},
    f("生產面板箭頭", confirm="next", timeout=15),
    f("無人機加速", confirm="next"),
    f("最多", at=[1357, 501]), {"wait": 0.3},
    f("確定", confirm="gone", busy_check=True),
    f("收取", timeout=3, on_fail="skip"), {"wait": 0.5},
    f("返回", 792), {"wait": 1}, f("返回", 799, confirm="next"),
    # 拖地圖找會客室
    f("進駐總覽", 819, head="find"),
    {"drag": [1500, 600], "to": [660, 455], "frame": 830, "confirm": "next"},
    f("會客室", confirm="next"),
    f("線索面板", confirm="gone", timeout=15), {"wait": 1},
    {"branch": [{"if": f("線索交流彈窗", head="find", timeout=1.5, on_fail="skip"),
                 "then": [f("返回", 941, timeout=5, on_fail="break"), {"wait": 0.8}]}]},
    f("每日線索", confirm="next", timeout=3, on_fail="skip"),
    f("領取", confirm="gone", timeout=3, on_fail="skip", busy_check=True),
    f("快速置入", 1060, color=True, timeout=2, on_fail="skip", busy_check=True),
    # 快速置入後線索板自己關掉回到房間: 重開線索板 → 傳遞
    f("線索面板", 1100, confirm="next", timeout=15),
    f("傳遞線索", confirm="next", busy_check=True),
    f("快速傳遞", timeout=15), {"wait": 0.8},
    f("傳遞關閉", confirm="gone"),
    f("返回", 1227), {"wait": 1}, f("返回", 1248, confirm="next"),
    f("進駐總覽", 1287, timeout=15),
    # 換班: 製造站 1、貿易站 1 (類別標題定位 → 相對點 ⇄; 拖曳捲動)
    f("標題_製造站", 1460, head="find", pick={"top": 1}),
    {"drag": [1300, 700], "to": [1300, 411], "frame": 1462, "confirm": "gone",
     "busy_check": True},
    f("標題_製造站", 1480, head="find", pick={"top": 1}),
    {"click": [1848, 480], "frame": 1479, "busy_check": True},
    f("標題_製造站", 1500, head="find", pick={"top": 1}),
    {"drag": [1300, 900], "to": [1300, 194], "frame": 1503, "confirm": "gone",
     "busy_check": True},
    f("標題_貿易站", 1526, head="find", pick={"top": 1}),
    {"click": [1857, 565], "frame": 1527, "busy_check": True},
    # 好友
    f("非工作區", confirm="next"),
    f("幹員休息", timeout=3, on_fail="skip"), {"wait": 0.5},
    f("導航", confirm="next"), f("好友"),
    {"branch": [{"if": f("離開基建確認", confirm="gone", timeout=3, on_fail="skip")}]},
    f("好友列表", confirm="next", timeout=30),
    f("訪問基建", pick={"top": 1}, scroll="vertical", timeout=15),
    {"repeat": 10, "steps": [f("訪問下位", timeout=30, on_fail="break"),
                             f("訪問下位", head="wait_gone", timeout=5, on_fail="skip")]},
    # 信用交易所
    f("導航", 2683, confirm="next"), f("採購中心"), f("信用交易所", timeout=20),
    {"branch": [{"if": f("收取信用", confirm={"appear": "獲得物資"}, timeout=3,
                         on_fail="break", busy_check=True),
                 "then": [f("獲得物資", head="find", timeout=8, on_fail="break"),
                          {"click": [960, 877], "frame": 2785, "confirm": "gone"}]}]},
    {"repeat": 10, "steps": [{"branch": [buy(n) for n in (
        "採購_招聘許可", "採購_裝置", "採購_初級作戰記錄", "採購_破損裝置", "採購_赤金")],
        "on_break": "break"}]},
    f("導航", 3135, confirm="next"), f("公開招募"),
]

PLAN = {
    "video": VIDEO, "name": "早_繁中",
    "templates": {n: dict({"frame": fr, "box": b},
                          **({} if n in NO_ABSENT else {"absent": ABSENT}))
                  for n, (fr, b) in T.items()},
    "calibration": {"pair": ["主畫面設定鈕", "主畫面倉庫"], "frame": 270,
                    "fallback": {"pair": ["標題列圖示", "標題列關閉鈕"]}},
    "busy": {"template": "忙碌指示"},
    "steps": STEPS,
    "report": {
        "branches": ["開頭彈窗影片裡是簽到、活動、公告各一個；別天可能是其他彈窗或順序不同，實跑卡在基建入口時補分岔。",
                     "商店只寫了影片裡買過的五種商品；要買別的商品，照同一個分支格式加。"],
        "unexplained": [],
        "notes": ["影片裡沒建步驟的操作：進駐總覽第一次打開時的教學彈窗（關閉）、多按一次返回又重開進駐總覽、"
                  "切到工作區分頁、游標停在製造站 2 的 ⇄ 上沒點（f1497）——都是一次性的探索。",
                  "商品格會每天換位置，固定矩形照捲動軸 horizontal 拉成整列；另一列的同款要靠下一輪找。"],
    },
}

if __name__ == "__main__":
    with open(sys.argv[1], "w", encoding="utf-8") as fp:
        json.dump(PLAN, fp, ensure_ascii=False, indent=1)
    print(sys.argv[1])
