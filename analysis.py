"""
WC2026 Pricing Engine — Live Results Analysis
=============================================

Colab notebook that ingests live_results_tracker from Google Sheets and outputs:
- Cumulative hit rate (model_pick + best_value)
- Hit rate by signal type
- Hit rate by probability bucket (calibration)
- P&L and CLV
- Calibration plot

Run cell-by-cell in Colab. Re-run after every match day.

SCHEMA EXPECTED (in live_results_tracker tab):
match_id | date | home_team | away_team |
model_home_prob | model_draw_prob | model_away_prob |
market_home_prob | market_draw_prob | market_away_prob |
model_pick | best_value | best_edge | signal |
stake | side_bet | entry_price |
actual_outcome (home/draw/away) | model_pick_hit (Y/N) | best_value_hit (Y/N) |
pnl | clv
"""

# =============================================================================
# CELL 1 — Setup and Authentication
# =============================================================================

from google.colab import auth
import gspread
from google.auth import default
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

auth.authenticate_user()
creds, _ = default()
gc = gspread.authorize(creds)

# CHANGE THIS to match your sheet name exactly
SHEET_NAME = "WC Team Data Collection"
sh = gc.open(SHEET_NAME)
print(f"Opened sheet: {sh.title}")


# =============================================================================
# CELL 2 — Load Tracker and Filter to Completed Matches
# =============================================================================

ws = sh.worksheet("live_results_tracker")
records = ws.get_all_records()
df = pd.DataFrame(records)
print(f"Loaded {len(df)} tracker rows")

# Filter to matches that have been played (actual_outcome is filled)
df_done = df[df["actual_outcome"].astype(str).str.strip() != ""].copy()
print(f"{len(df_done)} matches have results")

if len(df_done) == 0:
    print("\nNo completed matches yet — nothing to analyze. Come back after Match 1.")
else:
    # Coerce numeric columns
    numeric_cols = [
        "model_home_prob", "model_draw_prob", "model_away_prob",
        "market_home_prob", "market_draw_prob", "market_away_prob",
        "best_edge", "stake", "entry_price", "pnl", "clv"
    ]
    for col in numeric_cols:
        if col in df_done.columns:
            df_done[col] = pd.to_numeric(df_done[col], errors="coerce")

    # Standardize hit columns to booleans
    df_done["mp_hit"] = df_done["model_pick_hit"].astype(str).str.upper().str.strip() == "Y"
    df_done["bv_hit"] = df_done["best_value_hit"].astype(str).str.upper().str.strip() == "Y"

    print(f"Sample:\n{df_done[['match_id','home_team','away_team','signal','model_pick','best_value','actual_outcome','mp_hit','bv_hit']].head(10)}")


# =============================================================================
# CELL 3 — Hit Rates: Overall + By Signal
# =============================================================================

if len(df_done) > 0:
    print("=" * 60)
    print("HIT RATES")
    print("=" * 60)

    # Overall
    mp_rate = df_done["mp_hit"].mean()
    bv_rate = df_done["bv_hit"].mean()
    n = len(df_done)
    print(f"\nOverall (n={n}):")
    print(f"  model_pick:  {mp_rate:.1%}  ({df_done['mp_hit'].sum()}/{n})")
    print(f"  best_value:  {bv_rate:.1%}  ({df_done['bv_hit'].sum()}/{n})")

    # By signal
    print(f"\nBy signal tier:")
    print(f"  {'Signal':<14} {'n':>4}  {'model_pick':>12}  {'best_value':>12}")
    print(f"  {'-'*14} {'-'*4}  {'-'*12}  {'-'*12}")
    for sig in ["STRONG PLAY", "PLAY", "WATCH", "PASS", "REVIEW"]:
        sub = df_done[df_done["signal"] == sig]
        if len(sub) > 0:
            mp = sub["mp_hit"].mean()
            bv = sub["bv_hit"].mean()
            print(f"  {sig:<14} {len(sub):>4}  {mp:>11.1%}  {bv:>11.1%}")
        else:
            print(f"  {sig:<14} {0:>4}  {'—':>12}  {'—':>12}")

    # Draw-specific (per methodology — draws are most fragile)
    print(f"\nDraw recommendations (best_value = 'Draw'):")
    draw_picks = df_done[df_done["best_value"].astype(str).str.lower() == "draw"]
    if len(draw_picks) > 0:
        rate = draw_picks["bv_hit"].mean()
        print(f"  n={len(draw_picks)}, hit rate: {rate:.1%}")
    else:
        print(f"  No draw recommendations yet.")


# =============================================================================
# CELL 4 — Calibration by Probability Bucket
# =============================================================================

