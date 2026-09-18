import asyncio, random
from datetime import datetime, timezone
from sqlalchemy import select
from app.config import settings
from app.db import SessionLocal
from app.models import Alert, Listing, ListingSnapshot, ListingStatus
from app.notifications import notify
from app.vinted import VintedClient
def allowed(item:dict,a:Alert)->bool:
    text=str(item.get("title","")).lower()
    if a.exclude_terms and any(x.lower() in text for x in a.exclude_terms):return False
    return not a.include_terms or any(x.lower() in text for x in a.include_terms)
async def scan(a:Alert,client:VintedClient):
    items=await client.search(a)
    async with SessionLocal() as db:
        current=set()
        for item in items:
            if not allowed(item,a):continue
            eid=str(item["id"]);current.add(eid)
            x=await db.scalar(select(Listing).where(Listing.alert_id==a.id,Listing.external_id==eid))
            p=float(item.get("price",{}).get("amount") or item.get("price") or 0)
            if x is None:
                photo=item.get("photo") or {}
                x=Listing(alert_id=a.id,external_id=eid,title=item.get("title",""),price=p,url=item.get("url") or f"{settings.vinted_domain}/items/{eid}",image_url=photo.get("url"),condition=item.get("status"),status=ListingStatus.ACTIVE)
                db.add(x);await db.flush();db.add(ListingSnapshot(listing_id=x.id,price=p,status=ListingStatus.ACTIVE));await db.commit();await notify(x)
            elif x.price!=p:
                x.price=p;x.updated_at=datetime.now(timezone.utc);db.add(ListingSnapshot(listing_id=x.id,price=p,status=x.status));await db.commit()
        db_a=await db.get(Alert,a.id)
        if db_a:db_a.last_scan_at=datetime.now(timezone.utc);await db.commit()
async def run():
    client=VintedClient()
    while True:
        async with SessionLocal() as db: alerts=(await db.scalars(select(Alert).where(Alert.paused==False))).all()
        for a in alerts:
            try: await scan(a,client)
            except Exception as e: print(f"scan alert={a.id} error={e}")
            await asyncio.sleep(max(15,60/settings.scan_global_rpm)+random.uniform(1,8))
        await asyncio.sleep(20)
if __name__=="__main__":asyncio.run(run())
