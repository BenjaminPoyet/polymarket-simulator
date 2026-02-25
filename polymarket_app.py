import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import requests
import pandas as pd
import json

st.set_page_config(page_title="Polymarket Simulator", layout="wide")

# ── Theme ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Main background */
.stApp { background-color: #0e1117; }

/* Sidebar */
[data-testid="stSidebar"] {
    background-color: #0d1117;
    border-right: 1px solid #21262d;
}

/* Metric cards */
[data-testid="metric-container"] {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 18px 20px;
}
[data-testid="metric-container"] label {
    color: #8b949e !important;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #e6edf3 !important;
    font-size: 1.5rem;
    font-weight: 600;
}
[data-testid="metric-container"] [data-testid="stMetricDelta"] {
    font-size: 0.82rem;
}

/* Divider */
hr { border-color: #21262d !important; }

/* Dataframe */
[data-testid="stDataFrame"] { border: 1px solid #30363d; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

st.title("Polymarket Dual-Side Strategy Simulator")

# ── Sliders (sidebar) ──────────────────────────────────────────────────────────
st.sidebar.header("Strategy Parameters")
spread        = st.sidebar.slider("Spread",                  0.5,  5.0,  2.0, 0.5, format="%.1f%%") / 100
reversal_prob = st.sidebar.slider("Reversal Probability",    0,    50,   10,  5,   format="%d%%")   / 100
illiquid_prob = st.sidebar.slider("Illiquidity Probability", 0,    50,   5,   5,   format="%d%%")   / 100
n_bets        = st.sidebar.slider("Number of Bets",          10,   500,  100, 10)

# ── Constants ──────────────────────────────────────────────────────────────────
CAPITAL_0    = 50.0
BET_FRACTION = 0.12
THRESHOLD    = 0.75
ENTRY_PRICE  = 0.50
N_SIMS       = 300

# ── Simulation ─────────────────────────────────────────────────────────────────
# Strategy mechanics:
#   • Buy Yes at (0.50 + spread/2), No at (0.50 + spread/2)
#   • When threshold hit: sell loser at (1 - threshold) = 25¢
#   • Illiquidity: loser can't be sold → recover 0¢ instead of 25¢
#   • Reversal: "winner" resolves to $0 instead of $1

yes_ask = ENTRY_PRICE + spread / 2
no_ask  = (1.0 - ENTRY_PRICE) + spread / 2

def simulate(seed):
    rng     = np.random.default_rng(seed)
    capital = CAPITAL_0
    history = np.empty(n_bets + 1)
    history[0] = capital

    for t in range(n_bets):
        if capital < 0.50:
            history[t + 1:] = capital
            break

        bet   = capital * BET_FRACTION
        n_yes = (bet / 2) / yes_ask
        n_no  = (bet / 2) / no_ask

        reversal = rng.random() < reversal_prob
        illiquid = rng.random() < illiquid_prob

        loser_recovery = 0.0 if illiquid else n_no * (1.0 - THRESHOLD)
        winner_payout  = 0.0 if reversal  else n_yes * 1.0

        capital = max(0.0, capital + loser_recovery + winner_payout - bet)
        history[t + 1] = capital

    return history

paths  = np.array([simulate(i) for i in range(N_SIMS)])
finals = paths[:, -1]
rounds = np.arange(n_bets + 1)

p10 = np.percentile(paths, 10,  axis=0)
p25 = np.percentile(paths, 25,  axis=0)
p50 = np.percentile(paths, 50,  axis=0)
p75 = np.percentile(paths, 75,  axis=0)
p90 = np.percentile(paths, 90,  axis=0)

# ── Chart ──────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(11, 4.5))
fig.patch.set_facecolor("#0d1117")
ax.set_facecolor("#161b22")
for spine in ax.spines.values():
    spine.set_color("#30363d")

# Fan bands
ax.fill_between(rounds, p10, p90, alpha=0.12, color="#58a6ff")
ax.fill_between(rounds, p25, p75, alpha=0.22, color="#58a6ff")

# Sample paths (faint)
for i in np.random.default_rng(99).choice(N_SIMS, 40, replace=False):
    color = "#3fb950" if paths[i, -1] >= CAPITAL_0 else "#f85149"
    ax.plot(rounds, paths[i], color=color, alpha=0.08, linewidth=0.7)

# Median + start line
ax.plot(rounds, p50, color="#58a6ff", linewidth=2.2,
        label=f"Median  ${p50[-1]:.2f}")
ax.axhline(CAPITAL_0, color="#ffffff", linewidth=1, linestyle="--",
           alpha=0.4, label=f"Start  ${CAPITAL_0:.0f}")

ax.set_xlabel("Bet Number",  color="#8b949e", fontsize=10)
ax.set_ylabel("Capital ($)", color="#8b949e", fontsize=10)
ax.tick_params(colors="#8b949e")
ax.grid(alpha=0.25, color="#21262d")
ax.legend(facecolor="#161b22", edgecolor="#30363d",
          labelcolor="#c9d1d9", fontsize=10)

# Label 10th / 90th at end
ax.annotate(f"90th  ${p90[-1]:.0f}", xy=(rounds[-1], p90[-1]),
            xytext=(6, 0), textcoords="offset points",
            color="#3fb950", fontsize=8, va="center")
ax.annotate(f"10th  ${p10[-1]:.0f}", xy=(rounds[-1], p10[-1]),
            xytext=(6, 0), textcoords="offset points",
            color="#f85149", fontsize=8, va="center")

# ── Metrics ────────────────────────────────────────────────────────────────────
median_final = float(np.median(finals))
win_rate     = float((finals > CAPITAL_0).mean() * 100)
ruin_rate    = float((finals < CAPITAL_0 * 0.10).mean() * 100)

# Max drawdown per path → median across sims
peaks  = np.maximum.accumulate(paths, axis=1)
dds    = (peaks - paths) / np.where(peaks > 0, peaks, 1)
med_dd = float(np.median(np.max(dds, axis=1)) * 100)

# Analytical expected value per $1 bet
n_yes_1 = 0.5 / yes_ask
n_no_1  = 0.5 / no_ask
ev_success  = n_no_1 * (1 - THRESHOLD) + n_yes_1 * 1.0 - 1.0
ev_reversal = n_no_1 * (1 - THRESHOLD) + 0.0           - 1.0
ev_illiquid = 0.0                        + n_yes_1 * 1.0 - 1.0
ev_both_bad = 0.0                        + 0.0           - 1.0

p_normal    = (1 - reversal_prob) * (1 - illiquid_prob)
p_reversal  = reversal_prob       * (1 - illiquid_prob)
p_illiquid  = (1 - reversal_prob) * illiquid_prob
p_both      = reversal_prob       * illiquid_prob
ev_per_unit = (p_normal   * ev_success  + p_reversal * ev_reversal +
               p_illiquid * ev_illiquid + p_both     * ev_both_bad)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Median Final",    f"${median_final:.2f}",
          f"{(median_final / CAPITAL_0 - 1) * 100:+.1f}%")
m2.metric("Win Rate",        f"{win_rate:.0f}%")
m3.metric("Median Drawdown", f"{med_dd:.1f}%")
m4.metric("Ruin Risk (<$5)", f"{ruin_rate:.1f}%")
m5.metric("EV per Bet",      f"${ev_per_unit * BET_FRACTION * CAPITAL_0:+.3f}",
          f"({ev_per_unit * 100:+.2f}% per $1)")

st.pyplot(fig, use_container_width=True)

# ── Live Polymarket Markets ─────────────────────────────────────────────────────
st.divider()
st.header("Live Polymarket Markets — Bitcoin / BTC")

@st.cache_data(ttl=60)
def fetch_markets():
    resp = requests.get(
        "https://gamma-api.polymarket.com/markets",
        params={"limit": 200, "active": "true"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()

if st.button("Refresh", key="refresh_markets"):
    fetch_markets.clear()

def is_btc_market(m):
    """Return True if any string field in the market object contains bitcoin/btc."""
    for v in m.values():
        if isinstance(v, str) and any(kw in v.lower() for kw in ("bitcoin", "btc")):
            return True
    return False

try:
    from datetime import datetime, timezone
    markets_raw = fetch_markets()

    btc_markets = [
        m for m in markets_raw
        if is_btc_market(m)
        and (m.get("active") is True or m.get("resolved") is False)
    ]

    # Sort by end_date ascending (soonest to resolve first), take top 10
    def end_date_key(m):
        raw = m.get("end_date_iso") or m.get("endDate") or m.get("end_date") or ""
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return datetime.max.replace(tzinfo=timezone.utc)

    btc_markets.sort(key=end_date_key)
    btc_markets = btc_markets[:10]

    if not btc_markets:
        st.warning(f"No Bitcoin/BTC markets found in {len(markets_raw)} fetched markets.")
        with st.expander("Debug: inspect raw API response"):
            all_keys = sorted({k for m in markets_raw for k in m.keys()})
            st.markdown(f"**Total markets fetched:** {len(markets_raw)}")
            st.markdown(f"**All field names:** `{'`, `'.join(all_keys)}`")
            st.markdown("**First 3 raw market objects:**")
            for i, m in enumerate(markets_raw[:3]):
                st.json(m)
    else:
        rows = []
        for m in btc_markets:
            question   = m.get("question", "N/A")
            prices_raw = m.get("outcomePrices")
            volume     = m.get("volume", 0)

            try:
                prices    = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                yes_price = float(prices[0])
                no_price  = float(prices[1])
            except (TypeError, ValueError, IndexError):
                yes_price = no_price = float("nan")

            spread_val = yes_price + no_price - 1.0

            end_raw = m.get("end_date_iso") or m.get("endDate") or m.get("end_date") or ""
            try:
                end_str = datetime.fromisoformat(end_raw.replace("Z", "+00:00")).strftime("%Y-%m-%d")
            except ValueError:
                end_str = end_raw[:10] if end_raw else "N/A"

            rows.append({
                "Question":   question,
                "Yes":        yes_price,
                "No":         no_price,
                "Spread":     spread_val,
                "Volume ($)": float(volume) if volume else 0.0,
                "Resolves":   end_str,
            })

        df = pd.DataFrame(rows)

        def highlight_tight(row):
            spread = row["Spread"]
            if pd.notna(spread) and spread < 0.03:
                return ["background-color: #1a3a1a; color: #3fb950"] * len(row)
            return [""] * len(row)

        styled = (
            df.style
            .apply(highlight_tight, axis=1)
            .format(
                {
                    "Yes":        "{:.1%}",
                    "No":         "{:.1%}",
                    "Spread":     "{:.2%}",
                    "Volume ($)": "${:,.0f}",
                },
                na_rep="N/A",
            )
        )

        st.dataframe(styled, use_container_width=True, hide_index=True)
        st.caption(f"Top {len(btc_markets)} BTC markets by volume  •  Green rows = spread < 3%  •  Data from Polymarket Gamma API  •  Auto-cached for 60 s")

except requests.exceptions.ConnectionError:
    st.error("Could not connect to Polymarket API. Check your internet connection.")
except requests.exceptions.Timeout:
    st.error("Request timed out. The Polymarket API may be slow — try refreshing.")
except requests.exceptions.HTTPError as e:
    st.error(f"API returned an error: {e}")
except Exception as e:
    st.error(f"Unexpected error fetching market data: {e}")
