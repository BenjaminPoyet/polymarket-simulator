import json
import time
import requests
from datetime import datetime, timezone, timedelta

INTERVAL     = 5 * 60   # seconds between scans
SPREAD_LIMIT = 0.02
MIN_VOLUME   = 10_000
DAYS_AHEAD   = 7
URL          = "https://gamma-api.polymarket.com/markets"


def fetch_markets():
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    resp = requests.get(
        URL,
        params={
            "limit":        100,
            "active":       "true",
            "end_date_min": now_iso,
            "order":        "endDate",
            "ascending":    "true",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def scan():
    now_utc = datetime.now(timezone.utc)
    cutoff  = now_utc + timedelta(days=DAYS_AHEAD)

    try:
        raw = fetch_markets()
    except requests.exceptions.RequestException as e:
        print(f"  [error] Could not fetch markets: {e}")
        return

    opportunities = []

    for m in raw:
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

        # End date within 7 days
        end_raw = m.get("end_date_iso") or m.get("endDate") or m.get("end_date") or ""
        try:
            end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if end_dt <= now_utc or end_dt > cutoff:
            continue

        # Volume filter
        volume = float(m.get("volume") or 0)
        if volume < MIN_VOLUME:
            continue

        spread = yes_p + no_p - 1.0

        opportunities.append({
            "market": m.get("question", "N/A"),
            "yes":    yes_p,
            "no":     no_p,
            "spread": spread,
            "volume": volume,
            "ends":   end_dt.strftime("%Y-%m-%d"),
            "flag":   spread < SPREAD_LIMIT,
        })

    opportunities.sort(key=lambda x: x["volume"], reverse=True)
    return opportunities


def print_table(opportunities, scanned_at):
    col_q = 52
    header = (
        f"{'Market':<{col_q}}  {'Yes':>6}  {'No':>6}  {'Spread':>7}  "
        f"{'Volume':>12}  {'Ends':>10}  {'':>3}"
    )
    divider = "-" * len(header)

    print(f"\n{'=' * len(header)}")
    print(f"  Polymarket Opportunity Scanner  |  {scanned_at}  |  {len(opportunities)} markets")
    print(f"{'=' * len(header)}")
    print(header)
    print(divider)

    if not opportunities:
        print("  No opportunities match the filters.")
    else:
        for o in opportunities:
            question = o["market"]
            if len(question) > col_q:
                question = question[:col_q - 1] + "…"
            flag = "(*)" if o["flag"] else ""
            print(
                f"{question:<{col_q}}  "
                f"{o['yes']:>5.1%}  "
                f"{o['no']:>5.1%}  "
                f"{o['spread']:>6.2%}  "
                f"${o['volume']:>11,.0f}  "
                f"{o['ends']:>10}  "
                f"{flag:>3}"
            )

    flagged = sum(1 for o in opportunities if o["flag"])
    print(divider)
    print(f"  (*) = spread < {SPREAD_LIMIT:.0%}  |  {flagged} flagged  |  "
          f"volume > ${MIN_VOLUME:,}  |  ends within {DAYS_AHEAD} days")
    print()


def main():
    print(f"Polymarket Opportunity Scanner starting — refreshing every {INTERVAL // 60} min.")
    print("Press Ctrl+C to stop.\n")

    while True:
        scanned_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        opps = scan()
        if opps is not None:
            print_table(opps, scanned_at)
        try:
            time.sleep(INTERVAL)
        except KeyboardInterrupt:
            print("\nStopped.")
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
