"""Notion API 공통 설정. 모든 ID는 .env에서 로드."""
import os
from dotenv import load_dotenv
from notion_client import Client

load_dotenv()


def get_client() -> Client:
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise RuntimeError("NOTION_TOKEN이 설정되지 않았습니다.")
    return Client(auth=token)


# Daily
DAILY_DS_ID = os.environ.get("DAILY_DS_ID", "")
DAILY_DB_ID = os.environ.get("DAILY_DB_ID", "")
TEMPLATE_PAGE_ID = os.environ.get("TEMPLATE_PAGE_ID", "")

# Weekly
WEEKLY_DS_ID = os.environ.get("WEEKLY_DS_ID", "")
WEEKLY_DB_ID = os.environ.get("WEEKLY_DB_ID", "")

# Monthly
MONTHLY_DS_ID = os.environ.get("MONTHLY_DS_ID", "")
MONTHLY_DB_ID = os.environ.get("MONTHLY_DB_ID", "")

# Journal
JOURNAL_PAGE_ID = os.environ.get("JOURNAL_PAGE_ID", "")
