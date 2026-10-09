"""The hedging simulation must reproduce exact facts before any result is read."""
import numpy as np
import pytest

from src import config, hedging, pricing

F0, SIG = 7800.0, 0.13
N_PATHS = 4000


@pytest.fixture(scope="module")
def grid():
    res, prem, T = hedging.run_grid(F0, SIG, n_paths=N_PATHS, costs=[0, 1])
    return res, prem, T


def test_expected_pnl_is_price_at_implied_minus_price_at_realized(grid):
    # The hedge gains are martingale increments, so E[P&L] = premium - E[payoff], whatever the hedging frequency.
    res, _, _ = grid
    a = res[res.cost_bps == 0]
    gap = (a["mean_pct"] - a["theory_mean_pct_no_cost"]).abs() / a["se_pct"]
    assert gap.max() < 4.0


def test_theory_signs_and_size(grid):
    res, _, _ = grid
    t = res[res.cost_bps == 0].drop_duplicates("ratio").set_index("ratio")["theory_mean_pct_no_cost"]
    assert t.loc[0.8] > 15 and t.loc[1.2] < -15 and abs(t.loc[1.0]) < 1e-9


def test_spread_shrinks_with_the_square_root_of_rehedges(grid):
    res, _, _ = grid
    s = res[(res.cost_bps == 0) & (res.ratio == 1.0)].set_index("n_rehedges")["std_pct"]
    assert 2.2 < s.loc[42] / s.loc[294] < 3.2            # sqrt(7) = 2.65
    assert 1.5 < s.loc[14] / s.loc[42] < 2.0             # sqrt(3) = 1.73
    assert s.is_monotonic_decreasing


def test_costs_lower_the_mean_and_rise_with_trading_frequency(grid):
    res, _, _ = grid
    r = res[res.ratio == 1.0]
    for n_re in r["n_rehedges"].unique():
        m0 = r[(r.n_rehedges == n_re) & (r.cost_bps == 0)]["mean_pct"].iloc[0]
        m1 = r[(r.n_rehedges == n_re) & (r.cost_bps == 1)]["mean_pct"].iloc[0]
        assert m1 < m0
    c = r[r.cost_bps == 1].set_index("n_rehedges")["avg_cost_pct"]
    assert c.loc[294] > c.loc[42] > c.loc[2] > 0


def test_same_seed_gives_identical_results():
    a, _, _ = hedging.run_grid(F0, SIG, n_paths=500, ratios=[1.0], rehedge_days=[1], costs=[0])
    b, _, _ = hedging.run_grid(F0, SIG, n_paths=500, ratios=[1.0], rehedge_days=[1], costs=[0])
    assert a.equals(b)


def test_vectorized_pnl_matches_an_explicit_loop():
    rng = np.random.default_rng(3)
    n_steps, paths, every = 14, 5, 2
    T = n_steps / 7 / 252
    z = rng.standard_normal((paths, n_steps))
    F = hedging.simulate_forward_paths(100.0, 0.2, T, n_steps, z)
    K, cb = 100.0, 2.0
    pnl, prem, costs, n_re = hedging.hedged_pnl(F, K, T, 0.2, every, cb)
    dt = T / n_steps
    for p in range(paths):
        cash, pos = prem, 0.0
        for s in range(0, n_steps, every):
            d = float(pricing.delta("call", F[p, s], K, T - s * dt, 0.2))
            cash -= cb / 1e4 * abs(d - pos) * F[p, s]
            pos = d
            cash += pos * (F[p, min(s + every, n_steps)] - F[p, s])
        cash -= cb / 1e4 * abs(pos) * F[p, -1]
        cash -= max(F[p, -1] - K, 0.0)
        assert abs(cash - pnl[p]) < 1e-9


def test_simulated_forward_is_a_martingale():
    rng = np.random.default_rng(1)
    z = rng.standard_normal((20000, 294))
    F = hedging.simulate_forward_paths(100.0, 0.2, 42 / 252, 294, z)
    assert abs(F[:, -1].mean() / 100.0 - 1) < 0.004