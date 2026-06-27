# Methodology

Design decisions, formulas, and risk controls for the 2026 World Cup Pricing Engine.

| Component | Version | Tab |
|-----------|---------|-----|
| Match outcome (moneyline) | v0.2 (frozen) | `model_inputs_v02_FROZEN`, `model_output_FROZEN` |
| Over/Under | v0.3 (production) | `ou_model` |
| Over/Under (legacy reference) | v0.2 (frozen) | `ou_model_vo2_FROZEN` |
| v0.3 situational overlay for moneyline | Experimental | `model_inputs_v03 (experimental)` |

---

## 1. Project Purpose

The objective is to estimate fair-value probabilities for each World Cup match outcome and compare them against Kalshi market-implied probabilities to identify potential mispricings.

This is not primarily a winner-prediction exercise. `model_pick` (most likely outcome) and `best_value` (highest model-vs-market edge) are tracked separately because they frequently differ — the most likely outcome is not always the best-priced.

The project is framed as a quantitative market-pricing model using sports event contracts as the tradable asset, not a soccer prediction model.

---

## 2. Model Versions

| Version | Status | Scope |
|---------|--------|-------|
| Moneyline v0.2 | Official launch (frozen) | Match outcome probabilities (home/draw/away); four team-quality differentials |
| Moneyline v0.3 | Experimental overlay | Adds situational factors (climate, altitude, venue, host, tactical style); not used for live signals |
| O/U v0.3 | Official launch (production) | Goal totals via asymmetric xG weighting + tactical/venue/climate modifiers + Poisson |
| O/U v0.2 | Archived reference | Simple combined-xG Poisson; superseded by v0.3 but preserved frozen for comparison |

Moneyline v0.3 overlay remains experimental because the situational factors are uncalibrated for the binary match-outcome problem. For totals, however, the same factors have stronger theoretical justification (goal-scoring is more sensitive to environmental context than win/draw outcomes are), so the v0.3 O/U was promoted to production.

---

## 3. Match Outcome Model (Moneyline v0.2)

### 3.1 Inputs

Four team-quality differentials:

- **`elo_diff`** — broad team strength differential. Sourced from Opta Power Ratings; the column is labeled `elo` for historical reasons but contains Opta data. The original Opta-vs-Elo dual-anchor design was collapsed to a single quality measure to avoid double-counting.
- **`gd_last5_diff`** — goal differential differential from each team's last 5 competitive matches.
- **`xg_diff_diff`** — xG differential differential (xG for minus xG against, per-90 team aggregate).
- **`form_diff`** — form points differential from last 5 matches (W=3, D=1, L=0; max 15 per team).

#### Excluded factors

- **Shots on target**: redundant with xG and goal differential. Candidate for re-inclusion after calibration confirms incremental signal.
- **Opta as separate input**: collapsed into the single team-quality anchor to avoid double-counting.
- **Climate, altitude, host status, venue tier, tactical style**: collected and stored but excluded from v0.2 moneyline; used in v0.3 experimental overlay and in v0.3 O/U production.

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

This separation addresses a known limitation of pure sigmoid-based models, which over-allocate draw probability in heavy-mismatch matchups (see §10 Risk Controls). The heuristic is a known calibration candidate — see §16 Roadmap for the planned Poisson scoreline replacement.

---

## 4. Over/Under Model (v0.3 Production)

The production O/U model lives in the `ou_model` tab. The original v0.2 O/U is preserved in `ou_model_vo2_FROZEN` for reference and side-by-side evaluation.

### 4.1 xG inputs (asymmetric confederation adjustment)

Each team's xG inputs are adjusted by `conf_scalar` (§6), but offensive and defensive sides use different formulas:

**Offensive xG (simple discount):**
```
team_xg_for_adj  = team_xg_for * team_conf_scalar
```

A CAF team's attacking output is discounted by their confederation scalar (e.g., 0.96) before being used in the model.

**Defensive xG (elo-weighted blend between inflated and raw):**
```
team_xg_against_adj = (team_xg_against / team_conf_scalar) * (team_elo / 100)
                    + team_xg_against * (1 - team_elo / 100)
```

