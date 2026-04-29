# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests",
#     "beautifulsoup4",
#     "pytz",
# ]
# ///

import json
import re
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any

import requests
import urllib3
from bs4 import BeautifulSoup
import pytz

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

VET_URL = "https://vet.snu.ac.kr/cafe_menu/"

# ==========================================
# 1. 크롤링 및 파싱 로직 (기존 로직 유지)
# ==========================================
class Fetcher:
    @staticmethod
    def fetch(url: str) -> BeautifulSoup:
        response = requests.get(url, timeout=10)
        return BeautifulSoup(response.text, "html.parser")

class DateParser:
    @staticmethod
    def parse_vet_date(date_str: str) -> datetime | None:
        pattern = r"^\d{1,2}\.\s\d{1,2}\(.\)$"
        if not re.match(pattern, date_str):
            return None

        reference_date = datetime.now() - timedelta(days=7)
        reference_year = reference_date.year
        cleaned_str = re.sub(r'\(.*\)', '', date_str).strip()
        
        try:
            dt_obj = datetime.strptime(f"{reference_year}. {cleaned_str}", "%Y. %m. %d")
            if dt_obj.date() < reference_date.date():
                dt_obj = dt_obj.replace(year=reference_year + 1)
            return dt_obj
        except ValueError:
            return None

class VetExtractor:
    def __init__(self, soup: BeautifulSoup) -> None:
        self.soup = soup

    def _extract_lunch(self) -> dict[str, str]:
        tbl = self.soup.select("table")
        if not tbl:
            return {}
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
        all_elements = self.soup.find_all(string=re.compile("저녁메뉴"))
        if not all_elements:
            return ""
        text = all_elements[0].get_text()
        return text[text.find("저녁메뉴")+5:].strip()

    def extract(self) -> dict:
        lunches = self._extract_lunch()
        dinner = self._extract_dinner()
        return {
            "수의대식당": {
                date_str: {
                    "아침": [],
                    "점심": [
                        {
                            "메뉴": [{"이름": lunch_menu, "가격": None}]
                        }
                    ],
                    "저녁": [
                        {
                            "메뉴": [{"이름": dinner, "가격": None}]
                        }
                    ]
                }
                for date_str, lunch_menu in lunches.items()
            }
        }

# ==========================================
# 2. API 전송 로직 (올바른 DTO 형식 적용)
# ==========================================
def send_to_api(crawled_data: dict):
    api_url = "https://siksha-server-dev.wafflestudio.com/crawler/meals" 
    
    # 이 부분에 발급받은(사용가능한) 액세스 토큰(JWT)을 넣어야 서버로 보내지는 요청이 인증을 통과합니다.
    api_token = ""
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_token}"
    }
    
    meal_type_map = {
        "아침": "BREAKFAST",
        "점심": "LUNCH",
        "저녁": "DINNER"
    }

    for restaurant_name, dates in crawled_data.items():
        for date, meals_by_time in dates.items():
            for meal_time_kr, meal_groups in meals_by_time.items():
                if not meal_groups:
                    continue
                    
                meal_type_en = meal_type_map[meal_time_kr]
                dto_meals = []
                
                # 각 세트 메뉴를 서버 DTO(MealItem) 형식으로 변환
                for group in meal_groups:
                    menus = []
                    price = None
                    
                    for menu_item in group.get("메뉴", []):
                        name_text = menu_item["이름"]
                        if name_text and name_text != "없음":
                            menus.append(name_text)
                        
                        if price is None and menu_item.get("가격"):
                            price = menu_item["가격"]
                            
                    if menus:
                        dto_meals.append({
                            "price": price,
                            "noMeat": False,
                            "menus": menus
                        })
                
                if not dto_meals:
                    continue
                
                # 최종 페이로드 구성
                payload = {
                    "restaurant": restaurant_name,
                    "date": date,
                    "type": meal_type_en,
                    "meals": dto_meals
                }
                
                print(f"🚀 [{restaurant_name} / {date} / {meal_type_en}] 데이터 전송 중...")
                
                try:
                    response = requests.post(api_url, json=payload, headers=headers, timeout=5)
                    response.raise_for_status() 
                    print(f"  ✅ 전송 성공: {response.status_code}")
                except requests.exceptions.RequestException as e:
                    print(f"  ❌ 전송 실패: {e}")
                    if e.response is not None:
                        print(f"     응답 내용: {e.response.text}")

if __name__ == "__main__":
    print("🍽️ 수의대 식단 크롤링을 시작합니다...")
    
    try:
        soup = Fetcher.fetch(VET_URL)
        crawled_data = VetExtractor(soup).extract()
        
        print("📡 크롤링 완료! 백엔드 API로 전송을 시작합니다...")
        send_to_api(crawled_data)
        
        print("🎉 모든 작업이 완료되었습니다!")
        
    except Exception as e:
        print(f"🛑 오류 발생: {e}")