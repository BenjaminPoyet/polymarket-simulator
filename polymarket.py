import random

# ── Parameters ────────────────────────────────────────────────────────────────
CAPITAL_0        = 50.00   # Starting capital ($)
BET_SIZE         = 2.00    # Total dollars per bet (both sides combined)
SPREAD           = 0.02    # Market spread (2%)
THRESHOLD        = 0.75    # Sell trigger: sell loser when winner hits this
REVERSAL_PROB    = 0.20    # Probability market reverses after hitting threshold
N_BETS           = 100     # Number of sequential bets
ENTRY_PRICE      = 0.50    # Assumed balanced starting odds (50/50)

random.seed(42)

# ── Strategy mechanics ────────────────────────────────────────────────────────
# Buy Yes at (0.50 + spread/2) and No at (0.50 + spread/2) per share.
# Invest BET_SIZE/2 dollars in each side.
# When one side hits THRESHOLD, sell the LOSER at (1 - THRESHOLD).
# Hold the WINNER to resolution → pays $1/share (or $0 on reversal).

yes_ask = ENTRY_PRICE + SPREAD / 2          # 0.51
no_ask  = (1.0 - ENTRY_PRICE) + SPREAD / 2  # 0.51

n_yes = (BET_SIZE / 2) / yes_ask  # shares of Yes purchased
n_no  = (BET_SIZE / 2) / no_ask   # shares of No  purchased

# Payouts per outcome
success_pnl  = (n_no * (1.0 - THRESHOLD)) + (n_yes * 1.0) - BET_SIZE
reversal_pnl = (n_no * (1.0 - THRESHOLD)) + (n_yes * 0.0) - BET_SIZE

print("=" * 52)
print("  POLYMARKET DUAL-SIDE STRATEGY — SIMULATION")
print("=" * 52)
print(f"  Starting capital : ${CAPITAL_0:.2f}")
print(f"  Bet size (total) : ${BET_SIZE:.2f}  (${BET_SIZE/2:.2f} each side)")
print(f"  Spread           : {SPREAD*100:.1f}%")
print(f"  Exit threshold   : {THRESHOLD*100:.0f}%")
print(f"  Reversal prob    : {REVERSAL_PROB*100:.0f}%")
print(f"  Shares per side  : {n_yes:.4f}")
print(f"  P&L on success   : +${success_pnl:.4f}")
print(f"  P&L on reversal  : -${abs(reversal_pnl):.4f}")
ev = (1 - REVERSAL_PROB) * success_pnl + REVERSAL_PROB * reversal_pnl
print(f"  Expected value   : ${ev:+.4f} per bet")
print("=" * 52)
print()

# ── Run simulation ────────────────────────────────────────────────────────────
capital       = CAPITAL_0
wins          = 0
losses        = 0
total_profit  = 0.0
peak_capital  = capital
max_drawdown  = 0.0

print(f"{'Bet':>4}  {'Result':<10}  {'P&L':>8}  {'Capital':>9}  {'Drawdown':>9}")
print("-" * 52)

for i in range(1, N_BETS + 1):
    if capital < BET_SIZE:
        print(f"\n  Ran out of capital on bet {i}. Stopping.")
        break

    reversal = random.random() < REVERSAL_PROB

    if reversal:
        pnl    = reversal_pnl
        result = "REVERSAL"
        losses += 1
    else:
        pnl    = success_pnl
        result = "WIN"
        wins  += 1

    capital      += pnl
    total_profit += pnl

    # Track drawdown from peak
    if capital > peak_capital:
        peak_capital = capital
    drawdown = (peak_capital - capital) / peak_capital * 100

    if drawdown > max_drawdown:
        max_drawdown = drawdown

    # Print every bet (abbreviated for long runs, full for short)
    if N_BETS <= 100:
        marker = " <-- REVERSAL" if reversal else ""
        print(f"{i:>4}  {result:<10}  ${pnl:>+7.4f}  ${capital:>8.2f}  {drawdown:>8.1f}%{marker}")

# ── Summary ───────────────────────────────────────────────────────────────────
print("-" * 52)
print()
print("=" * 52)
print("  RESULTS SUMMARY")
print("=" * 52)
print(f"  Bets placed      : {wins + losses}")
print(f"  Wins             : {wins}  ({wins/(wins+losses)*100:.1f}%)")
print(f"  Reversals        : {losses}  ({losses/(wins+losses)*100:.1f}%)")
print(f"  Starting capital : ${CAPITAL_0:.2f}")
print(f"  Final capital    : ${capital:.2f}")
print(f"  Total P&L        : ${total_profit:+.2f}")
print(f"  Return           : {(capital - CAPITAL_0) / CAPITAL_0 * 100:+.1f}%")
print(f"  Peak capital     : ${peak_capital:.2f}")
print(f"  Max drawdown     : {max_drawdown:.1f}%")
print(f"  Avg P&L per bet  : ${total_profit / (wins + losses):+.4f}")
print("=" * 52)
