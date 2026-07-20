# Methodology

Design decisions, formulas, results, and risk controls for the 2026 World Cup Pricing Engine.

**Structure of this document:**
- **Part I** — Group Stage models (moneyline v0.2, O/U v0.3) and results
- **Part II** — Knockout Stage models (moneyline regularized logit, O/U simplified Monte Carlo) and results
- **Part III** — Cross-tournament findings: full ROI breakdown, what changed between stages, and what we'd do differently

| Component | Stage | Version | Status | Data / Code |
|-----------|-------|---------|--------|-------------|
| Moneyline | Group | v0.2 | Frozen, official | `data/gs_model_inputs_v02_FROZEN.csv`, `data/gs_model_outputs.csv` |
| Over/Under | Group | v0.3 | Frozen, official | `data/gs_ou_model_v03.csv` |
| Moneyline v0.3 overlay | Group | Experimental | Not used for live signals | — |
| O/U v0.2 | Group | Archived | Superseded by v0.3, preserved for comparison | `data/gs_ou_model_vo2_FROZEN.csv` |
| Moneyline | Knockout | Regularized multinomial logit | Frozen, official | `data/WC Team Data Collection - ml_knockout_model.csv`, `notebook/knockout_ml_model.py` |
| Over/Under | Knockout | Simplified xG-blend + Monte Carlo | Frozen, official | `data/WC Team Data Collection - ou_knockout_model.csv`, `notebook/knockout_ou_model.py` |
| Results tracker (all stages) | Both | — | Live-updated | `data/gs_results_tracker.csv` |

---

# PART I — GROUP STAGE

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

Moneyline v0.3 overlay remained experimental because the situational factors were uncalibrated for the binary match-outcome problem. For totals, the same factors had stronger theoretical justification (goal-scoring is more sensitive to environmental context than win/draw outcomes are), so the v0.3 O/U was promoted to production. In hindsight (Part III), this justification did not hold up empirically for the modifiers ultimately used.

---

## 3. Match Outcome Model (Moneyline v0.2)

### 3.1 Inputs

Four team-quality differentials:

- **`elo_diff`** — broad team strength differential. Sourced from Opta Power Ratings; the column is labeled `elo` for historical reasons but contains Opta data. The original Opta-vs-Elo dual-anchor design was collapsed to a single quality measure to avoid double-counting.
- **`gd_last5_diff`** — goal differential differential from each team's last 5 competitive matches.
- **`xg_diff_diff`** — xG differential differential (xG for minus xG against, per-90 team aggregate).
- **`form_diff`** — form points differential from last 5 matches (W=3, D=1, L=0; max 15 per team).

#### Excluded factors

- **Shots on target**: redundant with xG and goal differential.
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

```
home_win_prob  = (1 - draw_prob) * home_strength
away_win_prob  = (1 - draw_prob) * (1 - home_strength)
home_win_prob + draw_prob + away_win_prob = 100%
```

`draw_prob` is computed from matchup closeness, with |elo_diff| as the closeness proxy:

```
draw_prob = MAX(0.18, MIN(0.35, 0.30 - ABS(elo_diff) * 0.003))
```

Base draw probability of 30%, reduced by 0.3 percentage points per unit of Opta rating gap, floored at 18% (heavy mismatches) and capped at 35% (perfectly even matchups). Consistent with historical World Cup draw rates (~24% mean).

This heuristic is a known calibration candidate. **Part III confirms it was a real predictive limitation, not just a theoretical one** — see the knockout-stage draw-resilience patch, which was built directly in response to this.

---

## 4. Over/Under Model (v0.3 Production, Group Stage)

### 4.1 xG inputs (asymmetric confederation adjustment)

**Offensive xG (simple discount):**
```
team_xg_for_adj = team_xg_for * team_conf_scalar
```

**Defensive xG (elo-weighted blend between inflated and raw):**
```
team_xg_against_adj = (team_xg_against / team_conf_scalar) * (team_elo / 100)
                    + team_xg_against * (1 - team_elo / 100)
```

Defensive xG is inflated (divided by conf_scalar) rather than discounted, because a weak-confederation team's xg_against vs same-pool attackers understates how leaky they'd be against UEFA-level opposition. The elo weighting blends this inflated value with the raw value.

