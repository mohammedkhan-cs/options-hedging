"""Delta-hedging simulation. Sell one at-the-money call at the implied vol, hedge it with forwards, and
measure the profit or loss when the forward's realized volatility differs from the implied volatility.

Model (DECISIONS.md Section 3): the forward follows driftless geometric Brownian motion with constant vol,
interest rate zero (discount factor 1), 294 steps (7 per trading day) over 42 trading days. The hedge ratio is
the Black-76 delta at the IMPLIED vol, reset every m steps. All frequencies and cost levels use the same random
numbers, so differences between them are not sampling noise.

P&L of the seller = premium + hedge gains - option payoff - trading costs, where the hedge holds Delta forwards
and gains Delta * (change in F) over each interval; costs are cost_bps of the notional traded at every rehedge,
including the first trade and the unwind at expiry."""
import argparse
import hashlib
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import config, pricing


def simulate_forward_paths(F0, sigma, T, n_steps, z):
    """Driftless GBM: F_{t+dt} = F_t * exp(-0.5 sigma^2 dt + sigma sqrt(dt) z). z has shape (paths, n_steps)."""
    dt = T / n_steps
    logF = np.cumsum(-0.5 * sigma ** 2 * dt + sigma * np.sqrt(dt) * z, axis=1)
    return F0 * np.exp(np.concatenate([np.zeros((z.shape[0], 1)), logF], axis=1))


def hedged_pnl(F, K, T, sigma_imp, every_steps, cost_bps=0.0, df=1.0):
    """Seller's P&L per path. Returns (pnl, premium, total_costs, n_rehedges)."""
    n = F.shape[1] - 1
    dt = T / n
    premium = float(pricing.price("call", F[0, 0], K, T, sigma_imp, df))
    idx = np.arange(0, n, every_steps)                      # steps at which the hedge is reset
    tau = T - idx * dt                                      # time left at each reset
    D = pricing.delta("call", F[:, idx], K, tau[None, :], sigma_imp, df)   # (paths, resets)
    nxt = np.append(idx[1:], n)
    gains = (D * (F[:, nxt] - F[:, idx])).sum(axis=1)
    c = cost_bps / 1e4
    trades = np.abs(np.diff(np.concatenate([np.zeros((F.shape[0], 1)), D], axis=1), axis=1))
    costs = c * (trades * F[:, idx]).sum(axis=1) + c * np.abs(D[:, -1]) * F[:, -1]      # last term: unwind at expiry
    payoff = np.maximum(F[:, -1] - K, 0.0)
    return premium + gains - payoff - costs, premium, costs, len(idx)


def run_grid(F0, sigma_imp, n_paths=None, seed=None, ratios=None, steps_per_day=None, rehedge_days=None, costs=None):
    n_paths = n_paths or config.N_PATHS
    ratios = ratios or config.VOL_RATIOS
    spd = steps_per_day or config.STEPS_PER_DAY
    rehedge_days = rehedge_days or config.REHEDGE_EVERY_DAYS
    costs = config.COST_BPS if costs is None else costs
    n_steps = config.OPTION_TRADING_DAYS * spd
    T = config.OPTION_TRADING_DAYS / config.TRADING_DAYS_PER_YEAR
    rng = np.random.default_rng(config.RANDOM_SEED if seed is None else seed)
    z = rng.standard_normal((n_paths, n_steps))
    K = F0
    p_imp = float(pricing.price("call", F0, K, T, sigma_imp))
    rows = []
    for ratio in ratios:
        F = simulate_forward_paths(F0, ratio * sigma_imp, T, n_steps, z)
        theory = (p_imp - float(pricing.price("call", F0, K, T, ratio * sigma_imp))) / p_imp
        for days in rehedge_days:
            m = int(round(days * spd))
            for cb in costs:
                pnl, prem, cost, n_re = hedged_pnl(F, K, T, sigma_imp, m, cb)
                rel = pnl / prem
                rows.append({"ratio": ratio, "rehedge_every_days": days, "n_rehedges": n_re, "cost_bps": cb,
                             "mean_pct": 100 * rel.mean(), "se_pct": 100 * rel.std(ddof=1) / np.sqrt(n_paths),
                             "std_pct": 100 * rel.std(ddof=1), "p05_pct": 100 * np.percentile(rel, 5),
                             "avg_cost_pct": 100 * (cost / prem).mean(),
                             "theory_mean_pct_no_cost": 100 * theory})
    return pd.DataFrame(rows), p_imp, T


