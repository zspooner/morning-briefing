#!/usr/bin/env python3
"""Morning Briefing Bot - High-signal daily email: markets, trending repos, one heads-up."""
import os
from pathlib import Path
import argparse
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# Load .env from script directory
load_dotenv(Path(__file__).parent / ".env")

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_TO = os.getenv("EMAIL_TO")

# Webull API (personal portfolio)
WEBULL_APP_KEY = os.getenv("WEBULL_APP_KEY")
WEBULL_APP_SECRET = os.getenv("WEBULL_APP_SECRET")
WEBULL_ACCOUNT_ID = os.getenv("WEBULL_ACCOUNT_ID")

# Alpaca API — trading bot accounts
# Paper account (v1/v2 strategies, currently active)
ALPACA_PAPER_API_KEY = os.getenv("ALPACA_PAPER_API_KEY")
ALPACA_PAPER_SECRET_KEY = os.getenv("ALPACA_PAPER_SECRET_KEY")
ALPACA_PAPER_URL = "https://paper-api.alpaca.markets"
# Live account (v3 market-neutral PEAD)
ALPACA_V3_API_KEY = os.getenv("ALPACA_V3_API_KEY")
ALPACA_V3_SECRET_KEY = os.getenv("ALPACA_V3_SECRET_KEY")
ALPACA_LIVE_URL = "https://api.alpaca.markets"

# Portfolio holdings
MY_HOLDINGS = [
    "SPY", "QQQ", "NVDA", "PLTR", "HOOD", "GOOG", "SOFI",
    "META", "TSLA", "NBIS", "ASTS", "GRAB", "HIMS"
]

# Target companies for job alerts
TARGET_ORGS = ["anthropics", "janestreet", "twosigma", "citadel", "deepmind"]

# Repos to watch for new releases
WATCHED_REPOS = [
    "anthropics/claude-code",
    "anthropics/anthropic-sdk-python",
    "anthropics/courses",
    "modelcontextprotocol/servers",
]


def _webull_get(path: str, query_params: dict = None):
    """Make an authenticated GET request to the Webull API."""
    import hashlib, hmac, base64, uuid, urllib.parse

    if not WEBULL_APP_KEY or not WEBULL_APP_SECRET:
        return None

    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000+00:00')
    nonce = str(uuid.uuid4())
    host = 'api.webull.com'

    params = {
        'host': host,
        'x-app-key': WEBULL_APP_KEY,
        'x-signature-algorithm': 'HMAC-SHA1',
        'x-signature-version': '1.0',
        'x-signature-nonce': nonce,
        'x-timestamp': timestamp,
    }
    if query_params:
        params.update(query_params)

    sorted_params = '&'.join(f'{k}={v}' for k, v in sorted(params.items()))
    sign_string = f'{path}&{sorted_params}'
    encoded = urllib.parse.quote(sign_string, safe='')
    secret_key = (WEBULL_APP_SECRET + '&').encode()
    signature = base64.b64encode(
        hmac.new(secret_key, encoded.encode(), hashlib.sha1).digest()
    ).decode()

    headers = {
        'host': host, 'x-app-key': WEBULL_APP_KEY, 'x-timestamp': timestamp,
        'x-signature': signature, 'x-signature-algorithm': 'HMAC-SHA1',
        'x-signature-version': '1.0', 'x-signature-nonce': nonce,
        'Content-Type': 'application/json',
    }

    url = f'https://{host}{path}'
    if query_params:
        url += '?' + '&'.join(f'{k}={v}' for k, v in query_params.items())

    return requests.get(url, headers=headers, timeout=15)


def get_webull_portfolio() -> dict | None:
    """Get Webull portfolio: previous day's return via position price changes."""
    if not WEBULL_ACCOUNT_ID:
        return None

    try:
        resp = _webull_get('/account/positions', {
            'account_id': WEBULL_ACCOUNT_ID, 'page_size': '100',
        })
        if not resp or resp.status_code != 200:
            return None

        data = resp.json()
        holdings = data if isinstance(data, list) else data.get('holdings', [])

        # Aggregate by symbol, only active positions (market_value > $10)
        by_symbol = {}
        for h in holdings:
            sym = h.get('symbol', '?')
            mv = float(h.get('market_value', 0))
            qty = float(h.get('qty', 0))
            last_price = float(h.get('last_price', 0))
            if sym not in by_symbol:
                by_symbol[sym] = {"market_value": 0, "qty": 0, "last_price": last_price}
            by_symbol[sym]["market_value"] += mv
            by_symbol[sym]["qty"] += qty

        # Use yfinance to get previous close for daily change
        import yfinance as yf
        symbols = [s for s, d in by_symbol.items() if d["market_value"] > 10]
        daily_changes = []
        total_day_pnl = 0
        total_prev_value = 0

        for sym in symbols:
            try:
                stock = yf.Ticker(sym)
                info = stock.fast_info
                if info.last_price and info.previous_close:
                    day_chg_pct = ((info.last_price - info.previous_close) / info.previous_close) * 100
                    qty = by_symbol[sym]["qty"]
                    day_pnl = (info.last_price - info.previous_close) * qty
                    prev_val = info.previous_close * qty
                    total_day_pnl += day_pnl
                    total_prev_value += prev_val
                    daily_changes.append({
                        "symbol": sym,
                        "price": info.last_price,
                        "day_pnl": day_pnl,
                        "day_pct": day_chg_pct,
                    })
            except Exception:
                pass

        # Add market value for sorting
        for d in daily_changes:
            d["market_value"] = by_symbol.get(d["symbol"], {}).get("market_value", 0)
        daily_changes.sort(key=lambda x: x["market_value"], reverse=True)
        total_day_pct = (total_day_pnl / total_prev_value * 100) if total_prev_value > 0 else 0

        return {
            "day_pnl": total_day_pnl,
            "day_pct": total_day_pct,
            "positions": daily_changes,
        }

    except Exception:
        return None


