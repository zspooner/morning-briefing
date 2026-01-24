"""Fetch Google Calendar events."""
import os
import pickle
from datetime import datetime, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import GOOGLE_CALENDAR_ID, TIMEZONE

# If modifying scopes, delete token.pickle
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


def get_credentials():
    """Get or refresh Google Calendar credentials."""
    creds = None
    token_path = Path(__file__).parent / 'token.pickle'
    creds_path = Path(__file__).parent / 'credentials.json'

    # Load existing token
    if token_path.exists():
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)

    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                print("⚠️  credentials.json not found!")
                print("To set up Google Calendar:")
                print("1. Go to https://console.cloud.google.com/")
                print("2. Create a project and enable Calendar API")
                print("3. Create OAuth 2.0 credentials (Desktop app)")
                print("4. Download and save as credentials.json in this folder")
                return None

            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for next run
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)

    return creds


def get_todays_events():
    """Fetch today's calendar events."""
    creds = get_credentials()
    if not creds:
        return []

    try:
        service = build('calendar', 'v3', credentials=creds)

        # Get today's date range
        now = datetime.utcnow()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        events_result = service.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=start_of_day.isoformat() + 'Z',
            timeMax=end_of_day.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        formatted_events = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))

            # Parse time
            if 'T' in start:
                # Has specific time
                event_time = datetime.fromisoformat(start.replace('Z', '+00:00'))
                time_str = event_time.strftime("%-I:%M%p").lower()
            else:
                # All day event
                time_str = "all day"

            formatted_events.append({
                "time": time_str,
                "title": event.get('summary', 'No title'),
                "location": event.get('location', '')
            })

        return formatted_events

    except Exception as e:
        print(f"Error fetching calendar: {e}")
        return []


def format_calendar_briefing():
    """Format calendar events into briefing text."""
    events = get_todays_events()

    if not events:
        return "📆 CALENDAR\nNo events today"

    lines = ["📆 TODAY'S SCHEDULE"]
    for event in events:
        line = f"• {event['time']}: {event['title']}"
        if event['location']:
            line += f" @ {event['location']}"
        lines.append(line)

    return "\n".join(lines)


if __name__ == "__main__":
    # Test run
    print(format_calendar_briefing())
