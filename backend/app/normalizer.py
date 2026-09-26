import re
import unicodedata
from dataclasses import dataclass


def fold(value: str) -> str:
    return "".join(
        character for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    ).lower()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(value)).strip("-")


@dataclass(frozen=True)
class Normalized:
    key: str | None
    brand: str | None
    model: str | None
    category_key: str | None
    flags: frozenset[str]
    confidence: float
    recognized_text: str | None
    attributes: dict


EXCLUSION_PATTERNS = {
    "LOT": r"\b(?:lot|bundle)\b",
    "PARTS": r"\b(?:pieces? detachees?|pour pieces?|spares?)\b",
    "BROKEN": r"\b(?:hs|hors service|ne fonctionne pas|casse[ée]?)\b",
    "EMPTY_BOX": r"\b(?:boite|box)\s+(?:vide|seule)\b",
    "MANUAL_ONLY": r"\b(?:notice|manuel)\s+(?:seul(?:e)?|uniquement)\b",
}


def flags_for(text: str) -> frozenset[str]:
    plain = fold(text)
    flags = {name for name, pattern in EXCLUSION_PATTERNS.items() if re.search(pattern, plain)}
    if re.search(r"\b(?:neuf|new)\b.*\b(?:etiquette|scelle|sealed)\b", plain):
        flags.add("SEALED")
    if re.search(r"\b(?:sans boite|loose|cartouche seule|jeu seul)\b", plain):
        flags.add("LOOSE")
    if re.search(r"\b(?:code non utilise|unused code)\b", plain):
        flags.add("UNUSED_CODE")
    return frozenset(flags)


def condition_segment(condition: str | None) -> str | None:
    value = fold(condition or "")
    if not value:
        return None
    if any(label in value for label in ("neuf sans etiquette", "new without tags", "new without tag")):
        return "NEW_WITHOUT_TAGS"
    if ("neuf" in value and ("avec etiquette" in value or "scelle" in value)) or any(
        label in value for label in ("new with tags", "new with tag", "new sealed")
    ):
        return "NEW_WITH_TAGS"
    if "neuf" in value or "comme neuf" in value or value == "new":
        return "NEW_WITHOUT_TAGS"
    if "tres bon" in value or "excellent etat" in value or "very good" in value:
        return "VERY_GOOD"
    if "bon etat" in value or value == "bon" or value == "good" or "good condition" in value:
        return "GOOD"
    if "satisfaisant" in value or "satisfactory" in value or "etat correct" in value or value == "use":
        return "SATISFACTORY"
    return None


def _lego_number(text: str) -> tuple[str, str] | None:
    plain = fold(text)
    pattern = re.compile(r"\b(lego|set|ref(?:erence)?|n(?:o|umero)?)[^0-9]{0,30}(\d{4,6})\b")
    for match in pattern.finditer(plain):
        context, number = match.group(1), match.group(2)
        if 1990 <= int(number) <= 2030 and context == "lego":
            continue
        suffix = plain[match.end():match.end() + 16]
        if re.match(r"\s*(?:pieces?|pcs)\b", suffix):
            continue
        return number, text[max(0, match.start() - 10):match.end() + 10].strip()
    return None


def _platform(text: str) -> str | None:
    plain = fold(text)
    if re.search(r"\b(?:nintendo\s*)?switch\s*2\b", plain):
        return "switch2"
    if re.search(r"\b(?:nintendo\s*)?switch\b", plain):
        return "switch"
    if re.search(r"\bps\s*5\b|\bplaystation\s*5\b", plain):
        return "ps5"
    if re.search(r"\bxbox\s+(?:series\s+)?[xs]\b", plain):
        return "xbox-series"
    return None


def _game_title(text: str, platform: str) -> str:
    plain = fold(text)
    plain = re.sub(r"\b(?:nintendo|switch\s*2|switch|ps\s*5|playstation\s*5|xbox(?:\s+series)?\s*[xs])\b", " ", plain)
    plain = re.sub(r"\b(?:jeu|game|edition|standard|collector|neuf|scelle|cartouche|boite)\b", " ", plain)
    # Z-A, ZA and Z A intentionally collapse to the same token.
    plain = re.sub(r"\bz\s*[- ]?\s*a\b", "za", plain)
    tokens = [token for token in re.findall(r"[a-z0-9]+", plain) if len(token) > 1 or token.isdigit()]
    return "-".join(tokens[:10])


def _edition(text: str) -> str:
    plain = fold(text)
    if "collector" in plain:
        return "collector"
    if re.search(r"switch\s*2\s+edition|edition\s+switch\s*2", plain):
        return "switch2-edition"
    return "standard"


ACCESSORY_TYPES = (
    ("steering-wheel", r"\b(?:volant|racing wheel)\b"),
    ("controller", r"\b(?:manette|controller|gamepad)\b"),
    ("joy-con", r"\b(?:joy[ -]?con)\b"),
    ("dock", r"\b(?:dock|station d accueil)\b"),
    ("case", r"\b(?:housse|etui|case)\b"),
    ("screen-protector", r"\b(?:protection d ecran|verre trempe)\b"),
    ("charger", r"\b(?:chargeur|charger)\b"),
    ("cable", r"\b(?:cable|cordon)\b"),
    ("grip", r"\b(?:grip|poignee)\b"),
    ("stand", r"\b(?:support|stand)\b"),
    ("memory-card", r"\b(?:carte memoire|micro ?sd|memory card)\b"),
)


