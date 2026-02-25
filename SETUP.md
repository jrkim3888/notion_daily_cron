# Notion Daily Cron - 설정 및 파이프라인 가이드

## 개요

매일 cron으로 실행하여 Notion 워크스페이스에 Daily/Weekly/Monthly 페이지를 자동 생성하고,
Journal Overall 페이지에 동기화 블록을 추가하는 Python 자동화 도구.

---

## 환경 설정

### 1. 사전 요구사항

- Python 3.10+
- Notion Integration Token ([Notion Developers](https://developers.notion.com/)에서 생성)
- Integration이 대상 데이터베이스/페이지에 연결되어 있어야 함

### 2. 설치

```bash
git clone https://github.com/jrkim3888/notion_daily_cron.git
cd notion_daily_cron

python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

### 3. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일에 실제 값을 채워 넣는다:

```env
NOTION_TOKEN=ntn_your_integration_token

# Daily 데이터베이스
DAILY_DS_ID=데이터소스_ID
DAILY_DB_ID=데이터베이스_ID
TEMPLATE_PAGE_ID=템플릿_페이지_ID

# Weekly 데이터베이스
WEEKLY_DS_ID=데이터소스_ID
WEEKLY_DB_ID=데이터베이스_ID

# Monthly 데이터베이스
MONTHLY_DS_ID=데이터소스_ID
MONTHLY_DB_ID=데이터베이스_ID

# Journal Overall 페이지
JOURNAL_PAGE_ID=저널_페이지_ID
```

#### ID 확인 방법

- **데이터베이스 ID**: Notion에서 데이터베이스 페이지를 열고 URL에서 추출
  - `https://notion.so/xxxxxxxx?v=...` → `xxxxxxxx` 부분
- **데이터소스 ID**: `notion-client` 3.0+에서 `data_sources.query()`에 사용하는 ID
- **템플릿 페이지 ID**: Daily 페이지 생성 시 복사할 템플릿 페이지의 ID

---

## Notion 데이터베이스 구조

### Daily (일간)

| 속성 | 타입 | 설명 |
|------|------|------|
| 일간 | Title | 페이지 제목 (예: "2026-03-01 (일)") |
| 년도 | Select | 연도 (예: "2026년") |
| 날짜 | Date | 해당 날짜 |

### Weekly (주간)

| 속성 | 타입 | 설명 |
|------|------|------|
| 주간 | Title | 주간 제목 (예: "26년 9주 3.1-3.7") |
| 년도 | Select | 연도 |
| 일간 | Relation | Daily 페이지 연결 (양방향) |

### Monthly (월간)

| 속성 | 타입 | 설명 |
|------|------|------|
| 월간 | Title | 월간 제목 (예: "2026.03월") |
| 년도 | Select | 연도 |
| 주간 | Relation | Weekly 페이지 연결 (양방향) |

### Template 페이지

Daily 생성 시 복사되는 템플릿. heading_3 중 "기록 - 개인", "기록 - 업무"가 있으면
자동으로 `synced_block`으로 감싸서 Journal Overall과 동기화된다.

### Journal Overall 페이지

아래와 같은 토글 계층 구조로 관리된다:

```
▶ 2026년                          ← heading_1 (토글)
  ▶ 2026년 3월                    ← heading_2 (토글, 최신순)
    ▶ 2026년 3월 1일 (일)         ← heading_3 (토글, 최신순)
      [동기화 블록: 기록 - 개인]   ← synced_block (Daily 참조)
      [동기화 블록: 기록 - 업무]   ← synced_block (Daily 참조)
```

---

## 실행 파이프라인

### 실행 명령어

```bash
# 오늘 날짜 (cron용)
python run_daily.py

# 특정 날짜
python run_daily.py 2026-03-01

# 날짜 범위 (빠진 날짜 보정용)
python run_daily.py 2026-03-01 2026-03-05
```

### 실행 흐름

```
run_daily.py 실행
│
├─ [1/4] Daily 페이지
│   ├─ 날짜로 기존 페이지 검색 (YYYY-MM-DD 부분 매칭)
│   ├─ 없으면 → 새 페이지 생성 + 템플릿 적용
│   │   └─ "기록 - 개인/업무" heading을 synced_block으로 감싸서 복사
│   └─ 있으면 → 기존 페이지에서 synced_block ID 추출
│
├─ [2/4] Journal Overall (Daily 성공 + synced_block 존재 시)
│   ├─ 년도(H1) 토글 찾기/생성
│   ├─ 월(H2) 토글 찾기/생성
│   ├─ 날짜(H3) 토글 중복 체크
│   └─ 없으면 → 날짜 토글 생성 + synced_block 참조 추가
│
├─ [3/4] Weekly 페이지 (Daily 성공 시)
│   ├─ 해당 주 페이지 검색 (일요일~토요일 기준)
│   ├─ 없으면 → 새 페이지 생성 + Daily를 "일간" relation에 연결
│   └─ 있으면 → 기존 페이지의 "일간" relation에 Daily 추가
│
├─ [4/4] Monthly 페이지 (Weekly 성공 시)
│   ├─ 해당 월 페이지 검색
│   ├─ 없으면 → 새 페이지 생성 + Weekly를 "주간" relation에 연결
│   └─ 있으면 → 기존 페이지의 "주간" relation에 Weekly 추가
│
└─ 실행 요약 출력 (각 단계별 생성/기존/스킵/실패)
```

### 의존 관계

```
Daily ──────── 실패 시 ──→ Journal, Weekly 스킵
Weekly ─────── 실패 시 ──→ Monthly 스킵
```

단계별로 실패하면 의존하는 후속 단계는 자동 스킵되고, 로그에 사유가 기록된다.

---

## 파일 구조

```
notion_daily_cron/
├── run_daily.py           # 메인 실행 스크립트 (cron 진입점)
├── notion_config.py       # 공통 설정 (.env 로드, Notion 클라이언트)
├── add_daily.py           # Daily 페이지 생성 + 템플릿 복사
├── add_journal_entry.py   # Journal Overall 동기화 블록 추가
├── add_weekly.py          # Weekly 페이지 생성/연결
├── add_monthly.py         # Monthly 페이지 생성/연결
├── requirements.txt       # Python 의존성
├── .env.example           # 환경변수 템플릿
├── .gitignore
└── logs/                  # 실행 로그 (gitignore)
    └── notion_daily.log
```

### 모듈 의존 관계

```
run_daily.py
├── notion_config.py  ← get_client(), TEMPLATE_PAGE_ID
├── add_daily.py      ← create_daily_page()
│   └── notion_config.py ← DAILY_DS_ID, DAILY_DB_ID, TEMPLATE_PAGE_ID
├── add_journal_entry.py ← add_to_journal()
│   └── notion_config.py ← JOURNAL_PAGE_ID
├── add_weekly.py     ← ensure_weekly()
│   └── notion_config.py ← WEEKLY_DS_ID, WEEKLY_DB_ID
└── add_monthly.py    ← ensure_monthly()
    └── notion_config.py ← MONTHLY_DS_ID, MONTHLY_DB_ID
```

---

## Cron 설정

```bash
crontab -e
```

```cron
# 매일 00:05에 실행
5 0 * * * cd /path/to/notion_daily_cron && /path/to/venv/bin/python run_daily.py
```

### 로그 확인

```bash
# 최근 로그 확인
tail -50 logs/notion_daily.log

# 특정 날짜 로그 필터
grep "2026-03-01" logs/notion_daily.log
```

### 로그 출력 예시

```
2026-02-25 00:05:02 [INFO] 날짜: 2026-02-25 (수)
2026-02-25 00:05:02 [INFO] ==================================================
2026-02-25 00:05:04 [INFO] [1/4] Daily 페이지
2026-02-25 00:05:06 [INFO]   Daily 완료: 30f7a72e-xxxx-xxxx-xxxx-xxxxxxxxxxxx
2026-02-25 00:05:06 [INFO] [2/4] Journal Overall
2026-02-25 00:05:08 [INFO]   Journal 완료
2026-02-25 00:05:08 [INFO] [3/4] Weekly 페이지
2026-02-25 00:05:09 [INFO]   Weekly 완료: 30f7a72e-xxxx-xxxx-xxxx-xxxxxxxxxxxx
2026-02-25 00:05:09 [INFO] [4/4] Monthly 페이지
2026-02-25 00:05:10 [INFO]   Monthly 완료
2026-02-25 00:05:10 [INFO] ==================================================
2026-02-25 00:05:10 [INFO] [실행 요약] 2026-02-25
2026-02-25 00:05:10 [INFO]   Daily      | 생성 | 새 페이지 생성 (30f7a72e-...)
2026-02-25 00:05:10 [INFO]   Journal    | 생성 | 동기화 블록 추가 (2026년 2월 25일 (수))
2026-02-25 00:05:10 [INFO]   Weekly     | 기존 | 이미 존재하는 페이지 (30f7a72e-...)
2026-02-25 00:05:10 [INFO]   Monthly    | 기존 | 이미 존재하는 페이지 (2fa7a72e-...)
2026-02-25 00:05:10 [INFO] 완료!
```

---

## 주간 주차 계산 규칙

- **주 시작**: 일요일 ~ 토요일
- **주차 계산**: 해당 연도 첫 번째 일요일부터 카운트
- **연도 경계**: 주의 일요일이 속한 연도를 기준으로 함
  - 예: 2026-01-01(목) → "25년 52주 12.28-1.3" (일요일이 2025-12-28)
- **제목 형식**: `{연도 2자리}년 {주차}주 {시작월.일}-{종료월.일}`

---

## 멱등성 (Idempotency)

모든 단계는 중복 실행에 안전하다:

| 단계 | 중복 방지 방식 |
|------|--------------|
| Daily | 날짜(YYYY-MM-DD) 부분 검색으로 기존 페이지 확인 |
| Journal | 월 토글 내 날짜(년월일) 포함 여부로 체크 |
| Weekly | 주간 제목 정확히 일치하는 페이지 검색 |
| Monthly | 월간 제목 정확히 일치하는 페이지 검색 |
| Relation | 이미 연결된 ID면 스킵 |

같은 날짜로 여러 번 실행해도 중복 생성되지 않는다.
