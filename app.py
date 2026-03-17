import os
import json
import numpy as np
import pandas as pd
import streamlit as st
import requests

DATA_DIR = "data"

# 中英對照庫
TEAM_CN = {"Atlanta Hawks": "老鷹", "Boston Celtics": "塞爾提克", "Brooklyn Nets": "籃網", "Charlotte Hornets": "黃蜂", "Chicago Bulls": "公牛", "Cleveland Cavaliers": "騎士", "Dallas Mavericks": "獨行俠", "Denver Nuggets": "金塊", "Detroit Pistons": "活塞", "Golden State Warriors": "勇士", "Houston Rockets": "火箭", "Indiana Pacers": "溜馬", "LA Clippers": "快艇", "Los Angeles Lakers": "湖人", "Memphis Grizzlies": "灰熊", "Miami Heat": "熱火", "Milwaukee Bucks": "公鹿", "Minnesota Timberwolves": "灰狼", "New Orleans Pelicans": "鵜鶘", "New York Knicks": "尼克", "Oklahoma City Thunder": "雷霆", "Orlando Magic": "魔術", "Philadelphia 76ers": "76人", "Phoenix Suns": "太陽", "Portland Trail Blazers": "拓荒者", "Sacramento Kings": "國王", "San Antonio Spurs": "馬刺", "Toronto Raptors": "暴龍", "Utah Jazz": "爵士", "Washington Wizards": "巫師"}
ODDS_API_TEAMS = {k: k for k in TEAM_CN.keys()}
ODDS_API_TEAMS["LA Clippers"] = "Los Angeles Clippers"
STAR_PLAYERS = {"Lakers": ["LeBron James", "Anthony Davis"], "Nuggets": ["Nikola Jokic", "Jamal Murray"], "Celtics": ["Jayson Tatum", "Jaylen Brown", "Kristaps Porzingis"], "Mavericks": ["Luka Doncic", "Kyrie Irving"], "Thunder": ["Shai Gilgeous-Alexander", "Chet Holmgren"], "Timberwolves": ["Anthony Edwards", "Rudy Gobert"], "Bucks": ["Giannis Antetokounmpo", "Damian Lillard"], "Warriors": ["Stephen Curry", "Draymond Green"], "Suns": ["Kevin Durant", "Devin Booker"], "76ers": ["Joel Embiid", "Tyrese Maxey"], "Clippers": ["Kawhi Leonard", "James Harden"], "Heat": ["Jimmy Butler", "Bam Adebayo"], "Kings": ["De'Aaron Fox", "Domantas Sabonis"]}

st.set_page_config(page_title="NBA AI V33 職業決策中心", layout="wide", page_icon="⚡")

# 檢查資料庫是否存在
if not os.path.exists(f"{DATA_DIR}/games.json"):
    st.error("⚠️ 找不到本地數據！請先在終端機執行 `python3 update_data.py`")
    st.stop()

# 讀取 JSON 資料 (毫秒級)
def load_json(filename):
    with open(f"{DATA_DIR}/{filename}", "r") as f: return json.load(f)

games_df = pd.DataFrame(load_json("games.json"))
line_score = pd.DataFrame(load_json("line_score.json"))
stats_df = pd.DataFrame(load_json("team_stats.json"))
b2b_data = load_json("b2b.json")
injuries_data = load_json("injuries.json")
raw_inj = injuries_data.get("raw", "")

def get_injury_impact(team_name, raw_text): 
    penalty, reports = 0, []
    mascot = team_name.split()[-1] 
    search_key = "76ers" if mascot == "76ers" else mascot 
    if search_key in STAR_PLAYERS: 
        for player in STAR_PLAYERS[search_key]: 
            if player.lower() in raw_text: 
                chunk = raw_text[raw_text.find(player.lower()):raw_text.find(player.lower())+200]
                if any(w in chunk for w in ["out", "expected", "surgery"]): 
                    penalty += 5.0; reports.append(f"🚨 {player} - 缺陣")
                elif any(w in chunk for w in ["questionable", "gtd"]): 
                    penalty += 2.5; reports.append(f"⚠️ {player} - 存疑")
    return min(penalty, 9.5), reports

# 🏆 職業級蒙地卡羅 (14.5 標準差)
def monte_carlo(h_pts, a_pts, sims=10000):
    sim_h = np.random.normal(loc=h_pts, scale=14.5, size=sims)
    sim_a = np.random.normal(loc=a_pts, scale=14.5, size=sims)
    return sim_h - sim_a, sim_h + sim_a

def calculate_ev(win_prob, odds=1.90): return (win_prob * (odds - 1)) - (1 - win_prob)

# UI 佈局
st.sidebar.header("⚡ 系統狀態")
st.sidebar.success(f"資料庫更新時間:\n{injuries_data.get('last_updated', '未知')}")
api_key = st.sidebar.text_input("輸入 The Odds API 金鑰", type="password")

st.title("🏀 NBA AI V33 職業盤: 瞬開決策引擎")

