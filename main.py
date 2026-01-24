#!/usr/bin/env python3
"""Morning Briefing Bot - Daily SMS with calendar + stock updates."""
import argparse
from datetime import datetime

from stocks import format_stock_briefing

# Calendar is optional - requires Google API setup
try:
    from calendar_fetch import format_calendar_briefing
    CALENDAR_ENABLED = True
except ImportError:
    CALENDAR_ENABLED = False

# SMS is optional - requires Twilio setup
try:
    from notifier import send_sms
    SMS_ENABLED = True
except ImportError:
    SMS_ENABLED = False


def build_briefing() -> str:
    """Build the full morning briefing message."""
    lines = []

    # Header
    today = datetime.now()
    lines.append(f"☀️ MORNING BRIEFING")
    lines.append(f"{today.strftime('%A, %B %d')}")
    lines.append("")

    # Calendar section (if enabled)
    if CALENDAR_ENABLED:
        try:
            lines.append(format_calendar_briefing())
            lines.append("")
        except Exception as e:
            lines.append("📆 CALENDAR")
            lines.append("(not configured)")
            lines.append("")
    else:
        lines.append("📆 CALENDAR")
        lines.append("(install google-api-python-client to enable)")
        lines.append("")

    # Stock section
    lines.append(format_stock_briefing())

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Morning Briefing Bot")
    parser.add_argument("--test", action="store_true", help="Print briefing without sending SMS")
    parser.add_argument("--sms", action="store_true", help="Send briefing via SMS")
    args = parser.parse_args()

    print("Building morning briefing...\n")
    briefing = build_briefing()

    if args.test or not args.sms:
        print("=" * 40)
        print(briefing)
        print("=" * 40)
        print(f"\nCharacter count: {len(briefing)}")

    if args.sms:
        if SMS_ENABLED:
            print("\nSending via SMS...")
            send_sms(briefing)
        else:
            print("\n⚠️  SMS not available. Install twilio: pip install twilio")


if __name__ == "__main__":
    main()
