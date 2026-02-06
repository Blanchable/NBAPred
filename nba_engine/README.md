# NBA Prediction Engine v3

A fully automated pregame NBA prediction engine with built-in tracking and automated score grading.

> **Built with Claude Opus 4.5** - This project was developed with assistance from Anthropic's Claude Opus 4.5 AI model.

## Features

- **One-Click GUI Application**: Beautiful graphical interface - just click a button to get predictions
- **Built-in SQLite Storage**: Persistent local database tracks all predictions without external dependencies
- **Automated Score Checking**: "Check Scores" button fetches final scores and grades picks automatically
- **Winrate Dashboard**: See overall and confidence-level win percentages at a glance
- **18-Factor Scoring System**: Advanced weighted model for accurate predictions
- **Automated Data Fetching**: Pulls team stats, player stats, and injury reports automatically
- **Excel Backup**: Optional Excel export for legacy compatibility

## How It Works

1. **Run Today's Predictions** - Click the button to generate predictions for today's games
2. **Check Scores** - Click "Check Scores" to fetch final scores and automatically grade picks
3. **View Stats** - Click "Refresh Stats" to see updated win rate statistics from the database
4. **Export to CSV** - Optionally export predictions to CSV for external analysis

### Data Storage

Predictions are stored in a persistent SQLite database:
- **Windows**: `%APPDATA%\NBA_Engine\nba_predictions.db`
- **macOS**: `~/Library/Application Support/NBA_Engine/nba_predictions.db`
- **Linux**: `~/.local/share/NBA_Engine/nba_predictions.db`

Excel backup (optional): `%APPDATA%\NBA_Engine\tracking\NBA_Engine_Tracking.xlsx`

### Overwrite-by-Day Rule

Running the engine multiple times on the same day will **replace** that day's predictions entirely. Only the most recent run for each calendar date is kept. Past dates are never modified.

## Quick Start (Windows)

### First Time Setup

1. **Install Python** (if not already installed):
   - Download from https://www.python.org/downloads/
   - **IMPORTANT**: Check ✅ "Add Python to PATH" during installation

2. **Run Setup**:
   - Double-click `setup.bat`
   - Wait for it to install dependencies (1-2 minutes)

3. **Run the App**:
   - Double-click `run_app.bat`
   - Click "Run Today's Predictions" button

### Quick Start (Linux/macOS)

```bash
# 1. Make scripts executable
chmod +x run_app.sh

# 2. Run setup and app
./run_app.sh
```

### Command Line

```powershell
# Windows (after setup)
.venv\Scripts\python.exe run_today.py

# Linux/macOS
./venv/bin/python run_today.py

# Refresh winrates only
python run_today.py --refresh
```

## Excel Tracking File

Location: `outputs/tracking/NBA_Engine_Tracking.xlsx`

### Picks Sheet

Contains all predictions with the following columns:

| Column | Description |
|--------|-------------|
| run_date | Date predictions were made (YYYY-MM-DD) |
| run_timestamp | Exact time of prediction run |
| game_id | NBA game identifier |
| away_team | Away team abbreviation |
| home_team | Home team abbreviation |
| pick_team | Predicted winner |
| pick_side | HOME or AWAY |
| confidence_level | HIGH, MEDIUM, or LOW |
| edge_score_total | Total edge score (-100 to +100) |
| projected_margin_home | Projected point margin |
| home_win_prob | Home team win probability |
| away_win_prob | Away team win probability |
| top_5_factors | Top contributing factors |
| data_confidence | Data quality (HIGH/MEDIUM/LOW) |
| actual_winner | **YOU FILL THIS IN** after game |
| correct | Auto-calculated (1=win, 0=loss) |
| notes | Optional notes |

### Summary Sheet

Auto-calculated statistics:
- Overall win/loss record and win %
- Win % by confidence level (HIGH/MEDIUM/LOW)
- Pending picks count

## GUI Features

