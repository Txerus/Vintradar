#!/usr/bin/env python3
import argparse
import asyncio
import dataclasses
import json

from app.vinted import VintedClient, VintedError


async def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a live Vinted item page and VintRadar parsing.")
    parser.add_argument("id")
    args = parser.parse_args()
    client = VintedClient()
    try:
        detail = await client.detail(args.id)
    except VintedError as error:
        for request in client.request_history:
            print(f"URL: {request.url}")
            print(f"Final URL: {request.final_url or request.url}")
            print(f"HTTP status: {request.status_code}")
            print(f"Headers sent (values redacted): {', '.join(request.headers)}")
            if request.response_body:
                print(f"Error body: {request.response_body}")
        raise SystemExit(str(error)) from error
    for request in client.request_history:
        print(f"URL: {request.url}")
        print(f"Final URL: {request.final_url or request.url}")
        print(f"HTTP status: {request.status_code}")
        print(f"Headers sent (values redacted): {', '.join(request.headers)}")
    payload = dataclasses.asdict(detail)
    print("Parsed fields:")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    missing = sorted(key for key, value in payload.items() if value in (None, "", []))
    print(f"Unavailable fields: {', '.join(missing) or '(none)'}")


if __name__ == "__main__":
    asyncio.run(main())
