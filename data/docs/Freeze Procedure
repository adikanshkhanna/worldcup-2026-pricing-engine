# Freeze Procedure (Pre-Match)

Executed at T-1 hour before each match. No model inputs may be
modified after the freeze for the relevant match.

## Pre-match (T-1 hour)
1. Open Kalshi; pull current raw prices for moneyline (home/draw/away)
   and O/U contracts
2. Enter raw prices into `daily_odds` tab for this match
3. Verify devig output: market_home + market_draw + market_away = 100.00%
4. Verify O/U devig: market_over + market_under = 100.00%
5. Take screenshot of `model_outputs` row for this match
6. Copy into `live_results_tracker`:
   - model_home, model_draw, model_away (frozen)
   - market_home, market_draw, market_away (frozen, devigged)
   - best_edge, best_value, signal, pick
   - timestamp of freeze
7. If placing a bet:
   - stake (units)
   - entry price (cents)
   - notional P&L at $1u if wins / if loses
8. Lock the model_inputs row (Sheets: right-click → Protect range)

## Post-match (after final whistle)
1. Enter final score in tracker
2. Compute outcome: home_win / draw / away_win
3. Mark correct (Y/N) vs pick
4. If bet was placed:
   - Realized P&L
   - CLV = Kalshi closing price - Kalshi entry price (in cents)
5. Note any model behavior observations in `methodology_notes`

## Daily wrap (end of match day)
1. Run analysis snippet on cumulative tracker data
2. Review running hit rate, calibration, and P&L
3. Commit tracker snapshot to GitHub with date stamp
