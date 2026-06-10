# worldcup-2026-pricing-engine

Quantitative pre-game probability model for the 2026 FIFA World Cup group stage and knockout rounds. Targets Kalshi and Polymarket prediction markets (moneyline + over/under).

Built as independent research; framework parallels quant finance workflows — market devigging mirrors bond spread normalization (stripping bid-ask overround to recover true implied probabilities), and live forward-test discipline mirrors mark-to-market validation of pricing models.

---

## 1. Model Overview

Factor-based scoring system converting team-level inputs into fair-value win/draw/loss probabilities and expected goal totals.

| Component | Version | Architecture |
|-----------|---------|--------------|
| Moneyline | v0.2 (frozen) | 4 team-quality differentials → sigmoid → renormalized win/draw/loss |
| Over/Under | v0.3 (production) | Asymmetric xG weighting + tactical/venue/climate modifiers → Poisson |
| Moneyline v0.3 overlay | Experimental | Situational factors tracked side-by-side; not used for live signals |
| O/U v0.2 | Archived | Symmetric xG Poisson; preserved for forward-test comparison |

Match outcomes are signaled by comparing model probabilities to devigged Kalshi market-implied probabilities; positive `model − market` gaps generate STRONG PLAY / PLAY / WATCH signals with explicit risk controls for known model weaknesses.

Full methodology in [`methodology.md`](./methodology.md).

---

## 2. Moneyline Factor Architecture (v0.2)

### Production
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

### Roadmap
| Factor | Signal | Status |
|--------|--------|--------|
| F4 | Shots on target pressure | Excluded v0.2 (collinear with F3 xG) |
| F5 | H2H record, recency-weighted | Not implemented |
| F6 | Squad depth / injury load | Not implemented |
| F8 | Weather/climate mismatch | v0.3 experimental overlay (used in O/U production) |
| F9 | Travel fatigue + altitude | v0.3 experimental overlay (used in O/U production) |
| F10 | Tactical matchup | v0.3 experimental overlay (used in O/U production) |

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

Same thresholds apply to O/U via `ou_best_value` and `ou_signal`.

---

## 5. Risk Controls

### CHECK INPUTS
```
review_flag = "CHECK INPUTS" if best_edge >= 15%
```
A 15%+ model-market gap usually indicates a stale Kalshi price, a bad model input, or (rarely) a real disagreement. Forces manual review before action. Same threshold for O/U.

### BLOCK DRAW
```
draw_play_filter = "BLOCK DRAW" if (
    best_value     = "Draw" AND
    market_draw    < 15%    AND
    ABS(raw_score) > 1.5
)
```
Addresses systematic over-flagging of draws as STRONG PLAY in heavy-favorite matchups (Germany, Spain, Brazil, France, Portugal vs minnows), where the heuristic draw floor exceeds reasonable market draw probability. Blocked rows are converted to REVIEW; probabilities are not modified. Balanced-matchup draws are unaffected.

### Weak Schedule Flag (Moneyline)
```
weak_schedule_match = "FLAG" if home_team.weak_schedule_flag != away_team.weak_schedule_flag
```

Moneyline-specific transparency flag for cross-confederation matchups (e.g., UEFA vs AFC). The O/U model handles confederation normalization directly via `conf_scalar` at the input level; moneyline does not apply `conf_scalar` to avoid double-counting with F1 Opta, so this flag is the disclosure mechanism instead. Same-pool matchups (UEFA vs UEFA, AFC vs AFC) are NOT flagged — differentials remain internally valid even if baselines differ. Flag does not modify probabilities; used for forward-test bucketing.

---

## 6. Over/Under Model (v0.3 Production)

### xG inputs (asymmetric confederation adjustment)

Offensive and defensive xG use different `conf_scalar` adjustments:

```
team_xg_for_adj     = team_xg_for * team_conf_scalar
team_xg_against_adj = (team_xg_against / team_conf_scalar) * (team_elo / 100)
                    + team_xg_against * (1 - team_elo / 100)
```

xg_for is discounted (weak-pool attacks get smaller); xg_against is inflated and elo-blended (weak-pool defenses get larger when normalized to UEFA, with elo controlling how much normalization applies).

### Per-team expected goals (60/40 weighting)

```
home_exp_goals  = (home_xg_for_adj * 0.6) + (away_xg_against_adj * 0.4)
away_exp_goals  = (away_xg_for_adj * 0.6) + (home_xg_against_adj * 0.4)
total_exp_goals = home_exp_goals + away_exp_goals
```

The v0.2 O/U used a symmetric 50/50 split with no confederation scalar (preserved in `ou_model_vo2_FROZEN` for comparison).

### Multiplicative scalar adjustments

Tactical and climate modifiers are applied per-team. Venue penalty is part of the match-level situational modifier:

```
home_adj_xg = home_exp_goals * (1 + home_tactical_s) * (1 + home_climate_mod)
away_adj_xg = away_exp_goals * (1 + away_tactical_s) * (1 + away_climate_mod)

venue_penalty = IFS(
    venue_tier = "extreme",   -0.20,
    venue_tier = "high",      -0.15,
    venue_tier = "altitude",  -0.15,
    venue_tier = "moderate",  -0.08,
    venue_tier = "mild",       0,
    TRUE,                      0
)

situational_modifier      = away_tactical_s + venue_penalty
adjusted_total_exp_goals  = (home_adj_xg + away_adj_xg) * (1 + situational_modifier)
```

