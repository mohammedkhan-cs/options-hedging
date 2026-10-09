"""Phase 1 of the options project: snapshot the SPX chain, clean it, back out the forward and discount factor,
solve implied vols for out-of-the-money options, report ATM vol and skew, and plot the smile.

Run during regular US market hours (about 9:45-15:45 Eastern, weekday): Yahoo's bid/ask are often zero otherwise.
Run only after DECISIONS.md and PREDICTIONS.md are saved: predictions 1 and 2 are scored against this output."""
import argparse
import datetime as dt
import hashlib
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import chain, config, implied_vol

SKEW_STRIKE_RATIO = 0.90      # prediction 2: put 10% below the forward


def check_gate():
    for name in ("DECISIONS.md", "PREDICTIONS.md"):
        p = config.ROOT / name
        if not p.exists():
            sys.exit(f"STOP: {name} not found. Save it before pulling any option data.")
        text = p.read_text(encoding="utf-8")
        if "[SET THIS" in text:
            sys.exit(f"STOP: {name} still contains a [SET THIS ...] placeholder. Set the date and time, then save.")
        print(f"{name} SHA-256: {hashlib.sha256(p.read_bytes()).hexdigest()}")
    print("Compare these with the hashes you noted when you saved the files.\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--underlying", default=config.UNDERLYING)
    args = ap.parse_args()
    check_gate()

    calls_raw, puts_raw, meta = chain.load_snapshot(args.underlying)
    snap_date = dt.date.fromisoformat(meta["snapshot_local_date"])
    expiry = dt.date.fromisoformat(meta["expiry"])
    days = (expiry - snap_date).days
    T = days / 365.0
    spot = meta["spot"]
    print(f"Snapshot: {meta['underlying']} taken {meta['snapshot_utc']} (UTC); spot {spot:,.2f} (as of {meta['spot_date']})")
    print(f"Expiry {meta['expiry']}: {days} calendar days, T = {T:.4f} years (calendar days / 365)")
    print(f"Raw rows: {len(calls_raw)} calls, {len(puts_raw)} puts. Cache hashes: calls {chain.file_hash(chain.RAW_CALLS)[:16]}..., "
          f"puts {chain.file_hash(chain.RAW_PUTS)[:16]}...")

    calls, rc = chain.clean_quotes(calls_raw)
    puts, rp = chain.clean_quotes(puts_raw)
    print(f"Quote cleaning (calls): {rc}")
    print(f"Quote cleaning (puts) : {rp}")

    par = chain.forward_and_df(calls, puts, spot)
    r_implied = -np.log(par["df"]) / T
    print(f"\nPut-call parity fit on {par['n_strikes']} strikes ({par['strikes'][0]:.0f} to {par['strikes'][1]:.0f}): "
          f"forward {par['F']:,.2f}, discount factor {par['df']:.5f} (implied rate {r_implied*100:.2f}%), "
          f"R-squared {par['r2']:.6f}, largest residual {par['max_abs_resid']:.3f}")
    if not (0.90 < par["df"] < 1.0005):
        sys.exit(f"STOP: discount factor {par['df']:.4f} is implausible. Do not continue; paste this output.")
    F, df = par["F"], par["df"]

    t = chain.otm_table(calls, puts, F)
    t["iv"] = [implied_vol.implied_vol(r.kind, r.mid, F, r.strike, T, df) for r in t.itertuples()]
    n_nan = int(t["iv"].isna().sum())
    good = t[t["iv"].notna()].copy()
    print(f"\nOut-of-the-money options in {chain.MONEYNESS_LO}-{chain.MONEYNESS_HI} x forward: {len(t)}; "
          f"implied vol solved for {len(good)} ({n_nan} failed). Usable strikes: {good['strike'].nunique()}")
    if good["strike"].nunique() < config.MIN_STRIKES:
        print(f"\nFALLBACK RULE TRIGGERED: fewer than {config.MIN_STRIKES} usable strikes for {args.underlying}.")
        print(f"Per DECISIONS.md, log this in ASSUMPTIONS.md, move the data/raw/chain_* files aside, and rerun with: "
              f"python3 -m src.smile --underlying {config.FALLBACK_UNDERLYING}")
        sys.exit(2)

    atm = implied_vol.interp_iv(good["k_over_f"], good["iv"], 1.0)
    low = implied_vol.interp_iv(good["k_over_f"], good["iv"], SKEW_STRIKE_RATIO)
    skew = (low - atm) * 100 if np.isfinite(atm) and np.isfinite(low) else float("nan")
    print(f"\nAT-THE-MONEY implied vol (linear interpolation at K = forward): {atm*100:.2f}%")
    print(f"Implied vol at K = {SKEW_STRIKE_RATIO:.2f} x forward: {low*100:.2f}%  ->  skew vs ATM: {skew:+.2f} points")
    grid = [0.80, 0.85, 0.90, 0.95, 0.975, 1.00, 1.025, 1.05, 1.075, 1.10]
    print("\nSmile at selected strike / forward points (linear interpolation; the full table is saved to a CSV):")
    for g in grid:
        v = implied_vol.interp_iv(good["k_over_f"], good["iv"], g)
        print(f"  {g:6.3f}  " + (f"{v*100:6.2f}%" if np.isfinite(v) else "   n/a"))

    if "impliedVolatility" in good.columns:
        near = good[(good["k_over_f"] > 0.95) & (good["k_over_f"] < 1.05)]
        diff = (near["iv"] - near["impliedVolatility"]).abs().median() * 100
        print(f"\nInformational only: median |our IV - Yahoo's impliedVolatility column| within +/-5% of the forward: {diff:.2f} points")

    out_dir = config.DATA_PROCESSED
    out_dir.mkdir(parents=True, exist_ok=True)
    good.to_csv(out_dir / "chain_clean_iv.csv", index=False)
    config.OUT_TABLES.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"underlying": meta["underlying"], "snapshot_utc": meta["snapshot_utc"], "expiry": meta["expiry"],
                   "days": days, "T_years": T, "spot": spot, "forward": F, "discount_factor": df, "implied_rate": r_implied,
                   "parity_r2": par["r2"], "n_usable_strikes": int(good["strike"].nunique()),
                   "atm_iv": atm, "iv_at_0.90F": low, "skew_points": skew}]).to_csv(config.OUT_TABLES / "chain_summary.csv", index=False)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(good["k_over_f"], good["iv"] * 100, "o-", ms=3.5, lw=1, color="tab:blue")
    ax.axvline(1.0, color="grey", lw=0.6, ls="--")
    ax.set_xlabel("strike / forward")
    ax.set_ylabel("implied volatility (%)")
    ax.set_title(f"{meta['underlying']} implied-vol smile, expiry {meta['expiry']} ({days} days)")
    config.OUT_FIGURES.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(config.OUT_FIGURES / "vol_smile.png", dpi=130)
    plt.close(fig)
    print("\nWrote data/processed/chain_clean_iv.csv, outputs/tables/chain_summary.csv, outputs/figures/vol_smile.png")


if __name__ == "__main__":
    main()