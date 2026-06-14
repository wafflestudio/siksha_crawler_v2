import re
from typing import Any


PRICE_RE = re.compile(r"^(?P<name>.+?)\s*:?\s*(?P<price>[\d,]+)\s*원")
SPLIT_RE = re.compile(r"\s*[,&+*]\s*")
SECTION_RE = re.compile(r"^<(?P<section>[^>]+)>\s*(?P<body>.*)$")
RICE_INCLUDED_RE = re.compile(r"\s*\(\s*밥\s*포함\s*\)")
GAP_STEW_RESTAURANT = "220동식당 값찌개"
SECTION_TO_RESTAURANT = {
    "경성 돈카츠": "220동식당 경성 돈카츠",
    "경성돈카츠": "220동식당 경성 돈카츠",
    "바비든든": "220동식당 바비든든",
    "포포420": "220동식당 포포420",
    "값찌개": "220동식당 값찌개",
    "키친101": "220동식당 키친101",
}


def section_key(section: str) -> str:
    return re.sub(r"\s+", "", section.strip())


def normalize_names(name_text: str, restaurant: str) -> list[str]:
    name_text = name_text.replace("제육한접시 세트", "제육한접시")
    name_text = name_text.replace("제육한접시세트", "제육한접시")
    name_text = name_text.replace("고기한접시 세트", "고기한접시")
    name_text = name_text.replace("고기한접시세트", "고기한접시")
    name_text = name_text.replace("(#)", "").replace("[#]", "").strip()
    names = [name for part in SPLIT_RE.split(name_text) if (name := part.strip())]
    if restaurant == GAP_STEW_RESTAURANT:
        names = [RICE_INCLUDED_RE.sub("", name).strip() for name in names]
    return [name for name in names if name]


def parse_price_line(line: str, restaurant: str) -> dict[str, Any] | None:
    match = PRICE_RE.match(line)
    if match is None:
        return None

    names = normalize_names(match.group("name"), restaurant)
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
        if line.startswith("※") or line.startswith("("):
            continue

        section_match = SECTION_RE.match(line)
        if section_match is not None:
            current_restaurant = SECTION_TO_RESTAURANT.get(section_key(section_match.group("section")))
            line = section_match.group("body").strip()
            if not line:
                continue

        if current_restaurant is None:
            continue

        meal = parse_price_line(line, current_restaurant)
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
