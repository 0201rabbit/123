import streamlit as st 
import pandas as pd 
import requests 
import numpy as np
import time
from nba_api.stats.endpoints import leaguedashteamstats, scoreboardv2
from datetime import datetime, timedelta 

# ---------------------------------------------------------
# 0. 核心配置與對照庫 (維持 V32 輕量版)
# ---------------------------------------------------------
TEAM_CN = { 
    "Atlanta Hawks": "老鷹", "Boston Celtics": "塞爾提克", "Brooklyn Nets": "籃網", 
    "Charlotte Hornets": "黃蜂", "Chicago Bulls": "公牛", "Cleveland Cavaliers": "騎士", 
    "Dallas Mavericks": "獨行俠", "Denver Nuggets": "金塊", "Detroit Pistons": "活塞", 
    "Golden State Warriors": "勇士", "Houston Rockets": "火箭", "Indiana Pacers": "溜馬", 
    "LA Clippers": "快艇", "Los Angeles Lakers": "湖人", "Memphis Grizzlies": "灰熊", 
    "Miami Heat": "熱火", "Milwaukee Bucks": "公鹿", "Minnesota Timberwolves": "灰狼", 
    "New Orleans Pelicans": "鵜鶘", "New York Knicks": "尼克", "Oklahoma City Thunder": "雷霆", 
    "Orlando Magic": "魔術", "Philadelphia 76ers": "76人", "Phoenix Suns": "太陽", 
    "Portland Trail Blazers": "拓荒者", "Sacramento Kings": "國王", "San Antonio Spurs": "馬刺", 
    "Toronto Raptors": "暴龍", "Utah Jazz": "爵士", "Washington Wizards": "巫師" 
} 

ODDS_API_TEAMS = {k: k for k in TEAM_CN.keys()} 
ODDS_API_TEAMS["LA Clippers"] = "Los Angeles Clippers"

STAR_PLAYERS = { 
    "Lakers": ["LeBron James", "Anthony Davis", "D'Angelo Russell"],  
    "Nuggets": ["Nikola Jokic", "Jamal Murray", "Aaron Gordon"], 
    "Celtics": ["Jayson Tatum", "Jaylen Brown", "Kristaps Porzingis"],  
    "Mavericks": ["Luka Doncic", "Kyrie Irving"], 
    "Thunder": ["Shai Gilgeous-Alexander", "Jalen Williams", "Chet Holmgren"],  
    "Timberwolves": ["Anthony Edwards", "Rudy Gobert", "Karl-Anthony Towns"], 
    "Bucks": ["Giannis Antetokounmpo", "Damian Lillard"],  
    "Warriors": ["Stephen Curry", "Draymond Green"], 
    "Suns": ["Kevin Durant", "Devin Booker", "Bradley Beal"], 
    "76ers": ["Joel Embiid", "Tyrese Maxey"], 
    "Clippers": ["Kawhi Leonard", "James Harden"], 
    "Heat": ["Jimmy Butler", "Bam Adebayo"], 
    "Kings": ["De'Aaron Fox", "Domantas Sabonis"] 
} 

# ---------------------------------------------------------
# 1. 數據引擎：V32.7 回歸 V30 穩定模式
# ---------------------------------------------------------

@st.cache_data(ttl=10800) 
def fetch_injury_raw(): 
    try: 
        # 使用最簡單的 Header
        r = requests.get("https://www.cbssports.com/nba/injuries/", 
                         headers={"User-Agent": "Mozilla/5.0"}, 
                         timeout=10)
        return r.text.lower()
    except: return ""

def get_injury_impact(team_name, raw_text): 
    if not raw_text: return 0, []
    penalty, reports = 0, []
    mascot = team_name.split()[-1] 
    search_key = "76ers" if mascot == "76ers" else mascot 
    if search_key in STAR_PLAYERS: 
        for player in STAR_PLAYERS[search_key]: 
            if player.lower() in raw_text: 
                idx = raw_text.find(player.lower())
                chunk = raw_text[idx:idx+250]
                if any(word in chunk for word in ["out", "expected to be out", "surgery", "unavailable"]): 
                    penalty += 5.0; reports.append(f"🚨 [{TEAM_CN.get(team_name, mascot)}] {player} - 確定缺陣")
                elif any(word in chunk for word in ["questionable", "gtd", "decision", "doubtful"]): 
                    penalty += 2.5; reports.append(f"⚠️ [{TEAM_CN.get(team_name, mascot)}] {player} - 出戰成疑")
    return min(penalty, 9.5), reports

@st.cache_data(ttl=3600) 
def fetch_nba_lite(game_date_str): 
    date_obj = datetime.strptime(game_date_str, '%Y-%m-%d')
    date_api = date_obj.strftime('%m/%d/%Y') 
    
    # 🛡️ 核心：使用 V30 認證過的穩定 Headers
    headers = {
        'Host': 'stats.nba.com',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Referer': 'https://www.nba.com/',
    }
    
    try:
        # 1. 直接呼叫物件 (V30 模式)
        sb = scoreboardv2.ScoreboardV2(game_date=date_api, headers=headers, timeout=30)
        games_df = sb.get_data_frames()[0]
        line_score = sb.get_data_frames()[1]

        # 備援：若今日無數據載入昨日
        if games_df.empty:
            prev_api = (date_obj - timedelta(days=1)).strftime('%m/%d/%Y')
            sb_yest = scoreboardv2.ScoreboardV2(game_date=prev_api, headers=headers, timeout=30)
            games_df = sb_yest.get_data_frames()[0]
            line_score = sb_yest.get_data_frames()[1]

        time.sleep(2.0) # 給伺服器喘息空間
        
        # 2. 抓取基礎統計數據 (改回 Base 以求最快通關)
        ts = leaguedashteamstats.LeagueDashTeamStats(
            date_to_nullable=date_api, 
            headers=headers, 
            timeout=30,
            measure_type_detailed_defense='Base'
        )
        stats_df = ts.get_data_frames()[0]
        
        return games_df, line_score, stats_df
    except Exception as e:
        st.sidebar.warning(f"⚠️ 目前連線稍慢，建議按 'C' 清除快取再試一次。")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# ---------------------------------------------------------
