"""Fetch stock news and earnings data."""
import yfinance as yf
from datetime import datetime, timedelta
from config import WATCHLIST, MAX_NEWS_PER_STOCK
import warnings

# Suppress pandas deprecation warnings from yfinance
warnings.filterwarnings("ignore", category=DeprecationWarning)


def get_stock_news():
    """Get recent news for watchlist stocks."""
    news_items = []

    for ticker in WATCHLIST:
        try:
            stock = yf.Ticker(ticker)
            news = stock.news

            if news:
                # Handle both list and dict formats
                items = news if isinstance(news, list) else news.get("items", [])

                for item in items[:MAX_NEWS_PER_STOCK]:
                    title = item.get("title") or item.get("content", {}).get("title", "")
                    if title:
                        news_items.append({
                            "ticker": ticker,
                            "title": title,
                            "publisher": item.get("publisher") or item.get("content", {}).get("provider", {}).get("displayName", ""),
                        })
        except Exception as e:
            # Silently skip news errors
            pass

    return news_items


def get_earnings_calendar():
    """Get upcoming earnings dates for watchlist stocks."""
    earnings = []
    today = datetime.now()
    next_week = today + timedelta(days=14)  # Look 2 weeks ahead

    for ticker in WATCHLIST:
        try:
            stock = yf.Ticker(ticker)
            cal = stock.calendar

            if cal is None:
                continue

            # Handle dict format (new yfinance)
            if isinstance(cal, dict):
                earnings_date = cal.get("Earnings Date")
                if earnings_date:
                    # Can be a list or single date
                    if isinstance(earnings_date, list) and len(earnings_date) > 0:
                        earnings_date = earnings_date[0]

                    if hasattr(earnings_date, 'to_pydatetime'):
                        earnings_date = earnings_date.to_pydatetime().replace(tzinfo=None)
                    elif isinstance(earnings_date, str):
                        earnings_date = datetime.strptime(earnings_date[:10], "%Y-%m-%d")

                    if today <= earnings_date <= next_week:
                        earnings.append({
                            "ticker": ticker,
                            "date": earnings_date.strftime("%b %d")
                        })

            # Handle DataFrame format (older yfinance)
            elif hasattr(cal, 'empty') and not cal.empty:
                if 'Earnings Date' in cal.index:
                    earnings_date = cal.loc['Earnings Date']
                    if isinstance(earnings_date, (list, tuple)) and len(earnings_date) > 0:
                        earnings_date = earnings_date[0]

                    if earnings_date and today <= earnings_date <= next_week:
                        earnings.append({
                            "ticker": ticker,
                            "date": earnings_date.strftime("%b %d")
                        })

        except Exception:
            # Skip ETFs and stocks without earnings data
            pass

    return earnings


def get_price_summary():
    """Get current prices and daily change for watchlist."""
    summary = []

    for ticker in WATCHLIST:
        try:
            stock = yf.Ticker(ticker)
            info = stock.fast_info

            current = info.last_price
            prev_close = info.previous_close

            if current and prev_close:
                change_pct = ((current - prev_close) / prev_close) * 100
                summary.append({
                    "ticker": ticker,
                    "price": current,
                    "change_pct": change_pct
                })
        except Exception as e:
            print(f"Error fetching price for {ticker}: {e}")

    return summary


def format_stock_briefing():
    """Format all stock data into briefing text."""
    lines = []

    # Price movers (biggest gainers/losers)
    prices = get_price_summary()
    if prices:
        sorted_prices = sorted(prices, key=lambda x: x["change_pct"], reverse=True)
        top_gainer = sorted_prices[0]
        top_loser = sorted_prices[-1]

        lines.append("📈 MARKETS")
        lines.append(f"↑ {top_gainer['ticker']}: {top_gainer['change_pct']:+.1f}%")
        lines.append(f"↓ {top_loser['ticker']}: {top_loser['change_pct']:+.1f}%")

    # Upcoming earnings
    earnings = get_earnings_calendar()
    if earnings:
        lines.append("")
        lines.append("📅 EARNINGS SOON")
        for e in earnings:
            lines.append(f"• {e['ticker']}: {e['date']}")

    # Top news (limit to 3 total to keep SMS short)
    news = get_stock_news()
    if news:
        lines.append("")
        lines.append("📰 NEWS")
        for item in news[:3]:
            title = item["title"]
            # Truncate title if too long
            if len(title) > 55:
                title = title[:55] + "..."
            lines.append(f"• {item['ticker']}: {title}")

    return "\n".join(lines)


if __name__ == "__main__":
    # Test run
    print(format_stock_briefing())
