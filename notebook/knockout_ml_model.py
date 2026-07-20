"""
Knockout moneyline pricing model — 2026 World Cup Pricing Engine.
Author: Kareem Soliman

Fits a regularized multinomial logistic regression on graded group-stage
matches (69 of 72; New Zealand excluded for missing xG), using symmetric
(mirrored) training so neutral-venue knockout matches carry no artificial
home-listing bias. Applies a market-calibrated temperature (tau=1.35, fit
against 5 real Kalshi to-advance prices — see methodology.md S11.5) and an
empirically-tested draw-resilience adjustment (methodology.md S11.4) before
converting to advance probabilities.

Writes ONLY model_home / model_draw / model_away / model_home_adv /
model_away_adv for the row range specified below. Does not touch any other
column or any other round's rows.

Usage:
    1. Freeze `team_stats_knockout` to the values you want to price against
       BEFORE running this script.
    2. Set ROW_RANGE below to the sheet rows for the round you're pricing.
    3. Run once with WRITE_BACK = False to dry-run and inspect output.
    4. Set WRITE_BACK = True and re-run to commit.
"""

import numpy as np
import pandas as pd
import gspread
from google.colab import auth
from google.auth import default

# ============================================================
# CONFIG
# ============================================================
SHEET = "WC Team Data Collection"
STATS_TAB = "team_stats_knockout"
TRACKER_TAB = "live_results_tracker"
KO_TAB = "ml_knockout_model"

L2 = 0.5          # L2 regularization strength, chosen via 5-fold CV log-loss
K_DEF = 0.16      # draw-resilience boost magnitude (methodology.md S11.4)
TAU = 1.35        # temperature, calibrated against 5 Kalshi advance prices (S11.5)

# Sheet rows for the round currently being priced. Update this per round —
# e.g. RO32 = rows 2-17, RO16 = rows 18-21, QF = rows 22-25, SF/3rd/Final = 26-29.
# Only rows in this range are read and written; all other rows are untouched.
ROW_RANGE = range(1, 34)

WRITE_BACK = False  # set True only after reviewing dry-run output

# ============================================================
# STEP 1: CONNECT AND LOAD FROZEN KNOCKOUT TEAM RATINGS
# ============================================================
auth.authenticate_user()
creds, _ = default()
gc = gspread.authorize(creds)
book = gc.open(SHEET)

ks = pd.DataFrame(book.worksheet(STATS_TAB).get_all_records()).set_index("team")


def num(x):
    try:
        return float(str(x).replace("%", ""))
    except (ValueError, TypeError):
        return np.nan


for c in ["elo_ko", "gd_blend", "xg_for_blend", "xg_against_blend", "form_blend", "xgot_gs"]:
    if c in ks.columns:
        ks[c] = ks[c].map(num)


def kv(team, col):
    return ks.loc[team, col] if team in ks.index else np.nan


HOSTS = {"Mexico", "United States", "USA", "Canada"}


def is_host(team):
    return 1.0 if team in HOSTS else 0.0


def defensive_xga(team):
    return kv(team, "xg_against_blend")


def knockout_features(home, away):
    """Feature vector for a knockout matchup, from frozen post-group-stage ratings."""
    xg_net_home = kv(home, "xg_for_blend") - kv(home, "xg_against_blend")
    xg_net_away = kv(away, "xg_for_blend") - kv(away, "xg_against_blend")
    return np.array([
        kv(home, "elo_ko") - kv(away, "elo_ko"),
        kv(home, "gd_blend") - kv(away, "gd_blend"),
        xg_net_home - xg_net_away,
        kv(home, "form_blend") - kv(away, "form_blend"),
        is_host(home) - is_host(away),
    ], dtype=float)


