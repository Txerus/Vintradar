import httpx
from app.config import settings
async def notify(listing, label:str="NEW"):
    headers={"Title":f"{'🔥 ' if label=='DEAL' else ''}{listing.title}","Click":f"vintradar://item/{listing.id}","Actions":f"view, Voir sur Vinted, {listing.url}","Priority":"high" if label=="DEAL" else "default"}
    if settings.ntfy_token:headers["Authorization"]=f"Bearer {settings.ntfy_token}"
    async with httpx.AsyncClient() as c:
        await c.post(f"{settings.ntfy_url.rstrip('/')}/{settings.ntfy_topic}",content=f"{listing.price:.2f} {listing.currency}",headers=headers,timeout=10)
