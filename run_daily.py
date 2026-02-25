"""
매일 실행하는 통합 스크립트.
오늘 날짜 기준으로:
1. Daily 페이지 생성 (템플릿 적용)
2. Journal Overall에 동기화 블록 추가
3. Weekly 페이지 생성/연결
4. Monthly 페이지 생성/연결
"""
import sys
import logging
import traceback
from datetime import date
from pathlib import Path
from notion_client import APIResponseError
from notion_config import get_client, TEMPLATE_PAGE_ID
LOG_DIR = Path(__file__).parent / "logs"

_DAY_NAMES_KO = ["월", "화", "수", "목", "금", "토", "일"]

log = logging.getLogger("notion_daily")


def setup_logging():
    """콘솔 + 파일 로깅 설정. 중복 호출 시 핸들러를 추가하지 않는다."""
    if log.handlers:
        return

    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / "notion_daily.log"

    log.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 콘솔: INFO 이상
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    log.addHandler(console)

    # 파일: DEBUG 이상 (append 모드)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    log.addHandler(file_handler)

    log.info(f"로그 파일: {log_file}")


def make_daily_title(d: date) -> str:
    day_name = _DAY_NAMES_KO[d.weekday()]
    return f"{d.isoformat()} ({day_name})"


def make_journal_params(d: date) -> dict:
    return {
        "year": f"{d.year}년",
        "month": f"{d.year}년 {d.month}월",
        "date_title": f"{d.year}년 {d.month}월 {d.day}일 ({_DAY_NAMES_KO[d.weekday()]})",
    }