Defensive xG is INFLATED (divided by conf_scalar) rather than discounted, because a weak-confederation team's xg_against vs same-pool attackers understates how leaky they'd be against UEFA-level opposition. The elo weighting blends this inflated value with the raw value — stronger teams (high Opta rating) get more confederation adjustment, weaker teams stay closer to raw, acting as empirical-Bayes shrinkage toward the confederation prior.

This asymmetric treatment of offensive vs defensive xG is a deliberate design choice in v0.3.

### 4.2 Per-team expected goals (asymmetric 60/40 weighting)

```
home_exp_goals = (home_xg_for_adj * 0.6) + (away_xg_against_adj * 0.4)
away_exp_goals = (away_xg_for_adj * 0.6) + (home_xg_against_adj * 0.4)
total_exp_goals = home_exp_goals + away_exp_goals
```

The 60/40 split reflects that attacking output is more stable across opponents than defensive output is across attackers. The v0.2 O/U used a symmetric 50/50 split with no confederation scalar (preserved in `ou_model_vo2_FROZEN` for comparison).

### 4.3 Multiplicative scalar adjustments

Three modifiers are applied multiplicatively, not additively. Per-team tactical and climate modifiers are applied to each team's expected goals before combining; situational modifier is applied to the total.

**Per-team tactical modifiers:**
```
home_tactical_s, away_tactical_s = tactical style interaction values
                                   reflecting how each team's primary and
                                   secondary tactical style interacts with
                                   the opponent's style
```



**Venue tier penalty:**

```
venue_penalty = IFS(
    venue_tier = "extreme",   -0.20,
    venue_tier = "high",      -0.15,
    venue_tier = "altitude",  -0.15,
    venue_tier = "moderate",  -0.08,
    venue_tier = "mild",       0,
    TRUE,                      0
)
```

Reflects how extreme environments suppress total scoring.

**Climate modifier (per team, applied at per-team xG adjustment in §4.3):**

```
climate_modifier(team) = IFS(
    origin_climate < 10,   -0.08,
    origin_climate <= 20,   0,
    origin_climate <= 26,   0.05,
    TRUE,                  -0.10
)
```

Applied to each team's expected goals (see §4.3 below). Captures how teams adapt differently to match conditions based on their native climate.

**Combined situational modifier:**

```
situational_modifier         = away_tactical_s + venue_penalty
adjusted_total_exp_goals     = (home_adj_xg + away_adj_xg) * (1 + situational_modifier)
```

where `venue_penalty` is the IFS lookup above on `venue_tier`. Note that knockout-stage rows show #N/A in `venue_tier` and `situational_modifier` until the bracket resolves post-group-stage; this is expected and does not affect group-stage signals.

**Per-team adjusted xG (multiplicative):**
```
home_adj_xg = home_exp_goals * (1 + home_tactical_s) * (1 + home_climate_modifier)
away_adj_xg = away_exp_goals * (1 + away_tactical_s) * (1 + away_climate_modifier)
```

**Match-level adjusted total:**
```
adjusted_total_exp_goals = (home_adj_xg + away_adj_xg) * (1 + situational_modifier)
```

This three-layer multiplicative structure ensures environmental and tactical effects scale proportionally with projected goal volume rather than imposing flat additive penalties.

### 4.4 Probability calculation with variable lines

The O/U line for each match is read directly from Kalshi (`match_ou_line` column) — typically 2.5 but occasionally 1.5, 3.5, or 4.5 depending on the contract Kalshi offers for that match. Poisson probability is computed for the relevant line:

```
P(under L) = sum over k=0 to floor(L) of Poisson(k; adjusted_total)
P(over L)  = 1 - P(under L)
```

For the standard 2.5 line: `P(under 2.5) = Poisson(0) + Poisson(1) + Poisson(2)`. For higher lines (3.5, 4.5), additional Poisson terms are summed. For lower lines (1.5), fewer terms.

O/U market probabilities are devigged separately from moneyline using `kalshi_over_raw` and `kalshi_under_raw`. O/U signal thresholds match moneyline thresholds (§9).

### 4.4 Why O/U uses v0.3 architecture while moneyline uses v0.2

