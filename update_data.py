import os
import json
import time
import requests
import random
import pandas as pd
from datetime import datetime, timedelta

# 🏆 核心防護：全域套用 Session 與 Headers，讓 Akamai 視為正常瀏覽器
from nba_api.stats.library.http import NBAStatsHTTP
from nba_api.stats.endpoints import scoreboardv2, leaguedashteamstats

session = requests.Session()
NBAStatsHTTP._session = session
NBAStatsHTTP.headers = {
    "Host": "stats.nba.com",
    "Connection": "keep-alive",
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://www.nba.com/",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true"
}

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

def fetch_games(target_date):
    print(f"🔄 [1/4] 正在抓取 {target_date} 賽程...")
    sb = scoreboardv2.ScoreboardV2(game_date=target_date, timeout=30)
    games_df = sb.get_data_frames()[0]
    line_score = sb.get_data_frames()[1]
    
    games_df.to_json(f"{DATA_DIR}/games.json", orient="records")
    line_score.to_json(f"{DATA_DIR}/line_score.json", orient="records")
    print(f"✅ 賽程抓取完成 ({len(games_df)} 場)")

def fetch_team_stats(date_api):
    print(f"🔄 [2/4] 正在抓取進階攻防數據 (OFF_RTG, DEF_RTG, PACE)...")
    ts = leaguedashteamstats.LeagueDashTeamStats(
        measure_type_detailed_defense="Advanced", 
        date_to_nullable=date_api, timeout=30
    )
    df = ts.get_data_frames()[0]
    df.to_json(f"{DATA_DIR}/team_stats.json", orient="records")
    print("✅ 攻防數據抓取完成")

def fetch_b2b(yesterday_str):
    print(f"🔄 [3/4] 正在抓取昨日賽程計算 B2B 疲勞...")
    y_sb = scoreboardv2.ScoreboardV2(game_date=yesterday_str, timeout=30)
    y_games = y_sb.get_data_frames()[0]
    
    b2b_dict = {}
    for _, row in y_games.iterrows():
        b2b_dict[row["HOME_TEAM_ID"]] = "Home"
        b2b_dict[row["VISITOR_TEAM_ID"]] = "Away"
        
    with open(f"{DATA_DIR}/b2b.json", "w") as f:
        json.dump(b2b_dict, f)
    print("✅ B2B 數據計算完成")

def fetch_injuries():
    print("🔄 [4/4] 正在抓取 CBS 傷兵名單...")
    try:
        r = requests.get("https://www.cbssports.com/nba/injuries/", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        with open(f"{DATA_DIR}/injuries.json", "w") as f:
            json.dump({"raw": r.text.lower(), "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, f)
        print("✅ 傷兵名單抓取完成")
    except:
        print("⚠️ 傷兵抓取失敗，保留舊資料")

def run_update():
    print("🚀 啟動 NBA AI V33 數據更新程序 (ETL)")
    # 計算台灣時間對應的美國日期 (減 12 小時最保險)
    target_dt = datetime.now() - timedelta(hours=12)
    today_str = target_dt.strftime("%Y-%m-%d")
    date_api = target_dt.strftime("%m/%d/%Y")
    yest_str = (target_dt - timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        fetch_games(today_str)
        time.sleep(1.5) # 職業級 1.5 秒安全間隔
        
        fetch_team_stats(date_api)
        time.sleep(1.5)
        
        fetch_b2b(yest_str)
        time.sleep(1.0)
        
        fetch_injuries()
        print("\n🎉 更新大成功！資料已存入 data/，請安心開啟 app.py")
    except Exception as e:
        print(f"\n🚨 發生錯誤: {e}")

if __name__ == "__main__":
    run_update()
