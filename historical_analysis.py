"""
Polymarket Historical Analysis
================================
Fetches closed binary markets, pulls YES-token price history, and
back-tests two dual-side exit rules.

Rule 1: After 70% of the market's lifespan has elapsed, sell the loser
        the first time the leading side reaches 75%.

Rule 2: Before 33% of the market's lifespan has elapsed, if either side
        hits 90%, sell that side immediately. Then wait for it to pull
        back to 85% and sell the other (loser) side at ~15%.

Entry assumption: buy 1 YES share at p_start + 1 NO share at (1 - p_start)
Total cost = $1.00 per market regardless of starting odds.
"""

import json
import sys
import time
import requests
from collections import defaultdict

# ── Config ─────────────────────────────────────────────────────────────────────
GAMMA_URL    = "https://gamma-api.polymarket.com/markets"
CLOB_URL     = "https://clob.polymarket.com/prices-history"

MAX_MARKETS  = 500
MIN_VOLUME   = 5_000    # skip illiquid markets
MIN_POINTS   = 8        # skip markets with barely any history
RATE_LIMIT   = 0.08     # seconds between CLOB requests

# Rule thresholds
R1_TIME      = 0.70     # sell after this fraction of time has elapsed
R1_PRICE     = 0.75     # sell when leader reaches this probability

R2_TIME      = 0.33     # early-trigger window (fraction)
R2_ENTRY     = 0.90     # sell winner when it hits this
R2_REVERT    = 0.85     # sell loser when winner reverts to this


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_prices(raw):
    """Return (yes_price, no_price) floats or raise ValueError."""
    prices = json.loads(raw) if isinstance(raw, str) else raw
    if not prices or len(prices) != 2:
        raise ValueError("not binary")
    return float(prices[0]), float(prices[1])


