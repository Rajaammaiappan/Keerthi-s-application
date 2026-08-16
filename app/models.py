"""
Dataclasses / typed containers used throughout the FTE Location Planner.

The application never hard-codes business values (customer names, location
names, periods, etc). Everything here is a generic container that is filled
in dynamically from whatever Excel file the user uploads.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


# Canonical FTE categories the app understands. "Total" is always included
# because every uploaded workbook has a period-level total column
# (e.g. FTE_Dec_2025). Category-level columns (Internal/SWC/External/Others)
# are optional -- if a workbook doesn't have them, only "Total" is offered.
CANONICAL_CATEGORIES = ["Internal", "SWC", "External", "Others"]
TOTAL_CATEGORY = "Total"


@dataclass
class DetectedColumns:
    """Result of scanning the uploaded workbook's header row."""
    sno: Optional[str] = None
    vm_product: Optional[str] = None
    customer_account: Optional[str] = None
    component: Optional[str] = None
    country: Optional[str] = None
    location: Optional[str] = None
    base_location: Optional[str] = None
    # period -> {category_or_'Total': column_name}
    fte_columns: dict = field(default_factory=dict)
    unmatched_columns: list = field(default_factory=list)
    missing_required: list = field(default_factory=list)


@dataclass
class Dataset:
    """
    Fully parsed & normalized representation of one uploaded workbook.

    raw_df   : the original dataframe exactly as uploaded (for export/reference)
    long_df  : normalized long-format data, one row per
               (S.No, dimension columns..., Period, Category, FTE)
    dims     : dict of dimension name -> sorted list of distinct values found
    periods  : ordered list of period labels found in the workbook, in
               chronological order as they appeared left-to-right in Excel
    categories: list of FTE categories available (subset of CANONICAL_CATEGORIES + Total)
    warnings : data-quality warnings collected while parsing
    """
    raw_df: pd.DataFrame
    long_df: pd.DataFrame
    dims: dict
    periods: list
    categories: list
    warnings: list
    detected_columns: DetectedColumns
    source_filename: str
