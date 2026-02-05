from __future__ import annotations

from dataclasses import dataclass
import re
import sys
from typing import Any, Protocol
from urllib.parse import urljoin

from .config import Settings


@dataclass(slots=True)
class Ticket:
    title: str
    date: str
    price: str
    url: str


class _LocatorContext(Protocol):
    def locator(self, selector: str): ...


EURO = "\u20ac"
COOKIE_ACCEPT_SELECTORS = (
    "[data-testid='cookie-compliance-allow-all-button']",
    "button#onetrust-accept-btn-handler",
    "button:has-text('Tout autoriser')",
    "button:has-text('Tout accepter')",
    "button:has-text('Accepter')",
    "button:has-text('Accept all')",
    "button:has-text('Allow all')",
    "[aria-label*='Tout autoriser']",
)


def _debug(enabled: bool, message: str) -> None:
    if enabled:
        print(f"[debug] {message}", file=sys.stderr)


def _extract_price(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    amount_pattern = re.compile(r"(\d[\d\s,.]*\s?(?:\u20ac|\$|EUR|USD))", flags=re.IGNORECASE)
    for line in lines:
        lowered = line.lower()
        if EURO in line or "$" in line or "eur" in lowered or "usd" in lowered:
            amount_match = amount_pattern.search(line)
            return amount_match.group(1).strip() if amount_match else line

    compact = " ".join(lines)
    match = amount_pattern.search(compact)
    return match.group(1).strip() if match else ""


def _extract_all_prices(text: str) -> list[str]:
    pattern = re.compile(r"\d[\d\s,.]*\s?(?:\u20ac|\$|EUR|USD)", flags=re.IGNORECASE)
    seen: set[str] = set()
    out: list[str] = []
    for match in pattern.findall(text):
        price = " ".join(match.split())
        if price not in seen:
            seen.add(price)
            out.append(price)
    return out


async def _try_click_cookie_button(context: _LocatorContext, selector: str) -> bool:
    locator = context.locator(selector).first
    if await locator.count() == 0:
        return False
    if not await locator.is_visible():
        return False
    await locator.click(timeout=2_000)
    return True


async def _accept_cookies(page, debug: bool) -> None:
    contexts: list[_LocatorContext] = [page, *page.frames]
    for context in contexts:
        for selector in COOKIE_ACCEPT_SELECTORS:
            try:
                if await _try_click_cookie_button(context, selector):
                    _debug(debug, f"Cookie popup accepted with '{selector}'")
                    await page.wait_for_timeout(1_000)
                    return
            except Exception:
                continue
    _debug(debug, "No cookie accept button found/clicked")


async def scrape_listings(url: str, settings: Settings, debug: bool = False) -> list[Ticket]:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        _debug(debug, "Launching Chromium")
        browser = await p.chromium.launch(headless=settings.headless)
        page = await browser.new_page()
        _debug(debug, f"Opening page: {url}")
        await page.goto(url, timeout=settings.timeout_ms, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=min(settings.timeout_ms, 20_000))
        except Exception:
            pass
        await _accept_cookies(page, debug)

        # Let dynamic content render before querying cards
        await page.wait_for_timeout(2_500)
        for _ in range(3):
            await page.mouse.wheel(0, 2_000)
            await page.wait_for_timeout(500)
        for expand_selector in [
            "button:has-text('Afficher plus')",
            "button:has-text('Show more')",
            "[data-testid='listings-container'] button",
        ]:
            try:
                btn = page.locator(expand_selector).first
                if await btn.count() and await btn.is_visible():
                    await btn.click(timeout=2_000)
                    _debug(debug, f"Clicked expand button '{expand_selector}'")
                    await page.wait_for_timeout(1_500)
                    break
            except Exception:
                continue

        selector_candidates = [
            "[data-testid='listings-container']",
            "div[data-testid*='listing']:has-text('\u20ac')",
            "li[data-testid*='listing']:has-text('\u20ac')",
            "tr[data-testid*='listing']:has-text('\u20ac')",
            "div[data-testid*='listing']",
            "li[data-testid*='listing']",
            "tr[data-testid*='listing']",
            "div[data-testid='event-card']",
            "a[data-testid='event-link']",
            "article:has-text('\u20ac')",
            "li:has-text('\u20ac')",
        ]

        cards = None
        count = 0
        selected = ""
        for selector in selector_candidates:
            candidate = page.locator(selector)
            candidate_count = await candidate.count()
            _debug(debug, f"Selector '{selector}' -> {candidate_count}")
            if candidate_count > 0:
                cards = candidate
                count = candidate_count
                selected = selector
                break

        if cards is None:
            _debug(debug, "No candidate selector matched any listing.")
            await browser.close()
            return []

        _debug(debug, f"Using selector '{selected}' with {count} nodes")
        items: list[Ticket] = []
        seen: set[tuple[str, str, str]] = set()

        for i in range(count):
            card = cards.nth(i)
            text = await card.inner_text()
            href = await card.get_attribute("href")
            lines = [line.strip() for line in text.splitlines() if line.strip()]

            title = lines[0] if lines else ""
            date = lines[1] if len(lines) > 1 else ""
            full_url = urljoin(page.url, href or "")

            # listings-container often contains all rows in one block; split all prices
            multi_prices = _extract_all_prices(text) if selected == "[data-testid='listings-container']" else []
            if multi_prices:
                for price in multi_prices:
                    key = (title or "Listing", price, full_url)
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append(Ticket(title=title or "Listing", date=date, price=price, url=full_url))
                if debug and i < 3:
                    _debug(debug, f"Container prices extracted: {multi_prices[:8]}")
                continue

            price = _extract_price(text)
            if not price:
                continue

            key = (title, price, full_url)
            if key in seen:
                continue
            seen.add(key)
            items.append(Ticket(title=title, date=date, price=price, url=full_url))
            if debug and i < 5:
                _debug(debug, f"Sample {i + 1}: title='{title}' date='{date}' price='{price}'")

        if not items:
            _debug(debug, "No priced cards found, trying container-level fallback")
            try:
                container_text = await page.locator("[data-testid='listings-container']").inner_text()
                fallback_price = _extract_price(container_text)
                if fallback_price:
                    items.append(Ticket(title="Listing", date="", price=fallback_price, url=page.url))
            except Exception:
                pass
        if not items:
            _debug(debug, "No container price, trying page HTML fallback")
            try:
                html = await page.content()
                candidates = _extract_all_prices(html)
                for price in candidates[:10]:
                    items.append(Ticket(title="Listing", date="", price=price, url=page.url))
            except Exception:
                pass

        _debug(debug, f"Parsed tickets: {len(items)}")
        await browser.close()
        return items


def as_dicts(tickets: list[Ticket]) -> list[dict[str, Any]]:
    return [
        {"title": ticket.title, "date": ticket.date, "price": ticket.price, "url": ticket.url}
        for ticket in tickets
    ]
