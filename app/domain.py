"""Справочники предметной области: FODMAP-группы, аллергены, состояния, симптомы."""

from __future__ import annotations

FODMAP_GROUPS: dict[str, dict[str, str]] = {
    "fruc": {"name": "Фруктаны", "short": "Фр", "desc": "Пшеница, рожь, лук, чеснок, некоторые овощи и орехи"},
    "gos": {"name": "ГОС", "short": "ГОС", "desc": "Бобовые, орехи кешью и фисташки, соевое молоко"},
    "lac": {"name": "Лактоза", "short": "Лак", "desc": "Молоко, мягкие сыры, йогурт, мороженое"},
    "fru": {"name": "Избыток фруктозы", "short": "Фру", "desc": "Мёд, яблоки, груши, манго, сироп агавы"},
    "sor": {"name": "Сорбит и полиолы", "short": "Сор", "desc": "Косточковые фрукты, авокадо, сахарозаменители Е420, Е967"},
    "man": {"name": "Маннит", "short": "Ман", "desc": "Грибы, цветная капуста, батат, сельдерей"},
}

ALLERGENS: dict[str, str] = {
    "gluten": "Глютен",
    "milk": "Молочный белок",
    "egg": "Яйца",
    "peanut": "Арахис",
    "nuts": "Орехи",
    "fish": "Рыба",
    "shellfish": "Морепродукты",
    "soy": "Соя",
    "sesame": "Кунжут",
    "mustard": "Горчица",
    "celery": "Сельдерей",
    "sulfites": "Сульфиты",
}

FOOD_TAGS = {"vegan", "meat", "fish", "seafood", "dairy", "egg", "honey", "lactose_free"}

CATEGORIES: dict[str, dict[str, str]] = {
    "veg": {"name": "Овощи", "emoji": "🥕"},
    "fruit": {"name": "Фрукты и ягоды", "emoji": "🍓"},
    "grain": {"name": "Крупы и хлеб", "emoji": "🌾"},
    "dairy": {"name": "Молочное", "emoji": "🧀"},
    "alt": {"name": "Растительные альтернативы", "emoji": "🌱"},
    "meat": {"name": "Мясо и птица", "emoji": "🍗"},
    "fish": {"name": "Рыба и морепродукты", "emoji": "🐟"},
    "egg": {"name": "Яйца", "emoji": "🥚"},
    "legume": {"name": "Бобовые", "emoji": "🫘"},
    "nut": {"name": "Орехи и семена", "emoji": "🌰"},
    "fat": {"name": "Масла и жиры", "emoji": "🫒"},
    "sweet": {"name": "Сладкое и снеки", "emoji": "🍫"},
    "drink": {"name": "Напитки", "emoji": "🥤"},
    "sauce": {"name": "Соусы и приправы", "emoji": "🥫"},
    "spice": {"name": "Специи и травы", "emoji": "🌿"},
    "dish": {"name": "Готовые блюда", "emoji": "🍲"},
    "product": {"name": "Товары из магазина", "emoji": "🛒"},
    "custom": {"name": "Мои продукты", "emoji": "⭐"},
}

# kind: "portion" — оценивается по граммам, "allergy" — продукт запрещён целиком.
CONDITIONS: dict[str, dict] = {
    "fodmap": {"name": "Low-FODMAP (СРК)", "emoji": "🌀", "kind": "portion",
               "groups": list(FODMAP_GROUPS), "desc": "Синдром раздражённого кишечника, вздутие"},
    "lactose": {"name": "Непереносимость лактозы", "emoji": "🥛", "kind": "portion",
                "groups": ["lac"], "desc": "Молочный сахар"},
    "fructose": {"name": "Фруктозная мальабсорбция", "emoji": "🍎", "kind": "portion",
                 "groups": ["fru", "sor"], "desc": "Фрукты, мёд, сиропы"},
    "polyols": {"name": "Непереносимость полиолов", "emoji": "🍬", "kind": "portion",
                "groups": ["sor", "man"], "desc": "Сорбит, маннит, ксилит"},
    "celiac": {"name": "Целиакия", "emoji": "🌾", "kind": "allergy",
               "allergens": ["gluten"], "desc": "Строго без глютена"},
    "gluten": {"name": "Чувствительность к глютену", "emoji": "🍞", "kind": "allergy",
               "allergens": ["gluten"], "desc": "Без пшеницы, ржи, ячменя"},
    "milk_allergy": {"name": "Аллергия на белок молока", "emoji": "🧀", "kind": "allergy",
                     "allergens": ["milk"], "desc": "Казеин и сывороточный белок"},
    "egg_allergy": {"name": "Аллергия на яйца", "emoji": "🥚", "kind": "allergy", "allergens": ["egg"], "desc": ""},
    "peanut_allergy": {"name": "Аллергия на арахис", "emoji": "🥜", "kind": "allergy",
                       "allergens": ["peanut"], "desc": ""},
    "nut_allergy": {"name": "Аллергия на орехи", "emoji": "🌰", "kind": "allergy", "allergens": ["nuts"], "desc": ""},
    "fish_allergy": {"name": "Аллергия на рыбу", "emoji": "🐟", "kind": "allergy", "allergens": ["fish"], "desc": ""},
    "shellfish_allergy": {"name": "Аллергия на морепродукты", "emoji": "🦐", "kind": "allergy",
                          "allergens": ["shellfish"], "desc": ""},
    "soy_allergy": {"name": "Аллергия на сою", "emoji": "🫛", "kind": "allergy", "allergens": ["soy"], "desc": ""},
    "sesame_allergy": {"name": "Аллергия на кунжут", "emoji": "⚪", "kind": "allergy",
                       "allergens": ["sesame"], "desc": ""},
    "mustard_allergy": {"name": "Аллергия на горчицу", "emoji": "🟡", "kind": "allergy",
                        "allergens": ["mustard"], "desc": ""},
    "celery_allergy": {"name": "Аллергия на сельдерей", "emoji": "🥬", "kind": "allergy",
                       "allergens": ["celery"], "desc": ""},
    "sulfite_allergy": {"name": "Непереносимость сульфитов", "emoji": "🍷", "kind": "allergy",
                        "allergens": ["sulfites"], "desc": "Вино, сухофрукты"},
}

