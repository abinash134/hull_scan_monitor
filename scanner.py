import html
import json
import logging
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone

import requests

import config

log = logging.getLogger("hull_scan")


# ---------------------------------------------------------------------------
# Chartink client
# ---------------------------------------------------------------------------
class ChartinkClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.USER_AGENT})

    def _get_page(self):
        return self._with_retries(
            lambda: self.session.get(config.SCAN_URL, timeout=config.REQUEST_TIMEOUT)
        )

    def _post_process(self, scan_clause, csrf_token):
        return self._with_retries(
            lambda: self.session.post(
                "https://chartink.com/screener/process",
                data={
                    "scan_clause": scan_clause,
                    "debug_clause": "",
                    "column_clause": "",
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRF-TOKEN": csrf_token,
                    "Referer": config.SCAN_URL,
                },
                timeout=config.REQUEST_TIMEOUT,
            )
        )

    @staticmethod
    def _with_retries(fn):
        last_err = None
        for attempt in range(1, config.RETRY_ATTEMPTS + 1):
            try:
                resp = fn()
                if resp.status_code in (200, 419):
                    return resp
                last_err = RuntimeError(f"HTTP {resp.status_code}")
            except requests.RequestException as e:
                last_err = e
            log.warning("Attempt %s/%s failed: %s", attempt, config.RETRY_ATTEMPTS, last_err)
            if attempt < config.RETRY_ATTEMPTS:
                time.sleep(config.RETRY_BACKOFF_SECONDS * attempt)
        raise last_err

    def fetch_scan_clause_and_csrf(self):
        page = self._get_page().text

        csrf_match = re.search(
            r'<meta name="csrf-token" content="([^"]+)"', page
        )
        if not csrf_match:
            raise RuntimeError("Could not find CSRF token on page")
        csrf_token = csrf_match.group(1)

        scan_clause = self._extract_atlas_query(page)
        if not scan_clause:
            raise RuntimeError("Could not extract scan query from page")

        return scan_clause, csrf_token

    @staticmethod
    def _extract_atlas_query(page):
        match = re.search(
            r'<scanner\b[^>]*:scan-json="([^"]+)"', page, re.S
        )
        if not match:
            return None
        try:
            scan_json = json.loads(html.unescape(match.group(1)))
        except (json.JSONDecodeError, ValueError):
            return None
        query = scan_json.get("atlas_query")
        return query if isinstance(query, str) else None

    def run_scan(self, scan_clause, csrf_token):
        resp = self._post_process(scan_clause, csrf_token)
        if resp.status_code == 419:
            raise RuntimeError("CSRF/session token rejected (419)")
        payload = resp.json()
        return payload.get("data", []) or []


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
class ScanDatabase:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TEXT NOT NULL,
                total INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scan_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT,
                bsecode TEXT,
                close REAL,
                per_chg REAL,
                volume INTEGER,
                UNIQUE(scan_id, symbol)
            );

            CREATE INDEX IF NOT EXISTS idx_scan_results_symbol
                ON scan_results(symbol);
            """
        )
        self.conn.commit()

    def record_scan(self, stocks):
        run_at = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute("INSERT INTO scans (run_at, total) VALUES (?, ?)",
                                (run_at, len(stocks)))
        scan_id = cur.lastrowid
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO scan_results
                (scan_id, symbol, name, bsecode, close, per_chg, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    scan_id,
                    s.get("nsecode"),
                    s.get("name"),
                    s.get("bsecode"),
                    s.get("close"),
                    s.get("per_chg"),
                    s.get("volume"),
                )
                for s in stocks
            ],
        )
        self.conn.commit()
        return scan_id, run_at

    def previous_scan_symbols(self, exclude_scan_id):
        row = self.conn.execute(
            "SELECT id FROM scans WHERE id != ? ORDER BY id DESC LIMIT 1",
            (exclude_scan_id,),
        ).fetchone()
        if not row:
            return set()
        rows = self.conn.execute(
            "SELECT DISTINCT symbol FROM scan_results WHERE scan_id = ?",
            (row["id"],),
        ).fetchall()
        return {r["symbol"] for r in rows}

    def all_time_symbols(self):
        rows = self.conn.execute(
            "SELECT DISTINCT symbol FROM scan_results"
        ).fetchall()
        return {r["symbol"] for r in rows}


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
def send_telegram_message(text):
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        log.info("Telegram not configured; skipping alert:\n%s", text)
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        data={"chat_id": config.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
        timeout=config.REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        log.error("Telegram send failed: %s %s", resp.status_code, resp.text)
        return False
    return True


# ---------------------------------------------------------------------------
# Alert formatting
# ---------------------------------------------------------------------------
def format_new_stock_message(stocks, run_at):
    lines = ["*New stocks in HULL Scan!*", ""]
    for s in stocks:
        close = s.get("close")
        chg = s.get("per_chg")
        name = s.get("name") or s.get("nsecode")
        close_txt = f"{close:,.2f}" if isinstance(close, (int, float)) else "—"
        chg_txt = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else "—"
        lines.append(f"• *{s.get('nsecode')}* — {name}")
        lines.append(f"   Close: ₹{close_txt}  ({chg_txt})")
    lines.append("")
    lines.append(f"_Detected at {run_at}_")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run_scan_once(client, db):
    scan_clause, csrf_token = client.fetch_scan_clause_and_csrf()
    stocks = client.run_scan(scan_clause, csrf_token)
    log.info("Scan returned %s stock(s)", len(stocks))

    scan_id, run_at = db.record_scan(stocks)

    current_symbols = {s.get("nsecode") for s in stocks}
    previous_symbols = db.previous_scan_symbols(scan_id)
    new_symbols = current_symbols - previous_symbols

    if new_symbols:
        new_stocks = [s for s in stocks if s.get("nsecode") in new_symbols]
        message = format_new_stock_message(new_stocks, run_at)
        log.info("New stock(s): %s", ", ".join(sorted(new_symbols)))
        send_telegram_message(message)
    else:
        log.info("No new stocks detected")

    return stocks


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    client = ChartinkClient()
    db = ScanDatabase(config.DB_PATH)
    interval_seconds = config.SCAN_INTERVAL_MINUTES * 60

    log.info("HULL Scan monitor started (interval: %s min, db: %s)",
             config.SCAN_INTERVAL_MINUTES, config.DB_PATH)

    while True:
        started = time.time()
        try:
            run_scan_once(client, db)
        except Exception as e:
            log.exception("Scan run failed: %s", e)

        elapsed = time.time() - started
        sleep_for = max(interval_seconds - elapsed, 1)
        log.debug("Next scan in %.0fs", sleep_for)
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
