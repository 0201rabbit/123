import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import requests
from datetime import datetime, timedelta

# 延遲匯入，避免啟動時因缺少環境導致崩潰
try:
    from nba_api.stats.endpoints import scoreboardv2, leaguedashteamstats
except ImportError:
    st.error("缺失 nba_api 套件，請確保 requirements.txt 中已加入 nba_api")

# --- 1. 基礎設定與常數 ---
st.set_page_config(page_title="NBA AI V33 職業決策引擎", layout="wide", page_icon="⚡")
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

TEAM_CN = {
    "Atlanta Hawks": "老鷹", "Boston Celtics": "塞爾提克", "Brooklyn Nets": "籃網", "Charlotte Hornets": "黃蜂",
    "Chicago Bulls": "公牛", "Cleveland Cavaliers": "騎士", "Dallas Mavericks": "獨行俠", "Denver Nuggets": "金塊",
    "Detroit Pistons": "活塞", "Golden State Warriors": "勇士", "Houston Rockets": "火箭", "Indiana Pacers": "溜馬",
    "LA Clippers": "快艇", "Los Angeles Lakers": "湖人", "Memphis Grizzlies": "灰熊", "Miami Heat": "熱火",
    "Milwaukee Bucks": "公鹿", "Minnesota Timberwolves": "灰狼", "New Orleans Pelicans": "鵜鶘", "New York Knicks": "尼克",
    "Oklahoma City Thunder": "雷霆", "Orlando Magic": "魔術", "Philadelphia 76ers": "76人", "Phoenix Suns": "太陽",
    "Portland Trail Blazers": "拓荒者", "Sacramento Kings": "國王", "San Antonio Spurs": "馬刺", "Toronto Raptors": "暴龍",
    "Utah Jazz": "爵士", "Washington Wizards": "巫師"
}

STAR_PLAYERS = {
    "Lakers": ["LeBron James", "Anthony Davis"],
    "Nuggets": ["Nikola Jokic", "Jamal Murray"],
    "Celtics": ["Jayson Tatum", "Jaylen Brown", "Kristaps Porzingis"],
    "Mavericks": ["Luka Doncic", "Kyrie Irving"],
    "Thunder": ["Shai Gilgeous-Alexander", "Chet Holmgren"],
    "Timberwolves": ["Anthony Edwards", "Rudy Gobert"],
    "Bucks": ["Giannis Antetokounmpo", "Damian Lillard"],
    "Warriors": ["Stephen Curry", "Draymond Green"],
    "Suns": ["Kevin Durant", "Devin Booker"],
    "76ers": ["Joel Embiid", "Tyrese Maxey"],
    "Clippers": ["Kawhi Leonard", "James Harden"]
}

# --- 2. 側邊欄控制與狀態 (放在最前面，確保按鈕永遠出現) ---
st.sidebar.header("⚙️ 系統控制")

# 從 update_data 匯入更新邏輯
def trigger_update():
    from update_data import run_full_update
    with st.spinner("正在爬取 NBA 官網數據 (可能需要 20-30 秒)..."):
        if run_full_update():
            st.sidebar.success("✅ 數據同步成功！")
            st.rerun()
        else:
            st.sidebar.error("❌ 同步失敗，請查看 Logs。")

if st.sidebar.button("🔄 立即同步最新數據"):
    trigger_update()

# --- 3. 數據載入檢查 ---
def load_all_json():
    try:
        games = pd.read_json(f"{DATA_DIR}/games.json")
        line = pd.read_json(f"{DATA_DIR}/line_score.json")
        stats = pd.read_json(f"{DATA_DIR}/team_stats.json")
        with open(f"{DATA_DIR}/injuries.json", "r") as f:
            inj = json.load(f)
        with open(f"{DATA_DIR}/b2b.json", "r") as f:
            b2b = json.load(f)
        return games, line, stats, inj, b2b
    except:
        return None, None, None, None, None

# --- 4. 核心演算法 ---
def get_injury_impact(team_name, raw_text):
    penalty, reports = 0, []
    mascot = team_name.split()[-1]
    search_key = "76ers" if mascot == "76ers" else mascot
    if search_key in STAR_PLAYERS:
        for player in STAR_PLAYERS[search_key]:
            if player.lower() in raw_text:
                idx = raw_text.find(player.lower())
                chunk = raw_text[idx:idx+200]
                if any(w in chunk for w in ["out", "surgery", "expected to be out"]):
                    penalty += 5.5; reports.append(f"🚨 {player} - 缺陣")
                elif any(w in chunk for w in ["questionable", "gtd", "doubtful"]):
                    penalty += 2.5; reports.append(f"⚠️ {player} - 出戰成疑")
    return min(penalty, 9.5), reports

