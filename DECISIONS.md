# DECISIONS.md (options hedging project)

Written on: 10/7/2026 BEFORE any option data was pulled or any simulation was run.
Nothing below may be changed after results are seen. 
## 1. Question and hypotheses
Does the profit or loss of a delta-hedged short option track the gap between the volatility it was sold at (implied) and the volatility the index actually realizes, and how do rehedging frequency and trading costs change that?
- Relationship 1: average hedged P&L is approximately the option premium x (implied vol - realized vol) / implied vol.
- Relationship 2: the spread of hedged P&L shrinks in proportion to 1 / sqrt(number of rehedges).
- Descriptive, no test attached: the shape (skew) of the SPX implied-volatility smile on one real option-chain snapshot.

## 2. decisions
- Underlying: the S&P 500 index (Yahoo symbol ^SPX), European-style options, so Black-Scholes matches the contract.
- Expiry: the listed expiry closest to 60 calendar days from the snapshot date (about 42 trading days).
- Fallback, decided before any data: if fewer than 15 usable strikes remain after cleaning, switch to SPY and log it. No other reason to switch.

## 3. Implement decisions 
- Model: Black-76 (forward-price form of Black-Scholes). The forward price and discount factor are backed out of the chain by put-call parity, so no dividend yield or interest rate is guessed.
- Cleaning rules for the chain, fixed now: keep 0.80 <= strike/forward <= 1.10; drop quotes with bid = 0, ask < bid, or (ask - bid)/mid > 50%; use the mid price; use out-of-the-money options only (puts below the forward, calls above) to compute implied volatility.
- Simulation: the forward price follows driftless geometric Brownian motion with constant volatility; 10,000 paths; random seed 0; 294 steps (7 per trading day) over 42 trading days (T = 42/252 years); interest rate set to 0 in the simulation (discount factor 1).
- The option sold: one at-the-money (strike = starting forward) call, priced at the real chain's at-the-money implied vol, hedged with forwards.
- Realized volatility cases: 0.8x, 1.0x and 1.2x the implied vol. Rehedge every 21, 7, 3 and 1 trading days and 7 times a day (2, 6, 14, 42 and 294 rehedges). Transaction costs 0, 1 and 2 basis points of notional traded per hedge. All frequencies run on the same paths.

## 4. Known limitations (declared in advance)
- Constant-volatility geometric Brownian motion ignores the smile, jumps, and changing volatility. In continuous time a delta hedge is perfect only inside this model.
- One chain snapshot from Yahoo (delayed, noisy). The smile is one day, not a pattern.
- The simulation sets interest rates to zero.
- Costs apply to hedge trades only, not to the option itself.
- The hedge error results come from a model I chose, not from market data.
