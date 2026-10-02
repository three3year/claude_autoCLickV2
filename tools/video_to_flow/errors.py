class ToolError(Exception):
    """影片轉流程拒絕繼續 (計畫有誤、輸入讀不到、換算條件可疑…).

    訊息直接給 Claude/使用者看: 說清楚哪裡錯、怎麼修。丟出時 profile
    一個檔案都還沒寫。
    """
