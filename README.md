# worldcup-2026-pricing-engine

Quantitative pre-game probability model for 2026 FIFA World Cup group stage and knockout rounds. Targets Polymarket and Kalshi prediction markets (moneyline + over/under only).

Built as independent research -- framework parallels quant finance workflows: devigging mirrors bond spread normalization, Monte Carlo sensitivity mirrors LBO scenario tables.

---

## 1. Model Overview

10-factor scoring system converting team stats into fair-value win/draw/loss probabilities and expected goal totals. Final output blends model (45%) with market (55%) to account for WC liquidity dynamics.

## 2. Factor Architecture

| Factor | Signal | Cap |
|--------|--------|-----|
| F1 | FIFA/Elo rank gap | ±25 |
| F2 | Goals scored/conceded differential | ±18 |
| F3 | xG differential | ±16 |
| F4 | Shots on target pressure | ±14 |
| F5 | Head-to-head record (recency-weighted) | ±8 |
| F6 | Squad depth / injury load | ±14 |
| F7 | Form momentum (last 5) | ±10 |
| F8 | Weather/climate mismatch | ±8 |
| F9 | Travel fatigue + altitude stress | ±6 |
| F10 | Tactical matchup | ±5 |

## 3. Methodology

- **Devigging:** normalize raw market prices to true implied probabilities (step 1 before all analysis)
- **Poisson framework:** lambdas derived from xG-weighted inputs; draw probability computed via exact tied-scoreline grid
- **Blend:** 45% model / 55% market (locked until 20+ match sample exists)
- **Thresholds:** ML play >= 4% blended gap; O/U play requires >= 4% gap AND projection >= 0.35 goals clear of line

## 4. Data Sources

- Opta Power Rankings (WC2026 live strength ratings)
- Elo Ratings -- eloratings.net historical CSVs
- xG / shot data -- FBref via pandas read_html
- H2H history -- Kaggle martj42/international-football-results
- Recent form (<6 months) -- API-Football via RapidAPI free tier

## 5. Backtesting

WC2022 calibration: 4/5 correct primary calls. Single miss (Japan/Spain) assessed as variance given ~8% true probability. Each match produced locked calibration rules now embedded in model.

Full backtest notebook: notebooks/wc2022_backtest.ipynb (in progress)

## 6. Key Calibration Rules

Derived from WC2022 backtesting:

- Creative hub missing vs. low block: -0.4 to expected total
- Must-win + compromised defensive pivot: +0.25 to expected total
- Weak opponent discount: 12% on attacking inputs when 3+ of last 5 vs rank 55+
- Low-block underdog premium: +2 pts raw when market implied sits 8-18%

## 7. File Structure

    worldcup-2026-pricing-engine/
    |-- WC Team Data Collection - team_stats.csv
    |-- WC Team Data Collection - model_outputs_groupstage.csv
    |-- WC Team Data Collection - ou_model.csv
    |-- WC Team Data Collection - methodology_notes.csv
    |-- notebooks/
    |   |-- wc2022_backtest.ipynb       (in progress)
    |-- README.md

## 8. Recruiting Context

This project demonstrates quant finance-relevant skills:

- Factor modeling with collinearity controls
- Probability calibration (Platt scaling roadmap)
- Market microstructure awareness (devigging, liquidity-adjusted blending)
- Backtesting discipline (no lookahead, honest miss attribution)

Planned additions: logistic regression weight optimizer, XGBoost ensemble, dynamic Elo.

## 9. Performance Tracking

Live forward-test results for WC2026 group stage:

[Live Results Sheet](YOUR_GOOGLE_SHEET_LINK_HERE) | [Model Outputs CSV](WC%20Team%20Data%20Collection%20-%20model_outputs_groupstage.csv)

Columns tracked: match | predicted prob | market prob | edge | play/fade/pass | outcome | P&L (1u flat)

*Updated after each match day.*
