import os
from pathlib import Path

from bot.alarm import sound_alarm

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - fallback if dependency is missing
    load_dotenv = None


if load_dotenv is not None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env.real")


def notify_success(message: str) -> None:
    """Call via Twilio when configured, otherwise fall back to the local alarm."""
    if send_twilio_call(message):
        return
    sound_alarm(message)


def send_twilio_call(message: str) -> bool:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    to_number = os.getenv("TWILIO_TO_NUMBER")

    if not all([account_sid, auth_token, from_number, to_number]):
        return False

    try:
        from twilio.rest import Client
        from twilio.twiml.voice_response import VoiceResponse
    except Exception:
        return False

    try:
        client = Client(account_sid, auth_token)
        twiml = VoiceResponse()
        twiml.say(message, voice="alice")
        client.calls.create(
            twiml=str(twiml),
            to=to_number,
            from_=from_number,
        )
        print("notification: Twilio call initiated")
        return True
    except Exception as exc:
        print(f"notification: Twilio call failed, falling back to local alarm ({exc})")
        return False
