# Lady Bulldogs Hoops — Coach Dashboard

Streamlit app for the Highland Bulldogs girls basketball coaching staff.
Pulls live data from stats.stlhighschoolsports.com.

## Running the app

```powershell
# First time only
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Every time
streamlit run app.py
```

## Project constants

| Key | Value |
|-----|-------|
| Team ID | 111 |
| Season ID | 961 |
| Base URL | https://stats.stlhighschoolsports.com/sports/basketballgirls/stats |

## Key pages

- Schedule: `teamschedule.php?s=961&t=111`
- Box score: `boxscore.php?s=961&e={event_id}`
- Player: `teamstatplayer.php?t=111&s=961&p={player_id}`

## Architecture

- `scraper.py` — all HTTP + HTML parsing. No Streamlit imports here.
- `app.py` — all Streamlit UI. Calls scraper functions only.

## Box score column reference

**Offensive:** #, Name, Pts, FG (X-Y), FG%, 2FG (X-Y), 2F%, 3FG (X-Y), 3F%, FT (X-Y), FT%
**Defensive:** #, Name, RBS, OF, DF, AST, STL, TN, BK, FLS

## Notes

- `get_all_boxscores()` makes 33 HTTP requests — it's cached for 1 hour in the app.
- Be a good citizen: a 0.4s delay is baked in between requests.
- The score format on the schedule page is always winner-loser (e.g. W 49-36 means Highland 49, Opponent 36).
- Schedule page columns: Date | Time | Opponent | Result | Score(boxscore link) | Record — the boxscore link is on the score cell, not the opponent cell.
- Box score page has 4 tables: [0] quarter scores, [1] season records, [2] offensive stats, [3] defensive stats.
