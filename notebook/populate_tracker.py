"""
Populate live_results_tracker from model_output_FROZEN.

One-time setup script. Run once before kickoff. After this:
- Headers will be in row 1
- All 48 group-stage matches will be pre-filled with model probs, picks, signals
- Auto-hit formulas will be in columns S and T
- Market prices, stakes, outcomes left blank to fill in live

Assumes model_output_FROZEN has columns including:
match_number, home_team, away_team, model_home_prob (or AS), draw_prob,
away_win_prob, model_pick, best_value, best_edge, signal.

Adjust SOURCE_COLS dict below if your column names differ.
"""

# =============================================================================
# CELL 1 — Setup (skip if already authed in same Colab session)
# =============================================================================

from google.colab import auth
import gspread
from google.auth import default
import pandas as pd

auth.authenticate_user()
creds, _ = default()
gc = gspread.authorize(creds)

SHEET_NAME = "WC Team Data Collection"
SOURCE_TAB = "model_output_FROZEN"        # change if yours is named differently
DEST_TAB   = "live_results_tracker"

sh = gc.open(SHEET_NAME)
print(f"Opened: {sh.title}")


# =============================================================================
# CELL 2 — Read source tab, inspect columns
# =============================================================================

src_ws = sh.worksheet(SOURCE_TAB)
src_records = src_ws.get_all_records()
src_df = pd.DataFrame(src_records)

print(f"Loaded {len(src_df)} rows from {SOURCE_TAB}")
print(f"\nColumns found:")
for c in src_df.columns:
    print(f"  - {c}")

# After you see the column names printed above, edit the SOURCE_COLS
# dict in the next cell to match them exactly.


# =============================================================================
# CELL 3 — Map source columns to tracker columns
# EDIT THIS dict to match your actual model_output_FROZEN column names
# =============================================================================

SOURCE_COLS = {
    # tracker_column        : source_column_name_in_model_output_FROZEN
    "match_id"              : "match_number",   # or "match_id" — check yours
    "home_team"             : "home_team",
    "away_team"             : "away_team",
    "model_home_prob"       : "home_win_prob",
    "model_draw_prob"       : "draw_prob",
    "model_away_prob"       : "away_win_prob",
    "model_pick"            : "model_pick",     # may be "pick" in yours
    "best_value"            : "best_value",
    "best_edge"             : "best_edge",
    "signal"                : "signal",
}

# Sanity check: verify all source columns exist
missing = [v for v in SOURCE_COLS.values() if v not in src_df.columns]
if missing:
    print(f"⚠️  Missing source columns: {missing}")
    print(f"Edit SOURCE_COLS dict to match the column names printed in Cell 2.")
else:
    print(f"✓ All {len(SOURCE_COLS)} source columns mapped successfully.")


# =============================================================================
# CELL 4 — Build the tracker rows
# =============================================================================

TRACKER_HEADERS = [
    "match_id", "date", "home_team", "away_team",
    "model_home_prob", "model_draw_prob", "model_away_prob",
    "market_home_prob", "market_draw_prob", "market_away_prob",
    "model_pick", "best_value", "best_edge", "signal",
    "stake", "side_bet", "entry_price",
    "actual_outcome", "model_pick_hit", "best_value_hit",
    "pnl", "clv",
]

# Build rows
tracker_rows = []
for _, src_row in src_df.iterrows():
    row = []
    for col in TRACKER_HEADERS:
        if col in SOURCE_COLS:
            row.append(src_row[SOURCE_COLS[col]])
        else:
            row.append("")   # blank for fields filled in live
    tracker_rows.append(row)

print(f"Built {len(tracker_rows)} rows.")
print(f"\nSample row 1:")
for h, v in zip(TRACKER_HEADERS, tracker_rows[0]):
    print(f"  {h:<22} = {v!r}")


# =============================================================================
# CELL 5 — Write to live_results_tracker (DESTRUCTIVE — clears existing data)
# =============================================================================

dest_ws = sh.worksheet(DEST_TAB)

# Clear existing content
dest_ws.clear()
print(f"Cleared {DEST_TAB}.")

# Write header + data
all_rows = [TRACKER_HEADERS] + tracker_rows
dest_ws.update("A1", all_rows, value_input_option="USER_ENTERED")
print(f"Wrote {len(all_rows)} rows (1 header + {len(tracker_rows)} matches).")


# =============================================================================
# CELL 6 — Add auto-hit formulas to columns S and T
# =============================================================================

n_matches = len(tracker_rows)
formula_rows = []
for i in range(2, n_matches + 2):  # rows 2 through n+1
    s_formula = (
        f'=IF(R{i}="","",'
        f'IF(OR('
        f'AND(R{i}="home",K{i}=C{i}),'
        f'AND(R{i}="away",K{i}=D{i}),'
        f'AND(R{i}="draw",LOWER(K{i})="draw")'
        f'),"Y","N"))'
    )
    t_formula = (
        f'=IF(R{i}="","",'
        f'IF(OR('
        f'AND(R{i}="home",L{i}=C{i}),'
        f'AND(R{i}="away",L{i}=D{i}),'
        f'AND(R{i}="draw",LOWER(L{i})="draw")'
        f'),"Y","N"))'
    )
    formula_rows.append([s_formula, t_formula])

dest_ws.update(f"S2:T{n_matches + 1}", formula_rows, value_input_option="USER_ENTERED")
print(f"Added auto-hit formulas to S2:T{n_matches + 1}")
print("\n✓ Setup complete. Open the sheet to verify, then ready for live data.")