def monte_carlo(h_pts, a_pts, sims=10000):
    sim_h = np.random.normal(loc=h_pts, scale=14.5, size=sims)
    sim_a = np.random.normal(loc=a_pts, scale=14.5, size=sims)
    return sim_h - sim_a, sim_h + sim_a

# --- 5. 主畫面邏輯 ---
st.title("🏀 NBA AI V33 職業決策引擎")

games_df, line_df, stats_df, injuries_data, b2b_data = load_all_json()

if games_df is None or games_df.empty:
    st.warning("⚠️ 目前資料庫為空，請點擊左側「立即同步最新數據」按鈕。")
    st.stop()

st.sidebar.write(f"📅 數據時間: {injuries_data.get('last_updated', '未知')}")

# 開始計算對戰
match_data = []
t_dict = dict(zip(stats_df['TEAM_ID'], stats_df['TEAM_NAME']))
raw_inj = injuries_data.get("raw", "")

for _, row in games_df.iterrows():
    h_id, a_id = row["HOME_TEAM_ID"], row["VISITOR_TEAM_ID"]
    h_n_en, a_n_en = t_dict.get(h_id, ""), t_dict.get(a_id, "")
    if not h_n_en: continue

    # 進階攻防計算
    h_s = stats_df[stats_df["TEAM_ID"]==h_id].iloc[0]
    a_s = stats_df[stats_df["TEAM_ID"]==a_id].iloc[0]
    
    # PACE 校正
    game_pace = (2 * h_s["PACE"] * a_s["PACE"]) / (h_s["PACE"] + a_s["PACE"])
    
    # 懲罰項：傷兵與疲勞
    h_pen, h_rep = get_injury_impact(h_n_en, raw_inj)
    a_pen, a_rep = get_injury_impact(a_n_en, raw_inj)
    
    if str(h_id) in b2b_data: h_pen += 3.5; h_rep.append("🔋 主場 B2B 疲勞")
    if str(a_id) in b2b_data: a_pen += 5.0; a_rep.append("✈️ 客場 B2B 疲勞")
    
    # V33 預測公式
    elo_edge = (h_s["W_PCT"] - a_s["W_PCT"]) * 6.0
    proj_h = (h_s["OFF_RATING"]*0.55 + a_s["DEF_RATING"]*0.45) * (game_pace/100) + 2.5 - h_pen + elo_edge
    proj_a = (a_s["OFF_RATING"]*0.55 + h_s["DEF_RATING"]*0.45) * (game_pace/100) - a_pen - elo_edge
    
    # 蒙地卡羅勝率
    sim_diff, _ = monte_carlo(proj_h, proj_a)
    prob_h = np.mean(sim_diff > 0)
    
    # 實際比分
    h_act = line_df.loc[line_df['TEAM_ID'] == h_id, 'PTS'].values
    a_act = line_df.loc[line_df['TEAM_ID'] == a_id, 'PTS'].values
    act_str = f"{int(a_act[0])}:{int(h_act[0])}" if len(h_act)>0 and not np.isnan(h_act[0]) else "尚未開賽"

    match_data.append({
        "對戰組合": f"{TEAM_CN.get(a_n_en, a_n_en)} @ {TEAM_CN.get(h_n_en, h_n_en)}",
        "AI預計比分": f"{proj_a:.1f} : {proj_h:.1f}",
        "勝率 (主隊)": f"{prob_h:.1%}",
        "決策": "🔥 強勝" if prob_h > 0.6 else "✅ 傾向" if prob_h > 0.52 else "⚠️ 觀望" if prob_h > 0.48 else "✅ 傾向客" if prob_h > 0.4 else "🔥 強客勝",
        "實際比分": act_str,
        "reports": h_rep + a_rep,
        "proj_h": proj_h, "proj_a": proj_a
    })

# --- 6. 畫面呈現 ---
st.subheader("📊 今日賽程預測總表")
df_display = pd.DataFrame(match_data)[["對戰組合", "AI預計比分", "勝率 (主隊)", "決策", "實際比分"]]
st.dataframe(df_display, use_container_width=True)

st.divider()

st.subheader("🔍 蒙地卡羅深度解析儀")
if match_data:
    selected = st.selectbox("選擇分析場次：", match_data, format_func=lambda x: x["對戰組合"])
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"📝 **變數報告：{selected['對戰組合']}**")
        if selected["reports"]:
            for r in selected["reports"]: st.warning(r)
        else: st.success("✅ 雙方主力暫無傷情報告")
    with col2:
        u_spread = st.number_input("台彩讓分盤口 (主隊)", value=-2.5, step=0.5)
        sdiff, stot = monte_carlo(selected['proj_h'], selected['proj_a'])
        win_spread = np.mean(sdiff > -u_spread)
        st.metric("讓分過盤率 (主隊)", f"{win_spread:.1%}")
