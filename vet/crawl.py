import re
import sys
from pathlib import Path
import requests
import urllib3
from bs4 import BeautifulSoup

sys.path.append(str(Path(__file__).resolve().parent))
sys.path.append(str(Path(__file__).resolve().parents[1]))
from common.types import Payload
from vet.generalizers import 수의대식당


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_URL = "https://vet.snu.ac.kr/cafe_menu/"
RESTAURANT_NAME = "수의대식당"
CAFETERIA_GENERALIZERS = {
    RESTAURANT_NAME: 수의대식당,
}


def menu_url() -> str:
    return DEFAULT_URL


def fetch_html(url: str) -> str:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.text


def html_to_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    raw_lines = soup.get_text("\n").replace("\xa0", " ").splitlines()
    return [
        normalized
        for line in raw_lines
        if (normalized := re.sub(r"\s+", " ", line).strip())
    ]


def extract_lunch_rows(soup: BeautifulSoup) -> list[tuple[str, str]]:
    table = soup.select_one("table")
    if table is None:
        raise ValueError("VET 식단 테이블을 찾지 못했습니다.")

    lunch_rows: list[tuple[str, str]] = []
    for tr in table.select("tr"):
        tds = tr.select("td")
        if len(tds) != 3:
            continue

        date_text = tds[0].get_text(" ", strip=True)
        lunch_menu = tds[1].get_text(" ", strip=True)
        lunch_rows.append((date_text, lunch_menu))

    if not lunch_rows:
        raise ValueError("VET 점심 식단 행을 찾지 못했습니다.")

    return lunch_rows


def extract_dinner_menu(soup: BeautifulSoup) -> str:
    dinner_element = soup.find(string=re.compile("저녁메뉴"))
    if dinner_element is None:
        return ""

    dinner_text = dinner_element.get_text()
    return dinner_text[dinner_text.find("저녁메뉴") + len("저녁메뉴"):].strip()


def build_menu_payloads(html: str) -> list[Payload]:
    soup = BeautifulSoup(html, "html.parser")
    lunch_rows = extract_lunch_rows(soup)
    dinner_menu = extract_dinner_menu(soup)

    generalizer = CAFETERIA_GENERALIZERS.get(RESTAURANT_NAME)
    if generalizer is None:
        raise ValueError(f"VET 식당 generalizer를 찾지 못했습니다: {RESTAURANT_NAME}")

    payloads = generalizer.generalize_cafeteria(lunch_rows, dinner_menu)
    if not payloads:
        raise ValueError("VET 식단 payload를 생성하지 못했습니다.")

    return payloads


def record_failure(
    failures: list[tuple[str, Exception]],
    stage: str,
    url: str,
    exc: Exception,
) -> None:
    failures.append((RESTAURANT_NAME, exc))
    print(
        f"⚠️ VET 식단 {stage} 실패 "
        f"({type(exc).__name__}, url={url}): {exc}",
        file=sys.stderr,
    )


def crawl_vet_menu() -> tuple[list[Payload], list[tuple[str, Exception]]]:
    url = menu_url()
    failures: list[tuple[str, Exception]] = []

    try:
        html = fetch_html(url)
    except requests.exceptions.RequestException as exc:
        record_failure(failures, "fetch", url, exc)
        return [], failures

    try:
        return build_menu_payloads(html), failures
    except Exception as exc:
        record_failure(failures, "parse", url, exc)
        return [], failures
