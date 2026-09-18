import asyncio, random
from curl_cffi.requests import AsyncSession
from app.config import settings
class VintedError(RuntimeError):pass
class VintedClient:
    def __init__(self):
        self.base=settings.vinted_domain.rstrip("/")
        self.http=AsyncSession(impersonate="chrome")
        self.ready=False
    async def bootstrap(self):
        r=await self.http.get(self.base+"/",timeout=20)
        if r.status_code>=400: raise VintedError(f"bootstrap {r.status_code}")
        self.ready=True
    async def search(self, alert)->list[dict]:
        if not self.ready: await self.bootstrap()
        params={"search_text":" ".join(alert.include_terms),"order":"newest_first","per_page":48,"page":1}
        if alert.min_price is not None:params["price_from"]=alert.min_price
        if alert.max_price is not None:params["price_to"]=alert.max_price
        for attempt in range(4):
            r=await self.http.get(self.base+"/api/v2/catalog/items",params=params,timeout=20)
            if r.status_code==401:
                self.ready=False; await self.bootstrap(); continue
            if r.status_code in (403,429):
                await asyncio.sleep((2**attempt)+random.random()*2); continue
            if r.status_code>=400:raise VintedError(f"search {r.status_code}")
            return r.json().get("items",[])
        raise VintedError("Vinted temporairement indisponible")
