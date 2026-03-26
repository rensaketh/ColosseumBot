import subprocess
import sys


def _escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def sound_alarm(message: str = "Tickets added to cart!"):
    """Play a terminal bell, show a macOS notification, and speak an alert when available."""
    print(f"\n{'='*50}")
    print(f"SUCCESS: {message}")
    print(f"{'='*50}\n")

    # Terminal bell
    print("\a", flush=True)

    # macOS notification
    escaped = _escape_applescript(message)
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{escaped}" with title "ColosseumBot" sound name "Glass"',
            ],
            check=False,
        )
    except FileNotFoundError:
        pass  # not on macOS

    # Spoken fallback tends to be more noticeable than the terminal bell.
    try:
        subprocess.run(
            ["say", "Colosseum Bot alert. Tickets added to cart."],
            check=False,
        )
    except FileNotFoundError:
        pass
