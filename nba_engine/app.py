#!/usr/bin/env python3
"""
NBA Prediction Engine v3.1 - Modern GUI Application

Features:
- Run today's predictions with one click
- Excel tracking with overwrite-by-day
- Confidence % and Bucket display
- Winrate dashboard by confidence level
- Modern, clean UI design

NOTE: This engine ONLY supports today's slate. No historical modes.

TRACKING FILE LOCATION:
The tracking workbook is stored in a persistent location:
  Windows: %APPDATA%\\NBA_Engine\\tracking\\NBA_Engine_Tracking.xlsx
  macOS:   ~/Library/Application Support/NBA_Engine/tracking/
  Linux:   ~/.local/share/NBA_Engine/tracking/
"""

import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from pathlib import Path

# Import paths module FIRST to set up persistent storage locations
# This must be imported before any module that uses tracking paths
import paths
from paths import (
    TRACKING_FILE_PATH,
    log_startup_diagnostics,
    get_tracking_path_message,
    is_frozen,
    DATA_ROOT,
)

# Import storage module for SQLite persistence with daily slate + locking
from storage import (
    init_db,
    upsert_daily_slate,
    upsert_game,
    upsert_daily_pick_if_unlocked,
    get_daily_picks,
    lock_all_started_games,
    compute_stats,
    get_db_path,
    generate_game_id,
    get_now_local,
    get_today_date_local,
    # Legacy compatibility
    insert_run,
    upsert_pick,
)

# Import services for score checking
from services import (
    fetch_scores_for_date,
    grade_picks_for_date,
)


# Try to use ttkbootstrap for modern styling, fallback to plain ttk
try:
    import ttkbootstrap as ttkb
    from ttkbootstrap.constants import *
    HAS_BOOTSTRAP = True
except ImportError:
    HAS_BOOTSTRAP = False


# Color scheme
COLORS = {
    'bg': '#f5f6fa',
    'card_bg': '#ffffff',
    'primary': '#4472C4',
    'success': '#27ae60',
    'warning': '#f39c12',
    'danger': '#e74c3c',
    'text': '#2c3e50',
    'text_muted': '#7f8c8d',
    'border': '#dcdde1',
    'high': '#27ae60',
    'medium': '#f39c12', 
    'low': '#e74c3c',
}


