"""Configuration for morning briefing bot."""
import os
from dotenv import load_dotenv

load_dotenv()

# Your stock watchlist
WATCHLIST = [
    "AAPL", "NVDA", "TSLA", "SPY", "GOOGL", "QQQ",
    "PLTR", "HOOD", "GOOG", "SOFI", "META",
    "NBIS", "ASTS", "GRAB", "HIMS"
]

# Twilio SMS settings
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")  # Your Twilio number
YOUR_PHONE_NUMBER = os.getenv("YOUR_PHONE_NUMBER")  # Your personal number

# Google Calendar settings
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

# Briefing settings
TIMEZONE = "America/New_York"  # EST
MAX_NEWS_PER_STOCK = 2  # Limit news items to keep SMS reasonable