Climate modifier per team is a piecewise function on origin climate temperature (cold/mild/warm/hot ranges).

### Poisson probabilities

O/U lines are read from Kalshi per match — typically 2.5 but variable (1.5, 3.5, 4.5):

```
P(under L) = sum of Poisson(k; adjusted_total) for k = 0 to floor(L)
P(over L)  = 1 - P(under L)
```

O/U markets are devigged separately from moneyline.

**Architecture rationale:** O/U uses v0.3 (situational, multiplicative scalars) while moneyline uses v0.2 (team-quality differentials, sigmoid) because goal totals are more sensitive to environmental context than binary win/draw outcomes. Both architectures are forward-tested live; comparison informs whether v0.3 situational factors should be promoted to moneyline in v1.1.

---

## 7. Data Sources

- **Opta Power Rankings** — team strength anchor (`elo_diff`)
- **Kaggle martj42** international results 1872–present — form, recent GD
- **Footystats regional qualifier data** — xG per 90 by team (UEFA, CONMEBOL, CAF, AFC, CONCACAF, Gold Cup for hosts)
- **Kalshi** — moneyline and O/U contract prices (devigged)
- **Polymarket** — secondary market reference

A `conf_scalar` column in `team_stats` normalizes xG inputs across confederations (UEFA 1.00, CAF 0.96, CONMEBOL 0.88, AFC/CONCACAF 0.87, OFC 0.80). **Active in O/U production; not applied to moneyline** to avoid double-counting with F1 Opta. Apparent CONMEBOL undervaluation is a documented v1.1 calibration item. See methodology §6.

---

## 8. Backtesting and Forward Testing

WC2022 calibration is in progress (`notebooks/wc2022_backtest.ipynb`). Limited to prediction-quality testing only — historical Kalshi prices are not available, so market-edge backtesting is not claimed.

**Primary validation is live forward-testing from June 11, 2026.** Model outputs are frozen at T-1hr before each match (stored in `*_FROZEN_<date>` tabs) and tracked against realized outcomes for accuracy, calibration, and CLV (closing line value).

---

## 9. Documented Limitations

Full list in [`methodology.md`](./methodology.md#15-documented-limitations). Headline items:

- Hand-weighted scorecard model — weights not optimized; logistic regression calibration deferred until 20+ match sample exists
- xG inputs not normalized across confederations; `weak_schedule_match` flag surfaces affected matchups for separate forward-test evaluation
- Goal differential not opponent-adjusted (Norway-type schedule strength bias)
- Draw probability is heuristic — Poisson scoreline replacement is a v1.1 candidate
- New Zealand uses a goals-based fallback (no xG source)
- O/U v0.3 situational factor weights are uncalibrated; v0.2 O/U archived for side-by-side comparison
- Confederation quality scalars active in O/U but not moneyline (avoids double-counting with F1 Opta); apparent CONMEBOL undervaluation flagged as v1.1 calibration item

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
│   ├── ou_model_vo2_FROZEN.csv
│   ├── ou_model_v03.csv
│   └── methodology_notes.csv
└── notebooks/
    ├── populate_tracker.py
    ├── analysis.py
    └── wc2022_backtest.ipynb   (in progress)
```

---

## 11. Recruiting Context

Project demonstrates quant-finance-relevant skills:

- **Factor modeling** with explicit collinearity control (F4 excluded for redundancy with F3) and architecture differentiation (v0.2 for binary moneyline, v0.3 for continuous O/U totals)
- **Market microstructure** — proportional devigging applied consistently to moneyline and totals markets
- **Risk controls** — CHECK INPUTS, BLOCK DRAW, and weak-schedule flags address known model failure modes with transparent rules
- **Production vs research separation** — v0.2 moneyline frozen and forward-tested; v0.3 moneyline overlay tracked side-by-side as experimental; legacy v0.2 O/U preserved alongside v0.3 production for comparison
- **Validation discipline** — frozen pre-match predictions, forward-tested with no lookahead, tracked with CLV
- **Documentation** — full methodology in `methodology.md`; design decisions, limitations, and roadmap items logged transparently

Planned v1.1+ additions: logistic regression weight optimization on accumulated forward-test sample, Poisson-based draw replacement, regional xG normalization (corrected confederation scalars after CONMEBOL fix), v0.3 moneyline promotion after calibration.

---

## 12. Performance Tracking

Live forward-test results for WC2026:

[Live Results Sheet](https://docs.google.com/spreadsheets/d/1yc9avlxl9Q6yhSY-L9pOHyBw9OTRa8YHXEjiLBR4oBg/edit?usp=sharing) | [Model Outputs CSV](./data/model_output_FROZEN.csv)

Columns tracked: match | model probability (frozen T-1hr) | market probability (frozen T-1hr) | edge | signal | weak_schedule_match | outcome | P&L (1u flat) | CLV

*Updated after each match day.*
