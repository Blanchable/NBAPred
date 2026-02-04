"""
Excel Tracking Module for NBA Prediction Engine.

Manages a single persistent Excel workbook with:
- Picks sheet: One block of picks per calendar date (overwrite-by-day)
- Summary sheet: Auto-calculated winrate statistics

The engine ONLY supports today's slate - no historical/backfill functionality.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
import os

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import FormulaRule


# Constants
TRACKING_DIR = Path(__file__).parent.parent / "outputs" / "tracking"
TRACKING_FILE_PATH = TRACKING_DIR / "NBA_Engine_Tracking.xlsx"

# Sheet names
PICKS_SHEET = "Picks"
SUMMARY_SHEET = "Summary"

# Column headers for Picks sheet (exact order per spec)
PICKS_COLUMNS = [
    "run_date",              # A - YYYY-MM-DD
    "run_timestamp",         # B - YYYY-MM-DD HH:MM:SS local
    "game_id",               # C - string or blank
    "away_team",             # D
    "home_team",             # E
    "pick_team",             # F
    "pick_side",             # G - HOME or AWAY
    "confidence_level",      # H - HIGH, MEDIUM, LOW
    "edge_score_total",      # I
    "projected_margin_home", # J
    "home_win_prob",         # K
    "away_win_prob",         # L
    "top_5_factors",         # M
    "data_confidence",       # N - HIGH, MEDIUM, LOW
    "actual_winner",         # O - BLANK (user fills manually)
    "correct",               # P - formula-driven
    "notes",                 # Q - optional
]

# Styles
HEADER_FONT = Font(bold=True)
GREEN_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
RED_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style='thin'),
    right=Side(style='thin'),
    top=Side(style='thin'),
    bottom=Side(style='thin')
)


@dataclass
class PickEntry:
    """A single prediction entry for the Picks sheet."""
    run_date: str
    run_timestamp: str
    game_id: str
    away_team: str
    home_team: str
    pick_team: str
    pick_side: str  # "HOME" or "AWAY"
    confidence_level: str  # "HIGH", "MEDIUM", "LOW"
    edge_score_total: float
    projected_margin_home: float
    home_win_prob: float
    away_win_prob: float
    top_5_factors: str
    data_confidence: str
    actual_winner: str = ""  # Blank - user fills
    notes: str = ""
    
    def to_row(self, row_num: int) -> list:
        """Convert to row values with formula for correct column."""
        # Formula: =IF(O{row}="","",IF(O{row}=F{row},1,0))
        correct_formula = f'=IF(O{row_num}="","",IF(O{row_num}=F{row_num},1,0))'
        
        return [
            self.run_date,
            self.run_timestamp,
            self.game_id,
            self.away_team,
            self.home_team,
            self.pick_team,
            self.pick_side,
            self.confidence_level,
            self.edge_score_total,
            self.projected_margin_home,
            self.home_win_prob,
            self.away_win_prob,
            self.top_5_factors,
            self.data_confidence,
            self.actual_winner,
            correct_formula,  # Formula, not value
            self.notes,
        ]


@dataclass
class WinrateStats:
    """Winrate statistics computed from the Picks sheet."""
    # Overall
    total_graded: int = 0
    wins: int = 0
    losses: int = 0
    win_pct: float = 0.0
    
    # By confidence level
    high_graded: int = 0
    high_wins: int = 0
    high_losses: int = 0
    high_win_pct: float = 0.0
    
    medium_graded: int = 0
    medium_wins: int = 0
    medium_losses: int = 0
    medium_win_pct: float = 0.0
    
    low_graded: int = 0
    low_wins: int = 0
    low_losses: int = 0
    low_win_pct: float = 0.0
    
    # Pending (no actual_winner)
    pending_total: int = 0
    pending_high: int = 0
    pending_medium: int = 0
    pending_low: int = 0


class ExcelTracker:
    """
    Manages the NBA Engine tracking Excel workbook.
    
    Key features:
    - Single persistent workbook at outputs/tracking/NBA_Engine_Tracking.xlsx
    - Overwrite-by-day: Running multiple times replaces that day's picks
    - Summary sheet with auto-calculated winrate stats
    """
    
    def __init__(self, file_path: Path = None):
        """Initialize the tracker."""
        self.file_path = file_path or TRACKING_FILE_PATH
        self._ensure_directory()
    
    def _ensure_directory(self):
        """Ensure the tracking directory exists."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _create_new_workbook(self) -> Workbook:
        """Create a new workbook with Picks and Summary sheets."""
        wb = Workbook()
        
        # Rename default sheet to Picks
        picks_sheet = wb.active
        picks_sheet.title = PICKS_SHEET
        
        # Add header row
        for col_idx, header in enumerate(PICKS_COLUMNS, 1):
            cell = picks_sheet.cell(row=1, column=col_idx, value=header)
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal='center')
        
        # Freeze header row
        picks_sheet.freeze_panes = 'A2'
        
        # Enable auto-filter
        picks_sheet.auto_filter.ref = f"A1:{get_column_letter(len(PICKS_COLUMNS))}1"
        
        # Set column widths
        column_widths = {
            'A': 12,  # run_date
            'B': 20,  # run_timestamp
            'C': 12,  # game_id
            'D': 10,  # away_team
            'E': 10,  # home_team
            'F': 10,  # pick_team
            'G': 10,  # pick_side
            'H': 12,  # confidence_level
            'I': 15,  # edge_score_total
            'J': 18,  # projected_margin_home
            'K': 12,  # home_win_prob
            'L': 12,  # away_win_prob
            'M': 40,  # top_5_factors
            'N': 15,  # data_confidence
            'O': 14,  # actual_winner
            'P': 10,  # correct
            'Q': 20,  # notes
        }
        for col, width in column_widths.items():
            picks_sheet.column_dimensions[col].width = width
        
        # Create Summary sheet
        summary_sheet = wb.create_sheet(SUMMARY_SHEET)
        self._initialize_summary_sheet(summary_sheet)
        
        return wb
    
    def _initialize_summary_sheet(self, sheet):
        """Initialize the Summary sheet structure."""
        # Title
        sheet['A1'] = "NBA Engine Performance Summary"
        sheet['A1'].font = Font(bold=True, size=14)
        
        # Overall section
        sheet['A3'] = "OVERALL PERFORMANCE"
        sheet['A3'].font = Font(bold=True)
        
        sheet['A4'] = "Total Graded Picks:"
        sheet['A5'] = "Wins:"
        sheet['A6'] = "Losses:"
        sheet['A7'] = "Win %:"
        
        # By confidence section
        sheet['A9'] = "BY CONFIDENCE LEVEL"
        sheet['A9'].font = Font(bold=True)
        
        # HIGH
        sheet['A11'] = "HIGH Confidence"
        sheet['A11'].font = Font(bold=True)
        sheet['A12'] = "Graded:"
        sheet['A13'] = "Wins:"
        sheet['A14'] = "Losses:"
        sheet['A15'] = "Win %:"
        
        # MEDIUM
        sheet['A17'] = "MEDIUM Confidence"
        sheet['A17'].font = Font(bold=True)
        sheet['A18'] = "Graded:"
        sheet['A19'] = "Wins:"
        sheet['A20'] = "Losses:"
        sheet['A21'] = "Win %:"
        
        # LOW
        sheet['A23'] = "LOW Confidence"
        sheet['A23'].font = Font(bold=True)
        sheet['A24'] = "Graded:"
        sheet['A25'] = "Wins:"
        sheet['A26'] = "Losses:"
        sheet['A27'] = "Win %:"
        
        # Pending section
        sheet['A29'] = "PENDING (No Result Yet)"
        sheet['A29'].font = Font(bold=True)
        sheet['A30'] = "Total Pending:"
        sheet['A31'] = "HIGH Pending:"
        sheet['A32'] = "MEDIUM Pending:"
        sheet['A33'] = "LOW Pending:"
        
        # Last updated
        sheet['A35'] = "Last Updated:"
        
        # Set column widths
        sheet.column_dimensions['A'].width = 25
        sheet.column_dimensions['B'].width = 15
    
    def _load_or_create_workbook(self) -> Workbook:
        """Load existing workbook or create new one."""
        if self.file_path.exists():
            try:
                return load_workbook(self.file_path)
            except Exception as e:
                raise IOError(
                    f"Cannot open {self.file_path.name}. "
                    f"Please close the file and try again.\nError: {e}"
                )
        else:
            return self._create_new_workbook()
    
    def save_predictions(self, picks: List[PickEntry]) -> int:
        """
        Save predictions to the Picks sheet.
        
        Implements OVERWRITE-BY-DAY rule:
        - Deletes all rows where run_date == today's date
        - Appends new predictions at the bottom
        
        Args:
            picks: List of PickEntry objects to save
            
        Returns:
            Number of picks saved
        """
        if not picks:
            return 0
        
        # Get today's date
        today = picks[0].run_date
        
        try:
            wb = self._load_or_create_workbook()
        except IOError as e:
            raise e
        
        picks_sheet = wb[PICKS_SHEET]
        
        # Find and delete all rows for today's date
        rows_to_delete = []
        for row_idx in range(2, picks_sheet.max_row + 1):
            cell_value = picks_sheet.cell(row=row_idx, column=1).value
            if cell_value == today:
                rows_to_delete.append(row_idx)
        
        # Delete rows in reverse order to maintain indices
        for row_idx in reversed(rows_to_delete):
            picks_sheet.delete_rows(row_idx)
        
        # Find the next available row
        next_row = picks_sheet.max_row + 1
        if next_row == 1:  # Empty sheet (only header exists but max_row is 1)
            next_row = 2
        
        # Append new predictions
        for pick in picks:
            row_data = pick.to_row(next_row)
            for col_idx, value in enumerate(row_data, 1):
                cell = picks_sheet.cell(row=next_row, column=col_idx, value=value)
                cell.alignment = Alignment(horizontal='center')
            next_row += 1
        
        # Add conditional formatting for correct column (P)
        # Find the range of data rows
        data_start = 2
        data_end = picks_sheet.max_row
        
        if data_end >= data_start:
            # Green for correct (=1)
            picks_sheet.conditional_formatting.add(
                f'P{data_start}:P{data_end}',
                FormulaRule(
                    formula=['P2=1'],
                    fill=GREEN_FILL
                )
            )
            # Red for incorrect (=0)
            picks_sheet.conditional_formatting.add(
                f'P{data_start}:P{data_end}',
                FormulaRule(
                    formula=['P2=0'],
                    fill=RED_FILL
                )
            )
        
        # Update auto-filter range
        picks_sheet.auto_filter.ref = f"A1:{get_column_letter(len(PICKS_COLUMNS))}{picks_sheet.max_row}"
        
        # Save workbook
        try:
            wb.save(self.file_path)
        except PermissionError:
            raise IOError(
                f"Please close {self.file_path.name} and try again."
            )
        
        return len(picks)
    
    def compute_winrate_stats(self) -> WinrateStats:
        """
        Compute winrate statistics from the Picks sheet.
        
        Reads the Excel file, ignores rows where actual_winner is blank,
        and computes stats in Python.
        
        Returns:
            WinrateStats object with computed statistics
        """
        stats = WinrateStats()
        
        if not self.file_path.exists():
            return stats
        
        try:
            wb = load_workbook(self.file_path, data_only=True)
        except Exception:
            return stats
        
        picks_sheet = wb[PICKS_SHEET]
        
        # Process each data row
        for row_idx in range(2, picks_sheet.max_row + 1):
            # Get relevant columns
            confidence = picks_sheet.cell(row=row_idx, column=8).value  # H
            pick_team = picks_sheet.cell(row=row_idx, column=6).value   # F
            actual_winner = picks_sheet.cell(row=row_idx, column=15).value  # O
            
            if not confidence or not pick_team:
                continue
            
            confidence = str(confidence).upper()
            
            # Check if graded or pending
            if actual_winner and str(actual_winner).strip():
                # Graded pick
                is_correct = str(actual_winner).strip().upper() == str(pick_team).strip().upper()
                
                stats.total_graded += 1
                if is_correct:
                    stats.wins += 1
                else:
                    stats.losses += 1
                
                # By confidence
                if confidence == "HIGH":
                    stats.high_graded += 1
                    if is_correct:
                        stats.high_wins += 1
                    else:
                        stats.high_losses += 1
                elif confidence == "MEDIUM":
                    stats.medium_graded += 1
                    if is_correct:
                        stats.medium_wins += 1
                    else:
                        stats.medium_losses += 1
                elif confidence == "LOW":
                    stats.low_graded += 1
                    if is_correct:
                        stats.low_wins += 1
                    else:
                        stats.low_losses += 1
            else:
                # Pending pick
                stats.pending_total += 1
                if confidence == "HIGH":
                    stats.pending_high += 1
                elif confidence == "MEDIUM":
                    stats.pending_medium += 1
                elif confidence == "LOW":
                    stats.pending_low += 1
        
        # Calculate win percentages
        if stats.total_graded > 0:
            stats.win_pct = (stats.wins / stats.total_graded) * 100
        if stats.high_graded > 0:
            stats.high_win_pct = (stats.high_wins / stats.high_graded) * 100
        if stats.medium_graded > 0:
            stats.medium_win_pct = (stats.medium_wins / stats.medium_graded) * 100
        if stats.low_graded > 0:
            stats.low_win_pct = (stats.low_wins / stats.low_graded) * 100
        
        wb.close()
        return stats
    
    def update_summary_sheet(self, stats: WinrateStats = None):
        """
        Update the Summary sheet with computed statistics.
        
        Args:
            stats: Pre-computed stats, or None to compute fresh
        """
        if stats is None:
            stats = self.compute_winrate_stats()
        
        if not self.file_path.exists():
            return
        
        try:
            wb = load_workbook(self.file_path)
        except Exception:
            return
        
        summary_sheet = wb[SUMMARY_SHEET]
        
        # Overall
        summary_sheet['B4'] = stats.total_graded
        summary_sheet['B5'] = stats.wins
        summary_sheet['B6'] = stats.losses
        summary_sheet['B7'] = f"{stats.win_pct:.1f}%" if stats.total_graded > 0 else "N/A"
        
        # HIGH
        summary_sheet['B12'] = stats.high_graded
        summary_sheet['B13'] = stats.high_wins
        summary_sheet['B14'] = stats.high_losses
        summary_sheet['B15'] = f"{stats.high_win_pct:.1f}%" if stats.high_graded > 0 else "N/A"
        
        # MEDIUM
        summary_sheet['B18'] = stats.medium_graded
        summary_sheet['B19'] = stats.medium_wins
        summary_sheet['B20'] = stats.medium_losses
        summary_sheet['B21'] = f"{stats.medium_win_pct:.1f}%" if stats.medium_graded > 0 else "N/A"
        
        # LOW
        summary_sheet['B24'] = stats.low_graded
        summary_sheet['B25'] = stats.low_wins
        summary_sheet['B26'] = stats.low_losses
        summary_sheet['B27'] = f"{stats.low_win_pct:.1f}%" if stats.low_graded > 0 else "N/A"
        
        # Pending
        summary_sheet['B30'] = stats.pending_total
        summary_sheet['B31'] = stats.pending_high
        summary_sheet['B32'] = stats.pending_medium
        summary_sheet['B33'] = stats.pending_low
        
        # Last updated
        summary_sheet['B35'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            wb.save(self.file_path)
        except PermissionError:
            pass  # Silently fail if file is locked
        
        wb.close()
    
    def refresh_winrates(self) -> WinrateStats:
        """
        Refresh winrate statistics by re-reading the Excel file.
        
        Returns:
            Updated WinrateStats
        """
        stats = self.compute_winrate_stats()
        self.update_summary_sheet(stats)
        return stats
    
    def file_exists(self) -> bool:
        """Check if the tracking file exists."""
        return self.file_path.exists()
    
    def get_file_path(self) -> str:
        """Get the tracking file path as string."""
        return str(self.file_path)
