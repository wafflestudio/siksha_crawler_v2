# SNUCO Crawler Parsing Guide

이 문서는 `snuco/crawl.py`가 SNUCO 식단 페이지에서 HTML을 가져온 뒤, 식당별 generalizer에 데이터를 넘기기 전까지의 흐름을 설명한다.
식당별 메뉴 정규화 규칙은 `snuco/generalizers/` 안에서 관리한다.

## Entry Point

```python
crawl_snuco_menu(days_ahead: int = CRAWL_DAYS_AHEAD)
```

기본값은 `CRAWL_DAYS_AHEAD = 7`이다. `Asia/Seoul` 기준 오늘부터 7일 후까지, 총 8개 날짜를 순회한다.

```text
2026-05-17
2026-05-18
...
2026-05-24
```

각 날짜는 `menu_url(menu_date)`를 통해 다음 URL로 변환된다.

```text
https://snuco.snu.ac.kr/foodmenu/?date=YYYY-MM-DD
```

## Parsing Flow

전체 흐름은 다음과 같다.

```text
crawl_snuco_menu()
  -> menu_dates()
  -> menu_url(menu_date)
  -> fetch_html(url)
  -> build_menu_payloads(html, menu_date)
  -> BeautifulSoup(html)
  -> table.menu-table 찾기
  -> tbody > tr 단위로 식당 row 순회
  -> 식당명 정리
  -> 끼니별 td를 (meal_type, lines)로 변환
  -> 식당별 generalizer.generalize_cafeteria(meal_cells)
```

## Table Selection

`build_menu_payloads()`는 HTML에서 다음 table을 찾는다.

```python
table = soup.find("table", class_="menu-table")
```

이 table의 `tbody > tr` 하나를 식당 하나의 row로 본다. 각 row의 첫 번째 `td`는 식당명이고, 이후 `td`들은 아침/점심/저녁 cell이다.

## Restaurant Name

식당명은 첫 번째 `td`에서 가져온 뒤 `clean_restaurant_name()`으로 정리한다.

```python
restaurant_name = clean_restaurant_name(tds[0].get_text(" ", strip=True))
```

정리 규칙:

- 괄호 안 텍스트 제거
- `*` 제거
- 앞뒤 공백 제거

예시:

```text
학생회관식당(식당 위치 안내) -> 학생회관식당
```

`기숙사식당`은 SNUDORM 크롤러가 담당하므로 SNUCO에서 skip한다.

## Meal Cell Selection

식당 row의 두 번째 `td`부터는 끼니 cell이다. `meal_type_from_cell()`은 `td`의 class를 보고 서버 type을 정한다.

| HTML class | Type |
| --- | --- |
| `breakfast` | `BREAKFAST` |
| `lunch` | `LUNCH` |
| `dinner` | `DINNER` |

각 cell의 텍스트는 `cell_lines(td)`에서 줄 단위 list로 변환된다.

```python
[
    normalized
    for line in td.get_text(separator="\n").replace("\xa0", " ").splitlines()
    if (normalized := re.sub(r"\s+", " ", line).strip())
]
```

즉 HTML 내부의 줄바꿈, `<br>`, block text를 기준으로 나눠 빈 줄을 제거하고, 공백을 하나로 압축한다.

## Data Passed To Generalizer

식당별 generalizer에는 다음 형태의 `meal_cells`가 전달된다.

```python
[
    ("BREAKFAST", ["..."]),
    ("LUNCH", ["..."]),
    ("DINNER", ["..."]),
]
```

실제 `2026-05-15` SNUCO 페이지에서 `학생회관식당` row를 파싱하면 generalizer 직전 데이터는 다음처럼 만들어진다.

```python
restaurant_name = "학생회관식당"

meal_cells = [
    (
        "BREAKFAST",
        [
            "토마토스크램블에그(#) : 3,000원",
            "※ 운영시간 : 08:00~10:00",
        ],
    ),
    (
        "LUNCH",
        [
            "목살슬라이스덮밥 : 6,000원",
            "무쇠고기국백반 : 3,000원",
            "해물짬뽕수제비(#) : 5,500원",
            "※ 운영시간 : 11:00~14:30",
        ],
    ),
]
```

이후 `CAFETERIA_GENERALIZERS[restaurant_name]`에서 식당별 generalizer module을 찾고 다음처럼 호출한다.

```python
meal_payloads = generalizer.generalize_cafeteria(meal_cells)
```

`crawl.py`는 generalizer가 반환한 meal payload에 `restaurant`, `date`를 붙여 최종 payload list에 추가한다.

```python
{
    "restaurant": restaurant_name,
    "date": menu_date,
    **meal_payload,
}
```

## Failure Handling

날짜별로 fetch와 parse 단계를 분리해 처리한다.

- `fetch_html()`에서 `requests.exceptions.RequestException`이 발생하면 해당 날짜를 fetch failure로 기록하고 다음 날짜로 넘어간다.
- `build_menu_payloads()` 또는 generalizer 호출 중 예외가 발생하면 해당 날짜를 parse failure로 기록하고 다음 날짜로 넘어간다.
- 하나 이상의 failure가 있으면 `common.pipeline`에서 최종 exit code를 실패로 만든다.
