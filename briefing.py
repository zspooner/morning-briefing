#!/usr/bin/env python3
"""Morning Briefing Bot - Daily briefing with markets, portfolio news, and business ideas."""
import os
import argparse
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_TO = os.getenv("EMAIL_TO")

# Portfolio holdings
MY_HOLDINGS = [
    "SPY", "QQQ", "NVDA", "PLTR", "HOOD", "GOOG", "SOFI",
    "META", "TSLA", "NBIS", "ASTS", "GRAB", "HIMS"
]


def get_market_overview() -> dict:
    """Fetch market data and key economic events."""
    import yfinance as yf

    result = {"futures": {}, "events": [], "headlines": []}

    indices = {"S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Dow": "^DJI"}

    for name, ticker in indices.items():
        try:
            idx = yf.Ticker(ticker)
            info = idx.fast_info
            if info.last_price and info.previous_close:
                change_pct = ((info.last_price - info.previous_close) / info.previous_close) * 100
                result["futures"][name] = change_pct
        except Exception:
            pass

    if NEWS_API_KEY:
        try:
            resp = requests.get(
                "https://newsapi.org/v2/top-headlines",
                params={"apiKey": NEWS_API_KEY, "category": "business", "country": "us", "pageSize": 5},
                timeout=10
            )
            if resp.status_code == 200:
                articles = resp.json().get("articles", [])
                result["headlines"] = [a.get("title", "").split(" - ")[0] for a in articles[:3] if a.get("title")]
        except Exception:
            pass

    # Check for major earnings today
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
    stocks_to_check = [s for s in MY_HOLDINGS if s not in ["SPY", "QQQ"]]

    for symbol in stocks_to_check[:10]:
        try:
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={"apiKey": NEWS_API_KEY, "q": f"{symbol} stock", "from": yesterday, "sortBy": "relevancy", "pageSize": 3, "language": "en"},
                timeout=10
            )
            if resp.status_code == 200:
                articles = resp.json().get("articles", [])
                important_keywords = ["earnings", "upgrade", "downgrade", "analyst", "SEC", "FDA", "lawsuit", "acquire"]

                for article in articles[:2]:
                    title = article.get("title", "")
                    url = article.get("url", "")
                    is_important = any(kw.lower() in title.lower() for kw in important_keywords)
                    if title:
                        news_items.append({"symbol": symbol, "title": title.split(" - ")[0], "url": url, "important": is_important})
        except Exception:
            pass

    news_items.sort(key=lambda x: x["important"], reverse=True)
    return news_items[:8]


def get_ai_news() -> list:
    """Get latest AI development headlines."""
    if not NEWS_API_KEY:
        return []

    try:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={"apiKey": NEWS_API_KEY, "q": "artificial intelligence OR OpenAI OR ChatGPT OR LLM", "from": yesterday, "sortBy": "relevancy", "pageSize": 5, "language": "en"},
            timeout=10
        )
        if resp.status_code == 200:
            articles = resp.json().get("articles", [])
            return [{"title": a.get("title", "").split(" - ")[0], "url": a.get("url", "")} for a in articles[:2] if a.get("title")]
    except Exception:
        pass
    return []


def generate_business_ideas() -> list:
    """Generate 5 business ideas using Groq API with Llama."""
    fallback_ideas = [
        "Chrome extension that auto-generates LinkedIn posts from articles you read",
        "SaaS dashboard for restaurants to manage delivery app orders in one place",
        "Mobile app connecting pet owners with local sitters for same-day booking",
        "Weekly newsletter summarizing AI research papers for developers",
        "Marketplace for Notion power users to sell templates and automations"
    ]

    if not GROQ_API_KEY:
        return fallback_ideas

    try:
        today = datetime.now().strftime("%B %d, %Y")
        prompt = f"""Generate 5 startup ideas for {today}. Each should be specific, actionable, 10-15 words. Mix weekend projects and bigger opportunities. Tied to AI, remote work, creator economy, health tech. Return ONLY 5 numbered lines."""

        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "max_tokens": 300, "temperature": 0.8},
            timeout=30
        )

        if resp.status_code == 200:
            response_text = resp.json()["choices"][0]["message"]["content"]
            ideas = []
            for line in response_text.strip().split("\n"):
                line = line.strip()
                if line and line[0].isdigit():
                    idea = line.lstrip("0123456789.").strip()
                    if idea:
                        ideas.append(idea)
            return ideas[:5] if ideas else fallback_ideas

    except Exception as e:
        print(f"Groq error: {e}")

    return fallback_ideas