def run(target_date: date | None = None):
    setup_logging()

    today = target_date or date.today()
    title = make_daily_title(today)
    date_str = today.isoformat()
    year = f"{today.year}년"

    log.info(f"날짜: {date_str} ({_DAY_NAMES_KO[today.weekday()]})")
    log.info("=" * 50)

    notion = get_client()

    daily_page_id = None
    synced_ids = {}
    weekly_page_id = None

    # 결과 추적: {step: {"status": "생성"|"기존"|"스킵"|"실패", "detail": "..."}}
    results = {}

    # 1. Daily
    log.info("[1/4] Daily 페이지")
    try:
        from add_daily import create_daily_page
        daily_page, synced_ids, is_new = create_daily_page(
            notion, title, date_str, year, TEMPLATE_PAGE_ID
        )
        daily_page_id = daily_page["id"]
        if is_new:
            results["Daily"] = {"status": "생성", "detail": f"새 페이지 생성 ({daily_page_id})"}
        else:
            results["Daily"] = {"status": "기존", "detail": f"이미 존재하는 페이지 ({daily_page_id})"}
        log.info(f"  Daily 완료: {daily_page_id}")
    except APIResponseError as e:
        msg = f"Notion API 오류: {e.code} - {e.message}"
        results["Daily"] = {"status": "실패", "detail": msg}
        log.error(f"  Daily 실패: {msg}")
    except Exception as e:
        results["Daily"] = {"status": "실패", "detail": str(e)}
        log.error(f"  Daily 실패: {e}")
        log.debug(traceback.format_exc())

    # 2. Journal Overall
    log.info("[2/4] Journal Overall")
    if daily_page_id and synced_ids:
        try:
            from add_journal_entry import add_to_journal
            journal = make_journal_params(today)
            added = add_to_journal(
                notion, journal["year"], journal["month"],
                journal["date_title"], synced_ids,
            )
            if added:
                results["Journal"] = {"status": "생성", "detail": f"동기화 블록 추가 ({journal['date_title']})"}
            else:
                results["Journal"] = {"status": "기존", "detail": f"날짜 토글 이미 존재 ({journal['date_title']})"}
            log.info("  Journal 완료")
        except APIResponseError as e:
            msg = f"Notion API 오류: {e.code} - {e.message}"
            results["Journal"] = {"status": "실패", "detail": msg}
            log.error(f"  Journal 실패: {msg}")
        except Exception as e:
            results["Journal"] = {"status": "실패", "detail": str(e)}
            log.error(f"  Journal 실패: {e}")
            log.debug(traceback.format_exc())
    elif not daily_page_id:
        results["Journal"] = {"status": "스킵", "detail": "Daily 페이지 생성 실패"}
        log.warning("  Daily 실패로 스킵")
    else:
        results["Journal"] = {"status": "스킵", "detail": "synced_block이 없음"}
        log.info("  synced_block이 없어 스킵")

    # 3. Weekly
    log.info("[3/4] Weekly 페이지")
    if daily_page_id:
        try:
            from add_weekly import ensure_weekly
            weekly_page, is_new = ensure_weekly(notion, date_str, daily_page_id)
            weekly_page_id = weekly_page["id"]
            if is_new:
                results["Weekly"] = {"status": "생성", "detail": f"새 페이지 생성 ({weekly_page_id})"}
            else:
                results["Weekly"] = {"status": "기존", "detail": f"이미 존재하는 페이지 ({weekly_page_id})"}
            log.info(f"  Weekly 완료: {weekly_page_id}")
        except APIResponseError as e:
            msg = f"Notion API 오류: {e.code} - {e.message}"
            results["Weekly"] = {"status": "실패", "detail": msg}
            log.error(f"  Weekly 실패: {msg}")
        except Exception as e:
            results["Weekly"] = {"status": "실패", "detail": str(e)}
            log.error(f"  Weekly 실패: {e}")
            log.debug(traceback.format_exc())
    else:
        results["Weekly"] = {"status": "스킵", "detail": "Daily 페이지 생성 실패"}
        log.warning("  Daily 실패로 스킵")

    # 4. Monthly
    log.info("[4/4] Monthly 페이지")
    if weekly_page_id:
        try:
            from add_monthly import ensure_monthly
            monthly_page, is_new = ensure_monthly(notion, date_str, weekly_page_id)
            if is_new:
                results["Monthly"] = {"status": "생성", "detail": f"새 페이지 생성 ({monthly_page['id']})"}
            else:
                results["Monthly"] = {"status": "기존", "detail": f"이미 존재하는 페이지 ({monthly_page['id']})"}
            log.info("  Monthly 완료")
        except APIResponseError as e:
            msg = f"Notion API 오류: {e.code} - {e.message}"
            results["Monthly"] = {"status": "실패", "detail": msg}
            log.error(f"  Monthly 실패: {msg}")
        except Exception as e:
            results["Monthly"] = {"status": "실패", "detail": str(e)}
            log.error(f"  Monthly 실패: {e}")
            log.debug(traceback.format_exc())
    else:
        results["Monthly"] = {"status": "스킵", "detail": "Weekly 페이지 생성 실패"}
        log.warning("  Weekly 실패로 스킵")

    # 실행 요약
    log.info("=" * 50)
    log.info(f"[실행 요약] {date_str}")
    has_error = False
    for step in ["Daily", "Journal", "Weekly", "Monthly"]:
        r = results.get(step, {"status": "미실행", "detail": ""})
        status = r["status"]
        detail = r["detail"]
        if status == "실패":
            has_error = True
            log.error(f"  {step:10s} | {status} | {detail}")
        else:
            log.info(f"  {step:10s} | {status} | {detail}")

    if has_error:
        log.error("완료 (에러 있음)")
        sys.exit(1)
    else:
        log.info("완료!")


if __name__ == "__main__":
    args = sys.argv[1:]

    if len(args) == 0:
        # 인자 없음 → 오늘 날짜
        run()
    elif len(args) == 1:
        # 날짜 1개 → 해당 날짜
        try:
            target = date.fromisoformat(args[0])
        except ValueError:
            print(f"잘못된 날짜 형식: {args[0]} (YYYY-MM-DD)")
            sys.exit(1)
        run(target)
    elif len(args) == 2:
        # 날짜 2개 → 범위 순회
        try:
            start = date.fromisoformat(args[0])
            end = date.fromisoformat(args[1])
        except ValueError:
            print(f"잘못된 날짜 형식 (YYYY-MM-DD): {args[0]} {args[1]}")
            sys.exit(1)
        if start > end:
            print(f"시작일({start})이 종료일({end})보다 큽니다.")
            sys.exit(1)
        from datetime import timedelta
        current = start
        while current <= end:
            run(current)
            current += timedelta(days=1)
    else:
        print("사용법: python run_daily.py [날짜] [종료날짜]")
        print("  python run_daily.py              → 오늘 날짜")
        print("  python run_daily.py 2026-03-01   → 특정 날짜")
        print("  python run_daily.py 2026-03-01 2026-03-05 → 범위")
        sys.exit(1)
