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
/* Main background + global text */
.stApp { background-color: #0e1117; color: #ffffff; }
.stApp p, .stApp span, .stApp div, .stApp li,
.stApp h1, .stApp h2, .stApp h3, .stApp h4 { color: #ffffff; }

/* Sidebar */
[data-testid="stSidebar"] {
    background-color: #0d1117;
    border-right: 1px solid #21262d;
    color: #ffffff;
}
[data-testid="stSidebar"] * { color: #ffffff; }

/* Metric cards */
[data-testid="metric-container"] {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 18px 20px;
}
[data-testid="metric-container"] label {
    color: #cccccc !important;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #ffffff !important;
    font-size: 1.5rem;
    font-weight: 600;
}
[data-testid="metric-container"] [data-testid="stMetricDelta"] {
    font-size: 0.82rem;
}

/* Divider */
hr { border-color: #21262d !important; }

/* ── All input/select elements: dark text on light widget background ── */
input, textarea, select,
input[type="text"],
input[type="number"],
input[type="search"],
input[type="email"],
.stTextInput input,
.stNumberInput input,
.stSelectbox select,
[data-baseweb="input"] input,
[data-baseweb="select"] input,
[data-baseweb="textarea"] textarea {
    color: #111111 !important;
    background-color: #ffffff !important;
}

/* Selectbox dropdown option text */
[data-baseweb="select"] [data-testid="stSelectboxVirtualDropdown"],
[data-baseweb="popover"] li,
[data-baseweb="menu"] li {
    color: #111111 !important;
    background-color: #ffffff !important;
}

/* Placeholder text */
input::placeholder,
textarea::placeholder { color: #888888 !important; }

/* Widget labels (text_input, number_input, selectbox labels above the box) */
.stTextInput label,
.stNumberInput label,
.stSelectbox label { color: #cccccc !important; }

/* Dataframe */
[data-testid="stDataFrame"] { border: 1px solid #30363d; border-radius: 8px; }

/* Tabs */
[data-testid="stTabs"] [data-baseweb="tab-list"] { border-bottom: 1px solid #30363d; }
[data-testid="stTabs"] [data-baseweb="tab"] { color: #8b949e; background: transparent; }
[data-testid="stTabs"] [aria-selected="true"] { color: #ffffff !important; border-bottom: 2px solid #58a6ff !important; }
</style>
""", unsafe_allow_html=True)

st.title("Polymarket Dual-Side Strategy Simulator")

# ── Sliders (sidebar) ──────────────────────────────────────────────────────────
st.sidebar.header("Strategy Parameters")

CAPITAL_0    = st.sidebar.number_input("Starting Capital ($)", min_value=10.0,
                                        max_value=100_000.0, value=50.0, step=10.0)
BET_FRACTION = st.sidebar.slider("Bet Size (% of capital)", 10, 50, 12,
                                  format="%d%%") / 100
reinvest      = st.sidebar.toggle("Reinvest Gains", value=True,
                                   help="ON: bet grows with capital (compounding).  OFF: bet stays fixed to starting capital.")

st.sidebar.divider()
spread        = st.sidebar.slider("Spread",                  0.5,  5.0,  2.0, 0.5, format="%.1f%%", key="slider_spread") / 100
reversal_prob = st.sidebar.slider("Reversal Probability",    0,    50,   10,  5,   format="%d%%",   key="slider_reversal") / 100
illiquid_prob     = st.sidebar.slider("Illiquidity Probability", 0,  50,  5,  5, format="%d%%", key="slider_illiquid_prob") / 100
illiquid_discount = st.sidebar.slider("Illiquidity Discount",    0, 100, 72,  1,
                                       format="%d%%", key="slider_illiquid_discount",
                                       help="How much of the loser's value is lost when selling in illiquid conditions.") / 100
n_bets            = st.sidebar.slider("Number of Bets",         10, 500, 100, 10)

# ── Constants ──────────────────────────────────────────────────────────────────
THRESHOLD   = 0.75
ENTRY_PRICE = 0.50
N_SIMS      = 300

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

        bet   = capital * BET_FRACTION if reinvest else CAPITAL_0 * BET_FRACTION
        n_yes = (bet / 2) / yes_ask
        n_no  = (bet / 2) / no_ask

        reversal = rng.random() < reversal_prob
        illiquid = rng.random() < illiquid_prob

        loser_recovery = (n_no * (1.0 - THRESHOLD) * (1.0 - illiquid_discount)
                          if illiquid else n_no * (1.0 - THRESHOLD))
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
illiq_rec   = (1.0 - THRESHOLD) * (1.0 - illiquid_discount)
ev_success  = n_no_1 * (1 - THRESHOLD) + n_yes_1 * 1.0 - 1.0
ev_reversal = n_no_1 * (1 - THRESHOLD) + 0.0           - 1.0
ev_illiquid = n_no_1 * illiq_rec        + n_yes_1 * 1.0 - 1.0
ev_both_bad = n_no_1 * illiq_rec        + 0.0           - 1.0

p_normal    = (1 - reversal_prob) * (1 - illiquid_prob)
p_reversal  = reversal_prob       * (1 - illiquid_prob)
p_illiquid  = (1 - reversal_prob) * illiquid_prob
p_both      = reversal_prob       * illiquid_prob
ev_per_unit = (p_normal   * ev_success  + p_reversal * ev_reversal +
               p_illiquid * ev_illiquid + p_both     * ev_both_bad)

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_sim, tab_opp, tab_btc, tab_trades, tab_scan = st.tabs(
    ["Simulator", "Opportunities", "Live BTC Markets", "My Trades", "Scanner"]
)

# ══════════════════════════════════════════════════════════════════════════════
with tab_sim:
# ══════════════════════════════════════════════════════════════════════════════
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Median Final",    f"${median_final:.2f}",
              f"{(median_final / CAPITAL_0 - 1) * 100:+.1f}%")
    m2.metric("Win Rate",        f"{win_rate:.0f}%")
    m3.metric("Median Drawdown", f"{med_dd:.1f}%")
    m4.metric(f"Ruin Risk (<${CAPITAL_0 * 0.10:.0f})", f"{ruin_rate:.1f}%")
    m5.metric("EV per Bet",      f"${ev_per_unit * BET_FRACTION * CAPITAL_0:+.3f}",
              f"({ev_per_unit * 100:+.2f}% per $1)")

    st.pyplot(fig, use_container_width=True)

    def bets_to_reach(paths, target_capital):
        hits = []
        for path in paths:
            indices = np.where(path >= target_capital)[0]
            if len(indices) > 0:
                hits.append(int(indices[0]))
        pct    = len(hits) / len(paths) * 100
        median = int(np.median(hits)) if hits else None
        return pct, median

    st.subheader("Time to Target")
    t1, t2, t3 = st.columns(3)
    for col, mult, label in zip([t1, t2, t3], [2, 5, 10], ["2×", "5×", "10×"]):
        pct, med = bets_to_reach(paths, CAPITAL_0 * mult)
        value = f"{med} bets" if med is not None else "Not reached"
        col.metric(f"{label}  (${CAPITAL_0 * mult:,.0f})", value,
                   f"{pct:.0f}% of simulations")

# ══════════════════════════════════════════════════════════════════════════════
with tab_opp:
# ══════════════════════════════════════════════════════════════════════════════
    st.caption("Active binary markets sorted by volume. Green = spread < 2%.")

    @st.cache_data(ttl=120)
    def fetch_opportunities():
        resp = requests.get(
            "https://gamma-api.polymarket.com/markets",
            params={"limit": 100, "active": "true"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    if st.button("Refresh", key="refresh_opp"):
        fetch_opportunities.clear()

    try:
        from datetime import datetime, timezone

        opp_raw = fetch_opportunities()
        opp_rows = []
        for m in opp_raw:
            # Binary only: exactly 2 outcome prices
            prices_raw = m.get("outcomePrices")
            try:
                prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                if not prices or len(prices) != 2:
                    continue
                yes_p = float(prices[0])
                no_p  = float(prices[1])
            except (TypeError, ValueError, IndexError):
                continue

            end_raw = m.get("end_date_iso") or m.get("endDate") or m.get("end_date") or ""
            try:
                end_str = datetime.fromisoformat(end_raw.replace("Z", "+00:00")).strftime("%Y-%m-%d")
            except ValueError:
                end_str = end_raw[:10] if end_raw else "N/A"

            volume   = float(m.get("volume") or 0)
            spread_v = yes_p + no_p - 1.0
            opp_rows.append({
                "Question":   m.get("question", "N/A"),
                "Yes":        yes_p,
                "No":         no_p,
                "Spread":     spread_v,
                "Volume ($)": volume,
                "End Date":   end_str,
            })

        opp_rows.sort(key=lambda x: x["Volume ($)"], reverse=True)

        if not opp_rows:
            st.info("No binary markets found.")
        else:
            df_opp = pd.DataFrame(opp_rows)
            tight_count = int((df_opp["Spread"] < 0.02).sum())

            def highlight_opp(row):
                if pd.notna(row["Spread"]) and row["Spread"] < 0.02:
                    return ["background-color: #0d2a1a; color: #3fb950"] * len(row)
                return [""] * len(row)

            styled_opp = (
                df_opp.style
                .apply(highlight_opp, axis=1)
                .format({
                    "Yes":        "{:.1%}",
                    "No":         "{:.1%}",
                    "Spread":     "{:.2%}",
                    "Volume ($)": "${:,.0f}",
                }, na_rep="N/A")
            )
            st.dataframe(styled_opp, use_container_width=True, hide_index=True)
            st.caption(f"{len(opp_rows)} markets · {tight_count} tight spread (green)  •  "
                       "Spread < 2%  •  Auto-cached 2 min")

    except requests.exceptions.ConnectionError:
        st.error("Could not connect to Polymarket API. Check your internet connection.")
    except requests.exceptions.Timeout:
        st.error("Request timed out.")
    except requests.exceptions.HTTPError as e:
        st.error(f"API error: {e}")
    except Exception as e:
        st.error(f"Unexpected error: {e}")

# ══════════════════════════════════════════════════════════════════════════════
with tab_btc:
# ══════════════════════════════════════════════════════════════════════════════
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
                if pd.notna(row["Spread"]) and row["Spread"] < 0.03:
                    return ["background-color: #1a3a1a; color: #3fb950"] * len(row)
                return [""] * len(row)

            styled = (
                df.style
                .apply(highlight_tight, axis=1)
                .format({"Yes": "{:.1%}", "No": "{:.1%}",
                         "Spread": "{:.2%}", "Volume ($)": "${:,.0f}"}, na_rep="N/A")
            )
            st.dataframe(styled, use_container_width=True, hide_index=True)
            st.caption(f"Top {len(btc_markets)} BTC markets  •  Green = spread < 3%  •  "
                       "Auto-cached 60 s")

    except requests.exceptions.ConnectionError:
        st.error("Could not connect to Polymarket API. Check your internet connection.")
    except requests.exceptions.Timeout:
        st.error("Request timed out. The Polymarket API may be slow — try refreshing.")
    except requests.exceptions.HTTPError as e:
        st.error(f"API returned an error: {e}")
    except Exception as e:
        st.error(f"Unexpected error fetching market data: {e}")

# ══════════════════════════════════════════════════════════════════════════════
with tab_trades:
    # ══════════════════════════════════════════════════════════════════════════
    wallet_col, btn_col = st.columns([4, 1])
    wallet = wallet_col.text_input("Wallet address", placeholder="0x...",
                                    label_visibility="collapsed", key="wallet_input")

    if btn_col.button("Load My Trades", use_container_width=True):
        if not wallet or not wallet.startswith("0x"):
            st.warning("Please enter a valid 0x wallet address.")
        else:
            try:
                resp = requests.get(
                    "https://data-api.polymarket.com/activity",
                    params={"user": wallet},
                    timeout=15,
                )
                resp.raise_for_status()
                st.session_state["trades_raw"] = resp.json()
            except requests.exceptions.ConnectionError:
                st.error("Could not connect to Polymarket Data API.")
            except requests.exceptions.Timeout:
                st.error("Request timed out.")
            except requests.exceptions.HTTPError as e:
                st.error(f"API error: {e}")
            except Exception as e:
                st.error(f"Unexpected error: {e}")

    if "trades_raw" in st.session_state:
        from datetime import datetime, timezone as _tz

        data = st.session_state["trades_raw"]
        trades_list = data if isinstance(data, list) else data.get("data", data.get("activity", []))

        if not trades_list:
            st.info("No trade activity found for this wallet.")
        else:
            # ── Debug: show raw field names + sample values ──────────────────
            with st.expander("Debug: raw API fields (first 3 records)", expanded=False):
                all_keys = sorted({k for t in trades_list for k in t.keys()})
                st.write("**All field names:**", all_keys)
                for i, t in enumerate(trades_list[:3]):
                    st.write(f"**Record {i+1}:**",
                             {k: v for k, v in t.items()
                              if k in ("side", "type", "tradeType", "outcome", "outcomeIndex",
                                       "asset", "price", "avgPrice", "size", "shares",
                                       "usdcSize", "amount", "cashAmount", "cashPnl",
                                       "value", "cost", "notional", "proxyWallet",
                                       "title", "question", "market", "name",
                                       "timestamp", "createdAt", "date")})

            # ── Parse into clean rows ────────────────────────────────────────
            rows = []
            for t in trades_list:
                # Date
                ts = t.get("timestamp") or t.get("createdAt") or t.get("date") or ""
                try:
                    if isinstance(ts, (int, float)):
                        date_str = datetime.fromtimestamp(float(ts), tz=_tz.utc).strftime("%Y-%m-%d")
                    else:
                        date_str = str(ts)[:10]
                except Exception:
                    date_str = str(ts)[:10] if ts else "N/A"

                # Market question
                question = (t.get("title") or t.get("question") or t.get("market")
                            or t.get("marketQuestion") or t.get("name") or "Unknown")
                question = str(question)
                if len(question) > 72:
                    question = question[:71] + "…"

                # Side
                side_raw = str(t.get("side") or t.get("type") or t.get("tradeType") or "").upper()
                side = "Buy" if "BUY" in side_raw else ("Sell" if "SELL" in side_raw else side_raw.title())

                # Outcome / which token — normalise to Up/Down
                outcome = str(t.get("outcome") or "")
                if not outcome or outcome == "None":
                    idx = t.get("outcomeIndex")
                    outcome = "Up" if idx == 0 else ("Down" if idx == 1 else str(idx or ""))
                # Legacy YES/NO → Up/Down
                if outcome in ("YES", "0"): outcome = "Up"
                if outcome in ("NO",  "1"): outcome = "Down"

                # Price, shares, total USDC — use explicit None checks so 0.0 isn't skipped
                def _first(*keys):
                    for k in keys:
                        v = t.get(k)
                        if v is not None:
                            return v
                    return None

                price  = _first("price", "avgPrice", "executedPrice")
                shares = _first("size", "shares", "quantity")
                usdc   = _first("usdcSize", "amount", "cashAmount", "value",
                                "cost", "notional", "cashPnl")

                try:
                    price  = float(price)  if price  is not None else float("nan")
                    shares = float(shares) if shares is not None else float("nan")
                    usdc   = float(usdc)   if usdc   is not None else (
                                 price * shares if not (np.isnan(price) or np.isnan(shares)) else float("nan"))
                except (TypeError, ValueError):
                    price = shares = usdc = float("nan")

                rows.append({
                    "Date":        date_str,
                    "Market":      question,
                    "Token":       outcome,
                    "Action":      side,
                    "Price/share": price,
                    "Shares":      shares,
                    "Total ($)":   usdc,
                })

            df_trades = pd.DataFrame(rows)

            # ── Exclude Redeem actions ───────────────────────────────────────
            df_trades = df_trades[
                ~df_trades["Action"].str.upper().str.contains("REDEEM", na=False)
            ]

            # ── Dual-side filter: keep markets where both YES and NO were bought ──
            buy_df = df_trades[df_trades["Action"] == "Buy"]
            tokens_per_market = buy_df.groupby("Market")["Token"].apply(set)
            dual_markets = tokens_per_market[tokens_per_market.apply(
                lambda s: ("Up" in s and "Down" in s) or ("YES" in s and "NO" in s) or len(s) >= 2
            )].index
            df_dual = df_trades[df_trades["Market"].isin(dual_markets)]

            if df_dual.empty:
                st.info("No dual-side (YES + NO) markets found. "
                        "Only markets where both sides were bought are shown here.")
            else:
                # ── Group by market → one row per bet ────────────────────────
                market_rows = []
                for market, grp in df_dual.groupby("Market"):
                    inv_up   = grp[(grp["Action"] == "Buy")  & (grp["Token"] == "Up")  ]["Total ($)"].dropna().sum()
                    inv_dn   = grp[(grp["Action"] == "Buy")  & (grp["Token"] == "Down")]["Total ($)"].dropna().sum()
                    rec_up   = grp[(grp["Action"] == "Sell") & (grp["Token"] == "Up")  ]["Total ($)"].dropna().sum()
                    rec_dn   = grp[(grp["Action"] == "Sell") & (grp["Token"] == "Down")]["Total ($)"].dropna().sum()
                    tot_inv  = inv_up + inv_dn
                    tot_rec  = rec_up + rec_dn
                    pnl      = tot_rec - tot_inv
                    pnl_pct  = pnl / tot_inv * 100 if tot_inv > 0 else float("nan")
                    market_rows.append({
                        "Market":               market,
                        "Invested Up ($)":      inv_up,
                        "Invested Down ($)":    inv_dn,
                        "Total Invested ($)":   tot_inv,
                        "Recovered Up ($)":     rec_up,
                        "Recovered Down ($)":   rec_dn,
                        "Total Recovered ($)":  tot_rec,
                        "P&L ($)":              pnl,
                        "P&L (%)":              pnl_pct,
                    })

                df_grouped = pd.DataFrame(market_rows).reset_index(drop=True)

                # ── Append bold summary row ───────────────────────────────────
                tot_inv_sum = df_grouped["Total Invested ($)"].sum()
                summary = {
                    "Market":              "TOTAL",
                    "Invested Up ($)":     df_grouped["Invested Up ($)"].sum(),
                    "Invested Down ($)":   df_grouped["Invested Down ($)"].sum(),
                    "Total Invested ($)":  tot_inv_sum,
                    "Recovered Up ($)":    df_grouped["Recovered Up ($)"].sum(),
                    "Recovered Down ($)":  df_grouped["Recovered Down ($)"].sum(),
                    "Total Recovered ($)": df_grouped["Total Recovered ($)"].sum(),
                    "P&L ($)":             df_grouped["P&L ($)"].sum(),
                    "P&L (%)":             df_grouped["P&L ($)"].sum() / tot_inv_sum * 100
                                           if tot_inv_sum > 0 else float("nan"),
                }
                summary_idx = len(df_grouped)
                df_display = pd.concat([df_grouped, pd.DataFrame([summary])],
                                       ignore_index=True)

                # ── Styling ───────────────────────────────────────────────────
                def style_table(row):
                    styles = [""] * len(row)
                    cols   = list(row.index)
                    if row.name == summary_idx:
                        return ["background-color: #1c2233; font-weight: bold; "
                                "color: #ffffff"] * len(row)
                    pnl = row["P&L ($)"]
                    if pd.notna(pnl) and pnl > 0:
                        cell = "background-color: #0d2a1a; color: #3fb950; font-weight: 600"
                    elif pd.notna(pnl) and pnl < 0:
                        cell = "background-color: #2a0d0d; color: #f85149; font-weight: 600"
                    else:
                        cell = ""
                    for i, col in enumerate(cols):
                        if col in ("P&L ($)", "P&L (%)"):
                            styles[i] = cell
                    return styles

                def _d(v):
                    try: return f"${v:,.2f}"
                    except: return str(v)

                def _pnl(v):
                    try: return f"+${v:,.2f}" if v >= 0 else f"-${abs(v):,.2f}"
                    except: return str(v)

                def _pct(v):
                    try: return f"+{v:.1f}%" if v >= 0 else f"{v:.1f}%"
                    except: return str(v)

                styled = (
                    df_display.style
                    .apply(style_table, axis=1)
                    .format({
                        "Invested Up ($)":     _d,
                        "Invested Down ($)":   _d,
                        "Total Invested ($)":  _d,
                        "Recovered Up ($)":    _d,
                        "Recovered Down ($)":  _d,
                        "Total Recovered ($)": _d,
                        "P&L ($)":             _pnl,
                        "P&L (%)":             _pct,
                    }, na_rep="N/A")
                )
                st.dataframe(styled, use_container_width=True, hide_index=True)

                # ── Summary metric cards ──────────────────────────────────────
                total_pnl       = df_grouped["P&L ($)"].sum()
                wins            = int((df_grouped["P&L ($)"] > 0).sum())
                total_bets      = len(df_grouped)
                win_rate        = wins / total_bets * 100 if total_bets > 0 else float("nan")
                pnl_pct_overall = total_pnl / tot_inv_sum * 100 if tot_inv_sum > 0 else float("nan")

                st.markdown("---")
                s1, s2, s3, s4 = st.columns(4)
                s1.metric("Total Bets",     f"{total_bets}",
                          f"{wins} wins · {total_bets - wins} losses")
                s2.metric("Total Invested", f"${tot_inv_sum:,.2f}")
                s3.metric("Win Rate",
                          f"{win_rate:.0f}%" if not np.isnan(win_rate) else "N/A",
                          f"{wins} of {total_bets}")
                pnl_str = f"+${total_pnl:.2f}" if total_pnl >= 0 else f"-${abs(total_pnl):.2f}"
                s4.metric("Total P&L", pnl_str,
                          f"{pnl_pct_overall:+.1f}%" if not np.isnan(pnl_pct_overall) else "")

# ══════════════════════════════════════════════════════════════════════════════
with tab_scan:
    # ══════════════════════════════════════════════════════════════════════════
    sc1, sc2, sc3, sc4 = st.columns(4)
    SCAN_SPREAD_LIMIT = sc1.slider(
        "Max spread", 0.5, 10.0, 2.0, 0.5, format="%.1f%%", key="scan_spread"
    ) / 100
    SCAN_MIN_VOLUME = sc2.number_input(
        "Min volume ($)", min_value=0, max_value=1_000_000,
        value=10_000, step=1_000, key="scan_vol"
    )
    SCAN_HOURS_AHEAD = sc3.number_input(
        "Resolve within (hours)", min_value=1, max_value=720,
        value=24, step=1, key="scan_hours"
    )
    SCAN_PARITY_DEV = sc4.slider(
        "Max parity deviation", 1, 20, 10, 1, format="%d%%", key="scan_parity",
        help="Only show markets where Yes is within this % of 50. "
             "E.g. 10% → only 40%–60% Yes markets."
    ) / 100

    st.caption(
        f"Resolves within **{SCAN_HOURS_AHEAD}h**  •  "
        f"volume > ${SCAN_MIN_VOLUME:,}  •  "
        f"parity {50 - SCAN_PARITY_DEV*100:.0f}%–{50 + SCAN_PARITY_DEV*100:.0f}% Yes  •  "
        f"Green = spread < {SCAN_SPREAD_LIMIT:.0%}  •  Auto-cached 5 min"
    )

    @st.cache_data(ttl=300)
    def fetch_scanner_markets():
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = requests.get(
            "https://gamma-api.polymarket.com/markets",
            params={
                "limit":        500,
                "active":       "true",
                "end_date_min": now_iso,
                "order":        "endDate",
                "ascending":    "true",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    if st.button("Refresh", key="refresh_scan"):
        fetch_scanner_markets.clear()

    try:
        from datetime import datetime, timezone, timedelta
        now_utc = datetime.now(timezone.utc)
        cutoff  = now_utc + timedelta(hours=SCAN_HOURS_AHEAD)

        scan_raw = fetch_scanner_markets()
        scan_rows = []
        for m in scan_raw:
            prices_raw = m.get("outcomePrices")
            try:
                prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                if not prices or len(prices) != 2:
                    continue
                yes_p = float(prices[0])
                no_p  = float(prices[1])
            except (TypeError, ValueError, IndexError):
                continue

            # Skip already-resolved markets (one side at 100%)
            if yes_p >= 0.999 or no_p >= 0.999:
                continue

            end_raw = m.get("end_date_iso") or m.get("endDate") or m.get("end_date") or ""
            try:
                end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            if end_dt <= now_utc or end_dt > cutoff:
                continue

            volume = float(m.get("volume") or 0)
            if volume < SCAN_MIN_VOLUME:
                continue

            # Parity deviation: how far Yes is from 50%
            parity_dev = abs(yes_p - 0.5)
            if parity_dev > SCAN_PARITY_DEV:
                continue

            spread = yes_p + no_p - 1.0

            # Human-readable time until end
            hrs_left = (end_dt - now_utc).total_seconds() / 3600
            if hrs_left < 24:
                ends_str = f"{hrs_left:.0f}h"
            else:
                ends_str = f"{hrs_left / 24:.1f}d"

            scan_rows.append({
                "Market":      m.get("question", "N/A"),
                "Yes":         yes_p,
                "No":          no_p,
                "50/50 Dist":  parity_dev,
                "Spread":      spread,
                "Volume ($)":  volume,
                "Ends":        ends_str,
                "_flag":       spread < SCAN_SPREAD_LIMIT,
            })

        scan_rows.sort(key=lambda x: x["Volume ($)"], reverse=True)

        if not scan_rows:
            st.info("No markets match the current filters.")
        else:
            df_scan = pd.DataFrame(scan_rows)
            flagged    = int(df_scan["_flag"].sum())
            flag_index = set(df_scan.index[df_scan["_flag"]])

            def highlight_scan(row):
                if row.name in flag_index:
                    return ["background-color: #0d2a1a; color: #3fb950"] * len(row)
                return [""] * len(row)

            display_cols = ["Market", "Yes", "No", "50/50 Dist", "Spread", "Volume ($)", "Ends"]
            styled_scan = (
                df_scan[display_cols].style
                .apply(highlight_scan, axis=1)
                .format({
                    "Yes":        "{:.1%}",
                    "No":         "{:.1%}",
                    "50/50 Dist": "{:.1%}",
                    "Spread":     "{:.2%}",
                    "Volume ($)": "${:,.0f}",
                }, na_rep="N/A")
            )
            st.dataframe(styled_scan, use_container_width=True, hide_index=True)
            st.caption(
                f"{len(scan_rows)} markets shown  •  "
                f"{flagged} flagged (spread < {SCAN_SPREAD_LIMIT:.0%})"
            )

    except requests.exceptions.ConnectionError:
        st.error("Could not connect to Polymarket API.")
    except requests.exceptions.Timeout:
        st.error("Request timed out.")
    except requests.exceptions.HTTPError as e:
        st.error(f"API error: {e}")
    except Exception as e:
        st.error(f"Unexpected error: {e}")
