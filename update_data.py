import json
import time
import requests
import random
import pandas as pd
import os
from datetime import datetime, timedelta
from nba_api.stats.endpoints import scoreboardv2, leaguedashteamstats

DATA_DIR = "data"

def run_full_update():
    os.makedirs(DATA_DIR, exist_ok=True)
    target_dt = datetime.now() - timedelta(hours=8)
    today_str = target_dt.strftime("%Y-%m-%d")
    date_api = target_dt.strftime("%m/%d/%Y")
    yest_str = (target_dt - timedelta(days=1)).strftime("%Y-%m-%d")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.nba.com/",
        "Connection": "keep-alive"
    }

    try:
        # 1. 抓取賽程
        sb = scoreboardv2.ScoreboardV2(game_date=today_str, headers=headers, timeout=30)
        sb.get_data_frames()[0].to_json(f"{DATA_DIR}/games.json", orient="records")
        sb.get_data_frames()[1].to_json(f"{DATA_DIR}/line_score.json", orient="records")
        time.sleep(2)

        # 2. 抓取進階數據
        ts = leaguedashteamstats.LeagueDashTeamStats(measure_type_detailed_defense="Advanced", date_to_nullable=date_api, headers=headers, timeout=30)
        ts.get_data_frames()[0].to_json(f"{DATA_DIR}/team_stats.json", orient="records")
        time.sleep(2)

        # 3. 抓取 B2B
        sb_yest = scoreboardv2.ScoreboardV2(game_date=yest_str, headers=headers, timeout=30)
        y_games = sb_yest.get_data_frames()[0]
        b2b_dict = {str(row["HOME_TEAM_ID"]): "Home" for _, row in y_games.iterrows()}
        b2b_dict.update({str(row["VISITOR_TEAM_ID"]): "Away" for _, row in y_games.iterrows()})
        with open(f"{DATA_DIR}/b2b.json", "w") as f:
            json.dump(b2b_dict, f)

        # 4. 傷兵名單
        r = requests.get("https://www.cbssports.com/nba/injuries/", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        with open(f"{DATA_DIR}/injuries.json", "w") as f:
            json.dump({"raw": r.text.lower(), "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M")}, f)

        return True
    except Exception as e:
        print(f"Error: {e}")
        return False
