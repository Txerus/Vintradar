#!/usr/bin/env python3
import argparse, asyncio, json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from app.vinted import VintedClient

EXPECTED={"id","title","price","url","photo","status"}
PARSER_OPTIONAL={"url","photo","status"}

async def main():
    ap=argparse.ArgumentParser(description="Validate the live Vinted catalog payload against VintRadar parser expectations.")
    ap.add_argument("keyword")
    args=ap.parse_args()
    client=VintedClient()
    await client.bootstrap()
    cookies=client.http.cookies
    cookie_names=sorted(cookies.keys())
    print(f"Anonymous cookie obtained: {bool(cookie_names)} names={cookie_names}")
    alert=SimpleNamespace(include_terms=[args.keyword],min_price=None,max_price=None)
    params={"search_text":args.keyword,"order":"newest_first","per_page":48,"page":1}
    response=await client.http.get(client.base+"/api/v2/catalog/items",params=params,timeout=20)
    print(f"HTTP status: {response.status_code}")
    response.raise_for_status()
    payload=response.json()
    items=payload.get("items",[])
    print(f"Listings: {len(items)}")
    if not items:
        raise SystemExit("No listing returned; cannot validate parser keys")
    first=items[0]
    print("First raw listing:")
    print(json.dumps(first,ensure_ascii=False,indent=2,sort_keys=True))
    keys=set(first)
    missing=sorted(EXPECTED-keys)
    missing_required=sorted((EXPECTED-PARSER_OPTIONAL)-keys)
    new=sorted(keys-EXPECTED)
    print(f"Missing expected keys: {missing}")
    print(f"New/unmapped keys: {new}")
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out=Path("/app/tests/fixtures/vinted")/f"catalog_{args.keyword.replace(' ','_')}_{stamp}.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Fixture saved: {out}")
    if missing_required:
        raise SystemExit(f"Parser-breaking missing keys: {missing_required}")

if __name__=="__main__":
    asyncio.run(main())