def _fetch_alpaca_account(api_key: str, secret_key: str, base_url: str, label: str) -> dict | None:
    """Fetch P&L data from a single Alpaca account."""
    if not api_key or not secret_key:
        return None

    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}

    try:
        acct_resp = requests.get(f"{base_url}/v2/account", headers=headers, timeout=10)
        if acct_resp.status_code != 200:
            return None

        acct = acct_resp.json()
        equity = float(acct.get("equity", 0))
        last_equity = float(acct.get("last_equity", 0))

        # Skip empty/unfunded accounts
        if equity < 1 and last_equity < 1:
            return None

        # Yesterday's P&L
        daily_pnl = equity - last_equity if last_equity > 0 else 0
        daily_pct = (daily_pnl / last_equity) * 100 if last_equity > 0 else 0

        # Total return from portfolio history
        total_pnl, total_pct = 0, 0
        hist_resp = requests.get(
            f"{base_url}/v2/account/portfolio/history",
            headers=headers, params={"period": "all", "timeframe": "1D"}, timeout=10,
        )
        if hist_resp.status_code == 200:
            hist = hist_resp.json()
            base_value = hist.get("base_value", 0)
            if base_value and base_value > 0:
                total_pnl = equity - base_value
                total_pct = (total_pnl / base_value) * 100

        # Active positions
        pos_resp = requests.get(f"{base_url}/v2/positions", headers=headers, timeout=10)
        positions = []
        if pos_resp.status_code == 200:
            for p in pos_resp.json():
                positions.append({
                    "symbol": p.get("symbol", ""),
                    "pnl_pct": float(p.get("unrealized_plpc", 0)) * 100,
                })

        return {
            "label": label,
            "equity": equity,
            "daily_pnl": daily_pnl,
            "daily_pct": daily_pct,
            "total_pnl": total_pnl,
            "total_pct": total_pct,
            "positions": positions,
        }

    except Exception:
        return None


def get_bot_pnl() -> list:
    """Get P&L from all active Alpaca accounts (paper + live)."""
    accounts = []

    paper = _fetch_alpaca_account(
        ALPACA_PAPER_API_KEY, ALPACA_PAPER_SECRET_KEY, ALPACA_PAPER_URL, "Paper (v1/v2)"
    )
    if paper:
        accounts.append(paper)

    live = _fetch_alpaca_account(
        ALPACA_V3_API_KEY, ALPACA_V3_SECRET_KEY, ALPACA_LIVE_URL, "Live (v3)"
    )
    if live:
        accounts.append(live)

    return accounts


def get_earnings_calendar() -> list:
    """Get upcoming earnings dates for portfolio holdings (next 14 days)."""
    import yfinance as yf

    earnings = []
    today = datetime.now()
    lookahead = today + timedelta(days=14)

    for ticker in MY_HOLDINGS:
        if ticker in ("SPY", "QQQ"):
            continue
        try:
            stock = yf.Ticker(ticker)
            cal = stock.calendar
            if cal and isinstance(cal, dict):
                earnings_date = cal.get("Earnings Date")
                if earnings_date:
                    if isinstance(earnings_date, list) and len(earnings_date) > 0:
                        earnings_date = earnings_date[0]
                    if hasattr(earnings_date, 'to_pydatetime'):
                        earnings_date = earnings_date.to_pydatetime().replace(tzinfo=None)
                    elif isinstance(earnings_date, str):
                        earnings_date = datetime.strptime(earnings_date[:10], "%Y-%m-%d")
                    if today <= earnings_date <= lookahead:
                        days_away = (earnings_date - today).days
                        earnings.append({
                            "ticker": ticker,
                            "date": earnings_date.strftime("%b %d"),
                            "days_away": days_away,
                        })
        except Exception:
            pass

    earnings.sort(key=lambda x: x["days_away"])
    return earnings


