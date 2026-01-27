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
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
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


def get_market_headlines() -> list:
    """Get top business/market headlines from today."""
    if not NEWS_API_KEY:
        return []

    headlines = []
    try:
        resp = requests.get(
            "https://newsapi.org/v2/top-headlines",
            params={
                "apiKey": NEWS_API_KEY,
                "category": "business",
                "country": "us",
                "pageSize": 10
            },
            timeout=10
        )
        if resp.status_code == 200:
            articles = resp.json().get("articles", [])
            for article in articles[:6]:
                title = article.get("title", "")
                url = article.get("url", "")
                source = article.get("source", {}).get("name", "")
                if title and " - " in title:
                    title = title.rsplit(" - ", 1)[0]
                if title:
                    headlines.append({
                        "title": title,
                        "url": url,
                        "source": source
                    })
    except Exception:
        pass

    return headlines


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


def format_html_summary() -> str:
    """Build HTML email for afternoon market summary."""
    et = ZoneInfo("America/New_York")
    now = datetime.now(et)
    date_str = now.strftime("%A, %B %d")

    market = get_market_close_data()
    headlines = get_market_headlines()
    sectors = get_sector_performance()

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

    # Headlines
    headlines_html = ""
    for item in headlines[:5]:
        title = item["title"]
        url = item.get("url", "")
        source = item.get("source", "")
        if len(title) > 80:
            title = title[:77] + "..."
        source_tag = f' <span style="color:#9ca3af">({source})</span>' if source else ""
        if url:
            headlines_html += f'<li style="margin-bottom:10px"><a href="{url}" style="color:#2563eb;text-decoration:none">{title}</a>{source_tag}</li>'
        else:
            headlines_html += f'<li style="margin-bottom:10px;color:#374151">{title}{source_tag}</li>'

    if not headlines_html:
        headlines_html = '<li style="color:#9ca3af">No major headlines today</li>'

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:550px;margin:0 auto;padding:20px;background:#f9fafb">
  <div style="background:white;border-radius:12px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
    <h1 style="margin:0 0 4px 0;font-size:20px;color:#111">Market Close - {date_str}</h1>
    <p style="margin:0 0 20px 0;color:#6b7280;font-size:14px">4:00 PM ET Summary</p>

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

    <div style="margin-bottom:20px">
      <h2 style="margin:0 0 10px 0;font-size:14px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">Sectors</h2>
      <div style="font-size:13px">{sectors_html}</div>
    </div>

    <div>
      <h2 style="margin:0 0 10px 0;font-size:14px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">Today's Headlines</h2>
      <ul style="margin:0;padding-left:20px;font-size:14px;line-height:1.5">{headlines_html}</ul>
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
        headlines = get_market_headlines()
        sectors = get_sector_performance()

        print("=" * 50)
        print("INDICES")
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

        print("\nHEADLINES")
        for h in headlines[:5]:
            print(f"  - {h['title'][:60]}...")
        print("=" * 50)

    if args.send:
        et = ZoneInfo("America/New_York")
        now = datetime.now(et)
        subject = f"Market Close - {now.strftime('%b %d')}"
        html = format_html_summary()
        send_email(html, subject)


if __name__ == "__main__":
    main()
