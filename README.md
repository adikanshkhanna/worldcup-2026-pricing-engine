# worldcup-2026-pricing-engine

A quantitative market-pricing model for 2026 FIFA World Cup event contracts (Kalshi), covering the full group stage and knockout rounds. Compares model-derived fair-value probabilities against devigged market prices to identify potential mispricings, across both moneyline ("who wins") and over/under ("total goals") markets.

Built as a collaborative project between **Kareem Soliman** and **Adikansh Khanna** (market analysis, feature/data design, calibration decisions, and results interpretation) with AI-assisted implementation for code and computation. The analytical work — what factors matter, how to weight them, how to diagnose and correct model failures, and how to evaluate results honestly — is the core of the project; see [Recruiting Context](#8-recruiting-context) below.

Full technical detail, including knockout-stage architecture, all forward-test results, and a transparent ROI analysis (including one result we investigated and chose *not* to feature as a headline number, for good reason) is in [`methodology.md`](./methodology.md).

---

## 1. Project Overview

Two markets, two model families, two tournament stages:

| Component | Stage | Version | Architecture |
|-----------|-------|---------|--------------|
| Moneyline | Group | v0.2 (frozen) | 4-factor weighted scorecard → sigmoid → renormalized win/draw/loss |
| Over/Under | Group | v0.3 (frozen) | Asymmetric xG weighting + tactical/venue/climate modifiers → Poisson |
| Moneyline | Knockout | Regularized multinomial logit | Fitted on group-stage results; symmetric (neutral-venue) training; empirically-tested draw-resilience term; market-calibrated temperature |
| Over/Under | Knockout | Simplified xG-blend + Monte Carlo | Direct xG blend, no modifier stack; 10,000-draw simulation with Gamma-distributed parameter uncertainty |

The knockout-stage models were rebuilt from the group-stage models in direct response to specific, diagnosed failures — not a general revision pass. See §4 and `methodology.md` §16 for what changed and why.

---

## 2. Market Pricing and Devigging

Raw Kalshi contract prices typically sum to 102–106¢ due to spread and platform fee. They're normalized proportionally before any comparison to model output:

```
market_home = kalshi_home_raw / (kalshi_home_raw + kalshi_draw_raw + kalshi_away_raw)
```

**Worked example (Match 1, Mexico vs. South Africa):** Raw Kalshi 70/21/12¢ → devigged 67.96%/20.39%/11.65%. Model: 59.35%/25.53%/15.12%. Edge on Draw: +5.14pp.

---

## 3. Signal Generation

```
edge_outcome = model_prob - market_prob
best_value   = outcome with the largest edge
```

| Signal | Condition |
|--------|-----------|
| STRONG PLAY | edge ≥ 10% |
| PLAY | edge ≥ 6% |
| WATCH | edge ≥ 3% |
| PASS | edge < 3% |
| REVIEW | edge ≥ 15% (flagged for manual input check) or draw-filter triggered |

`model_pick` (most likely outcome) and `best_value` (largest edge vs. market) are tracked separately — they frequently disagree, and evaluating them requires different lenses (see §5).

---

## 4. Results

### Group Stage (n=72 matches)

| Metric | Result |
|---|---|
| Moneyline `model_pick` hit rate | 41/72 (56.9%) |
| Moneyline calibration | Well-calibrated 0–70% predicted probability; miscalibrated 70–80% (predicted 75%, realized 56%) |
| O/U `model_pick` hit rate | 25/55 (45.5%), below coin-flip |

**Diagnosed failure modes:** the moneyline model's draw-probability heuristic under-weighted the risk of heavy favorites being held to draws by defensively organized underdogs (not upsets — draws). The O/U model's stacked tactical/climate/venue modifiers were found to add systematic downward bias without improving accuracy — a naive "always pick over" baseline would have beaten the model.

### Knockout Stage (n=32 matches, RO32 through Final)

| Metric | Result |
|---|---|
| Moneyline `model_90_pick` (regulation result) hit rate | 21/32 (65.6%) |
| Moneyline `model_adv_pick` (to-advance market) hit rate | 25/32 (78.1%) |
| O/U `model_pick` hit rate | 19/32 (59%) |

Both models were rebuilt in direct response to the group-stage failure modes above, and both improved. Full methodology, including the regularized-logit architecture, the draw-resilience term (tested against real data before being added), market-calibrated temperature scaling, and the O/U model's move to a simplified Monte Carlo architecture, is documented in `methodology.md` Part II.

---

## 5. On Evaluating `best_value`: Hit Rate vs. ROI

A model that intentionally targets underpriced longshots is *expected* to have a hit rate below 50% — most of those bets lose, by design. The correct evaluation metric is flat-unit ROI at the market price, not raw hit rate. We computed this across all four model/stage combinations:

| Model | Stage | Hit rate | ROI (flat units, devigged price) |
|---|---|---|---|
| Moneyline | Group | 38.9% | +52.6% |
| Moneyline | Knockout | 46.9% | +25.2% |
| O/U | Group | 45.5% | −7.4% |
| O/U | Knockout | 51.6% | +5.9% |

The O/U comparison is the clean story here: group-stage O/U value bets lost money, consistent with the diagnosed modifier-noise bias; after that bias was cut for the knockout rebuild, O/U value bets turned modestly profitable. That's the diagnose-and-fix cycle showing up directly in the P&L, not just in an internal accuracy metric.

**The moneyline ROI numbers required a closer look before we'd stand behind them.** The group-stage +52.6% figure is real and not a single-bet artifact (removing the single largest win only brings it to +47.7%), but reviewing *which* bets drove it revealed something worth being upfront about: most of the largest-payout wins were "Draw" picks in heavy-favorite mismatches — exactly the pattern our own retrospective flagged as a model miscalibration, not a validated edge. In other words, a known flaw happened to be profitable in this specific 72-match sample; that's a different and weaker claim than "the model found a real, well-calibrated edge," and we're not presenting it as the latter. Full discussion in `methodology.md` §15.2.

---

## 6. Risk Controls

- **CHECK INPUTS** — fires when model-market disagreement exceeds 15%, since a gap that large usually means a stale price or bad input rather than a real edge.
- **BLOCK DRAW** — suppresses false-positive draw signals in heavy-mismatch games where the draw heuristic overshoots.
- **Weak Schedule Flag** — surfaces cross-confederation matchups where xG comparability may be distorted.

---

## 7. Data Note: Final Match Odds

The Final's market odds were sourced from **DraftKings**, not Kalshi (the source for every other match), due to a data-collection gap. The same devigging methodology was applied, but a small, unquantified cross-book difference should be assumed for this one match. Disclosed in full in `methodology.md` §14.

---

## 8. Recruiting Context

This project was built to demonstrate market-analysis and quantitative-reasoning skills relevant to finance roles — not as a software engineering exercise. The skills on display:

- **Probabilistic reasoning under uncertainty** — translating team-performance data into calibrated fair-value probabilities, and distinguishing a well-calibrated model from a merely accurate one.
- **Market microstructure literacy** — devigging, edge calculation, and understanding why hit rate and ROI answer different questions for a value-betting strategy.
- **Diagnostic rigor and honest iteration** — every model change in this project traces back to a specific, measured failure (documented, not glossed over), and every proposed fix was tested against real data before being adopted.
- **Calibration and risk judgment** — recognizing when a strong-looking result (the group-stage moneyline ROI) needed further scrutiny before being presented, and reporting the more complicated, more honest explanation instead of the more flattering one.
- **Financial modeling logic** — factor-based scoring, regularization/cross-validation discipline to avoid overfitting a small sample, and structured risk controls (CHECK INPUTS, BLOCK DRAW) analogous to trading-desk sanity checks.

The full quantitative build — regression fitting, Monte Carlo simulation, and the underlying code — was implemented with AI assistance. The modeling decisions, diagnostic work, and evaluation judgment throughout were not.

---

## 9. File Structure

```
worldcup-2026-pricing-engine/
├── README.md
├── methodology.md
├── LICENSE
├── data/
│   ├── team_stats.csv
│   ├── team_stats_knockout.csv
│   ├── model_inputs_v02_FROZEN.csv
│   ├── model_outputs.csv
│   ├── ou_model_v03.csv
│   ├── ou_model_vo2_FROZEN.csv
│   ├── ml_knockout_model.csv
│   ├── ou_knockout_model.csv
│   ├── live_results_tracker.csv
│   └── methodology_notes.csv
└── notebook/
    ├── populate_tracker.py
    ├── analysis.py
    └── knockout_ou_simulation.py
```

---

## 10. Performance Tracking

Live forward-test results for the full 2026 tournament (group stage + knockout) are in [`data/live_results_tracker.csv`](./data/live_results_tracker.csv) and the knockout-specific model files. Full breakdown, calibration tables, and the ROI analysis discussed in §5 are in [`methodology.md`](./methodology.md).
