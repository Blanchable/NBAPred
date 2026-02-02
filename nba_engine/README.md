# NBA Prediction Engine v1

A fully automated pregame NBA prediction engine that runs locally and generates predictions for today's games using team net ratings and home court advantage.

> **Built with Claude Opus 4.5** - This project was developed with assistance from Anthropic's Claude Opus 4.5 AI model.

## Features

- **One-Click GUI Application**: Beautiful graphical interface - just click a button to get predictions
- **Automated Slate Fetching**: Automatically retrieves today's NBA games from the official NBA API
- **Injury Report Integration**: Downloads and parses the latest official NBA injury report PDF
- **Simple Prediction Model**: Uses team net ratings (per 100 possessions) with home court adjustment
- **CSV Outputs**: Saves predictions and injuries to timestamped CSV files
- **Standalone Executable**: Can be built into a `.exe` file that runs without Python installed

## GUI Features

The graphical application (`app.py`) includes:

- **Predictions Tab**: View all games with projected margins and win probabilities
- **Injuries Tab**: Color-coded injury list (Out=red, Doubtful=orange, Questionable=yellow, Probable=green)
- **Log Tab**: See detailed progress and any errors
- **Save Button**: Export results to CSV with one click
- **Auto-Setup**: The launcher scripts will automatically set up the environment on first run

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
   - Click "Fetch Today's Predictions" button

### Build Standalone Executable (Optional)

Want to run without Python? Create a `.exe` file:

1. Double-click `build_exe.bat`
2. Wait for build to complete
3. Find `NBA_Predictor.exe` in the `dist/` folder
4. Copy it anywhere and double-click to run!

### Quick Start (Linux/macOS)

```bash
# 1. Make scripts executable
chmod +x run_app.sh

# 2. Run setup and app
./run_app.sh
```

### Command Line Alternative

For automation or scripting:

```powershell
# Windows (after setup)
.venv\Scripts\python.exe run_today.py

# Linux/macOS
./venv/bin/python run_today.py
```

## Project Structure

```
nba_engine/
├── ingest/
│   ├── __init__.py
│   ├── schedule.py      # Fetches today's games and team ratings
│   └── injuries.py      # Downloads and parses injury report PDF
├── model/
│   ├── __init__.py
│   └── pregame.py       # Prediction model (net rating + home court)
├── outputs/             # Generated CSV and PDF files
├── app.py               # GUI application
├── run_today.py         # Command-line interface
├── setup.bat            # First-time setup (Windows)
├── run_app.bat          # Run the app (Windows)
├── build_exe.bat        # Build standalone .exe (Windows)
├── run_app.sh           # Linux/macOS launcher
├── requirements.txt     # Python dependencies
└── README.md
```

## Output Files

After running, the `outputs/` folder will contain:

- `predictions_YYYYMMDD_HHMMSS.csv` - Predictions for each game
- `injuries_YYYYMMDD_HHMMSS.csv` - Parsed injury report entries
- `injury_report_YYYYMMDD_HHMMSS.pdf` - Downloaded injury report PDF
- `latest_injury_url.txt` - Cache file for injury report URL

### Predictions CSV Columns

| Column | Description |
|--------|-------------|
| `away_team` | Away team abbreviation |
| `home_team` | Home team abbreviation |
| `projected_margin_home` | Projected point margin (positive = home favored) |
| `home_win_prob` | Home team win probability (0-1) |
| `away_win_prob` | Away team win probability (0-1) |
| `start_time_utc` | Game start time in UTC |

### Injuries CSV Columns

| Column | Description |
|--------|-------------|
| `team` | Team abbreviation |
| `player` | Player name |
| `status` | Out, Doubtful, Questionable, or Probable |
| `reason` | Injury/reason description |

## Model Details (v2 - 20 Factor Point System)

### How It Works

The v2 model evaluates each game using **20 weighted factors** that sum to 100 points. Each factor produces a signed value from -1 (away advantage) to +1 (home advantage), which is multiplied by its weight.

### The 20 Factors

