#!/usr/bin/env python3
"""
NBA Prediction Engine - GUI Application (v2)

A GUI that fetches today's NBA predictions using the 20-factor weighted
point system and displays them in an easy-to-read format.
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from datetime import datetime
from pathlib import Path
import sys

# Add the current directory to path for imports when running as executable
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    APP_DIR = Path(sys.executable).parent
else:
    # Running as script
    APP_DIR = Path(__file__).parent

sys.path.insert(0, str(APP_DIR))

from ingest.schedule import (
    get_todays_games,
    get_advanced_team_stats,
    get_team_rest_days,
    get_current_season,
)
from ingest.injuries import (
    find_latest_injury_pdf,
    download_injury_pdf,
    parse_injury_pdf,
)
from model.point_system import score_game, GameScore


class NBAPredictor(tk.Tk):
    """Main application window for NBA Prediction Engine."""
    
    def __init__(self):
        super().__init__()
        
        self.title("NBA Prediction Engine v2 - 20 Factor System")
        self.geometry("1100x750")
        self.minsize(900, 600)
        
        # Configure style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Configure colors - using lighter theme for better readability
        self.configure(bg='#2d2d44')
        self.style.configure('TFrame', background='#2d2d44')
        self.style.configure('TLabel', background='#2d2d44', foreground='#ffffff')
        self.style.configure('TButton', padding=10, font=('Segoe UI', 11))
        self.style.configure('Header.TLabel', font=('Segoe UI', 24, 'bold'), foreground='#ff6b35')
        self.style.configure('SubHeader.TLabel', font=('Segoe UI', 14), foreground='#cccccc')
        self.style.configure('Status.TLabel', font=('Segoe UI', 10), foreground='#aaaaaa')
        
        # Configure Treeview for better readability
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
        
        # Create main container
        self.main_frame = ttk.Frame(self, padding=20)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_frame = ttk.Frame(self.main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        title_label = ttk.Label(
            header_frame, 
            text="🏀 NBA Prediction Engine v2",
            style='Header.TLabel'
        )
        title_label.pack(side=tk.LEFT)
        
        # Date label
        date_str = datetime.now().strftime("%A, %B %d, %Y")
        date_label = ttk.Label(
            header_frame,
            text=date_str,
            style='SubHeader.TLabel'
        )
        date_label.pack(side=tk.RIGHT, pady=10)
        
        # Button frame
        button_frame = ttk.Frame(self.main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        self.fetch_button = ttk.Button(
            button_frame,
            text="🔄 Fetch Today's Predictions",
            command=self.start_fetch
        )
        self.fetch_button.pack(side=tk.LEFT)
        
        self.save_button = ttk.Button(
            button_frame,
            text="💾 Save to CSV",
            command=self.save_to_csv,
            state=tk.DISABLED
        )
        self.save_button.pack(side=tk.LEFT, padx=10)
        
        # Status label
        self.status_var = tk.StringVar(value="Click 'Fetch Today's Predictions' to start")
        self.status_label = ttk.Label(
            button_frame,
            textvariable=self.status_var,
            style='Status.TLabel'
        )
        self.status_label.pack(side=tk.RIGHT)
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Predictions tab
        self.predictions_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.predictions_frame, text="📊 Predictions")
        
        # Create predictions treeview
        self.create_predictions_tree()
        
        # Factors tab
        self.factors_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.factors_frame, text="📈 Factor Breakdown")
        
        # Create factors view
        self.create_factors_view()
        
        # Injuries tab
        self.injuries_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.injuries_frame, text="🏥 Injuries")
        
        # Create injuries treeview
        self.create_injuries_tree()
        
        # Team Stats tab (for data validation)
        self.stats_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.stats_frame, text="📋 Team Stats")
        
        # Create team stats view
        self.create_stats_view()
        
        # Log tab
        self.log_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.log_frame, text="📝 Log")
        
        self.log_text = scrolledtext.ScrolledText(
            self.log_frame,
            wrap=tk.WORD,
            font=('Consolas', 10),
            bg='#1e1e2e',
            fg='#50fa7b',
            insertbackground='#50fa7b'
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Store data
        self.scores = []
        self.injuries = []
        self.team_stats = {}  # Store raw team stats for display
        
        # Progress bar
        self.progress = ttk.Progressbar(
            self.main_frame,
            mode='indeterminate',
            length=300
        )
        
    def create_predictions_tree(self):
        """Create the predictions treeview widget."""
        # Create frame with scrollbar
        tree_frame = ttk.Frame(self.predictions_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Treeview with new columns
        columns = ('matchup', 'pick', 'edge', 'home_prob', 'away_prob', 'margin', 'top_factors')
        self.pred_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            yscrollcommand=scrollbar.set
        )
        
        # Configure columns
        self.pred_tree.heading('matchup', text='Matchup')
        self.pred_tree.heading('pick', text='PICK')
        self.pred_tree.heading('edge', text='Edge Score')
        self.pred_tree.heading('home_prob', text='Home Win %')
        self.pred_tree.heading('away_prob', text='Away Win %')
        self.pred_tree.heading('margin', text='Proj. Margin')
        self.pred_tree.heading('top_factors', text='Top Factors')
        
        self.pred_tree.column('matchup', width=120, anchor='center')
        self.pred_tree.column('pick', width=60, anchor='center')
        self.pred_tree.column('edge', width=80, anchor='center')
        self.pred_tree.column('home_prob', width=85, anchor='center')
        self.pred_tree.column('away_prob', width=85, anchor='center')
        self.pred_tree.column('margin', width=85, anchor='center')
        self.pred_tree.column('top_factors', width=400, anchor='w')
        
        self.pred_tree.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.pred_tree.yview)
        
        # Style rows - light colors for readability
        self.pred_tree.tag_configure('home_pick', background='#d4edda', foreground='#155724')
        self.pred_tree.tag_configure('away_pick', background='#fff3cd', foreground='#856404')
        self.pred_tree.tag_configure('strong_home', background='#b8daff', foreground='#004085')
        self.pred_tree.tag_configure('strong_away', background='#f5c6cb', foreground='#721c24')
        
    def create_factors_view(self):
        """Create the factors breakdown view."""
        # Top frame for game selector
        selector_frame = ttk.Frame(self.factors_frame)
        selector_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(selector_frame, text="Select Game:", foreground='#ffffff').pack(side=tk.LEFT)
        
        self.game_selector = ttk.Combobox(selector_frame, state='readonly', width=30)
        self.game_selector.pack(side=tk.LEFT, padx=10)
        self.game_selector.bind('<<ComboboxSelected>>', self.on_game_selected)
        
        # Create factors treeview
        tree_frame = ttk.Frame(self.factors_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ('factor', 'weight', 'signed', 'contribution', 'inputs')
        self.factors_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            yscrollcommand=scrollbar.set
        )
        
        self.factors_tree.heading('factor', text='Factor')
        self.factors_tree.heading('weight', text='Weight')
        self.factors_tree.heading('signed', text='Signed Value')
        self.factors_tree.heading('contribution', text='Contribution')
        self.factors_tree.heading('inputs', text='Inputs Used')
        
        self.factors_tree.column('factor', width=160, anchor='w')
        self.factors_tree.column('weight', width=60, anchor='center')
        self.factors_tree.column('signed', width=90, anchor='center')
        self.factors_tree.column('contribution', width=90, anchor='center')
        self.factors_tree.column('inputs', width=400, anchor='w')
        
        self.factors_tree.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.factors_tree.yview)
        
        # Color tags
        self.factors_tree.tag_configure('positive', background='#d4edda', foreground='#155724')
        self.factors_tree.tag_configure('negative', background='#f8d7da', foreground='#721c24')
        self.factors_tree.tag_configure('neutral', background='#ffffff', foreground='#333333')
        
    def create_injuries_tree(self):
        """Create the injuries treeview widget."""
        # Create frame with scrollbar
        tree_frame = ttk.Frame(self.injuries_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Treeview
        columns = ('team', 'player', 'status', 'reason')
        self.inj_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            yscrollcommand=scrollbar.set
        )
        
        # Configure columns
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
        
        # Style by status - clear colors for readability
        self.inj_tree.tag_configure('Out', background='#f8d7da', foreground='#721c24')
        self.inj_tree.tag_configure('Doubtful', background='#ffe5d0', foreground='#8a4500')
        self.inj_tree.tag_configure('Questionable', background='#fff3cd', foreground='#856404')
        self.inj_tree.tag_configure('Probable', background='#d4edda', foreground='#155724')
    
    def create_stats_view(self):
        """Create the team stats validation view."""
        # Top frame for team selector
        selector_frame = ttk.Frame(self.stats_frame)
        selector_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(selector_frame, text="Select Team:", foreground='#ffffff').pack(side=tk.LEFT)
        
        self.team_selector = ttk.Combobox(selector_frame, state='readonly', width=30)
        self.team_selector.pack(side=tk.LEFT, padx=10)
        self.team_selector.bind('<<ComboboxSelected>>', self.on_team_selected)
        
        # Info label
        self.stats_info = ttk.Label(
            selector_frame, 
            text="View raw stats used for predictions",
            foreground='#aaaaaa'
        )
        self.stats_info.pack(side=tk.RIGHT)
        
        # Create stats treeview
        tree_frame = ttk.Frame(self.stats_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ('stat', 'value', 'description', 'typical_range')
        self.stats_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            yscrollcommand=scrollbar.set
        )
        
        self.stats_tree.heading('stat', text='Statistic')
        self.stats_tree.heading('value', text='Value')
        self.stats_tree.heading('description', text='Description')
        self.stats_tree.heading('typical_range', text='Typical Range')
        
        self.stats_tree.column('stat', width=140, anchor='w')
        self.stats_tree.column('value', width=80, anchor='center')
        self.stats_tree.column('description', width=300, anchor='w')
        self.stats_tree.column('typical_range', width=120, anchor='center')
        
        self.stats_tree.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.stats_tree.yview)
        
        # Color tags for values
        self.stats_tree.tag_configure('good', background='#d4edda', foreground='#155724')
        self.stats_tree.tag_configure('average', background='#ffffff', foreground='#333333')
        self.stats_tree.tag_configure('poor', background='#f8d7da', foreground='#721c24')
        
    def on_team_selected(self, event):
        """Handle team selection in stats tab."""
        # Clear existing stats
        for item in self.stats_tree.get_children():
            self.stats_tree.delete(item)
        
        team = self.team_selector.get()
        if not team or team not in self.team_stats:
            return
        
        stats = self.team_stats[team]
        
        # Define stat metadata: (key, description, typical_low, typical_high, higher_is_better)
        stat_info = [
            ('net_rating', 'Net Rating', 'Points per 100 poss differential', -12, 12, True),
            ('off_rating', 'Offensive Rating', 'Points scored per 100 poss', 105, 120, True),
            ('def_rating', 'Defensive Rating', 'Points allowed per 100 poss', 105, 120, False),
            ('pace', 'Pace', 'Possessions per game', 96, 104, None),
            ('efg_pct', 'Effective FG%', 'FG% adjusted for 3-pointers', 0.48, 0.58, True),
            ('fg3_pct', '3-Point %', 'Three-point field goal %', 0.33, 0.40, True),
            ('fg3a_rate', '3PA Rate', '3-point attempts / total FGA', 0.35, 0.50, None),
            ('ft_rate', 'Free Throw Rate', 'FTA / FGA', 0.20, 0.30, True),
            ('tov_pct', 'Turnover %', 'Turnovers per 100 poss', 12, 16, False),
            ('oreb_pct', 'Off Rebound %', '% of available off rebounds', 22, 30, True),
            ('dreb_pct', 'Def Rebound %', '% of available def rebounds', 72, 80, True),
            ('reb_pct', 'Total Rebound %', 'Overall rebounding rate', 48, 54, True),
            ('opp_fg3_pct', 'Opp 3P%', 'Opponent 3-point % allowed', 0.33, 0.40, False),
            ('pf_per_game', 'Fouls/Game', 'Personal fouls per game', 18, 24, False),
        ]
        
        for key, name, desc, low, high, higher_good in stat_info:
            value = stats.get(key, 'N/A')
            
            if value != 'N/A':
                # Format value
                if isinstance(value, float):
                    if value < 1:  # Percentages
                        display_val = f"{value:.1%}"
                    elif value > 50:  # Ratings
                        display_val = f"{value:.1f}"
                    else:
                        display_val = f"{value:.2f}"
                else:
                    display_val = str(value)
                
                # Determine if good/average/poor
                if higher_good is not None:
                    mid = (low + high) / 2
                    if higher_good:
                        if value > mid + (high - mid) * 0.3:
                            tag = 'good'
                        elif value < mid - (mid - low) * 0.3:
                            tag = 'poor'
                        else:
                            tag = 'average'
                    else:
                        if value < mid - (mid - low) * 0.3:
                            tag = 'good'
                        elif value > mid + (high - mid) * 0.3:
                            tag = 'poor'
                        else:
                            tag = 'average'
                else:
                    tag = 'average'
                
                typical = f"{low} - {high}" if isinstance(low, int) else f"{low:.0%} - {high:.0%}"
            else:
                display_val = 'N/A'
                tag = 'average'
                typical = 'N/A'
            
            self.stats_tree.insert(
                '', 'end',
                values=(name, display_val, desc, typical),
                tags=(tag,)
            )
        
    def log(self, message: str):
        """Add a message to the log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.update_idletasks()
        
    def start_fetch(self):
        """Start fetching data in a background thread."""
        self.fetch_button.config(state=tk.DISABLED)
        self.save_button.config(state=tk.DISABLED)
        self.progress.pack(pady=5)
        self.progress.start(10)
        self.status_var.set("Fetching data...")
        
        # Clear existing data
        for item in self.pred_tree.get_children():
            self.pred_tree.delete(item)
        for item in self.inj_tree.get_children():
            self.inj_tree.delete(item)
        for item in self.factors_tree.get_children():
            self.factors_tree.delete(item)
        for item in self.stats_tree.get_children():
            self.stats_tree.delete(item)
        self.game_selector['values'] = []
        self.team_selector['values'] = []
        self.log_text.delete(1.0, tk.END)
        
        # Run in background thread
        thread = threading.Thread(target=self.fetch_data, daemon=True)
        thread.start()
        
    def fetch_data(self):
        """Fetch all data (runs in background thread)."""
        try:
            # Step 1: Fetch today's games
            self.log("Fetching today's NBA games...")
            games = get_todays_games()
            
            if not games:
                self.log("No games found for today.")
                self.after(0, self.fetch_complete, False, "No games scheduled today")
                return
            
            self.log(f"Found {len(games)} games:")
            for game in games:
                self.log(f"  {game.away_team} @ {game.home_team}")
            
            # Step 2: Fetch advanced team stats
            self.log("\nFetching advanced team stats...")
            season = get_current_season()
            self.log(f"Season: {season}")
            
            team_stats = get_advanced_team_stats(season=season)
            self.team_stats = team_stats  # Store for display
            
            if team_stats:
                self.log(f"Loaded stats for {len(team_stats)} teams.")
                # Log sample stats for verification
                teams_playing = list(set(
                    [g.away_team for g in games] + [g.home_team for g in games]
                ))
                self.log("\nTeam stats for today's games:")
                for team in sorted(teams_playing):
                    if team in team_stats:
                        s = team_stats[team]
                        self.log(f"  {team}: NetRtg={s.get('net_rating', 0):+.1f}, "
                                f"OffRtg={s.get('off_rating', 0):.1f}, "
                                f"DefRtg={s.get('def_rating', 0):.1f}, "
                                f"Pace={s.get('pace', 0):.1f}")
            else:
                self.log("Warning: Could not load team stats. Using defaults.")
            
            # Step 3: Get rest days
            self.log("\nCalculating rest days...")
            teams_playing = list(set(
                [g.away_team for g in games] + [g.home_team for g in games]
            ))
            
            try:
                rest_days = get_team_rest_days(teams_playing, season=season)
                self.log(f"Calculated rest days for {len(rest_days)} teams:")
                for team in sorted(teams_playing):
                    days = rest_days.get(team, 1)
                    status = "B2B" if days == 0 else f"{days} day(s) rest"
                    self.log(f"  {team}: {status}")
            except Exception as e:
                self.log(f"Could not get rest days: {e}")
                rest_days = {t: 1 for t in teams_playing}
            
            # Step 4: Find and download injury report
            self.log("\nSearching for latest injury report...")
            output_dir = APP_DIR / "outputs"
            output_dir.mkdir(exist_ok=True)
            cache_file = output_dir / "latest_injury_url.txt"
            
            injury_url = find_latest_injury_pdf(cache_file=cache_file)
            
            if injury_url:
                self.log(f"Found: {injury_url}")
                pdf_bytes = download_injury_pdf(injury_url)
                
                if pdf_bytes:
                    self.log("Downloaded injury report.")
                    
                    # Parse injuries
                    self.log("\nParsing injuries...")
                    self.injuries = parse_injury_pdf(pdf_bytes)
                    self.log(f"Parsed {len(self.injuries)} injury entries.")
                else:
                    self.log("Warning: Failed to download PDF.")
                    self.injuries = []
            else:
                self.log("No recent injury report found.")
                self.injuries = []
            
            # Step 5: Generate predictions using point system
            self.log("\nGenerating predictions (20-factor system)...")
            self.scores = []
            
            for game in games:
                home_rest = rest_days.get(game.home_team, 1)
                away_rest = rest_days.get(game.away_team, 1)
                
                score = score_game(
                    home_team=game.home_team,
                    away_team=game.away_team,
                    team_stats=team_stats,
                    injuries=self.injuries,
                    player_stats={},
                    home_rest_days=home_rest,
                    away_rest_days=away_rest,
                )
                self.scores.append(score)
            
            # Sort by confidence
            self.scores.sort(key=lambda s: abs(s.edge_score_total), reverse=True)
            
            self.log(f"Generated {len(self.scores)} predictions.")
            
            # Update UI on main thread
            self.after(0, self.update_ui)
            self.after(0, self.fetch_complete, True, f"Loaded {len(games)} games")
            
        except Exception as e:
            self.log(f"\nError: {e}")
            import traceback
            self.log(traceback.format_exc())
            self.after(0, self.fetch_complete, False, f"Error: {str(e)[:50]}")
    
    def update_ui(self):
        """Update the UI with fetched data."""
        # Update predictions tree
        for score in self.scores:
            matchup = f"{score.away_team} @ {score.home_team}"
            edge = f"{score.edge_score_total:+.1f}"
            home_prob = f"{score.home_win_prob:.1%}"
            away_prob = f"{score.away_win_prob:.1%}"
            margin = f"{score.projected_margin_home:+.1f}"
            
            # Determine row color based on pick confidence
            if score.home_win_prob > 0.65:
                tag = 'strong_home'
            elif score.home_win_prob > 0.50:
                tag = 'home_pick'
            elif score.away_win_prob > 0.65:
                tag = 'strong_away'
            else:
                tag = 'away_pick'
            
            self.pred_tree.insert(
                '', 'end',
                values=(matchup, score.predicted_winner, edge, home_prob, 
                        away_prob, margin, score.top_5_factors_str),
                tags=(tag,)
            )
        
        # Update game selector for factors tab
        game_options = [f"{s.away_team} @ {s.home_team}" for s in self.scores]
        self.game_selector['values'] = game_options
        if game_options:
            self.game_selector.current(0)
            self.on_game_selected(None)
        
        # Update team selector for stats tab
        teams_playing = sorted(list(set(
            [s.away_team for s in self.scores] + [s.home_team for s in self.scores]
        )))
        self.team_selector['values'] = teams_playing
        if teams_playing:
            self.team_selector.current(0)
            self.on_team_selected(None)
        
        # Update injuries tree
        for injury in self.injuries:
            self.inj_tree.insert(
                '', 'end',
                values=(injury.team, injury.player, injury.status, injury.reason),
                tags=(injury.status,)
            )
    
    def on_game_selected(self, event):
        """Handle game selection in factors tab."""
        # Clear existing factors
        for item in self.factors_tree.get_children():
            self.factors_tree.delete(item)
        
        selection = self.game_selector.get()
        if not selection:
            return
        
        # Find the selected game score
        for score in self.scores:
            matchup = f"{score.away_team} @ {score.home_team}"
            if matchup == selection:
                # Display factors
                for factor in sorted(score.factors, key=lambda f: abs(f.contribution), reverse=True):
                    signed = f"{factor.signed_value:+.3f}"
                    contrib = f"{factor.contribution:+.2f}"
                    
                    if factor.contribution > 0.5:
                        tag = 'positive'
                    elif factor.contribution < -0.5:
                        tag = 'negative'
                    else:
                        tag = 'neutral'
                    
                    self.factors_tree.insert(
                        '', 'end',
                        values=(factor.display_name, factor.weight, signed, 
                                contrib, factor.inputs_used),
                        tags=(tag,)
                    )
                break
    
    def fetch_complete(self, success: bool, message: str):
        """Called when fetch is complete."""
        self.progress.stop()
        self.progress.pack_forget()
        self.fetch_button.config(state=tk.NORMAL)
        
        if success and self.scores:
            self.save_button.config(state=tk.NORMAL)
        
        self.status_var.set(message)
        
    def save_to_csv(self):
        """Save predictions and injuries to CSV files."""
        try:
            import pandas as pd
            
            output_dir = APP_DIR / "outputs"
            output_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Save predictions
            if self.scores:
                pred_data = []
                for score in self.scores:
                    pred_data.append({
                        "away_team": score.away_team,
                        "home_team": score.home_team,
                        "predicted_winner": score.predicted_winner,
                        "edge_score": score.edge_score_total,
                        "home_win_prob": score.home_win_prob,
                        "away_win_prob": score.away_win_prob,
                        "projected_margin_home": score.projected_margin_home,
                        "top_5_factors": score.top_5_factors_str,
                    })
                
                pred_path = output_dir / f"predictions_{timestamp}.csv"
                pd.DataFrame(pred_data).to_csv(pred_path, index=False)
                self.log(f"\nSaved predictions to: {pred_path.name}")
                
                # Save factors
                factors_data = []
                for score in self.scores:
                    matchup = f"{score.away_team}@{score.home_team}"
                    for factor in score.factors:
                        factors_data.append({
                            "matchup": matchup,
                            "factor_name": factor.display_name,
                            "weight": factor.weight,
                            "signed_value": round(factor.signed_value, 3),
                            "contribution": round(factor.contribution, 2),
                            "inputs_used": factor.inputs_used,
                        })
                
                factors_path = output_dir / f"factors_{timestamp}.csv"
                pd.DataFrame(factors_data).to_csv(factors_path, index=False)
                self.log(f"Saved factors to: {factors_path.name}")
            
            # Save injuries
            if self.injuries:
                inj_data = []
                for inj in self.injuries:
                    inj_data.append({
                        "team": inj.team,
                        "player": inj.player,
                        "status": inj.status,
                        "reason": inj.reason,
                    })
                
                inj_path = output_dir / f"injuries_{timestamp}.csv"
                pd.DataFrame(inj_data).to_csv(inj_path, index=False)
                self.log(f"Saved injuries to: {inj_path.name}")
            
            messagebox.showinfo(
                "Saved",
                f"Files saved to:\n{output_dir}"
            )
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")


def main():
    """Main entry point."""
    app = NBAPredictor()
    app.mainloop()


if __name__ == "__main__":
    main()
