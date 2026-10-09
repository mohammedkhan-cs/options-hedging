"""Pricing and Greeks must match independent facts before any later result counts."""
import numpy as np
import pytest
from scipy.stats import norm

from src import pricing

RNG = np.random.default_rng(0)


def random_inputs(n=200):
    F = RNG.uniform(50, 150, n)
    K = F * RNG.uniform(0.7, 1.3, n)
    T = RNG.uniform(0.05, 2.0, n)
    sigma = RNG.uniform(0.05, 0.8, n)
    df = np.exp(-RNG.uniform(0.0, 0.06, n) * T)
    return F, K, T, sigma, df


def test_atm_reference_value():
    # At the money on the forward, price = df * F * (2*N(sigma*sqrt(T)/2) - 1). F=100, sigma=0.2, T=1: N(0.1) = 0.5398278
    expected = 100 * (2 * 0.5398278 - 1)           # 7.96556, worked by hand
    for kind in ("call", "put"):
        assert abs(float(pricing.price(kind, 100, 100, 1.0, 0.2)) - expected) < 1e-4
    assert abs(float(pricing.price("call", 100, 100, 1.0, 0.2)) - 100 * (2 * norm.cdf(0.1) - 1)) < 1e-10


def test_put_call_parity():
    F, K, T, s, df = random_inputs()
    c, p = pricing.price("call", F, K, T, s, df), pricing.price("put", F, K, T, s, df)
    assert np.max(np.abs((c - p) - df * (F - K))) < 1e-10


def test_prices_respect_no_arbitrage_bounds():
    F, K, T, s, df = random_inputs()
    for kind in ("call", "put"):
        p = pricing.price(kind, F, K, T, s, df)
        assert np.all(p >= pricing.intrinsic(kind, F, K, df) - 1e-12)
        assert np.all(p <= df * (F if kind == "call" else K) + 1e-12)


def test_price_rises_with_volatility_and_vega_is_positive():
    F, K, T, s, df = random_inputs()
    for kind in ("call", "put"):
        assert np.all(pricing.price(kind, F, K, T, s * 1.1, df) > pricing.price(kind, F, K, T, s, df))
        assert np.all(pricing.vega(kind, F, K, T, s, df) > 0)


@pytest.mark.parametrize("kind", ["call", "put"])
def test_greeks_match_finite_differences(kind):
    F, K, T, s, df = random_inputs()
    r = -np.log(df) / T
    h = 1e-4 * F          # small step: central-difference error shrinks with the square of the step
    d_fd = (pricing.price(kind, F + h, K, T, s, df) - pricing.price(kind, F - h, K, T, s, df)) / (2 * h)
    assert np.max(np.abs(d_fd - pricing.delta(kind, F, K, T, s, df))) < 2e-6
    g_fd = (pricing.price(kind, F + h, K, T, s, df) - 2 * pricing.price(kind, F, K, T, s, df)
            + pricing.price(kind, F - h, K, T, s, df)) / h ** 2
    assert np.max(np.abs(g_fd - pricing.gamma(kind, F, K, T, s, df)) / (1 + pricing.gamma(kind, F, K, T, s, df))) < 1e-4
    hs = 1e-5
    v_fd = (pricing.price(kind, F, K, T, s + hs, df) - pricing.price(kind, F, K, T, s - hs, df)) / (2 * hs)
    assert np.max(np.abs(v_fd - pricing.vega(kind, F, K, T, s, df))) < 1e-5
    hT = 1e-5
    p_up = pricing.price(kind, F, K, T + hT, s, np.exp(-r * (T + hT)))
    p_dn = pricing.price(kind, F, K, T - hT, s, np.exp(-r * (T - hT)))
    th_fd = -(p_up - p_dn) / (2 * hT)             # theta = -dPrice/dT with r fixed
    assert np.max(np.abs(th_fd - pricing.theta(kind, F, K, T, s, r))) < 1e-4


def test_call_and_put_delta_differ_by_the_discount_factor():
    F, K, T, s, df = random_inputs()
    assert np.max(np.abs((pricing.delta("call", F, K, T, s, df) - pricing.delta("put", F, K, T, s, df)) - df)) < 1e-12


def test_limits_at_expiry_and_zero_volatility():
    assert float(pricing.price("call", 110, 100, 0.0, 0.2)) == 10.0
    assert float(pricing.price("put", 90, 100, 0.5, 0.0)) == 10.0
    assert float(pricing.delta("call", 110, 100, 0.0, 0.2)) == 1.0
    assert float(pricing.delta("put", 110, 100, 0.0, 0.2)) == 0.0
    assert float(pricing.gamma("call", 100, 100, 0.0, 0.2)) == 0.0


def test_works_on_arrays_and_rejects_bad_input():
    out = pricing.price("call", np.array([90.0, 100, 110]), 100, 0.5, 0.2)
    assert out.shape == (3,) and np.all(np.diff(out) > 0)
    with pytest.raises(ValueError):
        pricing.price("call", -1, 100, 0.5, 0.2)
    with pytest.raises(ValueError):
        pricing.price("straddle", 100, 100, 0.5, 0.2)