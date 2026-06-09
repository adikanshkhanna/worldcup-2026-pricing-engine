# Methodology

Design decisions, formulas, and risk controls for the 2026 World Cup Pricing Engine v0.2 (official launch model) and v0.3 (experimental overlay).

---

## 1. Project Purpose

The objective is to estimate fair-value probabilities for each World Cup match outcome and compare them against Kalshi market-implied probabilities to identify potential mispricings.

This is not primarily a winner-prediction exercise. `model_pick` (most likely outcome) and `best_value` (highest model-vs-market edge) are tracked separately because they frequently differ — the most likely outcome is not always the best-priced.

The project is framed as a quantitative market-pricing model using sports event contracts as the tradable asset, not a soccer prediction model.

---

## 2. Model Versions

| Version | Status | Description |
|---------|--------|-------------|
| v0.2 | Official launch | Clean base model using team-quality differentials; powers all official pre-match signals |
| v0.3 | Experimental | Situational overlay adding climate, altitude, venue, host, and tactical factors; tracked side-by-side for research, not used for live signals |
| O/U | In progress | Separate totals model using Poisson distribution on xG-derived expected goals |

v0.3 is held experimental because situational variables are more subjective and can produce overly aggressive edge signals. Until calibrated against backtest data, v0.3 will not be promoted to production.

---

## 3. v0.2 Match Outcome Model

### 3.1 Inputs

Four team-quality differentials:

- **`elo_diff`** — broad team strength differential. Sourced from Opta Power Ratings; the column is labeled `elo` for historical reasons but contains Opta data. The original Opta-vs-Elo dual-anchor design was collapsed to a single quality measure to avoid double-counting.
- **`gd_last5_diff`** — goal differential differential from each team's last 5 competitive matches.
- **`xg_diff_diff`** — xG differential differential (xG for minus xG against, per-90 team aggregate).
- **`form_diff`** — form points differential from last 5 matches (W=3, D=1, L=0; max 15 per team).

#### Excluded factors

- **Shots on target**: redundant with xG and goal differential. Candidate for re-inclusion after calibration confirms incremental signal.
- **Opta as separate input**: collapsed into the single team-quality anchor to avoid double-counting.
- **Climate, altitude, host status, venue tier, tactical style**: collected and stored but excluded from v0.2; used in v0.3 experimental overlay.

In this project, `home_team` refers to the *listed* home team in the Kalshi contract — not necessarily true home-field advantage. Positive matchup-difference values indicate an advantage for the listed home team.

### 3.2 Formula

```
raw_score = (elo_diff       * 0.06) +
            (gd_last5_diff  * 0.15) +
            (xg_diff_diff   * 0.35) +
            (form_diff      * 0.08)

home_strength = 1 / (1 + EXP(-raw_score))
```

`home_strength` represents the listed home team's share of non-draw win probability.

### 3.3 Probability Split

Draw probability is estimated separately rather than derived from the sigmoid:

```
home_win_prob  = (1 - draw_prob) * home_strength
away_win_prob  = (1 - draw_prob) * (1 - home_strength)
home_win_prob + draw_prob + away_win_prob = 100%
```

`draw_prob` is computed from matchup closeness, with |elo_diff| as the closeness proxy:

```
draw_prob = MAX(0.18, MIN(0.35, 0.30 - ABS(elo_diff) * 0.003))
```

In words: base draw probability of 30%, reduced by 0.3 percentage points per unit of Opta rating gap, floored at 18% (heavy mismatches) and capped at 35% (perfectly even matchups). This range is consistent with historical World Cup draw rates (~24% mean).

This separation addresses a known limitation of pure sigmoid-based models, which over-allocate draw probability in heavy-mismatch matchups (see §9 Risk Controls). The heuristic is a known calibration candidate — see §15 Roadmap for the planned Poisson scoreline replacement.

---

## 4. Over/Under Model

The O/U model lives in a separate `ou_model` tab and is not mixed into the win/draw/loss `raw_score`.

```
home_exp_goals  = (home_xg_for + away_xg_against) / 2
away_exp_goals  = (away_xg_for + home_xg_against) / 2
total_exp_goals = home_exp_goals + away_exp_goals

P(under 2.5)    = Poisson(0; total_exp_goals)
                + Poisson(1; total_exp_goals)
                + Poisson(2; total_exp_goals)

P(over 2.5)     = 1 - P(under 2.5)
```

O/U market probabilities are devigged separately from moneyline using `kalshi_over_raw` and `kalshi_under_raw`. O/U signal thresholds match moneyline thresholds until calibration suggests otherwise.

---

## 5. v0.3 Experimental Overlay

