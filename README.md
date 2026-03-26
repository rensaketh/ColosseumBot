# ColosseumBot

Small polling bot for the course ticketing challenge. It bootstraps an OctoFence-protected session, polls slot availability, resolves tariffs for a chosen slot, and tries to add tickets to cart.

## Requirements

- Python 3.14+
- Node.js
- macOS is optional, but the success alarm uses `osascript` and `say` when available

Python dependencies are listed in `requirements.txt`.

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
6. On success, `bot/alarm.py` prints a success banner and triggers notification/speech on macOS.

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
