# ColosseumBot

Small polling bot for the course ticketing challenge. It bootstraps an OctoFence-protected session, polls slot availability, resolves tariffs for a chosen slot, and tries to add tickets to cart.

## Requirements

- Python 3.14+
- Node.js
- macOS is optional, but the local fallback alarm uses `osascript` and `say` when available

Python dependencies are listed in `requirements.txt`. Node.js is a separate system dependency because the bootstrap solver runs `bot/js/solve_inline_challenge.js`.

## Install

If you already use a virtualenv in this repo:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

Or create one first:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Install Node.js separately if it is not already present. For example on macOS with Homebrew:

```bash
brew install node
```

## Notifications

Success notifications now use Twilio first and fall back to the local macOS alarm if Twilio is not configured or the API call fails.

Set these environment variables to enable Twilio calling:

```bash
export TWILIO_ACCOUNT_SID=your_account_sid
export TWILIO_AUTH_TOKEN=your_auth_token
export TWILIO_FROM_NUMBER=+15555550123
export TWILIO_TO_NUMBER=+15555550999
```

You can also copy `.env.example` to `.env.real` and fill in the values there. The bot will auto-load `.env.real` at runtime.

If Twilio variables are not set, the bot will still use the local terminal bell / macOS notification / spoken alert.

## Config

Main settings live in `config.yaml`.

Important fields:

- `active_event`: which event entry to run
- `target_date`: shared target date used by all events unless an event overrides it
- `events.<name>.slug`: event page slug
- `events.<name>.page`: page id used by `calendars_month`
- `events.<name>.object_guid`: optional fixed tariff guid; set `null` to resolve `Full price` dynamically
- `events.<name>.quantity`: number of tickets to add
- `poll_interval_seconds`: polling interval
- `proxy`: optional proxy, or `null`

## How It Works

1. `main.py` loads config and builds a fresh session.
2. `bot/session.py` strips volatile anti-bot cookies from prior runs, applies headers, and creates the HTTP client.
3. `bot/bootstrap.py` visits the site root and the active event page.
4. The bootstrap solver fetches `fp.js`, executes it together with the inline page script in a shared Node VM, and captures cookies like `octofence_jslc` and `octofence_jslc_fp`.
5. `bot/api.py` calls:
   - `calendars_month`
   - `tariffs`
   - `addtocart`
6. On success, `bot/notify.py` tries a Twilio voice call first and falls back to the local alarm in `bot/alarm.py`.

## Run

```bash
venv/bin/python main.py
```

Switch targets by changing `active_event` in `config.yaml`.

## Debug Output

The bot writes investigation artifacts under `debug/`, including:

- blocked HTML pages
- bootstrap inventories
- script scans
- last tariffs response
- last add-to-cart payload

Those files are ignored by git.

## Notes

- `cookies.json` is treated as runtime state and is also gitignored.
- The bootstrap is designed around the current challenge flow and may need updates if the target changes.