v0.3 adds situational factors as a research overlay:
- Climate mismatch (team origin climate vs venue climate)
- Altitude (origin altitude vs venue altitude)
- Venue tier
- Host status
- Tactical primary style matchup
- Tactical secondary style matchup

**Why not in production:** situational variables are subjective, weights are uncalibrated, and the overlay can produce aggressive edge signals on edge cases. v0.3 is tracked side-by-side with v0.2 for research only.

**Future production cap:** when v0.3 is promoted, the situational score will be capped:

```
capped_situational_score = MAX(-0.75, MIN(0.75, situational_score))
```

This prevents situational factors from dominating the team-quality base model.

---

## 6. Market Pricing and Devigging

### 6.1 Source

Kalshi event-contract prices are the primary market benchmark; Polymarket serves as a secondary reference.

### 6.2 Devigging

Raw Kalshi YES contract prices for home/draw/away typically sum to 102–106¢ due to spread and platform fee. They are normalized proportionally:

```
market_home = kalshi_home_raw / (kalshi_home_raw + kalshi_draw_raw + kalshi_away_raw)
```

(Same construction for `market_draw` and `market_away`.) Devigged probabilities sum to exactly 100%. The same normalization is applied to O/U contracts.

This is the first step in all analysis; comparing model probabilities to raw vigged prices would systematically understate edges.

**Worked example (Match 1, Mexico vs South Africa):**
- Raw Kalshi: 70 / 21 / 12 (sum = 103¢, 3¢ overround)
- Devigged: 67.96% / 20.39% / 11.65% (sum = 100.00%)
- Model v0.2: 59.35% / 25.53% / 15.12%
- Edge on Draw: +5.14pp → WATCH signal

### 6.3 Timing

Kalshi prices move materially before kickoff. Final signals must use the latest available prices, captured at T-1hr (see §10 Operational Workflow).

---

## 7. Edge Calculation

```
edge_home  = model_home_prob - market_home
edge_draw  = model_draw_prob - market_draw
edge_away  = model_away_prob - market_away

best_edge  = MAX(edge_home, edge_draw, edge_away)
best_value = outcome corresponding to best_edge
```

A positive edge means the model prices the outcome higher than the market; a negative edge means the model prices it lower.

`best_value` can differ from `model_pick`. `model_pick` is the most likely outcome; `best_value` is the outcome with the highest model-vs-market gap. Both are tracked.

---

## 8. Signal Rules

| Signal | Condition |
|--------|-----------|
| STRONG PLAY | `best_edge ≥ 10%` and not in REVIEW |
| PLAY | `best_edge ≥ 6%` and not in REVIEW |
| WATCH | `best_edge ≥ 3%` |
| PASS | `best_edge < 3%` |
| REVIEW | `review_flag = CHECK INPUTS` OR `draw_play_filter = BLOCK DRAW` |

Signal hierarchy: **REVIEW override fires first**, then STRONG PLAY → PLAY → WATCH → PASS.

REVIEW rows require manual verification before being considered actionable. They are not automatic plays.

---

## 9. Risk Controls

### 9.1 CHECK INPUTS

```
review_flag = "CHECK INPUTS" if best_edge >= 15% else ""
```

A 15%+ model-market gap is unusually large and typically indicates:
- Stale or illiquid Kalshi price
- Bad model input for one team (wrong xG, name mismatch, missing data)
- Genuine model-market disagreement (rare)

CHECK INPUTS does not invalidate the play — it forces manual review of underlying inputs before any action. Large edges are preserved on the dashboard rather than suppressed, to maintain transparency.

### 9.2 BLOCK DRAW

```
draw_play_filter = "BLOCK DRAW" if (
    best_value     = "Draw" AND
    market_draw    < 15%    AND
    ABS(raw_score) > 1.5
) else ""
```

**Rationale:** the v0.2 model systematically over-flagged draws as STRONG PLAY in heavy-favorite matches (e.g., Germany, Spain, Brazil, France, Portugal vs minnows). The heuristic draw probability floor was too high relative to market prices in severe mismatch games.

The filter blocks draw signals when:
- The model is calling Draw as `best_value`
- The market prices Draw very low (<15%)
- The raw score indicates a heavy mismatch (|raw_score| > 1.5)

Blocked draw rows are converted to REVIEW. The filter does not change probabilities — only signal classification.

Draws in *balanced* matchups (low |raw_score|, market_draw > 15%) are still legitimate value candidates and not affected by the filter.

---

## 10. Data Sources

| Source | Use |
|--------|-----|
| Opta Power Rankings | Team strength anchor (`elo_diff`) |
| Kaggle martj42 international results | Form, recent GD (`form_diff`, `gd_last5_diff`) |
| Footystats regional qualifier data | xG per 90 by team (`xg_diff_diff`) |
| Kalshi | Moneyline and O/U event-contract prices |
| Polymarket | Secondary market reference |