Match outcome (binary win/draw/loss) is less sensitive to environmental context than goal totals are. Situational factors (climate, altitude, venue, tactical style) have stronger theoretical justification for affecting how many goals are scored than for affecting which team wins. The decision to promote v0.3 architecture to production for O/U but not for moneyline reflects this asymmetry. Both are forward-tested live; the comparison will inform whether v0.3 situational factors should be promoted to moneyline in v1.1.

### 4.5 v0.2 O/U (archived reference)

Preserved in `ou_model_vo2_FROZEN`. Architecture:

```
home_exp_goals  = (home_xg_for + away_xg_against) / 2
away_exp_goals  = (away_xg_for + home_xg_against) / 2
total_exp_goals = home_exp_goals + away_exp_goals
P(under 2.5)    = Poisson cdf at 2 with lambda = total_exp_goals
```

No situational adjustments. Maintained for side-by-side evaluation against v0.3 during forward testing.

---

## 5. Moneyline v0.3 Experimental Overlay

A separate experimental overlay (`model_inputs_v03 (experimental)`) extends the moneyline factors with situational variables:
- Climate mismatch
- Altitude (team origin vs venue)
- Venue tier
- Host status
- Tactical primary and secondary style matchup

This overlay is NOT used for live moneyline signals. It is tracked side-by-side for research only. Promotion to production requires forward-test data showing it outperforms v0.2 on hit rate, calibration, or CLV.

A future production cap would limit the situational contribution:

```
capped_situational_score = MAX(-0.75, MIN(0.75, situational_score))
```

---

## 6. Confederation Quality Scalars

A `conf_scalar` column in `team_stats` (column L) with values derived from cross-confederation average Elo:

| Confederation | conf_scalar |
|---------------|-------------|
| UEFA | 1.00 (baseline) |
| CAF | 0.96 |
| CONMEBOL | 0.88 |
| AFC | 0.87 |
| CONCACAF (hosts via Gold Cup) | 0.87 |
| OFC fallback | 0.80 |

**Active in O/U production only.** In the v0.3 O/U model, each team's per-90 xG input is multiplied by their `conf_scalar` before being combined into expected goals. This normalizes raw xG values across confederation pools at the input level. See §4.1 for the modified formulas.

**Not applied to moneyline v0.2.** The moneyline model uses `xg_diff` directly without scalar adjustment because (a) the differential structure partially cancels confederation effects between two teams, and (b) F1 Opta already encodes confederation strength, so multiplying xG by `conf_scalar` would create double-counting. The `weak_schedule_match` flag (§10.3) handles confederation comparability transparently for moneyline.

**Known concerns documented as v1.1 calibration items:**
- The CONMEBOL value (0.88) appears inconsistent with WC-qualifier strength. Brazil, Argentina, and Uruguay rate significantly higher than 0.88 implies, suggesting the average may be skewed by including non-WC CONMEBOL nations.
- Coefficients are uncalibrated against forward-test data; values will be re-derived from observed CLV by confederation post-tournament.
- The asymmetric application (O/U yes, moneyline no) is a deliberate design choice but introduces structural inconsistency that should be reviewed when v0.3 moneyline overlay is calibrated.

---

## 7. Market Pricing and Devigging

### 7.1 Source

Kalshi event-contract prices are the primary market benchmark; Polymarket serves as a secondary reference.

### 7.2 Devigging

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

### 7.3 Timing

Kalshi prices move materially before kickoff. Final signals must use the latest available prices, captured at T-1hr (see §11 Operational Workflow).

---

## 8. Edge Calculation

```
edge_outcome = model_prob - market_prob
best_edge    = MAX(edge_home, edge_draw, edge_away)
best_value   = outcome corresponding to best_edge
```

A positive edge means the model prices the outcome higher than the market; a negative edge means the model prices it lower.

`best_value` can differ from `model_pick`. `model_pick` is the most likely outcome; `best_value` is the outcome with the highest model-vs-market gap. Both are tracked.

Same logic applies to O/U: `ou_best_value` is over or under, whichever has the larger devigged edge.

---

## 9. Signal Rules

