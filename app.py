import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scraper import aggregate_player_stats, get_all_boxscores, get_boxscore, get_schedule

st.set_page_config(
    page_title="Highland Lady Bulldogs",
    page_icon="🏀",
    layout="wide",
)

st.title("🏀 Highland Lady Bulldogs — 2025-26")


# ── Cached data loaders ────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def load_schedule() -> pd.DataFrame:
    return get_schedule()


@st.cache_data(ttl=3600, show_spinner=False)
def load_boxscore(event_id: int) -> dict:
    return get_boxscore(event_id)


@st.cache_data(ttl=3600, show_spinner=False)
def load_all_season_stats() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    schedule = load_schedule()
    off_df, def_df = get_all_boxscores(schedule)
    player_df = aggregate_player_stats(off_df, def_df)
    return off_df, def_df, player_df


# ── Load schedule (fast — 1 request) ──────────────────────────────────────────

with st.spinner("Loading schedule..."):
    schedule = load_schedule()

games = schedule[schedule["result"].isin(["W", "L"])].copy()
games["game_num"] = range(1, len(games) + 1)
games["label"] = games["date"] + " " + games["result"] + " vs " + games["opponent"]

tab_overview, tab_schedule, tab_players, tab_game = st.tabs(
    ["📊 Overview", "📅 Schedule", "👤 Player Stats", "🎮 Game Explorer"]
)


# ── TAB 1: OVERVIEW ───────────────────────────────────────────────────────────

with tab_overview:
    wins = (games["result"] == "W").sum()
    losses = (games["result"] == "L").sum()
    ppg = games["hld_score"].mean()
    opp_ppg = games["opp_score"].mean()
    avg_margin = games["margin"].mean()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Record", f"{wins}–{losses}")
    c2.metric("Win %", f"{wins / (wins + losses):.0%}")
    c3.metric("Pts Per Game", f"{ppg:.1f}")
    c4.metric("Opp PPG", f"{opp_ppg:.1f}")
    c5.metric("Avg Margin", f"{avg_margin:+.1f}")

    st.divider()

    # Scoring bar chart — green for wins, red for losses, opponent as line
    colors = ["#2ecc71" if r == "W" else "#e74c3c" for r in games["result"]]
    fig = go.Figure()
    fig.add_bar(
        x=games["label"],
        y=games["hld_score"],
        name="Highland",
        marker_color=colors,
    )
    fig.add_scatter(
        x=games["label"],
        y=games["opp_score"],
        mode="lines+markers",
        name="Opponent",
        line=dict(color="rgba(150,150,150,0.8)", dash="dot", width=2),
        marker=dict(size=5),
    )
    fig.update_layout(
        title="Points Scored by Game",
        xaxis_tickangle=-50,
        height=420,
        legend=dict(orientation="h", y=1.1),
        margin=dict(b=140),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Scoring margin with 5-game rolling average
    games["rolling_margin"] = games["margin"].rolling(5, min_periods=1).mean()
    fig2 = go.Figure()
    fig2.add_bar(
        x=games["label"],
        y=games["margin"],
        name="Margin",
        marker_color=colors,
        opacity=0.5,
    )
    fig2.add_scatter(
        x=games["label"],
        y=games["rolling_margin"],
        mode="lines",
        name="5-game avg",
        line=dict(color="#2980b9", width=3),
    )
    fig2.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
    fig2.update_layout(
        title="Scoring Margin (per game + 5-game rolling avg)",
        xaxis_tickangle=-50,
        height=350,
        legend=dict(orientation="h", y=1.1),
        margin=dict(b=140),
        hovermode="x unified",
    )
    st.plotly_chart(fig2, use_container_width=True)


# ── TAB 2: SCHEDULE ───────────────────────────────────────────────────────────

with tab_schedule:
    display = schedule.copy()
    display["Score"] = display.apply(
        lambda r: f"{int(r['hld_score'])}-{int(r['opp_score'])}"
        if pd.notna(r["hld_score"]) else "—",
        axis=1,
    )
    display = display.rename(columns={
        "date": "Date",
        "opponent": "Opponent",
        "location": "Location",
        "result": "W/L",
        "record": "Record",
    })

    def _color_result(val: str) -> str:
        if val == "W":
            return "background-color: #d4edda; color: #155724; font-weight: bold"
        if val == "L":
            return "background-color: #f8d7da; color: #721c24; font-weight: bold"
        return ""

    styled = (
        display[["Date", "Opponent", "Location", "W/L", "Score", "Record"]]
        .style.map(_color_result, subset=["W/L"])
    )
    st.dataframe(styled, use_container_width=True, height=950)


# ── TAB 3: PLAYER STATS ───────────────────────────────────────────────────────

with tab_players:
    st.caption(
        "Aggregates all 33 game box scores — takes ~20 seconds on first load, "
        "then cached for 1 hour."
    )

    if st.button("Load Season Player Stats", type="primary"):
        with st.spinner("Fetching all box scores... sit tight (runs once per hour)"):
            _, _, player_df = load_all_season_stats()

        if player_df.empty:
            st.warning("Could not load stats — check network connection.")
        else:
            # Pull out the columns the coach cares most about, in a sensible order
            priority = ["GP", "Pts", "PPG", "FG_made", "FG_att", "FG%",
                        "3FG_made", "3FG_att", "3FG%", "FT_made", "FT_att", "FT%",
                        "RBS", "RPG", "AST", "APG", "STL", "SPG", "TN", "BK"]
            cols = [c for c in priority if c in player_df.columns]
            remaining = [c for c in player_df.columns if c not in cols and c != "GP"]
            st.dataframe(
                player_df[cols + remaining],
                use_container_width=True,
                height=500,
            )

    else:
        st.info("Click the button above to load and aggregate the full season.")


# ── TAB 4: GAME EXPLORER ──────────────────────────────────────────────────────

with tab_game:
    schedule["sel_label"] = (
        schedule["date"] + "  "
        + schedule["result"].fillna("TBD") + "  vs  "
        + schedule["opponent"]
    )
    selected_label = st.selectbox("Pick a game", schedule["sel_label"])
    row = schedule[schedule["sel_label"] == selected_label].iloc[0]

    with st.spinner("Loading box score..."):
        bs = load_boxscore(int(row["event_id"]))

    if row["result"] == "W":
        result_badge = f"✅ W  {int(row['hld_score'])}-{int(row['opp_score'])}"
    elif row["result"] == "L":
        result_badge = f"❌ L  {int(row['hld_score'])}-{int(row['opp_score'])}"
    else:
        result_badge = "—"

    st.subheader(f"{row['date']}  ·  {row['opponent']}  ·  {result_badge}")
    st.caption(f"Location: {row['location']}  |  Season record after game: {row['record']}")
    st.divider()

    col_off, col_def = st.columns(2)
    with col_off:
        st.markdown("**Offensive Stats**")
        if not bs["offense"].empty:
            st.dataframe(bs["offense"], use_container_width=True, hide_index=True)
    with col_def:
        st.markdown("**Defensive Stats**  *(RBS · AST · STL · TN · BK · FLS)*")
        if not bs["defense"].empty:
            st.dataframe(bs["defense"], use_container_width=True, hide_index=True)