def get_market_overview() -> dict:
    """Fetch market indices and portfolio holdings."""
    import yfinance as yf

    result = {"indices": {}, "holdings": []}

    indices = {"S&P": "^GSPC", "Nasdaq": "^IXIC", "Dow": "^DJI"}
    for name, ticker in indices.items():
        try:
            idx = yf.Ticker(ticker)
            info = idx.fast_info
            if info.last_price and info.previous_close:
                change_pct = ((info.last_price - info.previous_close) / info.previous_close) * 100
                result["indices"][name] = {"price": info.last_price, "change_pct": change_pct}
        except Exception:
            pass

    for ticker in MY_HOLDINGS:
        try:
            stock = yf.Ticker(ticker)
            info = stock.fast_info
            if info.last_price and info.previous_close:
                change_pct = ((info.last_price - info.previous_close) / info.previous_close) * 100
                result["holdings"].append({"ticker": ticker, "price": info.last_price, "change_pct": change_pct})
        except Exception:
            pass

    # Sort by absolute change to surface biggest movers
    result["holdings"].sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    return result


def _is_junk_repo(repo: dict) -> bool:
    """Filter out forks, clones, non-English repos, and low-effort projects."""
    name = (repo.get("name") or "").lower()
    full_name = (repo.get("full_name") or "").lower()
    desc = (repo.get("description") or "")

    # Skip forks
    if repo.get("fork"):
        return True

    # Skip non-English descriptions (CJK characters dominate)
    cjk_count = sum(1 for c in desc if '\u4e00' <= c <= '\u9fff' or '\u3040' <= c <= '\u30ff' or '\uac00' <= c <= '\ud7af')
    if len(desc) > 10 and cjk_count / len(desc) > 0.3:
        return True

    # Skip obvious clones/copies of existing tools
    clone_signals = ["clone", "copy", "replica", "unofficial", "mirror", "fork-of", "alternative-to"]
    if any(s in name for s in clone_signals) or any(s in desc.lower() for s in clone_signals):
        return True

    # Skip repos with "best" or "awesome" lists (usually aggregators, not tools)
    if "awesome-" in name or "-best" in full_name:
        return True

    return False


def _add_relevance(repos: list) -> list:
    """Use Groq to add a 'why you care' line to each repo."""
    if not GROQ_API_KEY or not repos:
        return repos

    repo_lines = "\n".join(
        f"- {r['name']}: {r['description']} ({r['stars']} stars, {r['language']})"
        for r in repos
    )

    prompt = f"""For each GitHub repo below, write ONE sentence (max 12 words) explaining what it DOES and why it's useful.

Rules:
- Say what the tool actually does, not that it "is relevant"
- Be concrete: "Runs Claude Code sessions in parallel across branches" not "Useful for Claude Code"
- If a repo is just a clone/copy of an existing tool with no new capability, say "skip"
- If you can't tell what it does from the description, say "skip"

{repo_lines}

Return ONLY numbered lines. No intro."""

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "max_tokens": 200, "temperature": 0.3},
            timeout=15,
        )
        if resp.status_code == 200:
            lines = resp.json()["choices"][0]["message"]["content"].strip().split("\n")
            for i, line in enumerate(lines):
                if i < len(repos):
                    cleaned = line.lstrip("0123456789.) ").strip()
                    if cleaned.lower() != "skip":
                        repos[i]["why"] = cleaned
    except Exception:
        pass

    # Filter out repos marked as "skip"
    return [r for r in repos if r.get("why")]


def get_trending_repos() -> list:
    """Find high-signal trending repos in AI engineering, Claude, MCP, and quant ML."""
    repos = []
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    seen = set()

    queries = [
        ("claude code OR claude agent OR MCP server OR anthropic", 50),
        ("quant trading machine learning OR algorithmic trading python", 100),
        ("LLM agent framework OR coding agent", 200),
    ]

    for query, min_stars in queries:
        try:
            resp = requests.get(
                "https://api.github.com/search/repositories",
                params={
                    "q": f"{query} created:>{week_ago} stars:>{min_stars}",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": 8,
                },
                headers={"Accept": "application/vnd.github+json"},
                timeout=10,
            )
            if resp.status_code == 200:
                for repo in resp.json().get("items", []):
                    name = repo["full_name"]
                    if name not in seen and not _is_junk_repo(repo):
                        seen.add(name)
                        repos.append({
                            "name": name,
                            "description": (repo.get("description") or "")[:120],
                            "stars": repo.get("stargazers_count", 0),
                            "url": repo.get("html_url", ""),
                            "language": repo.get("language") or "",
                        })
        except Exception:
            pass

    # Also catch established repos that surged this week
    try:
        resp = requests.get(
            "https://api.github.com/search/repositories",
            params={
                "q": f'(claude OR anthropic OR MCP OR "trading bot" OR "quant") stars:>500 pushed:>{week_ago}',
                "sort": "updated",
                "order": "desc",
                "per_page": 10,
            },
            headers={"Accept": "application/vnd.github+json"},
            timeout=10,
        )
        if resp.status_code == 200:
            for repo in resp.json().get("items", []):
                name = repo["full_name"]
                if name not in seen and not _is_junk_repo(repo):
                    seen.add(name)
                    repos.append({
                        "name": name,
                        "description": (repo.get("description") or "")[:120],
                        "stars": repo.get("stargazers_count", 0),
                        "url": repo.get("html_url", ""),
                        "language": repo.get("language") or "",
                    })
    except Exception:
        pass

    repos.sort(key=lambda r: r["stars"], reverse=True)
    # Take top candidates, then filter through LLM for relevance
    return _add_relevance(repos[:8])[:4]


