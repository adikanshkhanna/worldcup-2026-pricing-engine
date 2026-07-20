"""
Knockout over/under (total goals) pricing model — 2026 World Cup Pricing Engine.
Author: Adikansh Khanna

Round-agnostic: prices every fixture present in FIXTURES_FILE, whatever mix of
RO32 / RO16 / QF / SF / Third Place / Final rows that file currently contains.
There is no round-specific logic in this script — to price a new round, update
team_stats_knockout with post-round ratings and point FIXTURES_FILE at a CSV
containing that round's matches (or the full remaining bracket).

Architecture (see methodology.md S12): a direct xG blend with no confederation
scalar, tactical modifier, climate modifier, or venue penalty. The group-stage
O/U model (v0.3) used all of those; the retrospective found they added
systematic downward bias without improving accuracy (46% hit rate, below a
naive always-over baseline), so this knockout version deliberately drops them.

Rather than treating the resulting expected-goals estimate as a fixed number,
this script treats it as uncertain: it draws LAMBDA_CV-scaled noise around the
point estimate (Gamma-distributed) and simulates Poisson goal-scoring N_SIMS
times per match, reading over/under probabilities off the simulated
distribution rather than a single closed-form calculation. Setting
LAMBDA_CV = 0 collapses this back to the point estimate and should match the
closed-form Poisson CDF almost exactly (used as a sanity check below, run
automatically before every batch).

Usage:
    1. Make sure team_stats_knockout.csv reflects the ratings you want to
       price against (post-group-stage for RO32; post-round for later rounds).
    2. Point FIXTURES_FILE at a CSV with the matches you want to price. Any
       subset of the bracket works — this script doesn't care which round(s)
       are in it.
    3. Run. Results print to console and are also written to
       knockout_ou_sim_results.csv for pasting into the sheet.
"""

import numpy as np
import pandas as pd
from scipy.stats import poisson

pd.set_option('display.float_format', lambda x: f'{x:.4f}')

# ============================================================
# CONFIG
# ============================================================
N_SIMS = 10000
LAMBDA_CV = 0.20   # coefficient of variation on lambda; edit to tighten/loosen
RANDOM_SEED = 42   # set to None for a fresh random draw every run instead of a reproducible one

TEAM_STATS_FILE = '/content/WC Team Data Collection - team_stats_knockout.csv'
FIXTURES_FILE = '/content/WC Team Data Collection - knockout_stage_matches.csv'
OUTPUT_FILE = 'knockout_ou_sim_results.csv'

# ============================================================
# STEP 1: LOAD DATA
# ============================================================
team_stats = pd.read_csv(TEAM_STATS_FILE)
fixtures = pd.read_csv(FIXTURES_FILE)
ts = team_stats.set_index('team')

missing_teams = (set(fixtures['home_team']) | set(fixtures['away_team'])) - set(ts.index)
if missing_teams:
    print(f"WARNING: these teams aren't in team_stats_knockout, fix names before continuing: {missing_teams}")

if 'round' in fixtures.columns:
    rounds_present = sorted(fixtures['round'].dropna().unique().tolist())
    print(f"Pricing {len(fixtures)} fixture(s) across round(s): {rounds_present}")
else:
    print(f"Pricing {len(fixtures)} fixture(s) (no 'round' column present in {FIXTURES_FILE})")

rng = np.random.default_rng(RANDOM_SEED)


