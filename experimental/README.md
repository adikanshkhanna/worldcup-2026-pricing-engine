# Experimental Models

This folder contains work-in-progress factor extensions NOT included in
the v1.0 frozen production model. These factors are built but excluded
pending calibration and backtest validation. They are stored here for
transparency and as a development roadmap reference.

**Do not use experimental outputs for live betting or interpret them
as model predictions.** Production model lives in /data.

## v0.3 — 10-factor extension
Adds F8 (climate), F9 (altitude/travel), F10 (tactical matchup) to the
v1.0 production factors. Weights are placeholders pending logistic
regression calibration on backtest sample.

Known issues with v0.3 (do not deploy):
- F8 weights uncalibrated
- F9 altitude penalty scale not validated
- F10 tactical matchup uses subjective tactical labels
- No backtest performance vs v1.0 baseline
