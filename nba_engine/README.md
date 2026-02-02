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

## Quick Start

### Option 1: GUI Application (Recommended)

The easiest way to use the prediction engine is with the graphical interface.

#### Windows PowerShell

```powershell
# 1. Create virtual environment
python -m venv .venv

# 2. Activate virtual environment
.\.venv\Scripts\Activate.ps1

# 3. Upgrade pip
pip install --upgrade pip

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run the GUI app
python app.py
```

#### Linux/macOS

```bash
# 1. Create virtual environment
python3 -m venv .venv

# 2. Activate virtual environment
source .venv/bin/activate

# 3. Upgrade pip
pip install --upgrade pip

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run the GUI app
python app.py
```

### Option 2: Build Standalone Executable (No Python Required)

Create a `.exe` file that you can double-click to run without needing Python installed.

#### Windows PowerShell

```powershell
# After installing dependencies (steps 1-4 above), run:
pyinstaller --onefile --windowed --name "NBA_Predictor" --add-data "ingest;ingest" --add-data "model;model" app.py
```

The executable will be created at `dist/NBA_Predictor.exe`. You can copy this file anywhere and double-click to run!

#### Linux/macOS

```bash
# After installing dependencies (steps 1-4 above), run:
pyinstaller --onefile --windowed --name "NBA_Predictor" --add-data "ingest:ingest" --add-data "model:model" app.py
```

The executable will be created at `dist/NBA_Predictor`.

### Option 3: Command Line (Original)

For automation or scripting, use the command-line interface:

```powershell
# Windows
python run_today.py

# Linux/macOS
python3 run_today.py
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
├── app.py               # GUI application (recommended)
├── run_today.py         # Command-line interface
├── run_app.bat          # Windows launcher (double-click to run)
├── run_app.sh           # Linux/macOS launcher
├── requirements.txt     # Python dependencies
└── README.md
```

## Easy Launch (After First Setup)

**Windows**: Double-click `run_app.bat`

**Linux/macOS**: Double-click `run_app.sh` (or run `./run_app.sh` in terminal)

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

## Model Details

### V1 Prediction Formula

The model uses a simple but effective approach:

```
ProjectedMarginHome = (home_net - away_net) × NET_SCALE + HOME_COURT_POINTS

Where:
- home_net = Home team's net rating (per 100 possessions)
- away_net = Away team's net rating (per 100 possessions)
- NET_SCALE = 0.5 (converts rating differential to game margin)
- HOME_COURT_POINTS = 2.0 (fixed home court advantage)
```

Win probability uses a logistic function:

```
WinProbHome = 1 / (1 + exp(-ProjectedMarginHome / PROB_SCALE))

Where:
- PROB_SCALE = 7.0 (controls steepness of probability curve)
```

### Constants (Placeholders for V1)

These constants can be tuned in future versions:

| Constant | Value | Description |
|----------|-------|-------------|
| `NET_SCALE` | 0.5 | Maps per-100 possession rating to game margin |
| `HOME_COURT_POINTS` | 2.0 | Fixed home court advantage in points |
| `PROB_SCALE` | 7.0 | Controls win probability curve steepness |

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
