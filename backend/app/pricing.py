from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class Comparable:
    id: int
    external_id: str
    product_key: str
    brand: str | None
    category_key: str | None
    condition_segment: str | None
    total_price: float
    title: str
    seller_id: str | None
    status: str
    first_seen_at: datetime
    flags: frozenset[str] = frozenset()
    image_url: str | None = None
    url: str = ""


@dataclass(frozen=True)
class Score:
    label: str
    percentile: float
    median: float
    p20: float
    p75: float
    count: int
    confidence: str
    comparable_ids: tuple[int, ...]
    fallback_level: int
    fallback_label: str
    before_count: int
    excluded: dict[str, int]


EXCLUDED_FLAGS = {"LOT", "PARTS", "BROKEN", "EMPTY_BOX", "MANUAL_ONLY"}
USED_CONDITIONS = {"VERY_GOOD", "GOOD", "SATISFACTORY"}
NEW_CONDITIONS = {"NEW_WITH_TAGS", "NEW_WITHOUT_TAGS"}


def percentile_value(values: list[float], quantile: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def _near_duplicate_key(item: Comparable) -> tuple[str, str]:
    words = "".join(character.lower() if character.isalnum() else " " for character in item.title)
    normalized = " ".join(words.split())
    return (item.seller_id or f"unknown:{item.external_id}", normalized[:180])


def _status_weight(status: str) -> float:
    if status == "SOLD_CONFIRMED":
        return 3.0
    if status in {"DISAPPEARED", "UNKNOWN"}:
        return 0.35
    if status == "DELETED":
        return 0.2
    return 1.0


def _weighted_prices(items: Iterable[Comparable]) -> list[float]:
    values: list[float] = []
    for item in items:
        repetitions = max(1, round(_status_weight(item.status) * 4))
        values.extend([item.total_price] * repetitions)
    return sorted(values)


def score_listing(
    target: Comparable,
    candidates: Iterable[Comparable],
    *,
    now: datetime | None = None,
    minimum: int = 5,
) -> Score | None:
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(days=90)
    excluded = {"self": 0, "window": 0, "flags": 0, "duplicate": 0, "outlier": 0}
    base: list[Comparable] = []
    for candidate in candidates:
        if candidate.id == target.id:
            excluded["self"] += 1
            continue
        observed = candidate.first_seen_at
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        if observed < cutoff:
            excluded["window"] += 1
            continue
        if candidate.flags & EXCLUDED_FLAGS:
            excluded["flags"] += 1
            continue
        if candidate.total_price <= 0:
            excluded["flags"] += 1
            continue
        base.append(candidate)
    before_count = len(base)

    levels = [
        (
            1,
            "même produit et même état",
            [x for x in base if x.product_key == target.product_key and x.condition_segment == target.condition_segment],
        )
    ]
    if target.condition_segment in USED_CONDITIONS:
        levels.append((
            2,
            "même produit, états d’occasion voisins",
            [x for x in base if x.product_key == target.product_key and x.condition_segment in USED_CONDITIONS],
        ))
    elif target.condition_segment in NEW_CONDITIONS:
        levels.append((
            2,
            "même produit, états neufs voisins",
            [x for x in base if x.product_key == target.product_key and x.condition_segment in NEW_CONDITIONS],
        ))
    levels.append((
        3,
        f"même marque et catégorie ({target.brand or 'marque inconnue'} {target.category_key or ''})",
        [
            x for x in base
            if target.brand and target.category_key
            and x.brand == target.brand and x.category_key == target.category_key
            and (
                (target.condition_segment in NEW_CONDITIONS and x.condition_segment in NEW_CONDITIONS)
                or (target.condition_segment in USED_CONDITIONS and x.condition_segment in USED_CONDITIONS)
                or x.condition_segment == target.condition_segment
            )
        ],
    ))
    selected: list[Comparable] = []
    fallback_level = 0
    fallback_label = ""
    for level, label, items in levels:
        deduplicated: dict[tuple[str, str], Comparable] = {}
        for item in items:
            key = _near_duplicate_key(item)
            previous = deduplicated.get(key)
            if previous is None or _status_weight(item.status) > _status_weight(previous.status):
                deduplicated[key] = item
        excluded["duplicate"] += len(items) - len(deduplicated)
        if len(deduplicated) >= minimum:
            selected = list(deduplicated.values())
            fallback_level, fallback_label = level, label
            break
    if not selected:
        return None

    raw = sorted(x.total_price for x in selected)
    q1, q3 = percentile_value(raw, .25), percentile_value(raw, .75)
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    clean_items = [x for x in selected if lower <= x.total_price <= upper]
    excluded["outlier"] = len(selected) - len(clean_items)
    if len(clean_items) < minimum:
        return None
    values = _weighted_prices(clean_items)
    percentile = sum(value <= target.total_price for value in values) / len(values)
    label = "DEAL" if percentile <= .20 else "GOOD" if percentile < .50 else "NORMAL" if percentile <= .75 else "EXPENSIVE"
    confidence = "HIGH" if len(clean_items) >= 30 else "MEDIUM" if len(clean_items) >= 10 else "LOW"
    if fallback_level == 3:
        confidence = "LOW"
    return Score(
        label=label,
        percentile=percentile,
        median=median(values),
        p20=percentile_value(values, .20),
        p75=percentile_value(values, .75),
        count=len(clean_items),
        confidence=confidence,
        comparable_ids=tuple(item.id for item in clean_items),
        fallback_level=fallback_level,
        fallback_label=fallback_label,
        before_count=before_count,
        excluded=excluded,
    )


def explanation(
    target: Comparable,
    score: Score | None,
    *,
    price: float,
    buyer_fee: float,
    shipping: float,
    recognition: dict,
    external_references: list[dict] | None = None,
) -> dict:
    if score is None:
        return {
            "evaluated": False,
            "reason": "moins de 5 annonces comparables admissibles sur 90 jours",
            "price": {"item": price, "buyer_fee": buyer_fee, "shipping": shipping, "total": target.total_price},
            "product": recognition,
            "condition_segment": target.condition_segment,
            "window_days": 90,
            "external_references": external_references or [],
        }
    payload = asdict(score)
    payload.update({
        "evaluated": True,
        "price": {"item": price, "buyer_fee": buyer_fee, "shipping": shipping, "total": target.total_price},
        "product": recognition,
        "condition_segment": target.condition_segment,
        "window_days": 90,
        "external_references": external_references or [],
    })
    reasons: list[str] = []
    if score.count < 10:
        reasons.append("moins de 10 comparables après exclusions")
    if score.fallback_level == 3:
        reasons.append("comparaison à la même marque et catégorie, pas au même modèle")
    if score.confidence == "LOW" and not reasons:
        reasons.append("une référence externe diverge fortement de la médiane Vinted")
    payload["low_confidence_reasons"] = reasons
    return payload


def robust_score(price: float, values: list[float]) -> Score | None:
    """Compatibility helper; production scoring uses score_listing with identities and segments."""
    now = datetime.now(timezone.utc)
    target = Comparable(0, "target", "compat", None, None, "GOOD", price, "", None, "ACTIVE", now)
    candidates = [
        Comparable(index + 1, str(index), "compat", None, None, "GOOD", value, str(index), None, "ACTIVE", now)
        for index, value in enumerate(values)
    ]
    return score_listing(target, candidates, now=now, minimum=3)
