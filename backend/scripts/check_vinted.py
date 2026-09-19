#!/usr/bin/env python3
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.vinted import VintedClient, VintedError


EXPECTED = {"id", "title", "price", "url", "photo", "status"}
PARSER_OPTIONAL = {"url", "photo", "status"}


def print_diagnostics(client: VintedClient) -> None:
    for index, diagnostic in enumerate(client.request_history, start=1):
        source = "fallback JSON-LD" if diagnostic.fallback_used else "API catalogue"
        print(f"Request {index} ({source}) URL: {diagnostic.url}")
        print(f"Request {index} headers (values redacted): {', '.join(diagnostic.headers) or '(none)'}")
        print(f"Request {index} HTTP status: {diagnostic.status_code}")
        if diagnostic.response_body is not None:
            print(f"Request {index} error response body:")
            print(diagnostic.response_body)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the live Vinted catalogue payload against VintRadar parser expectations."
    )
    parser.add_argument("keyword")
    args = parser.parse_args()
    client = VintedClient()
    await client.bootstrap()
    cookie_names = sorted(client.http.cookies.keys())
    print(f"Anonymous cookie obtained: {bool(cookie_names)} names={cookie_names}")
    alert = SimpleNamespace(
        include_terms=[args.keyword],
        min_price=None,
        max_price=None,
        filters={},
    )
    try:
        items = await client.search(alert)
    except VintedError as error:
        print_diagnostics(client)
        raise SystemExit(str(error)) from error

    print_diagnostics(client)
    print(f"Listings: {len(items)}")
    if not items:
        raise SystemExit("No listing returned; cannot validate parser keys")
    first = items[0]
    print("First raw listing:")
    print(json.dumps(first, ensure_ascii=False, indent=2, sort_keys=True))
    keys = set(first)
    missing = sorted(EXPECTED - keys)
    missing_required = sorted((EXPECTED - PARSER_OPTIONAL) - keys)
    new = sorted(keys - EXPECTED)
    print(f"Missing expected keys: {missing}")
    print(f"New/unmapped keys: {new}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_keyword = args.keyword.replace(" ", "_").replace("/", "_")
    out = Path("/app/tests/fixtures/vinted") / f"catalog_{safe_keyword}_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Fixture saved: {out}")
    if missing_required:
        raise SystemExit(f"Parser-breaking missing keys: {missing_required}")


if __name__ == "__main__":
    asyncio.run(main())
