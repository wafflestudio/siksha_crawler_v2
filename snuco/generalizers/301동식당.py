import re
from typing import Any


PRICE_RE = re.compile(r"^(?P<name>.+?)\s*:\s*(?P<price>[\d,]+)\s*원")
SPLIT_RE = re.compile(r"\s*[,&*]\s*")
OR_OPTION_SEPARATOR_RE = re.compile(r"\s*(?<![A-Za-z])OR(?![A-Za-z])\s*")
SECTION_RE = re.compile(r"^<(?P<section>[^>]+)>\s*(?P<body>.*)$")
SECTION_TO_RESTAURANT = {
    "천원의아침밥": "301동식당 천원의아침밥",
    "식사": "301동식당 일반",
    "TAKE-OUT": "301동식당 TAKE-OUT",
    "301동1층 교직원전용식당": "301동 1층 교직원전용식당",
    "301동 1층 교직원전용식당": "301동 1층 교직원전용식당",
}


def normalize_names(name_text: str) -> list[str]:
    name_text = re.sub(r"^<[^>]+>", "", name_text)
    name_text = name_text.replace("(#)", "").replace("[#]", "").strip()
    return [name for part in SPLIT_RE.split(name_text) if (name := part.strip())]


def split_or_option_meals(dto_meals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded_meals = []
    for meal in dto_meals:
        option_sets = [[]]
        has_or_option = False

        for menu in meal.get("menus", []):
            options = [part.strip() for part in OR_OPTION_SEPARATOR_RE.split(menu) if part.strip()]
            if len(options) <= 1:
                for option_set in option_sets:
                    option_set.append(menu)
                continue

            has_or_option = True
            option_sets = [
                option_set + [option]
                for option_set in option_sets
                for option in options
            ]

        if has_or_option:
            for menus in option_sets:
                expanded_meals.append({
                    "price": meal["price"],
                    "noMeat": meal["noMeat"],
                    "menus": menus,
                })
            continue

        expanded_meals.append(meal)

    return expanded_meals


def canonical_restaurant(section: str) -> str | None:
    return SECTION_TO_RESTAURANT.get(re.sub(r"\s+", " ", section.strip()))


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
    current_restaurant: str | None = "301동식당 일반"
    for line in lines:
        if line.startswith("※"):
            continue

        section_match = SECTION_RE.match(line)
        if section_match is not None:
            section = section_match.group("section").strip()
            current_restaurant = canonical_restaurant(section)
            line = section_match.group("body").strip()
            if not line:
                continue

        if current_restaurant is None:
            continue

        meal = parse_price_line(line)
        if meal is None:
            continue

        meals_by_restaurant.setdefault(current_restaurant, []).append(meal)

    return {
        restaurant: split_or_option_meals(meals)
        for restaurant, meals in meals_by_restaurant.items()
    }


def generalize_cafeteria(meal_cells: list[tuple[str, list[str]]]) -> list[dict[str, Any]]:
    payloads = []
    for meal_type, lines in meal_cells:
        meals_by_restaurant = parse_lines(lines)
        for restaurant, meals in meals_by_restaurant.items():
            if meals:
                payloads.append({"restaurant": restaurant, "type": meal_type, "meals": meals})
    return payloads
