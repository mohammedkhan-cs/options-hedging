"""All constants. Hand-filled to mirror DECISIONS.md. No logic."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
OUT_FIGURES = ROOT / "outputs" / "figures"
OUT_TABLES = ROOT / "outputs" / "tables"

# Owner decisions (DECISIONS.md Section 2)
UNDERLYING = "^SPX"          # Yahoo Finance symbol for the S&P 500 index (European-style options)
FALLBACK_UNDERLYING = "SPY"  # used only if fewer than MIN_STRIKES usable strikes remain after cleaning
MIN_STRIKES = 15
TARGET_CALENDAR_DAYS = 60    # listed expiry closest to this many calendar days from the snapshot date
OPTION_TRADING_DAYS = 42     # about 60 calendar days

# Implementer decisions (DECISIONS.md Section 3)
STEPS_PER_DAY = 7            # simulation grid: 7 steps per trading day, 294 steps over 42 days
REHEDGE_EVERY_DAYS = [21, 7, 3, 1, 1 / 7]   # 2, 6, 14, 42 and 294 rehedges over the option's life
VOL_RATIOS = [0.8, 1.0, 1.2]                # realized vol as a multiple of the implied vol the option was sold at
N_PATHS = 10_000
COST_BPS = [0, 1, 2]                         # cost per hedge trade, basis points of notional traded
TRADING_DAYS_PER_YEAR = 252
RANDOM_SEED = 0