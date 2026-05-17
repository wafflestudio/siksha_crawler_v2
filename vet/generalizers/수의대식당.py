import re
from datetime import datetime, timedelta
from typing import Any

import pytz


KST = pytz.timezone("Asia/Seoul")
RESTAURANT_NAME = "수의대식당"
DATE_PATTERN = r"^\d{1,2}\.\s\d{1,2}\(.\)$"


def parse_vet_date(date_text: str) -> str | None:
    if not re.match(DATE_PATTERN, date_text):
        return None

    reference_date = datetime.now(KST).replace(tzinfo=None) - timedelta(days=7)
    reference_year = reference_date.year
    cleaned_text = re.sub(r"\(.*\)", "", date_text).strip()

    try:
        parsed_date = datetime.strptime(f"{reference_year}. {cleaned_text}", "%Y. %m. %d")
    except ValueError:
        return None

    if parsed_date.date() < reference_date.date():
        parsed_date = parsed_date.replace(year=reference_year + 1)

    return parsed_date.strftime("%Y-%m-%d")


def build_meal_payload(menu_text: str) -> dict[str, Any] | None:
    normalized_menu = re.sub(r"\s+", " ", menu_text).strip()
    normalized_menu = re.sub(r"^[\s:：-]+", "", normalized_menu).strip()
    if not normalized_menu or normalized_menu == "없음" or "휴무" in normalized_menu:
        return None

    return {
        "price": None,
        "noMeat": False,
        "menus": [normalized_menu],
    }


def generalize_cafeteria(
    lunch_rows: list[tuple[str, str]],
    dinner_menu: str,
) -> list[dict[str, Any]]:
    dinner_payload = build_meal_payload(dinner_menu)
    payloads: list[dict[str, Any]] = []

    for raw_date, lunch_menu in lunch_rows:
        menu_date = parse_vet_date(raw_date)
        if menu_date is None:
            continue

        lunch_payload = build_meal_payload(lunch_menu)
        if lunch_payload is not None:
            payloads.append({
                "restaurant": RESTAURANT_NAME,
                "date": menu_date,
                "type": "LUNCH",
                "meals": [lunch_payload],
            })

        if dinner_payload is not None:
            payloads.append({
                "restaurant": RESTAURANT_NAME,
                "date": menu_date,
                "type": "DINNER",
                "meals": [dinner_payload],
            })

    return payloads