| Signal | Condition |
|--------|-----------|
| STRONG PLAY | `best_edge ≥ 10%` and not in REVIEW |
| PLAY | `best_edge ≥ 6%` and not in REVIEW |
| WATCH | `best_edge ≥ 3%` |
| PASS | `best_edge < 3%` |
| REVIEW | `CHECK INPUTS` OR `BLOCK DRAW` filter triggered |

Signal hierarchy: **REVIEW override fires first**, then STRONG PLAY → PLAY → WATCH → PASS.

Same thresholds apply to moneyline and O/U. REVIEW rows require manual verification before being considered actionable.

---

## 10. Risk Controls

### 10.1 CHECK INPUTS

```
review_flag = "CHECK INPUTS" if best_edge >= 15% else ""
```

A 15%+ model-market gap is unusually large and typically indicates:
- Stale or illiquid Kalshi price
- Bad model input for one team (wrong xG, name mismatch, missing data)
- Genuine model-market disagreement (rare)

CHECK INPUTS does not invalidate the play — it forces manual review of underlying inputs before any action. Large edges are preserved on the dashboard rather than suppressed, to maintain transparency.

Same threshold applies to O/U via `ou_review_flag`.

### 10.2 BLOCK DRAW

```
draw_play_filter = "BLOCK DRAW" if (
    best_value     = "Draw" AND
    market_draw    < 15%    AND
    ABS(raw_score) > 1.5
) else ""
```

**Rationale:** the v0.2 moneyline model systematically over-flagged draws as STRONG PLAY in heavy-favorite matches (e.g., Germany, Spain, Brazil, France, Portugal vs minnows). The heuristic draw probability floor was too high relative to market prices in severe mismatch games.

The filter blocks draw signals when:
- The model is calling Draw as `best_value`
- The market prices Draw very low (<15%)
- The raw score indicates a heavy mismatch (|raw_score| > 1.5)

Blocked draw rows are converted to REVIEW. The filter does not change probabilities — only signal classification.

Draws in *balanced* matchups (low |raw_score|, market_draw > 15%) are still legitimate value candidates and not affected by the filter.

### 10.3 Weak Schedule Flag (Moneyline transparency)

A transparency flag for the moneyline model, not a probability correction. Surfaces matches where cross-confederation data comparability may distort moneyline signal.

```
weak_schedule_flag (per team) = 1 if team's xG source is from a materially
                                  weaker confederation pool (AFC qualifiers,
                                  CAF qualifiers, CONCACAF non-host qualifiers,
                                  OFC fallback); 0 otherwise

weak_schedule_match = "FLAG" if home_team.weak_schedule_flag != away_team.weak_schedule_flag,
                              else ""
```

**Why moneyline-specific:** The O/U model handles confederation comparability directly at the input level via `conf_scalar` multiplication (§4.1, §6). The moneyline model does NOT apply `conf_scalar` to its xG inputs because doing so would double-count with F1 Opta. For moneyline, this flag is the disclosure mechanism: it identifies matches where the unadjusted `xg_diff_diff` may be distorted by pool baseline differences.

**Why asymmetric (XOR) logic:** xG comparability problems arise specifically in *cross-pool* matchups — a UEFA team (stats vs UEFA opposition) playing an AFC team (stats vs AFC opposition). When two teams come from the same pool (UEFA vs UEFA, or AFC vs AFC), the differential remains internally valid even if baselines differ from other confederations. The flag therefore fires only on cross-pool matchups.

This flag does not modify probabilities. Bucketing live results by `weak_schedule_match` will indicate whether moneyline systematically over- or under-predicts on cross-pool matches, informing whether `conf_scalar` should be applied to moneyline (with double-counting mitigation) in v1.1.

---

## 11. Data Sources

| Source | Use |
|--------|-----|
| Opta Power Rankings | Team strength anchor (`elo_diff`) |
| Kaggle martj42 international results | Form, recent GD (`form_diff`, `gd_last5_diff`) |
| Footystats regional qualifier data | xG per 90 by team (`xg_diff_diff`, O/U inputs) |
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

## 12. Operational Workflow

### 12.1 Freezing process

Before each match, official tabs are duplicated and pasted as values only. Frozen tabs are named with the kickoff date suffix:

