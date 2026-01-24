"""Send SMS notifications via Twilio."""
from twilio.rest import Client
from config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    YOUR_PHONE_NUMBER
)


def send_sms(message: str) -> bool:
    """Send SMS via Twilio."""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, YOUR_PHONE_NUMBER]):
        print("⚠️  Twilio credentials not configured!")
        print("Set these in your .env file:")
        print("  TWILIO_ACCOUNT_SID=xxx")
        print("  TWILIO_AUTH_TOKEN=xxx")
        print("  TWILIO_PHONE_NUMBER=+1xxxxxxxxxx")
        print("  YOUR_PHONE_NUMBER=+1xxxxxxxxxx")
        return False

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        # Twilio SMS limit is 1600 characters
        # Split into multiple messages if needed
        max_length = 1500  # Leave buffer

        if len(message) <= max_length:
            messages = [message]
        else:
            # Split by sections
            messages = []
            current = ""
            for line in message.split("\n"):
                if len(current) + len(line) + 1 > max_length:
                    messages.append(current.strip())
                    current = line + "\n"
                else:
                    current += line + "\n"
            if current.strip():
                messages.append(current.strip())

        for i, msg in enumerate(messages):
            if len(messages) > 1:
                msg = f"[{i+1}/{len(messages)}]\n{msg}"

            client.messages.create(
                body=msg,
                from_=TWILIO_PHONE_NUMBER,
                to=YOUR_PHONE_NUMBER
            )

        print(f"✓ Sent {len(messages)} SMS message(s)")
        return True

    except Exception as e:
        print(f"Error sending SMS: {e}")
        return False


if __name__ == "__main__":
    # Test
    send_sms("Test message from Morning Briefing Bot 🌅")
