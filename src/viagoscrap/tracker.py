from __future__ import annotations

import asyncio
import re
from typing import Any

from .config import Settings
from .notifier import send_min_drop_email
from .scraper import scrape_listings
from .storage import finish_run, insert_prices, insert_run_started, list_subscribers, refresh_event_stats, utc_now_iso


def parse_price(raw: str) -> tuple[float | None, str | None]:
    if not raw:
        return None, None

    currency = None
    if "\u20ac" in raw or "eur" in raw.lower():
        currency = "EUR"
    elif "$" in raw or "usd" in raw.lower():
        currency = "USD"

    match = re.search(r"(\d[\d\s.,]*)", raw)
    if not match:
        return None, currency

    numeric = match.group(1).replace(" ", "").replace("\u00a0", "")
    if "," in numeric and "." in numeric:
        numeric = numeric.replace(".", "").replace(",", ".")
    elif "," in numeric and "." not in numeric:
        numeric = numeric.replace(",", ".")
    try:
        return float(numeric), currency
    except ValueError:
        return None, currency


def is_price_drop(previous_low: float | None, new_low: float | None) -> bool:
    return previous_low is not None and new_low is not None and new_low < previous_low


def scrape_event_once(
    db_path: str,
    event: dict[str, Any],
    settings: Settings,
    debug: bool = False,
) -> dict[str, Any]:
    run_id = insert_run_started(db_path, int(event["id"]))
    previous_low = event.get("lowest_price_value")
    previous_low_value = float(previous_low) if previous_low is not None else None
    try:
        tickets = asyncio.run(scrape_listings(event["url"], settings, debug=debug))
        now = utc_now_iso()
        rows: list[dict[str, Any]] = []
        for ticket in tickets:
            price_value, currency = parse_price(ticket.price)
            rows.append(
                {
                    "scraped_at": now,
                    "title": ticket.title,
                    "date_label": ticket.date,
                    "price_raw": ticket.price,
                    "price_value": price_value,
                    "currency": currency,
                    "listing_url": ticket.url,
                }
            )

        saved = insert_prices(db_path, int(event["id"]), rows)
        refresh_event_stats(db_path, int(event["id"]))
        valid_prices = [row["price_value"] for row in rows if row["price_value"] is not None]
        min_price = min(valid_prices) if valid_prices else None
        alert_result: dict[str, Any] | None = None
        if is_price_drop(previous_low_value, min_price):
            recipients = [entry["email"] for entry in list_subscribers(db_path, int(event["id"])) if entry.get("email")]
            alert_result = send_min_drop_email(
                event_name=str(event.get("name", f"event-{event['id']}")),
                event_url=str(event.get("url", "")),
                old_price=previous_low_value,
                new_price=float(min_price),
                currency=(rows[0].get("currency") if rows else None) or "EUR",
                recipients=recipients,
            )
        finish_run(
            db_path,
            run_id,
            status="ok",
            error=None,
            items_found=len(tickets),
            items_saved=saved,
            min_price_found=min_price,
        )
        return {
            "event_id": int(event["id"]),
            "items_found": len(tickets),
            "items_saved": saved,
            "min_price_found": min_price,
            "status": "ok",
            "alert": alert_result,
        }
    except Exception as exc:
        finish_run(
            db_path,
            run_id,
            status="error",
            error=str(exc),
            items_found=0,
            items_saved=0,
            min_price_found=None,
        )
        return {"event_id": int(event["id"]), "status": "error", "error": str(exc)}
