import importlib.util
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import pytz
import requests
import urllib3
from bs4 import BeautifulSoup

sys.path.append(str(Path(__file__).resolve().parent))
sys.path.append(str(Path(__file__).resolve().parents[1]))
from common.types import Generalizer, Payload


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_URL = "https://snuco.snu.ac.kr/foodmenu/"
CRAWL_DAYS_AHEAD = 7
KST = pytz.timezone("Asia/Seoul")
GENERALIZER_DIR = Path(__file__).resolve().parent / "generalizers"
EXCLUDED_CAFETERIA_NAMES = {
    "기숙사식당",
    "버거운버거",
}
MEAL_TYPE_BY_CELL_CLASS = {
    "breakfast": "BREAKFAST",
    "lunch": "LUNCH",
    "dinner": "DINNER",
}
CAFETERIA_NAMES = (
    "학생회관식당",
    "자하연식당 3층",
    "자하연식당 2층",
    "예술계식당",
    "두레미담",
    "동원관식당",
    "3식당",
    "302동식당",
    "301동식당",
    "버거운버거",
    "공대간이식당",
    "75-1동 4층 푸드코트",
    "220동식당",
)
CAFETERIA_METADATA = {
    "학생회관식당": {"buildingNumber": "63동", "buildingName": "학생회관", "restaurant": "학생회관식당"},
    "자하연식당 3층": {"buildingNumber": "109동", "buildingName": "농협", "restaurant": "자하연식당 3층"},
    "자하연식당 2층": {"buildingNumber": "109동", "buildingName": "농협", "restaurant": "자하연식당 2층"},
    "예술계식당": {"buildingNumber": "74동", "buildingName": None, "restaurant": "예술계식당"},
    "두레미담": {"buildingNumber": "75-1동", "buildingName": "전망대", "restaurant": "두레미담"},
    "동원관식당": {"buildingNumber": "113동", "buildingName": None, "restaurant": "동원관식당"},
    "3식당": {"buildingNumber": "75-1동", "buildingName": "전망대", "restaurant": "3식당"},
    "302동식당": {"buildingNumber": "302동", "buildingName": None, "restaurant": "302동식당"},
    "301동식당": {"buildingNumber": "301동", "buildingName": None, "restaurant": "301동식당"},
    "버거운버거": {"buildingNumber": "75-1동", "buildingName": "전망대", "restaurant": "버거운버거"},
    "공대간이식당": {"buildingNumber": "30-2동", "buildingName": None, "restaurant": "공대간이식당"},
    "75-1동 4층 푸드코트": {"buildingNumber": "75-1동", "buildingName": "전망대", "restaurant": "4층 푸드코드"},
    "220동식당": {"buildingNumber": "220동", "buildingName": None, "restaurant": "220동식당"},
}


