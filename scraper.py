import re
import time
from io import StringIO

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://stats.stlhighschoolsports.com/sports/basketballgirls/stats"
TEAM_ID = 111
SEASON_ID = 961
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LadyBulldogsCoachApp/1.0)"}
_REQUEST_DELAY = 0.4  # seconds between requests — be a good citizen


def _get_html(path: str) -> str:
    resp = requests.get(f"{BASE_URL}/{path}", headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def get_schedule() -> pd.DataFrame:
    """
    Fetch the season schedule.

    Returns one row per game with columns:
      date, opponent, result, hld_score, opp_score, margin, record, event_id

    Page structure: Date | Time | Opponent | Result | Score(boxscore link) | Record
    The boxscore link lives on the score cell, not the opponent cell.
    """
    html = _get_html(f"teamschedule.php?s={SEASON_ID}&t={TEAM_ID}")
    soup = BeautifulSoup(html, "lxml")

    rows = []
    for tr in soup.select("table tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue

        # Find which cell holds the boxscore link and use its position as an anchor
        link_idx = next(
            (i for i, td in enumerate(tds)
             if td.find("a", href=lambda h: h and "boxscore.php" in h)),
            None,
        )
        if link_idx is None:
            continue

        link = tds[link_idx].find("a")
        event_id = int(link["href"].split("e=")[-1])
        score_text = tds[link_idx].get_text(strip=True)
        result = tds[link_idx - 1].get_text(strip=True)
        record = tds[link_idx + 1].get_text(strip=True) if link_idx + 1 < len(tds) else ""
        opponent = tds[2].get_text(strip=True)

        hld_score = opp_score = None
        if "-" in score_text and result in ("W", "L"):
            # Score format is always winner-loser (e.g. W 49-36 → Highland 49, Opp 36)
            a, b = (int(x) for x in score_text.split("-", 1))
            hld_score, opp_score = (a, b) if result == "W" else (b, a)

        rows.append({
            "date": tds[0].get_text(strip=True),
            "opponent": opponent,
            "result": result,
            "hld_score": hld_score,
            "opp_score": opp_score,
            "margin": (hld_score - opp_score) if hld_score is not None else None,
            "record": record,
            "event_id": event_id,
        })

    return pd.DataFrame(rows)


def get_boxscore(event_id: int) -> dict[str, pd.DataFrame]:
    """
    Fetch one game's box score.

    Returns {"offense": DataFrame, "defense": DataFrame}.
    Totals rows are removed; shot columns like "1-12" are split into
    separate _made and _att integer columns.
    """
    html = _get_html(f"boxscore.php?s={SEASON_ID}&e={event_id}")
    dfs = pd.read_html(StringIO(html))

    # Page tables: [0] quarter scores, [1] season records, [2] offense, [3] defense
    offense = _clean_boxscore(dfs[2]) if len(dfs) > 2 else pd.DataFrame()
    defense = _clean_boxscore(dfs[3]) if len(dfs) > 3 else pd.DataFrame()
    return {"offense": offense, "defense": defense}


def _clean_boxscore(df: pd.DataFrame) -> pd.DataFrame:
    """Remove header/totals rows and split 'X-Y' shot columns into made/att pairs."""
    # Drop rows where the name column looks like a header or totals row
    name_col = df.columns[1]
    df = df[~df[name_col].astype(str).isin(["—", "Name", "Totals"])].copy()
    df = df.reset_index(drop=True)

    # Split "X-Y" columns (e.g. FG, 2FG, 3FG, FT) into separate made/att columns
    shot_pattern = re.compile(r"^\d+-\d+$")
    for col in df.columns:
        sample = df[col].dropna().astype(str)
        if sample.empty:
            continue
        if sample.apply(lambda v: bool(shot_pattern.match(v))).mean() > 0.5:
            parts = df[col].astype(str).str.extract(r"^(\d+)-(\d+)$")
            df[f"{col}_made"] = pd.to_numeric(parts[0], errors="coerce").astype("Int64")
            df[f"{col}_att"] = pd.to_numeric(parts[1], errors="coerce").astype("Int64")
            df = df.drop(columns=[col])

    return df


def get_all_boxscores(schedule: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Fetch box scores for every game in schedule.

    Returns (offense_df, defense_df) with game-context columns added.
    Skips games that fail to load without raising.
    """
    off_frames: list[pd.DataFrame] = []
    def_frames: list[pd.DataFrame] = []

    for _, game in schedule.iterrows():
        try:
            bs = get_boxscore(int(game["event_id"]))
            for df, frames in [(bs["offense"], off_frames), (bs["defense"], def_frames)]:
                if df.empty:
                    continue
                enriched = df.copy()
                enriched["date"] = game["date"]
                enriched["opponent"] = game["opponent"]
                enriched["result"] = game["result"]
                frames.append(enriched)
            time.sleep(_REQUEST_DELAY)
        except Exception:
            continue

    off = pd.concat(off_frames, ignore_index=True) if off_frames else pd.DataFrame()
    def_ = pd.concat(def_frames, ignore_index=True) if def_frames else pd.DataFrame()
    return off, def_


def aggregate_player_stats(off_df: pd.DataFrame, def_df: pd.DataFrame) -> pd.DataFrame:
    """
    Combine offensive and defensive box score data into per-player season totals + averages.

    The second column of each DataFrame is the player name.
    """
    if off_df.empty:
        return pd.DataFrame()

    name_col = off_df.columns[1]

    def _sum_numeric(df: pd.DataFrame) -> pd.DataFrame:
        numeric = df.select_dtypes(include="number").columns.tolist()
        gp = df.groupby(name_col).size().rename("GP")
        totals = df.groupby(name_col)[numeric].sum()
        return totals.join(gp)

    off_agg = _sum_numeric(off_df)
    def_agg = _sum_numeric(def_df) if not def_df.empty else pd.DataFrame()

    combined = off_agg.join(def_agg, how="left", rsuffix="_def")

    # Derived per-game averages for key stats
    gp = combined["GP"]
    if "Pts" in combined.columns:
        combined["PPG"] = (combined["Pts"] / gp).round(1)
    for raw, avg_name in [("RBS", "RPG"), ("AST", "APG"), ("STL", "SPG")]:
        if raw in combined.columns:
            combined[avg_name] = (combined[raw] / gp).round(1)

    # Re-derive shot percentages from made/att totals
    for base, pct_col in [("FG", "FG%"), ("3FG", "3FG%"), ("FT", "FT%")]:
        made_col, att_col = f"{base}_made", f"{base}_att"
        if made_col in combined.columns and att_col in combined.columns:
            combined[pct_col] = (
                combined[made_col] / combined[att_col].replace(0, pd.NA) * 100
            ).round(1)

    return combined.sort_values("Pts", ascending=False) if "Pts" in combined.columns else combined
