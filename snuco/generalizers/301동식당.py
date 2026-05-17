import re
from typing import Any


PRICE_RE = re.compile(r"^(?P<name>.+?)\s*:\s*(?P<price>[\d,]+)\s*원")
SPLIT_RE = re.compile(r"\s*[,&*]\s*")
OR_OPTION_SEPARATOR_RE = re.compile(r"\s*(?<![A-Za-z])OR(?![A-Za-z])\s*")


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


def parse_lines(lines: list[str]) -> list[dict[str, Any]]:
    meals = []
    for line in lines:
        if line.startswith("※") or line.startswith("<"):
            continue

        match = PRICE_RE.match(line)
        if match is None:
            continue

        names = normalize_names(match.group("name"))
        if names:
            meals.append({
                "price": int(match.group("price").replace(",", "")),
                "noMeat": False,
                "menus": names,
            })
    return split_or_option_meals(meals)


def generalize_cafeteria(meal_cells: list[tuple[str, list[str]]]) -> list[dict[str, Any]]:
    payloads = []
    for meal_type, lines in meal_cells:
        meals = parse_lines(lines)
        if meals:
            payloads.append({"type": meal_type, "meals": meals})
    return payloads