def get_heads_up() -> dict | None:
    """Check for one high-signal alert: new releases from watched repos, or new roles at target companies."""

    # 1. Check watched repos for new releases (last 24h)
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for repo in WATCHED_REPOS:
        try:
            resp = requests.get(
                f"https://api.github.com/repos/{repo}/releases",
                params={"per_page": 1},
                headers={"Accept": "application/vnd.github+json"},
                timeout=10,
            )
            if resp.status_code == 200:
                releases = resp.json()
                if releases:
                    release = releases[0]
                    published = release.get("published_at", "")
                    if published > yesterday:
                        return {
                            "type": "release",
                            "title": f"{repo} {release.get('tag_name', '')}",
                            "body": (release.get("name") or release.get("body") or "")[:120],
                            "url": release.get("html_url", ""),
                        }
        except Exception:
            pass

    # 2. Check target orgs for new public repos (signals new projects/tools)
    for org in TARGET_ORGS:
        try:
            resp = requests.get(
                f"https://api.github.com/orgs/{org}/repos",
                params={"sort": "created", "direction": "desc", "per_page": 1},
                headers={"Accept": "application/vnd.github+json"},
                timeout=10,
            )
            if resp.status_code == 200:
                repos = resp.json()
                if repos:
                    repo = repos[0]
                    created = repo.get("created_at", "")
                    if created > yesterday:
                        return {
                            "type": "new_repo",
                            "title": f"New repo from {org}: {repo.get('name', '')}",
                            "body": (repo.get("description") or "")[:120],
                            "url": repo.get("html_url", ""),
                        }
        except Exception:
            pass

    # 3. Check Hacker News front page for relevant stories
    try:
        resp = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=10)
        if resp.status_code == 200:
            top_ids = resp.json()[:30]
            keywords = ["anthropic", "claude", "quant", "trading bot", "mcp", "coding agent", "ai agent"]
            for story_id in top_ids:
                try:
                    story = requests.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json", timeout=5
                    ).json()
                    title = (story.get("title") or "").lower()
                    if any(kw in title for kw in keywords):
                        return {
                            "type": "hn",
                            "title": story.get("title", ""),
                            "body": f"{story.get('score', 0)} points",
                            "url": story.get("url") or f"https://news.ycombinator.com/item?id={story_id}",
                        }
                except Exception:
                    pass
    except Exception:
        pass

    return None


