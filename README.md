# worldcup-2026-pricing-engine

Quantitative pre-game probability model for the 2026 FIFA World Cup group stage and knockout rounds. Targets Kalshi and Polymarket prediction markets (moneyline + over/under).

Built as independent research; framework parallels quant finance workflows — market devigging mirrors bond spread normalization (stripping bid-ask overround to recover true implied probabilities), and live forward-test discipline mirrors mark-to-market validation of pricing models.

---

## 1. Model Overview

Factor-based scoring system converting team-level inputs into fair-value win/draw/loss probabilities and expected goal totals.

- **v0.2** (production): four team-quality differentials → sigmoid → win/draw/loss probabilities
- **v0.3** (experimental): six additional situational factors (climate, altitude, venue, host, tactical style); built but excluded from production pending calibration
- **O/U** (in progress): Poisson-based totals model using xG-derived expected goals

Match outcomes are signaled by comparing model probabilities to devigged Kalshi market-implied probabilities; positive `model − market` gaps generate STRONG PLAY / PLAY / WATCH signals with explicit risk controls for known model weaknesses.

Full methodology in [`methodology.md`](./methodology.md).

---

## 2. Factor Architecture

### Production (v0.2)
| Factor | Signal | Weight | Source |
|--------|--------|--------|--------|
| F1 | Team strength differential (`elo_diff`) | 0.06 | Opta Power Ratings WC2026 |
| F2 | Goal differential, last 5 matches | 0.15 | Kaggle martj42 |
| F3 | xG differential (per 90, team-aggregated) | 0.35 | Footystats regional qualifier data |
| F7 | Form points, last 5 (W=3, D=1, L=0) | 0.08 | Kaggle martj42 |

```
raw_score     = (elo_diff * 0.06) + (gd_last5_diff * 0.15)
              + (xg_diff_diff * 0.35) + (form_diff * 0.08)

home_strength = 1 / (1 + EXP(-raw_score))
```

Draw probability is computed separately from matchup closeness:
```
draw_prob = MAX(0.18, MIN(0.35, 0.30 - ABS(elo_diff) * 0.003))
```

Final probabilities:
```
home_win_prob = (1 - draw_prob) * home_strength
away_win_prob = (1 - draw_prob) * (1 - home_strength)
```
Sums to 100% by construction.

### Roadmap (v0.3 experimental and beyond)
| Factor | Signal | Status |
|--------|--------|--------|
| F4 | Shots on target pressure | Excluded v0.2 (collinear with F3 xG) |
| F5 | H2H record, recency-weighted | Not implemented |
| F6 | Squad depth / injury load | Not implemented |
| F8 | Weather/climate mismatch | v0.3 experimental |
| F9 | Travel fatigue + altitude | v0.3 experimental |
| F10 | Tactical matchup | v0.3 experimental |

Factor weights will be calibrated via logistic regression once a 20+ match forward-tested sample exists.

---

## 3. Market Pricing and Devigging

Raw Kalshi YES contract prices for home/draw/away typically sum to 102–106¢ due to bid-ask spread and platform fee. They are normalized proportionally:

```
market_home = kalshi_home_raw / (kalshi_home_raw + kalshi_draw_raw + kalshi_away_raw)
```

(Same construction for `market_draw`, `market_away`, and O/U contracts.) Devigged probabilities sum to exactly 100%.

**Worked example (Match 1, Mexico vs South Africa):**
- Raw Kalshi: 70 / 21 / 12 (sum = 103¢, 3¢ overround)
- Devigged: 67.96% / 20.39% / 11.65% (sum = 100.00%)
- Model v0.2: 59.35% / 25.53% / 15.12%
- Edge on Draw: +5.14pp → WATCH signal

---

## 4. Signal Generation

```
edge_outcome = model_prob - market_prob
best_edge    = MAX(edge_home, edge_draw, edge_away)
best_value   = outcome corresponding to best_edge
```

| Signal | Condition |
|--------|-----------|
| STRONG PLAY | `best_edge ≥ 10%` and not in REVIEW |
| PLAY | `best_edge ≥ 6%` and not in REVIEW |
| WATCH | `best_edge ≥ 3%` |
| PASS | `best_edge < 3%` |
| REVIEW | `CHECK INPUTS` OR `BLOCK DRAW` filter triggered |

Signal hierarchy: **REVIEW override fires first**, then STRONG PLAY → PLAY → WATCH → PASS.

