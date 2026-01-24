# Morning Briefing Bot

Daily automated briefing delivered at 9 AM ET via [ntfy](https://ntfy.sh).

## What You Get

- **Market Overview**: S&P 500, Nasdaq, Dow indices + key economic events
- **Portfolio Watch**: News for your Webull holdings (earnings, upgrades/downgrades, SEC filings)
- **5 Business Ideas**: Fresh, actionable ideas generated daily by Llama (via Groq)

## Setup

### 1. Clone and install

```bash
git clone https://github.com/zspooner/morning-briefing.git
cd morning-briefing
pip install -r requirements.txt
```

### 2. Get API keys

| Service | URL | Purpose |
|---------|-----|---------|
| News API | https://newsapi.org/ | Market headlines & portfolio news |
| Groq | https://console.groq.com/ | Business idea generation (free tier) |
| Webull | Your existing account | Portfolio holdings |

### 3. Configure environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

### 4. Set up GitHub Secrets

Add these secrets to your repo (Settings → Secrets → Actions):

- `NEWS_API_KEY`
- `GROQ_API_KEY`
- `WEBULL_EMAIL`
- `WEBULL_PASSWORD`
- `WEBULL_DEVICE_ID`
- `WEBULL_TRADE_TOKEN`
- `NTFY_TOPIC` (default: `zack-briefing`)

### 5. Subscribe to notifications

On your phone, install the ntfy app and subscribe to your topic (default: `zack-briefing`).

## Usage

### Test locally

```bash
# Preview without sending
python briefing.py --test

# Send to ntfy
python briefing.py --send
```

### Automated delivery

The GitHub Action runs daily at 9:00 AM ET. You can also trigger manually from the Actions tab.

## Output Example

```
**Friday, January 24**

📊 **Markets**
Indices: S&P 500 +0.3%, Nasdaq +0.5%, Dow +0.2%
Key: TSLA earnings
• Fed signals rate decision coming in March

📰 **Portfolio Watch**
⚠️ NVDA: Upgraded to Buy by Morgan Stanley
AAPL: No significant news
MSFT: Cloud revenue beats expectations

💡 **Ideas**
1. Build an AI tool that summarizes earnings calls in 60 seconds
2. Create a Chrome extension for comparing product prices
3. Develop a mobile app for tracking gym progress with AI coach
4. Start a newsletter curating AI research for non-technical founders
5. Build a marketplace connecting local farmers with restaurants
```

## Dependencies

- Python 3.11+
- yfinance (market data)
- newsapi (news headlines)
- groq (Llama 3.3 70B for ideas - free tier)
- webull (portfolio data)
- requests (HTTP client)
