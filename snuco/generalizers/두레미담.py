import re
from typing import Any


SECTION_RE = re.compile(r"^<(?P<section>[^>]+)>\s*(?P<body>.*)$")
PRICE_ONLY_RE = re.compile(r"^(?P<price>[\d,]+)\s*원")
PRICE_RE = re.compile(r"^(?P<name>.+?)\s*:\s*(?P<price>[\d,]+)\s*원")
SPLIT_RE = re.compile(r"\s*[,&*]\s*")


def section_key(section: str) -> str:
    return re.sub(r"\s+", "", section.strip())


def parse_price_only(text: str) -> int | None:
    match = PRICE_ONLY_RE.match(text.strip())
    if match is None:
        return None
    return int(match.group("price").replace(",", ""))


def normalize_names(name_text: str) -> list[str]:
    name_text = name_text.replace("(#)", "").replace("[#]", "").strip()
    return [name for part in SPLIT_RE.split(name_text) if (name := part.strip())]


def parse_lines(lines: list[str]) -> dict[str, list[dict[str, Any]]]:
    meals_by_restaurant: dict[str, list[dict[str, Any]]] = {}
    buffet_price: int | None = None
    buffet_items: list[str] = []
    current_restaurant: str | None = None

    def flush_buffet() -> None:
        nonlocal buffet_price, buffet_items
        if buffet_items:
            meals_by_restaurant.setdefault("두레미담 셀프코너", []).append({
                "price": buffet_price,
                "noMeat": False,
                "menus": buffet_items,
            })
        buffet_price = None
        buffet_items = []

    for line in lines:
        if line.startswith("※"):
            continue

        section_match = SECTION_RE.match(line)
        if section_match is not None:
            flush_buffet()
            key = section_key(section_match.group("section"))
            body = section_match.group("body").strip()
            if key == "셀프코너":
                current_restaurant = "두레미담 셀프코너"
                buffet_price = parse_price_only(body)
            elif key == "주문식메뉴":
                current_restaurant = "두레미담 식당"
            else:
                current_restaurant = None
            continue

        price_match = PRICE_RE.match(line)
        if price_match is not None:
            flush_buffet()
            names = normalize_names(price_match.group("name"))
            if names:
                meals_by_restaurant.setdefault(current_restaurant or "두레미담 식당", []).append({
                    "price": int(price_match.group("price").replace(",", "")),
                    "noMeat": False,
                    "menus": names,
                })
            continue

        if buffet_price is not None:
            buffet_items.extend(normalize_names(line))

    flush_buffet()
    return meals_by_restaurant


def generalize_cafeteria(meal_cells: list[tuple[str, list[str]]]) -> list[dict[str, Any]]:
    payloads = []
    for meal_type, lines in meal_cells:
        meals_by_restaurant = parse_lines(lines)
        for restaurant, meals in meals_by_restaurant.items():
            if meals:
                payloads.append({"restaurant": restaurant, "type": meal_type, "meals": meals})
    return payloads
