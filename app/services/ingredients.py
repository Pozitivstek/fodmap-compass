"""Разбор состава упаковки: какие FODMAP-группы и аллергены, скорее всего, внутри."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# (группа, шаблон, сильный ли триггер). Сильный — продукт почти наверняка высокий FODMAP.
FODMAP_PATTERNS: tuple[tuple[str, str, bool], ...] = (
    ("fruc", r"\bлук(?!\s*зелен)|\bлуков|\bonion|\bчесно|\bgarlic|\bшалот|\bshallot", True),
    ("fruc", r"инулин|inulin|цикори|chicory|фруктоолигосахарид|олигофруктоз|oligofructose|\bfos\b", True),
    ("fruc", r"пшени|\bwheat|\bрж[аи]|ржан|\brye\b|ячмен|\bbarley|солод|\bmalt\b|спельт", False),
    ("fruc", r"топинамбур|артишок|artichoke", True),
    ("gos", r"фасол|\bbeans?\b|\bнут\b|нута\b|chickpea|чечевиц|lentil|\bгорох(?!ов\w* белок)|кешью|cashew|фисташ|pistachio", True),
    ("gos", r"соев\w* мук|soy flour|соевых бобов", False),
    ("lac", r"молок|\bmilk\b|сливк|\bcream\b|сыворот|\bwhey\b|лактоз|lactose|сгущ|творог|кефир|йогурт|yogh?urt|пахт|buttermilk", False),
    ("lac", r"сухое молоко|сухого молока|milk powder|сухая молочная|молочная сыворотка", True),
    ("fru", r"\bмед\b|\bмеда\b|медов|honey|фруктоз|fructose|агав|agave|глюкозно-фруктозн|high fructose|кукурузный сироп", True),
    ("fru", r"яблок|\bapple|груш|\bpear|манго|mango|\bинжир|\bfig", False),
    ("sor", r"сорбит|sorbitol|e ?420|ксилит|xylitol|e ?967|мальтит|maltitol|e ?965|изомальт|isomalt|e ?953|лактит|lactitol|e ?966", True),
    ("sor", r"чернослив|prune|кураг|абрикос|слив[аы]|\bplum|вишн|cherr|авокадо|avocado", False),
    ("man", r"маннит|mannitol|e ?421", True),
    ("man", r"гриб|шампиньон|mushroom|цветн\w* капуст|cauliflower", False),
)

NEGATIONS: tuple[tuple[str, str], ...] = (
    ("lac", r"без\s*лактоз\w*|безлактозн\w*|lactose[- ]free|sans lactose|кокосов\w* молок\w*|миндальн\w* молок\w*|"
            r"овсян\w* молок\w*|соев\w* молок\w*|рисов\w* молок\w*|coconut milk|almond milk|какао[- ]?масл\w*|cocoa butter"),
    ("fruc", r"масло,? настоянн\w* на чеснок\w*|чесночн\w* масл\w*|garlic[- ]infused oil|зелен\w* лук\w*"),
    ("fru", r"без\s*сахара|sugar[- ]free"),
)

ALLERGEN_PATTERNS: dict[str, str] = {
    "gluten": r"пшени|\bwheat|\bрж[аи]|ржан|\brye\b|ячмен|barley|овс|\boat|спельт|spelt|глютен|gluten|солод|\bmalt\b|манн\w* круп",
    "milk": r"молок|\bmilk\b|сливк|\bcream\b|сыворот|\bwhey\b|казеин|casein|лактоз|lactose|сыр\b|сыра\b|cheese|масло сливочн|\bbutter\b",
    "egg": r"яйц|яичн|\begg|меланж|альбумин",
    "peanut": r"арахис|peanut",
    "nuts": r"орех|фундук|миндал|кешью|фисташ|пекан|макадам|hazelnut|almond|cashew|pistachio|walnut|pecan|\bnuts?\b",
    "fish": r"\bрыб|\bfish|анчоус|anchov|тунец|лосос|треск",
    "shellfish": r"кревет|shrimp|prawn|краб|crab|кальмар|squid|мидии|mussel|омар|lobster|устриц|oyster",
    "soy": r"\bсо[яи]\b|соев|\bsoy|soja|лецитин соев",
    "sesame": r"кунжут|sesame|тахин",
    "mustard": r"горчиц|mustard",
    "celery": r"сельдер|celery",
    "sulfites": r"сульфит|sulphite|sulfite|e ?22[0-8]\b|диоксид серы|sulphur dioxide",
}

OFF_ALLERGENS = {
    "en:gluten": "gluten", "en:milk": "milk", "en:eggs": "egg", "en:peanuts": "peanut", "en:nuts": "nuts",
    "en:fish": "fish", "en:crustaceans": "shellfish", "en:molluscs": "shellfish", "en:soybeans": "soy",
    "en:sesame-seeds": "sesame", "en:mustard": "mustard", "en:celery": "celery",
    "en:sulphur-dioxide-and-sulphites": "sulfites",
}

TAG_PATTERNS: dict[str, str] = {
    "meat": r"говяд|свин|кури|индейк|баран|\bмяс|колбас|ветчин|бекон|\bbeef|\bpork|chicken|turkey|\bmeat|bacon|ham\b",
    "fish": r"\bрыб|лосос|тунец|треск|\bfish|salmon|tuna",
    "seafood": r"кревет|краб|кальмар|мидии|shrimp|crab|squid",
    "dairy": r"молок|сливк|сыр\b|сыра\b|творог|сыворот|\bmilk\b|cheese|\bcream\b|whey",
    "egg": r"яйц|яичн|\begg",
    "honey": r"\bм[её]д\b|honey",
}

MAJOR_INGREDIENT_COUNT = 3
LACTOSE_FREE = r"без\s*лактоз|безлактоз|lactose[- ]free|sans lactose"


@dataclass(frozen=True)
class Analysis:
    groups: dict[str, str] = field(default_factory=dict)  # группа → "high" | "possible"
    matches: tuple[str, ...] = ()
    allergens: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    lactose_free: bool = False

    @property
    def strong(self) -> bool:
        return "high" in self.groups.values()


def _clean(text: str) -> str:
    lowered = text.lower().replace("ё", "е").replace("_", " ")
    return re.sub(r"\s+", " ", lowered)


def _strip_negations(text: str) -> dict[str, str]:
    return {group: re.sub(pattern, " ", text) for group, pattern in NEGATIONS}


def _major_part(text: str) -> str:
    return ",".join(text.split(",")[:MAJOR_INGREDIENT_COUNT])


def analyze(text: str, off_allergens: list[str] | None = None, name: str = "") -> Analysis:
    full = _clean(f"{name}, {text}" if name else text)
    if not full.strip(" ,"):
        return Analysis()
    per_group = _strip_negations(full)
    groups: dict[str, str] = {}
    matches: list[str] = []
    for group, pattern, strong in FODMAP_PATTERNS:
        source = per_group.get(group, full)
        found = re.search(pattern, source)
        if not found:
            continue
        matches.append(found.group(0).strip())
        is_major = re.search(pattern, _major_part(source)) is not None
        level = "high" if strong or (is_major and group == "fruc") else "possible"
        if groups.get(group) != "high":
            groups[group] = level
    allergens = {code for code, pattern in ALLERGEN_PATTERNS.items() if re.search(pattern, full)}
    allergens |= {OFF_ALLERGENS[tag] for tag in (off_allergens or []) if tag in OFF_ALLERGENS}
    lactose_free = bool(re.search(LACTOSE_FREE, full))
    if lactose_free:
        groups.pop("lac", None)
    tags = tuple(sorted(tag for tag, pattern in TAG_PATTERNS.items() if re.search(pattern, full)))
    return Analysis(groups=groups, matches=tuple(dict.fromkeys(matches)), allergens=tuple(sorted(allergens)),
                    tags=tags, lactose_free=lactose_free)
