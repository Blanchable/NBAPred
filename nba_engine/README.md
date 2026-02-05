# NBA Prediction Engine v3

A fully automated pregame NBA prediction engine with Excel-based tracking and winrate dashboard.

> **Built with Claude Opus 4.5** - This project was developed with assistance from Anthropic's Claude Opus 4.5 AI model.

## Features

- **One-Click GUI Application**: Beautiful graphical interface - just click a button to get predictions
- **Excel Tracking**: Single persistent workbook tracks all predictions with overwrite-by-day logic
- **Winrate Dashboard**: See overall and confidence-level win percentages at a glance
- **21-Factor Scoring System**: Advanced weighted model for accurate predictions
- **Automated Data Fetching**: Pulls team stats, player stats, and injury reports automatically

## How It Works

1. **Run Today's Predictions** - Click the button to generate predictions for today's games
2. **Excel Logging** - Predictions are saved to `outputs/tracking/NBA_Engine_Tracking.xlsx`
3. **Manual Result Entry** - Fill in the `actual_winner` column in Excel after games complete
4. **Winrate Tracking** - Click "Refresh Winrates" to see updated performance stats

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

## The 21 Factors

| # | Factor | Weight | Description |
|---|--------|--------|-------------|
| 1 | Net Rating | 11 | Overall team strength (lineup-adjusted, softcapped) |
| 2 | Star Impact | 10 | Tiered star availability |
| 3 | Off vs Def Efficiency | 10 | Matchup-specific scoring |
| 4 | Turnover Differential | 6 | Ball security |
| 5 | Rotation Replacement | 5 | Next-man-up quality |
| 6 | Shot Quality | 5 | Effective FG% |
| 7 | 3P Edge | 5 | Three-point shooting |
| 8 | Free Throw Rate | 5 | Getting to the line |
| 9 | Rebounding | 5 | Board control (possession) |
| 10 | Rest/Fatigue | 5 | Days since last game |
| 11 | Rim Protection | 5 | Interior defense |
| 12 | Perimeter Defense | 5 | Opponent 3P% allowed |
| 13 | Bench Depth | 5 | Rotation quality |
| 14 | Matchup Fit | 4 | Style compatibility |
| 15 | Home/Road Split | 3 | Home vs away performance (softcapped) |
| 16 | Home Court | 3 | Fixed home advantage |
| 17 | Pace Control | 3 | Tempo advantage |
| 18 | Late Game Creation | 3 | Clutch performance |
| 19 | Shooting Variance | 2 | 3P reliance (variance) |
| 20 | Coaching | 0 | Neutral (no data) |
| 21 | Motivation | 0 | Neutral (no data) |

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