def check_gate():
    p = config.ROOT / "PREDICTIONS.md"
    if not p.exists() or "[SET THIS" in p.read_text(encoding="utf-8"):
        sys.exit("STOP: PREDICTIONS.md must be saved (no [SET THIS] placeholder) before the simulation runs.")
    print(f"PREDICTIONS.md SHA-256: {hashlib.sha256(p.read_bytes()).hexdigest()}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", type=int, default=config.N_PATHS)
    args = ap.parse_args()
    check_gate()
    summ = pd.read_csv(config.OUT_TABLES / "chain_summary.csv").iloc[0]
    F0, sig = float(summ["forward"]), float(summ["atm_iv"])
    res, prem, T = run_grid(F0, sig, n_paths=args.paths)
    print(f"Inputs from the chain: forward {F0:,.2f}, ATM implied vol {sig*100:.2f}%. Simulated option: ATM call, {config.OPTION_TRADING_DAYS} "
          f"trading days (T = {T:.4f} y), premium {prem:,.2f} index points ({100*prem/F0:.2f}% of the forward). Paths {args.paths:,}, seed {config.RANDOM_SEED}.")
    pd.set_option("display.width", 220, "display.float_format", lambda v: f"{v:,.2f}")

    a = res[res.cost_bps == 0]
    print("\nA. MEAN hedged P&L, % of premium (no costs). 'theory' = (price at implied vol - price at realized vol) / premium:")
    mean_t = a.pivot(index="n_rehedges", columns="ratio", values="mean_pct")
    mean_t.loc["theory"] = a.drop_duplicates("ratio").set_index("ratio")["theory_mean_pct_no_cost"]
    print(mean_t.to_string())
    se_t = a.pivot(index="n_rehedges", columns="ratio", values="se_pct")
    print("   Monte Carlo standard error of each mean (same layout):\n" + se_t.to_string())
    off = (a["mean_pct"] - a["theory_mean_pct_no_cost"]).abs() / a["se_pct"]
    print(f"   Largest gap between simulated and theoretical mean: {off.max():.1f} standard errors")

    print("\nB. SPREAD (standard deviation) of hedged P&L, % of premium (no costs):")
    print(a.pivot(index="n_rehedges", columns="ratio", values="std_pct").to_string())
    base = a[a.ratio == 1.0].set_index("n_rehedges")
    print("\n   At realized = implied: std x sqrt(rehedges), which is roughly constant if error ~ 1/sqrt(N):")
    print((base["std_pct"] * np.sqrt(base.index.to_numpy())).to_string())

    c = res[res.ratio == 1.0]
    print("\nC. TRADING COSTS at realized = implied: mean P&L, % of premium (rows = rehedges, columns = cost in bp per trade):")
    print(c.pivot(index="n_rehedges", columns="cost_bps", values="mean_pct").to_string())
    print("   Average total cost, % of premium:")
    print(c.pivot(index="n_rehedges", columns="cost_bps", values="avg_cost_pct").to_string())

    d = a[a.ratio == 1.0].set_index("n_rehedges")["std_pct"]
    print(f"\nPREDICTION CHECKS: daily hedging (42 rehedges) std {d.loc[42]:.2f}% of premium; 7 times a day (294) std {d.loc[294]:.2f}%; "
          f"ratio {d.loc[42]/d.loc[294]:.2f}. Mean P&L at 1.2x: {a[(a.ratio==1.2)&(a.n_rehedges==294)]['mean_pct'].iloc[0]:+.1f}%; "
          f"at 0.8x: {a[(a.ratio==0.8)&(a.n_rehedges==294)]['mean_pct'].iloc[0]:+.1f}%; at 1.0x: {a[(a.ratio==1.0)&(a.n_rehedges==294)]['mean_pct'].iloc[0]:+.2f}%")

    config.OUT_TABLES.mkdir(parents=True, exist_ok=True)
    res.to_csv(config.OUT_TABLES / "hedging_results.csv", index=False)
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    n = base.index.to_numpy()
    ax[0].loglog(n, base["std_pct"], "o-", label="simulated (realized = implied)")
    ax[0].loglog(n, base["std_pct"].iloc[-1] * np.sqrt(n[-1] / n), "--", color="grey", label="1/sqrt(N) reference")
    ax[0].set_xlabel("number of rehedges N"); ax[0].set_ylabel("std of hedged P&L (% of premium)"); ax[0].legend()
    top = a[a.n_rehedges == a.n_rehedges.max()].sort_values("ratio")
    ax[1].errorbar(top["ratio"], top["mean_pct"], yerr=1.96 * top["se_pct"], fmt="o", label="simulated mean (95% range)")
    ax[1].plot(top["ratio"], top["theory_mean_pct_no_cost"], "--", color="grey", label="price(implied) - price(realized)")
    ax[1].axhline(0, color="black", lw=0.5); ax[1].set_xlabel("realized vol / implied vol"); ax[1].set_ylabel("mean hedged P&L (% of premium)"); ax[1].legend()
    config.OUT_FIGURES.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(config.OUT_FIGURES / "hedging_results.png", dpi=130); plt.close(fig)
    print("\nWrote outputs/tables/hedging_results.csv and outputs/figures/hedging_results.png")


if __name__ == "__main__":
    main()