- `model_inputs_v02_FROZEN_0611`
- `model_output_FROZEN_0611`
- `daily_odds_FROZEN_0611`
- `ou_model_FROZEN_0611`

Freezing is executed at T-1hr after final Kalshi prices are entered and before kickoff. It preserves the exact pre-match outputs and prevents retroactive formula changes or data updates from contaminating the forward test.

### 12.2 Results tracking

After each match, `live_results_tracker` records:
- `model_pick` and `model_pick_hit`
- `best_value` and `best_value_hit`
- Signal tier
- `weak_schedule_match` flag value
- Frozen model and market probabilities
- O/U signal and `ou_result`
- `actual_outcome` (home win / draw / away win)
- CLV (closing line value)

Moneyline performance tracks `model_pick_hit` and `best_value_hit` separately. O/U performance tracks `ou_best_value_hit`.

### 12.3 Forward testing

Live forward-testing during the 2026 World Cup is the primary validation method. It avoids look-ahead bias and preserves real pre-match decision conditions, which is methodologically stronger than retrofitted backtests on incomplete historical inputs.

---

## 13. Evaluation Plan

After a meaningful sample (target: 20+ matches), evaluate:

1. **`model_pick` accuracy** — raw hit rate for the most likely outcome.
2. **`best_value` hit rate** — by signal tier (STRONG PLAY / PLAY / WATCH).
3. **Calibration** — group predictions into buckets (40–50%, 50–60%, 60–70%, 70–80%, 80%+) and check whether realized hit rates match predicted probabilities.
4. **Draw performance** — evaluated separately. Draw probability is the most fragile part of the current model.
5. **Weak-schedule bucket performance** — `weak_schedule_match = FLAG` rows analyzed separately from non-flagged rows.
6. **REVIEW row performance** — analyzed separately from official PLAY / STRONG PLAY.
7. **O/U hit rate** — by signal tier; v0.3 production vs v0.2 archived for relative performance.

---

## 14. Backtesting Plan

Backtesting is a credibility supplement, not the primary validation:

- Initial backtest is a 2022 World Cup sanity check: did higher model probabilities generally align with actual outcomes?
- Backtesting evaluates `model_pick` accuracy separately from `best_value` edge performance.
- Historical market-edge backtesting is **not** claimed because reliable historical Kalshi-equivalent prices are unavailable. Without historical market prices, only prediction quality can be backtested — not market mispricing performance.

---

## 15. Documented Limitations

- Hand-weighted scorecard model — weights not optimized; logistic regression calibration deferred until 20+ match sample exists.
- Weights should not be aggressively re-tuned on individual match results.
- Reliable calibration conclusions require 20+ matches.
- xG availability varies by confederation; regional sample sizes and competition strength are not normalized. Mitigated (not corrected) by `weak_schedule_match` flag.
- Goal differential is not fully opponent-adjusted; teams with weak qualifying schedules (e.g., Norway's UEFA group) may look artificially strong.
- Draw probabilities are heuristic; replacement with a Poisson scoreline grid or calibrated draw classifier is a v1.1 candidate.
- O/U v0.3 includes situational factors (tactical, venue, climate) whose individual contributions are uncalibrated. v0.2 O/U archived for side-by-side comparison.
- `conf_scalar` is active in O/U inputs but apparent CONMEBOL undervaluation (0.88) and uncalibrated coefficients are documented concerns. Not applied to moneyline to avoid double-counting with F1 Opta.
- Kalshi prices move before kickoff; final signals must use the latest prices.
- REVIEW rows are not final trading recommendations.

---

## 16. Roadmap

- Logistic regression weight optimization on accumulated forward-test sample
- Draw probability replacement (Poisson scoreline grid or calibrated draw classifier)
- v0.3 moneyline overlay promotion to production after situational factor calibration (with capped situational score)
- Confederation scalar activation in xG inputs, after CONMEBOL correction and F1 interaction analysis
- Regional xG normalization across confederations
- Opponent-adjusted goal differential
- KO-stage O/U model recalibration (added post-group-stage once bracket is known)
- Public results dashboard with running calibration plots and weak-schedule-bucketed performance
