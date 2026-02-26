"""
Polymarket Data Collector
=========================
Polls active binary markets every 30 seconds and appends rows to
odds_history.csv. When a market disappears (resolved), fetches its
final outcome and records a closing row.

CSV columns:
  market_id, question, yes_price, no_price, volume, timestamp,
  end_time, time_remaining_seconds, total_duration_seconds,
  time_consumed_pct, status, outcome

Run with:  python data_collector.py
Stop with: Ctrl+C
"""

import csv
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone

import requests

# ── Config ─────────────────────────────────────────────────────────────────────
GAMMA_URL    = "https://gamma-api.polymarket.com/markets"
POLL_SECONDS = 30
CSV_FILE     = "odds_history.csv"
API_LIMIT    = 100

CSV_COLUMNS = [
    "market_id", "question", "yes_price", "no_price", "volume",
    "timestamp", "end_time", "time_remaining_seconds",
    "total_duration_seconds", "time_consumed_pct", "status", "outcome",
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def now_utc():
    return datetime.now(timezone.utc)


def parse_iso(s):
    """Parse ISO-8601 string → aware datetime, or None."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_prices(raw):
    """Return (yes_price, no_price) floats or raise ValueError."""
    prices = json.loads(raw) if isinstance(raw, str) else raw
    if not prices or len(prices) != 2:
        raise ValueError("not binary")
    return float(prices[0]), float(prices[1])


def resolve_outcome(yes_p, no_p):
    """'yes_won', 'no_won', or 'unknown'."""
    if yes_p >= 0.95:
        return "yes_won"
    if no_p >= 0.95:
        return "no_won"
    return "unknown"


def fetch_active_markets():
    now_iso = now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
    resp = requests.get(
        GAMMA_URL,
        params={
            "active":       "true",
            "limit":        API_LIMIT,
            "end_date_min": now_iso,
            "order":        "volume",
            "ascending":    "false",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_market_by_id(market_id):
    resp = requests.get(f"{GAMMA_URL}/{market_id}", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data[0] if isinstance(data, list) else data


def build_row(m, ts, status="active", outcome=""):
    """Build a CSV row dict from a market object."""
    try:
        yes_p, no_p = parse_prices(m.get("outcomePrices"))
    except (TypeError, ValueError):
        yes_p = no_p = ""

    end_dt   = parse_iso(m.get("endDate"))
    start_dt = parse_iso(m.get("startDate") or m.get("createdAt"))

    time_remaining = ""
    total_duration = ""
    time_consumed  = ""

    if end_dt:
        time_remaining = max(0, (end_dt - ts).total_seconds())
        if start_dt:
            total_duration = max(0, (end_dt - start_dt).total_seconds())
            if total_duration > 0:
                elapsed = max(0, (ts - start_dt).total_seconds())
                time_consumed = round(min(elapsed / total_duration * 100, 100), 2)

    question = m.get("question", "")
    if len(question) > 120:
        question = question[:119] + "…"

    return {
        "market_id":             m.get("id", ""),
        "question":              question,
        "yes_price":             round(yes_p, 4) if yes_p != "" else "",
        "no_price":              round(no_p, 4) if no_p != "" else "",
        "volume":                round(float(m.get("volume") or 0), 2),
        "timestamp":             ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_time":              end_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if end_dt else "",
        "time_remaining_seconds": round(time_remaining) if time_remaining != "" else "",
        "total_duration_seconds": round(total_duration) if total_duration != "" else "",
        "time_consumed_pct":     time_consumed,
        "status":                status,
        "outcome":               outcome,
    }


def write_rows(rows, file_path=CSV_FILE):
    """Append rows to CSV, writing header only if file is new/empty."""
    is_new = not os.path.exists(file_path) or os.path.getsize(file_path) == 0
    with open(file_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerows(rows)


def load_known_ids(file_path=CSV_FILE):
    """Return set of market_ids seen in existing CSV (active rows only)."""
    known = {}
    if not os.path.exists(file_path):
        return known
    try:
        with open(file_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                mid = row.get("market_id")
                if mid and row.get("status") == "active":
                    known[mid] = row.get("question", "")
    except Exception:
        pass
    return known


# ── Main loop ──────────────────────────────────────────────────────────────────

def main():
    print(f"Polymarket Data Collector  —  polling every {POLL_SECONDS}s")
    print(f"Output file : {os.path.abspath(CSV_FILE)}")
    print("Stop with   : Ctrl+C\n")

    # Restore previously tracked markets from CSV so we can detect resolutions
    # across restarts.
    prev_ids = load_known_ids()
    if prev_ids:
        print(f"  Resumed: {len(prev_ids)} markets from existing CSV.\n")

    resolved_today = 0
    poll_count     = 0

    def _shutdown(sig, frame):
        print(f"\n\nStopped after {poll_count} polls. "
              f"{resolved_today} markets resolved this session.")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)

    while True:
        poll_start = time.time()
        ts         = now_utc()
        rows       = []
        current_ids = {}

        # ── Fetch active markets ─────────────────────────────────────────────
        try:
            markets = fetch_active_markets()
        except requests.exceptions.RequestException as e:
            print(f"[{ts.strftime('%H:%M:%S')}] Fetch error: {e} — retrying next poll.")
            time.sleep(POLL_SECONDS)
            continue

        # Filter to binary markets with parseable prices and BTC-related questions
        binary = []
        for m in markets:
            try:
                parse_prices(m.get("outcomePrices"))
                q = (m.get("question") or "").lower()
                if "bitcoin" in q or "btc" in q:
                    binary.append(m)
            except (TypeError, ValueError):
                pass

        for m in binary:
            mid = str(m.get("id", ""))
            current_ids[mid] = m.get("question", "")
            rows.append(build_row(m, ts, status="active", outcome=""))

        # ── Detect resolutions ───────────────────────────────────────────────
        disappeared = set(prev_ids.keys()) - set(current_ids.keys())
        for mid in disappeared:
            try:
                closed_m = fetch_market_by_id(mid)
                yes_p, no_p = parse_prices(closed_m.get("outcomePrices"))
                outcome = resolve_outcome(yes_p, no_p)
                if closed_m.get("closed") or outcome != "unknown":
                    rows.append(build_row(closed_m, ts,
                                          status="closed", outcome=outcome))
                    resolved_today += 1
                    print(f"  Resolved: [{outcome}] {closed_m.get('question','')[:70]}")
                else:
                    # Still in-flight or temporarily missing — keep tracking
                    current_ids[mid] = prev_ids[mid]
            except Exception as e:
                # API error — keep it in tracking set
                current_ids[mid] = prev_ids[mid]

        # ── Write to CSV ─────────────────────────────────────────────────────
        if rows:
            write_rows(rows)

        prev_ids   = current_ids
        poll_count += 1

        elapsed = time.time() - poll_start
        print(
            f"[{ts.strftime('%H:%M:%S')}]  "
            f"{len(binary)} BTC markets found  |  "
            f"Tracking {len(current_ids)} markets  |  "
            f"{resolved_today} resolved today  |  "
            f"poll #{poll_count}  ({elapsed:.1f}s)"
        )

        sleep_for = max(0, POLL_SECONDS - elapsed)
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
