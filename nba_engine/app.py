#!/usr/bin/env python3
"""
NBA Prediction Engine - GUI Application

A simple GUI that fetches today's NBA predictions and displays them
in an easy-to-read format.
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

from ingest.schedule import get_todays_games, get_team_ratings, get_current_season
from ingest.injuries import (
    find_latest_injury_pdf,
    download_injury_pdf,
    parse_injury_pdf,
)
from model.pregame import predict_games


class NBAPredictor(tk.Tk):
    """Main application window for NBA Prediction Engine."""
    
    def __init__(self):
        super().__init__()
        
        self.title("NBA Prediction Engine v1")
        self.geometry("900x700")
        self.minsize(700, 500)
        
        # Configure style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Configure colors
        self.configure(bg='#1a1a2e')
        self.style.configure('TFrame', background='#1a1a2e')
        self.style.configure('TLabel', background='#1a1a2e', foreground='#eee')
        self.style.configure('TButton', padding=10, font=('Segoe UI', 11))
        self.style.configure('Header.TLabel', font=('Segoe UI', 24, 'bold'), foreground='#ff6b35')
        self.style.configure('SubHeader.TLabel', font=('Segoe UI', 14), foreground='#aaa')
        self.style.configure('Status.TLabel', font=('Segoe UI', 10), foreground='#888')
        
        # Create main container
        self.main_frame = ttk.Frame(self, padding=20)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_frame = ttk.Frame(self.main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        title_label = ttk.Label(
            header_frame, 
            text="🏀 NBA Prediction Engine",
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
        
        # Injuries tab
        self.injuries_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.injuries_frame, text="🏥 Injuries")
        
        # Create injuries treeview
        self.create_injuries_tree()
        
        # Log tab
        self.log_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.log_frame, text="📝 Log")
        
        self.log_text = scrolledtext.ScrolledText(
            self.log_frame,
            wrap=tk.WORD,
            font=('Consolas', 10),
            bg='#0f0f1a',
            fg='#0f0',
            insertbackground='#0f0'
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Store data
        self.predictions = []
        self.injuries = []
        
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
        
        # Treeview
        columns = ('matchup', 'margin', 'home_prob', 'away_prob', 'time')
        self.pred_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            yscrollcommand=scrollbar.set
        )
        
        # Configure columns
        self.pred_tree.heading('matchup', text='Matchup')
        self.pred_tree.heading('margin', text='Projected Margin')
        self.pred_tree.heading('home_prob', text='Home Win %')
        self.pred_tree.heading('away_prob', text='Away Win %')
        self.pred_tree.heading('time', text='Start Time (UTC)')
        
        self.pred_tree.column('matchup', width=150, anchor='center')
        self.pred_tree.column('margin', width=120, anchor='center')
        self.pred_tree.column('home_prob', width=100, anchor='center')
        self.pred_tree.column('away_prob', width=100, anchor='center')
        self.pred_tree.column('time', width=150, anchor='center')
        
        self.pred_tree.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.pred_tree.yview)
        
        # Style alternating rows
        self.pred_tree.tag_configure('oddrow', background='#252540')
        self.pred_tree.tag_configure('evenrow', background='#1a1a2e')
        self.pred_tree.tag_configure('favorite', background='#1a3a1a')
        
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
        
        # Style by status
        self.inj_tree.tag_configure('Out', background='#3a1a1a', foreground='#ff6b6b')
        self.inj_tree.tag_configure('Doubtful', background='#3a2a1a', foreground='#ffa94d')
        self.inj_tree.tag_configure('Questionable', background='#3a3a1a', foreground='#ffd43b')
        self.inj_tree.tag_configure('Probable', background='#1a3a1a', foreground='#69db7c')
        
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
            
            # Step 2: Fetch team ratings
            self.log("\nFetching team ratings...")
            season = get_current_season()
            self.log(f"Season: {season}")
            
            ratings = get_team_ratings(season=season)
            
            if ratings:
                self.log(f"Loaded ratings for {len(ratings)} teams.")
            else:
                self.log("Warning: Could not load team ratings. Using defaults.")
            
            # Step 3: Find and download injury report
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
            
            # Step 4: Generate predictions
            self.log("\nGenerating predictions...")
            self.predictions = predict_games(games, ratings)
            self.log(f"Generated {len(self.predictions)} predictions.")
            
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
        for i, pred in enumerate(self.predictions):
            matchup = f"{pred.away_team} @ {pred.home_team}"
            margin = f"{pred.projected_margin_home:+.1f}"
            home_prob = f"{pred.home_win_prob:.1%}"
            away_prob = f"{pred.away_win_prob:.1%}"
            time_str = pred.start_time_utc[:16] if pred.start_time_utc else "TBD"
            
            tag = 'evenrow' if i % 2 == 0 else 'oddrow'
            if pred.home_win_prob > 0.65 or pred.away_win_prob > 0.65:
                tag = 'favorite'
            
            self.pred_tree.insert(
                '', 'end',
                values=(matchup, margin, home_prob, away_prob, time_str),
                tags=(tag,)
            )
        
        # Update injuries tree
        for injury in self.injuries:
            self.inj_tree.insert(
                '', 'end',
                values=(injury.team, injury.player, injury.status, injury.reason),
                tags=(injury.status,)
            )
    
    def fetch_complete(self, success: bool, message: str):
        """Called when fetch is complete."""
        self.progress.stop()
        self.progress.pack_forget()
        self.fetch_button.config(state=tk.NORMAL)
        
        if success and self.predictions:
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
            if self.predictions:
                pred_data = []
                for pred in self.predictions:
                    pred_data.append({
                        "away_team": pred.away_team,
                        "home_team": pred.home_team,
                        "projected_margin_home": pred.projected_margin_home,
                        "home_win_prob": pred.home_win_prob,
                        "away_win_prob": pred.away_win_prob,
                        "start_time_utc": pred.start_time_utc,
                    })
                
                pred_path = output_dir / f"predictions_{timestamp}.csv"
                pd.DataFrame(pred_data).to_csv(pred_path, index=False)
                self.log(f"\nSaved predictions to: {pred_path.name}")
            
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
