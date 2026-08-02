# HULL Scan Monitor

Scans a Chartink screener every 5 minutes, stores results in SQLite, and
sends a Telegram alert whenever a **new** stock appears in the scan.

## Setup

```bash
pip install -r requirements.txt
```

Configure via environment variables (see `.env.example`):

```bash
export HULL_SCAN_URL="https://chartink.com/screener/hull-scan-28"
export HULL_SCAN_INTERVAL=5
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="123456789"
```

`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are required for alerts. Without
them, new stocks are still recorded in the DB and logged, but no alert is sent.

## Run

```bash
python3 scanner.py
```

Run in the background:

```bash
nohup python3 scanner.py > scanner.log 2>&1 &
```

## How it works

1. Fetches the Chartink page to get a fresh session cookie, CSRF token, and the
   scan's current `atlas_query` (so the scan definition stays up to date).
2. POSTs the query to `/screener/process` to get the current matching stocks.
3. Stores every run in `scan_history.db` (`scans` + `scan_results` tables).
4. Compares the current symbols against the previous run; for any symbol that
   wasn't there last time, sends a Telegram alert with its price/change.

## Files

- `scanner.py` — main program
- `config.py` — configuration from environment variables
- `scan_history.db` — created automatically on first run
