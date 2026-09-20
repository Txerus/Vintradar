from typing import Any

import httpx

from app.config import settings


def notification_payload(listing: Any, label: str = "NEW") -> dict:
    deal_prefix = "🔥 " if label == "DEAL" else ""
    detail = getattr(listing, "pricing_explanation", {}) or {}
    if detail.get("evaluated"):
        delta = 0
        if detail.get("median"):
            delta = round((detail["price"]["total"] / detail["median"] - 1) * 100)
        reason = f"{delta:+d} % vs {detail.get('count', 0)} comparables"
    else:
        reason = f"Prix non évalué — {detail.get('reason', 'comparables insuffisants')}"
    total = getattr(listing, "total_item_price", listing.price)
    external_id = getattr(listing, "external_id", str(listing.id))
    return {
        "topic": settings.ntfy_topic,
        "title": f"{deal_prefix}{listing.title}",
        "message": f"{total:.2f} {listing.currency} · {reason}",
        "click": f"vintradar://item/{listing.id}",
        "actions": [
            {
                "action": "view",
                "label": "Voir sur Vinted",
                "url": f"https://www.vinted.fr/items/{external_id}",
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