# ============================================================
# STEP 2: FIT WEIGHTS ON GRADED GROUP-STAGE MATCHES
#          (fit source is team_stats, NOT team_stats_knockout —
#           the fit happens once, on pre-knockout data, and is frozen)
# ============================================================
gs = pd.DataFrame(book.worksheet("team_stats").get_all_records())
gs = gs.rename(columns={
    "gd_last5 (avg)": "gd",
    "xg_for (p90)": "xgf",
    "xg_against (p90)": "xga",
}).set_index("team_id")

for c in ["elo", "gd", "xgf", "xga", "form_pts"]:
    if c in gs.columns:
        gs[c] = gs[c].map(num)


def gv(team, col):
    return gs.loc[team, col] if team in gs.index else np.nan


def is_host_gs(team):
    return 1.0 if str(gv(team, "is_host")).strip().upper() == "YES" else 0.0


def group_stage_features(home, away):
    return np.array([
        gv(home, "elo") - gv(away, "elo"),
        gv(home, "gd") - gv(away, "gd"),
        (gv(home, "xgf") - gv(home, "xga")) - (gv(away, "xgf") - gv(away, "xga")),
        gv(home, "form_pts") - gv(away, "form_pts"),
        is_host_gs(home) - is_host_gs(away),
    ], dtype=float)


tracker = pd.DataFrame(book.worksheet(TRACKER_TAB).get_all_records())

rows, labels = [], []
for _, match in tracker.iterrows():
    home, away = match.get("home_team"), match.get("away_team")
    result = str(match.get("result")).strip().lower()

    if result not in ("home", "draw", "away"):
        continue
    if home not in gs.index or away not in gs.index:
        continue

    x = group_stage_features(home, away)
    if np.isnan(x).any():
        continue

    label = {"home": 0, "draw": 1, "away": 2}[result]

    # Symmetric (mirrored) training: include the match and its negated mirror
    # with swapped outcome, so the fitted intercept carries zero home-listing
    # bias — appropriate for knockout matches, which are neutral-venue.
    rows.append(x)
    labels.append(label)
    rows.append(-x)
    labels.append({0: 2, 1: 1, 2: 0}[label])

X = np.array(rows)
y = np.array(labels)

feature_mean, feature_std = X.mean(0), X.std(0)
feature_std[feature_std == 0] = 1
X_design = np.column_stack([np.ones(len(X)), (X - feature_mean) / feature_std])


def fit_multinomial_logit(X_design, y, l2, n_iter=6000, lr=0.25, n_classes=3):
    """Regularized multinomial logistic regression via batch gradient descent."""
    n, p = X_design.shape
    W = np.zeros((n_classes, p))
    Y_onehot = np.zeros((n, n_classes))
    Y_onehot[np.arange(n), y] = 1

    for _ in range(n_iter):
        logits = X_design @ W.T
        logits -= logits.max(axis=1, keepdims=True)
        probs = np.exp(logits)
        probs /= probs.sum(axis=1, keepdims=True)
        W -= lr * ((probs - Y_onehot).T @ X_design / n + l2 * W / n)

    return W


W = fit_multinomial_logit(X_design, y, L2)

# Defensive-quality stats (for the draw-resilience adjustment), computed
# across the currently-frozen knockout team pool.
defensive_ratings = np.array([
    defensive_xga(t) for t in ks.index if not np.isnan(defensive_xga(t))
])
defense_mean, defense_std = (
    (defensive_ratings.mean(), defensive_ratings.std()) if len(defensive_ratings) else (np.nan, 1.0)
)
gap_scale = X[:, 0].std()  # typical elo-gap magnitude, for scaling the draw boost

