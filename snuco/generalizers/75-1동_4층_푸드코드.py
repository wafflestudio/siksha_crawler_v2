import re
from typing import Any


PRICE_RE = re.compile(r"^(?P<name>.+?)\s*:?\s*(?P<price>[\d,]+)\s*원")
SPLIT_RE = re.compile(r"\s*[,&+*]\s*")
SECTION_RE = re.compile(r"^<(?P<section>[^>]+)>\s*(?P<body>.*)$")
SECTION_TO_RESTAURANT = {
    "서가앤쿡": "4층 푸드코드 서가앤쿡",
    "토끼정": "4층 푸드코드 토끼정",
    "숨쉬는순두부": "4층 푸드코드 숨쉬는순두부",
    "이공오 돈까스와 우동": "4층 푸드코드 이공오 돈까스와 우동",
    "이공오돈까스와우동": "4층 푸드코드 이공오 돈까스와 우동",
}


def section_key(section: str) -> str:
    return re.sub(r"\s+", "", section.strip())


def normalize_names(name_text: str) -> list[str]:
    name_text = name_text.replace("(#)", "").replace("[#]", "").strip()
    return [name for part in SPLIT_RE.split(name_text) if (name := part.strip())]


def parse_price_line(line: str) -> dict[str, Any] | None:
    match = PRICE_RE.match(line)
    if match is None:
        return None

    names = normalize_names(match.group("name"))
    if not names:
        return None

    return {
        "price": int(match.group("price").replace(",", "")),
        "noMeat": False,
        "menus": names,
    }


def parse_lines(lines: list[str]) -> dict[str, list[dict[str, Any]]]:
    meals_by_restaurant: dict[str, list[dict[str, Any]]] = {}
    current_restaurant: str | None = None

    for line in lines:
        if line.startswith("※"):
            continue

        section_match = SECTION_RE.match(line)
        if section_match is not None:
            current_restaurant = SECTION_TO_RESTAURANT.get(section_key(section_match.group("section")))
            line = section_match.group("body").strip()
            if not line:
                continue

        if current_restaurant is None:
            continue

        meal = parse_price_line(line)
        if meal is not None:
            meals_by_restaurant.setdefault(current_restaurant, []).append(meal)

    return meals_by_restaurant


def generalize_cafeteria(meal_cells: list[tuple[str, list[str]]]) -> list[dict[str, Any]]:
    payloads = []
    for meal_type, lines in meal_cells:
        meals_by_restaurant = parse_lines(lines)
        for restaurant, meals in meals_by_restaurant.items():
            if meals:
                payloads.append({"restaurant": restaurant, "type": meal_type, "meals": meals})
    return payloads
