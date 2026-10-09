"""Chain cleaning, put-call parity, and implied-vol solving must behave on synthetic chains with known answers."""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from src import chain, implied_vol, pricing

F0, DF0, T0 = 100.0, 0.99, 0.16
STRIKES = np.arange(80.0, 120.1, 2.5)


def true_sigma(k):
    return 0.20 + 0.001 * (F0 - k)            # linear smile: higher vol at lower strikes


def make_side(kind, half_spread=0.05):
    mid = pricing.price(kind, F0, STRIKES, T0, true_sigma(STRIKES), DF0)
    return pd.DataFrame({"strike": STRIKES, "bid": mid - half_spread, "ask": mid + half_spread})


def test_implied_vol_round_trip():
    rng = np.random.default_rng(0)
    for kind in ("call", "put"):
        for _ in range(100):
            K, s = F0 * rng.uniform(0.8, 1.2), rng.uniform(0.08, 0.7)
            p = float(pricing.price(kind, F0, K, T0, s, DF0))
            assert abs(implied_vol.implied_vol(kind, p, F0, K, T0, DF0) - s) < 1e-7


def test_implied_vol_is_nan_when_no_solution_exists():
    assert np.isnan(implied_vol.implied_vol("call", 0.5 * DF0 * 10, F0, 90.0, T0, DF0))   # below intrinsic
    assert np.isnan(implied_vol.implied_vol("call", DF0 * F0 + 1, F0, 90.0, T0, DF0))      # above the upper bound
    assert np.isnan(implied_vol.implied_vol("put", 0.0, F0, 90.0, T0, DF0))


def test_clean_quotes_drops_the_right_rows():
    df = pd.DataFrame({"strike": [1, 2, 3, 4, 5],
                       "bid": [0.0, 2.0, 1.0, 5.0, 1.0],
                       "ask": [1.0, 1.9, 3.0, 5.2, 1.1]})
    clean, why = chain.clean_quotes(df)
    assert list(clean["strike"]) == [4, 5]     # bid=0, crossed and wide (spread 2/2 = 100%) are dropped
    assert why["bid_not_positive"] == 1 and why["ask_below_bid"] == 1 and why["spread_too_wide"] == 1 and why["kept"] == 2


def test_parity_recovers_forward_and_discount_factor():
    calls, puts = make_side("call"), make_side("put")
    calls["mid"], puts["mid"] = (calls.bid + calls.ask) / 2, (puts.bid + puts.ask) / 2
    res = chain.forward_and_df(calls, puts, spot=100.5)
    assert abs(res["F"] - F0) < 0.05 and abs(res["df"] - DF0) < 0.001
    assert res["r2"] > 0.9999


def test_parity_fit_needs_enough_strikes():
    calls = pd.DataFrame({"strike": [100.0, 102.5], "mid": [5.0, 3.0]})
    puts = pd.DataFrame({"strike": [100.0, 102.5], "mid": [4.0, 5.0]})
    with pytest.raises(ValueError):
        chain.forward_and_df(calls, puts, spot=100.0)


def test_otm_table_uses_puts_below_and_calls_above_the_forward():
    calls, puts = make_side("call"), make_side("put")
    t = chain.otm_table(calls, puts, F0)
    assert set(t.loc[t.kind == "put", "strike"]) == {k for k in STRIKES if k < F0}
    assert set(t.loc[t.kind == "call", "strike"]) == {k for k in STRIKES if k >= F0 and k / F0 <= 1.10}
    assert t["k_over_f"].between(0.80, 1.10).all()


def test_smile_solved_from_otm_mids_matches_the_true_smile():
    calls, puts = make_side("call"), make_side("put")
    calls["mid"], puts["mid"] = (calls.bid + calls.ask) / 2, (puts.bid + puts.ask) / 2
    t = chain.otm_table(calls, puts, F0)
    t["iv"] = [implied_vol.implied_vol(r.kind, r.mid, F0, r.strike, T0, DF0) for r in t.itertuples()]
    assert np.max(np.abs(t["iv"] - true_sigma(t["strike"]))) < 1e-7
    assert abs(implied_vol.interp_iv(t["k_over_f"], t["iv"], 1.0) - 0.20) < 1e-7
    assert abs(implied_vol.interp_iv(t["k_over_f"], t["iv"], 0.90) - true_sigma(90.0)) < 1e-7
    assert np.isnan(implied_vol.interp_iv(t["k_over_f"], t["iv"], 0.5))      # no extrapolation


def test_choose_expiry_picks_the_closest_to_target_and_skips_the_past():
    today = dt.date(2026, 10, 7)
    exps = ["2026-10-07", "2026-10-16", "2026-11-20", "2026-12-18", "2027-01-15"]   # 0, 9, 44, 72, 100 days
    assert chain.choose_expiry(exps, today, 60) == "2026-12-18"
    assert chain.choose_expiry(exps, today, 40) == "2026-11-20"
    with pytest.raises(ValueError):
        chain.choose_expiry(["2026-10-01"], today)