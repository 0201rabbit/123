import json
import time
import requests
import random
import pandas as pd
import os
from datetime import datetime, timedelta
from nba_api.stats.endpoints import scoreboardv2, leaguedashteamstats

DATA_DIR = "data"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://www.nba.com/",
    "Connection": "keep-alive"
}

# 名稱改成 run_full_update，這樣 app.py 才能對應到
def run_full_update():
    os.makedirs(DATA_DIR, exist_ok=True)
    target_dt = datetime.now() - timedelta(hours=8)
    today_str = target_dt.strftime("%Y-%m-%d")
    date_api = target_dt.strftime("%m/%d/%Y")
    yest_str = (target_dt - timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        # 1. 抓取今日賽程與比分
        sb = scoreboardv2.ScoreboardV2(game_date=today_str, headers=headers, timeout=30)
        sb.get_data_frames()[0].to_json(f"{DATA_DIR}/games.json", orient="records")
        sb.get_data_frames()[1].to_json(f"{DATA_DIR}/line_score.json", orient="records")

        # 2. 抓取進階攻防數據 (PACE, OFF_RTG 等)
        ts = leaguedashteamstats.LeagueDashTeamStats(
            measure_type_detailed_defense="Advanced", 
            date_to_nullable=date_api, 
            headers=headers,
            timeout=30
        )
        ts.get_data_frames()[0].to_json(f"{DATA_DIR}/team_stats.json", orient="records")

        # 3. 抓取昨日賽程以計算 B2B 疲勞
        sb_yest = scoreboardv2.ScoreboardV2(game_date=yest_str, headers=headers, timeout=30)
        y_games = sb_yest.get_data_frames()[0]
        b2b_dict = {}
        for _, row in y_games.iterrows():
            b2b_dict[str(row["HOME_TEAM_ID"])] = "Home"
            b2b_dict[str(row["VISITOR_TEAM_ID"])] = "Away"
        with open(f"{DATA_DIR}/b2b.json", "w") as f:
            json.dump(b2b_dict, f)

        # 4. 抓取 CBS 傷兵名單
        r = requests.get("https://www.cbssports.com/nba/injuries/", timeout=15)
        with open(f"{DATA_DIR}/injuries.json", "w") as f:
            json.dump({
                "raw": r.text.lower(), 
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, f)

        return True
    except Exception as e:
        print(f"Error during update: {e}")
        return False
