#!/usr/bin/env python3
"""Morning Briefing Bot - Daily briefing with markets, portfolio news, and business ideas."""
import os
import argparse
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Optional dependencies with graceful degradation
WEBULL_ENABLED = False
try:
    from webull import webull
    WEBULL_ENABLED = True
except ImportError:
    pass

# Groq API for open source LLM (Llama)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ntfy configuration
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "zack-briefing")
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

# API Keys
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
WEBULL_EMAIL = os.getenv("WEBULL_EMAIL")
WEBULL_PASSWORD = os.getenv("WEBULL_PASSWORD")
WEBULL_DEVICE_ID = os.getenv("WEBULL_DEVICE_ID")
WEBULL_TRADE_TOKEN = os.getenv("WEBULL_TRADE_TOKEN")


def get_market_overview() -> dict:
    """Fetch market futures and key economic events."""
    import yfinance as yf

    result = {
        "futures": {},
        "events": [],
        "headlines": []
    }

    # Get futures/pre-market data for major indices
    indices = {
        "S&P 500": "^GSPC",
        "Nasdaq": "^IXIC",
        "Dow": "^DJI"
    }

    for name, ticker in indices.items():
        try:
            idx = yf.Ticker(ticker)
            info = idx.fast_info
            if info.last_price and info.previous_close:
                change_pct = ((info.last_price - info.previous_close) / info.previous_close) * 100
                result["futures"][name] = change_pct
        except Exception:
            pass

    # Get top market headlines from News API
    if NEWS_API_KEY:
        try:
            url = "https://newsapi.org/v2/top-headlines"
            params = {
                "apiKey": NEWS_API_KEY,
                "category": "business",
                "country": "us",
                "pageSize": 5
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                articles = resp.json().get("articles", [])
                result["headlines"] = [
                    a.get("title", "").split(" - ")[0]  # Remove source suffix
                    for a in articles[:3]
                    if a.get("title")
                ]
        except Exception:
            pass

    # Key events (Fed, earnings) - check financial calendars
    # For now, we'll use yfinance to check major earnings
    major_tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA"]
    today = datetime.now()

    for ticker in major_tickers:
        try:
            stock = yf.Ticker(ticker)
            cal = stock.calendar
            if cal and isinstance(cal, dict):
                earnings_date = cal.get("Earnings Date")
                if earnings_date:
                    if isinstance(earnings_date, list):
                        earnings_date = earnings_date[0]
                    if hasattr(earnings_date, 'to_pydatetime'):
                        earnings_date = earnings_date.to_pydatetime().replace(tzinfo=None)
                    if earnings_date.date() == today.date():
                        result["events"].append(f"{ticker} earnings")
        except Exception:
            pass

    return result


def get_webull_holdings() -> list:
    """Fetch current holdings from Webull account."""
    if not WEBULL_ENABLED:
        return []

    if not all([WEBULL_EMAIL, WEBULL_PASSWORD]):
        return []

    holdings = []
    try:
        wb = webull()

        # Login
        wb.login(WEBULL_EMAIL, WEBULL_PASSWORD)

        # Get trade token if provided
        if WEBULL_TRADE_TOKEN:
            wb._trade_token = WEBULL_TRADE_TOKEN

        # Get positions
        positions = wb.get_positions()

        if positions:
            for pos in positions:
                ticker = pos.get("ticker", {}).get("symbol", "")
                if ticker:
                    holdings.append({
                        "symbol": ticker,
                        "shares": float(pos.get("position", 0)),
                        "market_value": float(pos.get("marketValue", 0)),
                        "cost_basis": float(pos.get("costPrice", 0))
                    })
    except Exception as e:
        print(f"Webull error: {e}")

    return holdings


def get_portfolio_news(holdings: list) -> list:
    """Get news for portfolio holdings from the last 24 hours."""
    if not NEWS_API_KEY or not holdings:
        return []

    news_items = []
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    for holding in holdings[:10]:  # Limit to top 10 holdings
        symbol = holding["symbol"]
        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                "apiKey": NEWS_API_KEY,
                "q": f"{symbol} stock",
                "from": yesterday,
                "sortBy": "relevancy",
                "pageSize": 3,
                "language": "en"
            }
            resp = requests.get(url, params=params, timeout=10)

            if resp.status_code == 200:
                articles = resp.json().get("articles", [])

                # Flag important news (earnings, analyst, SEC)
                important_keywords = ["earnings", "upgrade", "downgrade", "analyst", "SEC", "FDA", "lawsuit", "acquire"]

                for article in articles[:2]:
                    title = article.get("title", "")
                    is_important = any(kw.lower() in title.lower() for kw in important_keywords)

                    if title:
                        news_items.append({
                            "symbol": symbol,
                            "title": title.split(" - ")[0],  # Remove source
                            "important": is_important
                        })
        except Exception:
            pass

    # Sort important news first
    news_items.sort(key=lambda x: x["important"], reverse=True)
    return news_items[:8]  # Return top 8 items


