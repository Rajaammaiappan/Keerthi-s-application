"""
Generic helpers shared across the app:
- flexible column-name matching (so slightly different header spellings
  from different Excel files still work)
- Base location value normalization (Yes/No/Y/N/TRUE/FALSE/1/0)
- a tiny in-memory store so a user's parsed dataset survives between
  page navigations without needing a database
"""
from __future__ import annotations

import re
import threading
import uuid
from typing import Optional

# ---------------------------------------------------------------------------
# Column name matching
# ---------------------------------------------------------------------------

def _normalize_header(name: str) -> str:
    """Lowercase, strip punctuation/whitespace so headers compare loosely."""
    name = str(name).strip().lower()
    name = re.sub(r"[^a-z0-9]+", "", name)
    return name


# Candidate spellings for each required dimension column. New synonyms can
# be added here without touching any other part of the app.
COLUMN_SYNONYMS = {
    "sno": ["sno", "s.no", "serialno", "slno", "sl.no", "id", "rowno"],
    "vm_product": ["vmproduct", "product", "vm"],
    "customer_account": ["customeraccount", "customer", "account", "client"],
    "component": ["component", "workstream", "tower"],
    "country": ["country"],
    "location": ["location", "site", "city"],
    "base_location": ["baselocation", "isbase", "basesite", "base"],
}


def find_column(actual_columns: list[str], field_key: str) -> Optional[str]:
    """Return the actual column name in the workbook that best matches
    the given logical field (e.g. 'customer_account')."""
    synonyms = {_normalize_header(s) for s in COLUMN_SYNONYMS[field_key]}
    for col in actual_columns:
        if _normalize_header(col) in synonyms:
            return col
    return None


# FTE columns look like FTE_<Month>_<Year> or FTE_<Month>_<Year>_<Category>
FTE_COLUMN_RE = re.compile(
    r"^FTE[_\s]*([A-Za-z]{3,9})[_\s]*(\d{4})(?:[_\s]+([A-Za-z]+))?$",
    re.IGNORECASE,
)

MONTH_ORDER = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

CATEGORY_ALIASES = {
    "internal": "Internal",
    "swc": "SWC",
    "external": "External",
    "others": "Others",
    "other": "Others",
}


def parse_fte_column(col_name: str):
    """
    Given a column name, return (period_label, category) if it looks like
    an FTE column, else None.

    period_label is normalized to 'Mon-YYYY' (e.g. 'Dec-2025') and used
    for both display and chronological sorting.
    category is one of Internal/SWC/External/Others/Total.
    """
    m = FTE_COLUMN_RE.match(str(col_name).strip())
    if not m:
        return None
    month_raw, year, cat_raw = m.groups()
    month_key = month_raw.lower()
    if month_key not in MONTH_ORDER:
        return None
    month_num = MONTH_ORDER[month_key]
    month_abbrev = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ][month_num - 1]
    period_label = f"{month_abbrev}-{year}"
    sort_key = int(year) * 100 + month_num

    if cat_raw is None:
        category = "Total"
    else:
        category = CATEGORY_ALIASES.get(cat_raw.lower())
        if category is None:
            return None
    return period_label, category, sort_key


# ---------------------------------------------------------------------------
# Base location value normalization
# ---------------------------------------------------------------------------

TRUE_VALUES = {"yes", "y", "true", "1", "1.0"}
FALSE_VALUES = {"no", "n", "false", "0", "0.0", "", "none", "nan"}


def normalize_base_flag(value) -> Optional[bool]:
    """Return True/False, or None if the value is blank/unrecognized."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return None


# ---------------------------------------------------------------------------
# In-memory dataset store (single-process; fine for this tool's scale)
# ---------------------------------------------------------------------------

class DatasetStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._store: dict[str, "Dataset"] = {}

    def new_id(self) -> str:
        return uuid.uuid4().hex

    def put(self, dataset_id: str, dataset) -> None:
        with self._lock:
            self._store[dataset_id] = dataset

    def get(self, dataset_id: str):
        with self._lock:
            return self._store.get(dataset_id)

    def delete(self, dataset_id: str) -> None:
        with self._lock:
            self._store.pop(dataset_id, None)


store = DatasetStore()
SESSION_COOKIE = "fte_dataset_id"
