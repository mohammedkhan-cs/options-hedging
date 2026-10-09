# PREDICTIONS.md (options hedging project)

Written on: 10/07/2026
Written BEFORE any option data was pulled or any simulation or regression output was viewed
Basis: predictions 1 and 2 are base-rate guesses; I had no view and did not look up current market levels. Predictions 3 and 4 are textbook approximations meant to test the simulation, not independent guesses.

## 1. About the real chain

- 60-day at-the-money implied vol of SPX
  - Prediction: 17%
  - 80% range: 13% to 25%
  - Reason: Long-run base rate. VIX has averaged about 19-20 since 1990 with the median in the high teens; I do not know current conditions.

- Implied vol of a put 10% below the forward, minus at-the-money
  - Prediction: +5 points
  - 80% range: +3 to +8
  - Reason: Index options carry a persistent crash-protection premium, so low strikes trade at higher implied vol (a downward-sloping smirk).

## 2. About the hedging simulation

- Spread (standard deviation) of hedged P&L with daily hedging, as % of the premium
  - Prediction: 12%
  - 80% range: 8% to 16%
  - Reason: About 0.7-1 x premium / sqrt(number of hedges), with 42 hedges.

- Spread of hedged P&L, hedging 7 times a day, as % of the premium
  - Prediction: 4.5%
  - 80% range: 3% to 6%
  - Reason: 294 hedges; error falls with sqrt(N), a factor of about 2.6.

- Mean hedged P&L when realized vol = 1.2 x implied
  - Prediction: -20% of premium
  - 80% range: -15% to -25%
  - Reason: Premium is roughly proportional to volatility, so P&L is about (implied - realized) / implied.

- Mean hedged P&L when realized vol = 0.8 x implied
  - Prediction: +20% of premium
  - 80% range: +15% to +25%
  - Reason: Same reason.

- Mean hedged P&L when realized vol = implied
  - Prediction: about 0
  - 80% range: within +/- 1% of premium
  - Reason: No gap between implied and realized.

## 3. After the run
- Predictions that were close, and why: the six simulation predictions (spread of 13.5% daily and 5.1% at 7 times a day, ratio 2.66; mean P&L of -19.9% at 1.2x, +20.0% at 0.8x, +0.07% at 1.0x) all landed inside my ranges. They were textbook approximations that the simulation implements, so this validates the code, not my forecasting. The simulated mean matched price(implied) - price(realized) to within 1.4 standard errors.
- Predictions that were wrong, and what my mental model missed: ATM implied vol was 12.79% against my 13-25% range, and the skew was +8.05 points against +3 to +8. I used a long-run base rate (VIX averages near 19-20) but the market on 2026-10-08 was calm and the smile steep. Both were narrow misses and stayed misses under every parity window. The expiry the rule picked was 53 days, not 60.
- Any result I doubted, and how I audited it: the put-call parity fit had a largest residual of 24 index points (R-squared 0.99982). I refit with windows from 2% to 15% around spot: the forward moved by 0.8 points, ATM implied vol by 0.08 points and skew by 0.06 points, so the result does not depend on the window. The residual grows with the window, which points to wide quotes on deep in-the-money options.
- What I would change in a second version: pull several snapshots and expiries, not one; replace constant-volatility GBM with a model with jumps or stochastic volatility; use measured SPX futures costs; hedge using realized-vol estimates from history.