# 獲取即時盤口
live_odds = {}
if api_key:
    try:
        r = requests.get(f"https://api.the-odds-api.com/v4/sports/basketball_nba/odds/?apiKey={api_key}&regions=us&markets=spreads,totals&bookmakers=pinnacle", timeout=5).json()
        live_odds = {g.get('home_team'): {"spread": next((o['point'] for m in g.get('bookmakers', [{}])[0].get('markets', []) if m['key'] == 'spreads' for o in m['outcomes'] if o['name'] == g.get('home_team')), None)} for g in r if g.get('bookmakers')}
    except: pass

match_data, hit_count, total_finished = [], 0, 0
t_dict = dict(zip(stats_df['TEAM_ID'], stats_df['TEAM_NAME']))

for _, row in games_df.iterrows():
    h_id, a_id = row["HOME_TEAM_ID"], row["VISITOR_TEAM_ID"]
    h_n_en, a_n_en = t_dict.get(h_id, ""), t_dict.get(a_id, "")
    if not h_n_en or not a_n_en: continue
    h_n, a_n = TEAM_CN.get(h_n_en, h_n_en), TEAM_CN.get(a_n_en, a_n_en)
    
    try:
        h_pts_raw = line_score.loc[line_score['TEAM_ID'] == h_id, 'PTS'].values
        a_pts_raw = line_score.loc[line_score['TEAM_ID'] == a_id, 'PTS'].values
        h_act = int(h_pts_raw[0]) if len(h_pts_raw)>0 and pd.notna(h_pts_raw[0]) else 0
        a_act = int(a_pts_raw[0]) if len(a_pts_raw)>0 and pd.notna(a_pts_raw[0]) else 0
        is_finished = h_act > 0 and a_act > 0
        
        # 核心算力：PACE 校正與 ELO 戰績底蘊
        h_d, a_d = stats_df[stats_df["TEAM_ID"]==h_id].iloc[0], stats_df[stats_df["TEAM_ID"]==a_id].iloc[0]
        game_pace = (2 * h_d["PACE"] * a_d["PACE"]) / (h_d["PACE"] + a_d["PACE"])
        
        h_pen, h_rep = get_injury_impact(h_n_en, raw_inj)
        a_pen, a_rep = get_injury_impact(a_n_en, raw_inj)
        
        # B2B 判定
        if str(h_id) in b2b_data: h_pen += 3.5; h_rep.append("🔋 主隊 B2B 疲勞")
        if str(a_id) in b2b_data: 
            a_pen += 5.5 if b2b_data[str(a_id)] == "Away" else 4.0
            a_rep.append("✈️ 客隊 B2B 疲勞")
            
        elo_edge = (h_d["W_PCT"] - a_d["W_PCT"]) * 5.0
        
        # 最終預測強度
        proj_h = (h_d["OFF_RATING"]*0.55 + a_d["DEF_RATING"]*0.45) * (game_pace/100) + 2.5 - h_pen + elo_edge
        proj_a = (a_d["OFF_RATING"]*0.55 + h_d["DEF_RATING"]*0.45) * (game_pace/100) - a_pen - elo_edge
        
        sim_diff, _ = monte_carlo(proj_h, proj_a)
        prob_h = np.mean(sim_diff > 0)
        
        decision = "⚠️ 五五波"
        if prob_h > 0.55: decision = f"主勝 ({prob_h:.1%})"
        elif prob_h < 0.45: decision = f"客勝 ({(1-prob_h):.1%})"
        
        hit_status = "無"
        if is_finished and decision != "⚠️ 五五波":
            total_finished += 1
            if (prob_h > 0.5 and h_act > a_act) or (prob_h < 0.5 and a_act > h_act):
                hit_status = "✅"
                hit_count += 1
            else: hit_status = "❌"

        m_spread = live_odds.get(ODDS_API_TEAMS.get(h_n_en), {}).get("spread", "-")

        match_data.append({
            "對戰組合": f"{a_n} @ {h_n}", "AI淨勝分": f"{proj_a:.1f} : {proj_h:.1f}",
            "市場讓分(主)": m_spread, "最佳決策": decision, 
            "實際比分": f"{a_act}:{h_act}" if is_finished else "-", "勝負命中": hit_status,
            "reports": h_rep + a_rep, "proj_h": proj_h, "proj_a": proj_a
        })
    except: continue

if total_finished > 0:
    st.sidebar.divider()
    st.sidebar.metric("🎯 本日命中率", f"{(hit_count/total_finished):.1%}")

st.header("📊 V33 決策總表 (10,000 次模擬)")
st.dataframe(pd.DataFrame(match_data)[["對戰組合", "AI淨勝分", "市場讓分(主)", "最佳決策", "實際比分", "勝負命中"]], use_container_width=True)

st.divider()
st.header("🔍 深度解析儀 (14.5 職業級標準差)")
if match_data:
    s_g = st.selectbox("選擇分析場次：", match_data, format_func=lambda x: x["對戰組合"])
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("📝 陣容與變數報告")
        if s_g["reports"]:
            for r in s_g["reports"]: st.warning(r)
        else: st.success("✅ 雙方陣容完整")
    with col_b:
        st.subheader("🎲 手動盤口測試")
        u_s = st.number_input("台彩讓分 (主)", value=-2.5, step=0.5)
        sd, _ = monte_carlo(s_g['proj_h'], s_g['proj_a'])
        pc = np.mean(sd > -u_s)
        st.metric("預估過盤率", f"{pc:.1%}", delta=f"EV: {calculate_ev(pc):.1%}")