### Performance Dashboard

Shows at the top of the window:
- **OVERALL**: Total win percentage and record
- **HIGH**: High confidence picks performance
- **MEDIUM**: Medium confidence picks performance  
- **LOW**: Low confidence picks performance
- **PENDING**: Number of picks awaiting results

### Buttons

- **Run Today's Predictions**: Generate and save predictions for today
- **Refresh Winrates**: Re-read Excel file and update dashboard
- **Open Tracking File**: Open the Excel file in your default app

### Tabs

- **Today's Predictions**: View all picks sorted by confidence
- **Factor Breakdown**: See detailed scoring factors for each game
- **Injuries**: View current injury report
- **Log**: See detailed run progress and any errors

## Project Structure

```
nba_engine/
├── ingest/
│   ├── schedule.py        # Fetches today's games
│   ├── team_stats.py      # Team statistics
│   ├── player_stats.py    # Player statistics
│   ├── injuries.py        # Injury report parsing
│   └── ...
├── model/
│   ├── point_system.py    # 21-factor scoring system
│   ├── star_impact.py     # Star player availability
│   ├── rotation_replacement.py  # Next-man-up evaluation
│   └── lineup_adjustment.py     # Lineup-adjusted strength
├── tracking/
│   ├── __init__.py
│   └── excel_tracker.py   # Excel workbook management
├── outputs/
│   └── tracking/          # Excel tracking file location
├── app.py                 # GUI application
├── run_today.py           # Command-line interface
├── requirements.txt       # Python dependencies
└── README.md
```

## The 18 Factors

| # | Factor | Weight | Description |
|---|--------|--------|-------------|
| 1 | Lineup Net Rating | 18 | Overall team strength (lineup-adjusted, softcapped) |
| 2 | Off vs Def Efficiency | 12 | Matchup-specific scoring |
| 3 | Shooting Advantage | 8 | Combined eFG% + 3P% (merged Shot Quality + 3P Edge) |
| 4 | Star Impact | 7 | Tiered star availability |
| 5 | Turnover Differential | 6 | Ball security |
| 6 | Rebounding | 6 | Board control (possession) |
| 7 | Rotation Replacement | 5 | Next-man-up quality |
| 8 | Rest/Fatigue | 5 | Days since last game |
| 9 | Variance Signal | 5 | 3P reliance (affects confidence) |
| 10 | Free Throw Differential | 4 | FT rate difference |
| 11 | Home Court | 4 | Fixed home advantage |
| 12 | Matchup Fit | 4 | Style compatibility |
| 13 | Home/Road Split | 3 | Home vs away performance (softcapped) |
| 14 | Rim Protection | 3 | Interior defense |
| 15 | Bench Depth | 3 | Rotation quality |
| 16 | Late Game Creation | 3 | Clutch performance |
| 17 | Perimeter Defense | 2 | Opponent 3P% allowed |
| 18 | Pace Control | 2 | Tempo advantage |

### Confidence Buckets

- **HIGH**: Confidence ≥ 72% AND at least 2 strong independent signals
- **MEDIUM**: Confidence ≥ 60% (or 72%+ without multi-signal confirmation)
- **LOW**: Confidence < 60%

## Troubleshooting

### "Please close NBA_Engine_Tracking.xlsx and try again"

The Excel file is open in another program. Close it and retry.

### "No games scheduled for today"

This is normal on days with no NBA games.

### "Could not load team stats"

The NBA API may be temporarily unavailable. The engine will use fallback values.

### Winrates not updating

Click "Refresh Winrates" to re-read the Excel file after making edits.

## Notes

- **Today Only**: This engine only supports today's slate. Historical analysis has been removed for simplicity.
- **Manual Results**: You must fill in `actual_winner` in the Excel file to track accuracy.
- **Overwrite Rule**: Re-running on the same day replaces previous predictions for that day.

## License

This project is for educational and personal use. NBA data is subject to NBA's terms of service.
