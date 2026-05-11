"""
Конфігурація MCP-сервера Worqen.
"""

import os

from dotenv import load_dotenv

# Завантажуємо .env з кореня проєкту
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
# ----- Drive файли -----
#
# FILE_FORMATS визначає як drive_client завантажує файл:
#   'docx' — нативний .docx у Drive (download_file повертає байти docx)
#   'gdoc' — Google Docs, експорт через files().export() у docx
#   'xlsx' — таблиця

FILE_IDS = {
    "tech_doc":      os.getenv("DRIVE_TECH_DOC_ID", ""),
    "user_stories":  os.getenv("DRIVE_USER_STORIES_ID", ""),
    "roadmap":       os.getenv("DRIVE_ROADMAP_ID", ""),
    "qa_report":     os.getenv("DRIVE_QA_REPORT_ID", ""),
    "prd_bootstrap": os.getenv("DRIVE_PRD_BOOTSTRAP_ID", ""),
    "prd_v1_1":      os.getenv("DRIVE_PRD_V1_1_ID", ""),
    "prd_v2":        os.getenv("DRIVE_PRD_V2_ID", ""),
    "aml_policy":    os.getenv("DRIVE_AML_ID", ""),
    "tos":           os.getenv("DRIVE_TOS_ID", ""),
    "privacy":       os.getenv("DRIVE_PRIVACY_ID", ""),
    "cookie":        os.getenv("DRIVE_COOKIE_ID", ""),
}

FILE_FORMATS = {
    "tech_doc":      "docx",
    "prd_bootstrap": "docx",
    "prd_v1_1":      "docx",
    "prd_v2":        "gdoc",
    "aml_policy":    "docx",
    "tos":           "docx",
    "privacy":       "docx",
    "cookie":        "docx",
    "user_stories":  "xlsx",
    "roadmap":       "xlsx",
    "qa_report":     "xlsx",
}

# ----- Кеш -----

CACHE_TTL_SECONDS = 30

# ----- Pagination -----

DEFAULT_LIST_LIMIT = 100
MAX_LIST_LIMIT = 500
TABLE_FORMAT_THRESHOLD = 20

# ----- Truncation для scan-tier -----

SCAN_TITLE_TRUNCATE = 200
SCAN_BUG_DESC_TRUNCATE = 150

# ----- Snapshot -----

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(PROJECT_DIR, "snapshots")
SNAPSHOT_RETENTION_DAYS = 30

# ----- Тригери для detect_conflicts -----

FORBIDDEN_TERMS = [
    "USDT",
    "Worker",
    "worker",
    "Client",
    "Hirer",
    "custody wallet",
    "Job(",
]

OBSOLETE_NUMBERS = [
    ("$0.50", "Worqs price (тепер $0.10)"),
    ("0.50 USDC", "Worqs price (тепер $0.10)"),
    ("100 welcome bonus", "Welcome bonus (тепер 60 Worqs + 100 Score)"),
    ("100 Worqs welcome", "Welcome bonus (тепер 60 Worqs + 100 Score)"),
    ("5⭐", "Rating (тепер Worqen Score)"),
    ("5 stars", "Rating (тепер Worqen Score)"),
    ("5-star", "Rating (тепер Worqen Score)"),
    ("1-5 rating", "Rating (тепер Worqen Score)"),
]

OPEN_QUESTION_MARKERS = [
    "TBD",
    "tbd",
    "потребує обговорення",
    "питання до команди",
    "потрібно вирішити",
    "?!",
    "???",
]

# ----- Team Discussions -----

TEAM_DISCUSSIONS_FOLDER_ID = os.getenv("DRIVE_TEAM_DISCUSSIONS_FOLDER_ID", "")
TEAM_DISCUSSIONS_DEFAULT_LIMIT = 50
TEAM_DISCUSSIONS_MAX_LIMIT = 200


# ----- Writer whitelists -----

US_EDITABLE_FIELDS = [
    "Title",
    "User Story",
    "Acceptance Criteria",
    "Edge Cases",
    "Dependencies",
    "Notes",
    "Related Decisions",
]

US_REQUIRED_ON_CREATE = [
    "Epic",
    "Title",
    "User Story",
    "Status",
    "Priority",
    "Version",
]

US_ALL_FIELDS = [
    "Epic", "ID", "Title", "User Story", "Status", "Priority", "Version",
    "Est. day", "Acceptance Criteria", "Edge Cases", "Dependencies",
    "Notes", "Related Decisions",
]

BUG_EDITABLE_FIELDS = [
    "Опис",
    "Де",
    "Очікувана поведінка",
    "Рекомендація для Романа",
    "Посилання на скрін",
    "Зафіксоване рішення",
    "Примітки",
]

BUG_REQUIRED_ON_CREATE = [
    "Тип",
    "Пріоритет",
    "Статус",
    "Опис",
]

BUG_ALL_FIELDS = [
    "ID", "Тип", "Пріоритет", "Джерело", "Статус",
    "Опис", "Де", "Очікувана поведінка",
    "Рекомендація для Романа", "Посилання на скрін",
    "Зафіксоване рішення", "Примітки",
]

XLSX_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
