import subprocess
import sys


def sound_alarm(message: str = "Tickets added to cart!"):
    """Play a system beep and show a macOS notification."""
    print(f"\n{'='*50}")
    print(f"SUCCESS: {message}")
    print(f"{'='*50}\n")

    # Terminal bell
    print("\a", flush=True)

    # macOS notification
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{message}" with title "ColosseumBot" sound name "Glass"',
            ],
            check=False,
        )
    except FileNotFoundError:
        pass  # not on macOS
