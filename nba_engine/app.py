#!/usr/bin/env python3
"""
NBA Prediction Engine v3 - GUI Application

Lineup-aware, matchup-sensitive NBA pregame predictions with:
- Player availability impact
- Home/road performance splits
- 20-factor weighted scoring system
- Power ratings for quick comparison
- Confidence levels (high/medium/low)
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from datetime import datetime
from pathlib import Path
import sys

# Add the current directory to path for imports
if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).parent

sys.path.insert(0, str(APP_DIR))

from ingest.schedule import get_todays_games, get_current_season
from ingest.team_stats import get_comprehensive_team_stats, get_team_rest_days, get_fallback_team_strength
from ingest.player_stats import get_player_stats
from ingest.injuries import find_latest_injury_pdf, download_injury_pdf, parse_injury_pdf
from model.lineup_adjustment import calculate_lineup_adjusted_strength
from model.point_system import score_game_v3, GameScore
from model.asof import get_data_confidence

# Import new utilities
from utils.dates import get_eastern_date, format_date, parse_date, enforce_date_limit, is_today
from utils.storage import (
    PredictionLogEntry,
    append_predictions,
    export_daily_predictions,
    compute_performance_summary,
    save_performance_summary,
    OUTPUTS_DIR,
)
from jobs.results import update_results_for_date


class NBAPredictor(tk.Tk):
    """Main application window for NBA Prediction Engine v3."""
    
    def __init__(self):
        super().__init__()
        
        self.title("NBA Prediction Engine v3 - Lineup-Aware")
        self.geometry("1200x800")
        self.minsize(1000, 650)
        
        # Configure style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.configure(bg='#2d2d44')
        self.style.configure('TFrame', background='#2d2d44')
        self.style.configure('TLabel', background='#2d2d44', foreground='#ffffff')
        self.style.configure('TButton', padding=10, font=('Segoe UI', 11))
        self.style.configure('Header.TLabel', font=('Segoe UI', 24, 'bold'), foreground='#ff6b35')
        self.style.configure('SubHeader.TLabel', font=('Segoe UI', 14), foreground='#cccccc')
        self.style.configure('Status.TLabel', font=('Segoe UI', 10), foreground='#aaaaaa')
        
        self.style.configure('Treeview',
            background='#ffffff',
            foreground='#000000',
            fieldbackground='#ffffff',
            font=('Segoe UI', 10),
            rowheight=28
        )
        self.style.configure('Treeview.Heading',
            background='#4a4a6a',
            foreground='#ffffff',
            font=('Segoe UI', 10, 'bold')
        )
        self.style.map('Treeview',
            background=[('selected', '#0078d4')],
            foreground=[('selected', '#ffffff')]
        )
        
        # Main container
        self.main_frame = ttk.Frame(self, padding=20)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_frame = ttk.Frame(self.main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(header_frame, text="🏀 NBA Prediction Engine v3", style='Header.TLabel').pack(side=tk.LEFT)
        ttk.Label(header_frame, text=datetime.now().strftime("%A, %B %d, %Y"), style='SubHeader.TLabel').pack(side=tk.RIGHT, pady=10)
        
        # Buttons - Row 1: Today's predictions
        button_frame1 = ttk.Frame(self.main_frame)
        button_frame1.pack(fill=tk.X, pady=5)
        
        self.fetch_button = ttk.Button(button_frame1, text="🔄 Fetch Today's Predictions", command=self.start_fetch)
        self.fetch_button.pack(side=tk.LEFT)
        
        self.save_button = ttk.Button(button_frame1, text="💾 Save to CSV", command=self.save_to_csv, state=tk.DISABLED)
        self.save_button.pack(side=tk.LEFT, padx=10)
        
        self.update_results_button = ttk.Button(button_frame1, text="📊 Update Results", command=self.start_update_results)
        self.update_results_button.pack(side=tk.LEFT, padx=10)
        
        self.export_excel_button = ttk.Button(button_frame1, text="📋 Export to Excel", command=self.export_to_excel)
        self.export_excel_button.pack(side=tk.LEFT, padx=10)
        
        self.status_var = tk.StringVar(value="Click 'Fetch Today's Predictions' to start")
        ttk.Label(button_frame1, textvariable=self.status_var, style='Status.TLabel').pack(side=tk.RIGHT)
        
        # Buttons - Row 2: Historical analysis
        button_frame2 = ttk.Frame(self.main_frame)
        button_frame2.pack(fill=tk.X, pady=5)
        
        ttk.Label(button_frame2, text="Historical Date:", style='TLabel').pack(side=tk.LEFT)
        
        # Date entry
        self.date_var = tk.StringVar(value=format_date(get_eastern_date()))
        self.date_entry = ttk.Entry(button_frame2, textvariable=self.date_var, width=12)
        self.date_entry.pack(side=tk.LEFT, padx=5)
        
        self.historical_button = ttk.Button(button_frame2, text="🕐 Run Historical", command=self.start_historical)
        self.historical_button.pack(side=tk.LEFT, padx=5)
        
        ttk.Separator(button_frame2, orient='vertical').pack(side=tk.LEFT, padx=10, fill='y')
        
        self.season_backfill_button = ttk.Button(button_frame2, text="📅 Full Season Backfill", command=self.start_season_backfill)
        self.season_backfill_button.pack(side=tk.LEFT, padx=5)
        
        # Performance summary label
        self.perf_var = tk.StringVar(value="")
        ttk.Label(button_frame2, textvariable=self.perf_var, style='Status.TLabel').pack(side=tk.RIGHT, padx=10)
        
        # Update performance summary display
        self.update_performance_display()
        
        # Notebook
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Predictions tab
        self.predictions_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.predictions_frame, text="📊 Predictions")
        self.create_predictions_tree()
        
        # Factors tab
        self.factors_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.factors_frame, text="📈 Factor Breakdown")
        self.create_factors_view()
        
        # Injuries tab
        self.injuries_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.injuries_frame, text="🏥 Injuries")
        self.create_injuries_tree()
        
        # Team Stats tab
        self.stats_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.stats_frame, text="📋 Team Stats")
        self.create_stats_view()
        
        # Log tab
        self.log_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.log_frame, text="📝 Log")
        self.log_text = scrolledtext.ScrolledText(self.log_frame, wrap=tk.WORD, font=('Consolas', 10), bg='#1e1e2e', fg='#50fa7b')
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Data storage
        self.scores = []
        self.injuries = []
        self.team_stats = {}
        
        # Progress bar
        self.progress = ttk.Progressbar(self.main_frame, mode='indeterminate', length=300)
        
    def create_predictions_tree(self):
        """Create the predictions treeview."""
        tree_frame = ttk.Frame(self.predictions_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ('matchup', 'pick', 'conf', 'power', 'edge', 'home_prob', 'away_prob', 'margin', 'top_factors')
        self.pred_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', yscrollcommand=scrollbar.set)
        
        self.pred_tree.heading('matchup', text='Matchup')
        self.pred_tree.heading('pick', text='PICK')
        self.pred_tree.heading('conf', text='Conf')
        self.pred_tree.heading('power', text='Power')
        self.pred_tree.heading('edge', text='Edge')
        self.pred_tree.heading('home_prob', text='Home %')
        self.pred_tree.heading('away_prob', text='Away %')
        self.pred_tree.heading('margin', text='Margin')
        self.pred_tree.heading('top_factors', text='Top Factors')
        
        self.pred_tree.column('matchup', width=110, anchor='center')
        self.pred_tree.column('pick', width=55, anchor='center')
        self.pred_tree.column('conf', width=55, anchor='center')
        self.pred_tree.column('power', width=75, anchor='center')
        self.pred_tree.column('edge', width=60, anchor='center')
        self.pred_tree.column('home_prob', width=65, anchor='center')
        self.pred_tree.column('away_prob', width=65, anchor='center')
        self.pred_tree.column('margin', width=60, anchor='center')
        self.pred_tree.column('top_factors', width=400, anchor='w')
        
        self.pred_tree.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.pred_tree.yview)
        
        # Tags
        self.pred_tree.tag_configure('high_conf', background='#d4edda', foreground='#155724')
        self.pred_tree.tag_configure('medium_conf', background='#fff3cd', foreground='#856404')
        self.pred_tree.tag_configure('low_conf', background='#f8d7da', foreground='#721c24')
        
    def create_factors_view(self):
        """Create the factors breakdown view."""
        selector_frame = ttk.Frame(self.factors_frame)
        selector_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(selector_frame, text="Select Game:", foreground='#ffffff').pack(side=tk.LEFT)
        self.game_selector = ttk.Combobox(selector_frame, state='readonly', width=30)
        self.game_selector.pack(side=tk.LEFT, padx=10)
        self.game_selector.bind('<<ComboboxSelected>>', self.on_game_selected)
        
        tree_frame = ttk.Frame(self.factors_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ('factor', 'weight', 'signed', 'contribution', 'inputs')
        self.factors_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', yscrollcommand=scrollbar.set)
        
        self.factors_tree.heading('factor', text='Factor')
        self.factors_tree.heading('weight', text='Weight')
        self.factors_tree.heading('signed', text='Signed')
        self.factors_tree.heading('contribution', text='Contrib')
        self.factors_tree.heading('inputs', text='Inputs Used')
        
        self.factors_tree.column('factor', width=150, anchor='w')
        self.factors_tree.column('weight', width=60, anchor='center')
        self.factors_tree.column('signed', width=70, anchor='center')
        self.factors_tree.column('contribution', width=70, anchor='center')
        self.factors_tree.column('inputs', width=450, anchor='w')
        
        self.factors_tree.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.factors_tree.yview)
        
        self.factors_tree.tag_configure('positive', background='#d4edda', foreground='#155724')
        self.factors_tree.tag_configure('negative', background='#f8d7da', foreground='#721c24')
        self.factors_tree.tag_configure('neutral', background='#ffffff', foreground='#333333')
        
    def create_injuries_tree(self):
        """Create the injuries treeview."""
        tree_frame = ttk.Frame(self.injuries_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ('team', 'player', 'status', 'reason')
        self.inj_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', yscrollcommand=scrollbar.set)
        
        self.inj_tree.heading('team', text='Team')
        self.inj_tree.heading('player', text='Player')
        self.inj_tree.heading('status', text='Status')
        self.inj_tree.heading('reason', text='Reason')
        
        self.inj_tree.column('team', width=80, anchor='center')
        self.inj_tree.column('player', width=180, anchor='w')
        self.inj_tree.column('status', width=100, anchor='center')
        self.inj_tree.column('reason', width=300, anchor='w')
        
        self.inj_tree.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.inj_tree.yview)
        
        self.inj_tree.tag_configure('Out', background='#f8d7da', foreground='#721c24')
        self.inj_tree.tag_configure('Doubtful', background='#ffe5d0', foreground='#8a4500')
        self.inj_tree.tag_configure('Questionable', background='#fff3cd', foreground='#856404')
        self.inj_tree.tag_configure('Probable', background='#d4edda', foreground='#155724')
        
    def create_stats_view(self):
        """Create the team stats view."""
        selector_frame = ttk.Frame(self.stats_frame)
        selector_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(selector_frame, text="Select Team:", foreground='#ffffff').pack(side=tk.LEFT)
        self.team_selector = ttk.Combobox(selector_frame, state='readonly', width=30)
        self.team_selector.pack(side=tk.LEFT, padx=10)
        self.team_selector.bind('<<ComboboxSelected>>', self.on_team_selected)
        
        tree_frame = ttk.Frame(self.stats_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ('stat', 'value', 'description')
        self.stats_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', yscrollcommand=scrollbar.set)
        
        self.stats_tree.heading('stat', text='Statistic')
        self.stats_tree.heading('value', text='Value')
        self.stats_tree.heading('description', text='Description')
        
        self.stats_tree.column('stat', width=150, anchor='w')
        self.stats_tree.column('value', width=100, anchor='center')
        self.stats_tree.column('description', width=400, anchor='w')
        
        self.stats_tree.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.stats_tree.yview)
        
        self.stats_tree.tag_configure('good', background='#d4edda', foreground='#155724')
        self.stats_tree.tag_configure('average', background='#ffffff', foreground='#333333')
        self.stats_tree.tag_configure('poor', background='#f8d7da', foreground='#721c24')
        
    def log(self, message: str):
        """Add message to log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.update_idletasks()
        
    def start_fetch(self):
        """Start fetching data."""
        self.fetch_button.config(state=tk.DISABLED)
        self.save_button.config(state=tk.DISABLED)
        self.progress.pack(pady=5)
        self.progress.start(10)
        self.status_var.set("Fetching data...")
        
        # Clear data
        for tree in [self.pred_tree, self.inj_tree, self.factors_tree, self.stats_tree]:
            for item in tree.get_children():
                tree.delete(item)
        self.game_selector['values'] = []
        self.team_selector['values'] = []
        self.log_text.delete(1.0, tk.END)
        
        thread = threading.Thread(target=self.fetch_data, daemon=True)
        thread.start()
        
    def fetch_data(self):
        """Fetch all data (background thread)."""
        try:
            # 1. Get games
            self.log("Fetching today's NBA games...")
            games, api_date, is_current_date = get_todays_games()
            
            if not games:
                self.log("No games found.")
                if not is_current_date:
                    self.log("⚠ API may not have updated yet. Try after 10 AM ET.")
                self.after(0, self.fetch_complete, False, "No games scheduled")
                return
            
            self.log(f"Found {len(games)} games for {api_date}")
            
            if not is_current_date:
                self.log("")
                self.log("⚠ WARNING: These may be YESTERDAY'S games!")
                self.log(f"  API Date: {api_date}")
                self.log("  NBA API typically updates around 6-10 AM ET.")
                self.log("")
            
            for g in games:
                self.log(f"  {g.away_team} @ {g.home_team}")
            
            # 2. Get team stats
            self.log("\nFetching team statistics...")
            season = get_current_season()
            
            try:
                team_strength = get_comprehensive_team_stats(season=season)
                if not team_strength:
                    self.log("  API returned empty, using fallback...")
                    team_strength = get_fallback_team_strength()
            except Exception as e:
                self.log(f"  API error: {e}")
                self.log("  Using fallback team data...")
                team_strength = get_fallback_team_strength()
            
            self.team_stats = {k: v.to_dict() if hasattr(v, 'to_dict') else v for k, v in team_strength.items()}
            self.log(f"Loaded stats for {len(team_strength)} teams")
            
            # 3. Get player stats
            self.log("\nFetching player statistics...")
            try:
                player_stats = get_player_stats(season=season)
            except:
                player_stats = {}
            self.log(f"Loaded players for {len(player_stats)} teams")
            
            # 4. Get rest days
            self.log("\nCalculating rest days...")
            teams_playing = list(set([g.away_team for g in games] + [g.home_team for g in games]))
            try:
                rest_days = get_team_rest_days(teams_playing, season=season)
            except:
                rest_days = {t: 1 for t in teams_playing}
            
            # 5. Get injuries
            self.log("\nFetching injury report...")
            output_dir = APP_DIR / "outputs"
            output_dir.mkdir(exist_ok=True)
            cache_file = output_dir / "latest_injury_url.txt"
            
            injury_url = find_latest_injury_pdf(cache_file=cache_file)
            if injury_url:
                self.log(f"Found: {injury_url}")
                pdf_bytes = download_injury_pdf(injury_url)
                if pdf_bytes:
                    self.injuries = parse_injury_pdf(pdf_bytes)
                    self.log(f"Parsed {len(self.injuries)} injuries")
            else:
                self.injuries = []
                self.log("No injury report found")
            
            # 6. Generate predictions
            self.log("\nGenerating lineup-adjusted predictions...")
            self.scores = []
            
            for game in games:
                home_ts = team_strength.get(game.home_team)
                away_ts = team_strength.get(game.away_team)
                
                if not home_ts or not away_ts:
                    continue
                
                home_players = player_stats.get(game.home_team, [])
                away_players = player_stats.get(game.away_team, [])
                
                home_lineup = calculate_lineup_adjusted_strength(
                    game.home_team, home_ts, home_players, self.injuries, True
                )
                away_lineup = calculate_lineup_adjusted_strength(
                    game.away_team, away_ts, away_players, self.injuries, False
                )
                
                home_stats = home_ts.to_dict() if hasattr(home_ts, 'to_dict') else home_ts
                away_stats = away_ts.to_dict() if hasattr(away_ts, 'to_dict') else away_ts
                
                # Filter injuries by team for star impact calculation
                home_injuries = [inj for inj in self.injuries if getattr(inj, 'team', '').upper() == game.home_team.upper()]
                away_injuries = [inj for inj in self.injuries if getattr(inj, 'team', '').upper() == game.away_team.upper()]
                
                score = score_game_v3(
                    home_team=game.home_team,
                    away_team=game.away_team,
                    home_strength=home_lineup,
                    away_strength=away_lineup,
                    home_stats=home_stats,
                    away_stats=away_stats,
                    home_rest_days=rest_days.get(game.home_team, 1),
                    away_rest_days=rest_days.get(game.away_team, 1),
                    home_players=home_players,
                    away_players=away_players,
                    home_injuries=home_injuries,
                    away_injuries=away_injuries,
                )
                self.scores.append(score)
            
            # Sort by abs(edge_score_total) (strongest edge first), then by confidence
            self.scores.sort(key=lambda s: (abs(s.edge_score_total), s.confidence), reverse=True)
            
            self.log(f"Generated {len(self.scores)} predictions")
            
            # Save predictions to log
            self.after(0, self.save_predictions_to_log)
            
            self.after(0, self.update_ui)
            self.after(0, self.update_performance_display)
            self.after(0, self.fetch_complete, True, f"Loaded {len(games)} games")
            
        except Exception as e:
            self.log(f"\nError: {e}")
            import traceback
            self.log(traceback.format_exc())
            self.after(0, self.fetch_complete, False, f"Error: {str(e)[:50]}")
    
    def update_ui(self):
        """Update UI with data."""
        # Predictions
        for score in self.scores:
            matchup = f"{score.away_team} @ {score.home_team}"
            power = f"{score.away_power_rating:.0f} v {score.home_power_rating:.0f}"
            
            # Use confidence label for tag coloring
            tag = f"{score.confidence_label.lower()}_conf"
            
            self.pred_tree.insert('', 'end', values=(
                matchup, score.predicted_winner, score.confidence_pct,
                power, f"{score.edge_score_total:+.1f}",
                f"{score.home_win_prob:.1%}", f"{score.away_win_prob:.1%}",
                f"{score.projected_margin_home:+.1f}", score.top_5_factors_str
            ), tags=(tag,))
        
        # Game selector
        game_options = [f"{s.away_team} @ {s.home_team}" for s in self.scores]
        self.game_selector['values'] = game_options
        if game_options:
            self.game_selector.current(0)
            self.on_game_selected(None)
        
        # Team selector
        teams = sorted(list(set([s.away_team for s in self.scores] + [s.home_team for s in self.scores])))
        self.team_selector['values'] = teams
        if teams:
            self.team_selector.current(0)
            self.on_team_selected(None)
        
        # Injuries
        for inj in self.injuries:
            self.inj_tree.insert('', 'end', values=(inj.team, inj.player, inj.status, inj.reason), tags=(inj.status,))
    
    def on_game_selected(self, event):
        """Handle game selection."""
        for item in self.factors_tree.get_children():
            self.factors_tree.delete(item)
        
        selection = self.game_selector.get()
        if not selection:
            return
        
        for score in self.scores:
            if f"{score.away_team} @ {score.home_team}" == selection:
                for f in sorted(score.factors, key=lambda x: abs(x.contribution), reverse=True):
                    tag = 'positive' if f.contribution > 0.5 else 'negative' if f.contribution < -0.5 else 'neutral'
                    self.factors_tree.insert('', 'end', values=(
                        f.display_name, f.weight, f"{f.signed_value:+.3f}",
                        f"{f.contribution:+.2f}", f.inputs_used
                    ), tags=(tag,))
                break
    
    def on_team_selected(self, event):
        """Handle team selection."""
        for item in self.stats_tree.get_children():
            self.stats_tree.delete(item)
        
        team = self.team_selector.get()
        if not team or team not in self.team_stats:
            return
        
        stats = self.team_stats[team]
        
        # Define stats with their display format
        # format: 'pct' = percentage (multiply by 100), 'num' = raw number
        stat_info = [
            ('net_rating', 'Net Rating', 'Points per 100 poss differential', 'num'),
            ('off_rating', 'Offensive Rating', 'Points scored per 100 poss', 'num'),
            ('def_rating', 'Defensive Rating', 'Points allowed per 100 poss', 'num'),
            ('home_net_rating', 'Home Net Rating', 'Net rating at home', 'num'),
            ('road_net_rating', 'Road Net Rating', 'Net rating on road', 'num'),
            ('pace', 'Pace', 'Possessions per game', 'num'),
            ('efg_pct', 'Effective FG%', 'Shooting efficiency', 'pct'),
            ('fg3_pct', '3-Point %', 'Three-point shooting', 'pct'),
            ('ft_rate', 'Free Throw Rate', 'FTA per FGA', 'num'),
            ('tov_pct', 'Turnover %', 'Turnovers per possession', 'num'),
            ('oreb_pct', 'Off Rebound %', 'Offensive rebounding rate', 'num'),
        ]
        
        for key, name, desc, fmt in stat_info:
            val = stats.get(key, 'N/A')
            if val != 'N/A':
                if isinstance(val, (int, float)):
                    if fmt == 'pct':
                        # Percentage: show as X.X%
                        display = f"{val:.1%}" if val <= 1 else f"{val:.1f}%"
                    else:
                        # Raw number: show with appropriate precision
                        display = f"{val:.1f}"
                else:
                    display = str(val)
            else:
                display = 'N/A'
            
            self.stats_tree.insert('', 'end', values=(name, display, desc), tags=('average',))
    
    def fetch_complete(self, success: bool, message: str):
        """Called when fetch completes."""
        self.progress.stop()
        self.progress.pack_forget()
        self.fetch_button.config(state=tk.NORMAL)
        if success and self.scores:
            self.save_button.config(state=tk.NORMAL)
        self.status_var.set(message)
        
    def save_to_csv(self):
        """Save to CSV."""
        try:
            import pandas as pd
            output_dir = APP_DIR / "outputs"
            output_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if self.scores:
                data = [{
                    "away_team": s.away_team, "home_team": s.home_team,
                    "predicted_winner": s.predicted_winner, "confidence": s.confidence,
                    "edge_score": s.edge_score_total, "home_win_prob": s.home_win_prob,
                    "away_win_prob": s.away_win_prob, "projected_margin": s.projected_margin_home,
                    "home_power": s.home_power_rating, "away_power": s.away_power_rating,
                    "top_factors": s.top_5_factors_str
                } for s in self.scores]
                
                pd.DataFrame(data).to_csv(output_dir / f"predictions_{timestamp}.csv", index=False)
                self.log(f"\nSaved predictions to predictions_{timestamp}.csv")
            
            if self.injuries:
                data = [{"team": i.team, "player": i.player, "status": i.status, "reason": i.reason} for i in self.injuries]
                pd.DataFrame(data).to_csv(output_dir / f"injuries_{timestamp}.csv", index=False)
                self.log(f"Saved injuries to injuries_{timestamp}.csv")
            
            messagebox.showinfo("Saved", f"Files saved to:\n{output_dir}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")
    
    def update_performance_display(self):
        """Update the performance summary display."""
        try:
            summary = compute_performance_summary()
            if summary.total_games > 0:
                self.perf_var.set(
                    f"Record: {summary.wins}/{summary.total_games} ({summary.win_pct:.1%}) | "
                    f"Last 7d: {summary.last_7_days_win_pct:.1%}"
                )
            else:
                self.perf_var.set("")
        except Exception:
            self.perf_var.set("")
    
    def start_update_results(self):
        """Start updating results in a background thread."""
        self.update_results_button.config(state=tk.DISABLED)
        self.status_var.set("Updating results...")
        thread = threading.Thread(target=self.update_results_worker, daemon=True)
        thread.start()
    
    def update_results_worker(self):
        """Worker thread to update results."""
        try:
            from jobs.results import update_all_pending_results
            
            self.log("\nUpdating results for pending predictions...")
            updated = update_all_pending_results()
            
            self.log(f"Updated {updated} predictions with results")
            
            # Update performance display
            self.after(0, self.update_performance_display)
            self.after(0, lambda: self.status_var.set(f"Updated {updated} results"))
            
        except Exception as e:
            self.log(f"\nError updating results: {e}")
            self.after(0, lambda: self.status_var.set("Error updating results"))
        finally:
            self.after(0, lambda: self.update_results_button.config(state=tk.NORMAL))
    
    def save_predictions_to_log(self):
        """Save current predictions to the prediction log."""
        if not self.scores:
            return
        
        try:
            # Determine data confidence
            data_confidence = get_data_confidence(
                team_stats_available=len(self.team_stats) > 0,
                player_stats_available=True,  # We got player stats
                injury_report_available=len(self.injuries) > 0,
            )
            
            entries = []
            run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            game_date = format_date(get_eastern_date())
            
            for score in self.scores:
                entry = PredictionLogEntry(
                    run_timestamp_local=run_timestamp,
                    game_date=game_date,
                    game_id="",
                    away_team=score.away_team,
                    home_team=score.home_team,
                    pick=score.predicted_winner,
                    edge_score_total=round(score.edge_score_total, 2),
                    projected_margin_home=round(score.projected_margin_home, 1),
                    home_win_prob=round(score.home_win_prob, 3),
                    away_win_prob=round(score.away_win_prob, 3),
                    confidence_level=score.confidence_label.upper(),
                    confidence_pct=score.confidence_pct,
                    top_5_factors=score.top_5_factors_str,
                    injury_report_url="",
                    data_confidence=data_confidence,
                )
                entries.append(entry)
            
            if entries:
                append_predictions(entries)
                export_daily_predictions(entries, game_date)
                self.log(f"Saved {len(entries)} predictions to log")
                
        except Exception as e:
            self.log(f"Error saving to log: {e}")
    
    def start_historical(self):
        """Start historical prediction run for selected date."""
        date_str = self.date_var.get().strip()
        
        try:
            target_date = parse_date(date_str)
            enforce_date_limit(target_date)
        except ValueError as e:
            messagebox.showerror("Invalid Date", str(e))
            return
        
        if is_today(target_date):
            messagebox.showinfo("Info", "For today's predictions, use 'Fetch Today's Predictions' button.")
            return
        
        self.historical_button.config(state=tk.DISABLED)
        self.status_var.set(f"Running historical analysis for {date_str}...")
        
        thread = threading.Thread(target=self.historical_worker, args=(target_date,), daemon=True)
        thread.start()
    
    def historical_worker(self, target_date):
        """Worker thread for historical prediction run."""
        try:
            from jobs.backfill import backfill_predictions
            
            self.log(f"\n{'='*60}")
            self.log(f"Running historical analysis for {format_date(target_date)}")
            self.log(f"{'='*60}")
            
            predictions = backfill_predictions(
                target_date=target_date,
                fill_results=True,  # Auto-fill results for past games
                use_cache=True,
            )
            
            self.log(f"Generated {len(predictions)} predictions")
            
            # Update performance display
            self.after(0, self.update_performance_display)
            self.after(0, lambda: self.status_var.set(f"Completed historical analysis: {len(predictions)} games"))
            
        except Exception as e:
            self.log(f"\nError in historical analysis: {e}")
            import traceback
            self.log(traceback.format_exc())
            self.after(0, lambda: self.status_var.set("Error in historical analysis"))
        finally:
            self.after(0, lambda: self.historical_button.config(state=tk.NORMAL))
    
    def start_season_backfill(self):
        """Start full season backfill."""
        result = messagebox.askyesno(
            "Full Season Backfill",
            "This will run predictions for all games in the current season.\n\n"
            "This may take several minutes and will make many API calls.\n\n"
            "Continue?"
        )
        
        if not result:
            return
        
        self.season_backfill_button.config(state=tk.DISABLED)
        self.status_var.set("Running full season backfill...")
        
        thread = threading.Thread(target=self.season_backfill_worker, daemon=True)
        thread.start()
    
    def season_backfill_worker(self):
        """Worker thread for full season backfill."""
        try:
            from jobs.backfill import backfill_date_range
            from jobs.excel_export import export_predictions_to_excel
            from utils.dates import get_eastern_date, get_season_for_date, get_date_limit
            from datetime import timedelta
            
            today = get_eastern_date()
            season = get_season_for_date(today)
            
            # Determine season start (October of start year)
            season_start_year = int(season.split("-")[0])
            season_start = parse_date(f"{season_start_year}-10-22")  # NBA typically starts late October
            
            # Limit to 3 months back
            earliest = get_date_limit()
            start_date = max(season_start, earliest)
            
            # End date is yesterday (today's games haven't been played)
            end_date = today - timedelta(days=1)
            
            if start_date > end_date:
                self.log("No historical dates to backfill")
                self.after(0, lambda: self.status_var.set("No historical dates to backfill"))
                return
            
            self.log(f"\n{'#'*60}")
            self.log(f"FULL SEASON BACKFILL: {season}")
            self.log(f"Date range: {format_date(start_date)} to {format_date(end_date)}")
            self.log(f"{'#'*60}")
            
            # Run backfill in chunks to stay within limits
            from utils.dates import get_date_range
            all_dates = get_date_range(start_date, end_date)
            
            total_predictions = 0
            chunk_size = 7  # Process 7 days at a time
            
            for i in range(0, len(all_dates), chunk_size):
                chunk = all_dates[i:i+chunk_size]
                chunk_start = chunk[0]
                chunk_end = chunk[-1]
                
                self.log(f"\nProcessing {format_date(chunk_start)} to {format_date(chunk_end)}...")
                self.after(0, lambda s=chunk_start, e=chunk_end: 
                           self.status_var.set(f"Backfilling {format_date(s)} to {format_date(e)}..."))
                
                try:
                    count = backfill_date_range(
                        start_date=chunk_start,
                        end_date=chunk_end,
                        fill_results=True,
                        max_days=chunk_size,
                        use_cache=True,
                    )
                    total_predictions += count
                except Exception as e:
                    self.log(f"  Error in chunk: {e}")
            
            self.log(f"\n{'#'*60}")
            self.log(f"BACKFILL COMPLETE: {total_predictions} total predictions")
            self.log(f"{'#'*60}")
            
            # Export to Excel
            self.log("\nExporting to Excel...")
            try:
                excel_path = export_predictions_to_excel(
                    title=f"NBA Predictions - {season} Season"
                )
                self.log(f"Exported to: {excel_path}")
                self.after(0, lambda: messagebox.showinfo("Backfill Complete", 
                    f"Generated {total_predictions} predictions\n\nExported to:\n{excel_path}"))
            except Exception as e:
                self.log(f"Error exporting to Excel: {e}")
            
            # Update performance display
            self.after(0, self.update_performance_display)
            self.after(0, lambda: self.status_var.set(f"Season backfill complete: {total_predictions} predictions"))
            
        except Exception as e:
            self.log(f"\nError in season backfill: {e}")
            import traceback
            self.log(traceback.format_exc())
            self.after(0, lambda: self.status_var.set("Error in season backfill"))
        finally:
            self.after(0, lambda: self.season_backfill_button.config(state=tk.NORMAL))
    
    def export_to_excel(self):
        """Export current predictions to Excel."""
        try:
            from jobs.excel_export import export_predictions_to_excel
            from utils.storage import load_predictions_log
            
            entries = load_predictions_log()
            
            if not entries:
                messagebox.showwarning("No Data", "No predictions to export. Run some predictions first.")
                return
            
            excel_path = export_predictions_to_excel(entries)
            
            self.log(f"\nExported to Excel: {excel_path}")
            messagebox.showinfo("Exported", f"Predictions exported to:\n{excel_path}")
            
        except Exception as e:
            self.log(f"Error exporting to Excel: {e}")
            messagebox.showerror("Export Error", f"Failed to export: {e}")


def main():
    app = NBAPredictor()
    app.mainloop()


if __name__ == "__main__":
    main()
