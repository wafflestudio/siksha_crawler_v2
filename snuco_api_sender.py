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
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Any
import requests
import urllib3
from bs4 import BeautifulSoup
import pytz

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. API 페이로드 객체 정의 (Data Object)
# ==========================================
@dataclass
class DailyMenuPayload:
    restaurant_name: str
    date: str
    breakfast: List[Dict[str, Any]]
    lunch: List[Dict[str, Any]]
    dinner: List[Dict[str, Any]]

# ==========================================
# 2. 크롤링 및 파싱 로직
# ==========================================
def clean_menu_name(text):
    text = re.sub(r'[※►].*', '', text)
    text = re.sub(r'[①②③④⑤]', '', text)
    text = text.replace('(잇템)', '').replace('[#]', '').replace('(#)', '')
    text = text.replace('< 채식뷔페 >:', '').replace('<주문식 메뉴>', '')
    text = re.sub(r'\d{1,2}:\d{2}\s*~\s*\d{1,2}:\d{2}', '', text)
    return text.strip()

def is_valid_meal(text):
    exclude_keywords = [
        "휴무", "휴점", "폐점", "휴업", "휴관", 
        "운영", "시간", "제공", "배식시간", "혼잡시간", 
        "브레이크", "break", "오전", "오후", "평일", "토요일", 
        "TakeOut", "TAKE", "결제", "문의", "학기중", "하계방학",
        "대학원생", "준비수량", "특성상", "조기품절", "가능성이", "양해"
    ]
    text_lower = text.lower()
    for keyword in exclude_keywords:
        if keyword.lower() in text_lower:
            return False
    return True

def crawl_snuco_menu():
    url = "https://snuco.snu.ac.kr/foodmenu/"
    tz = pytz.timezone('Asia/Seoul')
    today = datetime.now(tz).strftime("%Y-%m-%d")
    
    response = requests.get(url, params={"date": today}, verify=False)
    soup = BeautifulSoup(response.text, "html.parser")
    
    result = {}
    table = soup.find("table", class_="menu-table")
    
    if not table or not table.tbody:
        return result
        
    trs = table.tbody.find_all("tr", recursive=False)
    
    for tr in trs:
        tds = tr.find_all("td", recursive=False)
        if not tds:
            continue
            
        raw_restaurant_name = tds[0].text.strip()
        restaurant_name = re.sub(r'\(.*?\)', '', raw_restaurant_name).strip()
        
        if restaurant_name not in result:
            result[restaurant_name] = {today: {"아침": [], "점심": [], "저녁": []}}
            
        for td in tds[1:]:
            meal_type_class = td.get("class", [""])[0]
            
            meal_time = None
            if "breakfast" in meal_type_class:
                meal_time = "아침"
            elif "lunch" in meal_type_class:
                meal_time = "점심"
            elif "dinner" in meal_type_class:
                meal_time = "저녁"
                
            if not meal_time:
                continue
                
            raw_menus = td.get_text(separator="\n").split("\n")
            
            meal_groups = []       
            current_corner = None  
            current_menus = []     
            
            is_buffet_mode = False
            buffet_price = None
            buffet_items = []
            
            for raw_menu in raw_menus:
                menu_text = raw_menu.strip()
                if not menu_text or menu_text == "\xa0":
                    continue
                    
                if not is_valid_meal(menu_text):
                    continue
                    
                price = None
                price_match = re.search(r'([1-9]\d{0,2}(?:[,.]\d{3})*|\d+)\s*원', menu_text)
                if not price_match:
                    price_match = re.search(r'(?<!\d)([1-9]\d*00)(?!\d)', menu_text)

                if price_match:
                    price = int(re.sub(r'\D', '', price_match.group(1)))
                    menu_text = menu_text.replace(price_match.group(0), "").strip()
                
                clean_for_corner = menu_text.strip()
                
                is_corner_format = (clean_for_corner.startswith('<') and clean_for_corner.endswith('>')) or clean_for_corner == '+세미뷔페'
                
                if is_corner_format:
                    corner_name = clean_for_corner.replace('<', '').replace('>', '').replace('+', '').strip()
                    corner_name_no_space = corner_name.replace(' ', '')
                    
                    if corner_name_no_space in ["메뉴", "사이드"]:
                        continue 
                        
                    if is_buffet_mode and buffet_items:
                        current_menus.append({
                            "이름": buffet_items,
                            "가격": buffet_price
                        })
                        buffet_items = []
                        is_buffet_mode = False
                        
                    if current_menus:
                        group = {}
                        if current_corner:
                            group["코너"] = current_corner
                        group["메뉴"] = current_menus
                        meal_groups.append(group)
                        current_menus = []
                        
                    current_corner = corner_name
                    
                    if "뷔페" in corner_name_no_space or "셀프코너" in corner_name_no_space:
                        is_buffet_mode = True
                        buffet_price = price 
                        
                    continue
                    
                menu_text = clean_menu_name(menu_text)
                menu_text = re.sub(r'[:\-ㅁ\(\)]+$', '', menu_text).strip()
                
                if menu_text:
                    if is_buffet_mode:
                        buffet_items.append(menu_text)
                    else:
                        current_menus.append({
                            "이름": menu_text,
                            "가격": price
                        })
                        
            if is_buffet_mode and buffet_items:
                current_menus.append({
                    "이름": buffet_items,
                    "가격": buffet_price
                })
                
            if current_menus:
                group = {}
                if current_corner:
                    group["코너"] = current_corner
                group["메뉴"] = current_menus
                meal_groups.append(group)
                
            result[restaurant_name][today][meal_time] = meal_groups
                
    return result

