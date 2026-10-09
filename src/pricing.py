"""Black-76 pricing and Greeks for European options on a forward price F.

    call = df * (F*N(d1) - K*N(d2)),   put = df * (K*N(-d2) - F*N(-d1))
    d1 = (ln(F/K) + 0.5*sigma^2*T) / (sigma*sqrt(T)),   d2 = d1 - sigma*sqrt(T)

F is the forward (or futures) price for the option's expiry, T is in years, sigma is annualized volatility,
and df is the discount factor to expiry (exp(-r*T)). For a European index option this is the same model as
Black-Scholes with a dividend yield, written in terms of the forward so no dividend or rate has to be guessed.
Greeks are derivatives of the option price with respect to F, F (twice), sigma, and calendar time."""
import numpy as np
from scipy.stats import norm

KINDS = ("call", "put")


def _check(kind, F, K, T, sigma):
    if kind not in KINDS:
        raise ValueError(f"kind must be 'call' or 'put', got {kind!r}")
    if np.any(np.asarray(F) <= 0) or np.any(np.asarray(K) <= 0):
        raise ValueError("F and K must be positive")
    if np.any(np.asarray(T) < 0) or np.any(np.asarray(sigma) < 0):
        raise ValueError("T and sigma must be non-negative")


def _d1_d2(F, K, T, sigma):
    v = sigma * np.sqrt(T)
    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(F / K) + 0.5 * v ** 2) / v
    return d1, d1 - v, v


def intrinsic(kind, F, K, df=1.0):
    F, K = np.asarray(F, float), np.asarray(K, float)
    return df * (np.maximum(F - K, 0.0) if kind == "call" else np.maximum(K - F, 0.0))


def price(kind, F, K, T, sigma, df=1.0):
    F, K, T, sigma = (np.asarray(x, float) for x in (F, K, T, sigma))
    _check(kind, F, K, T, sigma)
    d1, d2, v = _d1_d2(F, K, T, sigma)
    if kind == "call":
        p = df * (F * norm.cdf(d1) - K * norm.cdf(d2))
    else:
        p = df * (K * norm.cdf(-d2) - F * norm.cdf(-d1))
    return np.where(v > 0, p, intrinsic(kind, F, K, df))


def delta(kind, F, K, T, sigma, df=1.0):
    """d price / d F. The number of forwards (or futures) that hedges one option."""
    F, K, T, sigma = (np.asarray(x, float) for x in (F, K, T, sigma))
    _check(kind, F, K, T, sigma)
    d1, _, v = _d1_d2(F, K, T, sigma)
    d = df * norm.cdf(d1) if kind == "call" else df * (norm.cdf(d1) - 1.0)
    at_expiry = df * (F > K) if kind == "call" else -df * (F < K)
    return np.where(v > 0, d, at_expiry)


def gamma(kind, F, K, T, sigma, df=1.0):
    """d^2 price / d F^2. Same for calls and puts."""
    F, K, T, sigma = (np.asarray(x, float) for x in (F, K, T, sigma))
    _check(kind, F, K, T, sigma)
    d1, _, v = _d1_d2(F, K, T, sigma)
    with np.errstate(divide="ignore", invalid="ignore"):
        g = df * norm.pdf(d1) / (F * v)
    return np.where(v > 0, g, 0.0)


def vega(kind, F, K, T, sigma, df=1.0):
    """d price / d sigma (per 1.00 of volatility, not per percentage point). Same for calls and puts."""
    F, K, T, sigma = (np.asarray(x, float) for x in (F, K, T, sigma))
    _check(kind, F, K, T, sigma)
    d1, _, v = _d1_d2(F, K, T, sigma)
    return np.where(v > 0, df * F * norm.pdf(d1) * np.sqrt(T), 0.0)


def theta(kind, F, K, T, sigma, r):
    """d price / d calendar time (price change per year as T shrinks), with the rate r held fixed so df = exp(-r*T)."""
    F, K, T, sigma = (np.asarray(x, float) for x in (F, K, T, sigma))
    _check(kind, F, K, T, sigma)
    df = np.exp(-r * T)
    d1, _, v = _d1_d2(F, K, T, sigma)
    p = price(kind, F, K, T, sigma, df)
    with np.errstate(divide="ignore", invalid="ignore"):
        decay = df * F * norm.pdf(d1) * sigma / (2.0 * np.sqrt(T))
    return np.where(v > 0, r * p - decay, 0.0)