# ============================================================
# STEP 3: PREDICT — 1X2, then to-advance via shootout formula
# ============================================================
def predict(home, away):
    x = knockout_features(home, away)
    if np.isnan(x).any():
        return None

    v = np.concatenate([[1], (x - feature_mean) / feature_std])
    logits = (W @ v) / TAU
    logits -= logits.max()
    probs = np.exp(logits)
    probs /= probs.sum()
    p_home, p_draw, p_away = probs

    # Draw-resilience adjustment: boost draw probability when the underdog
    # has a strong (low) blended defensive xGA relative to the field, scaled
    # by how large the rating gap is. See methodology.md S11.4.
    favorite_is_home = x[0] >= 0
    underdog = away if favorite_is_home else home
    underdog_xga = defensive_xga(underdog)

    if not np.isnan(underdog_xga) and not np.isnan(defense_mean):
        defense_z = (defense_mean - underdog_xga) / defense_std
        gap_z = min(1.0, max(0.0, (abs(x[0]) - gap_scale) / gap_scale))
        boost = min(
            max(0.0, K_DEF * defense_z) * gap_z,
            0.9 * (p_home if favorite_is_home else p_away),
        )
        if favorite_is_home:
            p_home -= boost
        else:
            p_away -= boost
        p_draw += boost

    # To-advance probability via shootout formula (methodology.md S11.6).
    shootout_win_prob = min(0.60, max(0.40, 0.5 + (p_home - p_away) * 0.25))
    p_home_advance = p_home + p_draw * shootout_win_prob
    p_away_advance = 1 - p_home_advance

    return p_home, p_draw, p_away, p_home_advance, p_away_advance


# ============================================================
# STEP 4: RUN FOR THE TARGET ROUND, PREVIEW, OPTIONALLY WRITE BACK
# ============================================================
ko_sheet = book.worksheet(KO_TAB)
header = ko_sheet.row_values(1)
km = pd.DataFrame(
    ko_sheet.get_all_records(expected_headers=[h for h in header if h.strip() != ""])
)

print(f"{'row':>4} {'match':27}{'Ph':>5}{'Pd':>5}{'Pa':>5}{'advH':>6}{'advA':>6}  sum")

predictions = {}
for sheet_row in ROW_RANGE:
    i = sheet_row - 2  # header is row 1
    home = km.iloc[i].get("home_team")
    away = km.iloc[i].get("away_team")

    result = predict(home, away)
    if result is None:
        print(f"{sheet_row:>4} {str(home)} v {str(away)}  SKIP (missing data)")
        continue

    predictions[sheet_row] = result
    p_home, p_draw, p_away, adv_home, adv_away = result
    label = f"{str(home)} v {str(away)}"[:26]
    print(
        f"{sheet_row:>4} {label:27}"
        f"{p_home:>5.0%}{p_draw:>5.0%}{p_away:>5.0%}"
        f"{adv_home:>6.0%}{adv_away:>6.0%}  {p_home + p_draw + p_away:.2f}"
    )

if WRITE_BACK and predictions:
    def col_letter(idx):
        letters = ""
        while idx > 0:
            idx, remainder = divmod(idx - 1, 26)
            letters = chr(65 + remainder) + letters
        return letters

    target_cols = {
        c: col_letter(header.index(c) + 1)
        for c in ["model_home", "model_draw", "model_away", "model_home_adv", "model_away_adv"]
    }

    for sheet_row, (p_home, p_draw, p_away, adv_home, adv_away) in predictions.items():
        ko_sheet.update(f"{target_cols['model_home']}{sheet_row}", [[round(p_home, 4)]])
        ko_sheet.update(f"{target_cols['model_draw']}{sheet_row}", [[round(p_draw, 4)]])
        ko_sheet.update(f"{target_cols['model_away']}{sheet_row}", [[round(p_away, 4)]])
        ko_sheet.update(f"{target_cols['model_home_adv']}{sheet_row}", [[round(adv_home, 4)]])
        ko_sheet.update(f"{target_cols['model_away_adv']}{sheet_row}", [[round(adv_away, 4)]])

    print(f"\nWrote {len(predictions)} rows to {KO_TAB}. Rows outside ROW_RANGE untouched.")
else:
    print("\nDRY RUN — nothing written. Set WRITE_BACK = True to commit.")
