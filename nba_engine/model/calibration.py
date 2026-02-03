"""
Calibration and logging module for prediction tracking.

Handles:
- Prediction logging for backtesting
- Calibration metrics (Brier score, reliability)
- Edge scale adjustment
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import csv
import json


@dataclass
class PredictionRecord:
    """Single prediction record for logging."""
    date: str
    game_id: str
    home_team: str
    away_team: str
    edge_score: float
    home_win_prob: float
    away_win_prob: float
    predicted_winner: str
    confidence: float  # Confidence as 0.0-1.0
    projected_margin: float
    actual_winner: str = ""  # Filled in later
    actual_margin: float = 0.0  # Filled in later
    correct: Optional[bool] = None
    
    @property
    def confidence_pct(self) -> str:
        """Get confidence as percentage string."""
        return f"{self.confidence * 100:.0f}%"


class PredictionLogger:
    """Handles logging predictions and calculating calibration metrics."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.log_file = output_dir / "prediction_log.csv"
        self.calibration_file = output_dir / "calibration_stats.json"
        self._ensure_log_exists()
    
    def _ensure_log_exists(self):
        """Create log file with headers if it doesn't exist."""
        if not self.log_file.exists():
            self.output_dir.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'date', 'game_id', 'home_team', 'away_team',
                    'edge_score', 'home_win_prob', 'away_win_prob',
                    'predicted_winner', 'confidence', 'projected_margin',
                    'actual_winner', 'actual_margin', 'correct'
                ])
    
    def log_prediction(self, record: PredictionRecord):
        """Append a prediction to the log."""
        with open(self.log_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                record.date,
                record.game_id,
                record.home_team,
                record.away_team,
                record.edge_score,
                record.home_win_prob,
                record.away_win_prob,
                record.predicted_winner,
                record.confidence,
                record.projected_margin,
                record.actual_winner,
                record.actual_margin,
                record.correct if record.correct is not None else ''
            ])
    
    def log_predictions(self, records: list[PredictionRecord]):
        """Log multiple predictions at once."""
        for record in records:
            self.log_prediction(record)
    
    def get_all_predictions(self) -> list[dict]:
        """Read all predictions from log."""
        if not self.log_file.exists():
            return []
        
        predictions = []
        with open(self.log_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                predictions.append(row)
        
        return predictions
    
    def calculate_calibration(self) -> dict:
        """
        Calculate calibration metrics from logged predictions.
        
        Returns dict with:
        - brier_score
        - accuracy
        - reliability_bins
        - sample_size
        """
        predictions = self.get_all_predictions()
        
        # Filter to predictions with results
        completed = [p for p in predictions if p.get('actual_winner')]
        
        if len(completed) < 10:
            return {
                'brier_score': None,
                'accuracy': None,
                'reliability_bins': {},
                'sample_size': len(completed),
                'message': 'Need at least 10 completed predictions for calibration'
            }
        
        # Calculate Brier score and accuracy
        brier_sum = 0.0
        correct_count = 0
        
        # Reliability bins: [50-55, 55-60, 60-65, 65-70, 70-75, 75-80, 80+]
        bins = {
            '50-55': {'predictions': 0, 'wins': 0},
            '55-60': {'predictions': 0, 'wins': 0},
            '60-65': {'predictions': 0, 'wins': 0},
            '65-70': {'predictions': 0, 'wins': 0},
            '70-75': {'predictions': 0, 'wins': 0},
            '75-80': {'predictions': 0, 'wins': 0},
            '80+': {'predictions': 0, 'wins': 0},
        }
        
        for pred in completed:
            try:
                home_prob = float(pred['home_win_prob'])
                actual_winner = pred['actual_winner']
                home_team = pred['home_team']
                
                # Outcome: 1 if home won, 0 if away won
                outcome = 1 if actual_winner == home_team else 0
                
                # Brier score component
                brier_sum += (home_prob - outcome) ** 2
                
                # Accuracy
                predicted_winner = pred['predicted_winner']
                if predicted_winner == actual_winner:
                    correct_count += 1
                
                # Reliability bins (use higher probability)
                prob = max(home_prob, 1 - home_prob)
                favorite_won = (home_prob > 0.5 and outcome == 1) or (home_prob < 0.5 and outcome == 0)
                
                if prob < 0.55:
                    bin_key = '50-55'
                elif prob < 0.60:
                    bin_key = '55-60'
                elif prob < 0.65:
                    bin_key = '60-65'
                elif prob < 0.70:
                    bin_key = '65-70'
                elif prob < 0.75:
                    bin_key = '70-75'
                elif prob < 0.80:
                    bin_key = '75-80'
                else:
                    bin_key = '80+'
                
                bins[bin_key]['predictions'] += 1
                if favorite_won:
                    bins[bin_key]['wins'] += 1
                    
            except (ValueError, KeyError):
                continue
        
        n = len(completed)
        brier_score = brier_sum / n if n > 0 else None
        accuracy = correct_count / n if n > 0 else None
        
        # Calculate bin percentages
        reliability = {}
        for bin_key, data in bins.items():
            if data['predictions'] > 0:
                reliability[bin_key] = {
                    'predictions': data['predictions'],
                    'wins': data['wins'],
                    'win_rate': data['wins'] / data['predictions']
                }
        
        return {
            'brier_score': brier_score,
            'accuracy': accuracy,
            'reliability_bins': reliability,
            'sample_size': n,
        }
    
    def save_calibration(self):
        """Save calibration metrics to file."""
        metrics = self.calculate_calibration()
        metrics['updated_at'] = datetime.now().isoformat()
        
        with open(self.calibration_file, 'w') as f:
            json.dump(metrics, f, indent=2)
    
    def suggest_edge_scale(self) -> Optional[float]:
        """
        Suggest an adjusted EDGE_SCALE based on calibration.
        
        If predictions are overconfident, increase scale.
        If underconfident, decrease scale.
        """
        metrics = self.calculate_calibration()
        
        if metrics.get('sample_size', 0) < 50:
            return None  # Not enough data
        
        # Compare predicted vs actual win rates in reliability bins
        # If favorites are winning less than predicted, we're overconfident
        
        total_predicted_prob = 0.0
        total_actual_wins = 0
        count = 0
        
        for bin_key, data in metrics.get('reliability_bins', {}).items():
            if data['predictions'] >= 5:  # Minimum sample
                # Bin midpoint as predicted probability
                if bin_key == '50-55':
                    midpoint = 0.525
                elif bin_key == '55-60':
                    midpoint = 0.575
                elif bin_key == '60-65':
                    midpoint = 0.625
                elif bin_key == '65-70':
                    midpoint = 0.675
                elif bin_key == '70-75':
                    midpoint = 0.725
                elif bin_key == '75-80':
                    midpoint = 0.775
                else:
                    midpoint = 0.85
                
                total_predicted_prob += midpoint * data['predictions']
                total_actual_wins += data['wins']
                count += data['predictions']
        
        if count < 50:
            return None
        
        avg_predicted = total_predicted_prob / count
        avg_actual = total_actual_wins / count
        
        # If overconfident (predicted > actual), increase scale
        # If underconfident (predicted < actual), decrease scale
        current_scale = 12.0
        
        if avg_predicted > avg_actual + 0.03:
            # Overconfident - suggest higher scale
            return current_scale * 1.1
        elif avg_predicted < avg_actual - 0.03:
            # Underconfident - suggest lower scale
            return current_scale * 0.9
        
        return current_scale  # Well calibrated


# Calibration constants
EDGE_TO_MARGIN = 4.5  # Edge score to margin mapping
MARGIN_PROB_SCALE = 7.0  # Margin to probability scale
PROB_MIN = 0.05
PROB_MAX = 0.95


def edge_to_margin(edge_score: float, scale: float = EDGE_TO_MARGIN) -> float:
    """Convert edge score to projected margin."""
    return edge_score / scale


def margin_to_win_prob(margin: float, scale: float = MARGIN_PROB_SCALE) -> float:
    """
    Convert projected margin to win probability.
    
    Reference:
        margin  0 -> 50%
        margin  3 -> 60%
        margin  5 -> 67%
        margin 10 -> 81%
    """
    from math import exp
    raw_prob = 1.0 / (1.0 + exp(-margin / scale))
    return max(PROB_MIN, min(PROB_MAX, raw_prob))


def edge_to_win_prob(edge_score: float) -> float:
    """Convert edge score to win probability via margin."""
    margin = edge_to_margin(edge_score)
    return margin_to_win_prob(margin)
