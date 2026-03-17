import streamlit as st
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime

# --- 1. 基礎設定 ---
st.set_page_config(page_title="NBA AI V33 職業決策引擎", layout="wide", page_icon="⚡")
DATA_DIR = "data"

# 核心對照表
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
    "Warriors": ["Stephen Curry", "Draymond Green"]
}

# --- 2. 側邊欄：更新按鈕 (放在最前面，防止 st.stop 擋住它) ---
st.sidebar.header("⚙️ 系統控制")

if st.sidebar.button("🔄 立即同步最新數據"):
    try:
        from update_data import run_full_update
        with st.spinner("正在同步 NBA 官網數據..."):
            if run_full_update():
                st.sidebar.success("✅ 同步成功！")
                st.rerun()
            else:
                st.sidebar.error("❌ 同步失敗，請檢查 Logs。")
    except ImportError:
        st.sidebar.error("❌ 找不到 update_data.py，請確認檔案已上傳至 GitHub。")
    except Exception as e:
        st.sidebar.error(f"❌ 錯誤: {e}")

# --- 3. 數據檢查與載入 ---
if not os.path.exists(f"{DATA_DIR}/games.json") or not os.path.exists(f"{DATA_DIR}/team_stats.json"):
    st.warning("⚠️ 目前資料庫為空。")
    st.info("請點擊左側 **「🔄 立即同步最新數據」** 按鈕來獲取資料。")
    st.stop()

def load_data():
    g = pd.read_json(f"{DATA_DIR}/games.json")
    l = pd.read_json(f"{DATA_DIR}/line_score.json")
    s = pd.read_json(f"{DATA_DIR}/team_stats.json")
    with open(f"{DATA_DIR}/injuries.json", "r") as f:
        inj_data = json.load(f)
    with open(f"{DATA_DIR}/b2b.json", "r") as f:
        b2b_data = json.load(f)
    return g, l, s, inj_data, b2b_data

games_df, line_df, stats_df, injuries_json, b2b_json = load_data()
st.sidebar.success(f"📅 資料庫更新時間:\n{injuries_json.get('last_updated', '未知')}")

# --- 4. 輔助運算函式 ---
def get_injury_impact(team_name, raw_text):
    penalty, reports = 0, []
    mascot = team_name.split()[-1]
    if mascot in STAR_PLAYERS:
        for p in STAR_PLAYERS[mascot]:
            if p.lower() in raw_text:
                penalty += 4.5
                reports.append(f"🚨 {p} 可能缺陣")
    return min(penalty, 9.5), reports

def monte_carlo(h_pts, a_pts, sims=10000):
    sim_h = np.random.normal(loc=h_pts, scale=14.5, size=sims)
    sim_a = np.random.normal(loc=a_pts, scale=14.5, size=sims)
    return sim_h - sim_a, sim_h + sim_a

# --- 5. 主畫面分析邏輯 ---
st.title("🏀 NBA AI V33 職業決策引擎")

match_data = []
t_dict = dict(zip(stats_df['TEAM_ID'], stats_df['TEAM_NAME']))
raw_inj = injuries_json.get("raw", "")

for _, row in games_df.iterrows():
    h_id, a_id = row["HOME_TEAM_ID"], row["VISITOR_TEAM_ID"]
    h_n_en, a_n_en = t_dict.get(h_id, ""), t_dict.get(a_id, "")
    if not h_n_en or not a_n_en: continue

    # 進階數據
    h_s = stats_df[stats_df["TEAM_ID"]==h_id].iloc[0]
    a_s = stats_df[stats_df["TEAM_ID"]==a_id].iloc[0]
    
    # PACE 校正與預測公式
    game_pace = (2 * h_s["PACE"] * a_s["PACE"]) / (h_s["PACE"] + a_s["PACE"])
    h_pen, h_rep = get_injury_impact(h_n_en, raw_inj)
    a_pen, a_rep = get_injury_impact(a_n_en, raw_inj)
    
    # 疲勞判定
    if str(h_id) in b2b_json: h_pen += 3.0; h_rep.append("🔋 B2B 疲勞")
    if str(a_id) in b2b_json: a_pen += 4.5; a_rep.append("✈️ B2B 疲勞")

    elo_edge = (h_s["W_PCT"] - a_s["W_PCT"]) * 5.5
    proj_h = (h_s["OFF_RATING"]*0.55 + a_s["DEF_RATING"]*0.45) * (game_pace/100) + 2.5 - h_pen + elo_edge
    proj_a = (a_s["OFF_RATING"]*0.55 + h_s["DEF_RATING"]*0.45) * (game_pace/100) - a_pen - elo_edge

    # 模擬
    sdiff, _ = monte_carlo(proj_h, proj_a)
    prob_h = np.mean(sdiff > 0)

    # 實際比分
    h_act = line_df.loc[line_df['TEAM_ID'] == h_id, 'PTS'].values
    a_act = line_df.loc[line_df['TEAM_ID'] == a_id, 'PTS'].values
    act_str = f"{int(a_act[0])}:{int(h_act[0])}" if len(h_act)>0 and not np.isnan(h_act[0]) else "-"

    match_data.append({
        "對戰組合": f"{TEAM_CN.get(a_n_en, a_n_en)} @ {TEAM_CN.get(h_n_en, h_n_en)}",
        "AI預計比分": f"{proj_a:.1f} : {proj_h:.1f}",
        "勝率 (主隊)": f"{prob_h:.1%}",
        "最佳決策": "🔥 強勝" if prob_h > 0.6 else "✅ 傾向" if prob_h > 0.52 else "⚠️ 觀望" if prob_h > 0.48 else "✅ 傾向客" if prob_h > 0.4 else "🔥 強客勝",
        "實際比分": act_str,
        "reports": h_rep + a_rep,
        "proj_h": proj_h, "proj_a": proj_a
    })

# --- 6. 畫面呈現 ---
st.subheader("📊 今日賽程預測總表")
st.dataframe(pd.DataFrame(match_data)[["對戰組合", "AI預計比分", "勝率 (主隊)", "最佳決策", "實際比分"]], use_container_width=True)

st.divider()

st.subheader("🔍 深度分析儀")
if match_data:
    selected = st.selectbox("選擇場次：", match_data, format_func=lambda x: x["對戰組合"])
    c1, c2 = st.columns(2)
    with c1:
        st.write("**變數報告：**")
        if selected["reports"]:
            for r in selected["reports"]: st.warning(r)
        else: st.success("✅ 雙方狀態穩定")
    with c2:
        u_spread = st.number_input("輸入台彩主隊讓分", value=-2.5, step=0.5)
        sd, _ = monte_carlo(selected['proj_h'], selected['proj_a'])
        st.metric("讓分過盤率 (主隊)", f"{np.mean(sd > -u_spread):.1%}")