class NBAPredictor(tk.Tk):
    """Main application window for NBA Prediction Engine."""
    
    def __init__(self):
        super().__init__()
        
        self.title("NBA Prediction Engine v3.1")
        self.geometry("1400x900")
        self.minsize(1200, 800)
        
        # Set background color
        self.configure(bg=COLORS['bg'])
        
        # Data storage
        self.scores = []
        self.injuries = []
        self.team_stats = {}
        
        # Roster tab caches
        self.roster_cache = {}  # team_abbrev -> list[RosterPlayer]
        self.player_stats_cache = None  # dict[team] -> list[PlayerImpact]
        self.todays_games_cache = None  # from get_todays_games()
        self.injury_rows_cache = []  # parsed InjuryRow list
        self.roster_loading = False
        
        # Projections tab caches
        self.team_stats_cache = None  # dict[team] -> TeamStrength
        self.projections_loading = False
        self.proj_last_updated = None
        
        # Configure styles
        self.setup_styles()
        
        # Create UI
        self.create_widgets()
        
        # Initialize database
        init_db()
        
        # Load initial winrate stats from database
        self.after(250, self.refresh_stats_from_db)
        
        # Run dependency smoke check
        self.after(500, self._dependency_smoke_check)
    
    def _dependency_smoke_check(self):
        """Check that critical dependencies are available (especially for PyInstaller builds)."""
        try:
            from nba_api.live.nba.endpoints import scoreboard  # noqa
            self.log("Dependency check: nba_api.live OK")
        except Exception as e:
            self.log(f"Dependency check FAILED: nba_api.live not available ({type(e).__name__}: {e})")
            messagebox.showwarning(
                "Dependency missing",
                "nba_api.live is missing. Roster/Projections may not load.\n\n"
                "If running from EXE, rebuild with PyInstaller hidden imports for nba_api.live.\n\n"
                f"Error: {type(e).__name__}: {e}"
            )
    
    def setup_styles(self):
        """Configure ttk styles for modern appearance."""
        style = ttk.Style()
        
        # Try to use a cleaner theme
        available_themes = style.theme_names()
        for theme in ['clam', 'alt', 'default']:
            if theme in available_themes:
                style.theme_use(theme)
                break
        
        # Configure general frame background
        style.configure('TFrame', background=COLORS['bg'])
        style.configure('Card.TFrame', background=COLORS['card_bg'])
        
        # Header style
        style.configure(
            'Header.TLabel',
            font=('Segoe UI', 20, 'bold'),
            foreground=COLORS['primary'],
            background=COLORS['bg'],
        )
        
        # Subheader style
        style.configure(
            'Subheader.TLabel',
            font=('Segoe UI', 14, 'bold'),
            foreground=COLORS['text'],
            background=COLORS['card_bg'],
        )
        
        # Normal label
        style.configure(
            'TLabel',
            font=('Segoe UI', 10),
            background=COLORS['bg'],
        )
        
        # Card label
        style.configure(
            'Card.TLabel',
            font=('Segoe UI', 10),
            background=COLORS['card_bg'],
        )
        
        # Status label
        style.configure(
            'Status.TLabel',
            font=('Segoe UI', 10),
            foreground=COLORS['text_muted'],
            background=COLORS['bg'],
        )
        
        # Large stat number
        style.configure(
            'StatNumber.TLabel',
            font=('Segoe UI', 24, 'bold'),
            background=COLORS['card_bg'],
        )
        
        # Stat label
        style.configure(
            'StatLabel.TLabel',
            font=('Segoe UI', 9),
            foreground=COLORS['text_muted'],
            background=COLORS['card_bg'],
        )
        
        # Primary button
        style.configure(
            'Primary.TButton',
            font=('Segoe UI', 11, 'bold'),
            padding=(20, 12),
        )
        
        # Secondary button
        style.configure(
            'Secondary.TButton',
            font=('Segoe UI', 10),
            padding=(15, 8),
        )
        
        # Confidence bucket styles
        style.configure(
            'High.TLabel',
            font=('Segoe UI', 10, 'bold'),
            foreground='#ffffff',
            background=COLORS['high'],
        )
        style.configure(
            'Medium.TLabel',
            font=('Segoe UI', 10, 'bold'),
            foreground='#ffffff',
            background=COLORS['medium'],
        )
        style.configure(
            'Low.TLabel',
            font=('Segoe UI', 10, 'bold'),
            foreground='#ffffff',
            background=COLORS['low'],
        )
        
        # Treeview styling
        style.configure(
            'Treeview',
            font=('Segoe UI', 10),
            rowheight=28,
            background=COLORS['card_bg'],
            fieldbackground=COLORS['card_bg'],
        )
        style.configure(
            'Treeview.Heading',
            font=('Segoe UI', 10, 'bold'),
            background=COLORS['primary'],
            foreground='white',
        )
        style.map('Treeview',
            background=[('selected', COLORS['primary'])],
            foreground=[('selected', 'white')]
        )
    
    def create_widgets(self):
        """Create all UI widgets with modern layout."""
        # Main container with padding
        self.main_frame = ttk.Frame(self, padding=20, style='TFrame')
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Top bar
        self.create_top_bar()
        
        # Content area (two columns)
        content_frame = ttk.Frame(self.main_frame, style='TFrame')
        content_frame.pack(fill=tk.BOTH, expand=True, pady=(15, 0))
        
        # Left column - Summary cards
        self.create_left_column(content_frame)
        
        # Right column - Tabs
        self.create_right_column(content_frame)
    
    def create_top_bar(self):
        """Create the top bar with title and actions."""
        top_frame = ttk.Frame(self.main_frame, style='TFrame')
        top_frame.pack(fill=tk.X)
        
        # Left side - Title and date
        left_frame = ttk.Frame(top_frame, style='TFrame')
        left_frame.pack(side=tk.LEFT)
        
        ttk.Label(
            left_frame,
            text="NBA Prediction Engine",
            style='Header.TLabel'
        ).pack(side=tk.LEFT)
        
        # Version badge
        version_frame = tk.Frame(left_frame, bg=COLORS['primary'], padx=8, pady=2)
        version_frame.pack(side=tk.LEFT, padx=(10, 0))
        tk.Label(
            version_frame,
            text="v3.1",
            font=('Segoe UI', 9, 'bold'),
            fg='white',
            bg=COLORS['primary']
        ).pack()
        
        # Date
        self.date_var = tk.StringVar(value=datetime.now().strftime("%A, %B %d, %Y"))
        ttk.Label(
            left_frame,
            textvariable=self.date_var,
            style='Status.TLabel'
        ).pack(side=tk.LEFT, padx=(20, 0))
        
        # Right side - Actions
        right_frame = ttk.Frame(top_frame, style='TFrame')
        right_frame.pack(side=tk.RIGHT)
        
        # Auto-poll toggle
        self.auto_poll_var = tk.BooleanVar(value=False)
        self.auto_poll_check = ttk.Checkbutton(
            right_frame,
            text="Auto-check (30m)",
            variable=self.auto_poll_var,
            command=self.toggle_auto_poll,
            style='TCheckbutton'
        )
        self.auto_poll_check.pack(side=tk.LEFT, padx=(0, 10))
        self.auto_poll_job = None
        
        # Status
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(
            right_frame,
            textvariable=self.status_var,
            style='Status.TLabel'
        ).pack(side=tk.LEFT, padx=(0, 15))
        
        # Buttons
        self.open_excel_button = ttk.Button(
            right_frame,
            text="📂 Open Tracking",
            command=self.open_tracking_file,
            style='Secondary.TButton'
        )
        self.open_excel_button.pack(side=tk.LEFT, padx=5)
        
        self.check_scores_button = ttk.Button(
            right_frame,
            text="📊 Check Scores",
            command=self.check_scores,
            style='Secondary.TButton'
        )
        self.check_scores_button.pack(side=tk.LEFT, padx=5)
        
        self.refresh_button = ttk.Button(
            right_frame,
            text="🔄 Refresh Stats",
            command=self.refresh_stats_from_db,
            style='Secondary.TButton'
        )
        self.refresh_button.pack(side=tk.LEFT, padx=5)
        
        self.run_button = ttk.Button(
            right_frame,
            text="▶ Run Predictions",
            command=self.start_prediction_run,
            style='Primary.TButton'
        )
        self.run_button.pack(side=tk.LEFT, padx=(5, 0))
    
    def create_left_column(self, parent):
        """Create the left column with summary cards."""
        left_frame = ttk.Frame(parent, style='TFrame', width=280)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 15))
        left_frame.pack_propagate(False)
        
        # Today's Games Card
        self.create_card(
            left_frame,
            "Today's Games",
            self.create_games_summary
        )
        
        # Confidence Distribution Card
        self.create_card(
            left_frame,
            "Confidence Distribution",
            self.create_confidence_summary
        )
        
        # Performance Card
        self.create_card(
            left_frame,
            "Win Rate by Bucket",
            self.create_performance_summary
        )
    
    def create_card(self, parent, title, content_func):
        """Create a styled card with title and content."""
        # Card container
        card = tk.Frame(parent, bg=COLORS['card_bg'], padx=15, pady=15)
        card.pack(fill=tk.X, pady=(0, 10))
        
        # Add subtle border effect
        card.configure(highlightbackground=COLORS['border'], highlightthickness=1)
        
        # Title
        tk.Label(
            card,
            text=title,
            font=('Segoe UI', 12, 'bold'),
            fg=COLORS['text'],
            bg=COLORS['card_bg'],
            anchor='w'
        ).pack(fill=tk.X, pady=(0, 10))
        
        # Content
        content_frame = tk.Frame(card, bg=COLORS['card_bg'])
        content_frame.pack(fill=tk.X)
        content_func(content_frame)
        
        return card
    
    def create_games_summary(self, parent):
        """Create today's games summary content."""
        self.games_count_var = tk.StringVar(value="--")
        
        tk.Label(
            parent,
            textvariable=self.games_count_var,
            font=('Segoe UI', 36, 'bold'),
            fg=COLORS['primary'],
            bg=COLORS['card_bg']
        ).pack()
        
        tk.Label(
            parent,
            text="games scheduled",
            font=('Segoe UI', 10),
            fg=COLORS['text_muted'],
            bg=COLORS['card_bg']
        ).pack()
    
    def create_confidence_summary(self, parent):
        """Create confidence distribution content."""
        # HIGH
        high_frame = tk.Frame(parent, bg=COLORS['card_bg'])
        high_frame.pack(fill=tk.X, pady=3)
        
        high_badge = tk.Frame(high_frame, bg=COLORS['high'], padx=8, pady=2)
        high_badge.pack(side=tk.LEFT)
        tk.Label(high_badge, text="HIGH", font=('Segoe UI', 9, 'bold'), 
                fg='white', bg=COLORS['high']).pack()
        
        self.high_count_var = tk.StringVar(value="0")
        tk.Label(high_frame, textvariable=self.high_count_var, 
                font=('Segoe UI', 11, 'bold'), fg=COLORS['text'],
                bg=COLORS['card_bg']).pack(side=tk.RIGHT)
        
        # MEDIUM
        med_frame = tk.Frame(parent, bg=COLORS['card_bg'])
        med_frame.pack(fill=tk.X, pady=3)
        
        med_badge = tk.Frame(med_frame, bg=COLORS['medium'], padx=8, pady=2)
        med_badge.pack(side=tk.LEFT)
        tk.Label(med_badge, text="MED", font=('Segoe UI', 9, 'bold'),
                fg='white', bg=COLORS['medium']).pack()
        
        self.med_count_var = tk.StringVar(value="0")
        tk.Label(med_frame, textvariable=self.med_count_var,
                font=('Segoe UI', 11, 'bold'), fg=COLORS['text'],
                bg=COLORS['card_bg']).pack(side=tk.RIGHT)
        
        # LOW
        low_frame = tk.Frame(parent, bg=COLORS['card_bg'])
        low_frame.pack(fill=tk.X, pady=3)
        
        low_badge = tk.Frame(low_frame, bg=COLORS['low'], padx=8, pady=2)
        low_badge.pack(side=tk.LEFT)
        tk.Label(low_badge, text="LOW", font=('Segoe UI', 9, 'bold'),
                fg='white', bg=COLORS['low']).pack()
        
        self.low_count_var = tk.StringVar(value="0")
        tk.Label(low_frame, textvariable=self.low_count_var,
                font=('Segoe UI', 11, 'bold'), fg=COLORS['text'],
                bg=COLORS['card_bg']).pack(side=tk.RIGHT)
    
    def create_performance_summary(self, parent):
        """Create performance summary content."""
        # Overall
        overall_frame = tk.Frame(parent, bg=COLORS['card_bg'])
        overall_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(overall_frame, text="Overall", font=('Segoe UI', 10),
                fg=COLORS['text'], bg=COLORS['card_bg']).pack(side=tk.LEFT)
        
        self.overall_winrate_var = tk.StringVar(value="--")
        self.overall_record_var = tk.StringVar(value="(0-0)")
        
        record_frame = tk.Frame(overall_frame, bg=COLORS['card_bg'])
        record_frame.pack(side=tk.RIGHT)
        tk.Label(record_frame, textvariable=self.overall_winrate_var,
                font=('Segoe UI', 11, 'bold'), fg=COLORS['text'],
                bg=COLORS['card_bg']).pack(side=tk.LEFT)
        tk.Label(record_frame, textvariable=self.overall_record_var,
                font=('Segoe UI', 9), fg=COLORS['text_muted'],
                bg=COLORS['card_bg']).pack(side=tk.LEFT, padx=(5, 0))
        
        # Separator
        ttk.Separator(parent, orient='horizontal').pack(fill=tk.X, pady=8)
        
        # HIGH
        self._create_winrate_row(parent, "HIGH", COLORS['high'], 
                                 'high_winrate_var', 'high_record_var')
        
        # MEDIUM
        self._create_winrate_row(parent, "MED", COLORS['medium'],
                                 'med_winrate_var', 'med_record_var')
        
        # LOW
        self._create_winrate_row(parent, "LOW", COLORS['low'],
                                 'low_winrate_var', 'low_record_var')
        
        # Pending
        pending_frame = tk.Frame(parent, bg=COLORS['card_bg'])
        pending_frame.pack(fill=tk.X, pady=(8, 0))
        
        tk.Label(pending_frame, text="Pending", font=('Segoe UI', 9),
                fg=COLORS['text_muted'], bg=COLORS['card_bg']).pack(side=tk.LEFT)
        
        self.pending_var = tk.StringVar(value="0")
        tk.Label(pending_frame, textvariable=self.pending_var,
                font=('Segoe UI', 9), fg=COLORS['text_muted'],
                bg=COLORS['card_bg']).pack(side=tk.RIGHT)
    
    def _create_winrate_row(self, parent, label, color, winrate_var_name, record_var_name):
        """Create a winrate row with colored label."""
        frame = tk.Frame(parent, bg=COLORS['card_bg'])
        frame.pack(fill=tk.X, pady=2)
        
        tk.Label(frame, text=label, font=('Segoe UI', 9, 'bold'),
                fg=color, bg=COLORS['card_bg']).pack(side=tk.LEFT)
        
        setattr(self, winrate_var_name, tk.StringVar(value="--"))
        setattr(self, record_var_name, tk.StringVar(value="(0-0)"))
        
        record_frame = tk.Frame(frame, bg=COLORS['card_bg'])
        record_frame.pack(side=tk.RIGHT)
        tk.Label(record_frame, textvariable=getattr(self, winrate_var_name),
                font=('Segoe UI', 10, 'bold'), fg=COLORS['text'],
                bg=COLORS['card_bg']).pack(side=tk.LEFT)
        tk.Label(record_frame, textvariable=getattr(self, record_var_name),
                font=('Segoe UI', 9), fg=COLORS['text_muted'],
                bg=COLORS['card_bg']).pack(side=tk.LEFT, padx=(5, 0))
    
    def create_right_column(self, parent):
        """Create the right column with tabs."""
        right_frame = ttk.Frame(parent, style='TFrame')
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Notebook for tabs
        self.notebook = ttk.Notebook(right_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Predictions tab
        self.predictions_frame = ttk.Frame(self.notebook, style='TFrame')
        self.notebook.add(self.predictions_frame, text="  📊 Today's Predictions  ")
        self.create_predictions_tree()
        
        # Factors tab
        self.factors_frame = ttk.Frame(self.notebook, style='TFrame')
        self.notebook.add(self.factors_frame, text="  📈 Factor Breakdown  ")
        self.create_factors_view()
        
        # Injuries tab
        self.injuries_frame = ttk.Frame(self.notebook, style='TFrame')
        self.notebook.add(self.injuries_frame, text="  🏥 Injuries  ")
        self.create_injuries_tree()
        
        # Roster tab
        self.roster_frame = ttk.Frame(self.notebook, style='TFrame')
        self.notebook.add(self.roster_frame, text="  🏀 Roster  ")
        self.create_roster_view()
        
        # Projections tab
        self.projections_frame = ttk.Frame(self.notebook, style='TFrame')
        self.notebook.add(self.projections_frame, text="  📈 Projections  ")
        self.create_projections_view()
        
        # Log tab
        self.log_frame = ttk.Frame(self.notebook, style='TFrame')
        self.notebook.add(self.log_frame, text="  📝 Log  ")
        self.create_log_view()
    
    def create_predictions_tree(self):
        """Create the predictions treeview with confidence, totals, and lock status display."""
        # Container with card-like appearance
        container = tk.Frame(self.predictions_frame, bg=COLORS['card_bg'])
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        columns = (
            'matchup', 'pick', 'side', 'conf_pct', 'bucket', 'locked',
            'pred_score', 'total', 'total_range', 'edge', 'margin'
        )
        
        self.pred_tree = ttk.Treeview(
            container,
            columns=columns,
            show='headings',
            selectmode='browse'
        )
        
        # Configure columns with better widths
        col_configs = [
            ('matchup', 'Matchup', 110),
            ('pick', 'Pick', 55),
            ('side', 'Side', 55),
            ('conf_pct', 'Conf %', 65),
            ('bucket', 'Bucket', 65),
            ('locked', 'Locked', 55),
            ('pred_score', 'Pred Score', 95),
            ('total', 'Total', 50),
            ('total_range', 'Range', 75),
            ('edge', 'Edge', 55),
            ('margin', 'Margin', 60),
        ]
        
        for col_id, heading, width in col_configs:
            self.pred_tree.heading(col_id, text=heading)
            self.pred_tree.column(col_id, width=width, anchor='center')
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.pred_tree.yview)
        self.pred_tree.configure(yscrollcommand=scrollbar.set)
        
        self.pred_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind selection
        self.pred_tree.bind('<<TreeviewSelect>>', self.on_prediction_selected)
        
        # Configure row tags for confidence buckets and lock status
        self.pred_tree.tag_configure('high', background='#d4edda')
        self.pred_tree.tag_configure('medium', background='#fff3cd')
        self.pred_tree.tag_configure('low', background='#f8d7da')
        self.pred_tree.tag_configure('locked', foreground='#666666')
    
    def create_factors_view(self):
        """Create the factor breakdown view with confidence summary."""
        # Container
        container = tk.Frame(self.factors_frame, bg=COLORS['card_bg'])
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Top bar with game selector and confidence display
        top_bar = tk.Frame(container, bg=COLORS['card_bg'])
        top_bar.pack(fill=tk.X, pady=(10, 15), padx=10)
        
        # Game selector
        selector_frame = tk.Frame(top_bar, bg=COLORS['card_bg'])
        selector_frame.pack(side=tk.LEFT)
        
        tk.Label(selector_frame, text="Select Game:", font=('Segoe UI', 10),
                bg=COLORS['card_bg'], fg=COLORS['text']).pack(side=tk.LEFT, padx=(0, 8))
        
        self.game_selector_var = tk.StringVar()
        self.game_selector = ttk.Combobox(
            selector_frame,
            textvariable=self.game_selector_var,
            state='readonly',
            width=25,
            font=('Segoe UI', 10)
        )
        self.game_selector.pack(side=tk.LEFT)
        self.game_selector.bind('<<ComboboxSelected>>', self.on_game_selected)
        
        # Confidence display (right side)
        conf_frame = tk.Frame(top_bar, bg=COLORS['card_bg'])
        conf_frame.pack(side=tk.RIGHT)
        
        tk.Label(conf_frame, text="Confidence:", font=('Segoe UI', 10),
                bg=COLORS['card_bg'], fg=COLORS['text_muted']).pack(side=tk.LEFT)
        
        self.factor_conf_var = tk.StringVar(value="--")
        tk.Label(conf_frame, textvariable=self.factor_conf_var,
                font=('Segoe UI', 12, 'bold'), bg=COLORS['card_bg'],
                fg=COLORS['primary']).pack(side=tk.LEFT, padx=(5, 10))
        
        self.factor_bucket_frame = tk.Frame(conf_frame, bg=COLORS['card_bg'])
        self.factor_bucket_frame.pack(side=tk.LEFT)
        
        self.factor_bucket_label = tk.Label(
            self.factor_bucket_frame, text="--", 
            font=('Segoe UI', 9, 'bold'), fg='white', bg=COLORS['text_muted'],
            padx=8, pady=2
        )
        self.factor_bucket_label.pack()
        
        # Totals summary bar
        totals_bar = tk.Frame(container, bg=COLORS['bg'], padx=10, pady=8)
        totals_bar.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        # Predicted score
        score_frame = tk.Frame(totals_bar, bg=COLORS['bg'])
        score_frame.pack(side=tk.LEFT, padx=(0, 20))
        
        tk.Label(score_frame, text="Pred Score:", font=('Segoe UI', 9),
                bg=COLORS['bg'], fg=COLORS['text_muted']).pack(side=tk.LEFT)
        self.factor_pred_score_var = tk.StringVar(value="-- - --")
        tk.Label(score_frame, textvariable=self.factor_pred_score_var,
                font=('Segoe UI', 10, 'bold'), bg=COLORS['bg'],
                fg=COLORS['text']).pack(side=tk.LEFT, padx=(5, 0))
        
        # Total with range
        total_frame = tk.Frame(totals_bar, bg=COLORS['bg'])
        total_frame.pack(side=tk.LEFT, padx=(0, 20))
        
        tk.Label(total_frame, text="Total:", font=('Segoe UI', 9),
                bg=COLORS['bg'], fg=COLORS['text_muted']).pack(side=tk.LEFT)
        self.factor_total_var = tk.StringVar(value="--")
        tk.Label(total_frame, textvariable=self.factor_total_var,
                font=('Segoe UI', 10, 'bold'), bg=COLORS['bg'],
                fg=COLORS['text']).pack(side=tk.LEFT, padx=(5, 0))
        
        # Expected possessions
        poss_frame = tk.Frame(totals_bar, bg=COLORS['bg'])
        poss_frame.pack(side=tk.LEFT, padx=(0, 20))
        
        tk.Label(poss_frame, text="Exp Poss:", font=('Segoe UI', 9),
                bg=COLORS['bg'], fg=COLORS['text_muted']).pack(side=tk.LEFT)
        self.factor_poss_var = tk.StringVar(value="--")
        tk.Label(poss_frame, textvariable=self.factor_poss_var,
                font=('Segoe UI', 10), bg=COLORS['bg'],
                fg=COLORS['text']).pack(side=tk.LEFT, padx=(5, 0))
        
        # PPPs
        ppp_frame = tk.Frame(totals_bar, bg=COLORS['bg'])
        ppp_frame.pack(side=tk.LEFT)
        
        tk.Label(ppp_frame, text="PPP:", font=('Segoe UI', 9),
                bg=COLORS['bg'], fg=COLORS['text_muted']).pack(side=tk.LEFT)
        self.factor_ppp_var = tk.StringVar(value="-- / --")
        tk.Label(ppp_frame, textvariable=self.factor_ppp_var,
                font=('Segoe UI', 10), bg=COLORS['bg'],
                fg=COLORS['text']).pack(side=tk.LEFT, padx=(5, 0))
        
        # Factors tree
        tree_frame = tk.Frame(container, bg=COLORS['card_bg'])
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        columns = ('factor', 'weight', 'signed_value', 'contribution', 'inputs')
        
        self.factors_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            selectmode='browse'
        )
        
        self.factors_tree.heading('factor', text='Factor')
        self.factors_tree.heading('weight', text='Weight')
        self.factors_tree.heading('signed_value', text='Value')
        self.factors_tree.heading('contribution', text='Contrib')
        self.factors_tree.heading('inputs', text='Inputs Used')
        
        self.factors_tree.column('factor', width=180)
        self.factors_tree.column('weight', width=70, anchor='center')
        self.factors_tree.column('signed_value', width=90, anchor='center')
        self.factors_tree.column('contribution', width=90, anchor='center')
        self.factors_tree.column('inputs', width=350)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.factors_tree.yview)
        self.factors_tree.configure(yscrollcommand=scrollbar.set)
        
        self.factors_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Color tags
        self.factors_tree.tag_configure('positive', foreground=COLORS['success'])
        self.factors_tree.tag_configure('negative', foreground=COLORS['danger'])
        self.factors_tree.tag_configure('neutral', foreground=COLORS['text_muted'])
    
    def create_injuries_tree(self):
        """Create the injuries treeview."""
        container = tk.Frame(self.injuries_frame, bg=COLORS['card_bg'])
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        columns = ('team', 'player', 'status', 'reason')
        
        self.injuries_tree = ttk.Treeview(
            container,
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
        
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.injuries_tree.yview)
        self.injuries_tree.configure(yscrollcommand=scrollbar.set)
        
        self.injuries_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Status color tags
        self.injuries_tree.tag_configure('out', background='#f8d7da', foreground='#721c24')
        self.injuries_tree.tag_configure('doubtful', background='#fff3cd', foreground='#856404')
        self.injuries_tree.tag_configure('questionable', background='#ffeeba', foreground='#856404')
        self.injuries_tree.tag_configure('probable', background='#d4edda', foreground='#155724')
    
    def create_log_view(self):
        """Create the log text view."""
        container = tk.Frame(self.log_frame, bg=COLORS['card_bg'])
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_text = tk.Text(
            container,
            wrap=tk.WORD,
            font=('Consolas', 10),
            bg=COLORS['card_bg'],
            fg=COLORS['text'],
            state=tk.DISABLED,
            padx=10,
            pady=10
        )
        
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def create_roster_view(self):
        """Create the roster tab with team selector and player table."""
        from ingest.roster import get_all_team_abbrevs
        
        # Container
        container = tk.Frame(self.roster_frame, bg=COLORS['card_bg'])
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Top controls bar
        controls_frame = tk.Frame(container, bg=COLORS['card_bg'])
        controls_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        # Team selector
        tk.Label(
            controls_frame,
            text="Team:",
            font=('Segoe UI', 10),
            bg=COLORS['card_bg'],
            fg=COLORS['text']
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        self.roster_team_var = tk.StringVar()
        self.roster_team_combo = ttk.Combobox(
            controls_frame,
            textvariable=self.roster_team_var,
            state='readonly',
            width=8,
            values=get_all_team_abbrevs(),
            font=('Segoe UI', 10)
        )
        self.roster_team_combo.pack(side=tk.LEFT, padx=(0, 15))
        self.roster_team_combo.bind('<<ComboboxSelected>>', self._on_roster_team_selected)
        
        # Tonight only checkbox
        self.roster_tonight_only_var = tk.BooleanVar(value=False)
        self.roster_tonight_check = ttk.Checkbutton(
            controls_frame,
            text="Only teams playing tonight",
            variable=self.roster_tonight_only_var,
            command=self._update_roster_team_filter
        )
        self.roster_tonight_check.pack(side=tk.LEFT, padx=(0, 15))
        
        # Refresh button
        self.roster_refresh_btn = ttk.Button(
            controls_frame,
            text="🔄 Refresh",
            command=lambda: self.refresh_roster_tab(),
            style='Secondary.TButton'
        )
        self.roster_refresh_btn.pack(side=tk.LEFT, padx=(0, 15))
        
        # Tonight info label
        self.roster_tonight_var = tk.StringVar(value="Select a team")
        tk.Label(
            controls_frame,
            textvariable=self.roster_tonight_var,
            font=('Segoe UI', 10, 'italic'),
            bg=COLORS['card_bg'],
            fg=COLORS['text_muted']
        ).pack(side=tk.LEFT)
        
        # Status filter frame
        filter_frame = tk.Frame(container, bg=COLORS['card_bg'])
        filter_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        # Hide OUT checkbox
        self.roster_hide_out_var = tk.BooleanVar(value=False)
        self.roster_hide_out_check = ttk.Checkbutton(
            filter_frame,
            text="Hide OUT/Doubtful",
            variable=self.roster_hide_out_var,
            command=self._apply_roster_filters
        )
        self.roster_hide_out_check.pack(side=tk.LEFT, padx=(0, 15))
        
        # Search box
        tk.Label(
            filter_frame,
            text="Search:",
            font=('Segoe UI', 9),
            bg=COLORS['card_bg'],
            fg=COLORS['text_muted']
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        self.roster_search_var = tk.StringVar()
        self.roster_search_var.trace_add('write', lambda *_: self._apply_roster_filters())
        self.roster_search_entry = ttk.Entry(
            filter_frame,
            textvariable=self.roster_search_var,
            width=20,
            font=('Segoe UI', 9)
        )
        self.roster_search_entry.pack(side=tk.LEFT)
        
        # Roster treeview
        tree_frame = tk.Frame(container, bg=COLORS['card_bg'])
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        columns = (
            'name', 'pos', 'role', 'status', 'tonight',
            'mpg', 'ppg', 'rpg', 'apg', 'fg_pct', 'fg3_pct', 'usg'
        )
        
        self.roster_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            selectmode='browse'
        )
        
        # Configure columns
        col_configs = [
            ('name', 'Player', 150, 'w'),
            ('pos', 'Pos', 45, 'center'),
            ('role', 'Role', 70, 'center'),
            ('status', 'Status', 85, 'center'),
            ('tonight', 'Tonight', 60, 'center'),
            ('mpg', 'MPG', 50, 'center'),
            ('ppg', 'PPG', 50, 'center'),
            ('rpg', 'RPG', 45, 'center'),
            ('apg', 'APG', 45, 'center'),
            ('fg_pct', 'FG%', 50, 'center'),
            ('fg3_pct', '3P%', 50, 'center'),
            ('usg', 'USG%', 50, 'center'),
        ]
        
        for col_id, heading, width, anchor in col_configs:
            self.roster_tree.heading(col_id, text=heading)
            self.roster_tree.column(col_id, width=width, anchor=anchor)
        
        # Scrollbar
        roster_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.roster_tree.yview)
        self.roster_tree.configure(yscrollcommand=roster_scroll.set)
        
        self.roster_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        roster_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Configure row tags for highlighting
        self.roster_tree.tag_configure('star', foreground=COLORS['primary'], font=('Segoe UI', 9, 'bold'))
        self.roster_tree.tag_configure('key', foreground=COLORS['text'])
        self.roster_tree.tag_configure('out', foreground=COLORS['danger'])
        self.roster_tree.tag_configure('doubtful', foreground='#a55a00')
        self.roster_tree.tag_configure('questionable', foreground=COLORS['warning'])
        self.roster_tree.tag_configure('probable', foreground='#2d7a2d')
        
        # Player detail panel (bottom)
        detail_frame = tk.Frame(container, bg=COLORS['bg'], height=80)
        detail_frame.pack(fill=tk.X, padx=10, pady=5)
        detail_frame.pack_propagate(False)
        
        self.roster_detail_var = tk.StringVar(value="Select a player to see details")
        tk.Label(
            detail_frame,
            textvariable=self.roster_detail_var,
            font=('Segoe UI', 10),
            bg=COLORS['bg'],
            fg=COLORS['text'],
            justify=tk.LEFT,
            anchor='w'
        ).pack(fill=tk.X, padx=10, pady=10)
        
        # Bind selection
        self.roster_tree.bind('<<TreeviewSelect>>', self._on_roster_player_selected)
        
        # Store full roster data for filtering
        self._roster_full_data = []
    
    def _on_roster_team_selected(self, event=None):
        """Handle team selection in roster dropdown."""
        team = self.roster_team_var.get()
        if team:
            self.refresh_roster_tab(team)
    
    def _update_roster_team_filter(self):
        """Update team dropdown based on tonight-only filter."""
        from ingest.roster import get_all_team_abbrevs
        
        if self.roster_tonight_only_var.get():
            # Filter to only teams playing tonight
            teams_tonight = set()
            if self.todays_games_cache:
                for game in self.todays_games_cache:
                    teams_tonight.add(game.away_team)
                    teams_tonight.add(game.home_team)
            
            if teams_tonight:
                self.roster_team_combo['values'] = sorted(teams_tonight)
            else:
                self.roster_team_combo['values'] = get_all_team_abbrevs()
        else:
            self.roster_team_combo['values'] = get_all_team_abbrevs()
    
    def _apply_roster_filters(self):
        """Apply search and status filters to roster display."""
        # Clear current display
        for item in self.roster_tree.get_children():
            self.roster_tree.delete(item)
        
        search_term = self.roster_search_var.get().lower().strip()
        hide_out = self.roster_hide_out_var.get()
        
        for row_data in self._roster_full_data:
            # Apply search filter
            if search_term and search_term not in row_data['name'].lower():
                continue
            
            # Apply status filter
            status = row_data.get('status', '').upper()
            if hide_out and status in ('OUT', 'DOUBTFUL'):
                continue
            
            # Insert row
            values = (
                row_data['name'],
                row_data['pos'],
                row_data['role'],
                row_data['status'],
                row_data['tonight'],
                row_data['mpg'],
                row_data['ppg'],
                row_data['rpg'],
                row_data['apg'],
                row_data['fg_pct'],
                row_data['fg3_pct'],
                row_data['usg'],
            )
            self.roster_tree.insert('', tk.END, values=values, tags=row_data.get('tags', ()))
    
    def _on_roster_player_selected(self, event=None):
        """Handle player selection in roster tree."""
        selection = self.roster_tree.selection()
        if not selection:
            return
        
        item = self.roster_tree.item(selection[0])
        values = item['values']
        
        if values:
            name = values[0]
            pos = values[1]
            role = values[2]
            status = values[3]
            tonight = values[4]
            mpg = values[5]
            ppg = values[6]
            rpg = values[7]
            apg = values[8]
            fg = values[9]
            fg3 = values[10]
            usg = values[11]
            
            detail = f"{name} ({pos}) - {role}\n"
            detail += f"Status: {status}  |  Tonight: {tonight}\n"
            detail += f"Stats: {mpg} MPG, {ppg} PPG, {rpg} RPG, {apg} APG  |  Shooting: {fg} FG%, {fg3} 3P%  |  Usage: {usg}%"
            
            self.roster_detail_var.set(detail)
    
    def refresh_roster_tab(self, team_abbrev: str = None):
        """Refresh roster data for the selected team."""
        if self.roster_loading:
            return
        
        if team_abbrev is None:
            team_abbrev = self.roster_team_var.get()
        
        if not team_abbrev:
            return
        
        self.roster_loading = True
        self.roster_refresh_btn.config(state=tk.DISABLED)
        self.roster_tonight_var.set("Loading...")
        self.log(f"Loading roster for {team_abbrev}...")
        
        def _fetch_roster():
            try:
                from ingest.schedule import get_todays_games, get_current_season
                from ingest.roster import get_team_roster
                from ingest.player_stats import get_player_stats
                from ingest.injuries import find_latest_injury_pdf, download_injury_pdf, parse_injury_pdf
                from ingest.availability import normalize_player_name
                
                season = get_current_season()
                
                # ── Phase 1: roster + schedule + injuries (fast) ──────
                
                # Fetch roster FIRST — this is the critical data
                if team_abbrev not in self.roster_cache:
                    roster = get_team_roster(team_abbrev, season=season)
                    self.roster_cache[team_abbrev] = roster
                else:
                    roster = self.roster_cache[team_abbrev]
                
                if not roster:
                    ta = team_abbrev
                    self.after(0, lambda: self._roster_load_error(
                        f"No roster data returned for {ta}. "
                        "The NBA API may be temporarily unavailable — try again in a moment."
                    ))
                    return
                
                # Fetch today's games (cache it)
                if self.todays_games_cache is None:
                    try:
                        games, _, _ = get_todays_games()
                        self.todays_games_cache = games
                    except Exception:
                        self.todays_games_cache = []
                
                # Fetch injury report if needed
                if not self.injury_rows_cache:
                    try:
                        pdf_path = find_latest_injury_pdf()
                        if not pdf_path:
                            pdf_path = download_injury_pdf()
                        if pdf_path:
                            self.injury_rows_cache = parse_injury_pdf(pdf_path)
                    except Exception as e:
                        print(f"  Could not load injury report: {e}")
                
                # Build injury lookup
                injury_map = {}
                for row in self.injury_rows_cache:
                    key = (row.team, normalize_player_name(row.player))
                    status = row.get_canonical_status() if hasattr(row, 'get_canonical_status') else row.status
                    injury_map[key] = status
                
                # Determine if team plays tonight
                tonight_game = None
                if self.todays_games_cache:
                    for game in self.todays_games_cache:
                        if game.away_team == team_abbrev or game.home_team == team_abbrev:
                            tonight_game = game
                            break
                
                if tonight_game:
                    if tonight_game.home_team == team_abbrev:
                        tonight_summary = f"Tonight: vs {tonight_game.away_team} (Home)"
                    else:
                        tonight_summary = f"Tonight: @ {tonight_game.home_team} (Away)"
                else:
                    tonight_summary = "No game today"
                
                # Build stats map from whatever is already cached (may be empty)
                stats_map = {}
                need_stats_fetch = self.player_stats_cache is None
                if self.player_stats_cache:
                    for impact in self.player_stats_cache.get(team_abbrev, []):
                        stats_map[normalize_player_name(impact.player_name)] = impact
                
                # Render roster immediately with whatever data is available
                rows = self._build_roster_row_data(
                    roster, stats_map, injury_map, tonight_game, team_abbrev
                )
                ts = tonight_summary
                self.after(0, lambda: self._render_roster_rows(rows, ts))
                
                # ── Phase 2: player-stats enrichment (may be slow) ────
                if need_stats_fetch:
                    self.after(0, lambda: self.log("  Loading player stats for enrichment..."))
                    try:
                        self.player_stats_cache = get_player_stats(season=season)
                    except Exception as ps_err:
                        print(f"  ⚠ Player stats fetch failed: {ps_err}")
                        self.player_stats_cache = {}
                    
                    # Re-render with stats enrichment if we got data
                    new_impacts = self.player_stats_cache.get(team_abbrev, [])
                    if new_impacts:
                        stats_map = {}
                        for impact in new_impacts:
                            stats_map[normalize_player_name(impact.player_name)] = impact
                        rows = self._build_roster_row_data(
                            roster, stats_map, injury_map, tonight_game, team_abbrev
                        )
                        self.after(0, lambda: self._render_roster_rows(rows, ts))
                        self.after(0, lambda: self.log("  Player stats loaded — roster enriched."))
                    else:
                        ta = team_abbrev
                        self.after(0, lambda: self.log(
                            f"  ⚠ No player stats for {ta} — roster shown without stat enrichment."
                        ))
                
            except Exception as e:
                import traceback
                error_msg = f"Error loading roster: {e}"
                print(error_msg)
                traceback.print_exc()
                self.after(0, lambda: self._roster_load_error(error_msg))
        
        # Run in background thread
        thread = threading.Thread(target=_fetch_roster, daemon=True)
        thread.start()
    
    def _render_roster_rows(self, rows: list, tonight_summary: str):
        """Render roster rows in the treeview."""
        # Store full data for filtering
        self._roster_full_data = rows
        
        # Update tonight label
        self.roster_tonight_var.set(tonight_summary)
        
        # Update team filter (in case games cache was populated)
        self._update_roster_team_filter()
        
        # Apply filters and render
        self._apply_roster_filters()
        
        # Re-enable refresh button
        self.roster_refresh_btn.config(state=tk.NORMAL)
        self.roster_loading = False
        
        self.log(f"  Loaded {len(rows)} players for {self.roster_team_var.get()}")
    
    def _build_roster_row_data(self, roster, stats_map, injury_map, tonight_game, team_abbrev):
        """Build row data dicts for the roster treeview.

        Extracted so it can be called twice: once for an immediate render
        (possibly without stats) and again after stats arrive.
        """
        from ingest.availability import normalize_player_name

        rows = []
        for player in roster:
            name_norm = normalize_player_name(player.player_name)
            impact = stats_map.get(name_norm)

            # Get stats
            if impact:
                mpg = f"{impact.minutes_per_game:.1f}"
                ppg = f"{impact.points_per_game:.1f}"
                rpg = f"{impact.rebounds_per_game:.1f}"
                apg = f"{impact.assists_per_game:.1f}"
                fg_pct = f"{impact.fg_pct:.1f}"
                fg3_pct = f"{impact.fg3_pct:.1f}"
                usg = f"{impact.usage_pct:.1f}"

                if impact.is_star:
                    role = "Star"
                elif impact.is_key_player:
                    role = "Key"
                elif impact.minutes_per_game >= 15:
                    role = "Rotation"
                else:
                    role = "Bench"
            else:
                mpg = ppg = rpg = apg = fg_pct = fg3_pct = usg = "--"
                role = "Bench"

            # Determine status
            injury_key = (team_abbrev, name_norm)
            status = injury_map.get(injury_key, "Available")
            if status.upper() in ("AVAILABLE", ""):
                status = "Available"

            # Determine tonight
            if not tonight_game:
                tonight = "N/A"
            elif status.upper() in ("OUT", "DOUBTFUL"):
                tonight = "No"
            elif status.upper() == "QUESTIONABLE":
                tonight = "Maybe"
            else:
                tonight = "Yes"

            # Determine tags for highlighting
            tags = []
            status_upper = status.upper()
            if status_upper == "OUT":
                tags.append('out')
            elif status_upper == "DOUBTFUL":
                tags.append('doubtful')
            elif status_upper == "QUESTIONABLE":
                tags.append('questionable')
            elif status_upper == "PROBABLE":
                tags.append('probable')

            if impact:
                if impact.is_star:
                    tags.append('star')
                elif impact.is_key_player:
                    tags.append('key')

            row_data = {
                'name': player.player_name,
                'pos': player.position or "--",
                'role': role,
                'status': status,
                'tonight': tonight,
                'mpg': mpg,
                'ppg': ppg,
                'rpg': rpg,
                'apg': apg,
                'fg_pct': fg_pct,
                'fg3_pct': fg3_pct,
                'usg': usg,
                'tags': tuple(tags),
            }
            rows.append(row_data)

        # Sort: stars first, then by role, then by name
        role_order = {'Star': 0, 'Key': 1, 'Rotation': 2, 'Bench': 3}
        rows.sort(key=lambda r: (role_order.get(r['role'], 4), r['name']))
        return rows

    def _roster_load_error(self, error_msg: str):
        """Handle roster load error with popup notification."""
        self.roster_loading = False
        try:
            self.roster_tonight_var.set("Error loading roster")
            self.roster_refresh_btn.config(state=tk.NORMAL)
        except Exception:
            pass
        self.log(f"ERROR (Roster): {error_msg}")
        messagebox.showerror("Roster failed to load", error_msg)
    
    # =========================================================================
    # PROJECTIONS TAB
    # =========================================================================
    
    def create_projections_view(self):
        """Create the projections tab with controls and player table."""
        from services.projections import ProjectionMode
        
        # Container
        container = tk.Frame(self.projections_frame, bg=COLORS['card_bg'])
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Top controls bar
        controls_frame = tk.Frame(container, bg=COLORS['card_bg'])
        controls_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        # Date label (today)
        tk.Label(
            controls_frame,
            text="Date:",
            font=('Segoe UI', 10),
            bg=COLORS['card_bg'],
            fg=COLORS['text']
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        self.proj_date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.proj_date_entry = ttk.Entry(
            controls_frame,
            textvariable=self.proj_date_var,
            width=12,
            font=('Segoe UI', 10)
        )
        self.proj_date_entry.pack(side=tk.LEFT, padx=(0, 15))
        
        # View dropdown
        tk.Label(
            controls_frame,
            text="View:",
            font=('Segoe UI', 10),
            bg=COLORS['card_bg'],
            fg=COLORS['text']
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        self.proj_view_var = tk.StringVar(value="Slate")
        self.proj_view_combo = ttk.Combobox(
            controls_frame,
            textvariable=self.proj_view_var,
            state='readonly',
            width=8,
            values=["Slate", "Game"],
            font=('Segoe UI', 10)
        )
        self.proj_view_combo.pack(side=tk.LEFT, padx=(0, 15))
        self.proj_view_combo.bind('<<ComboboxSelected>>', self._on_proj_view_changed)
        
        # Game dropdown (only active in Game view)
        tk.Label(
            controls_frame,
            text="Game:",
            font=('Segoe UI', 10),
            bg=COLORS['card_bg'],
            fg=COLORS['text']
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        self.proj_game_var = tk.StringVar()
        self.proj_game_combo = ttk.Combobox(
            controls_frame,
            textvariable=self.proj_game_var,
            state='disabled',
            width=20,
            font=('Segoe UI', 10)
        )
        self.proj_game_combo.pack(side=tk.LEFT, padx=(0, 15))
        
        # Second row for mode and buttons
        controls_frame2 = tk.Frame(container, bg=COLORS['card_bg'])
        controls_frame2.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        # Mode dropdown
        tk.Label(
            controls_frame2,
            text="Mode:",
            font=('Segoe UI', 10),
            bg=COLORS['card_bg'],
            fg=COLORS['text']
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        self.proj_mode_var = tk.StringVar(value=ProjectionMode.BASELINE_PACE)
        self.proj_mode_combo = ttk.Combobox(
            controls_frame2,
            textvariable=self.proj_mode_var,
            state='readonly',
            width=22,
            values=[
                ProjectionMode.BASELINE,
                ProjectionMode.BASELINE_PACE,
                ProjectionMode.BASELINE_PACE_DEF,
            ],
            font=('Segoe UI', 10)
        )
        self.proj_mode_combo.pack(side=tk.LEFT, padx=(0, 15))
        
        # Minutes dropdown
        tk.Label(
            controls_frame2,
            text="Minutes:",
            font=('Segoe UI', 10),
            bg=COLORS['card_bg'],
            fg=COLORS['text']
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        self.proj_min_var = tk.StringVar(value="Season MPG")
        self.proj_min_combo = ttk.Combobox(
            controls_frame2,
            textvariable=self.proj_min_var,
            state='readonly',
            width=12,
            values=["Season MPG"],
            font=('Segoe UI', 10)
        )
        self.proj_min_combo.pack(side=tk.LEFT, padx=(0, 15))
        
        # Refresh button
        self.proj_refresh_btn = ttk.Button(
            controls_frame2,
            text="🔄 Refresh",
            command=self.refresh_projections,
            style='Secondary.TButton'
        )
        self.proj_refresh_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Check Injuries button
        self.proj_injuries_btn = ttk.Button(
            controls_frame2,
            text="🏥 Check Injuries",
            command=self._refresh_injuries_then_projections,
            style='Secondary.TButton'
        )
        self.proj_injuries_btn.pack(side=tk.LEFT, padx=(0, 15))
        
        # Last updated label
        self.proj_updated_var = tk.StringVar(value="Not loaded")
        tk.Label(
            controls_frame2,
            textvariable=self.proj_updated_var,
            font=('Segoe UI', 9, 'italic'),
            bg=COLORS['card_bg'],
            fg=COLORS['text_muted']
        ).pack(side=tk.LEFT)
        
        # Projections treeview
        tree_frame = tk.Frame(container, bg=COLORS['card_bg'])
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        columns = (
            'player', 'team', 'status', 'tonight',
            'proj_min', 'proj_pts', 'proj_reb', 'proj_ast', 'proj_3pm', 'uncertainty'
        )
        
        self.proj_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            selectmode='browse'
        )
        
        # Configure columns
        col_configs = [
            ('player', 'Player', 150, 'w'),
            ('team', 'Team', 50, 'center'),
            ('status', 'Status', 85, 'center'),
            ('tonight', 'Tonight', 60, 'center'),
            ('proj_min', 'ProjMin', 65, 'center'),
            ('proj_pts', 'ProjPTS', 65, 'center'),
            ('proj_reb', 'ProjREB', 65, 'center'),
            ('proj_ast', 'ProjAST', 65, 'center'),
            ('proj_3pm', 'Proj3PM', 65, 'center'),
            ('uncertainty', 'Uncertainty', 80, 'center'),
        ]
        
        for col_id, heading, width, anchor in col_configs:
            self.proj_tree.heading(col_id, text=heading, command=lambda c=col_id: self._sort_proj_tree(c))
            self.proj_tree.column(col_id, width=width, anchor=anchor)
        
        # Scrollbar
        proj_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.proj_tree.yview)
        self.proj_tree.configure(yscrollcommand=proj_scroll.set)
        
        self.proj_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        proj_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Configure row tags
        self.proj_tree.tag_configure('out', foreground=COLORS['danger'])
        self.proj_tree.tag_configure('doubtful', foreground='#a55a00')
        self.proj_tree.tag_configure('questionable', foreground=COLORS['warning'])
        self.proj_tree.tag_configure('star', foreground=COLORS['primary'], font=('Segoe UI', 9, 'bold'))
        
        # Player detail panel
        detail_frame = tk.Frame(container, bg=COLORS['bg'], height=80)
        detail_frame.pack(fill=tk.X, padx=10, pady=5)
        detail_frame.pack_propagate(False)
        
        self.proj_detail_var = tk.StringVar(value="Select a player to see projection details")
        tk.Label(
            detail_frame,
            textvariable=self.proj_detail_var,
            font=('Segoe UI', 10),
            bg=COLORS['bg'],
            fg=COLORS['text'],
            justify=tk.LEFT,
            anchor='w'
        ).pack(fill=tk.X, padx=10, pady=10)
        
        # Bind selection
        self.proj_tree.bind('<<TreeviewSelect>>', self._on_proj_player_selected)
        
        # Store game mapping
        self.proj_game_map = {}  # display string -> game object
        self.proj_sort_reverse = {}  # column -> bool for sort direction
        self._proj_full_data = []  # Full projection data for reference
    
    def _on_proj_view_changed(self, event=None):
        """Handle view change between Slate and Game."""
        view = self.proj_view_var.get()
        if view == "Game":
            self.proj_game_combo.config(state='readonly')
        else:
            self.proj_game_combo.config(state='disabled')
    
    def _sort_proj_tree(self, col):
        """Sort projections treeview by column."""
        # Get all items
        items = [(self.proj_tree.set(item, col), item) for item in self.proj_tree.get_children('')]
        
        # Determine sort direction
        reverse = self.proj_sort_reverse.get(col, False)
        self.proj_sort_reverse[col] = not reverse
        
        # Try numeric sort for numeric columns
        numeric_cols = ('proj_min', 'proj_pts', 'proj_reb', 'proj_ast', 'proj_3pm')
        if col in numeric_cols:
            try:
                items.sort(key=lambda x: float(x[0]) if x[0] else 0, reverse=reverse)
            except ValueError:
                items.sort(key=lambda x: x[0], reverse=reverse)
        else:
            items.sort(key=lambda x: x[0], reverse=reverse)
        
        # Rearrange items
        for index, (_, item) in enumerate(items):
            self.proj_tree.move(item, '', index)
    
    def _on_proj_player_selected(self, event=None):
        """Handle player selection in projections tree."""
        selection = self.proj_tree.selection()
        if not selection:
            return
        
        item = self.proj_tree.item(selection[0])
        values = item['values']
        
        if values:
            player = values[0]
            team = values[1]
            status = values[2]
            tonight = values[3]
            proj_min = values[4]
            proj_pts = values[5]
            proj_reb = values[6]
            proj_ast = values[7]
            proj_3pm = values[8]
            uncertainty = values[9]
            
            detail = f"{player} ({team}) - Status: {status}, Tonight: {tonight}\n"
            detail += f"Projections: {proj_min} MIN, {proj_pts} PTS, {proj_reb} REB, {proj_ast} AST, {proj_3pm} 3PM\n"
            detail += f"Uncertainty: {uncertainty}"
            
            self.proj_detail_var.set(detail)
    
    def _refresh_injuries_then_projections(self):
        """Refresh injuries cache then projections."""
        self.injury_rows_cache = []  # Clear cache to force refresh
        self.refresh_projections()
    
    def refresh_projections(self):
        """Refresh projections for the current view."""
        if self.projections_loading:
            return
        
        self.projections_loading = True
        self.proj_refresh_btn.config(state=tk.DISABLED)
        self.proj_injuries_btn.config(state=tk.DISABLED)
        self.proj_updated_var.set("Loading...")
        self.log("Loading projections...")
        
        def _fetch_projections():
            try:
                from ingest.schedule import get_todays_games, get_current_season
                from ingest.roster import get_team_roster
                from ingest.player_stats import get_player_stats
                from ingest.team_stats import get_comprehensive_team_stats
                from ingest.injuries import find_latest_injury_pdf, download_injury_pdf, parse_injury_pdf
                from ingest.availability import normalize_player_name
                from services.projections import project_slate, project_game
                
                season = get_current_season()
                view = self.proj_view_var.get()
                mode = self.proj_mode_var.get()
                
                # Fetch today's games
                games, _, _ = get_todays_games()
                self.todays_games_cache = games
                
                if not games:
                    self.after(0, lambda: self._proj_load_error("No games scheduled for today"))
                    return
                
                # Update game dropdown
                game_displays = []
                self.proj_game_map = {}
                for game in games:
                    display = f"{game.away_team} @ {game.home_team}"
                    game_displays.append(display)
                    self.proj_game_map[display] = game
                
                self.after(0, lambda: self._update_proj_game_dropdown(game_displays))
                
                # Ensure player stats cache exists (non-fatal if it fails)
                if self.player_stats_cache is None:
                    try:
                        self.player_stats_cache = get_player_stats(season=season)
                    except Exception as ps_err:
                        print(f"  ⚠ Player stats fetch failed: {ps_err}")
                        self.player_stats_cache = {}
                
                # Ensure team stats cache exists
                if self.team_stats_cache is None:
                    self.team_stats_cache = get_comprehensive_team_stats(season=season)
                
                # Fetch injury report if needed
                if not self.injury_rows_cache:
                    try:
                        pdf_path = find_latest_injury_pdf()
                        if not pdf_path:
                            pdf_path = download_injury_pdf()
                        if pdf_path:
                            self.injury_rows_cache = parse_injury_pdf(pdf_path)
                    except Exception as e:
                        print(f"  Could not load injury report: {e}")
                
                # Build injury map by team
                injuries_by_team = {}
                for row in self.injury_rows_cache:
                    if row.team not in injuries_by_team:
                        injuries_by_team[row.team] = {}
                    name_norm = normalize_player_name(row.player)
                    status = row.get_canonical_status() if hasattr(row, 'get_canonical_status') else row.status
                    injuries_by_team[row.team][name_norm] = status
                
                # Determine which teams we need rosters for
                if view == "Game":
                    game_display = self.proj_game_var.get()
                    if game_display and game_display in self.proj_game_map:
                        selected_game = self.proj_game_map[game_display]
                        teams_needed = [selected_game.home_team, selected_game.away_team]
                        target_games = [selected_game]
                    else:
                        # No game selected, use first game
                        teams_needed = [games[0].home_team, games[0].away_team]
                        target_games = [games[0]]
                else:
                    # Slate view - all teams
                    teams_needed = set()
                    for game in games:
                        teams_needed.add(game.home_team)
                        teams_needed.add(game.away_team)
                    teams_needed = list(teams_needed)
                    target_games = games
                
                # Fetch rosters for needed teams
                rosters_by_team = {}
                for team in teams_needed:
                    if team not in self.roster_cache:
                        roster = get_team_roster(team, season=season)
                        self.roster_cache[team] = roster
                    rosters_by_team[team] = self.roster_cache[team]
                
                # Run projections
                if view == "Game" and len(target_games) == 1:
                    game = target_games[0]
                    result = project_game(
                        game=game,
                        roster_home=rosters_by_team.get(game.home_team, []),
                        roster_away=rosters_by_team.get(game.away_team, []),
                        player_stats_by_team=self.player_stats_cache,
                        injuries_by_team=injuries_by_team,
                        team_stats=self.team_stats_cache,
                        mode=mode,
                    )
                    projections = result['combined']
                else:
                    projections = project_slate(
                        games=target_games,
                        rosters_by_team=rosters_by_team,
                        player_stats_by_team=self.player_stats_cache,
                        injuries_by_team=injuries_by_team,
                        team_stats=self.team_stats_cache,
                        mode=mode,
                        top_n=100,
                    )
                
                # Update UI from main thread
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.after(0, lambda: self._render_projections(projections, timestamp))
                
            except Exception as e:
                import traceback
                error_msg = f"Error loading projections: {e}"
                print(error_msg)
                traceback.print_exc()
                self.after(0, lambda: self._proj_load_error(error_msg))
        
        # Run in background thread
        thread = threading.Thread(target=_fetch_projections, daemon=True)
        thread.start()
    
    def _update_proj_game_dropdown(self, game_displays: list):
        """Update the game dropdown with available games."""
        self.proj_game_combo['values'] = game_displays
        if game_displays and not self.proj_game_var.get():
            self.proj_game_var.set(game_displays[0])
    
    def _render_projections(self, projections: list, timestamp: str):
        """Render projection rows in the treeview."""
        # Clear tree
        for item in self.proj_tree.get_children():
            self.proj_tree.delete(item)
        
        # Store full data
        self._proj_full_data = projections
        
        # Insert rows
        for proj in projections:
            # Determine tags
            tags = []
            status_upper = proj.status.upper()
            if status_upper == "OUT":
                tags.append('out')
            elif status_upper == "DOUBTFUL":
                tags.append('doubtful')
            elif status_upper == "QUESTIONABLE":
                tags.append('questionable')
            
            # Highlight high scorers
            if proj.proj_pts >= 20:
                tags.append('star')
            
            values = (
                proj.player_name,
                proj.team_abbrev,
                proj.status,
                proj.tonight,
                proj.proj_min,
                proj.proj_pts,
                proj.proj_reb,
                proj.proj_ast,
                proj.proj_3pm,
                proj.uncertainty,
            )
            self.proj_tree.insert('', tk.END, values=values, tags=tuple(tags))
        
        # Update timestamp
        self.proj_updated_var.set(f"Updated: {timestamp}")
        
        # Re-enable buttons
        self.proj_refresh_btn.config(state=tk.NORMAL)
        self.proj_injuries_btn.config(state=tk.NORMAL)
        self.projections_loading = False
        
        self.log(f"  Loaded {len(projections)} player projections")
    
    def _proj_load_error(self, error_msg: str):
        """Handle projection load error with popup notification."""
        self.projections_loading = False
        try:
            self.proj_updated_var.set("Error loading")
            self.proj_refresh_btn.config(state=tk.NORMAL)
            self.proj_injuries_btn.config(state=tk.NORMAL)
        except Exception:
            pass
        self.log(f"ERROR (Projections): {error_msg}")
        messagebox.showerror("Projections failed to load", error_msg)
    
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
                self.overall_record_var.set(f"({stats.wins}-{stats.losses})")
            else:
                self.overall_winrate_var.set("--")
                self.overall_record_var.set("(0-0)")
            
            # Update HIGH
            if stats.high_graded > 0:
                self.high_winrate_var.set(f"{stats.high_win_pct:.1f}%")
                self.high_record_var.set(f"({stats.high_wins}-{stats.high_losses})")
            else:
                self.high_winrate_var.set("--")
                self.high_record_var.set("(0-0)")
            
            # Update MEDIUM
            if stats.medium_graded > 0:
                self.med_winrate_var.set(f"{stats.medium_win_pct:.1f}%")
                self.med_record_var.set(f"({stats.medium_wins}-{stats.medium_losses})")
            else:
                self.med_winrate_var.set("--")
                self.med_record_var.set("(0-0)")
            
            # Update LOW
            if stats.low_graded > 0:
                self.low_winrate_var.set(f"{stats.low_win_pct:.1f}%")
                self.low_record_var.set(f"({stats.low_wins}-{stats.low_losses})")
            else:
                self.low_winrate_var.set("--")
                self.low_record_var.set("(0-0)")
            
            # Update pending
            self.pending_var.set(str(stats.pending_total))
            
            # Update summary sheet
            tracker.update_summary_sheet(stats)
            
            self.log(f"Winrates refreshed: {stats.wins}/{stats.total_graded} overall, {stats.pending_total} pending")
            
        except Exception as e:
            self.log(f"Error refreshing winrates: {e}")
    
    def refresh_stats_from_db(self):
        """Refresh winrate statistics from SQLite database."""
        try:
            stats = compute_stats()
            
            # Update overall
            if stats.total_graded > 0:
                self.overall_winrate_var.set(f"{stats.win_pct:.1f}%")
                self.overall_record_var.set(f"({stats.wins}-{stats.losses})")
            else:
                self.overall_winrate_var.set("--")
                self.overall_record_var.set("(0-0)")
            
            # Update HIGH
            if stats.high_graded > 0:
                self.high_winrate_var.set(f"{stats.high_win_pct:.1f}%")
                self.high_record_var.set(f"({stats.high_wins}-{stats.high_losses})")
            else:
                self.high_winrate_var.set("--")
                self.high_record_var.set("(0-0)")
            
            # Update MEDIUM
            if stats.med_graded > 0:
                self.med_winrate_var.set(f"{stats.med_win_pct:.1f}%")
                self.med_record_var.set(f"({stats.med_wins}-{stats.med_losses})")
            else:
                self.med_winrate_var.set("--")
                self.med_record_var.set("(0-0)")
            
            # Update LOW
            if stats.low_graded > 0:
                self.low_winrate_var.set(f"{stats.low_win_pct:.1f}%")
                self.low_record_var.set(f"({stats.low_wins}-{stats.low_losses})")
            else:
                self.low_winrate_var.set("--")
                self.low_record_var.set("(0-0)")
            
            # Update pending
            self.pending_var.set(str(stats.pending))
            
            self.log(f"Stats refreshed from DB: {stats.wins}/{stats.total_graded} overall, {stats.pending} pending")
            
        except Exception as e:
            self.log(f"Error refreshing stats from DB: {e}")
            # Fall back to Excel if DB fails
            self.refresh_winrates()
    
    def toggle_auto_poll(self):
        """Toggle automatic score polling every 30 minutes."""
        if self.auto_poll_var.get():
            # Enable auto-poll
            self.log("Auto-poll enabled - checking scores every 30 minutes")
            self.schedule_next_poll()
        else:
            # Disable auto-poll
            if self.auto_poll_job:
                self.after_cancel(self.auto_poll_job)
                self.auto_poll_job = None
            self.log("Auto-poll disabled")
    
    def schedule_next_poll(self):
        """Schedule the next automatic score check."""
        if not self.auto_poll_var.get():
            return
        
        # 30 minutes = 30 * 60 * 1000 milliseconds
        poll_interval_ms = 30 * 60 * 1000
        self.auto_poll_job = self.after(poll_interval_ms, self.auto_check_scores)
    
    def auto_check_scores(self):
        """Automatically check scores (called by timer)."""
        if not self.auto_poll_var.get():
            return
        
        self.log(f"\n[Auto-poll] Checking scores at {datetime.now().strftime('%H:%M:%S')}")
        
        def _auto_check():
            try:
                from datetime import timezone, timedelta
                
                now_utc = datetime.now(timezone.utc)
                et_offset = timedelta(hours=-5)
                now_et = now_utc + et_offset
                today = now_et.strftime("%Y-%m-%d")
                
                games_updated, picks_graded, picks_pending = grade_picks_for_date(today)
                
                self.log(f"  Graded: {picks_graded}, Pending: {picks_pending}")
                
                self.after(0, self.refresh_stats_from_db)
                
            except Exception as e:
                self.log(f"  [Auto-poll] Error: {e}")
            finally:
                # Schedule next poll
                self.after(0, self.schedule_next_poll)
        
        thread = threading.Thread(target=_auto_check, daemon=True)
        thread.start()
    
    def check_scores(self):
        """Check scores for today's games and grade picks."""
        self.check_scores_button.config(state=tk.DISABLED)
        self.status_var.set("Checking scores...")
        
        def _check():
            try:
                from datetime import datetime, timezone, timedelta
                
                # Get today's date in ET
                now_utc = datetime.now(timezone.utc)
                et_offset = timedelta(hours=-5)
                now_et = now_utc + et_offset
                today = now_et.strftime("%Y-%m-%d")
                
                self.log(f"\nChecking scores for {today}...")
                
                # Fetch scores and grade picks
                games_updated, picks_graded, picks_pending = grade_picks_for_date(today)
                
                self.log(f"  Games updated: {games_updated}")
                self.log(f"  Picks graded: {picks_graded}")
                self.log(f"  Picks pending: {picks_pending}")
                
                # Refresh stats display
                self.after(0, self.refresh_stats_from_db)
                self.after(0, lambda: self.status_var.set(f"Scores checked - {picks_graded} graded"))
                
            except Exception as e:
                self.log(f"Error checking scores: {e}")
                self.after(0, lambda: self.status_var.set(f"Error: {e}"))
            finally:
                self.after(0, lambda: self.check_scores_button.config(state=tk.NORMAL))
        
        thread = threading.Thread(target=_check, daemon=True)
        thread.start()
    
    def persist_predictions_to_db(self, scores: list, run_date: str, games_with_times: list = None) -> tuple:
        """
        Persist predictions to the SQLite database using daily slate with per-game locking.
        
        Games that have already started will not be overwritten (locked).
        Games that haven't started will be overwritten with the latest prediction.
        
        Args:
            scores: List of GameScore objects
            run_date: Date of the run (YYYY-MM-DD)
            games_with_times: Optional list of games with start times from API
        
        Returns:
            Tuple of (saved_count, locked_count)
        """
        now_local = get_now_local()
        
        # Create/update daily slate
        upsert_daily_slate(run_date, now_local, model_version="v3.2")
        
        # Build mapping of game times from API data if available
        game_times = {}
        if games_with_times:
            for g in games_with_times:
                key = f"{g.away_team}@{g.home_team}"
                game_times[key] = {
                    'game_id': g.game_id,
                    'start_time_utc': getattr(g, 'start_time_utc', None),
                }
        
        saved = 0
        locked = 0
        
        for score in scores:
            # Determine game_id - use API game_id if available, else generate
            matchup_key = f"{score.away_team}@{score.home_team}"
            api_info = game_times.get(matchup_key, {})
            
            game_id = api_info.get('game_id') or getattr(score, 'game_id', None)
            if not game_id:
                game_id = generate_game_id(run_date, score.away_team, score.home_team)
            
            start_time_utc = api_info.get('start_time_utc')
            
            # Upsert game record with start time
            upsert_game(
                game_id=game_id,
                game_date=run_date,
                away_team=score.away_team,
                home_team=score.home_team,
                start_time_utc=start_time_utc,
                status="scheduled",
            )
            
            # Determine pick side
            pick_side = "HOME" if score.predicted_winner == score.home_team else "AWAY"
            
            # Build pick data
            pick_data = {
                'matchup': f"{score.away_team} @ {score.home_team}",
                'pick_team': score.predicted_winner,
                'pick_side': pick_side,
                'conf_pct': score.confidence_pct_value,
                'bucket': score.confidence_bucket,
                'pred_away_score': score.display_away_points,
                'pred_home_score': score.display_home_points,
                'pred_total': score.predicted_total,
                'range_low': score.total_range_low,
                'range_high': score.total_range_high,
                'internal_edge': score.edge_score_total,
                'internal_margin': score.projected_margin_home,
            }
            
            # Try to save pick (will be blocked if game has started)
            was_saved, is_locked = upsert_daily_pick_if_unlocked(
                run_date, game_id, pick_data, now_local
            )
            
            if was_saved:
                saved += 1
            if is_locked:
                locked += 1
        
        return saved, locked
    
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
            
            # Update games count
            self.after(0, lambda: self.games_count_var.set(str(len(games))))
            
            # Get team stats
            self.log("\n[3/7] Fetching team statistics...")
            season = get_current_season()
            team_strength = get_comprehensive_team_stats(season)
            self.team_stats = team_strength
            
            team_stats_available = len(team_strength) > 0
            
            if not team_strength:
                self.log("  Warning: Using fallback stats")
                team_strength = get_fallback_team_strength()
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
            
            # Sort by confidence bucket then confidence % desc
            bucket_order = {'HIGH': 0, 'MEDIUM': 1, 'MED': 1, 'LOW': 2}
            scores.sort(key=lambda s: (bucket_order.get(s.confidence_bucket, 2), -s.confidence_pct_value))
            self.scores = scores
            
            self.log(f"\n  Generated {len(scores)} predictions")
            
            # Update confidence counts
            high_count = sum(1 for s in scores if s.confidence_bucket == 'HIGH')
            med_count = sum(1 for s in scores if s.confidence_bucket == 'MEDIUM')
            low_count = sum(1 for s in scores if s.confidence_bucket == 'LOW')
            
            self.after(0, lambda: self.high_count_var.set(str(high_count)))
            self.after(0, lambda: self.med_count_var.set(str(med_count)))
            self.after(0, lambda: self.low_count_var.set(str(low_count)))
            
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
            
            # Create entries with new format
            entries = []
            for score in scores:
                pick_side = "HOME" if score.predicted_winner == score.home_team else "AWAY"
                
                # Map bucket to short form for spreadsheet
                bucket_short = score.confidence_bucket
                if bucket_short == "MEDIUM":
                    bucket_short = "MED"
                
                entry = PickEntry(
                    run_date=run_date,
                    game_id=getattr(score, 'game_id', ''),
                    away_team=score.away_team,
                    home_team=score.home_team,
                    pick_team=score.predicted_winner,
                    pick_side=pick_side,
                    confidence_pct=score.confidence_pct_value,
                    confidence_bucket=bucket_short,
                    model_prob=score.confidence,
                    edge_score=score.edge_score_total,
                    # Totals prediction fields
                    pred_away_pts=score.display_away_points,
                    pred_home_pts=score.display_home_points,
                    pred_total=score.display_total,
                    total_range_low=round(score.total_range_low),
                    total_range_high=round(score.total_range_high),
                    expected_pace=score.expected_possessions,
                    ppp_away=score.ppp_away,
                    ppp_home=score.ppp_home,
                    variance_band=score.totals_band_width,
                )
                entries.append(entry)
            
            # Save to SQLite database (primary storage) with per-game locking
            try:
                db_saved, db_locked = self.persist_predictions_to_db(self.scores, run_date, games)
                if db_locked > 0:
                    self.log(f"  Saved {db_saved} predictions to database ({db_locked} locked - already started)")
                else:
                    self.log(f"  Saved {db_saved} predictions to database")
                self.log(f"  DB location: {get_db_path()}")
            except Exception as e:
                self.log(f"  Warning: Could not save to DB: {e}")
            
            # Also save to Excel (legacy backup)
            try:
                tracker = ExcelTracker()
                saved_count = tracker.save_predictions(entries)
                self.log(f"  Saved {saved_count} predictions to Excel (backup)")
                self.log(f"  {get_tracking_path_message()}")
                
                # Update Excel summary
                stats = tracker.refresh_winrates()
                self.log(f"  Updated Excel summary sheet")
                
            except IOError as e:
                self.log(f"  Excel backup skipped: {e}")
                # Don't fail the whole operation if Excel is locked
            
            # Update UI
            self.after(0, self.update_predictions_display)
            self.after(0, self.update_injuries_display)
            self.after(0, self.update_game_selector)
            self.after(0, self.refresh_stats_from_db)
            
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
        """Update the predictions treeview with confidence, totals, and lock status display."""
        # Clear existing
        for item in self.pred_tree.get_children():
            self.pred_tree.delete(item)
        
        # Get lock status from database
        today = get_today_date_local()
        daily_picks = get_daily_picks(today)
        
        # Build lock status lookup
        lock_status = {}
        for pick in daily_picks:
            key = f"{pick.get('away_team', '')} @ {pick.get('home_team', '')}"
            lock_status[key] = pick.get('locked', 0) == 1
        
        # Add predictions
        for score in self.scores:
            matchup = f"{score.away_team} @ {score.home_team}"
            pick_side = "HOME" if score.predicted_winner == score.home_team else "AWAY"
            conf_bucket = score.confidence_bucket
            
            # Check if locked
            is_locked = lock_status.get(matchup, False)
            locked_display = "🔒" if is_locked else ""
            
            # Format predicted score
            pred_score = f"{score.display_away_points}-{score.display_home_points}"
            
            # Determine tags
            tags = []
            tag = conf_bucket.lower()
            if tag == 'med':
                tag = 'medium'
            tags.append(tag)
            
            if is_locked:
                tags.append('locked')
            
            self.pred_tree.insert('', tk.END, values=(
                matchup,
                score.predicted_winner,
                pick_side,
                f"{score.confidence_pct_value:.1f}%",
                conf_bucket,
                locked_display,
                pred_score,
                score.display_total,
                score.display_total_range,
                f"{score.edge_score_total:+.1f}",
                f"{score.projected_margin_home:+.1f}",
            ), tags=tuple(tags))
    
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
                # Update confidence display
                self.factor_conf_var.set(f"{score.confidence_pct_value:.1f}%")
                
                # Update bucket label with color
                bucket = score.confidence_bucket
                bucket_colors = {
                    'HIGH': COLORS['high'],
                    'MEDIUM': COLORS['medium'],
                    'MED': COLORS['medium'],
                    'LOW': COLORS['low']
                }
                self.factor_bucket_label.config(
                    text=bucket,
                    bg=bucket_colors.get(bucket, COLORS['text_muted'])
                )
                
                # Update totals summary
                self.factor_pred_score_var.set(
                    f"{score.away_team} {score.display_away_points} - "
                    f"{score.home_team} {score.display_home_points}"
                )
                self.factor_total_var.set(score.display_total_with_range)
                self.factor_poss_var.set(f"{score.expected_possessions:.1f}")
                self.factor_ppp_var.set(
                    f"{score.away_team} {score.ppp_away:.3f} / "
                    f"{score.home_team} {score.ppp_home:.3f}"
                )
                
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
                        factor.display_name,
                        factor.weight,
                        f"{factor.signed_value:+.3f}",
                        f"{factor.contribution:+.2f}",
                        factor.inputs_used,
                    ), tags=(tag,))
                break
    
    def open_tracking_file(self):
        """Open the tracking Excel file."""
        # Note: TRACKING_FILE_PATH is imported at module level from paths module
        import subprocess
        import platform
        
        if not TRACKING_FILE_PATH.exists():
            messagebox.showinfo(
                "File Not Found",
                f"No tracking file exists yet.\nRun predictions first.\n\nExpected location:\n{TRACKING_FILE_PATH}"
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
    # Log startup diagnostics (writes to persistent log file)
    print("\n" + "=" * 60)
    print("NBA Prediction Engine v3.1")
    print("=" * 60)
    log_startup_diagnostics()
    print(get_tracking_path_message())
    print("=" * 60 + "\n")
    
    app = NBAPredictor()
    app.mainloop()


if __name__ == "__main__":
    main()
