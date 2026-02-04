from __future__ import annotations

import argparse
import asyncio
import json

from dotenv import load_dotenv

from .config import Settings
from .scraper import as_dicts, scrape_listings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape Viagogo listings")
    parser.add_argument("--url", required=True, help="Page URL to scrape")
    parser.add_argument("--pretty", action="store_true", help="Pretty JSON output")
    return parser


def main() -> None:
    load_dotenv()
    args = build_parser().parse_args()
    settings = Settings.from_env()
    tickets = asyncio.run(scrape_listings(args.url, settings))
    payload = as_dicts(tickets)

    if args.pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
