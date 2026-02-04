#!/usr/bin/env python3
"""
NBA Prediction Engine v3 - GUI Application

Features:
- Run today's predictions with one click
- Excel tracking with overwrite-by-day
- Winrate dashboard by confidence level
- Manual result entry via Excel file

NOTE: This engine ONLY supports today's slate. No historical modes.
"""

import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from pathlib import Path


class NBAPredictor(tk.Tk):
    """Main application window for NBA Prediction Engine."""
    
    def __init__(self):
        super().__init__()
        
        self.title("NBA Prediction Engine v3")
        self.geometry("1200x800")
        self.minsize(1000, 700)
        
        # Data storage
        self.scores = []
        self.injuries = []
        self.team_stats = {}
        
        # Configure styles
        self.setup_styles()
        
        # Create UI
        self.create_widgets()
        
        # Load initial winrate stats
        self.refresh_winrates()
    
    def setup_styles(self):
        """Configure ttk styles."""
        style = ttk.Style()
        
        # Main button style
        style.configure(
            'Main.TButton',
            font=('Segoe UI', 11, 'bold'),
            padding=(15, 8)
        )
        
        # Secondary button style
        style.configure(
            'Secondary.TButton',
            font=('Segoe UI', 10),
            padding=(10, 5)
        )
        
        # Status label
        style.configure(
            'Status.TLabel',
            font=('Segoe UI', 10),
            foreground='#666666'
        )
        
        # Winrate display
        style.configure(
            'Winrate.TLabel',
            font=('Segoe UI', 11, 'bold'),
        )
        
        # Header
        style.configure(
            'Header.TLabel',
            font=('Segoe UI', 14, 'bold'),
        )
    
    def create_widgets(self):
        """Create all UI widgets."""
        # Main container
        self.main_frame = ttk.Frame(self, padding=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header frame
        header_frame = ttk.Frame(self.main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(
            header_frame,
            text="NBA Prediction Engine v3",
            style='Header.TLabel'
        ).pack(side=tk.LEFT)
        
        # Date display
        self.date_var = tk.StringVar(value=datetime.now().strftime("%A, %B %d, %Y"))
        ttk.Label(
            header_frame,
            textvariable=self.date_var,
            style='Status.TLabel'
        ).pack(side=tk.RIGHT)
        
        # Button frame
        button_frame = ttk.Frame(self.main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        # Run button
        self.run_button = ttk.Button(
            button_frame,
            text="▶ Run Today's Predictions",
            command=self.start_prediction_run,
            style='Main.TButton'
        )
        self.run_button.pack(side=tk.LEFT, padx=5)
        
        # Refresh winrates button
        self.refresh_button = ttk.Button(
            button_frame,
            text="🔄 Refresh Winrates",
            command=self.refresh_winrates,
            style='Secondary.TButton'
        )
        self.refresh_button.pack(side=tk.LEFT, padx=5)
        
        # Open Excel button
        self.open_excel_button = ttk.Button(
            button_frame,
            text="📂 Open Tracking File",
            command=self.open_tracking_file,
            style='Secondary.TButton'
        )
        self.open_excel_button.pack(side=tk.LEFT, padx=5)
        
        # Status label
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(
            button_frame,
            textvariable=self.status_var,
            style='Status.TLabel'
        ).pack(side=tk.RIGHT, padx=10)
        
        # Winrate display frame
        winrate_frame = ttk.LabelFrame(self.main_frame, text="Performance Dashboard", padding=10)
        winrate_frame.pack(fill=tk.X, pady=10)
        
        # Overall winrate
        overall_frame = ttk.Frame(winrate_frame)
        overall_frame.pack(side=tk.LEFT, padx=20)
        
        ttk.Label(overall_frame, text="OVERALL", style='Winrate.TLabel').pack()
        self.overall_winrate_var = tk.StringVar(value="--")
        ttk.Label(overall_frame, textvariable=self.overall_winrate_var, font=('Segoe UI', 20, 'bold')).pack()
        self.overall_record_var = tk.StringVar(value="0-0")
        ttk.Label(overall_frame, textvariable=self.overall_record_var, style='Status.TLabel').pack()
        
        # HIGH confidence
        high_frame = ttk.Frame(winrate_frame)
        high_frame.pack(side=tk.LEFT, padx=20)
        
        ttk.Label(high_frame, text="HIGH", style='Winrate.TLabel', foreground='green').pack()
        self.high_winrate_var = tk.StringVar(value="--")
        ttk.Label(high_frame, textvariable=self.high_winrate_var, font=('Segoe UI', 18, 'bold'), foreground='green').pack()
        self.high_record_var = tk.StringVar(value="0-0")
        ttk.Label(high_frame, textvariable=self.high_record_var, style='Status.TLabel').pack()
        
        # MEDIUM confidence
        medium_frame = ttk.Frame(winrate_frame)
        medium_frame.pack(side=tk.LEFT, padx=20)
        
        ttk.Label(medium_frame, text="MEDIUM", style='Winrate.TLabel', foreground='#CC7700').pack()
        self.medium_winrate_var = tk.StringVar(value="--")
        ttk.Label(medium_frame, textvariable=self.medium_winrate_var, font=('Segoe UI', 18, 'bold'), foreground='#CC7700').pack()
        self.medium_record_var = tk.StringVar(value="0-0")
        ttk.Label(medium_frame, textvariable=self.medium_record_var, style='Status.TLabel').pack()
        
        # LOW confidence
        low_frame = ttk.Frame(winrate_frame)
        low_frame.pack(side=tk.LEFT, padx=20)
        
        ttk.Label(low_frame, text="LOW", style='Winrate.TLabel', foreground='red').pack()
        self.low_winrate_var = tk.StringVar(value="--")
        ttk.Label(low_frame, textvariable=self.low_winrate_var, font=('Segoe UI', 18, 'bold'), foreground='red').pack()
        self.low_record_var = tk.StringVar(value="0-0")
        ttk.Label(low_frame, textvariable=self.low_record_var, style='Status.TLabel').pack()
        
        # Pending
        pending_frame = ttk.Frame(winrate_frame)
        pending_frame.pack(side=tk.LEFT, padx=20)
        
        ttk.Label(pending_frame, text="PENDING", style='Winrate.TLabel', foreground='#666666').pack()
        self.pending_var = tk.StringVar(value="0")
        ttk.Label(pending_frame, textvariable=self.pending_var, font=('Segoe UI', 18, 'bold'), foreground='#666666').pack()
        ttk.Label(pending_frame, text="awaiting results", style='Status.TLabel').pack()
        
        # Notebook for tabs
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Predictions tab
        self.predictions_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.predictions_frame, text="📊 Today's Predictions")
        self.create_predictions_tree()
        
        # Factors tab
        self.factors_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.factors_frame, text="📈 Factor Breakdown")
        self.create_factors_view()
        
        # Injuries tab
        self.injuries_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.injuries_frame, text="🏥 Injuries")
        self.create_injuries_tree()
        
        # Log tab
        self.log_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.log_frame, text="📝 Log")
        self.create_log_view()
    
    def create_predictions_tree(self):
        """Create the predictions treeview."""
        columns = (
            'matchup', 'pick', 'side', 'confidence', 'edge', 
            'home_prob', 'away_prob', 'margin'
        )
        
        self.pred_tree = ttk.Treeview(
            self.predictions_frame,
            columns=columns,
            show='headings',
            selectmode='browse'
        )
        
        # Configure columns
        self.pred_tree.heading('matchup', text='Matchup')
        self.pred_tree.heading('pick', text='Pick')
        self.pred_tree.heading('side', text='Side')
        self.pred_tree.heading('confidence', text='Confidence')
        self.pred_tree.heading('edge', text='Edge')
        self.pred_tree.heading('home_prob', text='Home %')
        self.pred_tree.heading('away_prob', text='Away %')
        self.pred_tree.heading('margin', text='Margin')
        
        self.pred_tree.column('matchup', width=150, anchor='center')
        self.pred_tree.column('pick', width=80, anchor='center')
        self.pred_tree.column('side', width=80, anchor='center')
        self.pred_tree.column('confidence', width=100, anchor='center')
        self.pred_tree.column('edge', width=80, anchor='center')
        self.pred_tree.column('home_prob', width=80, anchor='center')
        self.pred_tree.column('away_prob', width=80, anchor='center')
        self.pred_tree.column('margin', width=80, anchor='center')
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.predictions_frame, orient=tk.VERTICAL, command=self.pred_tree.yview)
        self.pred_tree.configure(yscrollcommand=scrollbar.set)
        
        self.pred_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind selection
        self.pred_tree.bind('<<TreeviewSelect>>', self.on_prediction_selected)
        
        # Configure row colors
        self.pred_tree.tag_configure('high', background='#E8F5E9')
        self.pred_tree.tag_configure('medium', background='#FFF3E0')
        self.pred_tree.tag_configure('low', background='#FFEBEE')
    
    def create_factors_view(self):
        """Create the factor breakdown view."""
        # Game selector
        selector_frame = ttk.Frame(self.factors_frame)
        selector_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(selector_frame, text="Select Game:").pack(side=tk.LEFT, padx=5)
        
        self.game_selector_var = tk.StringVar()
        self.game_selector = ttk.Combobox(
            selector_frame,
            textvariable=self.game_selector_var,
            state='readonly',
            width=30
        )
        self.game_selector.pack(side=tk.LEFT, padx=5)
        self.game_selector.bind('<<ComboboxSelected>>', self.on_game_selected)
        
        # Factors tree
        columns = ('factor', 'weight', 'signed_value', 'contribution', 'inputs')
        
        self.factors_tree = ttk.Treeview(
            self.factors_frame,
            columns=columns,
            show='headings',
            selectmode='browse'
        )
        
        self.factors_tree.heading('factor', text='Factor')
        self.factors_tree.heading('weight', text='Weight')
        self.factors_tree.heading('signed_value', text='Signed Value')
        self.factors_tree.heading('contribution', text='Contribution')
        self.factors_tree.heading('inputs', text='Inputs Used')
        
        self.factors_tree.column('factor', width=200)
        self.factors_tree.column('weight', width=80, anchor='center')
        self.factors_tree.column('signed_value', width=100, anchor='center')
        self.factors_tree.column('contribution', width=100, anchor='center')
        self.factors_tree.column('inputs', width=400)
        
        scrollbar = ttk.Scrollbar(self.factors_frame, orient=tk.VERTICAL, command=self.factors_tree.yview)
        self.factors_tree.configure(yscrollcommand=scrollbar.set)
        
        self.factors_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Color tags
        self.factors_tree.tag_configure('positive', foreground='green')
        self.factors_tree.tag_configure('negative', foreground='red')
        self.factors_tree.tag_configure('neutral', foreground='gray')
    
    def create_injuries_tree(self):
        """Create the injuries treeview."""
        columns = ('team', 'player', 'status', 'reason')
        
        self.injuries_tree = ttk.Treeview(
            self.injuries_frame,
            columns=columns,
            show='headings',
            selectmode='browse'
        )
        
        self.injuries_tree.heading('team', text='Team')
        self.injuries_tree.heading('player', text='Player')
        self.injuries_tree.heading('status', text='Status')
        self.injuries_tree.heading('reason', text='Reason')
        
        self.injuries_tree.column('team', width=80, anchor='center')
        self.injuries_tree.column('player', width=200)
        self.injuries_tree.column('status', width=120, anchor='center')
        self.injuries_tree.column('reason', width=400)
        
        scrollbar = ttk.Scrollbar(self.injuries_frame, orient=tk.VERTICAL, command=self.injuries_tree.yview)
        self.injuries_tree.configure(yscrollcommand=scrollbar.set)
        
        self.injuries_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Status color tags
        self.injuries_tree.tag_configure('out', background='#FFCDD2', foreground='#B71C1C')
        self.injuries_tree.tag_configure('doubtful', background='#FFE0B2', foreground='#E65100')
        self.injuries_tree.tag_configure('questionable', background='#FFF9C4', foreground='#F57F17')
        self.injuries_tree.tag_configure('probable', background='#C8E6C9', foreground='#1B5E20')
    
    def create_log_view(self):
        """Create the log text view."""
        self.log_text = tk.Text(
            self.log_frame,
            wrap=tk.WORD,
            font=('Consolas', 10),
            state=tk.DISABLED
        )
        
        scrollbar = ttk.Scrollbar(self.log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def log(self, message: str):
        """Add a message to the log."""
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
    
    def refresh_winrates(self):
        """Refresh winrate statistics from Excel file."""
        try:
            from tracking import ExcelTracker
            
            tracker = ExcelTracker()
            stats = tracker.compute_winrate_stats()
            
            # Update overall
            if stats.total_graded > 0:
                self.overall_winrate_var.set(f"{stats.win_pct:.1f}%")
                self.overall_record_var.set(f"{stats.wins}-{stats.losses}")
            else:
                self.overall_winrate_var.set("--")
                self.overall_record_var.set("0-0")
            
            # Update HIGH
            if stats.high_graded > 0:
                self.high_winrate_var.set(f"{stats.high_win_pct:.1f}%")
                self.high_record_var.set(f"{stats.high_wins}-{stats.high_losses}")
            else:
                self.high_winrate_var.set("--")
                self.high_record_var.set("0-0")
            
            # Update MEDIUM
            if stats.medium_graded > 0:
                self.medium_winrate_var.set(f"{stats.medium_win_pct:.1f}%")
                self.medium_record_var.set(f"{stats.medium_wins}-{stats.medium_losses}")
            else:
                self.medium_winrate_var.set("--")
                self.medium_record_var.set("0-0")
            
            # Update LOW
            if stats.low_graded > 0:
                self.low_winrate_var.set(f"{stats.low_win_pct:.1f}%")
                self.low_record_var.set(f"{stats.low_wins}-{stats.low_losses}")
            else:
                self.low_winrate_var.set("--")
                self.low_record_var.set("0-0")
            
            # Update pending
            self.pending_var.set(str(stats.pending_total))
            
            # Update summary sheet
            tracker.update_summary_sheet(stats)
            
            self.log(f"Winrates refreshed: {stats.wins}/{stats.total_graded} overall, {stats.pending_total} pending")
            
        except Exception as e:
            self.log(f"Error refreshing winrates: {e}")
    
    def start_prediction_run(self):
        """Start the prediction run in a background thread."""
        self.run_button.config(state=tk.DISABLED)
        self.status_var.set("Running predictions...")
        self.log("\n" + "=" * 60)
        self.log(f"Starting prediction run at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("=" * 60)
        
        thread = threading.Thread(target=self.run_predictions, daemon=True)
        thread.start()
    
    def run_predictions(self):
        """Run the prediction engine (background thread)."""
        try:
            from ingest.schedule import get_todays_games, get_current_season
            from ingest.team_stats import (
                get_comprehensive_team_stats,
                get_team_rest_days,
                get_fallback_team_strength,
            )
            from ingest.player_stats import get_player_stats, get_fallback_player_stats
            from ingest.injuries import (
                find_latest_injury_pdf,
                download_injury_pdf,
                parse_injury_pdf,
            )
            from ingest.inactives import fetch_all_game_inactives, merge_inactives_with_injuries
            from ingest.known_absences import load_known_absences, merge_known_absences_with_injuries
            from ingest.news_absences import fetch_all_news_absences, merge_news_absences_with_injuries
            from model.lineup_adjustment import calculate_lineup_adjusted_strength
            from model.point_system import score_game_v3, validate_system
            from tracking import ExcelTracker, PickEntry
            
            # Validate system
            self.log("\n[1/7] Validating scoring system...")
            validate_system()
            self.log("  OK - Weights sum to 100")
            
            # Get games
            self.log("\n[2/7] Fetching today's games...")
            games, api_date, is_current = get_todays_games()
            
            if not games:
                self.log("  No games scheduled for today")
                self.after(0, lambda: self.status_var.set("No games today"))
                self.after(0, lambda: self.run_button.config(state=tk.NORMAL))
                return
            
            self.log(f"  Found {len(games)} games")
            for game in games:
                self.log(f"    {game.away_team} @ {game.home_team}")
            
            # Get team stats
            self.log("\n[3/7] Fetching team statistics...")
            season = get_current_season()
            team_strength = get_comprehensive_team_stats(season)
            self.team_stats = team_strength
            
            team_stats_available = len(team_strength) > 0
            
            if not team_strength:
                self.log("  Warning: Using fallback stats")
                for game in games:
                    for team in [game.home_team, game.away_team]:
                        if team not in team_strength:
                            team_strength[team] = get_fallback_team_strength(team)
            else:
                self.log(f"  Loaded stats for {len(team_strength)} teams")
            
            # Get player stats
            self.log("\n[4/7] Fetching player statistics...")
            player_stats = get_player_stats(season)
            
            player_stats_available = len(player_stats) > 0
            
            if not player_stats:
                self.log("  Warning: Using fallback player stats")
                player_stats = get_fallback_player_stats(
                    [g.home_team for g in games] + [g.away_team for g in games]
                )
            else:
                total_players = sum(len(p) for p in player_stats.values())
                self.log(f"  Loaded {total_players} players")
            
            # Get rest days
            self.log("\n[5/7] Calculating rest days...")
            rest_days = get_team_rest_days(season)
            self.log(f"  Calculated for {len(rest_days)} teams")
            
            # Get injuries
            self.log("\n[6/7] Fetching injury data...")
            injury_url = find_latest_injury_pdf()
            injuries = []
            injury_report_available = False
            
            if injury_url:
                self.log(f"  Found injury report")
                pdf_bytes = download_injury_pdf(injury_url)
                if pdf_bytes:
                    injuries = parse_injury_pdf(pdf_bytes)
                    injury_report_available = True
                    self.log(f"  Parsed {len(injuries)} entries")
            
            # Merge additional injury sources
            known_absences = load_known_absences()
            if known_absences:
                injuries = merge_known_absences_with_injuries(injuries, known_absences)
                self.log(f"  Added {len(known_absences)} manual absences")
            
            teams_playing = list(set([g.away_team for g in games] + [g.home_team for g in games]))
            news_absences = fetch_all_news_absences(teams_playing)
            if news_absences:
                injuries = merge_news_absences_with_injuries(injuries, news_absences)
                self.log(f"  Added {len(news_absences)} ESPN entries")
            
            game_ids = [g.game_id for g in games if g.game_id]
            inactives = {}
            if game_ids:
                inactives = fetch_all_game_inactives(game_ids)
                if inactives:
                    injuries = merge_inactives_with_injuries(injuries, inactives)
                    self.log(f"  Merged inactives")
            
            self.injuries = injuries
            
            # Generate predictions
            self.log("\n[7/7] Generating predictions...")
            scores = []
            
            for game in games:
                home_ts = team_strength.get(game.home_team)
                away_ts = team_strength.get(game.away_team)
                
                if home_ts is None or away_ts is None:
                    self.log(f"  Skipping {game.away_team} @ {game.home_team} (missing stats)")
                    continue
                
                home_players = player_stats.get(game.home_team, [])
                away_players = player_stats.get(game.away_team, [])
                
                home_lineup = calculate_lineup_adjusted_strength(
                    team=game.home_team,
                    team_strength=home_ts,
                    players=home_players,
                    injuries=injuries,
                    is_home=True,
                    inactives=inactives,
                    injury_report_available=injury_report_available,
                )
                
                away_lineup = calculate_lineup_adjusted_strength(
                    team=game.away_team,
                    team_strength=away_ts,
                    players=away_players,
                    injuries=injuries,
                    is_home=False,
                    inactives=inactives,
                    injury_report_available=injury_report_available,
                )
                
                home_rest = rest_days.get(game.home_team, 1)
                away_rest = rest_days.get(game.away_team, 1)
                
                home_stats = home_ts.to_dict() if hasattr(home_ts, 'to_dict') else home_ts
                away_stats = away_ts.to_dict() if hasattr(away_ts, 'to_dict') else away_ts
                
                home_injuries = [inj for inj in injuries if getattr(inj, 'team', '').upper() == game.home_team.upper()]
                away_injuries = [inj for inj in injuries if getattr(inj, 'team', '').upper() == game.away_team.upper()]
                
                score = score_game_v3(
                    home_team=game.home_team,
                    away_team=game.away_team,
                    home_strength=home_lineup,
                    away_strength=away_lineup,
                    home_stats=home_stats,
                    away_stats=away_stats,
                    home_rest_days=home_rest,
                    away_rest_days=away_rest,
                    home_players=home_players,
                    away_players=away_players,
                    home_injuries=home_injuries,
                    away_injuries=away_injuries,
                )
                
                score.game_id = game.game_id
                scores.append(score)
            
            # Sort by confidence
            scores.sort(key=lambda s: (abs(s.edge_score_total), s.confidence), reverse=True)
            self.scores = scores
            
            self.log(f"\n  Generated {len(scores)} predictions")
            
            # Save to Excel
            self.log("\nSaving to Excel tracking...")
            
            now = datetime.now()
            run_date = now.strftime("%Y-%m-%d")
            run_timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
            
            # Determine data confidence
            if team_stats_available and player_stats_available and injury_report_available:
                data_confidence = "HIGH"
            elif team_stats_available and injury_report_available:
                data_confidence = "MEDIUM"
            else:
                data_confidence = "LOW"
            
            # Create entries
            entries = []
            for score in scores:
                pick_side = "HOME" if score.predicted_winner == score.home_team else "AWAY"
                
                entry = PickEntry(
                    run_date=run_date,
                    run_timestamp=run_timestamp,
                    game_id=getattr(score, 'game_id', ''),
                    away_team=score.away_team,
                    home_team=score.home_team,
                    pick_team=score.predicted_winner,
                    pick_side=pick_side,
                    confidence_level=score.confidence_label.upper(),
                    edge_score_total=round(score.edge_score_total, 2),
                    projected_margin_home=round(score.projected_margin_home, 1),
                    home_win_prob=round(score.home_win_prob, 3),
                    away_win_prob=round(score.away_win_prob, 3),
                    top_5_factors=score.top_5_factors_str,
                    data_confidence=data_confidence,
                )
                entries.append(entry)
            
            try:
                tracker = ExcelTracker()
                saved_count = tracker.save_predictions(entries)
                self.log(f"  Saved {saved_count} predictions (overwrote any previous for today)")
                
                # Update summary
                stats = tracker.refresh_winrates()
                self.log(f"  Updated summary sheet")
                
            except IOError as e:
                self.log(f"  ERROR: {e}")
                self.after(0, lambda: messagebox.showerror(
                    "File Error",
                    "Please close NBA_Engine_Tracking.xlsx and try again."
                ))
                self.after(0, lambda: self.run_button.config(state=tk.NORMAL))
                return
            
            # Update UI
            self.after(0, self.update_predictions_display)
            self.after(0, self.update_injuries_display)
            self.after(0, self.update_game_selector)
            self.after(0, self.refresh_winrates)
            
            self.after(0, lambda: self.status_var.set(f"Predictions updated for {run_date}"))
            self.log(f"\n✓ Complete! Predictions saved for {run_date}")
            
        except Exception as e:
            import traceback
            self.log(f"\nERROR: {e}")
            self.log(traceback.format_exc())
            self.after(0, lambda: self.status_var.set(f"Error: {e}"))
        finally:
            self.after(0, lambda: self.run_button.config(state=tk.NORMAL))
    
    def update_predictions_display(self):
        """Update the predictions treeview."""
        # Clear existing
        for item in self.pred_tree.get_children():
            self.pred_tree.delete(item)
        
        # Add predictions
        for score in self.scores:
            matchup = f"{score.away_team} @ {score.home_team}"
            pick_side = "HOME" if score.predicted_winner == score.home_team else "AWAY"
            conf_label = score.confidence_label.upper()
            
            # Determine tag
            tag = conf_label.lower()
            
            self.pred_tree.insert('', tk.END, values=(
                matchup,
                score.predicted_winner,
                pick_side,
                conf_label,
                f"{score.edge_score_total:+.1f}",
                f"{score.home_win_prob:.1%}",
                f"{score.away_win_prob:.1%}",
                f"{score.projected_margin_home:+.1f}",
            ), tags=(tag,))
    
    def update_injuries_display(self):
        """Update the injuries treeview."""
        # Clear existing
        for item in self.injuries_tree.get_children():
            self.injuries_tree.delete(item)
        
        # Add injuries
        for injury in self.injuries:
            status = getattr(injury, 'status', 'Unknown')
            status_lower = status.lower()
            
            # Determine tag
            if 'out' in status_lower:
                tag = 'out'
            elif 'doubtful' in status_lower:
                tag = 'doubtful'
            elif 'questionable' in status_lower:
                tag = 'questionable'
            elif 'probable' in status_lower:
                tag = 'probable'
            else:
                tag = ''
            
            self.injuries_tree.insert('', tk.END, values=(
                getattr(injury, 'team', ''),
                getattr(injury, 'player', ''),
                status,
                getattr(injury, 'reason', ''),
            ), tags=(tag,) if tag else ())
    
    def update_game_selector(self):
        """Update the game selector combobox."""
        games = [f"{s.away_team} @ {s.home_team}" for s in self.scores]
        self.game_selector['values'] = games
        if games:
            self.game_selector.current(0)
            self.on_game_selected(None)
    
    def on_prediction_selected(self, event):
        """Handle prediction selection."""
        selection = self.pred_tree.selection()
        if not selection:
            return
        
        # Get selected matchup
        item = self.pred_tree.item(selection[0])
        matchup = item['values'][0]
        
        # Find and select in game selector
        games = list(self.game_selector['values'])
        if matchup in games:
            self.game_selector.current(games.index(matchup))
            self.on_game_selected(None)
            self.notebook.select(self.factors_frame)
    
    def on_game_selected(self, event):
        """Handle game selection for factor breakdown."""
        # Clear existing
        for item in self.factors_tree.get_children():
            self.factors_tree.delete(item)
        
        selected = self.game_selector_var.get()
        if not selected:
            return
        
        # Find the matching score
        for score in self.scores:
            matchup = f"{score.away_team} @ {score.home_team}"
            if matchup == selected:
                # Display factors
                for factor in score.factors:
                    # Determine tag
                    if factor.contribution > 0.5:
                        tag = 'positive'
                    elif factor.contribution < -0.5:
                        tag = 'negative'
                    else:
                        tag = 'neutral'
                    
                    self.factors_tree.insert('', tk.END, values=(
                        factor.name,
                        factor.weight,
                        f"{factor.signed_value:+.3f}",
                        f"{factor.contribution:+.2f}",
                        factor.inputs_used,
                    ), tags=(tag,))
                break
    
    def open_tracking_file(self):
        """Open the tracking Excel file."""
        from tracking import TRACKING_FILE_PATH
        import subprocess
        import platform
        
        if not TRACKING_FILE_PATH.exists():
            messagebox.showinfo(
                "File Not Found",
                "No tracking file exists yet. Run predictions first."
            )
            return
        
        try:
            if platform.system() == 'Windows':
                import os
                os.startfile(str(TRACKING_FILE_PATH))
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', str(TRACKING_FILE_PATH)])
            else:  # Linux
                subprocess.run(['xdg-open', str(TRACKING_FILE_PATH)])
            
            self.log(f"Opened: {TRACKING_FILE_PATH}")
        except Exception as e:
            self.log(f"Error opening file: {e}")
            messagebox.showerror("Error", f"Could not open file: {e}")


def main():
    """Main entry point."""
    app = NBAPredictor()
    app.mainloop()


if __name__ == "__main__":
    main()