### 4.2 Per-team expected goals (asymmetric 60/40 weighting)

```
home_exp_goals  = (home_xg_for_adj * 0.6) + (away_xg_against_adj * 0.4)
away_exp_goals  = (away_xg_for_adj * 0.6) + (home_xg_against_adj * 0.4)
total_exp_goals = home_exp_goals + away_exp_goals
```

### 4.3 Multiplicative scalar adjustments

```
home_adj_xg = home_exp_goals * (1 + home_tactical_s) * (1 + home_climate_modifier)
away_adj_xg = away_exp_goals * (1 + away_tactical_s) * (1 + away_climate_modifier)

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

Climate modifier per team is a piecewise function on origin climate temperature:

```
climate_modifier(team) = IFS(
    origin_climate < 10,   -0.08,
    origin_climate <= 20,   0,
    origin_climate <= 26,   0.05,
    TRUE,                  -0.10
)
```

This three-layer multiplicative structure was intended to scale environmental and tactical effects proportionally with projected goal volume. **Part III's retrospective found this stacking created a systematic downward bias — see §12.**

### 4.4 Probability calculation with variable lines

```
P(under L) = sum over k=0 to floor(L) of Poisson(k; adjusted_total)
P(over L)  = 1 - P(under L)
```

O/U lines are read directly from Kalshi (typically 2.5, occasionally 1.5/3.5/4.5).

### 4.5 v0.2 O/U (archived reference)

```
home_exp_goals  = (home_xg_for + away_xg_against) / 2
away_exp_goals  = (away_xg_for + home_xg_against) / 2
total_exp_goals = home_exp_goals + away_exp_goals
P(under 2.5)    = Poisson cdf at 2 with lambda = total_exp_goals
```

No situational adjustments. Preserved for side-by-side evaluation.

---

## 5. Moneyline v0.3 Experimental Overlay

Extends the moneyline factors with climate mismatch, altitude, venue tier, host status, and tactical style matchup. Not used for live signals — tracked side-by-side for research only.

```
capped_situational_score = MAX(-0.75, MIN(0.75, situational_score))
```

---

## 6. Confederation Quality Scalars

| Confederation | conf_scalar |
|---------------|-------------|
| UEFA | 1.00 (baseline) |
| CAF | 0.96 |
| CONMEBOL | 0.88 |
| AFC | 0.87 |
| CONCACAF (hosts via Gold Cup) | 0.87 |
| OFC fallback | 0.80 |

**Active in O/U production only.** Not applied to moneyline v0.2 — the differential structure partially cancels confederation effects, and F1 Opta already encodes confederation strength, so multiplying xG by `conf_scalar` would double-count. The `weak_schedule_match` flag (§7.3) is the moneyline disclosure mechanism instead.

**Documented v1.1 calibration concern:** the CONMEBOL value (0.88) appeared inconsistent with WC-qualifier strength (Brazil, Argentina, Uruguay rate meaningfully higher).

---

## 7. Market Pricing, Devigging, Edge, and Risk Controls

### 7.1 Devigging

```
market_home = kalshi_home_raw / (kalshi_home_raw + kalshi_draw_raw + kalshi_away_raw)
```

Same construction for `market_draw`, `market_away`, and O/U contracts. Devigged probabilities sum to exactly 100%. This is applied before any edge calculation.

**Worked example (Match 1, Mexico vs South Africa):** Raw Kalshi 70/21/12 (103¢, 3¢ overround) → devigged 67.96%/20.39%/11.65%. Model v0.2: 59.35%/25.53%/15.12%. Edge on Draw: +5.14pp → WATCH.

### 7.2 Edge and Signal

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

`best_value` (highest-edge outcome) and `model_pick` (most likely outcome) are tracked separately and often differ — see Part III §13 for why this distinction matters for evaluation.

### 7.3 Risk Controls

**CHECK INPUTS:** `"CHECK INPUTS" if best_edge >= 15%` — forces manual review; a 15%+ gap usually signals a stale price or bad input, rarely a genuine edge.

**BLOCK DRAW:** `"BLOCK DRAW" if best_value = "Draw" AND market_draw < 15% AND ABS(raw_score) > 1.5` — addresses systematic over-flagging of draws as STRONG PLAY in heavy-favorite matchups. Blocked rows convert to REVIEW; probabilities are not modified.

**Weak Schedule Flag:** `"FLAG" if home_team.weak_schedule_flag != away_team.weak_schedule_flag` — moneyline-specific transparency flag for cross-confederation matchups, since moneyline does not apply `conf_scalar` directly.

---

## 8. Data Sources

| Source | Use |
|--------|-----|
| Opta Power Rankings | Team strength anchor (`elo_diff`) |
| Kaggle martj42 international results | Form, recent GD |
| Footystats regional qualifier data | xG per 90 by team |
| Kalshi | Moneyline and O/U event-contract prices |
| Polymarket | Secondary market reference |

xG sourced per confederation from the relevant regional qualifiers (UEFA European Qualifiers, CONMEBOL Qualifiers, CAF Qualifiers, AFC Qualifiers, CONCACAF Qualifiers, Gold Cup for hosts). New Zealand (OFC) has no qualifier xG source and uses a goals-based fallback — see §15.

---

## 9. Operational Workflow

Before each match, official tabs are duplicated and frozen (pasted as values) at T-1hr, before final Kalshi prices lock and before kickoff. This preserves exact pre-match outputs and prevents retroactive contamination of the forward test. `live_results_tracker` then records model/market probabilities, picks, signals, and outcomes after each match.

Live forward-testing during the tournament is the primary validation method — it avoids look-ahead bias, which a retrofitted backtest cannot fully guarantee.

---

## 10. Group Stage Results

**Sample: all 72 group stage matches (June 11 – June 27, 2026).**

*(Note: an earlier internal retrospective cited n=66. That draft was run before the final 6 group matches had concluded — a real-time analysis timing gap, not a data exclusion. All results below use the complete, final 72-match sample.)*

### Moneyline

`model_pick` hit rate: **41/72 (56.9%)** — above the 48.5% home-win base rate and the 33% random-pick baseline, indicating real predictive skill in outcome selection.

### Calibration by predicted probability bucket

| Predicted probability of model_pick | n | Realized hit rate | Delta |
|---|---|---|---|
| 0–40% | 17 | 29.4% | -1.2% |
| 40–50% | 4 | 50.0% | +3.8% |
| 50–60% | 15 | 60.0% | +4.3% |
| 60–70% | 20 | 70.0% | +5.4% |
| **70–80%** | **9** | **55.6%** | **-19.2%** |
| 80%+ | 1 | 100.0% | n/a |

The 0–70% range is well-calibrated. The 70–80% bucket is the one clear miscalibration: predicted 75%, realized 56%.

### Failure mode: heavy favorites drawn by defensive underdogs

The 70-80% bucket miss was not driven by outright upsets — it was driven by draws. Spain vs. Cabo Verde, England vs. Ghana, Switzerland vs. Qatar, and Ecuador vs. Curaçao are representative cases: a heavy favorite failed to convert against a defensively organized underdog, resulting in a draw rather than the expected win. The v0.2 draw-probability heuristic under-weighted this risk in exactly the matchups where the underdog's defensive quality (not overall quality) made a draw more likely than the model's flat, elo-gap-only heuristic assumed.

The model over-recommends draws generally (34.8% of picks vs. 27.3% actual draw rate), but the 70-80% bucket shows the failure is *concentrated* in high-mismatch games specifically, not spread evenly.

### O/U (v0.3) Results

O/U pick hit rate (actionable picks only, excluding PASS/No Play): **25/55 (45.5%)** — below coin-flip.

| Metric | Value |
|---|---|
| Tournament avg total goals | 3.10 |
| Actual over rate at 2.5 line | 54.1% |
| Model picked under (of actionable picks) | 64% |

Two distinct problems: (1) directional bias toward "under" against a tournament that leaned "over," and (2) poor pick selection even within each direction (over-picks hit ~50%, under-picks hit ~44%) — meaning the model wasn't just biased, it was also picking the wrong specific matches within its bias.

### Probable causes (diagnosed, tested in Part II)

1. **Climate modifier too aggressive** — subtracting up to 20% from expected goals for non-temperate-origin teams, likely over-applied given most 2026 host cities ran hot in summer.
2. **Confederation/elo blend on xg_against compounded downward** rather than amplifying appropriately for weak-pool matchups.
3. **Venue penalty stacking additively** with tactical and climate modifiers, compounding downward pressure beyond what physical conditions justify.
4. **No tournament-context adjustment** (e.g., win-and-advance pressure increasing goal-scoring risk-taking) — not modeled at all.

A naive "always pick over" baseline would have hit 54% — beating the model. This became the explicit benchmark the knockout O/U rebuild was measured against (Part II).

---

# PART II — KNOCKOUT STAGE

## 11. Knockout Moneyline Model

### 11.1 Purpose and market structure

Generates fair-value probabilities for knockout matches and compares them against Kalshi prices to identify mispricings. Two markets are priced: the **1X2 market** (home/draw/away in regulation) and the **to-advance market** (which team progresses, via any route). The to-advance market is the primary product, since it matches Kalshi's actual knockout contract structure.

This is a distinct model from the frozen group-stage moneyline v0.2. It is a fitted regularized multinomial logistic regression — the calibrated-regression step the v0.2 roadmap explicitly deferred until a sufficient sample existed (69+ graded matches).

### 11.2 Core model

- **Features:** `elo_diff`, `gd_diff`, `xg_diff` (net), `form_diff`, `host`.
- **Regularization:** L2 = 0.5, selected via 5-fold cross-validated log-loss.
- **Fitted weights (standardized home–away contrast):** elo +2.03 (dominant), xg +0.77, host +0.28, form +0.18, gd −0.59 (mild gd/xg collinearity artifact; droppable with negligible log-loss change). xGOT was tested and added no out-of-fold value once elo/gd/xg were present — consistent with the group-stage finding that xGOT reflects non-persistent finishing variance, not a stable team quality signal.
- **Fit against a structured-scorecard alternative:** a head-to-head comparison against the original v0.2-style weighted-scorecard architecture showed the regularized logistic regression dominating on out-of-fold log-loss (0.661 vs. 0.854). This confirms the deferred-regression roadmap item from group stage was the correct call once sample size allowed it.

The model was built and frozen using team_stats as of the close of group-stage matchday 3 — 66 of 72 group matches had final results at build time (69 of 72 once New Zealand's 3 OFC matches, excluded for missing xG, are set aside from that count). This reflects a real operational constraint, not an oversight: knockout matches begin almost immediately after the group stage ends, leaving a narrow window to rebuild and validate a new architecture. Waiting for full group-stage completion would have compressed the entire knockout model build into a single night. `team_stats_knockout` ratings (`elo_ko`, `xg_for_blend`, `xg_against_blend`) reflect team form as of that build point, which is documented here as a frozen cutoff rather than a live-updating input.

### 11.3 Neutral-venue symmetry

Knockout matches are played at neutral sites, so "home" is a listing convention, not a real venue advantage. The model is trained on each match **and its mirror image** (negated features, swapped outcome), forcing zero home-listing bias. The only real venue advantage — for host nations Mexico, USA, and Canada — is captured by an explicit `host` term.

### 11.4 Draw-resilience adjustment

Directly built in response to the group-stage failure mode (§10): heavy favorites held to draws by defensive underdogs. Tested empirically before being added — among mismatches (rating gap above median), underdogs with strong defenses (low blended xGA) drew **31.6%** of the time vs. **12.5%** for weak-defense underdogs (n=35). A logistic check confirmed the direction (defensive-quality coefficient −0.68).

Implementation: `P(draw)` receives a modest, bounded boost based on (a) the underdog's blended xGA relative to field average and (b) rating-gap size. Kept small (K_DEF = 0.16) with no interaction term, to avoid overfitting a 35-match sample.

**Blended xGA** combines pre-tournament xg_against with realized tournament xGA (weighted 0.40, reflecting a 3-game sample).

### 11.5 Temperature calibration (τ = 1.35)

Raw softmax probabilities were over-extreme in large mismatches. A temperature parameter τ divides logits before the softmax. τ was calibrated (not hand-picked) to minimize squared deviation between model to-advance probabilities and real Kalshi to-advance prices across 5 contracts available at calibration time:

| Match | Model advance | Kalshi advance |
|---|---|---|
| Côte d'Ivoire | 38% | 36% |
| France | 92% | 88% |
| Mexico | 64% | 63% |
| England | 86% | 88% |
| Belgium | 54% | 59% |

Optimum τ = 1.35. This is a calibration layer applied on top of the fitted weights — it does not change them.

**Disclosed tradeoff:** matching the market's overall sharpness means edges no longer come from being systematically more/less confident than the market globally — they come from per-match deviations and matches without a Kalshi price yet. **Caveat:** τ rests on only 5 market prices; a small-sample calibration that should be refit as more contracts open in future work.

### 11.6 Advance probability formula

```
P(advance) = P(win in 90) + P(draw in 90) × P(win shootout)
P(win shootout) = clip(0.5 + (P_home − P_away) × 0.25, 0.40, 0.60)
```

The shootout term compresses toward 50/50, reflecting penalty variance and goalkeeper compression. The favorite's advance-probability edge comes mainly from regulation win probability, not the shootout term.

### 11.7 Sheet output columns

- `model_home`/`model_draw`/`model_away` — τ-calibrated 1X2 probabilities.
- `model_home_adv`/`model_away_adv` — to-advance probabilities.
- `model_90_pick` — most likely regulation result, including "Draw" when genuinely close.
- `model_adv_pick` — favored team to advance.
- `upset_alert` — "UPSET LIVE" when advance probabilities are within ~15 points, "WATCH" within ~30, blank otherwise. Display-only triage flag; does not modify probabilities.

### 11.8 Edge and signal (both markets)

Same signal tiers as group stage (STRONG PLAY ≥10%, PLAY ≥6%, WATCH ≥3%, PASS <3%, REVIEW override ≥15%), applied separately to 1X2 edges and to-advance edges. The group-stage BLOCK DRAW filter is not ported to the to-advance market, since that market has no draw outcome to block.

### 11.9 Penalty-xG sensitivity check (disclosed, not used in production)

Tournament xG includes penalties (~0.79 xG each), noisy on a 3-game sample. As a robustness check, penalty-derived xG was stripped and the model refit. Result: directionally sensible but the bracket-level magnitude (e.g., swinging Netherlands–Morocco from 58/42 to 71/29) exceeded what a 1–2-penalty sample justifies. **Decision: reported as a sensitivity check, not used in production.** This is a cost-vs-disqualifying distinction — the data doesn't yet exist in the clean form needed (a data-collection cost), not a claim that penalty-adjusted xG is invalid in principle.

### 11.10 Known limitations (moneyline, knockout)

1. Penalty xG excluded from production pending direct non-penalty xG collection.
2. Draw-resilience effect rests on n=35 — directional, not statistically precise.
3. τ=1.35 calibrated on only 5 market prices.
4. gd coefficient mildly negative from gd/xg collinearity — harmless, droppable.
5. Host factor has few in-sample knockout cases; weight kept modest.
6. New Zealand's 3 group matches excluded from the 69-match training fit (xG uncollected for OFC).

---

## 12. Knockout Over/Under Model

### 12.1 Why this model differs from group stage

The group-stage O/U retrospective (§10) identified that the tactical/climate/venue modifier stack was contributing noise, not signal — the modifiers were systematically negative and compounded multiplicatively into a downward bias on expected goals, without a corresponding gain in accuracy (46% hit rate, worse than a naive always-over baseline).

**This was an intentional simplification, not a time-constrained shortcut.** The knockout O/U model drops the tactical, climate, and venue modifier layers entirely and applies the same feature-discipline standard already used on the moneyline side (where xGOT, penalty-net, and set-piece-net features were cut for failing to improve out-of-fold log-loss): if a component doesn't demonstrably improve calibration or accuracy, it is cut, regardless of how intuitive it seemed at design time.

### 12.2 Architecture

Per-team expected goals, direct xG blend with no confederation scalar or modifiers:

```
home_base_lambda = xg_for_blend(home) * 0.6 + xg_against_blend(away) * 0.4
away_base_lambda = xg_for_blend(away) * 0.6 + xg_against_blend(home) * 0.4
```

### 12.3 Monte Carlo simulation with parameter uncertainty

Rather than treating the base lambda as a fixed point estimate, the model draws from a Gamma distribution around it to reflect uncertainty in the rating itself, then simulates Poisson goal-scoring:

- **Coefficient of variation on lambda:** 0.20 (Gamma shape/scale derived from this target CV)
- **10,000 simulated draws per match**
- Over/under probabilities are the empirical share of simulated totals above/below the line

```
k = 1 / (lambda_cv ** 2)
home_lambda_draws = Gamma(shape=k, scale=home_base_lambda / k, size=10000)
away_lambda_draws = Gamma(shape=k, scale=away_base_lambda / k, size=10000)
home_goals_sim = Poisson(home_lambda_draws)
away_goals_sim = Poisson(away_lambda_draws)
over_prob = mean(total_goals_sim > line)
```

**Validation check:** with `lambda_cv = 0`, the simulation collapses to fixed lambdas every draw, which should converge to the closed-form Poisson CDF. This sanity check is run before every batch to confirm the simulation implementation is correct, independent of whether the Gamma-uncertainty layer is switched on.

### 12.4 Rationale for Monte Carlo over closed-form Poisson

The closed-form Poisson CDF (used in group-stage v0.2 O/U and available here at CV=0) assumes the lambda point estimate is known with certainty. The knockout version instead treats lambda itself as uncertain — reflecting that a blended xG rating is an estimate, not a fact — and propagates that uncertainty into wider, more honest over/under probabilities. This is a different kind of rigor than adding more modifiers: it acknowledges estimation uncertainty in the inputs that are kept, rather than adding more inputs whose individual effect sizes were not empirically supported.

### 12.5 Known limitations (O/U, knockout)

- Lambda-CV of 0.20 is a chosen parameter, not fit to data; a natural v1.2 extension is calibrating it against realized variance in the knockout sample.
- No confederation, venue, or climate adjustment at all — a deliberate simplification, but one that means any real venue/climate effect (e.g., a genuinely hot, humid knockout venue) is currently unmodeled rather than modeled-and-wrong. This tradeoff is disclosed, not hidden.
- Small per-round sample sizes (8 RO32 matches, 8 RO16, 4 QF, 2 SF, 2 finals matches) limit how precisely any future recalibration can be done stage-by-stage.

---

## 13. Knockout Stage Results

**Sample: 32 knockout matches (RO32 through Final), including the Final with DraftKings-sourced odds — see §14.3 for the data-provenance note.**

### Moneyline

| Metric | Result |
|---|---|
| `model_90_pick` hit rate (regulation result) | 21/32 (65.6%) |
| `model_adv_pick` hit rate (to-advance) | 25/32 (78.1%) |

Both are meaningfully improved over the group-stage 56.9% moneyline hit rate. The to-advance market — the model's primary product and the one that actually matches Kalshi's contract structure — performed best.

### Over/Under

| Metric | Result |
|---|---|
| `model_pick` hit rate | 19/32 (59%) |
| Edge-based pick hit rate | 13/23 (57%) |

Improved from the group-stage 45.5%, consistent with the diagnosed-and-corrected modifier-noise fix in §12.

---

## 14. Final Match Data Note

The Final (Spain vs. Argentina, match_id 104) initially had no market odds recorded in any tracked source, creating a gap in the edge/signal columns for that match. Odds were subsequently obtained from **DraftKings** (moneyline/to-advance market) rather than Kalshi, which was used for every other match in this dataset.

This is disclosed here for reproducibility: DraftKings and Kalshi are different books with different liquidity, vig structure, and price-discovery dynamics. The devigging methodology (§7.1) was applied identically to the DraftKings quote, but a small, unquantified cross-book difference should be assumed for this single match. All Final-match edge and ROI figures in this document carry this caveat; they are not perfectly apples-to-apples with the Kalshi-sourced figures elsewhere in the sample.

---

# PART III — CROSS-TOURNAMENT FINDINGS

## 15. Full ROI Breakdown

Hit rate alone does not evaluate a value-betting strategy correctly. `best_value` picks are deliberately chosen for the size of their edge (model probability − market probability), which is frequently largest on underdogs — a bet type expected to lose more often than it wins, but which should be profitable in aggregate if the edge is real, since the payout on a win is large relative to the stake.

The correct evaluation metric for `best_value` is therefore **realized ROI from flat-unit staking at the devigged market price**, not hit rate. Below is the full breakdown across all four model/stage combinations. All prices used are already devigged (§7.1) — ROI figures reflect true edge capture, not an artifact of platform vig.

| Model | Stage | N | Hit rate | Staked | Net P&L | ROI |
|---|---|---|---|---|---|---|
| Moneyline | Group Stage | 72 | 28/72 (38.9%) | 18.35u | +9.65u | **+52.6%** |
| Moneyline | Knockout | 32 | 15/32 (46.9%) | 11.98u | +3.02u | **+25.2%** |
| O/U | Group Stage | 55 | 25/55 (45.5%) | 26.99u | −1.99u | **−7.4%** |
| O/U | Knockout | 31 | 16/31 (51.6%) | 15.11u | +0.89u | **+5.9%** |

*(O/U figures use only actionable picks, excluding PASS/"No Play" rows, matching the tracker's own hit-rate grading. Knockout moneyline includes the Final; see §14 for the DraftKings caveat.)*

### 15.1 O/U: a clean before/after

The O/U comparison is the cleanest evidence of the diagnose-and-fix cycle in this project. Group-stage O/U value bets **lost money** (−7.4%) — consistent with the modifier-stack noise diagnosed in §10 corrupting both the pick and the edge estimate. After the modifiers were cut (§12), knockout O/U value bets turned modestly profitable (+5.9%). The direction of the fix, not just the model's internal accuracy metric, is what changed.

### 15.2 Moneyline ROI: real, but requires an important caveat

The moneyline `best_value` ROI figures are large — especially the group-stage +52.6%. Before treating this as a headline result, two checks were run:

**Is it driven by a single lucky bet?** No. Removing the single largest-payout win (Spain vs. Cabo Verde draw, priced at 6.86¢) only reduces group-stage ROI from 52.6% to 47.7%. The result is broad-based, not a one-bet artifact — the same check on knockout ROI shows the Final's Spain pick contributed a proportionally typical amount (+25.2% with it, +22.7% without), not an outsized share.

**Is it capturing a real edge, or printing a known bias?** This is the more important question, and the honest answer is more complicated. Reviewing the highest-payout group-stage wins shows a clear pattern: **the large majority are "Draw" picks in heavy-favorite mismatches** — Spain/Cabo Verde, Ecuador/Curaçao, Qatar/Switzerland, Portugal/DR Congo, England/Ghana, Belgium/Iran, among others. This is precisely the failure mode this project's own retrospective (§10) identified as a *miscalibration*: the model over-predicts draws in mismatches relative to actual draw frequency, and 70-80%-confidence favorites underperformed their predicted hit rate specifically because of these draws.

**What this means:** the group-stage ROI figure is real (the bets were placed at these prices and did win), but it should not be read as validation that the model's draw-heavy tendency in mismatches is a *correctly calibrated edge*. It is more accurate to describe it as: a documented miscalibration happened to be directionally profitable in this specific 72-match sample, because the underdogs in question specifically held on more often than either the model's stated confidence or the market's price implied. This is a meaningfully different (and weaker) claim than "the model found a persistent, well-calibrated edge in mismatched games," and the two should not be conflated in any external-facing summary of this project.

### 15.3 Sample-size caveats

- Knockout moneyline ROI (n=32) is sensitive to 2–3 large-payout wins (Paraguay at 14.85¢, Norway at 29.7¢); losing either would meaningfully compress the ROI figure, though it would likely remain positive.
- All ROI figures here are single-tournament results. No claim is made that these returns would replicate in a different sample, a different tournament, or over a longer time horizon.

---

## 16. What Changed Between Group Stage and Knockout Stage — Summary

| Element | Group Stage | Knockout Stage | Why it changed |
|---|---|---|---|
| Moneyline architecture | Hand-weighted scorecard (v0.2) | Regularized multinomial logistic regression | Sufficient sample (69+ matches) existed to fit weights properly; CV comparison showed the fitted model dominating (log-loss 0.661 vs. 0.854) |
| Draw handling | Flat heuristic on \|elo_diff\| | Empirically-tested draw-resilience term based on underdog defensive quality | Group-stage retrospective identified defensive-underdog draws as the specific, diagnosable failure mode |
| Home advantage | Real (listed home team) | Removed via symmetric/mirrored training; explicit host term only for USA/Mexico/Canada | Knockout matches are neutral-venue; the group-stage home-field assumption no longer applies |
| O/U architecture | Multiplicative modifier stack (conf scalar, tactical, climate, venue) | Direct xG blend + Monte Carlo parameter uncertainty | Modifiers diagnosed as adding noise, not signal (46% hit rate, below naive baseline) |
| Confidence calibration | Uncalibrated sigmoid | τ=1.35, fit to 5 real Kalshi prices | Raw model was mildly overconfident in large mismatches |

The throughline: both models were rebuilt in direct response to a specific, measured failure identified in the group-stage retrospective, not a general "let's improve things" pass. Each fix was tested against data before being adopted (the draw-resilience coefficient direction, the CV-driven architecture comparison, the temperature calibration against real prices) rather than assumed from theory.

---

## 17. Documented Limitations (Full List)

**Group stage:**
- Hand-weighted scorecard — weights not optimized via regression until knockout stage.
- xG availability varies by confederation; not fully normalized (mitigated, not corrected, by `weak_schedule_match`).
- Goal differential not opponent-adjusted.
- Draw probability heuristic under-weighted defensive-underdog draw risk in high-mismatch games — this is the headline diagnosed failure.
- O/U v0.3 situational factors (tactical, venue, climate) were uncalibrated and, per the retrospective, net-harmful to accuracy.
- `conf_scalar` CONMEBOL value (0.88) may be miscalibrated relative to top CONMEBOL teams' actual strength.
- New Zealand uses a goals-based xG fallback (no qualifier xG source).

**Knockout stage:**
- Penalty-xG sensitivity excluded from production (small-sample, large swings).
- Draw-resilience term based on n=35.
- τ=1.35 calibrated on 5 market prices only.
- No confederation/venue/climate adjustment in knockout O/U (deliberate simplification, disclosed tradeoff).
- Final match odds sourced from DraftKings, not Kalshi (§14).

**Cross-cutting:**
- All ROI figures are single-tournament, forward-tested results — not validated against a historical backtest with real historical market prices (none exist for Kalshi-equivalent contracts).
- The group-stage moneyline ROI figure, while real, is concentrated in draw-picks that reflect a documented model miscalibration rather than a validated, well-calibrated edge (§15.2).

---

## 18. Roadmap / Future Work

- Recalibrate `lambda_cv` in the knockout O/U model against realized tournament variance.
- Refit τ on a larger set of Kalshi to-advance prices as more become available.
- Investigate whether the draw-resilience coefficient generalizes to a larger out-of-tournament sample.
- Revisit whether any venue/climate signal should be reintroduced to knockout O/U in a properly-tested (not assumed) form.
- Correct the CONMEBOL `conf_scalar` value and re-evaluate its interaction with F1 Opta if confederation scalars are ever applied to moneyline.

---

## 19. Narrative Summary

This project's value is in the diagnostic and iterative cycle, not a claim of market-beating performance. Two models were built, forward-tested live against real Kalshi (and, for one match, DraftKings) prices, measured, found wanting in specific and identifiable ways, rebuilt with targeted and empirically-tested fixes, and re-measured. The knockout-stage improvements in both hit rate (moneyline 56.9%→65.6%/78.1%; O/U 45.5%→59%) and O/U ROI (−7.4%→+5.9%) are the evidence that the diagnosis-and-fix cycle worked. Where a result looked unusually strong (group-stage moneyline ROI), the underlying cause was investigated rather than accepted at face value, and the honest, more complicated explanation is reported here rather than the more flattering one.
