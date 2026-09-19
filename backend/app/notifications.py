from typing import Any

import httpx

from app.config import settings


def notification_payload(listing: Any, label: str = "NEW") -> dict:
    deal_prefix = "🔥 " if label == "DEAL" else ""
    return {
        "topic": settings.ntfy_topic,
        "title": f"{deal_prefix}{listing.title}",
        "message": f"{listing.price:.2f} {listing.currency}",
        "click": f"vintradar://item/{listing.id}",
        "actions": [
            {
                "action": "view",
                "label": "Voir sur Vinted",
                "url": listing.url,
            }
        ],
        "priority": "high" if label == "DEAL" else "default",
    }


async def notify(listing: Any, label: str = "NEW", client: httpx.AsyncClient | None = None) -> None:
    headers: dict[str, str] = {}
    if settings.ntfy_token:
        headers["Authorization"] = f"Bearer {settings.ntfy_token}"
    owns_client = client is None
    active_client = client or httpx.AsyncClient()
    try:
        response = await active_client.post(
            settings.ntfy_url.rstrip("/"),
            json=notification_payload(listing, label),
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
    finally:
        if owns_client:
            await active_client.aclose()
