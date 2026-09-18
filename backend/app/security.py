from fastapi import Header, HTTPException
from app.config import settings
async def require_token(authorization:str|None=Header(default=None)):
    if authorization != f"Bearer {settings.vintradar_api_token}":
        raise HTTPException(401,"Token invalide")
