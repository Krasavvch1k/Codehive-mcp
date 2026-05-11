"""Configuration for the Codehive module in worqen-mcp."""

import os
from dotenv import load_dotenv

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(_ROOT, ".env"))

CODEHIVE_ROOT_FOLDER_ID = os.getenv("CODEHIVE_ROOT_FOLDER_ID", "")

CODEHIVE_DEFAULT_LIST_LIMIT = 100
CODEHIVE_MAX_LIST_LIMIT = 500
CODEHIVE_DEFAULT_SEARCH_LIMIT = 20
CODEHIVE_MAX_SEARCH_LIMIT = 100
CODEHIVE_DEFAULT_SEARCH_CONTEXT_CHARS = 200
CODEHIVE_MAX_RECURSION_DEPTH = 3

GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDES_MIME = "application/vnd.google-apps.presentation"
GOOGLE_FOLDER_MIME = "application/vnd.google-apps.folder"