# ==========================================
# 3. API 전송 로직 (인증 포함)
# ==========================================
def send_to_api(crawled_data: dict):
    # TODO 1: 실제 백엔드 API 엔드포인트로 변경
    api_url = "https://api.siksha.com/v2/menus" 
    
    # TODO 2: 발급받은 실제 API 키나 JWT 토큰으로 변경
    # 보안을 위해 환경변수(os.environ.get)를 사용하는 것이 좋지만, 우선 문자열로 하드코딩해 두었습니다.
    api_token = os.environ.get("SIKSHA_API_TOKEN", "your_secret_jwt_token_here")
    
    # HTTP 헤더 설정 (JSON 형식 명시 및 인증 토큰 포함)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_token}" # Bearer 방식이 아니면 "x-api-key": api_token 등으로 수정
    }
    
    for restaurant_name, dates in crawled_data.items():
        for date, meals in dates.items():
            
            payload_obj = DailyMenuPayload(
                restaurant_name=restaurant_name,
                date=date,
                breakfast=meals.get("아침", []),
                lunch=meals.get("점심", []),
                dinner=meals.get("저녁", [])
            )
            
            payload_json = asdict(payload_obj)
            
            print(f"🚀 [{restaurant_name} / {date}] 데이터 전송 중...")
            
            # API 전송 시뮬레이션 (현재는 서버가 없으므로 프린트만 하고 실제 요청은 주석 처리)
            # 나중에 주석(#)을 풀고 실행하시면 됩니다.
            
            '''
            try:
                # timeout=5 는 5초 이상 응답이 없으면 멈추게 하여 무한 대기를 방지합니다.
                response = requests.post(api_url, json=payload_json, headers=headers, timeout=5)
                
                # HTTP 상태 코드가 200번대(성공)가 아니면 에러를 발생시킵니다.
                response.raise_for_status() 
                
                print(f"  ✅ 전송 성공: {response.status_code}")
                
            except requests.exceptions.RequestException as e:
                print(f"  ❌ 전송 실패: {e}")
            '''

if __name__ == "__main__":
    print("🍽️ 식단 크롤링을 시작합니다...")
    crawled_data = crawl_snuco_menu()
    
    print("📡 크롤링 완료! 백엔드 API로 전송을 시작합니다...")
    send_to_api(crawled_data)
    
    print("🎉 모든 작업이 완료되었습니다!")