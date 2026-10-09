"""Robustness check on the put-call parity fit (informational; the main run keeps its pre-set +/-10% window).
Refits the forward and discount factor with narrower and wider strike windows and shows how much the
ATM implied vol and the 0.90F skew would change. Reads the cached chain snapshot only."""
import datetime as dt

import numpy as np
import pandas as pd

from src import chain, config, implied_vol


def main():
    calls_raw, puts_raw, meta = chain.load_snapshot(config.UNDERLYING)
    days = (dt.date.fromisoformat(meta["expiry"]) - dt.date.fromisoformat(meta["snapshot_local_date"])).days
    T, spot = days / 365.0, meta["spot"]
    calls, _ = chain.clean_quotes(calls_raw)
    puts, _ = chain.clean_quotes(puts_raw)
    rows = []
    for w in (0.02, 0.03, 0.05, 0.10, 0.15):
        try:
            p = chain.forward_and_df(calls, puts, spot, window=w)
        except ValueError as e:
            rows.append({"window": w, "note": str(e)[:60]})
            continue
        t = chain.otm_table(calls, puts, p["F"])
        iv = np.array([implied_vol.implied_vol(r.kind, r.mid, p["F"], r.strike, T, p["df"]) for r in t.itertuples()])
        ok = np.isfinite(iv)
        atm = implied_vol.interp_iv(t["k_over_f"][ok], iv[ok], 1.0)
        low = implied_vol.interp_iv(t["k_over_f"][ok], iv[ok], 0.90)
        rows.append({"window": w, "n_strikes": p["n_strikes"], "forward": round(p["F"], 2), "df": round(p["df"], 5),
                     "r2": round(p["r2"], 7), "max_resid": round(p["max_abs_resid"], 2),
                     "atm_iv_%": round(atm * 100, 3), "iv_0.90F_%": round(low * 100, 3), "skew_pts": round((low - atm) * 100, 3)})
    pd.set_option("display.width", 200)
    print(f"Parity window robustness (spot {spot:,.2f}, {days} days). The main run uses window 0.10.")
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()