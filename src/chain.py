"""Option-chain snapshot (cached unedited), quote cleaning, and the forward and discount factor from put-call parity.
Cleaning rules are the ones fixed in DECISIONS.md Section 3 before any data was pulled."""
import datetime as dt
import hashlib
import json

import numpy as np
import pandas as pd

from src import config

MAX_REL_SPREAD = 0.50          # drop quotes with (ask - bid) / mid above this
MONEYNESS_LO, MONEYNESS_HI = 0.80, 1.10   # keep strike / forward inside this window
PARITY_WINDOW = 0.10           # first parity fit uses strikes within +/- 10% of spot
MIN_PARITY_STRIKES = 5

RAW_CALLS = config.DATA_RAW / "chain_calls.csv"
RAW_PUTS = config.DATA_RAW / "chain_puts.csv"
RAW_META = config.DATA_RAW / "chain_meta.json"


def choose_expiry(expiries, snapshot_date, target_days=None):
    """The listed expiry whose distance from the snapshot date is closest to target_days (ties go to the earlier date)."""
    target_days = target_days or config.TARGET_CALENDAR_DAYS
    future = [e for e in expiries if (dt.date.fromisoformat(e) - snapshot_date).days > 0]
    if not future:
        raise ValueError("No future expiries available.")
    return min(future, key=lambda e: (abs((dt.date.fromisoformat(e) - snapshot_date).days - target_days), e))


def download_snapshot(underlying):
    """Pull one chain from Yahoo Finance and cache it unedited. Never overwrites an existing snapshot."""
    import yfinance as yf
    tk = yf.Ticker(underlying)
    now = dt.datetime.now(dt.timezone.utc)
    snapshot_date = dt.datetime.now().date()
    expiries = tk.options
    if not expiries:
        raise RuntimeError(f"Yahoo returned no option expiries for {underlying}.")
    expiry = choose_expiry(expiries, snapshot_date)
    oc = tk.option_chain(expiry)
    hist = tk.history(period="5d")
    if hist.empty:
        raise RuntimeError(f"No price history for {underlying}.")
    config.DATA_RAW.mkdir(parents=True, exist_ok=True)
    oc.calls.to_csv(RAW_CALLS, index=False)
    oc.puts.to_csv(RAW_PUTS, index=False)
    meta = {"underlying": underlying, "snapshot_utc": now.isoformat(), "snapshot_local_date": snapshot_date.isoformat(),
            "expiry": expiry, "spot": float(hist["Close"].iloc[-1]), "spot_date": str(hist.index[-1]),
            "all_expiries": list(expiries), "yfinance_version": yf.__version__}
    RAW_META.write_text(json.dumps(meta, indent=2))
    return meta


def load_snapshot(underlying):
    """Use the cached snapshot if present (never silently re-pull); otherwise download one."""
    if RAW_META.exists() and RAW_CALLS.exists() and RAW_PUTS.exists():
        meta = json.loads(RAW_META.read_text())
        if meta["underlying"] != underlying:
            raise RuntimeError(f"Cached snapshot is for {meta['underlying']}, not {underlying}. "
                               "Move the three data/raw/chain_* files aside (and log it in ASSUMPTIONS.md) to pull a new one.")
    else:
        meta = download_snapshot(underlying)
    return pd.read_csv(RAW_CALLS), pd.read_csv(RAW_PUTS), meta


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_quotes(df, max_rel_spread=MAX_REL_SPREAD):
    """Apply the quote rules from DECISIONS.md. Returns (clean frame with a mid column, dict of drop counts)."""
    d = df.copy()
    d["mid"] = (d["bid"] + d["ask"]) / 2.0
    reasons = {"bid_not_positive": int((~(d["bid"] > 0)).sum()),
               "ask_below_bid": int((d["ask"] < d["bid"]).sum())}
    ok = (d["bid"] > 0) & (d["ask"] >= d["bid"]) & (d["mid"] > 0)
    wide = ok & (((d["ask"] - d["bid"]) / d["mid"]) > max_rel_spread)
    reasons["spread_too_wide"] = int(wide.sum())
    keep = ok & ~wide
    reasons["kept"] = int(keep.sum())
    reasons["input_rows"] = int(len(d))
    return d[keep].reset_index(drop=True), reasons


def forward_and_df(calls, puts, spot, window=PARITY_WINDOW):
    """Put-call parity: C - P = df*(F - K). Regress (C - P) on K across strikes quoted for both a call and a put:
    slope = -df, intercept = df*F. Returns F, df, the implied rate, R-squared and the largest residual."""
    m = calls[["strike", "mid"]].merge(puts[["strike", "mid"]], on="strike", suffixes=("_c", "_p"))
    m = m[(m["strike"] >= spot * (1 - window)) & (m["strike"] <= spot * (1 + window))]
    if len(m) < MIN_PARITY_STRIKES:
        raise ValueError(f"Only {len(m)} strikes have both a clean call and put near the money (need {MIN_PARITY_STRIKES}).")
    y = (m["mid_c"] - m["mid_p"]).to_numpy()
    k = m["strike"].to_numpy()
    slope, intercept = np.polyfit(k, y, 1)
    df = -slope
    F = intercept / df
    resid = y - (intercept + slope * k)
    r2 = 1 - resid.var() / y.var() if y.var() > 0 else float("nan")
    return {"F": float(F), "df": float(df), "n_strikes": int(len(m)), "r2": float(r2),
            "max_abs_resid": float(np.max(np.abs(resid))), "strikes": (float(k.min()), float(k.max()))}


def otm_table(calls, puts, F, lo=MONEYNESS_LO, hi=MONEYNESS_HI):
    """Out-of-the-money options only (puts below the forward, calls at or above it), inside the moneyness window."""
    p = puts[puts["strike"] < F].assign(kind="put")
    c = calls[calls["strike"] >= F].assign(kind="call")
    t = pd.concat([p, c], ignore_index=True)
    t["k_over_f"] = t["strike"] / F
    t = t[(t["k_over_f"] >= lo) & (t["k_over_f"] <= hi)]
    return t.sort_values("strike").reset_index(drop=True)