# worldcup-2026-pricing-engine

Quantitative pre-game probability model for 2026 FIFA World Cup group stage and knockout rounds. Targets Polymarket and Kalshi prediction markets (moneyline + over/under only).

Built as independent research -- framework parallels quant finance workflows: devigging mirrors bond spread normalization, *Monte Carlo sensitivity mirrors LBO scenario tables. (in progress)

---

## 1. Model Overview

10-factor scoring system converting team stats into fair-value win/draw/loss probabilities and expected goal totals. Final output blends model (45%) with market (55%) to account for WC liquidity dynamics.

## 2. Factor Architecture

### Production (v1.0 frozen)
| Factor | Signal | Weight | Source |
|--------|--------|--------|--------|
| F1 | Opta Power Rating differential | 0.06 | Opta WC2026 |
| F2 | Goal differential, last 5 matches | 0.15 | Kaggle martj42 |
| F3 | xG differential (per 90, team agg) | 0.35 | Footystats regional |
| F7 | Form points, last 5 (W=3, D=1, L=0) | 0.08 | Kaggle martj42 |

### Roadmap (v1.1+ experimental)
| Factor | Signal | Status |
|--------|--------|--------|
| F4 | Shots on target pressure | Excluded v1.0 (collinear with xG) |
| F5 | H2H record, recency-weighted | Not yet implemented |
| F6 | Squad depth / injury load | Not yet implemented |
| F8 | Weather/climate mismatch | Built, excluded from frozen v1.0 |
| F9 | Travel fatigue + altitude | Built, excluded from frozen v1.0 |
| F10 | Tactical matchup | Built, excluded from frozen v1.0 |

## 3. Methodology

- **Devigging:** normalize raw market prices to true implied probabilities (step 1 before all analysis)
- **Poisson framework:** lambdas derived from xG-weighted inputs; draw probability computed via exact tied-scoreline grid
- **Blend:** 45% model / 55% market (locked until 20+ match sample exists)
- **Thresholds:** ML play >= 4% blended gap; O/U play requires >= 4% gap AND projection >= 0.35 goals clear of line

## 4. Data Sources
- Opta Power Rankings (team strength anchor)
- Kaggle martj42 international results (form, GD, H2H)
- Footystats regional qualifier data (xG per 90 by team)
- Polymarket / Kalshi (live market prices for blending and comparison)

## 5. Backtesting
WC2022 calibration is in-progress (notebooks/wc2022_backtest.ipynb).
Production validation will be live forward-test from June 11, 2026
onward — predictions locked T-1hr before each match, tracked against
realized outcomes for accuracy and calibration.

## 6. Observed Patterns (Exploratory)
Patterns flagged during model development that may warrant
factor weights in v1.1:
- 
Status: not embedded in v1.0 production. Calibration candidates for v1.1.
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

[Live Results Sheet](https://docs.google.com/spreadsheets/d/1yc9avlxl9Q6yhSY-L9pOHyBw9OTRa8YHXEjiLBR4oBg/edit?usp=sharing) | [Model Outputs CSV](WC%20Team%20Data%20Collection%20-%20model_outputs_groupstage.csv)

Columns tracked: match | predicted prob | market prob | edge | play/fade/pass | outcome | P&L (1u flat)

*Updated after each match day.*
