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
"""

import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from pathlib import Path


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
        
        # Configure styles
        self.setup_styles()
        
        # Create UI
        self.create_widgets()
        
        # Load initial winrate stats
        self.refresh_winrates()
    
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
        
        self.refresh_button = ttk.Button(
            right_frame,
            text="🔄 Refresh Stats",
            command=self.refresh_winrates,
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
        
        # Log tab
        self.log_frame = ttk.Frame(self.notebook, style='TFrame')
        self.notebook.add(self.log_frame, text="  📝 Log  ")
        self.create_log_view()
    
    def create_predictions_tree(self):
        """Create the predictions treeview with confidence display."""
        # Container with card-like appearance
        container = tk.Frame(self.predictions_frame, bg=COLORS['card_bg'])
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        columns = (
            'matchup', 'pick', 'side', 'conf_pct', 'bucket', 'edge', 
            'home_prob', 'away_prob', 'margin'
        )
        
        self.pred_tree = ttk.Treeview(
            container,
            columns=columns,
            show='headings',
            selectmode='browse'
        )
        
        # Configure columns with better widths
        col_configs = [
            ('matchup', 'Matchup', 130),
            ('pick', 'Pick', 70),
            ('side', 'Side', 70),
            ('conf_pct', 'Conf %', 80),
            ('bucket', 'Bucket', 80),
            ('edge', 'Edge', 70),
            ('home_prob', 'Home %', 80),
            ('away_prob', 'Away %', 80),
            ('margin', 'Margin', 80),
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
        
        # Configure row tags for confidence buckets
        self.pred_tree.tag_configure('high', background='#d4edda')
        self.pred_tree.tag_configure('medium', background='#fff3cd')
        self.pred_tree.tag_configure('low', background='#f8d7da')
    
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
        """Update the predictions treeview with confidence display."""
        # Clear existing
        for item in self.pred_tree.get_children():
            self.pred_tree.delete(item)
        
        # Add predictions
        for score in self.scores:
            matchup = f"{score.away_team} @ {score.home_team}"
            pick_side = "HOME" if score.predicted_winner == score.home_team else "AWAY"
            conf_bucket = score.confidence_bucket
            
            # Determine tag
            tag = conf_bucket.lower()
            if tag == 'med':
                tag = 'medium'
            
            self.pred_tree.insert('', tk.END, values=(
                matchup,
                score.predicted_winner,
                pick_side,
                f"{score.confidence_pct_value:.1f}%",
                conf_bucket,
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