### xG sources by confederation

- **UEFA**: European WC Qualifiers 2024–25
- **CONMEBOL**: WC Qualifiers Sep 2024 onward (12 matches/team for sample stability)
- **CAF**: CAF WC Qualifiers 2023–25 (preferred over AFCON 2025 for cross-team consistency)
- **AFC**: AFC WC Qualifiers Nov 2024+
- **CONCACAF non-hosts**: CONCACAF WC Qualifiers 2024–25
- **CONCACAF hosts (Mexico, USA, Canada)**: Gold Cup 2025
- **OFC (New Zealand)**: no available source; goals-based fallback

### Team naming

Team names are standardized across all tabs to avoid lookup failures. Examples: `USA`, `IR Iran`, `Czechia`, `Cabo Verde`, `Côte d'Ivoire`, `DR Congo`, `Turkey`.

### Friendlies

Friendlies are excluded from competitive form calculations where possible. Some pre-WC friendly-style competitions (FIFA Series, Kirin Cup, King's Cup) occasionally bypass the friendly filter — logged as a known limitation.

---

## 11. Operational Workflow

### 11.1 Freezing process

Before each match, official tabs are duplicated and pasted as values only. Frozen tabs are named with the kickoff date suffix:

- `model_inputs_v02_FROZEN_0611`
- `model_output_FROZEN_0611`
- `daily_odds_FROZEN_0611`
- `ou_model_FROZEN_0611`

Freezing is executed at T-1hr after final Kalshi prices are entered and before kickoff. It preserves the exact pre-match outputs and prevents retroactive formula changes or data updates from contaminating the forward test.

### 11.2 Results tracking

After each match, `results_tracker` records:
- `model_pick` and `model_pick_hit`
- `best_value` and `best_value_hit`
- Signal tier
- Frozen model and market probabilities
- O/U signal and `ou_result`
- `actual_result` (home win / draw / away win)
- CLV (closing line value)

Moneyline performance tracks `model_pick_hit` and `best_value_hit` separately. O/U performance tracks `ou_best_value_hit`.

### 11.3 Forward testing

Live forward-testing during the 2026 World Cup is the primary validation method. It avoids look-ahead bias and preserves real pre-match decision conditions, which is methodologically stronger than retrofitted backtests on incomplete historical inputs.

---

## 12. Evaluation Plan

After a meaningful sample (target: 20+ matches), evaluate:

1. **`model_pick` accuracy** — raw hit rate for the most likely outcome.
2. **`best_value` hit rate** — by signal tier (STRONG PLAY / PLAY / WATCH).
3. **Calibration** — group predictions into buckets (40–50%, 50–60%, 60–70%, 70–80%, 80%+) and check whether realized hit rates match predicted probabilities.
4. **Draw performance** — evaluated separately. Draw probability is the most fragile part of the current model.
5. **REVIEW row performance** — analyzed separately from official PLAY / STRONG PLAY.
6. **O/U hit rate** — by signal tier.

---

## 13. Backtesting Plan

Backtesting is a credibility supplement, not the primary validation:

- Initial backtest is a 2022 World Cup sanity check: did higher model probabilities generally align with actual outcomes?
- Backtesting evaluates `model_pick` accuracy separately from `best_value` edge performance.
- Historical market-edge backtesting is **not** claimed because reliable historical Kalshi-equivalent prices are unavailable. Without historical market prices, only prediction quality can be backtested — not market mispricing performance.

---

## 14. Documented Limitations

- v0.2 is a hand-weighted scorecard model, not a machine-learning model. Weights are educated initial values, not optimized.
- Weights should not be aggressively re-tuned on individual match results.
- Reliable calibration conclusions require 20+ matches.
- xG availability varies by confederation; regional sample sizes and competition strength are not normalized.
- Goal differential is not fully opponent-adjusted; teams with weak qualifying schedules (e.g., Norway's UEFA group) may look artificially strong.
- Draw probabilities are heuristic; replacement with a Poisson scoreline grid or calibrated draw classifier is a v1.1 candidate.
- Kalshi prices move before kickoff; final signals must use the latest prices.
- REVIEW rows are not final trading recommendations.

---

## 15. Roadmap

- Logistic regression weight optimization on accumulated forward-test sample
- Draw probability replacement (Poisson scoreline grid or calibrated classifier)
- v0.3 promotion to production after situational factor calibration (with capped situational score)
- Regional xG normalization across confederations
- Opponent-adjusted goal differential
- KO-stage O/U model (added post-group-stage once bracket is known)
- Public results dashboard with running calibration plots