`best_value` (highest-edge outcome) and `model_pick` (most likely outcome) are tracked separately; they often differ.

---

## 5. Risk Controls

### CHECK INPUTS
```
review_flag = "CHECK INPUTS" if best_edge >= 15%
```
A 15%+ model-market gap usually indicates a stale Kalshi price, a bad model input, or (rarely) a real disagreement. Forces manual review before action.

### BLOCK DRAW
```
draw_play_filter = "BLOCK DRAW" if (
    best_value     = "Draw" AND
    market_draw    < 15%    AND
    ABS(raw_score) > 1.5
)
```
Addresses systematic over-flagging of draws as STRONG PLAY in heavy-favorite matchups (Germany, Spain, Brazil, France, Portugal vs minnows), where the heuristic draw floor exceeds reasonable market draw probability. Blocked rows are converted to REVIEW; probabilities are not modified. Balanced-matchup draws are unaffected.

---

## 6. Over/Under Model

Separate engine in `ou_model` tab. Expected goals are derived from team-level xG, total goals follow a Poisson distribution:

```
home_exp_goals  = (home_xg_for + away_xg_against) / 2
away_exp_goals  = (away_xg_for + home_xg_against) / 2
total_exp_goals = home_exp_goals + away_exp_goals

P(under 2.5)    = Poisson(0; total_exp_goals)
                + Poisson(1; total_exp_goals)
                + Poisson(2; total_exp_goals)

P(over 2.5)     = 1 - P(under 2.5)
```

O/U markets are devigged separately from moneyline.

---

## 7. Data Sources

- **Opta Power Rankings** — team strength anchor (`elo_diff`)
- **Kaggle martj42** international results 1872–present — form, recent GD
- **Footystats regional qualifier data** — xG per 90 by team (UEFA, CONMEBOL, CAF, AFC, CONCACAF, Gold Cup for hosts)
- **Kalshi** — moneyline and O/U contract prices (devigged)
- **Polymarket** — secondary market reference

---

## 8. Backtesting and Forward Testing

WC2022 calibration is in progress (`notebooks/wc2022_backtest.ipynb`). Limited to prediction-quality testing only — historical Kalshi prices are not available, so market-edge backtesting is not claimed.

**Primary validation is live forward-testing from June 11, 2026.** Model outputs are frozen at T-1hr before each match (stored in `*_FROZEN_<date>` tabs) and tracked against realized outcomes for accuracy, calibration, and CLV (closing line value).

---

## 9. Documented Limitations

Full list in [`methodology.md`](./methodology.md#14-documented-limitations). Headline items:

- Hand-weighted scorecard model — weights not optimized; logistic regression calibration deferred until 20+ match sample exists
- Regional xG heterogeneity — qualifier strengths not normalized across confederations
- Goal differential not opponent-adjusted (Norway-type schedule strength bias)
- Draw probability is heuristic — Poisson scoreline replacement is a v1.1 candidate
- New Zealand uses a goals-based fallback (no xG source)

---

## 10. File Structure

```
worldcup-2026-pricing-engine/
├── README.md
├── methodology.md
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

## 11. Recruiting Context

Project demonstrates quant-finance-relevant skills:

- **Factor modeling** with explicit collinearity control (F4 excluded for redundancy with F3)
- **Market microstructure** — proportional devigging applied consistently to moneyline and totals markets
- **Risk controls** — CHECK INPUTS and BLOCK DRAW filters address known model failure modes with transparent rules
- **Validation discipline** — frozen pre-match predictions, forward-tested with no lookahead, tracked with CLV
- **Documentation** — full methodology in `methodology.md`; design decisions and limitations logged transparently

Planned v1.1+ additions: logistic regression weight optimization on accumulated forward-test sample, Poisson-based draw replacement, regional xG normalization, v0.3 promotion after situational factor calibration.

---

## 12. Performance Tracking

Live forward-test results for WC2026:

[Live Results Sheet](https://docs.google.com/spreadsheets/d/1yc9avlxl9Q6yhSY-L9pOHyBw9OTRa8YHXEjiLBR4oBg/edit?usp=sharing) | [Model Outputs CSV](./data/model_output_FROZEN.csv)

Columns tracked: match | model probability (frozen T-1hr) | market probability (frozen T-1hr) | edge | signal | outcome | P&L (1u flat) | CLV

*Updated after each match day.*
