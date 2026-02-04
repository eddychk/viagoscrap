from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playwright.async_api import async_playwright

from .config import Settings


@dataclass(slots=True)
class Ticket:
    title: str
    date: str
    price: str
    url: str


async def scrape_listings(url: str, settings: Settings) -> list[Ticket]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.headless)
        page = await browser.new_page()
        await page.goto(url, timeout=settings.timeout_ms, wait_until="domcontentloaded")

        # Let dynamic content render before querying cards
        await page.wait_for_timeout(2_000)

        cards = page.locator("a[data-testid='event-link'], div[data-testid='event-card']")
        count = await cards.count()
        items: list[Ticket] = []

        for i in range(count):
            card = cards.nth(i)
            text = await card.inner_text()
            href = await card.get_attribute("href")
            lines = [line.strip() for line in text.splitlines() if line.strip()]

            title = lines[0] if lines else ""
            date = lines[1] if len(lines) > 1 else ""
            price = next((line for line in lines if "$" in line or "EUR" in line), "")
            full_url = href if (href or "").startswith("http") else f"https://www.viagogo.com{href or ''}"
            items.append(Ticket(title=title, date=date, price=price, url=full_url))

        await browser.close()
        return items


def as_dicts(tickets: list[Ticket]) -> list[dict[str, Any]]:
    return [ticket.__dict__ for ticket in tickets]