# 2. 蒙地卡羅萬次模擬引擎
# ---------------------------------------------------------
def run_monte_carlo(h_pts, a_pts, n_sims=10000):
    sim_h = np.random.normal(loc=h_pts, scale=12.0, size=n_sims)
    sim_a = np.random.normal(loc=a_pts, scale=12.0, size=n_sims)
    return sim_h - sim_a, sim_h + sim_a

def calculate_ev(win_prob, odds=1.90):
    return (win_prob * (odds - 1)) - (1 - win_prob)

# ---------------------------------------------------------
# 3. UI 介面
# ---------------------------------------------------------
st.set_page_config(page_title="NBA AI V32.7 穩定回歸版", layout="wide", page_icon="🏀") 

st.sidebar.header("🗓️ 歷史回測與實戰控制") 
target_date = st.sidebar.date_input("選擇賽事日期", datetime.now() - timedelta(hours=8)) 
formatted_date = target_date.strftime('%Y-%m-%d') 

st.title(f"🏀 NBA AI V32 職業盤: 蒙地卡羅與 EV 決策引擎 ({formatted_date})") 

with st.spinner("啟動穩定引擎：正在參考 V30 路徑讀取數據..."): 
    games_df, line_df, stats_df = fetch_nba_lite(formatted_date) 
    raw_inj = fetch_injury_raw() 

if games_df.empty: 
    st.warning(f"📅 目前抓不到 {formatted_date} 的數據。")
    st.info("💡 解決辦法：\n1. 點擊畫面按鍵盤 'C' 清除快取。\n2. 登入 Streamlit 並 Reboot App。\n3. 若 V30 能動，請先用 V30 抓取，再回來重整此頁。")
else:
    match_data, hit_count, total_finished = [], 0, 0
    t_dict = dict(zip(stats_df['TEAM_ID'], stats_df['TEAM_NAME'])) if not stats_df.empty else {}

    st.header("📊 蒙地卡羅 EV 決策總表 (10,000 次模擬)")
    
    for _, row in games_df.iterrows(): 
        h_id, a_id = row["HOME_TEAM_ID"], row["VISITOR_TEAM_ID"] 
        h_n_en, a_n_en = t_dict.get(h_id, ""), t_dict.get(a_id, "")
        if not h_n_en or not a_n_en: continue

        h_n, a_n = TEAM_CN.get(h_n_en, h_n_en), TEAM_CN.get(a_n_en, a_n_en) 
        
        try: 
            h_pts_raw = line_df.loc[line_df['TEAM_ID'] == h_id, 'PTS'].values 
            a_pts_raw = line_df.loc[line_df['TEAM_ID'] == a_id, 'PTS'].values 
            h_act, a_act = (int(h_pts_raw[0]), int(a_pts_raw[0])) if len(h_pts_raw) > 0 and pd.notna(h_pts_raw[0]) else (0, 0)
            is_finished = (h_act > 0 and a_act > 0)

            h_d = stats_df[stats_df["TEAM_ID"] == h_id].iloc[0]
            a_d = stats_df[stats_df["TEAM_ID"] == a_id].iloc[0]
            
            h_pen, h_rep = get_injury_impact(h_n_en, raw_inj) 
            a_pen, a_rep = get_injury_impact(a_n_en, raw_inj) 
            
            proj_h = h_d["PTS"] + 2.5 - h_pen
            proj_a = a_d["PTS"] - a_pen

            sim_diff, _ = run_monte_carlo(proj_h, proj_a)
            prob_h = np.mean(sim_diff > 0)
            
            decision = f"⚠️ 五五波"
            if prob_h > 0.55: decision = f"主勝 ({prob_h:.1%})"
            elif prob_h < 0.45: decision = f"客勝 ({(1-prob_h):.1%})"

            hit_status = "無"
            if is_finished and "⚠️" not in decision:
                total_finished += 1
                if (prob_h > 0.5 and h_act > a_act) or (prob_h < 0.5 and a_act > h_act):
                    hit_status = "✅"; hit_count += 1
                else: hit_status = "❌"
            
            match_data.append({
                "對戰組合": f"{a_n} @ {h_n}", "AI淨勝分(客:主)": f"{proj_a:.1f} : {proj_h:.1f}", 
                "最佳 EV 決策": decision, "實際比分": f"{a_act} : {h_act}" if is_finished else "-", 
                "勝負命中": hit_status, "reports": h_rep + a_rep, "proj_h": proj_h, "proj_a": proj_a
            }) 
        except: continue 

    df_display = pd.DataFrame(match_data)
    if not df_display.empty:
        st.dataframe(df_display[["對戰組合", "AI淨勝分(客:主)", "最佳 EV 決策", "實際比分", "勝負命中"]], use_container_width=True)

    if total_finished > 0:
        st.sidebar.divider()
        st.sidebar.metric("🎯 本日 EV 策略命中率", f"{(hit_count/total_finished):.1%}")

st.caption("NBA AI V32.7 - 穩定回歸版：參考 V30 成功路徑，捨棄強攻，回歸標準連線。")