# ============================================================
# STEP 2: SIMULATION FUNCTION (single match, N_SIMS draws)
# ============================================================
def simulate_match(home_team, away_team, ou_line, n_sims=N_SIMS, lambda_cv=LAMBDA_CV):
    """
    Prices a single over/under market via Monte Carlo simulation.

    Expected goals use a direct 60/40 xG blend (own attack weighted 0.6,
    opponent's blended xG-against weighted 0.4) with no confederation,
    tactical, climate, or venue adjustment. See methodology.md S12.2.
    """
    home_base_lambda = ts.loc[home_team, 'xg_for_blend'] * 0.6 + ts.loc[away_team, 'xg_against_blend'] * 0.4
    away_base_lambda = ts.loc[away_team, 'xg_for_blend'] * 0.6 + ts.loc[home_team, 'xg_against_blend'] * 0.4

    if lambda_cv > 0:
        # Treat lambda as uncertain rather than a known fixed point estimate:
        # draw from a Gamma distribution with the target coefficient of
        # variation, then simulate Poisson goal-scoring from each draw.
        k = 1 / (lambda_cv ** 2)  # gamma shape param, derived from target CV
        home_lambda_draws = rng.gamma(shape=k, scale=home_base_lambda / k, size=n_sims)
        away_lambda_draws = rng.gamma(shape=k, scale=away_base_lambda / k, size=n_sims)
    else:
        # CV=0 collapses to a fixed lambda every draw — used as a sanity
        # check against the closed-form Poisson CDF (STEP 3 below).
        home_lambda_draws = np.full(n_sims, home_base_lambda)
        away_lambda_draws = np.full(n_sims, away_base_lambda)

    home_goals_sim = rng.poisson(home_lambda_draws)
    away_goals_sim = rng.poisson(away_lambda_draws)
    total_goals_sim = home_goals_sim + away_goals_sim

    over_prob = (total_goals_sim > ou_line).mean()
    under_prob = (total_goals_sim < ou_line).mean()

    return {
        'home_base_lambda': home_base_lambda,
        'away_base_lambda': away_base_lambda,
        'lambda_point_estimate': home_base_lambda + away_base_lambda,
        'sim_mean_total': total_goals_sim.mean(),
        'sim_median_total': np.median(total_goals_sim),
        'sim_std_total': total_goals_sim.std(),
        'over_prob': over_prob,
        'under_prob': under_prob,
        'pick': 'over' if over_prob > under_prob else 'under',
        'confidence': max(over_prob, under_prob),
    }


# ============================================================
# STEP 3: SANITY CHECK — sim with LAMBDA_CV=0 should match closed-form Poisson
# ============================================================
print("\n=== SANITY CHECK: sim (CV=0) vs closed-form Poisson, first fixture ===")
test_row = fixtures.iloc[0]
sim_check = simulate_match(test_row['home_team'], test_row['away_team'], test_row['ou_line'], lambda_cv=0)
analytic_over = 1 - poisson.cdf(int(test_row['ou_line']), sim_check['lambda_point_estimate'])
print(f"Sim over_prob (CV=0):   {sim_check['over_prob']:.4f}")
print(f"Closed-form over_prob:  {analytic_over:.4f}")
print(f"(should be very close — small gap is just sim noise at {N_SIMS} draws)\n")

# ============================================================
# STEP 4: RUN FULL BATCH WITH PARAMETER UNCERTAINTY (LAMBDA_CV from config)
# ============================================================
sim_results = []
for _, row in fixtures.iterrows():
    result = simulate_match(row['home_team'], row['away_team'], row['ou_line'])
    result.update({
        'match_id': row['match_id'],
        'home_team': row['home_team'],
        'away_team': row['away_team'],
        'ou_line': row['ou_line'],
    })
    if 'round' in row.index:
        result['round'] = row['round']
    sim_results.append(result)

out = pd.DataFrame(sim_results)

display_cols = [c for c in ['match_id', 'round', 'home_team', 'away_team'] if c in out.columns]
display_cols += ['ou_line', 'lambda_point_estimate', 'sim_mean_total',
                  'sim_std_total', 'over_prob', 'under_prob', 'pick', 'confidence']

print(f"=== {N_SIMS}-SIM RESULTS (lambda_cv={LAMBDA_CV}) ===")
print(out[display_cols].to_string(index=False))

out[display_cols].to_csv(OUTPUT_FILE, index=False)
print(f"\nSaved to {OUTPUT_FILE} — download from the Colab file panel, paste into the sheet.")

# ============================================================
# STEP 5: QUICK SPOT-CHECK HELPER — run one match on demand
# ============================================================
print("\n" + "=" * 60)
print("To check a single match ad hoc, run:")
print("simulate_match('TeamA', 'TeamB', 2.5)")
print("=" * 60)
