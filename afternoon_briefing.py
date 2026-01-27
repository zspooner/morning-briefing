#!/usr/bin/env python3
"""Afternoon Market Summary - Daily market close briefing at 4:15 PM EST."""
import os
from pathlib import Path
import argparse
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# Load .env from script directory
load_dotenv(Path(__file__).parent / ".env")

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_TO = os.getenv("EMAIL_TO")

# Portfolio holdings
MY_HOLDINGS = [
    "SPY", "QQQ", "NVDA", "PLTR", "HOOD", "GOOG", "SOFI",
    "META", "TSLA", "NBIS", "ASTS", "GRAB", "HIMS"
]


def get_market_close_data() -> dict:
    """Fetch end-of-day market data."""
    import yfinance as yf

    result = {"indices": {}, "holdings": {}, "top_gainers": [], "top_losers": []}

    # Major indices
    indices = {"S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Dow Jones": "^DJI"}
    for name, ticker in indices.items():
        try:
            idx = yf.Ticker(ticker)
            info = idx.fast_info
            if info.last_price and info.previous_close:
                change_pct = ((info.last_price - info.previous_close) / info.previous_close) * 100
                result["indices"][name] = {
                    "price": info.last_price,
                    "change_pct": change_pct
                }
        except Exception:
            pass

    # User's holdings with prices
    holdings_data = []
    for ticker in MY_HOLDINGS:
        try:
            stock = yf.Ticker(ticker)
            info = stock.fast_info
            if info.last_price and info.previous_close:
                change_pct = ((info.last_price - info.previous_close) / info.previous_close) * 100
                holdings_data.append({
                    "ticker": ticker,
                    "price": info.last_price,
                    "change_pct": change_pct
                })
                result["holdings"][ticker] = {
                    "price": info.last_price,
                    "change_pct": change_pct
                }
        except Exception:
            pass

    # Sort to find top gainers and losers from portfolio
    sorted_holdings = sorted(holdings_data, key=lambda x: x["change_pct"], reverse=True)
    result["top_gainers"] = sorted_holdings[:3]
    result["top_losers"] = sorted_holdings[-3:][::-1]  # Reverse to show biggest loser first

    return result


def get_sector_performance() -> dict:
    """Get sector ETF performance for the day."""
    import yfinance as yf

    sectors = {
        "Technology": "XLK",
        "Healthcare": "XLV",
        "Financials": "XLF",
        "Energy": "XLE",
        "Consumer": "XLY",
        "Industrials": "XLI"
    }

    performance = {}
    for name, ticker in sectors.items():
        try:
            etf = yf.Ticker(ticker)
            info = etf.fast_info
            if info.last_price and info.previous_close:
                change_pct = ((info.last_price - info.previous_close) / info.previous_close) * 100
                performance[name] = change_pct
        except Exception:
            pass

    return performance


def generate_market_summary(indices: dict, sectors: dict) -> str:
    """Use Groq LLM to generate a 1-2 sentence summary of why the market moved today."""
    fallback_summaries = [
        "Markets showed mixed performance today with sector rotation driving most of the movement.",
        "Trading was relatively muted today as investors digested recent economic data.",
        "The market saw broad-based movement today driven by macroeconomic factors.",
    ]

    if not GROQ_API_KEY:
        import random
        return random.choice(fallback_summaries)

    # Build context for the LLM
    indices_str = ", ".join([f"{name} {data['change_pct']:+.2f}%" for name, data in indices.items()])
    sectors_sorted = sorted(sectors.items(), key=lambda x: x[1], reverse=True)
    top_sector = sectors_sorted[0] if sectors_sorted else ("Tech", 0)
    bottom_sector = sectors_sorted[-1] if sectors_sorted else ("Healthcare", 0)

    today = datetime.now().strftime("%B %d, %Y")

    prompt = f"""You are a concise financial analyst. Based on today's market data ({today}), write 1-2 sentences explaining WHY the market moved the way it did.

Today's data:
- Indices: {indices_str}
- Best sector: {top_sector[0]} ({top_sector[1]:+.1f}%)
- Worst sector: {bottom_sector[0]} ({bottom_sector[1]:+.1f}%)

Guidelines:
- Be specific about likely drivers (earnings season, Fed expectations, sector rotation, economic data, etc.)
- Don't just restate the numbers - explain the narrative
- Keep it conversational but informed
- 1-2 sentences max, no fluff

Return ONLY the summary, nothing else."""

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
                "temperature": 0.7
            },
            timeout=15
        )

        if resp.status_code == 200:
            summary = resp.json()["choices"][0]["message"]["content"].strip()
            if summary and len(summary) > 20:
                return summary

    except Exception as e:
        print(f"Groq error: {e}")

    import random
    return random.choice(fallback_summaries)


