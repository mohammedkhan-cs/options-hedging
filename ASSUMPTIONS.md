# ASSUMPTIONS (options hedging)

- Environment: Python 3.9.6; numpy 1.26.4, scipy 1.13.1, pandas 2.2.3, matplotlib 3.9.4, yfinance 1.2.0, pytest. 27 tests passed on 10/08/2026.
- DECISIONS.md SHA-256 44a0c68d8f5d01b62621f556cacbbf662d59799110b80abe6baf0cafb152429c; PREDICTIONS.md SHA-256 at the chain pull and at the simulation 3253562cd9d32a898edfd451a9dbcecace11170857a1ee37c858ab790ddc4b1e.  
- Chain: ^SPX, snapshot 2026-10-08 16:39 UTC (12:39 ET), expiry 2026-11-30 (53 calendar days; the listed expiry closest to 60). Raw files cached unedited in data/raw/chain_*. Yahoo data is not redistributed in the repo.
- Cleaning (pre-set): bid > 0, ask >= bid, relative spread <= 50%, mid prices, OTM options only, 0.80-1.10 x forward. Dropped: calls 13 of 314, puts 4 of 365.
- Forward and discount factor from put-call parity on strikes within +/-10% of spot (166 strikes): forward 7,823.09, discount factor 0.99358, R-squared 0.999824, largest residual 24.1. Robustness over windows 2%-15%: forward 7,823.09-7,823.91, ATM vol 12.775-12.859%, skew 8.015-8.073 points.
- Implied vol: Black-76, Brent solver; 390 options, 0 failures; T = calendar days / 365 (time of day ignored, about 0.3% effect). ATM vol 12.79% (linear interpolation at K = forward); 0.90F vol 20.84%; skew +8.05 points.
- Simulation uses 42 trading days as fixed in DECISIONS.md, not the chain's 53 calendar days (about 37 trading days). Only the chain's ATM vol is used. Rate set to 0. Costs of 1 and 2 bp are assumptions. 10,000 paths, seed 0.
- Test log: one of my tests had a wrong bound (asserted a ratio above 1.8 where theory says 1.73) and an earlier finite-difference check used too large a step; both were fixed in the tests and the code was unchanged.
- Results: see outputs/tables/chain_summary.csv and hedging_results.csv. Predictions scored in PREDICTIONS.md section 3.