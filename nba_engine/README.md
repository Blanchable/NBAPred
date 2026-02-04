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
│   ├── schedule.py        # Fetches today's games
│   ├── team_stats.py      # Team statistics and strength
│   ├── player_stats.py    # Player statistics
│   ├── injuries.py        # Downloads and parses injury report PDF
│   ├── availability.py    # Availability normalization
│   ├── inactives.py       # Game-day inactive lists
│   ├── known_absences.py  # Manual absence overrides
│   └── news_absences.py   # News-based absences (ESPN)
├── model/
│   ├── __init__.py
│   ├── point_system.py    # 21-factor weighted scoring system
│   ├── star_impact.py     # Tiered star availability (NEW)
│   ├── rotation_replacement.py  # Next-man-up evaluation (NEW)
│   ├── lineup_adjustment.py     # Lineup-adjusted strength
│   └── calibration.py     # Win probability calibration
├── tests/
│   ├── test_star_impact.py      # Star impact unit tests
│   ├── test_rotation_replacement.py  # Replacement unit tests
│   ├── test_availability.py
│   └── test_pick_logic.py
├── outputs/               # Generated CSV and PDF files
├── data/
│   └── known_absences.csv # Manual player absence overrides
├── app.py                 # GUI application
├── run_today.py           # Command-line interface
├── setup.bat              # First-time setup (Windows)
├── run_app.bat            # Run the app (Windows)
├── build_exe.bat          # Build standalone .exe (Windows)
├── run_app.sh             # Linux/macOS launcher
├── requirements.txt       # Python dependencies
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

## Model Details (v3 - 21 Factor Point System with Star Tiers)

### How It Works

The v3 model evaluates each game using **21 weighted factors** that sum to 100 points. Each factor produces a signed value from -1 (away advantage) to +1 (home advantage), which is multiplied by its weight.

### Star Impact System (New in v3)

The v3 model replaces the old "Star Availability" percentage with a **tiered star system**:

- **Tier A (Top Star)**: 4 base points - The team's best player by impact (PPG + 0.7×APG)
- **Tier B (Secondary Stars)**: 2 base points each - The next 2 best players

Status multipliers are applied:
- OUT: 0.0 (full loss)
- DOUBTFUL: 0.25
- QUESTIONABLE: 0.60
- PROBABLE: 0.85
- AVAILABLE: 1.0

A **dampener** prevents double-counting when injuries are already reflected in team stats (reduces impact by 35-65% for established injuries).

### Rotation Replacement Factor (New in v3)

**Only activates** when a Tier A or Tier B star is OUT or DOUBTFUL:
- Evaluates "next-man-up" quality using Points Per Minute (PPM)
- Compares star quality to replacement candidates
- Bounded contribution: can adjust prediction by up to ±4 points

Role player injuries do **not** trigger this factor.

### The 21 Factors

| # | Factor | Weight | Description |
|---|--------|--------|-------------|
| 1 | Net Rating | 14 | Overall team strength (points per 100 possessions) |
| 2 | **Star Impact** | 9 | Tiered star availability (Tier A/B system) |
| 3 | **Rotation Replacement** | 4 | Next-man-up quality (only when stars OUT/DOUBTFUL) |
| 4 | Off vs Def Efficiency | 8 | Matchup-specific scoring efficiency |
| 5 | Turnover Differential | 6 | Ball security advantage |
| 6 | Shot Quality | 6 | Effective field goal percentage |
| 7 | 3P Edge | 6 | Three-point shooting volume and accuracy |
| 8 | Free Throw Rate | 5 | Ability to get to the line |
| 9 | Rebounding | 5 | Overall rebounding advantage |
| 10 | Home/Road Split | 5 | Performance at home vs away |
| 11 | Home Court | 4 | Fixed home court advantage |
| 12 | Rest/Fatigue | 4 | Days since last game |
| 13 | Rim Protection | 4 | Interior defense |
| 14 | Perimeter Defense | 4 | Opponent 3P% allowed |
| 15 | Matchup Fit | 4 | Style compatibility |
| 16 | Bench Depth | 3 | Rotation quality |
| 17 | Pace Control | 3 | Tempo advantage |
| 18 | Late Game Creation | 3 | Clutch performance proxy |
| 19 | Coaching | 2 | Neutral (no data yet) |
| 20 | Shooting Variance | 3 | 3P reliance (variance) |
| 21 | Motivation | 1 | Neutral (no data yet) |

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
