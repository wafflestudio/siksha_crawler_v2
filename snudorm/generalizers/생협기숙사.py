import re
from typing import Any


TIME_RE = re.compile(r"^※\s*운영시간\s*:\s*(?P<service_time>\d{1,2}:\d{2}~\d{1,2}:\d{2})$")
PRICE_RE = re.compile(r"^(?P<menu>.+?)\s*[:;：；]\s*(?P<price>[\d,]+원)$")
MENU_NAME_SPLIT_RE = re.compile(r"\s*[,/&*]\s*")
MEAL_TYPE_ORDER = ("BREAKFAST", "LUNCH", "DINNER")


def meal_type_from_service_time(service_time: str) -> str | None:
    start_time = service_time.split("~", 1)[0]
    hour = int(start_time.split(":", 1)[0])
    if 7 <= hour <= 9:
        return "BREAKFAST"
    if 11 <= hour <= 14:
        return "LUNCH"
    if 17 <= hour <= 19:
        return "DINNER"
    return None


def parse_menu_line(line: str) -> tuple[str, int | None]:
    price_match = PRICE_RE.match(line)
    if not price_match:
        return line, None

    return (
        price_match.group("menu").strip(),
        int(price_match.group("price").replace(",", "").replace("원", "")),
    )


def normalize_menu_names(name_text: str, meal_type: str) -> list[str]:
    name_text = name_text.replace("(잇템)", "").replace("(#)", "").replace("[#]", "").strip()
    return [name.strip() for name in MENU_NAME_SPLIT_RE.split(name_text) if name.strip()]


def build_meal(names: list[str], price: int | None) -> dict[str, Any]:
    return {"price": price, "noMeat": False, "menus": names}


def parse_menu_lines(lines: list[str], meal_type: str) -> list[dict[str, Any]]:
    meals = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        menu_text, price = parse_menu_line(line)
        names = normalize_menu_names(menu_text, meal_type)
        if names:
            meals.append(build_meal(names, price))

    return meals


def generalize_cafeteria(lines: list[str]) -> list[dict[str, Any]]:
    meals_by_type: dict[str, list[dict[str, Any]]] = {}
    current_menu_lines: list[str] = []

    for line in lines:
        time_match = TIME_RE.match(line.strip())
        if time_match is None:
            current_menu_lines.append(line)
            continue

        meal_type = meal_type_from_service_time(time_match.group("service_time"))
        if meal_type is not None:
            meals = parse_menu_lines(current_menu_lines, meal_type)
            if meals:
                meals_by_type.setdefault(meal_type, []).extend(meals)

        current_menu_lines = []

    return [
        {"type": meal_type, "meals": meals_by_type[meal_type]}
        for meal_type in MEAL_TYPE_ORDER
        if meal_type in meals_by_type
    ]
