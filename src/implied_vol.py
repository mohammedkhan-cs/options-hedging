"""Implied volatility: solve Black-76 price(sigma) = observed price for sigma, plus interpolation along the smile."""
import numpy as np
from scipy.optimize import brentq

from src import pricing


def implied_vol(kind, price, F, K, T, df=1.0, lo=1e-4, hi=5.0):
    """Return sigma such that the Black-76 price equals `price`, or NaN if no such sigma exists
    (price at or below intrinsic, at or above the upper bound, or outside [lo, hi])."""
    intrinsic = float(pricing.intrinsic(kind, F, K, df))
    upper = df * F if kind == "call" else df * K
    if not (intrinsic < price < upper):
        return np.nan

    def f(s):
        return float(pricing.price(kind, F, K, T, s, df)) - price

    if f(lo) > 0 or f(hi) < 0:
        return np.nan
    return float(brentq(f, lo, hi, xtol=1e-12))


def interp_iv(x, iv, target):
    """Linear interpolation of iv at x = target. NaN if the target is outside the observed range (no extrapolation)."""
    x, iv = np.asarray(x, float), np.asarray(iv, float)
    ok = np.isfinite(x) & np.isfinite(iv)
    x, iv = x[ok], iv[ok]
    if len(x) < 2 or target < x.min() or target > x.max():
        return np.nan
    order = np.argsort(x)
    return float(np.interp(target, x[order], iv[order]))