def fetch_closed_markets(limit=MAX_MARKETS):
    resp = requests.get(
        GAMMA_URL,
        params={"limit": limit, "closed": "true",
                "order": "volume", "ascending": "false"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_history(token_id):
    resp = requests.get(
        CLOB_URL,
        params={"market": token_id, "interval": "max", "fidelity": 60},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("history", [])


# ── Simulation helpers ─────────────────────────────────────────────────────────

def simulate_rule1(history, yes_wins):
    """
    Sell the loser once the leader hits R1_PRICE, but only after R1_TIME
    of the total duration has passed.

    Returns (pnl, triggered)
    """
    t0, t1 = history[0]["t"], history[-1]["t"]
    duration = t1 - t0
    if duration == 0:
        return 0.0, False

    trigger_t = t0 + R1_TIME * duration
    p_start   = history[0]["p"]
    cost      = 1.0  # p_start + (1 - p_start)

    for pt in history:
        t, p_yes = pt["t"], pt["p"]
        if t < trigger_t:
            continue

        p_no = 1.0 - p_yes

        if p_yes >= R1_PRICE:          # YES leading → sell NO
            loser_proceeds = p_no      # NO price right now
            winner_payout  = 1.0 if yes_wins else 0.0
            return (loser_proceeds + winner_payout) - cost, True

        if p_yes <= (1.0 - R1_PRICE):  # NO leading → sell YES
            loser_proceeds = p_yes
            winner_payout  = 1.0 if not yes_wins else 0.0
            return (loser_proceeds + winner_payout) - cost, True

    # Trigger never fired – hold both to resolution
    return 0.0, False


def simulate_rule2(history, yes_wins):
    """
    If either side hits R2_ENTRY before R2_TIME has elapsed:
      1. Sell that side immediately.
      2. Wait for it to pull back to R2_REVERT; when it does, sell the other.
      3. If no pull-back before resolution, hold the remaining side to close.

    Returns (pnl, triggered)
    """
    t0, t1 = history[0]["t"], history[-1]["t"]
    duration = t1 - t0
    if duration == 0:
        return 0.0, False

    window_t  = t0 + R2_TIME * duration
    cost      = 1.0

    # ── Phase 1: look for early 90% hit ─────────────────────────────────────
    trigger_idx  = None
    winner_is_yes = None
    winner_sold  = None

    for i, pt in enumerate(history):
        if pt["t"] > window_t:
            break
        p = pt["p"]
        if p >= R2_ENTRY:
            trigger_idx   = i
            winner_is_yes = True
            winner_sold   = p          # sold YES at this price
            break
        if p <= (1.0 - R2_ENTRY):
            trigger_idx   = i
            winner_is_yes = False
            winner_sold   = 1.0 - p    # sold NO at this price
            break

    if trigger_idx is None:
        return 0.0, False              # never triggered

    revenue = winner_sold

    # ── Phase 2: wait for reversion ─────────────────────────────────────────
    reversion_price = None
    for pt in history[trigger_idx + 1:]:
        p = pt["p"]
        if winner_is_yes:
            # sold YES; wait for YES to drop back to R2_REVERT → sell NO at ~15%
            if p <= R2_REVERT:
                reversion_price = 1.0 - p   # NO price at that moment
                break
        else:
            # sold NO; wait for NO to drop back to R2_REVERT (YES rises to 1 - R2_REVERT)
            if p >= (1.0 - R2_REVERT):
                reversion_price = p          # YES price at that moment
                break

    if reversion_price is not None:
        revenue += reversion_price
    else:
        # No reversion before resolution – hold remaining side to close
        if winner_is_yes:
            revenue += 1.0 if not yes_wins else 0.0   # hold NO to resolution
        else:
            revenue += 1.0 if yes_wins else 0.0       # hold YES to resolution

    return revenue - cost, True


# ── Aggregation ────────────────────────────────────────────────────────────────

class RuleStats:
    def __init__(self, name):
        self.name     = name
        self.total    = 0
        self.triggered = 0
        self.pnls     = []

    def record(self, pnl, triggered):
        self.total += 1
        if triggered:
            self.triggered += 1
            self.pnls.append(pnl)

    def summary(self):
        if not self.pnls:
            return {
                "Rule": self.name, "Markets": self.total,
                "Triggered": 0, "Trigger%": "0%",
                "Wins": 0, "Win Rate": "N/A",
                "Avg Profit": "N/A", "Avg Loss": "N/A",
                "Total P&L": "$0.00",
            }
        wins   = [p for p in self.pnls if p > 0]
        losses = [p for p in self.pnls if p <= 0]
        return {
            "Rule":       self.name,
            "Markets":    self.total,
            "Triggered":  self.triggered,
            "Trigger%":   f"{self.triggered / self.total * 100:.0f}%",
            "Wins":       len(wins),
            "Win Rate":   f"{len(wins) / len(self.pnls) * 100:.1f}%",
            "Avg Profit": f"${sum(wins)   / len(wins)   :.3f}" if wins   else "N/A",
            "Avg Loss":   f"${sum(losses) / len(losses):.3f}" if losses else "N/A",
            "Total P&L":  f"${sum(self.pnls):.3f}",
        }


def print_table(rows):
    if not rows:
        return
    keys = list(rows[0].keys())
    col_w = {k: max(len(k), max(len(str(r[k])) for r in rows)) for k in keys}
    sep   = "  ".join("-" * col_w[k] for k in keys)
    hdr   = "  ".join(k.ljust(col_w[k]) for k in keys)
    print(hdr)
    print(sep)
    for r in rows:
        print("  ".join(str(r[k]).ljust(col_w[k]) for k in keys))


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"Fetching up to {MAX_MARKETS} closed markets (min volume ${MIN_VOLUME:,})…")
    try:
        markets = fetch_closed_markets()
    except requests.exceptions.RequestException as e:
        print(f"[error] Could not fetch markets: {e}")
        sys.exit(1)

    print(f"  Got {len(markets)} markets from API")

    r1 = RuleStats("Rule 1  (sell loser @ 75% after 70% time)")
    r2 = RuleStats("Rule 2  (sell winner @ 90% early, revert @ 85%)")

    skipped_volume  = 0
    skipped_prices  = 0
    skipped_history = 0
    processed       = 0

    for i, m in enumerate(markets):

        # ── Volume filter ────────────────────────────────────────────────────
        volume = float(m.get("volume") or 0)
        if volume < MIN_VOLUME:
            skipped_volume += 1
            continue

        # ── Outcome prices → determine winner ───────────────────────────────
        try:
            yes_p, no_p = _parse_prices(m.get("outcomePrices"))
        except (TypeError, ValueError):
            skipped_prices += 1
            continue

        # Must be clearly resolved (one side ~0, other ~1)
        if not (yes_p >= 0.95 or no_p >= 0.95):
            skipped_prices += 1
            continue

        yes_wins = yes_p >= 0.95

        # ── Token IDs ───────────────────────────────────────────────────────
        ids_raw = m.get("clobTokenIds")
        if not ids_raw:
            skipped_prices += 1
            continue
        try:
            ids = json.loads(ids_raw) if isinstance(ids_raw, str) else ids_raw
            token_id = ids[0]
        except (TypeError, ValueError, IndexError):
            skipped_prices += 1
            continue

        # ── Price history ───────────────────────────────────────────────────
        try:
            history = fetch_history(token_id)
            time.sleep(RATE_LIMIT)
        except requests.exceptions.RequestException as e:
            skipped_history += 1
            continue

        if len(history) < MIN_POINTS:
            skipped_history += 1
            continue

        # ── Simulate ────────────────────────────────────────────────────────
        pnl1, trig1 = simulate_rule1(history, yes_wins)
        pnl2, trig2 = simulate_rule2(history, yes_wins)

        r1.record(pnl1, trig1)
        r2.record(pnl2, trig2)

        processed += 1
        pct = processed / max(len(markets) - skipped_volume, 1) * 100
        sys.stdout.write(
            f"\r  Processed {processed} markets  "
            f"(R1 triggered {r1.triggered}  R2 triggered {r2.triggered})   "
        )
        sys.stdout.flush()

    print(f"\n\nDone.  Skipped: {skipped_volume} low-volume, "
          f"{skipped_prices} bad prices, {skipped_history} no history.\n")

    # ── Summary table ────────────────────────────────────────────────────────
    print("=" * 80)
    print("  RESULTS SUMMARY")
    print("=" * 80)
    rows = [r1.summary(), r2.summary()]
    print_table(rows)
    print()

    # ── Per-rule detail ──────────────────────────────────────────────────────
    for stats in (r1, r2):
        s = stats.summary()
        print(f"  {stats.name}")
        print(f"    Markets processed : {s['Markets']}")
        print(f"    Triggered         : {s['Triggered']}  ({s['Trigger%']})")
        print(f"    Wins / Win rate   : {s['Wins']}  /  {s['Win Rate']}")
        print(f"    Avg profit (wins) : {s['Avg Profit']}")
        print(f"    Avg loss  (losses): {s['Avg Loss']}")
        print(f"    Total P&L         : {s['Total P&L']}  "
              f"(over {s['Triggered']} triggered trades, "
              f"${float(s['Total P&L'].replace('$',''))  / max(int(s['Triggered']),1):.3f} avg)")
        print()


if __name__ == "__main__":
    main()
