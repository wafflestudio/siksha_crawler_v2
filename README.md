# Siksha Crawler V2

학교 식당 메뉴 페이지를 크롤링해 Siksha 서버의 crawler API로 전송하는 Python 크롤러입니다. 현재 대상은 SNUCO 식당, 기숙사 식당, 수의대 식당입니다.

## Structure

```text
.
├── common/
│   ├── pipeline.py      # JSON 저장, API 전송, 공통 실행 흐름
│   └── types.py         # payload, crawl result, generalizer protocol 타입
├── snuco/
│   ├── crawl.py         # SNUCO HTML 요청/1차 파싱/generalizer 호출
│   ├── api_sender.py    # SNUCO payload를 서버 API로 전송
│   ├── json_generator.py
│   └── generalizers/    # SNUCO 식당별 정규화
├── snudorm/
│   ├── crawl.py
│   ├── api_sender.py
│   ├── json_generator.py
│   └── generalizers/    # 아워홈, 생협기숙사 정규화
├── vet/
│   ├── crawl.py
│   ├── api_sender.py
│   ├── json_generator.py
│   └── generalizers/    # 수의대식당 정규화
└── .github/workflows/run_crawler.yml
```

각 식당 소스는 같은 흐름을 따릅니다.

```text
api_sender.py / json_generator.py
  -> common.pipeline
  -> crawl.py
  -> source별 HTML fetch 및 1차 파싱
  -> 식당별 generalizer
  -> 서버 DTO 형태 payload 생성
  -> JSON 저장 또는 API 전송
```

`api_sender.py`와 `json_generator.py`는 orchestrator 역할만 합니다. 실제 페이지 구조 처리와 식당별 메뉴 정규화는 각 source의 `crawl.py`와 `generalizers/`에 둡니다.

Source별 parsing 흐름은 각 폴더 README에 따로 정리되어 있습니다.

- [snuco/README.md](snuco/README.md)
- [snudorm/README.md](snudorm/README.md)
- [vet/README.md](vet/README.md)

## Crawling Targets

| Source | URL | Range | Notes |
| --- | --- | --- | --- |
| SNUCO | `https://snuco.snu.ac.kr/foodmenu/` | Asia/Seoul 기준 오늘부터 7일 후까지 | `기숙사식당`은 제외하고 SNUDORM이 담당 |
| SNUDORM | `https://snudorm.snu.ac.kr/foodmenu/` | Asia/Seoul 기준 오늘부터 7일 후까지 | `아워홈(901동)`, `생협기숙사(919동)` |
| VET | `https://vet.snu.ac.kr/cafe_menu/` | 페이지에 게시된 주 단위 식단 | `수의대식당` 단일 대상 |

## Payload

서버로 보내는 payload는 다음 형태입니다.

```json
{
  "buildingNumber": "109동",
  "buildingName": "농협",
  "restaurant": "자하연식당 3층",
  "date": "2026-05-17",
  "type": "LUNCH",
  "meals": [
    {
      "price": 6000,
      "noMeat": false,
      "menus": ["뚝배기순두부", "그린샐러드"]
    }
  ]
}
```

주요 필드:

| Field | Meaning |
| --- | --- |
| `buildingNumber` | 서버 DB의 `building_v2.number`와 일치해야 하는 건물 번호 |
| `buildingName` | 건물명. 없으면 `null` |
| `restaurant` | 서버 DB의 `restaurant_v2.name`과 일치해야 하는 식당명 |
| `date` | `YYYY-MM-DD` 형식의 식단 날짜 |
| `type` | `BREAKFAST`, `LUNCH`, `DINNER` |
| `meals` | 같은 식당/날짜/끼니 안의 메뉴 세트 목록 |
| `meals[].price` | 가격. 알 수 없으면 `null` |
| `meals[].noMeat` | 채식/비육류 여부. 현재는 기본적으로 `false` |
| `meals[].menus` | 정규화 전 메뉴명 목록 |

서버는 같은 `buildingNumber + restaurant + date + type` 데이터를 삭제한 뒤 새 payload로 다시 저장합니다. 따라서 같은 끼니 payload를 다시 보내면 해당 끼니는 overwrite 방식으로 동기화됩니다.