def format_html_summary() -> str:
    """Build HTML email for afternoon market summary."""
    et = ZoneInfo("America/New_York")
    now = datetime.now(et)
    date_str = now.strftime("%A, %B %d")

    market = get_market_close_data()
    sectors = get_sector_performance()
    summary = generate_market_summary(market.get("indices", {}), sectors)

    # Calculate portfolio daily change
    holdings = market.get("holdings", {})
    if holdings:
        avg_change = sum(h["change_pct"] for h in holdings.values()) / len(holdings)
    else:
        avg_change = 0

    # Build indices section
    indices_html = ""
    for name, data in market.get("indices", {}).items():
        price = data["price"]
        pct = data["change_pct"]
        color = "#22c55e" if pct >= 0 else "#ef4444"
        arrow = "+" if pct >= 0 else ""
        indices_html += f'''
        <div style="display:inline-block;min-width:140px;margin:8px 12px 8px 0;padding:12px;background:#f8fafc;border-radius:8px;border-left:3px solid {color}">
            <div style="color:#64748b;font-size:12px;margin-bottom:4px">{name}</div>
            <div style="font-size:16px;font-weight:600;color:#1e293b">{price:,.0f}</div>
            <div style="color:{color};font-size:14px;font-weight:500">{arrow}{pct:.2f}%</div>
        </div>'''

    # Portfolio summary - color based on overall performance
    portfolio_color = "#22c55e" if avg_change >= 0 else "#ef4444"
    portfolio_arrow = "+" if avg_change >= 0 else ""

    # Holdings grid
    holdings_html = ""
    for ticker, data in holdings.items():
        pct = data["change_pct"]
        price = data["price"]
        color = "#22c55e" if pct >= 0 else "#ef4444"
        arrow = "+" if pct >= 0 else ""
        holdings_html += f'''
        <div style="display:inline-block;width:80px;margin:4px 8px 4px 0;text-align:center">
            <div style="font-weight:600;color:#374151">{ticker}</div>
            <div style="color:{color};font-size:13px">{arrow}{pct:.1f}%</div>
            <div style="color:#9ca3af;font-size:11px">${price:.2f}</div>
        </div>'''

    # Top movers
    movers_html = ""
    gainers = market.get("top_gainers", [])
    losers = market.get("top_losers", [])

    if gainers:
        movers_html += '<div style="margin-bottom:8px"><strong style="color:#22c55e">Top Gainers:</strong> '
        movers_html += ", ".join([f'{g["ticker"]} (+{g["change_pct"]:.1f}%)' for g in gainers if g["change_pct"] > 0])
        movers_html += '</div>'

    if losers:
        movers_html += '<div><strong style="color:#ef4444">Top Losers:</strong> '
        movers_html += ", ".join([f'{l["ticker"]} ({l["change_pct"]:.1f}%)' for l in losers if l["change_pct"] < 0])
        movers_html += '</div>'

    # Sectors
    sectors_html = ""
    sorted_sectors = sorted(sectors.items(), key=lambda x: x[1], reverse=True)
    for name, pct in sorted_sectors:
        color = "#22c55e" if pct >= 0 else "#ef4444"
        arrow = "+" if pct >= 0 else ""
        sectors_html += f'<span style="margin-right:12px;color:{color}">{name} {arrow}{pct:.1f}%</span>'

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:550px;margin:0 auto;padding:20px;background:#f9fafb">
  <div style="background:white;border-radius:12px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
    <h1 style="margin:0 0 4px 0;font-size:20px;color:#111">Market Close - {date_str}</h1>
    <p style="margin:0 0 20px 0;color:#6b7280;font-size:14px">4:00 PM ET Summary</p>

    <div style="margin-bottom:20px;padding:16px;background:linear-gradient(135deg,#eff6ff 0%,#dbeafe 100%);border-radius:8px;border-left:4px solid #3b82f6">
      <p style="margin:0;font-size:14px;color:#1e40af;line-height:1.6">{summary}</p>
    </div>

    <div style="margin-bottom:20px">
      <h2 style="margin:0 0 12px 0;font-size:14px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">Major Indices</h2>
      {indices_html}
    </div>

    <div style="margin-bottom:20px;padding:16px;background:linear-gradient(135deg,#f0fdf4 0%,#dcfce7 100%);border-radius:8px;border-left:4px solid {portfolio_color}">
      <div style="font-size:12px;color:#6b7280;margin-bottom:4px">YOUR PORTFOLIO</div>
      <div style="font-size:24px;font-weight:700;color:{portfolio_color}">{portfolio_arrow}{avg_change:.2f}%</div>
      <div style="color:#6b7280;font-size:12px">Average across {len(holdings)} holdings</div>
    </div>

    <div style="margin-bottom:20px">
      <h2 style="margin:0 0 12px 0;font-size:14px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">Holdings</h2>
      {holdings_html}
      <div style="margin-top:12px;font-size:13px">{movers_html}</div>
    </div>

    <div>
      <h2 style="margin:0 0 10px 0;font-size:14px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">Sectors</h2>
      <div style="font-size:13px">{sectors_html}</div>
    </div>
  </div>
  <p style="text-align:center;color:#9ca3af;font-size:12px;margin-top:16px">Market Close Summary</p>
