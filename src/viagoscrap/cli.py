from __future__ import annotations

import argparse
import asyncio
import json
import sys

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv() -> bool:
        return False

from .config import Settings
from .scraper import as_dicts, scrape_listings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape Viagogo listings")
    parser.add_argument("--url", required=True, help="Page URL to scrape")
    parser.add_argument("--pretty", action="store_true", help="Pretty JSON output")
    parser.add_argument("--debug", action="store_true", help="Print debug logs to stderr")
    return parser


def main() -> None:
    load_dotenv()
    args = build_parser().parse_args()
    settings = Settings.from_env()
    if args.debug:
        print(f"[debug] headless={settings.headless} timeout_ms={settings.timeout_ms}", file=sys.stderr)
    tickets = asyncio.run(scrape_listings(args.url, settings, debug=args.debug))
    payload = as_dicts(tickets)
    if args.debug and not payload:
        print("[debug] No listings parsed. Selectors may need update for this page.", file=sys.stderr)

    if args.pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