def load_generalizer(file_name: str) -> Generalizer:
    path = GENERALIZER_DIR / file_name
    module_name = f"snuco.generalizers.{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"SNUCO generalizer를 로드하지 못했습니다: {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


CAFETERIA_GENERALIZERS = {
    CAFETERIA_NAMES[0]: load_generalizer("학생회관식당.py"),
    CAFETERIA_NAMES[1]: load_generalizer("자하연식당_3층.py"),
    CAFETERIA_NAMES[2]: load_generalizer("자하연식당_2층.py"),
    CAFETERIA_NAMES[3]: load_generalizer("예술계식당.py"),
    CAFETERIA_NAMES[4]: load_generalizer("두레미담.py"),
    CAFETERIA_NAMES[5]: load_generalizer("동원관식당.py"),
    CAFETERIA_NAMES[6]: load_generalizer("3식당.py"),
    CAFETERIA_NAMES[7]: load_generalizer("302동식당.py"),
    CAFETERIA_NAMES[8]: load_generalizer("301동식당.py"),
    CAFETERIA_NAMES[9]: load_generalizer("버거운버거.py"),
    CAFETERIA_NAMES[10]: load_generalizer("공대간이식당.py"),
    CAFETERIA_NAMES[11]: load_generalizer("75-1동_4층_푸드코드.py"),
    CAFETERIA_NAMES[12]: load_generalizer("220동식당.py"),
}


def menu_dates(days_ahead: int = CRAWL_DAYS_AHEAD) -> list[str]:
    start_date = datetime.now(KST).date()
    return [
        (start_date + timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(days_ahead + 1)
    ]


def fetch_html(url: str) -> str:
    response = requests.get(url, timeout=10, verify=False)
    response.raise_for_status()
    return response.text


def menu_url(menu_date: str) -> str:
    return f"{DEFAULT_URL}?{urlencode({'date': menu_date})}"


def html_to_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    raw_lines = soup.get_text("\n").replace("\xa0", " ").splitlines()
    return [
        normalized
        for line in raw_lines
        if (normalized := re.sub(r"\s+", " ", line).strip())
    ]


def clean_restaurant_name(raw_restaurant_name: str) -> str:
    return re.sub(r"\(.*?\)", "", raw_restaurant_name).replace("*", "").strip()


def cell_lines(td) -> list[str]:
    return [
        normalized
        for line in td.get_text(separator="\n").replace("\xa0", " ").splitlines()
        if (normalized := re.sub(r"\s+", " ", line).strip())
    ]


def meal_type_from_cell(td) -> str | None:
    classes = td.get("class", [])
    for cell_class in classes:
        if cell_class in MEAL_TYPE_BY_CELL_CLASS:
            return MEAL_TYPE_BY_CELL_CLASS[cell_class]
    return None


def build_menu_payloads(html: str, menu_date: str) -> list[Payload]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="menu-table")
    if not table or not table.tbody:
        raise ValueError("SNUCO 식단 테이블을 찾지 못했습니다.")

    payloads: list[Payload] = []
    for tr in table.tbody.find_all("tr", recursive=False):
        tds = tr.find_all("td", recursive=False)
        if not tds:
            continue

        restaurant_name = clean_restaurant_name(tds[0].get_text(" ", strip=True))
        if restaurant_name in EXCLUDED_CAFETERIA_NAMES:
            continue

        generalizer = CAFETERIA_GENERALIZERS.get(restaurant_name)
        if generalizer is None:
            raise ValueError(f"SNUCO 식당 generalizer를 찾지 못했습니다: {restaurant_name}")
        metadata = CAFETERIA_METADATA.get(restaurant_name)
        if metadata is None:
            raise ValueError(f"SNUCO 식당 metadata를 찾지 못했습니다: {restaurant_name}")

        meal_cells = [
            (meal_type, lines)
            for td in tds[1:]
            if (meal_type := meal_type_from_cell(td)) is not None
            if (lines := cell_lines(td))
        ]
        for meal_payload in generalizer.generalize_cafeteria(meal_cells):
            payloads.append({
                **metadata,
                "date": menu_date,
                **meal_payload,
            })

    return payloads


def record_failure(
    failures: list[tuple[str, Exception]],
    menu_date: str,
    stage: str,
    url: str,
    exc: Exception,
) -> None:
    failures.append((menu_date, exc))
    print(
        f"⚠️ [{menu_date}] SNUCO 식단 {stage} 실패 "
        f"({type(exc).__name__}, url={url}): {exc}",
        file=sys.stderr,
    )


def crawl_snuco_menu(days_ahead: int = CRAWL_DAYS_AHEAD) -> tuple[list[Payload], list[tuple[str, Exception]]]:
    payloads: list[Payload] = []
    failures: list[tuple[str, Exception]] = []

    for menu_date in menu_dates(days_ahead):
        url = menu_url(menu_date)
        try:
            html = fetch_html(url)
        except requests.exceptions.RequestException as exc:
            record_failure(failures, menu_date, "fetch", url, exc)
            continue

        try:
            payloads.extend(build_menu_payloads(html, menu_date))
        except Exception as exc:
            record_failure(failures, menu_date, "parse", url, exc)

    return payloads, failures