def _accessory(
    text: str,
    platform: str | None,
    category: str,
    flags: frozenset[str],
) -> Normalized | None:
    plain = fold(text)
    category_plain = fold(category)
    if "console" in category_plain or re.search(r"\bconsole\b", plain):
        return None
    accessory_type = next((name for name, pattern in ACCESSORY_TYPES if re.search(pattern, plain)), None)
    category_is_accessory = any(word in category_plain for word in ("accessoire", "peripherique", "gaming"))
    if not accessory_type or (not platform and not category_is_accessory):
        return None
    platform_key = platform or "unknown"
    confidence = .95 if platform else .7
    return Normalized(
        f"accessory:{platform_key}:{accessory_type}", None, accessory_type, "accessory",
        flags, confidence, text[:200],
        {"platform": platform_key, "accessory_type": accessory_type, "product_type": "accessory"},
    )


def _console(text: str, platform: str, category: str, flags: frozenset[str]) -> Normalized | None:
    plain = fold(text)
    category_plain = fold(category)
    console_words = r"\b(?:console|pack|bundle|edition|go|gb|to|tb)\b"
    game_words = r"\b(?:jeu|game|cartouche)\b"
    category_is_console = any(word in category_plain for word in ("console", "systeme de jeu"))
    without_platform = re.sub(
        r"\b(?:nintendo|switch\s*2|switch|ps\s*5|playstation\s*5|xbox(?:\s+series)?\s*[xs])\b",
        " ", plain,
    )
    without_platform = re.sub(
        r"\b(?:neuf|neuve|nouveau|nouvelle|avec|sans|etiquette|scellee?|occasion|tres|bon|etat)\b|\d+\s*(?:go|gb|to|tb)",
        " ", without_platform,
    )
    platform_only = not re.findall(r"[a-z0-9]+", without_platform)
    if not (category_is_console or platform_only or re.search(console_words, plain)):
        return None
    if re.search(game_words, plain) and not (category_is_console or "console" in plain):
        return None
    capacity_match = re.search(r"\b(\d+)\s*(go|gb|to|tb)\b", plain)
    capacity = "".join(capacity_match.groups()) if capacity_match else None
    pack = "pack" if re.search(r"\b(?:pack|bundle|avec jeu)\b", plain) else "console"
    model = "-".join(filter(None, [platform, capacity, pack]))
    return Normalized(
        f"console:{model}", None, model, "console", flags, 0.95,
        text[:200], {"platform": platform, "capacity": capacity, "pack": pack, "product_type": "console"},
    )


def _generic(title: str, brand: str | None, category: str | None, size: str | None, flags: frozenset[str]) -> Normalized:
    ignored = {"neuf", "bon", "etat", "tres", "avec", "sans", "pour", "taille", "article", "vinted"}
    brand_slug = slug(brand or "inconnue")
    category_slug = slug(category or "categorie-inconnue")
    tokens = [token for token in slug(title).split("-") if token and token not in ignored and not token.isdigit()]
    model_tokens = "-".join(tokens[:6]) or "modele-inconnu"
    relevant_size = slug(size or "") if category and any(x in fold(category) for x in ("vetement", "chauss", "mode")) else ""
    key = ":".join(filter(None, ["generic", brand_slug, category_slug, model_tokens, relevant_size]))
    confidence = 0.7 if brand and category and model_tokens != "modele-inconnu" else 0.2
    return Normalized(
        key, brand, model_tokens, category_slug, flags, confidence, title[:200],
        {"size": size, "product_type": "other", "category_confident": bool(category)},
    )


def normalize(
    title: str,
    description: str = "",
    *,
    brand: str | None = None,
    category: str | None = None,
    size: str | None = None,
    lego_validated: bool | None = None,
) -> Normalized:
    text = f"{title} {description}".strip()
    flags = flags_for(text)
    lego = _lego_number(text)
    if lego:
        number, evidence = lego
        confidence = 1.0 if lego_validated else 0.72 if lego_validated is None else 0.25
        if lego_validated is False:
            return _generic(title, brand or "LEGO", category, size, flags)
        return Normalized(
            f"lego:{number}", "LEGO", number, "lego", flags, confidence, evidence,
            {"set_number": number, "validated": lego_validated},
        )

    platform = _platform(text)
    category_plain = fold(category or "")
    accessory = _accessory(text, platform, category or "", flags)
    if accessory:
        return accessory
    if platform:
        console = _console(text, platform, category or "", flags)
        if console:
            return console
        looks_like_game = (
            any(word in category_plain for word in ("jeu", "game"))
            or re.search(r"\b(?:jeu|game|cartouche|pokemon|mario|zelda)\b", fold(text))
        )
        if looks_like_game:
            game = _game_title(title, platform)
            if not game or game == "jeu":
                game = _game_title(description, platform)
            if game:
                edition = _edition(text)
                return Normalized(
                    f"game:{platform}:{game}:{edition}", brand, game, "game", flags, 0.9,
                    title[:200], {"platform": platform, "edition": edition, "product_type": "game"},
                )

    return _generic(title, brand, category, size, flags)