여러 세부 판매 단위가 있는 식당은 parent 식당명을 포함한 세부 단위를 `restaurant`로 평탄화해서 전송합니다. 예를 들어 `301동식당`의 `<301동1층 교직원전용식당>` 섹션은 `buildingNumber = "301동"`, `restaurant = "301동 1층 교직원전용식당"`으로 전송합니다.

`자하연식당 2층`, `자하연식당 3층`은 운영 시간과 식단표 노출이 분리되어 있어 각각 별도 restaurant로 전송합니다.

## Local Setup

이 저장소는 `uv` 기반으로 의존성을 관리합니다.

WSL/Linux에서 `uv` 설치:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv --version
```

의존성 설치:

```bash
uv sync
```

`uv sync`는 기본적으로 `.venv`를 생성합니다. 코드가 `.venv` 경로에 직접 의존하지는 않으며, 실행은 `uv run`을 기준으로 합니다.

## Generate JSON

서버로 전송하지 않고 payload 결과만 확인할 때 사용합니다.

```bash
uv run python snuco/json_generator.py
uv run python snudorm/json_generator.py
uv run python vet/json_generator.py
```

각 명령은 repository root에 다음 파일을 생성합니다.

```text
snuco_payload.json
snudorm_payload.json
vet_payload.json
```

이 파일들은 확인용 생성물이며 git에는 포함하지 않습니다.

## Send To API

API 전송에는 `CRAWLER_API_KEY`가 필요합니다.

```bash
export CRAWLER_API_KEY=...
uv run python snuco/api_sender.py
uv run python snudorm/api_sender.py
uv run python vet/api_sender.py
```

기본 API endpoint:

```text
https://siksha-server-dev.wafflestudio.com/crawler/meals
```

다른 서버로 전송하려면 `CRAWLER_API_URL`을 지정합니다.

```bash
export CRAWLER_API_URL=http://localhost:8080/crawler/meals
```

## GitHub Actions

`.github/workflows/run_crawler.yml`의 `Daily Siksha Crawler` workflow가 운영 실행을 담당합니다.

- 수동 실행: `workflow_dispatch`
- 자동 실행: 매일 UTC 20:00, 한국 시간 05:00
- 실행 순서:
  1. `python snuco/api_sender.py`
  2. `python snudorm/api_sender.py`
  3. `python vet/api_sender.py`

각 crawler step은 `continue-on-error: true`로 실행됩니다. 마지막 `크롤러 실행 결과 확인` step에서 세 crawler 중 하나라도 실패했는지 확인하고 workflow를 실패 처리합니다.

## Error Handling

SNUCO와 SNUDORM은 여러 날짜를 순회합니다.

- fetch 실패: 해당 날짜를 failure로 기록하고 다음 날짜를 계속 처리합니다.
- parse/generalizer 실패: 해당 날짜를 failure로 기록하고 다음 날짜를 계속 처리합니다.
- 일부 날짜가 실패해도 성공한 날짜의 payload는 저장하거나 전송합니다.
- 하나 이상의 failure가 있으면 최종 exit code는 실패가 됩니다.

VET은 단일 페이지 구조입니다.

- fetch 또는 parse/generalizer 실패 시 failure를 기록합니다.
- payload는 비어 있을 수 있습니다.
- failure가 있으면 최종 exit code는 실패가 됩니다.

API 전송 단계에서는 각 payload별 전송 실패를 모은 뒤, 실패가 하나라도 있으면 예외를 발생시킵니다.

## Generalizer Policy

식당별 메뉴 텍스트 구조가 서로 다르기 때문에 공통 base class로 강하게 묶지 않습니다. 각 식당은 독립적인 `generalizers/*.py` 파일에서 정규화 규칙을 관리합니다.

공통 계약은 `common/types.py`의 `Generalizer` protocol 정도만 사용합니다. 각 generalizer module은 `generalize_cafeteria(...)` 함수를 제공하고, `crawl.py`가 식당명에 맞는 generalizer를 직접 호출합니다.

새 식당을 추가할 때는 보통 다음 순서로 작업합니다.

1. 대상 source의 `generalizers/`에 식당별 정규화 파일을 추가합니다.
2. `crawl.py`의 식당명 목록과 generalizer mapping에 추가합니다.
3. `json_generator.py`로 payload를 생성해 식당명, 날짜, type, menus 구조를 확인합니다.
4. 필요하면 `api_sender.py`로 서버 API 전송을 검증합니다.
