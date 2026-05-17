# VET Crawler Parsing Guide

이 문서는 `vet/crawl.py`가 수의대 식당 페이지에서 HTML을 가져온 뒤, `수의대식당` generalizer에 데이터를 넘기기 전까지의 흐름을 설명한다.
날짜 보정과 메뉴 payload 생성 규칙은 `vet/generalizers/수의대식당.py` 안에서 관리한다.

## Entry Point

```python
crawl_vet_menu()
```

VET은 SNUCO/SNUDORM처럼 날짜별 URL을 순회하지 않는다. 수의대 식당 페이지 하나를 요청하고, 페이지에 게시된 주 단위 표를 파싱한다.

요청 URL:

```text
https://vet.snu.ac.kr/cafe_menu/
```

## Parsing Flow

전체 흐름은 다음과 같다.

```text
crawl_vet_menu()
  -> menu_url()
  -> fetch_html(url)
  -> build_menu_payloads(html)
  -> BeautifulSoup(html)
  -> extract_lunch_rows(soup)
  -> extract_dinner_menu(soup)
  -> 수의대식당.generalize_cafeteria(lunch_rows, dinner_menu)
```

## Lunch Rows

`extract_lunch_rows()`는 페이지에서 첫 번째 `table`을 찾는다.

```python
table = soup.select_one("table")
```

이후 table 내부의 `tr`을 순회하면서 `td`가 정확히 3개인 row만 점심 식단 row로 취급한다.

```python
tds = tr.select("td")
if len(tds) != 3:
    continue
```

각 row에서 첫 번째 `td`는 날짜, 두 번째 `td`는 점심 메뉴로 읽는다. 세 번째 `td`는 현재 generalizer에 넘기지 않는다.

```python
date_text = tds[0].get_text(" ", strip=True)
lunch_menu = tds[1].get_text(" ", strip=True)
lunch_rows.append((date_text, lunch_menu))
```

## Dinner Menu

`extract_dinner_menu()`는 HTML 전체에서 `저녁메뉴` 문자열이 들어간 text node를 찾는다.

```python
dinner_element = soup.find(string=re.compile("저녁메뉴"))
```

찾으면 `저녁메뉴` 뒤의 문자열만 잘라 generalizer에 넘긴다.

```python
dinner_text[dinner_text.find("저녁메뉴") + len("저녁메뉴"):].strip()
```

## Data Passed To Generalizer

실제 VET 페이지를 파싱하면 generalizer 직전 데이터는 다음처럼 만들어진다.

```python
lunch_rows = [
    ("5. 18(월)", "차돌된장찌개"),
    ("5. 19(화)", "순두부찌개"),
    ("5. 20(수)", "부대찌개"),
]

dinner_menu = ": 제육볶음"
```

이후 고정 식당명 `수의대식당`에 해당하는 generalizer를 찾아 다음처럼 호출한다.

```python
payloads = 수의대식당.generalize_cafeteria(lunch_rows, dinner_menu)
```

SNUCO/SNUDORM과 달리 VET generalizer는 날짜별 payload까지 직접 만든다. 그래서 `crawl.py`는 반환된 payload list에 `restaurant`, `date`를 추가로 붙이지 않고 그대로 반환한다.

## Failure Handling

VET은 단일 페이지 크롤러다.

- `fetch_html()`에서 `requests.exceptions.RequestException`이 발생하면 fetch failure를 기록하고 빈 payload list를 반환한다.
- table을 찾지 못하거나, 점심 row가 없거나, generalizer 호출 중 예외가 발생하면 parse failure를 기록하고 빈 payload list를 반환한다.
- failure가 있으면 `common.pipeline`에서 최종 exit code를 실패로 만든다.
