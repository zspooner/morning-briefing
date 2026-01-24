#!/usr/bin/env python3
"""Morning Briefing Bot - Daily briefing with markets, portfolio news, and business ideas."""
import os
import argparse
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Groq API for open source LLM (Llama)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ntfy configuration
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "zack-briefing")
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

# API Keys
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

# Portfolio holdings (hardcoded for now)
MY_HOLDINGS = [
    "SPY", "QQQ", "NVDA", "PLTR", "HOOD", "GOOG", "SOFI",
    "META", "TSLA", "NBIS", "ASTS", "GRAB", "HIMS"
]


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


def get_portfolio_news() -> list:
    """Get news for portfolio holdings from the last 24 hours."""
    if not NEWS_API_KEY:
        return []

    news_items = []
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Skip ETFs, focus on individual stocks
    stocks_to_check = [s for s in MY_HOLDINGS if s not in ["SPY", "QQQ"]]

    for symbol in stocks_to_check[:10]:
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
    return news_items[:8]


def get_ai_news() -> list:
    """Get latest AI development headlines."""
    if not NEWS_API_KEY:
        return []

    try:
        url = "https://newsapi.org/v2/everything"
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        params = {
            "apiKey": NEWS_API_KEY,
            "q": "artificial intelligence OR OpenAI OR ChatGPT OR LLM OR machine learning",
            "from": yesterday,
            "sortBy": "relevancy",
            "pageSize": 5,
            "language": "en"
        }
        resp = requests.get(url, params=params, timeout=10)

        if resp.status_code == 200:
            articles = resp.json().get("articles", [])
            return [
                a.get("title", "").split(" - ")[0]
                for a in articles[:2]
                if a.get("title")
            ]
    except Exception:
        pass

    return []


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

        prompt = f"""Generate exactly 5 startup/side project ideas for {today}.

Requirements:
- Specific and actionable (not vague like "AI tool")
- Mix of weekend projects and bigger SaaS opportunities
- Tied to current trends: AI agents, remote work, creator economy, health tech
- Realistic for a solo developer or small team to build
- Each idea should be 10-15 words, descriptive enough to understand the product

Return ONLY 5 numbered lines. No intro, no explanation.

1. Chrome extension that uses AI to auto-generate LinkedIn posts from articles you read
2. SaaS dashboard for small restaurants to manage DoorDash/UberEats orders in one place
3. Mobile app connecting pet owners with verified local pet sitters for same-day booking
4. Weekly newsletter curating the best AI research papers, summarized for developers
5. Marketplace where Notion power users sell custom templates and automations"""

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
    lines.append(now.strftime("%A, %B %d").upper())
    lines.append("")

    # Market Overview
    market = get_market_overview()

    lines.append("MARKETS")
    if market["futures"]:
        for name, pct in market["futures"].items():
            arrow = "▲" if pct >= 0 else "▼"
            lines.append(f"  {name}: {arrow} {abs(pct):.1f}%")

    if market["events"]:
        lines.append(f"  Today: {', '.join(market['events'][:2])}")

    lines.append("")

    # AI News
    lines.append("AI NEWS")
    ai_news = get_ai_news()
    if ai_news:
        for headline in ai_news[:2]:
            if len(headline) > 55:
                headline = headline[:52] + "..."
            lines.append(f"  • {headline}")
    else:
        lines.append("  No major updates")

    lines.append("")

    # Portfolio Watch
    lines.append("YOUR STOCKS")
    news = get_portfolio_news()

    if news:
        seen_symbols = set()
        for item in news:
            if item["symbol"] not in seen_symbols:
                flag = "!" if item["important"] else " "
                title = item["title"]
                if len(title) > 45:
                    title = title[:42] + "..."
                lines.append(f" {flag}{item['symbol']}: {title}")
                seen_symbols.add(item["symbol"])
                if len(seen_symbols) >= 4:
                    break
    else:
        lines.append("  No significant news")

    lines.append("")

    # Business Ideas
    lines.append("IDEAS")
    ideas = generate_business_ideas()
    for i, idea in enumerate(ideas, 1):
        if len(idea) > 60:
            idea = idea[:57] + "..."
        lines.append(f"  {i}. {idea}")

    return "\n".join(lines)


def send_ntfy(message: str, title: str = "Morning Briefing"):
    """Send notification via ntfy.sh."""
    try:
        # Use JSON body to properly handle unicode in title
        resp = requests.post(
            NTFY_URL,
            json={
                "topic": NTFY_TOPIC,
                "title": title,
                "message": message,
                "tags": ["coffee", "chart_with_upwards_trend"],
                "markdown": True
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
