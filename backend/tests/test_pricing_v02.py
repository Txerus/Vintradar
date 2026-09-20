from datetime import datetime, timedelta, timezone

from app.normalizer import condition_segment, normalize
from app.pricing import Comparable, score_listing
from app.worker import allowed, score_reaches_threshold


NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)


def comparable(
    identifier: int,
    price: float,
    *,
    product: str = "lego:42035",
    condition: str = "VERY_GOOD",
    brand: str = "LEGO",
    category: str = "lego",
    seller: str | None = None,
    title: str | None = None,
    age: int = 1,
    status: str = "ACTIVE",
    flags=frozenset(),
) -> Comparable:
    return Comparable(
        identifier, str(identifier), product, brand, category, condition, price,
        title or f"LEGO 42035 #{identifier}", seller or f"seller-{identifier}", status,
        NOW - timedelta(days=age), flags,
    )


def test_same_product_same_condition_self_by_id_and_iqr() -> None:
    target = comparable(1, 25)
    values = [
        target,
        comparable(2, 25),  # Same value must remain; identity, not value, excludes self.
        comparable(3, 30), comparable(4, 35), comparable(5, 40), comparable(6, 45),
        comparable(7, 5000),  # IQR outlier.
        comparable(8, 1, product="lego:99999"),
        comparable(9, 1, condition="NEW_WITH_TAGS"),
        comparable(10, 1, age=91),
    ]
    score = score_listing(target, values, now=NOW)
    assert score is not None
    assert score.fallback_level == 1
    assert 2 in score.comparable_ids
    assert 1 not in score.comparable_ids
    assert 7 not in score.comparable_ids
    assert score.excluded["self"] == 1
    assert score.excluded["window"] == 1
    assert score.excluded["outlier"] == 1


def test_hierarchical_used_fallback_never_mixes_new_and_used() -> None:
    target = comparable(1, 25, condition="VERY_GOOD")
    values = [
        target,
        comparable(2, 20, condition="VERY_GOOD"),
        comparable(3, 30, condition="GOOD"),
        comparable(4, 35, condition="GOOD"),
        comparable(5, 40, condition="SATISFACTORY"),
        comparable(6, 45, condition="VERY_GOOD"),
        comparable(7, 2, condition="NEW_WITH_TAGS"),
    ]
    score = score_listing(target, values, now=NOW)
    assert score is not None
    assert score.fallback_level == 2
    assert score.fallback_label == "même produit, états d’occasion voisins"
    assert 7 not in score.comparable_ids


def test_brand_category_fallback_caps_confidence_and_deduplicates_reposts() -> None:
    target = comparable(1, 25)
    values = [target]
    for identifier in range(2, 8):
        values.append(comparable(
            identifier, 20 + identifier, product=f"lego:{10000 + identifier}",
            seller="same" if identifier in (2, 3) else None,
            title="Même republication" if identifier in (2, 3) else None,
        ))
    score = score_listing(target, values, now=NOW)
    assert score is not None
    assert score.fallback_level == 3
    assert score.confidence == "LOW"
    assert score.excluded["duplicate"] >= 1


def test_lego_number_heuristics_and_description() -> None:
    assert not normalize("LEGO de 2019").key.startswith("lego:")
    assert not normalize("LEGO 1000 pièces").key.startswith("lego:")
    assert not normalize("Prix 42035 euros").key.startswith("lego:")
    assert normalize("LEGO 42035").key == "lego:42035"
    assert normalize("set n°10318").key == "lego:10318"
    assert normalize("Joli jouet", "Réf 42035, complet").key == "lego:42035"
    assert normalize("LEGO Technic 42035", lego_validated=True).confidence == 1
    assert normalize("LEGO Technic 42035").confidence < 1


def test_video_game_variants_are_equal_and_console_is_distinct() -> None:
    first = normalize("Pokémon Légendes Z-A Switch 2", category="Jeux vidéo")
    second = normalize("pokemon legendes ZA nintendo switch 2", category="Jeux vidéo")
    console = normalize("Console Nintendo Switch 2 256 Go avec manette", category="Consoles")
    assert first.key == second.key == "game:switch2:pokemon-legendes-za:standard"
    assert console.key.startswith("console:")
    assert console.key != first.key


def test_condition_segments_and_whole_word_accent_insensitive_filters() -> None:
    class Alert:
        include_terms = ["LÉGO"]
        exclude_terms = ["boîte vide"]

    assert condition_segment("Neuf avec étiquette") == "NEW_WITH_TAGS"
    assert condition_segment("Très bon état") == "VERY_GOOD"
    assert allowed({"title": "Beau lego complet"}, Alert())
    assert not allowed({"title": "Arc de Legolas"}, Alert())
    assert not allowed({"title": "LEGO", "description": "Boite vide"}, Alert())


def test_all_threshold_accepts_unscored_only_deal_rejects_it() -> None:
    assert score_reaches_threshold(None, "ALL")
    assert not score_reaches_threshold(None, "DEAL")
    assert not score_reaches_threshold(None, "GOOD")
    assert not score_reaches_threshold(None, "NORMAL")