DIET_STYLES: dict[str, dict] = {
    "omnivore": {"name": "Ем всё", "emoji": "🍽️", "exclude": []},
    "pescatarian": {"name": "Пескетарианство", "emoji": "🐟", "exclude": ["meat"]},
    "vegetarian": {"name": "Вегетарианство", "emoji": "🥗", "exclude": ["meat", "fish", "seafood"]},
    "vegan": {"name": "Веганство", "emoji": "🌱", "exclude": ["meat", "fish", "seafood", "dairy", "egg", "honey"]},
}

MEALS: dict[str, dict[str, str]] = {
    "breakfast": {"name": "Завтрак", "emoji": "🌅"},
    "lunch": {"name": "Обед", "emoji": "☀️"},
    "dinner": {"name": "Ужин", "emoji": "🌙"},
    "snack": {"name": "Перекус", "emoji": "🍎"},
}

SYMPTOMS: dict[str, dict[str, str]] = {
    "bloating": {"name": "Вздутие", "emoji": "🎈"},
    "gas": {"name": "Газы", "emoji": "💨"},
    "pain": {"name": "Боль в животе", "emoji": "😖"},
    "cramps": {"name": "Спазмы", "emoji": "⚡"},
    "diarrhea": {"name": "Диарея", "emoji": "🚽"},
    "constipation": {"name": "Запор", "emoji": "🧱"},
    "nausea": {"name": "Тошнота", "emoji": "🤢"},
    "heartburn": {"name": "Изжога", "emoji": "🔥"},
    "fatigue": {"name": "Усталость", "emoji": "😴"},
    "headache": {"name": "Головная боль", "emoji": "🤕"},
    "rash": {"name": "Сыпь или зуд", "emoji": "🔴"},
    "fog": {"name": "Туман в голове", "emoji": "🌫️"},
}

# Самочувствие после еды → насколько это плохой сигнал (0 — всё хорошо).
FEELINGS: dict[str, dict] = {
    "great": {"name": "Всё отлично", "emoji": "😊", "weight": 0},
    "ok": {"name": "Нормально", "emoji": "🙂", "weight": 0},
    "mild": {"name": "Дискомфорт", "emoji": "😕", "weight": 1},
    "bad": {"name": "Плохо", "emoji": "😣", "weight": 2},
}

ACTIVITY: dict[str, dict] = {
    "low": {"name": "Сидячий образ жизни", "factor": 1.2},
    "light": {"name": "Лёгкая активность 1–3 раза в неделю", "factor": 1.375},
    "medium": {"name": "Тренировки 3–5 раз в неделю", "factor": 1.55},
    "high": {"name": "Ежедневные тренировки", "factor": 1.725},
}

GOALS: dict[str, dict] = {
    "lose": {"name": "Снизить вес", "factor": 0.85},
    "keep": {"name": "Держать вес", "factor": 1.0},
    "gain": {"name": "Набрать вес", "factor": 1.12},
}

TIPS: tuple[str, ...] = (
    "Чеснок и лук отдают фруктаны в воду, но не в масло. Масло, настоянное на чесноке, — безопасная замена.",
    "Зелёная часть лука-порея и зелёный лук безопасны — используйте их вместо луковицы.",
    "Безопасные порции суммируются: овсянка + банан + мёд в одном завтраке могут дать «перебор».",
    "Чем спелее банан, тем больше в нём фруктанов. Берите слегка зеленоватые.",
    "Выдержанные сыры (пармезан, чеддер, гауда) почти не содержат лактозы.",
    "Консервированные нут и чечевица переносятся лучше варёных: ГОС уходят в жидкость. Промывайте их.",
    "Хлеб на долгой закваске часто переносится лучше обычного: брожение расщепляет фруктаны.",
    "Ешьте медленно и не пропускайте приёмы пищи: большие перерывы и переедание усиливают симптомы.",
    "Строгая фаза low-FODMAP длится 2–6 недель. Дальше продукты возвращают по одной группе.",
    "Сахарозаменители E420, E421, E953, E965, E966, E967 — полиолы. Ищите их в «сахарозаменителях» и жвачке.",
    "Кофе и алкоголь сами по себе не FODMAP, но могут раздражать кишечник.",
    "Пейте воду между приёмами пищи — это помогает при запорах и не разбавляет желудочный сок во время еды.",
    "Записывайте самочувствие через 2–3 часа после еды: так легче связать симптом с продуктом.",
    "Мята перечная (чай) может уменьшать спазмы.",
    "Клетчатку добавляйте постепенно: киви, овёс, семена чиа и льна — дружелюбные источники.",
    "Стресс влияет на кишечник не меньше еды. Отмечайте в заметках, если день был тяжёлым.",
)

TOLERANCE_STATUSES: dict[str, dict[str, str]] = {
    "ok": {"name": "Подходит мне", "emoji": "💚"},
    "caution": {"name": "Осторожно", "emoji": "💛"},
    "avoid": {"name": "Мне не подходит", "emoji": "❤️‍🩹"},
}
