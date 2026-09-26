import os
from types import SimpleNamespace

import httpx
import pytest

from app.notifications import notification_payload, notify


pytestmark = pytest.mark.skipif(
    os.getenv("NTFY_INTEGRATION") != "1",
    reason="requires the real ntfy service container",
)


@pytest.mark.asyncio
async def test_real_ntfy_container_accepts_json_priority_and_custom_click() -> None:
    listing = SimpleNamespace(
        id=277,
        external_id="10144942217",
        title="Édition spéciale 🎮",
        price=25.0,
        total_item_price=26.95,
        currency="EUR",
        pricing_explanation={"evaluated": False, "reason": "test d’intégration"},
    )
    payload = notification_payload(listing, "DEAL")
    assert payload["priority"] == 5
    assert payload["click"] == "vintradar://item/277"
    # CI runners can expose unrelated proxy variables. The test must exercise
    # the local container directly so it cannot silently hit another service.
    async with httpx.AsyncClient(trust_env=False) as client:
        assert await notify(listing, "DEAL", client=client) == 200
