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
        
        # Buttons
        button_frame = ttk.Frame(self.main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        self.fetch_button = ttk.Button(button_frame, text="🔄 Fetch Today's Predictions", command=self.start_fetch)
        self.fetch_button.pack(side=tk.LEFT)
        
        self.save_button = ttk.Button(button_frame, text="💾 Save to CSV", command=self.save_to_csv, state=tk.DISABLED)
        self.save_button.pack(side=tk.LEFT, padx=10)
        
        self.status_var = tk.StringVar(value="Click 'Fetch Today's Predictions' to start")
        ttk.Label(button_frame, textvariable=self.status_var, style='Status.TLabel').pack(side=tk.RIGHT)
        
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
                
                score = score_game_v3(
                    home_team=game.home_team,
                    away_team=game.away_team,
                    home_strength=home_lineup,
                    away_strength=away_lineup,
                    home_stats=home_stats,
                    away_stats=away_stats,
                    home_rest_days=rest_days.get(game.home_team, 1),
                    away_rest_days=rest_days.get(game.away_team, 1),
                )
                self.scores.append(score)
            
            # Sort by confidence (highest first)
            self.scores.sort(key=lambda s: (s.confidence, abs(s.edge_score_total)), reverse=True)
            
            self.log(f"Generated {len(self.scores)} predictions")
            
            self.after(0, self.update_ui)
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
        
        stat_info = [
            ('net_rating', 'Net Rating', 'Points per 100 poss differential'),
            ('off_rating', 'Offensive Rating', 'Points scored per 100 poss'),
            ('def_rating', 'Defensive Rating', 'Points allowed per 100 poss'),
            ('home_net_rating', 'Home Net Rating', 'Net rating at home'),
            ('road_net_rating', 'Road Net Rating', 'Net rating on road'),
            ('pace', 'Pace', 'Possessions per game'),
            ('efg_pct', 'Effective FG%', 'Shooting efficiency'),
            ('fg3_pct', '3-Point %', 'Three-point shooting'),
            ('ft_rate', 'Free Throw Rate', 'FTA per FGA'),
            ('tov_pct', 'Turnover %', 'Turnovers per possession'),
            ('oreb_pct', 'Off Rebound %', 'Offensive rebounding rate'),
        ]
        
        for key, name, desc in stat_info:
            val = stats.get(key, 'N/A')
            if val != 'N/A':
                if isinstance(val, float):
                    if val < 1:
                        display = f"{val:.1%}"
                    else:
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


def main():
    app = NBAPredictor()
    app.mainloop()


if __name__ == "__main__":
    main()
