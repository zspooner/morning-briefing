#!/usr/bin/env python3
"""Check how past discovery flags have performed. Run anytime to see if the scanner is working.

Usage: python check_discovery.py
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

import yfinance as yf

LOG_PATH = Path(__file__).parent / "discovery_log.jsonl"


def main():
    if not LOG_PATH.exists():
        print("No discovery log yet. Run the briefing a few times first.")
        return

    # Load all flags
    flags = []
    for line in LOG_PATH.read_text().strip().split("\n"):
        if line.strip():
            flags.append(json.loads(line))

    if not flags:
        print("Log is empty.")
        return

    # Deduplicate: one entry per (date, ticker)
    seen = set()
    unique_flags = []
    for f in flags:
        key = (f["date"], f["ticker"])
        if key not in seen:
            seen.add(key)
            unique_flags.append(f)
    flags = unique_flags

    # Group by ticker to batch download
    tickers = list({f["ticker"] for f in flags})
    print(f"Checking {len(flags)} flags across {len(tickers)} tickers...\n")

    # Download current + historical prices
    prices = {}
    try:
        data = yf.download(tickers, period="1y", progress=False, threads=True)
        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    df = data
                else:
                    df = data[ticker]
                if df is not None and not df.empty:
                    prices[ticker] = df["Close"]
            except Exception:
                pass
    except Exception as e:
        print(f"Download error: {e}")
        return

    # Evaluate each flag
    results = []
    for f in flags:
        ticker = f["ticker"]
        flag_date = f["date"]
        flag_price = f["price"]

        if ticker not in prices or flag_price is None:
            continue

        series = prices[ticker]
        # Current price
        current = float(series.iloc[-1])
        ret = (current - flag_price) / flag_price * 100

        # Days since flag
        flag_dt = datetime.strptime(flag_date, "%Y-%m-%d")
        days = (datetime.now() - flag_dt).days

        results.append({
            "date": flag_date,
            "ticker": ticker,
            "flag_price": flag_price,
            "current_price": round(current, 2),
            "return_pct": round(ret, 1),
            "days_held": days,
            "signals": f["signals"],
        })

    if not results:
        print("No evaluable flags yet.")
        return

    # Sort by return
    results.sort(key=lambda x: x["return_pct"], reverse=True)

    # Summary stats
    returns = [r["return_pct"] for r in results]
    avg_ret = sum(returns) / len(returns)
    hit_rate = sum(1 for r in returns if r > 0) / len(returns) * 100
    median_ret = sorted(returns)[len(returns) // 2]
    home_runs = sum(1 for r in returns if r > 30) / len(returns) * 100

    print("=" * 60)
    print("DISCOVERY SCANNER — LIVE PERFORMANCE TRACKER")
    print("=" * 60)
    print(f"  Flags tracked:  {len(results)}")
    print(f"  Date range:     {results[-1]['date']} to {results[0]['date']}")
    print(f"  Avg return:     {'+' if avg_ret >= 0 else ''}{avg_ret:.1f}%")
    print(f"  Median return:  {'+' if median_ret >= 0 else ''}{median_ret:.1f}%")
    print(f"  Hit rate:       {hit_rate:.0f}%")
    print(f"  Home runs (>30%): {home_runs:.0f}%")
    print()

    # Top winners
    print("TOP 5 WINNERS:")
    for r in results[:5]:
        print(f"  {r['ticker']:6s}  flagged {r['date']} at ${r['flag_price']:.2f}"
              f"  → ${r['current_price']:.2f}  ({'+' if r['return_pct'] >= 0 else ''}{r['return_pct']}%"
              f"  in {r['days_held']}d)")

    print()
    print("BOTTOM 5:")
    for r in results[-5:]:
        print(f"  {r['ticker']:6s}  flagged {r['date']} at ${r['flag_price']:.2f}"
              f"  → ${r['current_price']:.2f}  ({'+' if r['return_pct'] >= 0 else ''}{r['return_pct']}%"
              f"  in {r['days_held']}d)")

    # Monthly breakdown if enough data
    by_month = defaultdict(list)
    for r in results:
        month = r["date"][:7]
        by_month[month].append(r["return_pct"])

    if len(by_month) > 1:
        print()
        print("BY MONTH:")
        for month in sorted(by_month.keys()):
            rets = by_month[month]
            m_avg = sum(rets) / len(rets)
            m_hit = sum(1 for r in rets if r > 0) / len(rets) * 100
            print(f"  {month}:  {len(rets)} flags  avg {'+' if m_avg >= 0 else ''}{m_avg:.1f}%  hit {m_hit:.0f}%")

    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