def format_html_briefing() -> str:
    """Build HTML email briefing."""
    et = ZoneInfo("America/New_York")
    now = datetime.now(et)
    date_str = now.strftime("%A, %B %d")

    market = get_market_overview()
    ai_news = get_ai_news()
    portfolio_news = get_portfolio_news()
    ideas = generate_business_ideas()

    # Build market section
    market_rows = ""
    for name, pct in market.get("futures", {}).items():
        color = "#22c55e" if pct >= 0 else "#ef4444"
        arrow = "▲" if pct >= 0 else "▼"
        market_rows += f'<tr><td style="padding:4px 12px 4px 0;color:#666">{name}</td><td style="color:{color};font-weight:600">{arrow} {abs(pct):.1f}%</td></tr>'

    events_html = ""
    if market.get("events"):
        events_html = f'<p style="margin:8px 0 0 0;color:#666;font-size:13px">📅 {", ".join(market["events"][:2])}</p>'

    # AI news section
    ai_html = ""
    for item in ai_news[:2]:
        title = item["title"] if isinstance(item, dict) else item
        url = item.get("url", "") if isinstance(item, dict) else ""
        if len(title) > 70:
            title = title[:67] + "..."
        if url:
            ai_html += f'<li style="margin-bottom:8px"><a href="{url}" style="color:#2563eb;text-decoration:none">{title}</a></li>'
        else:
            ai_html += f'<li style="margin-bottom:8px;color:#374151">{title}</li>'
    if not ai_html:
        ai_html = '<li style="color:#9ca3af">No major AI news today</li>'

    # Portfolio section
    portfolio_html = ""
    seen = set()
    for item in portfolio_news:
        if item["symbol"] not in seen:
            title = item["title"]
            url = item.get("url", "")
            if len(title) > 50:
                title = title[:47] + "..."
            flag = "🔔 " if item["important"] else ""
            if url:
                portfolio_html += f'<li style="margin-bottom:8px"><strong>{item["symbol"]}</strong>: {flag}<a href="{url}" style="color:#2563eb;text-decoration:none">{title}</a></li>'
            else:
                portfolio_html += f'<li style="margin-bottom:8px"><strong>{item["symbol"]}</strong>: {flag}{title}</li>'
            seen.add(item["symbol"])
            if len(seen) >= 4:
                break
    if not portfolio_html:
        portfolio_html = '<li style="color:#9ca3af">No significant news for your holdings</li>'

    # Ideas section
    ideas_html = ""
    for i, idea in enumerate(ideas, 1):
        if len(idea) > 70:
            idea = idea[:67] + "..."
        ideas_html += f'<li style="margin-bottom:6px">{idea}</li>'

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:500px;margin:0 auto;padding:20px;background:#f9fafb">
  <div style="background:white;border-radius:12px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
    <h1 style="margin:0 0 20px 0;font-size:20px;color:#111">☀️ {date_str}</h1>

    <div style="margin-bottom:20px">
      <h2 style="margin:0 0 10px 0;font-size:14px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">Markets</h2>
      <table style="font-size:15px">{market_rows}</table>
      {events_html}
    </div>

    <div style="margin-bottom:20px">
      <h2 style="margin:0 0 10px 0;font-size:14px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">🤖 AI News</h2>
      <ul style="margin:0;padding-left:20px;font-size:14px">{ai_html}</ul>
    </div>

    <div style="margin-bottom:20px">
      <h2 style="margin:0 0 10px 0;font-size:14px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">📊 Your Stocks</h2>
      <ul style="margin:0;padding-left:20px;font-size:14px">{portfolio_html}</ul>
    </div>

    <div>
      <h2 style="margin:0 0 10px 0;font-size:14px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">💡 Ideas</h2>
      <ol style="margin:0;padding-left:20px;font-size:14px">{ideas_html}</ol>
    </div>
  </div>
  <p style="text-align:center;color:#9ca3af;font-size:12px;margin-top:16px">Delivered by Morning Briefing Bot</p>
</body>
</html>
"""
    return html


def send_email(html: str, subject: str):
    """Send email via Resend API."""
    if not RESEND_API_KEY or not EMAIL_TO:
        print("❌ Missing RESEND_API_KEY or EMAIL_TO")
        return False

    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={
                "from": "Morning Briefing <onboarding@resend.dev>",
                "to": [EMAIL_TO],
                "subject": subject,
                "html": html
            },
            timeout=15
        )

        if resp.status_code == 200:
            print(f"✅ Email sent to {EMAIL_TO}")
            return True
        else:
            print(f"❌ Resend error: {resp.status_code} - {resp.text}")
            return False

    except Exception as e:
        print(f"❌ Email error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Morning Briefing Bot")
    parser.add_argument("--test", action="store_true", help="Print briefing without sending")
    parser.add_argument("--send", action="store_true", help="Send briefing via email")
    args = parser.parse_args()

    print("☀️ Building morning briefing...\n")

    if args.test or not args.send:
        # Show text preview
        market = get_market_overview()
        ai_news = get_ai_news()
        portfolio_news = get_portfolio_news()
        ideas = generate_business_ideas()

        print("=" * 50)
        print("MARKETS")
        for name, pct in market.get("futures", {}).items():
            arrow = "▲" if pct >= 0 else "▼"
            print(f"  {name}: {arrow} {abs(pct):.1f}%")
        print("\nAI NEWS")
        for h in ai_news[:2]:
            print(f"  • {h[:60]}...")
        print("\nYOUR STOCKS")
        seen = set()
        for item in portfolio_news[:4]:
            if item["symbol"] not in seen:
                print(f"  {item['symbol']}: {item['title'][:45]}...")
                seen.add(item["symbol"])
        print("\nIDEAS")
        for i, idea in enumerate(ideas, 1):
            print(f"  {i}. {idea[:60]}...")
        print("=" * 50)

    if args.send:
        et = ZoneInfo("America/New_York")
        now = datetime.now(et)
        subject = f"☀️ Morning Briefing - {now.strftime('%b %d')}"
        html = format_html_briefing()
        send_email(html, subject)


if __name__ == "__main__":
    main()