def generate_business_ideas() -> list:
    """Generate 5 business ideas using Groq API with Llama."""
    fallback_ideas = [
        "Build an AI-powered code review tool for small teams",
        "Create a subscription box for productivity tools",
        "Develop a mobile app for tracking personal finances",
        "Start a newsletter aggregating startup funding news",
        "Build a marketplace for freelance AI prompt engineers"
    ]

    if not GROQ_API_KEY:
        return fallback_ideas

    try:
        today = datetime.now().strftime("%B %d, %Y")

        prompt = f"""Generate exactly 5 business ideas for today ({today}).

Requirements:
- Each idea should be specific and actionable
- Mix of quick builds (weekend projects) and bigger opportunities
- Tie ideas to current trends (AI, remote work, creator economy, sustainability)
- Ideas should be realistic for a solo developer or small team
- One sentence per idea, max 80 characters each

Format: Return ONLY 5 numbered lines, nothing else.
Example format:
1. Build a Chrome extension that summarizes YouTube videos with AI
2. Create a SaaS for small restaurants to manage online orders
3. Develop an app connecting pet owners with local pet sitters
4. Launch a newsletter curating AI research papers for developers
5. Build a marketplace for selling Notion templates"""

        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": 0.8
            },
            timeout=30
        )

        if resp.status_code == 200:
            response_text = resp.json()["choices"][0]["message"]["content"]
            ideas = []

            for line in response_text.strip().split("\n"):
                line = line.strip()
                if line and line[0].isdigit():
                    # Remove number prefix
                    idea = line.lstrip("0123456789.").strip()
                    if idea:
                        ideas.append(idea)

            return ideas[:5] if ideas else fallback_ideas
        else:
            print(f"Groq API error: {resp.status_code}")
            return fallback_ideas

    except Exception as e:
        print(f"Groq API error: {e}")
        return fallback_ideas


def format_briefing() -> str:
    """Build the complete morning briefing."""
    lines = []

    # Header
    et = ZoneInfo("America/New_York")
    now = datetime.now(et)
    lines.append(f"**{now.strftime('%A, %B %d')}**")
    lines.append("")

    # Market Overview
    market = get_market_overview()

    lines.append("📊 **Markets**")

    # Futures
    if market["futures"]:
        futures_str = ", ".join([
            f"{name} {pct:+.1f}%"
            for name, pct in market["futures"].items()
        ])
        lines.append(f"Indices: {futures_str}")

    # Key events
    if market["events"]:
        lines.append(f"Key: {', '.join(market['events'][:3])}")

    # Top headlines
    if market["headlines"]:
        for headline in market["headlines"][:2]:
            if len(headline) > 60:
                headline = headline[:57] + "..."
            lines.append(f"• {headline}")

    lines.append("")

    # Portfolio Watch
    lines.append("📰 **Portfolio Watch**")

    holdings = get_webull_holdings()

    if holdings:
        news = get_portfolio_news(holdings)

        if news:
            # Group by symbol
            seen_symbols = set()
            for item in news:
                if item["symbol"] not in seen_symbols:
                    flag = "⚠️ " if item["important"] else ""
                    title = item["title"]
                    if len(title) > 50:
                        title = title[:47] + "..."
                    lines.append(f"{flag}{item['symbol']}: {title}")
                    seen_symbols.add(item["symbol"])

                    if len(seen_symbols) >= 5:
                        break
        else:
            for h in holdings[:5]:
                lines.append(f"{h['symbol']}: No significant news")
    else:
        lines.append("(Configure Webull credentials to see portfolio)")

    lines.append("")

    # Business Ideas
    lines.append("💡 **Ideas**")
    ideas = generate_business_ideas()

    for i, idea in enumerate(ideas, 1):
        lines.append(f"{i}. {idea}")

    return "\n".join(lines)


def send_ntfy(message: str, title: str = "Morning Briefing"):
    """Send notification via ntfy.sh."""
    try:
        resp = requests.post(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Tags": "coffee,chart_with_upwards_trend",
                "Markdown": "yes"
            },
            timeout=10
        )
        resp.raise_for_status()
        print(f"✅ Notification sent to {NTFY_TOPIC}")
        return True
    except Exception as e:
        print(f"❌ Failed to send notification: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Morning Briefing Bot")
    parser.add_argument("--test", action="store_true", help="Print briefing without sending")
    parser.add_argument("--send", action="store_true", help="Send briefing via ntfy")
    args = parser.parse_args()

    print("☀️ Building morning briefing...\n")
    briefing = format_briefing()

    if args.test or not args.send:
        print("=" * 50)
        print(briefing)
        print("=" * 50)
        print(f"\nCharacters: {len(briefing)}")

    if args.send:
        et = ZoneInfo("America/New_York")
        now = datetime.now(et)
        title = f"☀️ Morning Briefing - {now.strftime('%b %d')}"
        send_ntfy(briefing, title)


if __name__ == "__main__":
    main()