| # | Factor | Weight | Description |
|---|--------|--------|-------------|
| 1 | Net Rating | 14 | Overall team strength (points per 100 possessions) |
| 2 | Star Availability | 13 | Impact of injuries on key players |
| 3 | Off vs Def Efficiency | 8 | Matchup-specific scoring efficiency |
| 4 | Turnover Differential | 7 | Ball security advantage |
| 5 | Shot Quality | 7 | Effective field goal percentage |
| 6 | 3P Edge | 7 | Three-point shooting volume and accuracy |
| 7 | Free Throw Rate | 6 | Ability to get to the line |
| 8 | Rebounding | 6 | Overall rebounding advantage |
| 9 | Home Court | 5 | Fixed home court advantage |
| 10 | Rest/Fatigue | 5 | Days since last game |
| 11 | Rim Protection | 4 | Interior defense |
| 12 | Perimeter Defense | 4 | Opponent 3P% allowed |
| 13 | Matchup Fit | 4 | Style compatibility |
| 14 | Bench Depth | 4 | Rotation quality |
| 15 | Pace Control | 3 | Tempo advantage |
| 16 | Late Game Creation | 3 | Clutch performance proxy |
| 17 | Coaching | 3 | Neutral in v2 (no data) |
| 18 | Foul Trouble Risk | 2 | Team foul rate |
| 19 | Shooting Variance | 2 | 3P reliance (variance) |
| 20 | Motivation | 1 | Neutral in v2 (no data) |

### Edge Score to Win Probability

```
EdgeScore = Σ(weight_i × signed_value_i)  # Range: -100 to +100
WinProbHome = 1 / (1 + exp(-EdgeScore / 12.0))
ProjectedMargin = EdgeScore / 6.0
```

### Output Columns

| Column | Description |
|--------|-------------|
| `predicted_winner` | Team abbreviation of predicted winner |
| `edge_score` | Total edge score (-100 to +100) |
| `home_win_prob` | Home team win probability |
| `away_win_prob` | Away team win probability |
| `projected_margin_home` | Projected point margin |
| `top_5_factors` | Top 5 contributing factors |

### Factor Breakdown Tab

The GUI includes a "Factor Breakdown" tab that shows all 20 factors for each game:
- **Factor Name**: The factor being evaluated
- **Weight**: How much this factor matters (out of 100)
- **Signed Value**: Direction and magnitude (-1 to +1)
- **Contribution**: Weight × Signed Value
- **Inputs Used**: The actual data used for calculation

## Data Sources

1. **Today's Games**: `nba_api.live.nba.endpoints.scoreboard.ScoreBoard()`
2. **Team Ratings**: `nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats()`
3. **Injury Reports**: NBA official PDFs from `https://ak-static.cms.nba.com/referee/injury/`

## Known Limitations

### V1 Limitations

- **Injury parsing is heuristic**: The PDF parser uses text extraction and pattern matching. Some injury entries may be missed or incorrectly split. This will be improved in future versions.

- **Simple model**: The prediction model uses only team net ratings and a fixed home court value. It does not account for:
  - Individual player impacts/injuries
  - Back-to-back games
  - Travel fatigue
  - Matchup-specific factors
  - Recent form/momentum

- **No playoff handling**: The model assumes regular season context only.

- **No market comparison**: V1 does not compare predictions against betting markets or track accuracy.

### API Dependencies

- Requires internet connection to fetch data
- NBA API may have rate limits during high-traffic periods
- Injury report PDFs are not always available (especially off-season)

## Extending the Engine

### Adding a Point System

The `model/pregame.py` module is structured for easy extension. To add a point-based scoring system:

1. Implement adjustments in `predict_margin_with_points()`:

```python
def predict_margin_with_points(
    home_net: float,
    away_net: float,
    home_injuries: list = None,
    away_injuries: list = None,
) -> float:
    base_margin = predict_margin(home_net, away_net)
    
    # Add your point adjustments here
    adjustment = 0.0
    adjustment += calculate_injury_impact(home_injuries, away_injuries)
    adjustment += calculate_rest_impact(...)
    
    return base_margin + adjustment
```

2. Update `predict_game()` to use the new function

### Adding Live Updates

Future versions can add real-time score tracking by:

1. Creating a new `ingest/live.py` module
2. Polling `ScoreBoard()` during game times
3. Implementing in-game probability updates

## Troubleshooting

### "No games found for today"

This is normal on days with no scheduled NBA games. The engine will still attempt to download the injury report.

### "Could not load team ratings"

This may occur:
- During the off-season (no current season data)
- If the NBA API is temporarily unavailable
- On the first days of a new season

The engine will continue with default ratings (0.0).

### "No injury report found"

The injury report search goes back 36 hours. If no report is found:
- The NBA may not have published a recent report
- It may be the off-season
- There may be a network issue

The engine will continue without injury data.

## License

This project is for educational and personal use. NBA data is subject to NBA's terms of service.
