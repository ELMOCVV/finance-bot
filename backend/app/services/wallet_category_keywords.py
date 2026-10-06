"""Словник автокатегоризації для витрат з Apple Wallet.

Як дописувати:
  * "categories" — можливі назви категорії користувача (перша знайдена серед
    його витратних категорій буде використана, регістр не важливий);
  * "keywords" — підрядки, які шукаються в назві продавця (регістр не важливий).

Правила перевіряються згори вниз — перше збігання виграє, тож більш
специфічні правила ставте вище. Якщо нічого не підійшло — витрата
потрапляє в «Інше» (або без категорії, якщо такої немає).
"""

CATEGORY_RULES: list[dict] = [
    {
        "categories": ["Здоров'я", "Аптека", "Аптеки", "Здоровье"],
        "keywords": [
            "аптека", "apteka", "pharm", "подорожник", "podorozhnyk", "аптека анц",
            "бажаємо здоров", "медікус", "діла", "синево", "synevo",
        ],
    },
    {
        "categories": ["Кафе", "Кафе та ресторани", "Ресторани", "Їжа"],
        "keywords": [
            "кафе", "cafe", "coffee", "кава", "кофе", "ресторан", "restaurant",
            "mcdonald", "макдональдс", "kfc", "пузата хата", "puzata", "aroma kava",
            "starbucks", "lviv croissants", "домінос", "dominos", "pizza", "піца",
            "сушія", "sushi", "bolt food", "glovo", "wolt",
        ],
    },
    {
        "categories": ["Їжа", "Продукти", "Продукты", "Еда"],
        "keywords": [
            "атб", "atb", "сільпо", "silpo", "novus", "новус", "metro cash", "метро кеш",
            "ашан", "auchan", "фора", "fora", "варус", "varus", "eko market",
            "еко маркет", "велмарт", "velmart", "fozzy", "фоззі", "наш край",
            "rukavychka", "рукавичка", "spar", "lidl", "biedronka", "billa",
            "kaufland", "carrefour", "rewe", "aldi", "tesco",
        ],
    },
    {
        "categories": ["Транспорт", "Таксі", "Авто"],
        "keywords": [
            "uber", "uklon", "уклон", "bolt", "таксі", "taxi", "метрополітен", "metro kyiv",
            "укрзалізниця", "ukrzaliznytsia", "uz.gov", "wog", "окко", "okko", "socar",
            "upg", "shell", "parking", "паркінг", "flixbus", "ryanair", "wizz",
        ],
    },
    {
        "categories": ["Комунальні", "Зв'язок", "Комуналка"],
        "keywords": [
            "київстар", "kyivstar", "vodafone", "lifecell", "лайфселл", "yasno", "ясно",
            "нафтогаз", "naftogaz", "водоканал", "тенет", "volia", "воля",
        ],
    },
    {
        "categories": ["Одяг", "Одежда"],
        "keywords": [
            "zara", "h&m", "reserved", "bershka", "pull&bear", "lc waikiki", "colin's",
            "sinsay", "uniqlo", "nike", "adidas", "intertop", "answear",
        ],
    },
    {
        "categories": ["Розваги", "Підписки"],
        "keywords": [
            "netflix", "spotify", "youtube", "apple.com", "itunes", "steam", "playstation",
            "кінотеатр", "multiplex", "мультиплекс", "planeta kino", "планета кіно",
        ],
    },
]

# Категорія за замовчуванням, якщо жодне правило не спрацювало
# (стандартна витратна категорія, яку бот створює кожному користувачу).
FALLBACK_CATEGORY_NAMES: list[str] = ["Інше", "Без категорії", "Другое", "Прочее"]
