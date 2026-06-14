import os
from datetime import date, datetime, timedelta

import pytz


KST = pytz.timezone("Asia/Seoul")


def configured_menu_dates(days_ahead: int) -> list[str]:
    start_date = parse_date(os.getenv("CRAWLER_START_DATE")) or datetime.now(KST).date()
    end_date = parse_date(os.getenv("CRAWLER_END_DATE")) or start_date + timedelta(days=days_ahead)

    if end_date < start_date:
        raise ValueError("CRAWLER_END_DATE는 CRAWLER_START_DATE보다 빠를 수 없습니다.")

    return [
        (start_date + timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range((end_date - start_date).days + 1)
    ]


def parse_date(value: str | None) -> date | None:
    if value is None or not value.strip():
        return None
    return date.fromisoformat(value.strip())
