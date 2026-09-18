from datetime import datetime, timezone
from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import session
from app.models import Alert, Listing, ListingSnapshot, UserFlag
from app.schemas import AlertIn, AlertOut, ListingOut, FlagIn, FlagOut, SnapshotOut, DashboardOut
from app.security import require_token
app=FastAPI(title="VintRadar API",version="0.1.0")
@app.get("/health")
async def health():return {"status":"ok"}
@app.get("/alerts",response_model=list[AlertOut],dependencies=[Depends(require_token)])
async def alerts(db:AsyncSession=Depends(session)):return (await db.scalars(select(Alert).order_by(Alert.id))).all()
@app.post("/alerts",response_model=AlertOut,dependencies=[Depends(require_token)])
async def create_alert(body:AlertIn,db:AsyncSession=Depends(session)):
    a=Alert(**body.model_dump());db.add(a);await db.commit();await db.refresh(a);return a
@app.get("/alerts/{aid}",response_model=AlertOut,dependencies=[Depends(require_token)])
async def get_alert(aid:int,db:AsyncSession=Depends(session)):
    a=await db.get(Alert,aid)
    if not a:raise HTTPException(404)
    return a
@app.patch("/alerts/{aid}",response_model=AlertOut,dependencies=[Depends(require_token)])
async def patch_alert(aid:int,body:AlertIn,db:AsyncSession=Depends(session)):
    a=await db.get(Alert,aid)
    if not a:raise HTTPException(404)
    for k,v in body.model_dump().items():setattr(a,k,v)
    await db.commit();await db.refresh(a);return a
@app.delete("/alerts/{aid}",status_code=204,dependencies=[Depends(require_token)])
async def delete_alert(aid:int,db:AsyncSession=Depends(session)):
    a=await db.get(Alert,aid)
    if not a:raise HTTPException(404)
    await db.delete(a);await db.commit()
@app.post("/alerts/{aid}/pause",response_model=AlertOut,dependencies=[Depends(require_token)])
async def pause(aid:int,db:AsyncSession=Depends(session)):
    a=await db.get(Alert,aid)
    if not a:raise HTTPException(404)
    a.paused=not a.paused;await db.commit();await db.refresh(a);return a
@app.get("/listings",response_model=list[ListingOut],dependencies=[Depends(require_token)])
async def listings(alert_id:int|None=None,q:str|None=None,limit:int=Query(50,le=100),offset:int=0,db:AsyncSession=Depends(session)):
    s=select(Listing).order_by(Listing.created_at.desc()).limit(limit).offset(offset)
    if alert_id:s=s.where(Listing.alert_id==alert_id)
    if q:s=s.where(Listing.title.ilike(f"%{q}%"))
    return (await db.scalars(s)).all()
@app.get("/listings/{lid}",response_model=ListingOut,dependencies=[Depends(require_token)])
async def listing(lid:int,db:AsyncSession=Depends(session)):
    x=await db.get(Listing,lid)
    if not x:raise HTTPException(404)
    return x
@app.get("/listings/{lid}/history",response_model=list[SnapshotOut],dependencies=[Depends(require_token)])
async def listing_history(lid:int,db:AsyncSession=Depends(session)):
    return (await db.scalars(select(ListingSnapshot).where(ListingSnapshot.listing_id==lid).order_by(ListingSnapshot.observed_at))).all()
@app.get("/flags",response_model=list[FlagOut],dependencies=[Depends(require_token)])
async def flags(db:AsyncSession=Depends(session)):
    return (await db.scalars(select(UserFlag).order_by(UserFlag.listing_id))).all()
async def set_flag(lid:int,key:str,body:FlagIn,db:AsyncSession):
    f=await db.get(UserFlag,lid)
    if not f:f=UserFlag(listing_id=lid);db.add(f)
    setattr(f,key,body.value);await db.commit();return {"ok":True}
@app.put("/listings/{lid}/favorite",dependencies=[Depends(require_token)])
async def favorite(lid:int,body:FlagIn,db:AsyncSession=Depends(session)):return await set_flag(lid,"favorite",body,db)
@app.put("/listings/{lid}/seen",dependencies=[Depends(require_token)])
async def seen(lid:int,body:FlagIn,db:AsyncSession=Depends(session)):return await set_flag(lid,"seen",body,db)
@app.put("/listings/{lid}/hidden",dependencies=[Depends(require_token)])
async def hidden(lid:int,body:FlagIn,db:AsyncSession=Depends(session)):return await set_flag(lid,"hidden",body,db)
@app.get("/dashboard",response_model=DashboardOut,dependencies=[Depends(require_token)])
async def dashboard(db:AsyncSession=Depends(session)):
    ac=await db.scalar(select(func.count()).select_from(Alert));lc=await db.scalar(select(func.count()).select_from(Listing));active=await db.scalar(select(func.count()).select_from(Listing).where(Listing.status=="ACTIVE"));last=await db.scalar(select(func.max(Alert.last_scan_at)))
    return DashboardOut(alerts=ac or 0,listings=lc or 0,active=active or 0,last_scan_at=last)
@app.get("/worker/status",dependencies=[Depends(require_token)])
async def worker_status(db:AsyncSession=Depends(session)):
    last=await db.scalar(select(func.max(Alert.last_scan_at)));return {"last_scan_at":last,"now":datetime.now(timezone.utc)}