if len(df_done) > 0:
    # Get the model probability assigned to the model_pick
    def pick_prob(row):
        if row["model_pick"] == row["home_team"]:
            return row["model_home_prob"]
        elif row["model_pick"] == row["away_team"]:
            return row["model_away_prob"]
        elif str(row["model_pick"]).lower() == "draw":
            return row["model_draw_prob"]
        return np.nan

    df_done["pick_prob"] = df_done.apply(pick_prob, axis=1)

    print("\n" + "=" * 60)
    print("CALIBRATION (predicted vs realized for model_pick)")
    print("=" * 60)

    buckets = [(0.30, 0.40), (0.40, 0.50), (0.50, 0.60),
               (0.60, 0.70), (0.70, 0.80), (0.80, 1.01)]

    print(f"\n  {'Bucket':<12} {'n':>4}  {'Predicted':>11}  {'Realized':>11}  {'Delta':>8}")
    print(f"  {'-'*12} {'-'*4}  {'-'*11}  {'-'*11}  {'-'*8}")

    calib_data = []
    for low, high in buckets:
        sub = df_done[(df_done["pick_prob"] >= low) & (df_done["pick_prob"] < high)]
        if len(sub) > 0:
            pred = sub["pick_prob"].mean()
            real = sub["mp_hit"].mean()
            delta = real - pred
            print(f"  {low:>4.0%}-{high:>3.0%}    {len(sub):>4}  {pred:>10.1%}  {real:>10.1%}  {delta:>+7.1%}")
            calib_data.append((pred, real, len(sub)))
        else:
            print(f"  {low:>4.0%}-{high:>3.0%}    {0:>4}  {'—':>11}  {'—':>11}  {'—':>8}")


# =============================================================================
# CELL 5 — P&L and CLV
# =============================================================================

if len(df_done) > 0:
    bets = df_done[df_done["stake"].notna() & (df_done["stake"] > 0)].copy()

    print("\n" + "=" * 60)
    print("P&L AND CLV")
    print("=" * 60)

    if len(bets) == 0:
        print("\nNo bets placed yet.")
    else:
        total_pnl = bets["pnl"].sum()
        total_stake = bets["stake"].sum()
        roi = total_pnl / total_stake if total_stake > 0 else 0
        win_count = (bets["pnl"] > 0).sum()

        print(f"\nBets placed: {len(bets)}")
        print(f"Total staked: {total_stake:.2f}u")
        print(f"Cumulative P&L: {total_pnl:+.2f}u")
        print(f"Win rate (bets): {win_count}/{len(bets)} = {win_count/len(bets):.1%}")
        print(f"ROI: {roi:+.1%}")

        if "clv" in bets.columns:
            clv_data = bets["clv"].dropna()
            if len(clv_data) > 0:
                mean_clv = clv_data.mean()
                positive_clv_pct = (clv_data > 0).mean()
                print(f"\nMean CLV: {mean_clv:+.2f}¢")
                print(f"Positive CLV: {positive_clv_pct:.1%} of bets")
                print(f"(Positive CLV indicates beating the closing line — pro-bettor metric)")

        # By signal tier
        print(f"\nP&L by signal:")
        for sig in ["STRONG PLAY", "PLAY", "WATCH"]:
            sub = bets[bets["signal"] == sig]
            if len(sub) > 0:
                pnl_sub = sub["pnl"].sum()
                stake_sub = sub["stake"].sum()
                roi_sub = pnl_sub / stake_sub if stake_sub > 0 else 0
                print(f"  {sig:<14} n={len(sub):>3}  P&L={pnl_sub:+.2f}u  ROI={roi_sub:+.1%}")


# =============================================================================
# CELL 6 — Calibration Plot
# =============================================================================

if len(df_done) > 0 and len(calib_data) >= 2:
    pred_vals = [x[0] for x in calib_data]
    real_vals = [x[1] for x in calib_data]
    sizes = [x[2] * 80 for x in calib_data]  # dot size scales with sample count

    plt.figure(figsize=(7, 7))
    plt.plot([0, 1], [0, 1], "k--", alpha=0.5, linewidth=1, label="Perfect calibration")
    plt.scatter(pred_vals, real_vals, s=sizes, alpha=0.6, c="steelblue",
                edgecolors="navy", linewidths=1.5, label="Observed")

    # Annotate sample sizes
    for pred, real, n in calib_data:
        plt.annotate(f"n={n}", (pred, real), xytext=(8, 8),
                     textcoords="offset points", fontsize=9)

    plt.xlim(0.25, 1.0)
    plt.ylim(0.0, 1.0)
    plt.xlabel("Predicted probability (mean of bucket)")
    plt.ylabel("Realized hit rate")
    plt.title(f"v0.2 Model Calibration — model_pick ({len(df_done)} matches)")
    plt.legend(loc="upper left")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.show()

    print("\nReading the plot:")
    print("  Dots ABOVE the diagonal → model is UNDERconfident (real win rate exceeds prediction)")
    print("  Dots BELOW the diagonal → model is OVERconfident (predictions exceed real win rate)")
    print("  Dots ON the diagonal → well calibrated")
elif len(df_done) > 0:
    print("\nNot enough buckets with data yet for a calibration plot (need ≥2).")


# =============================================================================
# CELL 7 — One-Line Daily Summary (paste into your notes)
# =============================================================================

if len(df_done) > 0:
    summary = (
        f"WC2026 v0.2 — through {len(df_done)} matches: "
        f"model_pick {df_done['mp_hit'].mean():.0%} | "
        f"best_value {df_done['bv_hit'].mean():.0%}"
    )
    bets = df_done[df_done["stake"].notna() & (df_done["stake"] > 0)]
    if len(bets) > 0:
        summary += (
            f" | P&L {bets['pnl'].sum():+.1f}u over {len(bets)} bets "
            f"(ROI {bets['pnl'].sum()/bets['stake'].sum():+.0%})"
        )
        if "clv" in bets.columns and bets["clv"].notna().any():
            summary += f" | mean CLV {bets['clv'].mean():+.1f}¢"

    print("\n" + "=" * 60)
    print("DAILY SUMMARY")
    print("=" * 60)
    print(summary)
