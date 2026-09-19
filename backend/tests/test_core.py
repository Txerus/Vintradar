from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.normalizer import normalize
from app.notifications import notification_payload, notify
from app.pricing import robust_score
from app.worker import alert_is_due, allowed, score_reaches_threshold


class AlertFixture:
    include_terms = ["technic", "concorde"]
    exclude_terms = ["lot"]


def test_lego_normalization() -> None:
    normalized = normalize("LEGO Technic 42146 neuf scellé")
    assert normalized.key == "lego:42146"
    assert "SEALED" in normalized.flags


def test_scoring_and_thresholds() -> None:
    score = robust_score(10, [10, 20, 30, 40, 50, 60, 1000])
    assert score is not None
    assert score.label == "DEAL"
    assert score.median < 100
    assert score_reaches_threshold(score, "DEAL")
    assert score_reaches_threshold(score, "GOOD")


def test_filters() -> None:
    assert allowed({"title": "LEGO Concorde"}, AlertFixture())
    assert not allowed({"title": "lot LEGO Concorde"}, AlertFixture())


def test_ntfy_json_payload_accepts_unicode() -> None:
    listing = SimpleNamespace(
        id=12,
        title="Édition spéciale 🎮",
        price=42.5,
        currency="EUR",
        url="https://www.vinted.fr/items/12",
    )
    payload = notification_payload(listing, "DEAL")
    assert payload["title"] == "🔥 Édition spéciale 🎮"
    assert payload["topic"]
    assert payload["click"] == "vintradar://item/12"
    assert payload["actions"][0]["url"] == listing.url


@pytest.mark.asyncio
async def test_ntfy_posts_json_to_root_without_unicode_headers() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["json"] = __import__("json").loads(request.content)
        return httpx.Response(200, request=request)

    listing = SimpleNamespace(
        id=12,
        title="Édition spéciale 🎮",
        price=42.5,
        currency="EUR",
        url="https://www.vinted.fr/items/12",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await notify(listing, "DEAL", client=client)
    assert captured["url"].rstrip("/") == "http://localhost:8080"
    assert "title" not in captured["headers"]
    assert captured["json"]["title"] == "🔥 Édition spéciale 🎮"


def test_paused_alert_is_never_due() -> None:
    alert = SimpleNamespace(paused=True, last_scan_at=None, scan_minutes=5)
    assert not alert_is_due(alert)


def test_alert_respects_its_scan_interval() -> None:
    now = datetime.now(timezone.utc)
    alert = SimpleNamespace(paused=False, last_scan_at=now - timedelta(minutes=4), scan_minutes=5)
    assert not alert_is_due(alert, now)
    alert.last_scan_at = now - timedelta(minutes=5)
    assert alert_is_due(alert, now)