</body>
</html>
"""
    return html


def send_email(html: str, subject: str):
    """Send email via Resend API."""
    if not RESEND_API_KEY or not EMAIL_TO:
        print("Missing RESEND_API_KEY or EMAIL_TO")
        return False

    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={
                "from": "Market Summary <onboarding@resend.dev>",
                "to": [EMAIL_TO],
                "subject": subject,
                "html": html
            },
            timeout=15
        )

        if resp.status_code == 200:
            print(f"Email sent to {EMAIL_TO}")
            return True
        else:
            print(f"Resend error: {resp.status_code} - {resp.text}")
            return False

    except Exception as e:
        print(f"Email error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Afternoon Market Summary")
    parser.add_argument("--test", action="store_true", help="Print summary without sending")
    parser.add_argument("--send", action="store_true", help="Send summary via email")
    args = parser.parse_args()

    print("Building afternoon market summary...\n")

    if args.test or not args.send:
        market = get_market_close_data()
        sectors = get_sector_performance()
        summary = generate_market_summary(market.get("indices", {}), sectors)

        print("=" * 50)
        print("WHY THE MARKET MOVED")
        print(f"  {summary}")

        print("\nINDICES")
        for name, data in market.get("indices", {}).items():
            arrow = "+" if data["change_pct"] >= 0 else ""
            print(f"  {name}: {data['price']:,.0f} ({arrow}{data['change_pct']:.2f}%)")

        print("\nHOLDINGS")
        for ticker, data in market.get("holdings", {}).items():
            arrow = "+" if data["change_pct"] >= 0 else ""
            print(f"  {ticker}: ${data['price']:.2f} ({arrow}{data['change_pct']:.1f}%)")

        print("\nSECTORS")
        for name, pct in sectors.items():
            arrow = "+" if pct >= 0 else ""
            print(f"  {name}: {arrow}{pct:.1f}%")
        print("=" * 50)

    if args.send:
        et = ZoneInfo("America/New_York")
        now = datetime.now(et)
        subject = f"Market Close - {now.strftime('%b %d')}"
        html = format_html_summary()
        send_email(html, subject)


if __name__ == "__main__":
    main()