def get_trending_stocks() -> list:
    """Discovery radar: finds stocks matching the 1-year big winner profile.

    Two-stage approach:
    1. SOCIAL DISCOVERY — ApeWisdom + Yahoo surface names getting early buzz
    2. WINNER PROFILE FILTER — only flag stocks that match the data-driven
       profile of stocks that went on to 2x+ (GBM model, AUC 0.967):
       - Market cap $1-20B (sweet spot for multi-baggers)
       - Price under $50 (lower-priced stocks outperform)
       - Revenue growing (>3%)
       - Higher volatility (>30% annualized — exciting, narrative-driven)
       - Not at all-time highs (still has room to run)
       - Not already up 100%+ in 3 months (missed the move)

    Social buzz is the funnel. The winner profile is the filter.
    """
    MEGA_CAPS = {
        "AAPL", "MSFT", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "NVDA",
        "BRK.A", "BRK.B", "JPM", "V", "MA", "UNH", "JNJ", "WMT", "PG",
        "XOM", "HD", "CVX", "LLY", "ABBV", "MRK", "KO", "PEP", "BAC",
        "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "TQQQ", "SQQQ",
        "SPXL", "SPXS", "VXX", "UVXY",
    }
    FALSE_TICKERS = {
        "A", "I", "AM", "AN", "AT", "BE", "BY", "DO", "GO", "IF",
        "IN", "IS", "IT", "MY", "NO", "OF", "ON", "OR", "SO", "TO",
        "UP", "US", "WE", "DD", "CEO", "IPO", "ETF", "GDP", "SEC",
        "FBI", "CIA", "FDA", "FED", "ATH", "OTM", "ITM", "DTE", "IV",
        "PE", "EPS", "RSI", "IMO", "FYI", "TBH", "EOD", "AH", "PM",
        "TA", "FA", "PT", "SP", "ALL", "FOR", "ARE", "NOW", "NEW",
        "HAS", "CAN", "ONE", "TWO", "OLD", "BIG", "LOW", "RUN",
        "TOP", "AI", "EV", "UK", "EU", "US", "RE", "TD",
    }

    try:
        import math
        import numpy as np
        import yfinance as yf

        # ── Stage 1: Social discovery (find names people are talking about) ──
        reddit_tickers = {}
        for page in range(1, 4):
            try:
                r = requests.get(f"https://apewisdom.io/api/v1.0/filter/all-stocks/page/{page}", timeout=10)
                if r.status_code == 200:
                    for t in r.json().get("results", []):
                        ticker = t.get("ticker", "").upper()
                        if ticker and ticker not in MEGA_CAPS and ticker not in FALSE_TICKERS and len(ticker) <= 5:
                            reddit_tickers[ticker] = t
            except Exception:
                pass

        yahoo_trending = set()
        try:
            r = requests.get("https://query1.finance.yahoo.com/v1/finance/trending/US",
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if r.status_code == 200:
                for q in r.json().get("finance", {}).get("result", [{}])[0].get("quotes", []):
                    sym = q["symbol"]
                    if "-" not in sym:
                        yahoo_trending.add(sym)
        except Exception:
            pass

        # Take ALL Reddit candidates (not just top 50) — the winner profile
        # filter is strict enough, so cast a wide net for social discovery
        top_syms = list(reddit_tickers.keys())
        for sym in yahoo_trending:
            if sym not in reddit_tickers and sym not in MEGA_CAPS and sym not in FALSE_TICKERS:
                top_syms.append(sym)
                reddit_tickers[sym] = {"ticker": sym, "mentions": 0}

        # ── Stage 2: Get data and apply winner profile filter ──
        market_data = {}
        try:
            batch = yf.download(top_syms[:100], period="1y", progress=False, threads=True)
            import pandas as pd
            for sym in top_syms[:100]:
                try:
                    if isinstance(batch.columns, pd.MultiIndex):
                        if sym not in batch.columns.get_level_values("Ticker"):
                            continue
                        df = batch.xs(sym, level="Ticker", axis=1)
                    else:
                        df = batch
                    if df is None or df.empty or len(df) < 50:
                        continue

                    latest = df.iloc[-1]
                    prev = df.iloc[-2]
                    price = float(latest["Close"])
                    if price < 2:
                        continue

                    # Winner profile features
                    ticker_obj = yf.Ticker(sym)
                    info = ticker_obj.fast_info
                    cap = getattr(info, "market_cap", None)

                    # Hard filters from winner analysis
                    if cap and cap > 20e9:
                        continue  # too big for multi-bagger potential
                    if not cap:
                        continue  # can't evaluate without market cap
                    if price > 100:
                        continue  # winner profile: lower-priced stocks outperform

                    # 3-month return (skip if already extended)
                    change_3mo = 0
                    if len(df) >= 63:
                        p63 = float(df["Close"].iloc[-63])
                        change_3mo = (price - p63) / p63 * 100 if p63 > 0 else 0
                    if change_3mo > 100:
                        continue  # already had its run

                    # 52-week high/low
                    high_52w = float(df["Close"].max())
                    low_52w = float(df["Close"].min())
                    pct_from_high = (price - high_52w) / high_52w * 100
                    pct_from_low = (price - low_52w) / low_52w * 100 if low_52w > 0 else 0

                    # Volatility (annualized, 20-day)
                    daily_returns = df["Close"].pct_change().dropna().iloc[-20:]
                    volatility = float(daily_returns.std() * (252 ** 0.5)) if len(daily_returns) >= 10 else 0

                    # Revenue/earnings growth from yfinance
                    rev_growth, earn_growth, profit_margin = None, None, None
                    try:
                        ti = ticker_obj.info
                        rev_growth = ti.get("revenueGrowth")
                        earn_growth = ti.get("earningsGrowth")
                        profit_margin = ti.get("profitMargins")
                    except Exception:
                        pass

                    # 1-month return
                    change_1mo = 0
                    if len(df) >= 21:
                        p21 = float(df["Close"].iloc[-21])
                        change_1mo = (price - p21) / p21 * 100 if p21 > 0 else 0

                    market_data[sym] = {
                        "price": round(price, 2),
                        "change_1d": round(float((price - prev["Close"]) / prev["Close"] * 100), 1),
                        "change_1mo": round(change_1mo, 1),
                        "change_3mo": round(change_3mo, 1),
                        "pct_from_52w_high": round(pct_from_high, 1),
                        "pct_from_52w_low": round(pct_from_low, 1),
                        "volatility": round(volatility * 100, 1),
                        "market_cap": cap,
                        "rev_growth": rev_growth,
                        "earn_growth": earn_growth,
                        "profit_margin": profit_margin,
                    }
                except Exception:
                    pass
        except Exception:
            pass

        # ── Stage 3: Score against winner profile ──
        scored = []
        for sym in top_syms[:100]:
            if sym not in market_data:
                continue

            rd = reddit_tickers.get(sym, {})
            mkt = market_data[sym]
            signals = []
            profile_score = 0  # how many winner profile traits does it match?

            # Trait 1: Right-sized market cap ($1B-$20B, sweet spot $3-8B)
            cap = mkt.get("market_cap")
            if cap:
                if 3e9 <= cap <= 8e9:
                    profile_score += 3
                    signals.append(f"Sweet spot cap (${cap/1e9:.1f}B)")
                elif 1e9 <= cap < 3e9:
                    profile_score += 2
                    signals.append(f"Small cap (${cap/1e9:.1f}B)")
                elif 8e9 < cap <= 20e9:
                    profile_score += 1
                    signals.append(f"Mid cap (${cap/1e9:.1f}B)")
                else:
                    continue  # outside winner range

            # Trait 2: Revenue growing (strongest fundamental signal)
            if mkt["rev_growth"] is not None and mkt["rev_growth"] > 0.03:
                profile_score += 3
                signals.append(f"Revenue growing +{mkt['rev_growth']:.0%}")
            elif mkt["rev_growth"] is not None and mkt["rev_growth"] > 0:
                profile_score += 1
                signals.append(f"Revenue +{mkt['rev_growth']:.0%}")

            # Trait 3: Earnings positive or improving
            if mkt["earn_growth"] is not None and mkt["earn_growth"] > 0:
                profile_score += 2
                signals.append(f"Earnings growing +{mkt['earn_growth']:.0%}")

            # Trait 4: Higher volatility (>30% — exciting, narrative-driven names)
            if mkt["volatility"] > 40:
                profile_score += 2
                signals.append(f"High volatility ({mkt['volatility']}%)")
            elif mkt["volatility"] > 30:
                profile_score += 1
                signals.append(f"Volatile ({mkt['volatility']}%)")

            # Trait 5: Not at all-time highs (room to run)
            if mkt["pct_from_52w_high"] < -20:
                profile_score += 2
                signals.append(f"{abs(mkt['pct_from_52w_high'])}% below 52w high")
            elif mkt["pct_from_52w_high"] < -7:
                profile_score += 1
                signals.append(f"{abs(mkt['pct_from_52w_high'])}% below 52w high")

            # Social signal context (not a profile trait, but useful info)
            mentions = rd.get("mentions", 0) or 0
            mentions_ago = rd.get("mentions_24h_ago") or mentions or 1
            m_accel = (mentions - mentions_ago) / mentions_ago if mentions_ago > 0 else 0
            if m_accel > 0.3 and mentions >= 3:
                signals.append(f"Reddit buzz +{m_accel:.0%}")
            elif mentions >= 5:
                signals.append(f"{mentions} Reddit mentions")
            if sym in yahoo_trending:
                signals.append("Yahoo trending")

            # Require profile score >= 3 (matches multiple winner traits)
            if profile_score < 3:
                continue

            scored.append({
                "ticker": sym, "score": profile_score, "signals": signals,
                "price": mkt["price"], "change_1d": mkt["change_1d"],
                "market_cap": cap, "signal_count": profile_score,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[:5]

        # Log every flag for out-of-sample tracking
        if top:
            import json as _json
            log_path = Path(__file__).parent / "discovery_log.jsonl"
            now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            with open(log_path, "a") as f:
                for t in top:
                    entry = {
                        "date": now_utc,
                        "ticker": t["ticker"],
                        "score": t["score"],
                        "price": t["price"],
                        "signals": t["signals"],
                        "signal_count": t["signal_count"],
                    }
                    f.write(_json.dumps(entry) + "\n")

        return top

    except Exception:
        return []


def format_html_briefing() -> str:
    """Build lean HTML email briefing."""
    et = ZoneInfo("America/New_York")
    now = datetime.now(et)
    date_str = now.strftime("%A, %B %d")

    market = get_market_overview()
    webull = get_webull_portfolio()
    bots = get_bot_pnl()
    earnings = get_earnings_calendar()
    repos = get_trending_repos()
    heads_up = get_heads_up()
    trending = get_trending_stocks()

    # --- Portfolio holdings (Webull positions with daily P&L, sorted by market value) ---
    holdings_html = ""
    if webull:
        for p in webull["positions"]:
            pc = "#22c55e" if p["day_pnl"] >= 0 else "#ef4444"
            arrow = "▲" if p["day_pnl"] >= 0 else "▼"
            ps = "+" if p["day_pnl"] >= 0 else ""
            holdings_html += (
                f'<div style="display:inline-block;width:80px;margin:3px 6px;text-align:center">'
                f'<div style="font-weight:600;color:#374151;font-size:13px">{p["symbol"]}</div>'
                f'<div style="color:{pc};font-size:12px">{arrow}{abs(p["day_pct"]):.1f}%</div>'
                f'<div style="color:{pc};font-size:11px">{ps}${p["day_pnl"]:,.0f}</div>'
                f'</div>'
            )
    else:
        for h in market.get("holdings", []):
            pct = h["change_pct"]
            color = "#22c55e" if pct >= 0 else "#ef4444"
            arrow = "▲" if pct >= 0 else "▼"
            holdings_html += (
                f'<div style="display:inline-block;width:80px;margin:3px 6px;text-align:center">'
                f'<div style="font-weight:600;color:#374151;font-size:13px">{h["ticker"]}</div>'
                f'<div style="color:{color};font-size:12px">{arrow}{abs(pct):.1f}%</div>'
                f'</div>'
            )

    # --- Heads up (single item, if any) ---
    heads_up_html = ""
    if heads_up:
        type_labels = {"release": "🚀 New Release", "new_repo": "✨ New Repo", "hn": "🔶 On HN"}
        label = type_labels.get(heads_up["type"], "📌 Heads Up")
        heads_up_html = (
            f'<div style="margin-bottom:20px;padding:14px;background:#fef3c7;border-radius:8px;'
            f'border-left:4px solid #f59e0b">'
            f'<div style="font-size:11px;color:#92400e;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">{label}</div>'
            f'<a href="{heads_up["url"]}" style="color:#1d4ed8;font-weight:600;text-decoration:none;font-size:14px">'
            f'{heads_up["title"]}</a>'
        )
        if heads_up["body"]:
            heads_up_html += f'<p style="margin:4px 0 0 0;color:#78350f;font-size:13px">{heads_up["body"]}</p>'
        heads_up_html += '</div>'

    # --- Bot P&L ---
    bot_html = ""
    for bot in bots:
        d_color = "#22c55e" if bot["daily_pnl"] >= 0 else "#ef4444"
        t_color = "#22c55e" if bot["total_pnl"] >= 0 else "#ef4444"
        d_sign = "+" if bot["daily_pnl"] >= 0 else ""
        t_sign = "+" if bot["total_pnl"] >= 0 else ""
        pos_count = len(bot["positions"])
        pos_str = ""
        if bot["positions"]:
            pos_parts = []
            for p in bot["positions"][:5]:
                pc = "#22c55e" if p["pnl_pct"] >= 0 else "#ef4444"
                ps = "+" if p["pnl_pct"] >= 0 else ""
                pos_parts.append(f'<span style="color:{pc};font-size:12px">{p["symbol"]} {ps}{p["pnl_pct"]:.1f}%</span>')
            pos_str = f'<div style="margin-top:10px;padding-top:10px;border-top:1px solid rgba(0,0,0,0.06)">{" &nbsp;·&nbsp; ".join(pos_parts)}</div>'
        bot_html += (
            f'<div style="margin-bottom:12px;padding:16px;background:linear-gradient(135deg,#f0fdf4 0%,#dcfce7 100%);'
            f'border-radius:8px;border-left:4px solid #10b981">'
            f'<h2 style="margin:0 0 14px 0;font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">'
            f'Trading Bot — {bot["label"]}</h2>'
            f'<table style="width:100%;border-collapse:collapse"><tr>'
            f'<td style="text-align:center;padding:0 8px;width:33%">'
            f'<div style="color:#64748b;font-size:11px;margin-bottom:4px">Yesterday</div>'
            f'<div style="font-size:18px;font-weight:700;color:{d_color}">{d_sign}${bot["daily_pnl"]:,.0f}</div>'
            f'<div style="color:{d_color};font-size:12px">{d_sign}{bot["daily_pct"]:.1f}%</div></td>'
            f'<td style="text-align:center;padding:0 8px;width:33%;border-left:1px solid rgba(0,0,0,0.06);border-right:1px solid rgba(0,0,0,0.06)">'
            f'<div style="color:#64748b;font-size:11px;margin-bottom:4px">Total Return</div>'
            f'<div style="font-size:18px;font-weight:700;color:{t_color}">{t_sign}${bot["total_pnl"]:,.0f}</div>'
            f'<div style="color:{t_color};font-size:12px">{t_sign}{bot["total_pct"]:.1f}%</div></td>'
            f'<td style="text-align:center;padding:0 8px;width:33%">'
            f'<div style="color:#64748b;font-size:11px;margin-bottom:4px">Positions</div>'
            f'<div style="font-size:18px;font-weight:700;color:#1e293b">{pos_count}</div></td>'
            f'</tr></table>{pos_str}</div>'
        )

    # --- Earnings calendar ---
    earnings_html = ""
    if earnings:
        items = ""
        for e in earnings:
            urgency = "🔴" if e["days_away"] <= 1 else "🟡" if e["days_away"] <= 3 else "⚪"
            items += (
                f'<span style="display:inline-block;margin:3px 10px 3px 0;padding:4px 10px;'
                f'background:#f8fafc;border-radius:4px;font-size:13px">'
                f'{urgency} <strong>{e["ticker"]}</strong> {e["date"]}</span>'
            )
        earnings_html = (
            f'<div style="margin-bottom:18px">'
            f'<h2 style="margin:0 0 8px 0;font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">Earnings Soon</h2>'
            f'{items}</div>'
        )

    # --- Trending stocks (social momentum scanner) ---
    trending_html = ""
    if trending:
        items_html = ""
        for t in trending:
            tier = "🔥" if t["score"] >= 60 else "⚡"
            color = "#22c55e" if t.get("change_1d", 0) >= 0 else "#ef4444"
            chg_str = f"+{t['change_1d']}%" if t.get("change_1d", 0) >= 0 else f"{t['change_1d']}%"
            cap = t.get("market_cap")
            if cap and cap >= 1e9:
                cap_str = f"${cap/1e9:.1f}B"
            elif cap and cap >= 1e6:
                cap_str = f"${cap/1e6:.0f}M"
            else:
                cap_str = ""
            sig_str = " · ".join(t["signals"][:3])
            items_html += (
                f'<div style="margin-bottom:8px;padding:10px 12px;background:#fefce8;border-radius:6px;'
                f'border-left:3px solid #eab308">'
                f'<div style="display:flex;justify-content:space-between;align-items:center">'
                f'<span style="font-weight:700;font-size:14px;color:#1e293b">{tier} {t["ticker"]}'
                f'<span style="font-weight:400;color:#6b7280;font-size:12px;margin-left:6px">{cap_str}</span></span>'
                f'<span style="font-weight:600;color:{color};font-size:13px">${t.get("price", "?")} ({chg_str})</span>'
                f'</div>'
                f'<div style="color:#78350f;font-size:11px;margin-top:4px">{sig_str}</div>'
                f'</div>'
            )
        trending_html = (
            f'<div style="margin-bottom:18px">'
            f'<h2 style="margin:0 0 8px 0;font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">'
            f'📡 On My Radar — Early Discovery</h2>'
            f'{items_html}</div>'
        )

    # --- Trending repos ---
    repos_html = ""
    for repo in repos:
        stars_str = f"⭐ {repo['stars']:,}" if repo["stars"] else ""
        lang_str = f' · {repo["language"]}' if repo["language"] else ""
        why = repo.get("why", repo["description"])
        repos_html += (
            f'<div style="margin-bottom:10px;padding:10px 12px;background:#f0f9ff;border-radius:6px;'
            f'border-left:3px solid #3b82f6">'
            f'<a href="{repo["url"]}" style="color:#1d4ed8;font-weight:600;text-decoration:none;font-size:13px">'
            f'{repo["name"]}</a>'
            f'<span style="color:#6b7280;font-size:11px;margin-left:8px">{stars_str}{lang_str}</span>'
            f'<p style="margin:3px 0 0 0;color:#374151;font-size:12px;line-height:1.4">{why}</p>'
            f'</div>'
        )
    if not repos_html:
        repos_html = '<p style="color:#9ca3af;font-size:13px">Nothing notable this week</p>'

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:480px;margin:0 auto;padding:16px;background:#f9fafb">
  <div style="background:white;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
    <h1 style="margin:0 0 16px 0;font-size:18px;color:#111">☀️ {date_str}</h1>

    {heads_up_html}

    <div style="margin-bottom:18px">
      <h2 style="margin:0 0 8px 0;font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">Portfolio — Last Trading Day</h2>
      <div>{holdings_html}</div>
    </div>

    {bot_html}

    {earnings_html}

    {trending_html}

    <div>
      <h2 style="margin:0 0 8px 0;font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">Trending Repos</h2>
      {repos_html}
    </div>
  </div>
  <p style="text-align:center;color:#9ca3af;font-size:11px;margin-top:12px">Morning Briefing</p>
</body>
</html>"""
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
        market = get_market_overview()
        webull = get_webull_portfolio()
        bots = get_bot_pnl()
        earnings = get_earnings_calendar()
        repos = get_trending_repos()
        heads_up = get_heads_up()

        print("=" * 50)
        if heads_up:
            print(f"⚡ HEADS UP: {heads_up['title']}")
            if heads_up["body"]:
                print(f"  {heads_up['body']}")
            print()

        print("PORTFOLIO — LAST TRADING DAY")
        if webull:
            d_sign = "+" if webull["day_pnl"] >= 0 else ""
            print(f"  Total: {d_sign}${webull['day_pnl']:,.0f} ({d_sign}{webull['day_pct']:.1f}%)")
            for p in webull["positions"][:6]:
                ps = "+" if p["day_pnl"] >= 0 else ""
                print(f"  {p['symbol']}: {ps}${p['day_pnl']:,.0f} ({ps}{p['day_pct']:.1f}%)")
        print()

        for bot in bots:
            d_sign = "+" if bot["daily_pnl"] >= 0 else ""
            t_sign = "+" if bot["total_pnl"] >= 0 else ""
            print(f"BOT — {bot['label']}")
            print(f"  Yesterday: {d_sign}${bot['daily_pnl']:,.0f} ({d_sign}{bot['daily_pct']:.1f}%)")
            print(f"  Total:     {t_sign}${bot['total_pnl']:,.0f} ({t_sign}{bot['total_pct']:.1f}%)")
            if bot["positions"]:
                pos_str = ", ".join(f"{p['symbol']} {'+' if p['pnl_pct']>=0 else ''}{p['pnl_pct']:.1f}%" for p in bot["positions"][:5])
                print(f"  Positions: {pos_str}")
            else:
                print(f"  Positions: 0")
            print()

        if earnings:
            print("EARNINGS SOON")
            for e in earnings:
                print(f"  {e['ticker']}: {e['date']} ({e['days_away']}d)")
            print()

        trending = get_trending_stocks()
        if trending:
            print("ON MY RADAR — EARLY DISCOVERY")
            for t in trending:
                tier = "🔥" if t["score"] >= 60 else "⚡"
                sigs = " · ".join(t["signals"][:3])
                chg = t.get("change_1d", 0)
                print(f"  {tier} {t['ticker']} ${t.get('price','?')} ({'+' if chg>=0 else ''}{chg}%) — {sigs}")
            print()

        print("REPOS")
        for r in repos:
            why = r.get("why", r["description"][:60])
            print(f"  ⭐{r['stars']:,} {r['name']} — {why}")
        print("=" * 50)

    if args.send:
        et = ZoneInfo("America/New_York")
        now = datetime.now(et)
        subject = f"☀️ {now.strftime('%b %d')} — Markets + Repos"
        html = format_html_briefing()
        send_email(html, subject)


if __name__ == "__main__":
    main()
