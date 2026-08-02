# HULL Scan Monitor

Scans a Chartink screener every 5 minutes, stores results in SQLite, and
sends a Telegram alert whenever a **new** stock appears in the scan.

The scanner runs continuously, but only actually scans during **market hours
(09:30–15:30 IST, Monday–Friday)**. Outside those hours it stays idle.

## Setup

```bash
pip install -r requirements.txt
```

Configure via environment variables (see `.env.example`):

```bash
export HULL_SCAN_URL="https://chartink.com/screener/hull-scan-28"
export HULL_SCAN_INTERVAL=5
export MARKET_TZ="Asia/Kolkata"
export MARKET_OPEN="09:30"
export MARKET_CLOSE="15:30"
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="123456789"
```

`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are required for alerts. Without
them, new stocks are still recorded in the DB and logged, but no alert is sent.

## Deploying on a server (recommended: systemd)

The included `hull-scan-monitor.service` keeps the process running forever and
auto-restarts it on crash or reboot.

```bash
# 1. Copy the project to the server (e.g. from your repo)
scp -r hull_scan_monitor user@server:/opt/hull_scan_monitor

# 2. SSH into the server and install dependencies
ssh user@server
cd /opt/hull_scan_monitor
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 3. Set the Telegram credentials (edit .env.example -> .env or export below)
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="123456789"

# 4. Install the systemd service
sudo cp hull-scan-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable hull-scan-monitor
sudo systemctl start hull-scan-monitor

# 5. Check it's running and watch the log
systemctl status hull-scan-monitor
sudo journalctl -u hull-scan-monitor -f
```

> The systemd service reads env vars from the shell at start time. To make the
> Telegram credentials permanent, put them in the `[Service]` section of the
> unit file (or a systemd environment file):
>
> ```ini
> Environment=TELEGRAM_BOT_TOKEN=123456:ABC...
> Environment=TELEGRAM_CHAT_ID=123456789
> ```
>
> then `sudo systemctl daemon-reload && sudo systemctl restart hull-scan-monitor`.

## Run manually (without systemd)

```bash
nohup python3 scanner.py > scanner.log 2>&1 &
```

To stop:

```bash
pkill -f scanner.py
```

## How it works

1. Fetches the Chartink page to get a fresh session cookie, CSRF token, and the
   scan's current `atlas_query` (so the scan definition stays up to date).
2. Checks whether the market is open (09:30–15:30 IST, Mon–Fri). If not, skips.
3. POSTs the query to `/screener/process` to get the current matching stocks.
4. Stores every run in `scan_history.db` (`scans` + `scan_results` tables).
5. Compares the current symbols against the previous run; for any symbol that
   wasn't there last time, sends a Telegram alert with its price/change.

## Files

- `scanner.py` — main program
- `config.py` — configuration from environment variables
- `hull-scan-monitor.service` — systemd unit for server deployment
- `scan_history.db` — created automatically on first run
