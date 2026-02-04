from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.executescript(
            """
            PRAGMA journal_mode = WAL;

            CREATE TABLE IF NOT EXISTS tracked_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_scraped_at TEXT,
                lowest_price_value REAL,
                lowest_price_raw TEXT,
                lowest_currency TEXT,
                lowest_seen_at TEXT
            );

            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                scraped_at TEXT NOT NULL,
                title TEXT,
                date_label TEXT,
                price_raw TEXT,
                price_value REAL,
                currency TEXT,
                listing_url TEXT,
                FOREIGN KEY (event_id) REFERENCES tracked_events(id)
            );

            CREATE TABLE IF NOT EXISTS scrape_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                error TEXT,
                items_found INTEGER NOT NULL DEFAULT 0,
                items_saved INTEGER NOT NULL DEFAULT 0,
                min_price_found REAL,
                FOREIGN KEY (event_id) REFERENCES tracked_events(id)
            );

            CREATE TABLE IF NOT EXISTS subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                event_id INTEGER,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(email, event_id),
                FOREIGN KEY (event_id) REFERENCES tracked_events(id)
            );

            CREATE INDEX IF NOT EXISTS idx_price_history_event_time
                ON price_history(event_id, scraped_at);
            CREATE INDEX IF NOT EXISTS idx_scrape_runs_event_time
                ON scrape_runs(event_id, started_at);
            CREATE INDEX IF NOT EXISTS idx_subscribers_event
                ON subscribers(event_id, active);
            """
        )


def list_events(db_path: str) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, name, url, active, created_at, last_scraped_at,
                   lowest_price_value, lowest_price_raw, lowest_currency, lowest_seen_at
            FROM tracked_events
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_event(db_path: str, event_id: int) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT id, name, url, active, created_at, last_scraped_at,
                   lowest_price_value, lowest_price_raw, lowest_currency, lowest_seen_at
            FROM tracked_events
            WHERE id = ?
            """,
            (event_id,),
        ).fetchone()
    return dict(row) if row else None


def add_event(db_path: str, name: str, url: str, active: bool = True) -> int:
    now = utc_now_iso()
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO tracked_events(name, url, active, created_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                name = excluded.name,
                active = excluded.active
            """,
            (name.strip(), url.strip(), 1 if active else 0, now),
        )
        if cur.lastrowid:
            return int(cur.lastrowid)
        row = conn.execute(
            "SELECT id FROM tracked_events WHERE url = ?",
            (url.strip(),),
        ).fetchone()
    if not row:
        raise RuntimeError("Failed to resolve event id after upsert")
    return int(row["id"])


def active_events(db_path: str) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, name, url, active, created_at, last_scraped_at,
                   lowest_price_value, lowest_price_raw, lowest_currency, lowest_seen_at
            FROM tracked_events
            WHERE active = 1
            ORDER BY id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def insert_run_started(db_path: str, event_id: int) -> int:
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO scrape_runs(event_id, started_at, status)
            VALUES(?, ?, 'running')
            """,
            (event_id, utc_now_iso()),
        )
        return int(cur.lastrowid)


def finish_run(
    db_path: str,
    run_id: int,
    *,
    status: str,
    error: str | None,
    items_found: int,
    items_saved: int,
    min_price_found: float | None,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE scrape_runs
            SET finished_at = ?, status = ?, error = ?, items_found = ?,
                items_saved = ?, min_price_found = ?
            WHERE id = ?
            """,
            (utc_now_iso(), status, error, items_found, items_saved, min_price_found, run_id),
        )


def insert_prices(
    db_path: str,
    event_id: int,
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0
    with _connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO price_history(event_id, scraped_at, title, date_label, price_raw, price_value, currency, listing_url)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    event_id,
                    row["scraped_at"],
                    row.get("title"),
                    row.get("date_label"),
                    row.get("price_raw"),
                    row.get("price_value"),
                    row.get("currency"),
                    row.get("listing_url"),
                )
                for row in rows
            ],
        )
    return len(rows)


def refresh_event_stats(db_path: str, event_id: int) -> None:
    with _connect(db_path) as conn:
        lowest = conn.execute(
            """
            SELECT price_value, price_raw, currency, scraped_at
            FROM price_history
            WHERE event_id = ? AND price_value IS NOT NULL
            ORDER BY price_value ASC, scraped_at ASC
            LIMIT 1
            """,
            (event_id,),
        ).fetchone()
        last_scrape = conn.execute(
            """
            SELECT MAX(scraped_at) AS last_scraped_at
            FROM price_history
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchone()
        conn.execute(
            """
            UPDATE tracked_events
            SET last_scraped_at = ?,
                lowest_price_value = ?,
                lowest_price_raw = ?,
                lowest_currency = ?,
                lowest_seen_at = ?
            WHERE id = ?
            """,
            (
                last_scrape["last_scraped_at"] if last_scrape else None,
                lowest["price_value"] if lowest else None,
                lowest["price_raw"] if lowest else None,
                lowest["currency"] if lowest else None,
                lowest["scraped_at"] if lowest else None,
                event_id,
            ),
        )


def event_history(db_path: str, event_id: int, limit: int = 500) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, event_id, scraped_at, title, date_label, price_raw, price_value, currency, listing_url
            FROM price_history
            WHERE event_id = ?
            ORDER BY scraped_at DESC, id DESC
            LIMIT ?
            """,
            (event_id, max(1, min(limit, 5000))),
        ).fetchall()
    return [dict(row) for row in rows]


def chart_points(db_path: str, event_id: int) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT scraped_at, MIN(price_value) AS min_price
            FROM price_history
            WHERE event_id = ? AND price_value IS NOT NULL
            GROUP BY scraped_at
            ORDER BY scraped_at
            """,
            (event_id,),
        ).fetchall()
    return [{"scraped_at": row["scraped_at"], "min_price": row["min_price"]} for row in rows]


def list_runs(db_path: str, event_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
    sql = """
        SELECT id, event_id, started_at, finished_at, status, error, items_found, items_saved, min_price_found
        FROM scrape_runs
    """
    params: tuple[Any, ...] = ()
    if event_id is not None:
        sql += " WHERE event_id = ?"
        params = (event_id,)
    sql += " ORDER BY started_at DESC LIMIT ?"
    params += (max(1, min(limit, 1000)),)
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def add_subscriber(db_path: str, email: str, event_id: int | None) -> int:
    clean_email = email.strip().lower()
    now = utc_now_iso()
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO subscribers(email, event_id, active, created_at)
            VALUES(?, ?, 1, ?)
            ON CONFLICT(email, event_id) DO UPDATE SET active = 1
            """,
            (clean_email, event_id, now),
        )
        if cur.lastrowid:
            return int(cur.lastrowid)
        row = conn.execute(
            "SELECT id FROM subscribers WHERE email = ? AND event_id IS ?",
            (clean_email, event_id),
        ).fetchone()
    if not row:
        raise RuntimeError("Failed to resolve subscriber id after upsert")
    return int(row["id"])


def list_subscribers(db_path: str, event_id: int | None = None) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        if event_id is None:
            rows = conn.execute(
                """
                SELECT id, email, event_id, active, created_at
                FROM subscribers
                WHERE active = 1
                ORDER BY created_at DESC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, email, event_id, active, created_at
                FROM subscribers
                WHERE active = 1 AND (event_id IS NULL OR event_id = ?)
                ORDER BY created_at DESC
                """,
                (event_id,),
            ).fetchall()
    return [dict(row) for row in rows]


def deactivate_subscriber(db_path: str, subscriber_id: int) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE subscribers SET active = 0 WHERE id = ?",
            (subscriber_id,),
        )
