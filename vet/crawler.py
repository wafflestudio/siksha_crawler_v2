import json
import re
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

VET_URL = "https://vet.snu.ac.kr/cafe_menu/"


class Fetcher:
    @staticmethod
    def fetch(url: str) -> BeautifulSoup:
        response = requests.get(url, timeout=10)
        return BeautifulSoup(response.text, "html.parser")


class DateParser:
    @staticmethod
    def parse_vet_date(date_str: str) -> datetime | None:
        """
        input:
            date_str: str. format should be 'Month. Day(Weekday)' ex) 4. 03(금)

        output:
            datetime | None. corresponding datetime object if the input is valid, otherwise, None.
        """
        # 1. Validation: Check if it matches the pattern 'Month. Day(Weekday)'
        # Pattern: Digit(s) - Dot - Space - Digit(s) - Parentheses with content
        pattern = r"^\d{1,2}\.\s\d{1,2}\(.\)$"
        if not re.match(pattern, date_str):
            return None

        # 2. Clean and Parse
        # subtract a week for the reference to be past for all date values
        reference_date = datetime.now() - timedelta(days=7)
        reference_year = reference_date.year

        # Remove parentheses and content for parsing
        cleaned_str = re.sub(r'\(.*\)', '', date_str).strip()

        # Create date object assuming current year
        dt_obj = datetime.strptime(f"{reference_year}. {cleaned_str}", "%Y. %m. %d")

        # 3. Future-proofing: If the date is in the past, move it to next year
        if dt_obj.date() < reference_date.date():
            dt_obj = dt_obj.replace(year=reference_year + 1)

        return dt_obj


class VetExtractor:
    def __init__(self, soup: BeautifulSoup) -> None:
        self.soup = soup

    def _extract_lunch(self) -> dict[str, str]:
        """
        returns dict[str, str]
            key: date string formatted with %Y-%m-%d
            value: the lunch of the date
        """
        tbl = self.soup.select("table")
        assert len(tbl) == 1
        tbl = tbl[0]
        lunches = {}
        for tr in tbl.select("tr"):
            tds = tr.select("td")
            if len(tds) != 3:
                continue
            date = DateParser.parse_vet_date(tds[0].get_text().strip())
            if date is None:
                continue
            lunches[date.strftime("%Y-%m-%d")] = tds[1].get_text().strip()
        return lunches

    def _extract_dinner(self) -> str:
        "returns the dinner of the week"
        all_elements = self. soup.find_all(string=re.compile("저녁메뉴"))
        assert len(all_elements) == 1
        text = all_elements[0].get_text()
        return text[text.find("저녁메뉴")+5:].strip()

    def extract(self) -> dict:
        lunches = self._extract_lunch()
        dinner = self._extract_dinner()
        return {
            "수의대식당": {
                date_str: {
                    "아침": [],
                    "점심": [{"메뉴": [{"이름": lunch_menu, "가격": None}]}],
                    "저녁": [{"메뉴": [{"이름": dinner, "가격": None}]}]
                }
                for date_str, lunch_menu in lunches.items()
            }
        }


if __name__ == "__main__":
    soup = Fetcher.fetch(VET_URL)
    data = VetExtractor(soup).extract()
    with open("./vet/menu.json", 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
