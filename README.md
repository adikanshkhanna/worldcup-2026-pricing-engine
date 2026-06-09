# worldcup-2026-pricing-engine

Quantitative pre-game probability model for the 2026 FIFA World Cup group stage and knockout rounds. Targets Kalshi and Polymarket prediction markets (moneyline + over/under).

Built as independent research; framework parallels quant finance workflows — market devigging mirrors bond spread normalization (stripping bid-ask overround to recover true implied probabilities), and live forward-test discipline mirrors mark-to-market validation of pricing models.

---

## 1. Model Overview

Factor-based scoring system converting team-level inputs into fair-value win/draw/loss probabilities and expected goal totals. Production v1.0 ships with four factors; six additional factors are built but excluded from production pending calibration (see §2 Roadmap). Final output blends model probability (45%) with devigged market probability (55%) to account for low-liquidity dynamics in early World Cup contracts.

---

## 2. Factor Architecture

### Production (v1.0 frozen)
| Factor | Signal | Weight | Source |
|--------|--------|--------|--------|
| F1 | Opta Power Rating differential | 0.06 | Opta WC2026 |
| F2 | Goal differential, last 5 matches | 0.15 | Kaggle martj42 |
| F3 | xG differential (per 90, team-aggregated) | 0.35 | Footystats regional qualifier data |
| F7 | Form points, last 5 (W=3, D=1, L=0) | 0.08 | Kaggle martj42 |

Raw score = weighted sum of differentials. Home strength derived via sigmoid; probabilities split into home/draw/away and renormalized to sum to 100%.

### Roadmap (v1.1+ experimental)
| Factor | Signal | Status |
|--------|--------|--------|
| F4 | Shots on target pressure | Excluded v1.0 (collinear with xG; documented in methodology_notes) |
| F5 | H2H record, recency-weighted | Not implemented |
| F6 | Squad depth / injury load | Not implemented |
| F8 | Weather/climate mismatch | Built, excluded from frozen v1.0 |
| F9 | Travel fatigue + altitude | Built, excluded from frozen v1.0 |
| F10 | Tactical matchup | Built, excluded from frozen v1.0 |

Factor weights will be calibrated via logistic regression once a 20+ match sample exists.

---

## 3. Methodology

**Devigging.** Raw Kalshi YES contract prices for home/draw/away typically sum to 102–106 cents due to bid-ask spread and platform fee. Prices are normalized proportionally:

```
p_outcome = raw_outcome / (raw_home + raw_draw + raw_away)
```

This is the first step in all analysis; comparing model probabilities to raw vigged prices would systematically understate edges. The same proportional devig is applied to O/U contracts.

*Example (Match 1, Mexico vs South Africa):*
- Raw Kalshi: 70 / 21 / 12 (sum = 103¢, 3¢ overround)
- Devigged: 67.96% / 20.39% / 11.65% (sum = 100.00%)
- Model: 59.35% / 25.53% / 15.12%
- Edge on draw: +5.14 points → WATCH signal

**Match outcome.** Sigmoid mapping of weighted factor differentials produces home_strength; probabilities split into home/draw/away and renormalized to sum to 100%.

**Over/Under.** Expected total goals derived from team-level xG (per-90 for and against, combined into a match-level projection). Compared against devigged Kalshi O/U contract prices to identify mispricing.

**Blend.** Final output = 0.45 × model probability + 0.55 × devigged market probability. The 45/55 weighting is intentionally market-leaning until validation builds; will be re-calibrated after a 20-match sample.

**Signal thresholds.**
- Moneyline: blended-vs-market gap ≥ 4 percentage points
- O/U: blended-vs-market gap ≥ 4 pp AND model projection ≥ 0.35 goals clear of the line

**Risk filters.** Draw bets are blocked when one team has ≥70% model probability AND draw edge ≥8%, addressing known sigmoid-based overestimation of draw probability in heavy-mismatch matchups. Permanent fix is draw-specific calibration, planned for v1.1.

---

## 4. Data Sources

- **Opta Power Rankings** — team strength anchor (WC2026 release)
- **Kaggle martj42** international results 1872–present — form, recent goal differential
- **Footystats regional qualifier data** — xG per 90 by team (UEFA, CONMEBOL, CAF, AFC, CONCACAF, Gold Cup for CONCACAF hosts)
- **Kalshi** — moneyline and O/U contract prices (devigged)
- **Polymarket** — secondary market reference

---

## 5. Backtesting

WC2022 calibration is in progress (`notebooks/wc2022_backtest.ipynb`).

Primary validation is live forward-test starting June 11, 2026 — model outputs are frozen T-1hr before each match and tracked against realized outcomes for accuracy, calibration, and CLV (closing line value).

---

## 6. Documented Limitations

Logged in `methodology_notes.csv`; the following are candidates for v1.1:

- **Form weight may over-weight recent performance** vs. underlying team quality; some near-toss-up matchups are sensitive to this weight.
- **Sigmoid bias on draws** — model overestimates draw probability when one team is heavily favored; addressed in v1.0 via BLOCK DRAW filter (see §3).
- **Regional xG heterogeneity** — qualifier strengths not normalized across confederations (e.g., a Norway +4.4 12-month GD reflects weak UEFA Group opposition more than absolute quality).
- **New Zealand** — no available xG source; team uses goals-based fallback for F3.
- **Pre-WC friendlies** — FIFA Series, Kirin Cup, King's Cup occasionally slip past the friendly filter in form/GD calculations.

---

## 7. File Structure

```
worldcup-2026-pricing-engine/
├── README.md
├── LICENSE
├── data/
│   ├── team_stats.csv
│   ├── model_inputs_v02_FROZEN.csv
│   ├── model_output_FROZEN.csv
│   ├── ou_model_v02_FROZEN.csv
│   └── methodology_notes.csv
└── notebooks/
    └── wc2022_backtest.ipynb   (in progress)
```

---

## 8. Recruiting Context

Project demonstrates quant-finance-relevant skills:

- **Factor modeling** with explicit collinearity control (F4 excluded for redundancy with F3)
- **Market microstructure** — proportional devigging applied consistently to moneyline and totals markets
- **Probability calibration** — separation of production vs. experimental factors; draw filter addresses identified model bias
- **Validation discipline** — frozen pre-match predictions, forward-tested with no lookahead, tracked with CLV
- **Documentation** — methodology_notes log of design decisions and known limitations

Planned v1.1+ additions: logistic regression weight optimization on backtest sample, draw-specific calibration, regional xG normalization.

---

## 9. Performance Tracking

Live forward-test results for WC2026:

[Live Results Sheet](https://docs.google.com/spreadsheets/d/1yc9avlxl9Q6yhSY-L9pOHyBw9OTRa8YHXEjiLBR4oBg/edit?usp=sharing) | [Model Outputs CSV](./data/model_output_FROZEN.csv)

Columns tracked: match | model probability (frozen T-1hr) | market probability (frozen T-1hr) | edge | signal | outcome | P&L (1u flat) | CLV

*Updated after each match day.*
